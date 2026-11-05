#!/usr/bin/env python3
"""Run the pinned Firefox fixture and native references in a private Wayland session."""
import argparse,base64,hashlib,json,os,select,signal,socket,subprocess,sys,tempfile,time
import uuid
from contextlib import ExitStack
from pathlib import Path
from marionette import Marionette
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Tests/Wayland'))
from gnustep import pasteboard_storage

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--firefox',type=Path,required=True)
parser.add_argument('--native-library',type=Path,required=True)
parser.add_argument('--hook',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--library-path',action='append',default=[])
parser.add_argument('--compositor',default='/usr/NextSpace/bin/nextspace-compositor')
parser.add_argument('--backend',required=True)
parser.add_argument('--port',type=int,default=2829)
parser.add_argument('--click-counts',action='store_true',help='Qualify native double/triple click selection')
fixture_mode=parser.add_mutually_exclusive_group()
fixture_mode.add_argument('--controls',action='store_true',help='Exercise the optional checkbox/radio input binding')
fixture_mode.add_argument('--buttons',action='store_true',help='Exercise native input buttons through the same provider')
fixture_mode.add_argument('--sliders',action='store_true',help='Exercise native range controls through NSSlider')
fixture_mode.add_argument('--text',action='store_true',help='Exercise native text/password editors and engine transactions')
args=parser.parse_args();here=Path(__file__).resolve().parent
if args.click_counts and not args.text:parser.error('--click-counts requires --text')
mode='text' if args.text else 'sliders' if args.sliders else 'buttons' if args.buttons else 'controls' if args.controls else 'progress'
reference_model='text-controls.json' if args.text else 'range-controls.json' if args.sliders else 'button-controls.json' if args.buttons else 'input-controls.json' if args.controls else 'progress-controls.json'
interactive=args.controls or args.buttons or args.sliders or args.text
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
    services=ExitStack()
    renderer_status={}
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
    def collect_renderer_status():
        log=args.output/'hook.log'
        if not log.exists():return
        pids={int(line.split()[0]) for line in log.read_text().splitlines() if ' native-progress ' in line or ' native-widget ' in line or ' native-button ' in line or ' native-text ' in line}
        for pid in pids-renderer_status.keys():
            try:
                status=dict(line.split(':',1) for line in Path('/proc',str(pid),'status').read_text().splitlines() if ':' in line)
                renderer_status[pid]=dict(pid=pid,seccomp=int(status['Seccomp']),no_new_privs=int(status['NoNewPrivs']))
            except FileNotFoundError:pass
    try:
        server=subprocess.Popen([args.compositor,'-c',str(child.fileno())],pass_fds=[child.fileno()],env=env,
            stdout=subprocess.PIPE,stderr=(args.output/'compositor.log').open('w'),text=True);child.close()
        assert select.select([server.stdout],[],[],10)[0],'Compositor startup'
        line=server.stdout.readline().strip();assert line.startswith('WAYLAND_DISPLAY=')
        env['WAYLAND_DISPLAY']=line.split('=',1)[1]
        if args.text:
            env['NEXTSPACE_SESSION_ID']='firefox-native-text-'+uuid.uuid4().hex
            services.enter_context(pasteboard_storage(Path('/Library/bin/gpbs-wayland'),
                args.native_library.parent/'native-ui/native-pasteboard-probe',env,args.output))
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
        if interactive:browser_env['NEXTSPACE_FIREFOX_INPUT']='1'
        if args.buttons:browser_env['NEXTSPACE_FIREFOX_BUTTONS']='1'
        if args.sliders:browser_env['NEXTSPACE_FIREFOX_SLIDERS']='1'
        if args.text:browser_env['NEXTSPACE_FIREFOX_TEXT']='1'
        fixture=here/('test-'+mode+'.html')
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
            '--library',str(args.native_library.resolve()),'--controls',str(here/reference_model),
            '--output',str(args.output/'references'),*(['--keys'] if args.sliders or args.text else []),*(['--pointers'] if args.text else []),*(['--click-counts'] if args.click_counts else []),'-GSBackend',args.backend],env=env,check=True,timeout=30,
            stdout=(args.output/'references.stdout').open('w'),stderr=(args.output/'references.stderr').open('w'))
        if interactive:
            subprocess.run([sys.executable,str(here.parent/'ChromiumScrollers/native-control-reference.py'),
                '--library',str(args.native_library.resolve()),'--controls',str(here/reference_model),
                '--output',str(args.output/'focused-references'),'--focus','-GSBackend',args.backend],env=env,check=True,timeout=30,
                stdout=(args.output/'focused-references.stdout').open('w'),stderr=(args.output/'focused-references.stderr').open('w'))
        checker=subprocess.Popen([sys.executable,str(here/('check-'+mode+'.py')),'--port',str(args.port),
            '--expected-pid',str(browser.pid),'--references',str(args.output/'references'),
            '--output',str(args.output/'checks'),*(['--native-log',str(args.output/'native.jsonl')] if args.text else [])],env=env)
        try:
            deadline=time.monotonic()+(120 if args.sliders or args.click_counts else 60)
            while checker.poll() is None:
                collect_renderer_status()
                assert browser.poll() is None and time.monotonic()<deadline,'Owned Firefox fixture check'
                time.sleep(.01)
            assert checker.returncode==0,checker.returncode
        finally:terminate(checker)
        crashed_renderer=None
        if interactive:
            crash_client=connect_client()
            try:
                session=crash_client.command('WebDriver:NewSession',{})
                assert session['capabilities']['moz:processID']==browser.pid
                crash_client.command('WebDriver:Navigate',dict(url=fixture.as_uri()))
                crash_client.command('WebDriver:TakeScreenshot',dict(full=False))
                pid=int(next(line.split()[0] for line in reversed((args.output/'hook.log').read_text().splitlines()) if ' native-widget id=' in line or ' native-button id=' in line or ' native-text id=' in line))
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
            loss_client.command('WebDriver:Navigate',dict(url=(fixture if interactive else here/'test-progress.html').as_uri()))
            before=loss_client.command('WebDriver:TakeScreenshot',dict(full=False))
            (args.output/'before-helper-loss.png').write_bytes(base64.b64decode(before['value']))
            _,helper_reclaimed,_,_=native_ledger()
            assert len(helper_reclaimed)==(6 if interactive else 0),helper_reclaimed
            helper.kill();helper.wait(timeout=5)
            started=time.monotonic()
            script='document.getElementById("normal").value="Fallback";document.getElementById("normal").focus();document.getElementById("normal").setSelectionRange(8,8);return true' if args.text else 'document.getElementById("normal").value=61;document.getElementById("normal").focus();return true' if args.sliders else 'document.getElementById("button").value="Fallback label";document.getElementById("button").focus();return true' if args.buttons else 'document.getElementById("check").checked=true;document.getElementById("check").focus();return true' if args.controls else 'document.getElementById("normal").value=61;return true'
            loss_client.command('WebDriver:ExecuteScript',dict(script=script,args=[]))
            after=loss_client.command('WebDriver:TakeScreenshot',dict(full=False))
            (args.output/'after-helper-loss.png').write_bytes(base64.b64decode(after['value']))
            if args.text:
                loss_client.command('WebDriver:PerformActions',dict(actions=[dict(type='key',id='loss-keyboard',actions=[dict(type='keyDown',value='X'),dict(type='keyUp',value='X')])]))
                value=loss_client.command('WebDriver:ExecuteScript',dict(script='return document.getElementById("normal").value',args=[]))['value']
                assert value=='FallbackX',value
                control_element=loss_client.command('WebDriver:FindElement',dict(using='css selector',value='#normal'))['value']
                loss_client.command('WebDriver:ElementClick',dict(id=next(iter(control_element.values()))))
                loss_client.command('WebDriver:PerformActions',dict(actions=[dict(type='key',id='loss-keyboard',actions=[dict(type='keyDown',value='Y'),dict(type='keyUp',value='Y')])]))
                value=loss_client.command('WebDriver:ExecuteScript',dict(script='return document.getElementById("normal").value',args=[]))['value']
                assert value.replace('Y','')=='FallbackX',value
            elif args.sliders:
                loss_client.command('WebDriver:PerformActions',dict(actions=[dict(type='key',id='loss-keyboard',actions=[dict(type='keyDown',value='\ue014'),dict(type='keyUp',value='\ue014')])]))
                assert loss_client.command('WebDriver:ExecuteScript',dict(script='return document.getElementById("normal").valueAsNumber',args=[]))['value']==62
                control_element=loss_client.command('WebDriver:FindElement',dict(using='css selector',value='#normal'))['value']
                loss_client.command('WebDriver:ElementClick',dict(id=next(iter(control_element.values()))))
                value=loss_client.command('WebDriver:ExecuteScript',dict(script='return document.getElementById("normal").valueAsNumber',args=[]))['value']
                assert 0<=value<=100 and value!=62,value
            elif args.buttons:
                loss_client.command('WebDriver:PerformActions',dict(actions=[dict(type='key',id='loss-keyboard',actions=[dict(type='keyDown',value=' '),dict(type='keyUp',value=' ')])]))
                assert loss_client.command('WebDriver:ExecuteScript',dict(script='return actions',args=[]))['value']==1
                control_element=loss_client.command('WebDriver:FindElement',dict(using='css selector',value='#button'))['value']
                loss_client.command('WebDriver:ElementClick',dict(id=next(iter(control_element.values()))))
                value=loss_client.command('WebDriver:ExecuteScript',dict(script='return actions',args=[]))['value']
                assert value==2,value
            elif args.controls:
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
            button=loss_client.command('WebDriver:FindElement',dict(using='css selector',value='#ordinary' if interactive else '#button'))['value']
            loss_client.command('WebDriver:ElementClick',dict(id=next(iter(button.values()))))
            action=loss_client.command('WebDriver:ExecuteScript',dict(script='return document.getElementById("ordinary").textContent' if interactive else 'return document.getElementById("button").textContent',args=[]))['value']
            assert action=='Activated',action
            helper_loss=dict(helper_exit=helper.returncode,value=value,engine_action=action,elapsed_seconds=time.monotonic()-started,native_objects_reclaimed_by_helper_exit=len(helper_reclaimed),mouse_and_key_retained=interactive)
        finally:loss_client.close()
        pids={int(line.split()[0]) for line in (args.output/'hook.log').read_text().splitlines() if ' native-progress ' in line or ' native-widget ' in line or ' native-button ' in line or ' native-text ' in line}
        collect_renderer_status();sandbox=[]
        for pid in sorted(pids):
            if crashed_renderer and pid==crashed_renderer['pid']:
                sandbox.append(dict(pid=pid,seccomp=crashed_renderer['seccomp'],no_new_privs=crashed_renderer['no_new_privs']));continue
            assert pid in renderer_status,('Missing live renderer sandbox observation',pid)
            sandbox.append(renderer_status[pid])
        assert sandbox and all(p['seccomp']==2 and p['no_new_privs']==1 for p in sandbox),sandbox
        trace,live,created,destroyed=native_ledger()
        assert created>0 and created==destroyed+len(helper_reclaimed) and live==helper_reclaimed,(created,destroyed,live)
        if args.controls:
            assert {2,3}<={e['kind'] for e in trace if e['event']=='native-form-action'}
            assert {2,3}<={e['result'] for e in trace if e['event']=='native-form-key'}
        if args.sliders:
            assert any(e['event']=='native-form-action' and e['kind']==4 for e in trace)
            assert any(e['event']=='native-form-key' and e['kind']==4 for e in trace)
        if args.buttons:
            assert any(e['event']=='native-form-action' and e['kind']==1 for e in trace)
        report=dict(sandbox=sandbox,native_created=created,native_destroyed=destroyed,helper_loss=helper_loss,renderer_crash=crashed_renderer,
            firefox_sha256=digest(args.firefox),libxul_sha256=digest(args.firefox.parent/'libxul.so'),
            checks=json.loads((args.output/'checks/results.json').read_text()))
        (args.output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(dict(passed=len(report['checks']),native_created=created,native_destroyed=destroyed)),flush=True)
    finally:
        terminate(browser);terminate(helper)
        services.close()
        if server and server.poll() is None:
            try:control('quit');server.wait(timeout=5)
            except (OSError,subprocess.TimeoutExpired):terminate(server)
        child.close();parent.close()
