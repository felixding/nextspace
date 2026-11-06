#!/usr/bin/env python3
"""Real session supervisor, native host, Workspace connection and Firefox."""
import argparse
import ast
import ctypes as C
import json
import os
from pathlib import Path
import select
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'Experiments/FirefoxNativeUI'))
sys.path.insert(0,str(REPO/'Experiments/ChromiumScrollers'))
from marionette import Marionette
from helper import Request,Response
from session_activation import prepare as activation_environment
from gnustep import private_defaults

p=argparse.ArgumentParser(description=__doc__)
for name in ['supervisor','compositor','shell-probe','registry-probe','library','firefox','hook','output']:
    p.add_argument('--'+name,type=Path,required=True)
p.add_argument('--backend',required=True)
p.add_argument('--host-program',type=Path,help='Exercise the installed/staged host launcher instead of its source entry point')
p.add_argument('--launcher',type=Path,help='Exercise the user launcher and its automatic optional-host selection')
p.add_argument('--backend-bundle',type=Path,help='Select a staged backend in a private GNUstep library without changing installed aliases')
p.add_argument('--library-path',action='append',default=[])
p.add_argument('--port',type=int,default=2834)
p.add_argument('--hold',action='store_true',help='Expose a private control socket for an additional owned browser test before teardown')
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
rows=[];observed=set();session=None;client=None;state=None;native_probe=None
def check(case,passed,**values):
    rows.append(dict(case=case,passed=bool(passed),**values))
    (a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
def wait(read,predicate,timeout=15):
    deadline=time.monotonic()+timeout
    while True:
        value=read()
        if predicate(value):return value
        assert not session or session.poll() is None,(session.returncode,(a.output/'session.stderr').read_text()[-3000:])
        assert time.monotonic()<deadline,value
        time.sleep(.02)
def process_tree():
    processes={}
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            status=dict(l.split(':',1) for l in (p/'status').read_text().splitlines() if ':' in l)
            processes[int(p.name)]=dict(pid=int(p.name),parent=int(status['PPid']),name=status['Name'].strip(),
                seccomp=status.get('Seccomp','').strip(),no_new_privs=status.get('NoNewPrivs','').strip(),
                arguments=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace'))
        except (OSError,ValueError):pass
    owned={session.pid}
    for _ in range(len(processes)):
        before=len(owned);owned.update(pid for pid,row in processes.items() if row['parent'] in owned)
        if len(owned)==before:break
    observed.update(owned)
    return [processes[pid] for pid in owned if pid in processes]
with tempfile.TemporaryDirectory(prefix='native-ui-session-') as runtime:
    environment=dict(os.environ,XDG_RUNTIME_DIR=runtime,XDG_SESSION_CLASS='user',
        WLR_BACKENDS='headless',WLR_RENDERER='pixman',LD_LIBRARY_PATH=':'.join(a.library_path),PYTHONFAULTHANDLER='1')
    for name in ['DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','LD_PRELOAD','NEXTSPACE_NATIVE_UI_SOCKET']:
        environment.pop(name,None)
    environment.update(activation_environment(a.output))
    if a.backend_bundle:
        assert a.backend_bundle.is_dir() and a.backend_bundle.name.startswith('libgnustep-'+a.backend+'-')
        private_defaults(environment,runtime)
        bundles=Path(runtime)/'empty-library/Bundles';bundles.mkdir(parents=True)
        (bundles/a.backend_bundle.name).symlink_to(a.backend_bundle.resolve(),target_is_directory=True)
        shutil.copy2(environment['GNUSTEP_CONFIG_FILE'],a.output/'GNUstep.conf')
    host_command=[str(a.host_program),'-GSBackend',a.backend] if a.host_program else [
        '/usr/bin/python3',str(REPO/'Libraries/NativeUI/Host/main.py'),'--library',str(a.library),'-GSBackend',a.backend]
    host=a.output/'host';host.write_text('#!/bin/sh\nexec '+shlex.join(host_command)+'\n');host.chmod(0o700)
    fifo=a.output/'input.fifo';os.mkfifo(fifo,0o600);input_fd=os.open(fifo,os.O_RDWR|os.O_NONBLOCK)
    method=a.output/'input-method'
    method.write_text('#!/usr/bin/python3\nimport os\nfd=os.open('+repr(str(fifo))+',os.O_RDWR);os.dup2(fd,0);os.close(fd)\nlog=os.open('+repr(str(a.output/'input.jsonl'))+',os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600);os.dup2(log,1);os.close(log)\nos.execv('+repr(str(a.registry_probe))+','+repr([str(a.registry_probe),'--input-method'])+')\n');method.chmod(0o700)
    profile=Path(runtime)/'profile';profile.mkdir()
    preferences={'marionette.port':a.port,'browser.shell.checkDefaultBrowser':False,'browser.startup.page':0,
        'browser.aboutwelcome.enabled':False,'browser.startup.homepage_override.mstone':'ignore',
        'widget.gtk.global-menu.enabled':True,'widget.gtk.global-menu.wayland.enabled':True,'gfx.webrender.software':True}
    (profile/'user.js').write_text(''.join('user_pref('+json.dumps(k)+', '+json.dumps(v)+');\n' for k,v in preferences.items()))
    browser=a.output/'browser'
    browser.write_text('#!/bin/sh\nexport LD_PRELOAD='+shlex.quote(str(a.hook))+'\nexport NEXTSPACE_FIREFOX_SOCKET="$NEXTSPACE_NATIVE_UI_SOCKET"\nexport NEXTSPACE_FIREFOX_LOG='+shlex.quote(str(a.output/'hook.log'))+'\nexport NEXTSPACE_FIREFOX_INPUT=1 NEXTSPACE_FIREFOX_TEXT=1 NEXTSPACE_FIREFOX_FRONTEND=1 NEXTSPACE_FIREFOX_MENU_LIFECYCLE=1 NEXTSPACE_FIREFOX_MENU_KEYS=1\nexec '+shlex.join([str(a.firefox),'--no-remote','--profile',str(profile),'--marionette','--remote-allow-system-access',(REPO/'Experiments/FirefoxNativeUI/test-text.html').as_uri()])+'\n');browser.chmod(0o700)
    events=[];published={};pending=b''
    def pump():
        global pending
        while select.select([session.stdout],[],[],0)[0]:
            data=os.read(session.stdout.fileno(),65536)
            if not data:break
            pending+=data
            while b'\n' in pending:
                line,pending=pending.split(b'\n',1);text=line.decode(errors='replace')
                with (a.output/'session.stdout').open('a') as log:log.write(text+'\n')
                if text.startswith('{'):
                    try:events.append(json.loads(text))
                    except ValueError:pass
                elif '=' in text:
                    key,value=text.split('=',1);published[key]=value
        return events
    def command(value):session.stdin.write((value+'\n').encode());session.stdin.flush()
    def windows():
        pump();return next((e['windows'] for e in reversed(events) if e.get('event') in ['windows','ready'] and 'windows' in e),[])
    def shown(window):return not window['flags']&(2|32)
    def host_pid():
        return next((v['pid'] for v in process_tree() if '/NativeUI/Host/main.py' in v['arguments'] or '/nextspace-native-ui/main.py' in v['arguments']),None)
    def shell_pid():
        return next((v['pid'] for v in process_tree() if str(a.shell_probe) in v['arguments'] and '--nextspace-shell-fd' in v['arguments']),None)
    def keyboard(value):os.write(input_fd,(value+'\n').encode())
    def key_t():
        keyboard(f'forward-modifiers {alt_mask} 0 0 0');keyboard('forward 20 1');keyboard('forward 20 0');keyboard('forward-modifiers 0 0 0 0');keyboard('sync')
    def context(value):client.command('Marionette:SetContext',dict(value=value))
    def js(code):return client.command('WebDriver:ExecuteScript',dict(script=code,args=[]))['value']
    def handles():return client.command('WebDriver:GetWindowHandles')
    def edit_key(value,modifier=None):
        actions=([dict(type='keyDown',value=modifier)] if modifier else [])+[dict(type='keyDown',value=value),dict(type='keyUp',value=value)]+([dict(type='keyUp',value=modifier)] if modifier else [])
        client.command('WebDriver:PerformActions',dict(actions=[dict(type='key',id='recovery-keyboard',actions=actions)]))
    def fields(label):
        for surface,identifier in [('content','normal'),('content','password'),('chrome','urlbar-input')]:
            context(surface)
            js("let e=document.getElementById("+json.dumps(identifier)+");e.focus();e.value='Alpha beta';e.setSelectionRange(3,3);return true")
            def field_state():
                return js("let e=document.getElementById("+json.dumps(identifier)+");return {value:e.value,start:e.selectionStart,end:e.selectionEnd}")
            edit_key('a','\ue009')
            actual=field_state();check(label+'-'+identifier+'-native-emacs',actual==dict(value='Alpha beta',start=0,end=0),state=actual)
            edit_key('Z');actual=field_state()
            check(label+'-'+identifier+'-native-transaction',actual==dict(value='ZAlpha beta',start=1,end=1),state=actual)
            js("document.getElementById("+json.dumps(identifier)+").addEventListener('beforeinput',e=>e.preventDefault(),{once:true});return true")
            edit_key('Q');actual=field_state()
            check(label+'-'+identifier+'-cancellation-retained',actual==dict(value='ZAlpha beta',start=1,end=1),state=actual)
        context('content');js('document.body.focus();return true')
    try:
        session=subprocess.Popen([
            str(a.launcher or a.supervisor),*(['--private-bus','--native-ui-host',str(host)] if not a.launcher else []),
            '--compositor',str(a.compositor),'--input-method',str(method),'--',str(a.shell_probe)],env=environment,
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(a.output/'session.stderr').open('w'))
        os.set_blocking(session.stdout.fileno(),False)
        wait(pump,lambda rs:any(e.get('event')=='ready' and 'windows' in e for e in rs))
        check('session-starts-shared-native-host',bool(host_pid()) and bool(shell_pid()))
        endpoint=Path(published['NEXTSPACE_NATIVE_UI_SOCKET']);state=endpoint.parent
        check('session-private-endpoint',endpoint.is_socket() and endpoint.stat().st_mode&0o777==0o600 and state.stat().st_mode&0o777==0o700)
        with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as query:
            query.settimeout(5);query.connect(str(endpoint));query.send(bytes(Request(magic=0x4e585343,operation=7)))
            response=Response.from_buffer_copy(query.recv(65536))
            check('shared-model-and-global-key-capabilities',int(response.parts[5].height)==7)
        native_probe=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET);native_probe.settimeout(5);native_probe.connect(str(endpoint))
        import struct
        peer_pid,peer_uid,_=struct.unpack('3i',native_probe.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        native_inode=os.fstat(native_probe.fileno()).st_ino
        check('session-retains-original-client-endpoint',peer_pid==session.pid and peer_uid==os.getuid())
        bus_env=dict(environment,**published)
        inherited=subprocess.check_output(['gdbus','call','--session','--dest','org.nextspace.ValidationEnvironment',
            '--object-path','/org/nextspace/ValidationEnvironment','--method','org.nextspace.ValidationEnvironment.GetEnvironment'],env=bus_env,text=True)
        activated=ast.literal_eval(inherited)[0]
        check('dbus-activation-inherits-native-endpoint',activated.get('NEXTSPACE_NATIVE_UI_SOCKET')==str(endpoint))
        menus=subprocess.check_output(['gdbus','call','--session','--dest','com.canonical.AppMenu.Registrar',
            '--object-path','/com/canonical/AppMenu/Registrar','--method','com.canonical.AppMenu.Registrar.GetMenus'],env=bus_env,text=True)
        check('real-host-advertises-wayland-consumer','[]' in menus,result=menus.strip())
        unsupported=subprocess.run(['gdbus','call','--session','--dest','com.canonical.AppMenu.Registrar',
            '--object-path','/com/canonical/AppMenu/Registrar','--method','com.canonical.AppMenu.Registrar.RegisterWindow','1','/test'],env=bus_env,capture_output=True,text=True)
        check('host-does-not-claim-x11-registration',unsupported.returncode!=0 and 'WaylandOnly' in unsupported.stderr)
        # A headless seat has no physical keyboard supplying an XKB keymap.
        # Obtain one from the actual XKB library and give it to the authorized
        # virtual keyboard. No shortcut or key-binding rules are supplied here.
        xkb=C.CDLL('libxkbcommon.so.0')
        xkb.xkb_context_new.argtypes=[C.c_int];xkb.xkb_context_new.restype=C.c_void_p
        xkb.xkb_keymap_new_from_names.argtypes=[C.c_void_p,C.c_void_p,C.c_int];xkb.xkb_keymap_new_from_names.restype=C.c_void_p
        xkb.xkb_keymap_get_as_string.argtypes=[C.c_void_p,C.c_int];xkb.xkb_keymap_get_as_string.restype=C.c_void_p
        xkb.xkb_keymap_mod_get_index.argtypes=[C.c_void_p,C.c_char_p];xkb.xkb_keymap_mod_get_index.restype=C.c_uint
        ctx=xkb.xkb_context_new(0);mapping=xkb.xkb_keymap_new_from_names(ctx,None,0);assert mapping
        text=xkb.xkb_keymap_get_as_string(mapping,1);assert text
        keymap=a.output/'keymap.xkb';keymap.write_bytes(C.string_at(text)+b'\0')
        index=xkb.xkb_keymap_mod_get_index(mapping,b'Mod1');assert index<32;alt_mask=1<<index
        libc=C.CDLL(None);libc.free.argtypes=[C.c_void_p];libc.free(text)
        xkb.xkb_keymap_unref.argtypes=[C.c_void_p];xkb.xkb_keymap_unref(mapping)
        xkb.xkb_context_unref.argtypes=[C.c_void_p];xkb.xkb_context_unref(ctx)
        keyboard('keymap '+str(keymap));keyboard('sync')
        wait(lambda:(a.output/'input.jsonl').read_text(),lambda s:'"event":"keymap"' in s)
        check('headless-keyboard-keymap-ready',True)
        command('launch '+str(browser));started=wait(pump,lambda rs:any(e.get('event')=='launched' for e in rs))
        browser_pid=next(e['pid'] for e in reversed(started) if e.get('event')=='launched')
        check('browser-launched-by-workspace',any(v['pid']==browser_pid for v in process_tree()))
        def connect():
            try:return Marionette(a.port)
            except ConnectionRefusedError:return None
        client=wait(connect,bool,30);created=client.command('WebDriver:NewSession',{})
        check('unchanged-browser-owned-session',created['capabilities']['moz:processID']==browser_pid)
        wait(pump,lambda rs:any(e.get('event')=='dbus-menu-bound' and e['pid']==browser_pid for e in rs))
        native=wait(windows,lambda ws:any(w['pid']==host_pid() and shown(w) for w in ws))
        check('workspace-automatically-selects-native-menu',any(w['pid']==host_pid() and w['level']==20 for w in native))
        original=handles()[0];context('content');js("document.body.tabIndex=0;document.body.focus();window.__sessionKeys=[];document.addEventListener('keydown',e=>__sessionKeys.push({key:e.key,alt:e.altKey,trusted:e.isTrusted}));return true")
        def shortcut(label):
            before=set(handles());start=len(pump());key_t()
            try:after=wait(handles,lambda hs:len(hs)==len(before)+1)
            except AssertionError:
                (a.output/'key-diagnostic.json').write_text(json.dumps(js('return window.__sessionKeys'))+'\n');raise
            wait(pump,lambda rs:any(e.get('event')=='application-command' for e in rs[start:]))
            tail=events[start:];check(label+'-one-native-application-command',len([e for e in tail if e.get('event')=='application-command'])==1)
            new=next(h for h in after if h not in before);client.command('WebDriver:SwitchToWindow',dict(handle=new));client.command('WebDriver:CloseWindow')
            client.command('WebDriver:SwitchToWindow',dict(handle=original));context('content');js('document.body.focus();return true')
        shortcut('session-startup')
        old_shell=shell_pid();os.kill(old_shell,signal.SIGKILL)
        wait(shell_pid,lambda pid:pid and pid!=old_shell)
        wait(pump,lambda rs:sum(e.get('event')=='ready' and 'windows' in e for e in rs)>=2)
        wait(windows,lambda ws:any(w['pid']==host_pid() and shown(w) for w in ws))
        check('workspace-restarts-with-new-private-menu-role',shell_pid()!=old_shell and any(w['pid']==browser_pid for w in windows()))
        shortcut('workspace-recovery')
        fields('before-host-loss')
        js("normal.__recoveryMarker='same-frame';password.__recoveryMarker='same-frame';return true")
        old_host=host_pid();unchanged_shell=shell_pid();start=len(pump());os.kill(old_host,signal.SIGKILL)
        replacement=wait(host_pid,lambda pid:pid and pid!=old_host)
        wait(pump,lambda rs:any(e.get('event')=='dbus-menu-bound' and e['pid']==browser_pid for e in rs[start:]))
        wait(windows,lambda ws:any(w['pid']==replacement and shown(w) for w in ws))
        check('host-restart-replays-current-native-menu',shell_pid()==unchanged_shell and any(w['pid']==browser_pid for w in windows()))
        check('host-restart-preserves-live-field-models',js("return normal.__recoveryMarker==='same-frame' && password.__recoveryMarker==='same-frame' && normal.value==='ZAlpha beta' && password.value==='ZAlpha beta'"))
        native_probe.send(bytes(Request(magic=0x4e585343,operation=7)))
        restored_api=Response.from_buffer_copy(native_probe.recv(65536))
        check('same-client-socket-serves-replacement-host',os.fstat(native_probe.fileno()).st_ino==native_inode and int(restored_api.parts[5].height)==7)
        shortcut('native-host-recovery')
        fields('after-host-loss')
        if a.hold:
            control_path=a.output/'control.sock'
            with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as control:
                control.bind(str(control_path));os.chmod(control_path,0o600);control.listen(1)
                print(json.dumps(dict(event='fixture-ready',control=str(control_path))),flush=True)
                try:
                    done=False
                    while not done:
                        ready,_,_=select.select([control,session.stdout],[],[],.1);pump();process_tree()
                        if control not in ready:continue
                        connection,_=control.accept()
                        with connection:
                            request=json.loads(connection.recv(8192));operation=request['operation']
                            if operation=='status':
                                result=dict(host=host_pid(),shell=shell_pid(),browser=browser_pid,session=session.pid,windows=windows(),environment=published)
                            elif operation=='keyboard':keyboard(request['text']);result=dict(ok=True)
                            elif operation=='shell':command(request['text']);result=dict(ok=True)
                            elif operation=='restart-host':os.kill(host_pid(),signal.SIGKILL);result=dict(ok=True)
                            elif operation=='firefox-eval':
                                context(request.get('context','content'));result=dict(ok=True,value=js(request['script']))
                            elif operation=='firefox-screenshot':
                                import base64
                                name=a.output/'firefox-multiline.png'
                                name.write_bytes(base64.b64decode(client.command('WebDriver:TakeScreenshot',dict(full=False))['value']))
                                result=dict(ok=True,path=str(name))
                            elif operation=='native-reference':
                                name=request['name'];assert name==Path(name).name and name not in ('.','..')
                                target=a.output/name;assert not target.exists();target.mkdir()
                                spec=target/'controls.json';spec.write_text(json.dumps(request['controls']))
                                with (target/'stdout').open('w') as stdout,(target/'stderr').open('w') as stderr:
                                    subprocess.run([sys.executable,str(REPO/'Experiments/ChromiumScrollers/native-control-reference.py'),
                                        '--library',str(a.library),'--controls',str(spec),'--output',str(target),
                                        '-GSBackend',a.backend]+(['--focus'] if request.get('focus') else []),
                                        env=bus_env,stdout=stdout,stderr=stderr,timeout=30,check=True)
                                result=dict(ok=True,path=str(target),reference=json.loads((target/'results.json').read_text()))
                            elif operation=='verify-firefox':
                                before=len(rows)
                                window=next(w for w in windows() if w['pid']==browser_pid and w['level']==0)
                                command('activate '+str(window['id']))
                                wait(windows,lambda ws:any(w['pid']==browser_pid and w['flags']&1 for w in ws))
                                wait(windows,lambda ws:sum(w['pid']==host_pid() and w['level']==20 and shown(w) for w in ws)==1)
                                shortcut('after-chromium-host-loss-switch')
                                fields('after-chromium-host-loss-switch')
                                result=dict(ok=True,passed=len(rows)-before)
                            elif operation=='quit':done=True;result=dict(ok=True)
                            else:raise ValueError(operation)
                            connection.send(json.dumps(result).encode())
                finally:control_path.unlink(missing_ok=True)
        snapshot=process_tree();(a.output/'processes.json').write_text(json.dumps(snapshot,indent=2)+'\n')
        contents=[v for v in snapshot if v['arguments'].rstrip().endswith(' tab')]
        check('browser-sandbox-retained',bool(contents) and all(v['seccomp']=='2' and v['no_new_privs']=='1' for v in contents))
        shutil.copytree(state/'menus',a.output/'native-menu-state')
        client.close();client=None
        command('quit');session.wait(timeout=15)
        check('ordinary-session-exit',session.returncode==0)
        diagnostics=(a.output/'session.stderr').read_text()
        check('native-host-stops-before-display-teardown','Native UI host stopped with 0.' in diagnostics and 'Fatal Python error' not in diagnostics)
        check('session-removes-native-endpoint-and-state',not state.exists())
    finally:
        if native_probe:native_probe.close()
        if client:
            try:client.close()
            except (EOFError,ConnectionError):
                if session.poll() is None:raise
        if session and session.poll() is None:
            process_tree();session.terminate()
            try:session.wait(timeout=15)
            except subprocess.TimeoutExpired:session.kill();session.wait(timeout=5)
        os.close(input_fd);fifo.unlink(missing_ok=True)
        live=[]
        for pid in observed:
            try:
                if Path('/proc',str(pid),'stat').read_text().rsplit(') ',1)[1].split()[0] not in ['Z','X']:live.append(pid)
            except FileNotFoundError:pass
        (a.output/'cleanup.json').write_text(json.dumps(dict(pids=sorted(observed),live=live),indent=2)+'\n')
        assert not live,live
print(json.dumps(dict(passed=len(rows))))
