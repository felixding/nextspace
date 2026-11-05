#!/usr/bin/env python3
"""Run the pinned Firefox fixture and native references in a private Wayland session."""
import argparse,base64,hashlib,json,os,select,signal,socket,subprocess,sys,tempfile,time
from pathlib import Path
from marionette import Marionette

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--firefox',type=Path,required=True)
parser.add_argument('--native-library',type=Path,required=True)
parser.add_argument('--hook',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--library-path',action='append',default=[])
parser.add_argument('--compositor',default='/usr/NextSpace/bin/nextspace-compositor')
parser.add_argument('--backend',required=True)
parser.add_argument('--port',type=int,default=2829)
parser.add_argument('--controls',action='store_true',help='Exercise the optional checkbox/radio input binding')
args=parser.parse_args();here=Path(__file__).resolve().parent
pin=json.loads((here/'binary-pin.json').read_text())
def digest(path):
    with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()
for name,path in (('firefox-esr',args.firefox),('libxul.so',args.firefox.parent/'libxul.so')):
    if not path.is_file():parser.error('Missing '+str(path))
    if digest(path)!=pin['files_sha256']['usr/lib/firefox-esr/'+name]:parser.error('Unsupported '+name)
for path in (args.native_library,args.hook):
    if not path.is_file():parser.error('Missing '+str(path))
if not 1<=args.port<=65535:parser.error('Invalid private Marionette port')
with socket.socket() as probe:
    try:probe.bind(('127.0.0.1',args.port))
    except OSError:parser.error('Private Marionette port already in use')
args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=True)
def terminate(process):
    if process is None or process.poll() is not None:return
    process.terminate()
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:process.kill();process.wait()
def interrupted(signum,frame):raise KeyboardInterrupt
signal.signal(signal.SIGTERM,interrupted)
with tempfile.TemporaryDirectory(prefix='fixture-',dir=args.output) as temporary:
    root=Path(temporary);root.chmod(0o700)
    runtime=root/'runtime';runtime.mkdir(mode=0o700)
    profile=root/'profile';profile.mkdir()
    preferences={'marionette.port':args.port,'browser.shell.checkDefaultBrowser':False,
        'browser.startup.page':0,'browser.startup.homepage':'about:blank',
        'browser.aboutwelcome.enabled':False,'browser.startup.homepage_override.mstone':'ignore',
        'datareporting.policy.dataSubmissionEnabled':False,'gfx.webrender.software':True}
    (profile/'user.js').write_text(''.join('user_pref('+json.dumps(k)+', '+json.dumps(v)+');\n' for k,v in preferences.items()))
    env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),WLR_BACKENDS='headless',WLR_RENDERER='pixman',MOZ_ENABLE_WAYLAND='1')
    for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','LD_PRELOAD','GTK_MODULES','QT_QPA_GENERIC_PLUGINS'):env.pop(key,None)
    if args.library_path:env['LD_LIBRARY_PATH']=':'.join(args.library_path)
    parent,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);parent.settimeout(5)
    server=helper=browser=None
    def control(command):parent.sendall(command.encode());return json.loads(parent.recv(65536))
    def connect_client():
        deadline=time.monotonic()+5
        while True:
            assert browser.poll() is None,'Owned Firefox exited'
            try:return Marionette(args.port)
            except (ConnectionRefusedError,EOFError):
                # A prior Marionette transport may still be closing. Wait on
                # this owned browser; never restart it on an observation race.
                assert time.monotonic()<deadline,'Owned Marionette connection'
                time.sleep(.02)
    def native_ledger():
        trace=[json.loads(line) for line in (args.output/'native.jsonl').read_text().splitlines()]
        live=set();created=destroyed=0
        for event in trace:
            if event['event']=='native-form-control':
                key=event['process'],event['control'],event['kind'];assert key not in live;live.add(key);created+=1
            elif event['event'] in ('native-progress-destroy','native-form-destroy'):
                key=event['process'],event['control'],event.get('kind',5);assert key in live;live.remove(key);destroyed+=1
        return trace,live,created,destroyed
    try:
        server=subprocess.Popen([args.compositor,'-c',str(child.fileno())],pass_fds=[child.fileno()],env=env,
            stdout=subprocess.PIPE,stderr=(args.output/'compositor.log').open('w'),text=True);child.close()
        assert select.select([server.stdout],[],[],10)[0],'Compositor startup'
        line=server.stdout.readline().strip();assert line.startswith('WAYLAND_DISPLAY=')
        env['WAYLAND_DISPLAY']=line.split('=',1)[1]
        output=control('outputs')[0]['name'];assert control('resize-output '+output+' 1280 900')['ok']
        endpoint=root/'native.sock'
        helper=subprocess.Popen([sys.executable,str(here.parent/'ChromiumScrollers/helper.py'),
            '--library',str(args.native_library.resolve()),'--socket',str(endpoint),'-GSBackend',args.backend],
            env=env,stdout=(args.output/'native.jsonl').open('w'),stderr=(args.output/'helper.stderr').open('w'))
        deadline=time.monotonic()+30
        while not endpoint.exists():
            assert helper.poll() is None and time.monotonic()<deadline,'Native helper startup'
            time.sleep(.02)
        browser_env=dict(env,LD_PRELOAD=str(args.hook.resolve()),NEXTSPACE_FIREFOX_SOCKET=str(endpoint),
            NEXTSPACE_FIREFOX_LOG=str(args.output/'hook.log'))
        if args.controls:browser_env['NEXTSPACE_FIREFOX_INPUT']='1'
        fixture=here/('test-controls.html' if args.controls else 'test-progress.html')
        command=[str(args.firefox.resolve()),'--no-remote','--profile',str(profile),'--marionette',fixture.as_uri()]
        browser=subprocess.Popen(command,env=browser_env,stdout=(args.output/'firefox.stdout').open('w'),stderr=(args.output/'firefox.stderr').open('w'))
        (args.output/'launch.json').write_text(json.dumps(dict(compositor=server.pid,helper=helper.pid,
            firefox=browser.pid,args=command,preferences=preferences,hook_sha256=digest(args.hook)),indent=2)+'\n')
        deadline=time.monotonic()+30
        while True:
            assert browser.poll() is None and time.monotonic()<deadline,'Firefox startup'
            try:ready=Marionette(args.port);ready.close();break
            except ConnectionRefusedError:time.sleep(.05)
        subprocess.run([sys.executable,str(here.parent/'ChromiumScrollers/native-control-reference.py'),
            '--library',str(args.native_library.resolve()),'--controls',str(here/('input-controls.json' if args.controls else 'progress-controls.json')),
            '--output',str(args.output/'references'),'-GSBackend',args.backend],env=env,check=True,timeout=30,
            stdout=(args.output/'references.stdout').open('w'),stderr=(args.output/'references.stderr').open('w'))
        if args.controls:
            subprocess.run([sys.executable,str(here.parent/'ChromiumScrollers/native-control-reference.py'),
                '--library',str(args.native_library.resolve()),'--controls',str(here/'input-controls.json'),
                '--output',str(args.output/'focused-references'),'--focus','-GSBackend',args.backend],env=env,check=True,timeout=30,
                stdout=(args.output/'focused-references.stdout').open('w'),stderr=(args.output/'focused-references.stderr').open('w'))
        subprocess.run([sys.executable,str(here/('check-controls.py' if args.controls else 'check-progress.py')),'--port',str(args.port),
            '--expected-pid',str(browser.pid),'--references',str(args.output/'references'),
            '--output',str(args.output/'checks')],env=env,check=True,timeout=60)
        crashed_renderer=None
        if args.controls:
            crash_client=connect_client()
            try:
                session=crash_client.command('WebDriver:NewSession',{})
                assert session['capabilities']['moz:processID']==browser.pid
                crash_client.command('WebDriver:Navigate',dict(url=fixture.as_uri()))
                crash_client.command('WebDriver:TakeScreenshot',dict(full=False))
                pid=int(next(line.split()[0] for line in reversed((args.output/'hook.log').read_text().splitlines()) if ' native-widget id=' in line))
                # Never signal a namespace-local PID or another browser. Prove
                # this is a live descendant of the owned browser first.
                assert pid>1 and pid!=browser.pid
                status=dict(line.split(':',1) for line in Path('/proc',str(pid),'status').read_text().splitlines() if ':' in line)
                assert int(status['Uid'].split()[0])==os.getuid()
                ancestor=pid
                while ancestor>1 and ancestor!=browser.pid:
                    fields=dict(line.split(':',1) for line in Path('/proc',str(ancestor),'status').read_text().splitlines() if ':' in line)
                    ancestor=int(fields['PPid'])
                assert ancestor==browser.pid
                before_trace,live,_,_=native_ledger();assert len(live)==6,live
                process=next(iter(live))[0]
                os.kill(pid,signal.SIGKILL)
                deadline=time.monotonic()+3
                while native_ledger()[1]:
                    assert helper.poll() is None and time.monotonic()<deadline,'Native renderer-crash cleanup'
                    time.sleep(.01)
                trace=native_ledger()[0]
                assert any(e['event']=='native-notifier-owner-exit' and e['process']==process for e in trace)
                crashed_renderer=dict(pid=pid,seccomp=int(status['Seccomp']),no_new_privs=int(status['NoNewPrivs']),native_objects_released=len(live),kernel_owner_exit=True)
                crash_client.command('WebDriver:Navigate',dict(url='about:blank'))
            finally:crash_client.close()
        loss_client=connect_client()
        try:
            loss_session=loss_client.command('WebDriver:NewSession',{})
            assert loss_session['capabilities']['moz:processID']==browser.pid
            loss_client.command('WebDriver:Navigate',dict(url=(fixture if args.controls else here/'test-progress.html').as_uri()))
            before=loss_client.command('WebDriver:TakeScreenshot',dict(full=False))
            (args.output/'before-helper-loss.png').write_bytes(base64.b64decode(before['value']))
            _,helper_reclaimed,_,_=native_ledger()
            assert len(helper_reclaimed)==(6 if args.controls else 0),helper_reclaimed
            helper.kill();helper.wait(timeout=5)
            started=time.monotonic()
            loss_client.command('WebDriver:ExecuteScript',dict(script='document.getElementById("check").checked=true;document.getElementById("check").focus();return true' if args.controls else 'document.getElementById("normal").value=61;return true',args=[]))
            after=loss_client.command('WebDriver:TakeScreenshot',dict(full=False))
            (args.output/'after-helper-loss.png').write_bytes(base64.b64decode(after['value']))
            if args.controls:
                loss_client.command('WebDriver:PerformActions',dict(actions=[dict(type='key',id='loss-keyboard',actions=[dict(type='keyDown',value=' '),dict(type='keyUp',value=' ')])]))
                value=loss_client.command('WebDriver:ExecuteScript',dict(script='return document.getElementById("check").checked',args=[]))['value']
                assert value is False,value
                control_element=loss_client.command('WebDriver:FindElement',dict(using='css selector',value='#check'))['value']
                loss_client.command('WebDriver:ElementClick',dict(id=next(iter(control_element.values()))))
                value=loss_client.command('WebDriver:ExecuteScript',dict(script='return document.getElementById("check").checked',args=[]))['value']
                assert value is True,value
            else:
                value=loss_client.command('WebDriver:ExecuteScript',dict(script='return document.getElementById("normal").position',args=[]))['value']
                assert value==.61,value
            button=loss_client.command('WebDriver:FindElement',dict(using='css selector',value='#ordinary' if args.controls else '#button'))['value']
            loss_client.command('WebDriver:ElementClick',dict(id=next(iter(button.values()))))
            action=loss_client.command('WebDriver:ExecuteScript',dict(script='return document.getElementById("ordinary").textContent' if args.controls else 'return document.getElementById("button").textContent',args=[]))['value']
            assert action=='Activated',action
            helper_loss=dict(helper_exit=helper.returncode,value=value,engine_action=action,elapsed_seconds=time.monotonic()-started,native_objects_reclaimed_by_helper_exit=len(helper_reclaimed),mouse_and_key_retained=args.controls)
        finally:loss_client.close()
        pids={int(line.split()[0]) for line in (args.output/'hook.log').read_text().splitlines() if ' native-progress ' in line or ' native-widget ' in line}
        sandbox=[]
        for pid in sorted(pids):
            if crashed_renderer and pid==crashed_renderer['pid']:
                sandbox.append(dict(pid=pid,seccomp=crashed_renderer['seccomp'],no_new_privs=crashed_renderer['no_new_privs']));continue
            status=dict(line.split(':',1) for line in Path('/proc',str(pid),'status').read_text().splitlines() if ':' in line)
            sandbox.append(dict(pid=pid,seccomp=int(status['Seccomp']),no_new_privs=int(status['NoNewPrivs'])))
        assert sandbox and all(p['seccomp']==2 and p['no_new_privs']==1 for p in sandbox),sandbox
        trace,live,created,destroyed=native_ledger()
        assert created>0 and created==destroyed+len(helper_reclaimed) and live==helper_reclaimed,(created,destroyed,live)
        if args.controls:
            assert {2,3}<={e['kind'] for e in trace if e['event']=='native-form-action'}
            assert {2,3}<={e['result'] for e in trace if e['event']=='native-form-key'}
        report=dict(sandbox=sandbox,native_created=created,native_destroyed=destroyed,helper_loss=helper_loss,renderer_crash=crashed_renderer,
            firefox_sha256=digest(args.firefox),libxul_sha256=digest(args.firefox.parent/'libxul.so'),
            checks=json.loads((args.output/'checks/results.json').read_text()))
        (args.output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(dict(passed=len(report['checks']),native_created=created,native_destroyed=destroyed)),flush=True)
    finally:
        terminate(browser);terminate(helper)
        if server and server.poll() is None:
            try:control('quit');server.wait(timeout=5)
            except (OSError,subprocess.TimeoutExpired):terminate(server)
        child.close();parent.close()
