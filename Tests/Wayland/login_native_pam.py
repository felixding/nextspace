"""Native UI/owned-compositor driver for login_pam.py's disposable PAM fixture."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import pwd
import select
import shlex
import shutil
import signal
import socket
import struct
import subprocess
import sys
import time

from login_pam import identity, until


def native_environment(root,config):
    mode=config.parent/'native-display.json'
    vt=json.loads(mode.read_text()).get('vt') if mode.exists() else None
    environment=dict(os.environ,GNUSTEP_CONFIG_FILE=str(config),
        LD_LIBRARY_PATH=str(root/'candidate/lib')+':/usr/NextSpace/lib:/usr/local/lib',
        PATH='/usr/NextSpace/bin:/Library/bin:'+os.environ.get('PATH','/usr/bin:/bin'),
        WLR_BACKENDS='drm,libinput' if vt else 'headless',WLR_HEADLESS_OUTPUTS='1',
        WLR_RENDERER='pixman',GSK_RENDERER='cairo',GTK_A11Y='none')
    if vt:
        environment.pop('WLR_HEADLESS_OUTPUTS',None)
        environment['LIBSEAT_BACKEND']='logind'
    return environment


def execute_role(program,arguments,environment,log):
    with log.open('a') as output:
        os.dup2(output.fileno(),1);os.dup2(output.fileno(),2)
    os.execve(program,[str(program),*arguments],environment)


def prepare(context):
    root,art=context['root'],context['artifacts']
    (art/'native-display.json').write_text(json.dumps(dict(vt=context.get('vt')))+'\n')
    shutil.copy2(Path(__file__).resolve(),art/'native-source.py')
    library=art/'system-library';(library/'Preferences').mkdir(parents=True)
    # Overlay the configured system library, retaining installed desktop assets.
    configuration_source=Path('/Library/Preferences/GNUstep.conf').read_text()
    setting=next(line.split('=',1)[1] for line in configuration_source.splitlines()
        if line.startswith('GNUSTEP_SYSTEM_LIBRARY='))
    system_library=Path(shlex.split(setting,comments=True)[0])
    assert system_library.is_dir(),system_library
    for entry in system_library.iterdir():
        if entry.name not in ('Preferences','Frameworks','Bundles','Themes'):
            (library/entry.name).symlink_to(entry,target_is_directory=entry.is_dir())
    for entry in (system_library/'Preferences').glob('*'):
        if entry.name!='Login':(library/'Preferences'/entry.name).symlink_to(entry,target_is_directory=entry.is_dir())
    frameworks=root/'candidate/Frameworks'
    if context['user_desktop']:assert frameworks.is_dir(), 'The desktop candidate requires its framework bundles'
    if frameworks.is_dir():(library/'Frameworks').symlink_to(frameworks,target_is_directory=True)
    release=art/'release-user'
    literals=['native UI handoff',"a'b",'日本語','$(touch forbidden)']
    arguments=[sys.executable,str(context['pam_driver']),'--user',str(context['user_home']/'identity.json'),str(release),*literals]
    homes=[context['greeter_home']]
    if context['user_desktop']:homes.append(context['user_home'])
    backend=root/'candidate/libgnustep-wayland-032.bundle'
    if not backend.is_dir():backend=root/'candidate/libgnustep-wayland-title-state-032.bundle'
    for base in (library,*[home/'Library' for home in homes]):
        for name,target in [('Bundles/libgnustep-wayland-title-state-032.bundle',backend),
                            ('Bundles/libgnustep-wayland-032.bundle',backend),
                            ('Themes/NextSpace.theme',root/'candidate/NextSpace.theme')]:
            link=base/name;link.parent.mkdir(parents=True,exist_ok=True);link.symlink_to(target)
    for home in homes:
        (home/'Library/Preferences').mkdir(exist_ok=True)
        profile=root/'greeter-display-profile.plist'
        if home==context['greeter_home'] and profile.is_file():
            assert (root/'bin/nextspace-display-profile').is_file()
            saved=plistlib.loads(profile.read_bytes())
            scales={entry['Scale120'] for entry in saved['Layout']}
            assert saved['Schema']==2 and len(scales)==1
            context['greeter_profile_scale']=next(iter(scales))
            directory=home/'Library/Preferences/.NextSpace';directory.mkdir()
            shutil.copy2(profile,directory/'WaylandDisplays.plist')
        owner=home.stat()
        for path in [home/'Library',*(home/'Library').rglob('*')]:
            if not path.is_symlink():os.chown(path,owner.st_uid,owner.st_gid)
    def configuration(home,name):
        path=art/name
        path.write_text(configuration_source+
            '\nGNUSTEP_USER_CONFIG_FILE=\nGNUSTEP_SYSTEM_LIBRARY='+str(library)+'\n'+
            'GNUSTEP_USER_DEFAULTS_DIR='+str(home/'Library/Preferences/.GNUstepDefaults')+'\n')
        return path
    config=configuration(context['greeter_home'],'GNUstep.conf')
    if context['user_desktop']:
        assert (root/'candidate/Workspace.app/Workspace').is_file()
        user_config=configuration(context['user_home'],'user-GNUstep.conf')
        arguments=[sys.executable,str(root/'login_native_pam.py'),'--desktop-user',str(root),str(user_config),
            str(context['user_home']/'identity.json'),*literals]
        context['user_config']=user_config
    (library/'Preferences/Login').write_bytes(plistlib.dumps(dict(NativeSessionCommand=arguments)))
    context.update(config=config,user_arguments=arguments,expected_user_arguments=literals,release=release)
    relay=root/'relay.sh'
    if not relay.exists():
        relay.write_text('#!/bin/sh\nexec /usr/bin/python3 '+shlex.quote(str(root/'login_native_pam.py'))+
            ' --relay '+shlex.quote(str(root))+' "$@"\n');relay.chmod(0o755)
    return [sys.executable,str(root/'login_native_pam.py'),'--greeter',str(root),str(config),
        str(context['greeter_home']/'identity.json')]


def greeter(root,config,destination):
    temporary=destination.with_suffix('.tmp');temporary.write_text(json.dumps(identity(),indent=2)+'\n');temporary.replace(destination)
    program=root/'bin/nextspace-wayland-greeter'
    helper=root/'bin/nextspace-display-profile'
    preparation=['--greeter-profile',str(helper)] if helper.is_file() else []
    execute_role(program,['--compositor',str(root/'relay.sh'),*preparation,'--',str(root/'candidate/Login.app/Login'),
        '-GSBackend','libgnustep-wayland','-GSTheme','NextSpace'],native_environment(root,config),destination.parent/'native-greeter.log')


def desktop_user(root,config,destination,arguments):
    row=identity();row['arguments']=arguments
    destination.write_text(json.dumps(row,indent=2)+'\n')
    program=root/'bin/nextspace-wayland-session'
    environment=native_environment(root,config)
    captures=destination.parent/'captures';captures.mkdir(mode=0o700)
    environment['NEXTSPACE_WAYLAND_CAPTURE_DIR']=str(captures)
    options=['--compositor',str(root/'relay.sh')]
    locker=root/'bin/nextspace-wayland-locker'
    if locker.is_file():options+=['--locker',str(locker)]
    execute_role(program,[*options,'--',str(root/'candidate/Workspace.app/Workspace'),
        '-GSBackend','libgnustep-wayland','-GSTheme','NextSpace'],environment,destination.parent/'native-user.log')


def relay(root,arguments):
    # A private fixture control relay leaves the supervisor's broker on FD3.
    # Production never exposes this control socket or launches this wrapper.
    home=Path.home()
    endpoint=Path(os.environ['XDG_RUNTIME_DIR'])/f'nextspace-test-control-{os.getpid()}.sock'
    if endpoint.exists():endpoint.unlink()
    listener=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET);listener.bind(str(endpoint));endpoint.chmod(0o600);listener.listen(1)
    control,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
    process=subprocess.Popen([str(root/'candidate/bin/nextspace-compositor'),'-c',str(child.fileno()),*arguments],
        pass_fds=[3,child.fileno()])
    child.close()
    record=dict(pid=os.getpid(),supervisor_pid=os.getppid(),compositor_pid=process.pid,uid=os.getuid(),
        session=os.environ['NEXTSPACE_SESSION_ID'],session_class=os.environ.get('XDG_SESSION_CLASS'),
        runtime=os.environ['XDG_RUNTIME_DIR'],control=str(endpoint),environment=identity()['environment'],
        wayland=os.environ.get('WAYLAND_DISPLAY'),bus=os.environ.get('DBUS_SESSION_BUS_ADDRESS'))
    temporary=home/'relay.tmp';temporary.write_text(json.dumps(record,indent=2)+'\n');temporary.replace(home/'relay.json')
    stopped=False;client=None
    def stop(signum,frame):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop)
    try:
        while not stopped and process.poll() is None:
            readable=select.select([listener,*([client] if client else [])],[],[],0.1)[0]
            if listener in readable:
                connection,_=listener.accept()
                peer=struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                assert peer[1] in (0,os.getuid())
                if client:client.close()
                client=connection
            if client and client in readable:
                data=client.recv(65536)
                if not data:client.close();client=None;continue
                control.sendall(data)
                while not stopped and process.poll() is None:
                    if select.select([control],[],[],0.1)[0]:client.sendall(control.recv(65536));break
    finally:
        if client:client.close()
        listener.close();control.close();endpoint.unlink(missing_ok=True)
        if process.poll() is None:process.terminate();process.wait(timeout=5)


def process_tree(pid):
    found={pid};pending=[pid]
    while pending:
        parent=pending.pop()
        try:children=Path(f'/proc/{parent}/task/{parent}/children').read_text().split()
        except FileNotFoundError:continue
        for child in map(int,children):
            if child not in found:found.add(child);pending.append(child)
    return sorted(found)


def process_records(pids):
    result={}
    for name,pid in pids.items():
        try:
            fields={key:value.strip() for line in Path(f'/proc/{pid}/status').read_text().splitlines()
                for key,value in [line.split(':',1)] if key in ('Name','State','PPid','Uid')}
            fields['executable']=str(Path(f'/proc/{pid}/exe').resolve())
            fields['pid']=pid;result[name]=fields
        except FileNotFoundError:pass
    return result


def desktop_logout(context,greeter):
    root,home,art=context['root'],context['user_home'],context['artifacts']
    account=pwd.getpwnam(context['user'])
    def relay_ready():
        path=home/'relay.json'
        return json.loads(path.read_text()) if path.exists() else None
    session=until(relay_ready,'authenticated user compositor relay')
    assert session['uid']==account.pw_uid and session['session_class']=='user',session
    assert session['session']!=greeter['session'] and session['bus']!=greeter['bus'],session
    assert 'GREETD_SOCK' not in session['environment'],session
    control=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET);control.settimeout(5);control.connect(session['control'])
    def command(text):control.sendall(text.encode());return json.loads(control.recv(65536))
    binary=(root/'candidate/Workspace.app/Workspace').resolve()
    debugger=None
    try:
        def windows():
            found=[]
            for window in command('windows'):
                try:executable=Path(f"/proc/{window['pid']}/exe").resolve(strict=True)
                except FileNotFoundError:continue
                if executable==binary and window['visible']:found.append(window)
            return found
        def ready():
            found=windows()
            recycler=next((w for w in found if w['title']=='Recycler'),None)
            viewer=next((w for w in found if w['style'] & 1),None)
            return (recycler,viewer) if recycler and viewer else None
        recycler,viewer=until(ready,'actual Workspace Recycler and file viewer',timeout=30)
        assert recycler['pid']==viewer['pid']
        pid=recycler['pid']
        raw=dict(value.split('=',1) for value in Path(f'/proc/{pid}/environ').read_bytes().decode().split('\0') if '=' in value)
        assert raw['XDG_SESSION_CLASS']=='user' and raw['XDG_SESSION_TYPE']=='wayland' and 'GREETD_SOCK' not in raw
        assert raw['NEXTSPACE_SESSION_ID']==session['session'] and raw['DBUS_SESSION_BUS_ADDRESS']==session['bus']
        output=command('outputs')[0]['name']
        target_scale=150
        assert command(f'test-scale {output} {target_scale} 10000')['ok'];assert command('confirm')['ok']
        def scaled():
            found=ready()
            return found if found and all(w['preferred_scale']==target_scale and
                w['buffer_width']==(w['width']*target_scale+60)//120 and
                w['buffer_height']==(w['height']*target_scale+60)//120 for w in found) else None
        recycler,viewer=until(scaled,'actual Workspace preferred-density buffers')
        libraries=sorted({line.split()[-1] for line in Path(f'/proc/{pid}/maps').read_text().splitlines()
            if any(token in line for token in ('libgnustep-','libobjc.so.','libSystemKit.so.','libDesktopKit.so.'))})
        assert any('libgnustep-wayland' in path for path in libraries),libraries
        query=subprocess.run([str(root/'candidate/bin/WorkspaceProbe'),'--managed-applications'],env=raw,
            user=account.pw_uid,group=account.pw_gid,extra_groups=[],capture_output=True,text=True,timeout=10)
        (art/'user-applications.stderr').write_text(query.stderr)
        assert query.returncode==0,query.stderr
        applications=json.loads(query.stdout)
        (art/'user-applications.json').write_text(json.dumps(applications,indent=2)+'\n')
        preferences=next((app for app in applications if app.get('NSApplicationName')=='Preferences'),None)
        assert preferences and preferences.get('uses_distributed_objects') is not False, applications
        kernel_vt=None
        if context.get('kernel_input'):
            from vt_switch import run as kernel_vt_run
            kernel_vt=kernel_vt_run(command,context,session,viewer)
        if os.environ.get('NEXTSPACE_PAM_DEBUG_WORKSPACE')=='1':
            with (art/'workspace-debugger.log').open('w') as output:
                debugger=subprocess.Popen(['gdb','--quiet','--batch','-ex','set pagination off',
                    '-ex','set confirm off','-ex','handle SIGPIPE nostop noprint pass','-p',str(pid),
                    '-ex','continue','-ex','thread apply all bt'],stdout=output,stderr=subprocess.STDOUT)
            def tracing():
                assert debugger.poll() is None, (art/'workspace-debugger.log').read_text()
                state=process_records({'workspace':pid})['workspace']
                status=Path(f'/proc/{pid}/status').read_text()
                return f'TracerPid:\t{debugger.pid}\n' in status and not state['State'].startswith('t')
            until(tracing,'fixture debugger attached and resumed')
        owned=process_tree(session['supervisor_pid'])
        def open_logout():
            before=command('windows');previous={window['id'] for window in before}
            (art/'user-desktop-windows.json').write_text(json.dumps(before,indent=2)+'\n')
            assert command(f"focus {viewer['id']}")['ok']
            # GNUstep's default Command modifier is Alt.
            assert command('key 56 1')['ok'];key(16);assert command('key 56 0')['ok']
            def panel():
                return next((w for w in command('windows') if w['pid']==pid and w['visible'] and
                    w['focused'] and w['id'] not in previous and w['style'] & 1 and
                    w['buffer_width']==(w['width']*target_scale+60)//120 and
                    w['buffer_height']==(w['height']*target_scale+60)//120),None)
            return until(panel,'ordinary Workspace logout confirmation')
        def key(code):
            assert command(f'key {code} 1')['ok'];time.sleep(.02);assert command(f'key {code} 0')['ok']
        def click(dialog,x):
            assert command(f"pointer {dialog['x']+x} {dialog['y']+dialog['height']-20}")['ok']
            assert command('button 272 1')['ok'];time.sleep(.02);assert command('button 272 0')['ok']
        cancelled=open_logout();click(cancelled,cancelled['width']-220)
        until(lambda:not any(w['id']==cancelled['id'] and w['visible'] for w in command('windows')),
            'Workspace logout cancellation')
        target_scale=180
        assert command(f'test-scale {output} {target_scale} 10000')['ok'];assert command('confirm')['ok']
        recycler,viewer=until(scaled,'Workspace redraw after cancelled logout')
        dialog=open_logout()
        (art/'user-logout-panel.json').write_text(json.dumps(dialog,indent=2)+'\n')
        if context['logout_keyboard']: key(28)
        else: click(dialog,dialog['width']-35)
        until(lambda:all(not Path('/proc/'+str(pid)).exists() for pid in owned),'user desktop process teardown')
        control.close();control=None
        assert not list(Path(session['runtime']).glob('nextspace-bus-*')),'User desktop private bus survived logout'
        return dict(actual_workspace=True,session=session,pid=pid,executable=str(binary),
            application_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),libraries=libraries,
            recycler=recycler,viewer=viewer,initial_scale=150,scale=target_scale,ordinary_logout_confirmation=True,
            logout_cancelled_once=True,redraw_after_cancellation=True,
            confirmation_input='keyboard' if context['logout_keyboard'] else 'pointer',
            applications=applications,
            owned_processes=owned,all_owned_processes_reaped=True,private_bus_removed=True,kernel_vt=kernel_vt)
    except BaseException:
        if control:
            try:(art/'user-desktop-failure-windows.json').write_text(json.dumps(command('windows'),indent=2)+'\n')
            except (OSError,ValueError):pass
        raise
    finally:
        if control:control.close()
        if debugger and debugger.poll() is None:debugger.terminate();debugger.wait(timeout=5)


def drive(context):
    art=context['artifacts'];home=context['greeter_home']
    account=pwd.getpwnam(context['greeter']);user=pwd.getpwnam(context['user'])
    initial=until(lambda: json.loads((home/'relay.json').read_text()) if (home/'relay.json').exists() else None,'native greeter relay')
    assert initial['uid']==account.pw_uid and initial['session_class']=='greeter',initial
    control=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET);control.settimeout(5);control.connect(initial['control'])
    def command(text):control.sendall(text.encode());return json.loads(control.recv(65536))
    def window():
        return next((w for w in command('windows') if w['title']=='Login' and w['style']==0 and w['visible']),None)
    try:
        before=until(window,'real PAM native Login panel')
        saved_scale=context.get('greeter_profile_scale')
        def restored_profile():
            w=window()
            return w if w and w['preferred_scale']==saved_scale and (w['buffer_width'],w['buffer_height'])==(
                (w['width']*saved_scale+60)//120,(w['height']*saved_scale+60)//120) else None
        if saved_scale:before=until(restored_profile,'initial real-PAM greeter saved display profile')
        initial_profile_window=before
        login_arguments=Path(f"/proc/{before['pid']}/cmdline").read_bytes().split(b'\0')
        assert b'--nextspace-shell-fd' not in login_arguments, 'Greeter received an unused shell capability'
        output=command('outputs')[0]['name']
        assert command(f'test-scale {output} 150 10000')['ok'];assert command('confirm')['ok']
        before=until(lambda: window() if window()['preferred_scale']==150 and window()['buffer_width']==578 else None,
            'real PAM greeter preferred-density buffer')
        pids=dict(supervisor=initial['supervisor_pid'],compositor=initial['compositor_pid'],relay=initial['pid'],login=before['pid'])
        primary_pids=dict(pids)
        # This fixture account belongs only to this greeter. Include its bus
        # and any toolkit daemons when checking complete session teardown.
        for process in Path('/proc').iterdir():
            if not process.name.isdecimal():continue
            try:
                if process.stat().st_uid==account.pw_uid and int(process.name) not in pids.values():
                    pids['greeter_child_'+process.name]=int(process.name)
            except FileNotFoundError:pass
        runtime={name:dict(pid=pid,executable=str(Path(f'/proc/{pid}/exe').resolve()),
            libraries=sorted({line.split()[-1] for line in Path(f'/proc/{pid}/maps').read_text().splitlines()
                if any(token in line for token in ('libgnustep-','libobjc.so.','libSystemKit.so.','libDesktopKit.so.','libwlroots-'))}))
            for name,pid in primary_pids.items()}
        (art/'native-runtime-before.json').write_text(json.dumps(runtime,indent=2)+'\n')
        (art/'greeter-processes-before.json').write_text(json.dumps(process_records(pids),indent=2)+'\n')
        assert command(f"focus {before['id']}")['ok']
        keys=dict(zip('abcdefghijklmnopqrstuvwxyz',[30,48,46,32,18,33,34,35,23,36,37,38,50,49,24,25,16,19,31,20,22,47,17,45,21,44]))
        # The generated credential stays in memory; do not record key events.
        for text in (context['user'],context['secret']):
            for char in text:
                if char.isdigit():code={'1':2,'2':3,'3':4,'4':5,'5':6,'6':7,'7':8,'8':9,'9':10,'0':11}[char]
                else:code=keys[char]
                assert command(f'key {code} 1')['ok'];time.sleep(.01)
                assert command(f'key {code} 0')['ok'];time.sleep(.01)
            assert command('key 28 1')['ok'];time.sleep(.01);assert command('key 28 0')['ok']
        until(lambda:(context['user_home']/'identity.json').exists(),'native UI authenticated user launch')
        after=json.loads((context['user_home']/'identity.json').read_text())
        assert after['uid']==after['euid']==user.pw_uid and after['gid']==user.pw_gid,after
        import grp
        assert grp.getgrnam(context['group']).gr_gid in after['groups'],after
        assert after['arguments']==context['expected_user_arguments'] and not (context['user_home']/'forbidden').exists(),after
        env=after['environment'];assert env['XDG_SESSION_TYPE']=='wayland' and env['HOME']==str(context['user_home']),after
        assert 'GREETD_SOCK' not in env,after
        assert Path(env['XDG_RUNTIME_DIR']).stat().st_uid==user.pw_uid,after
        details=subprocess.check_output(['loginctl','show-session',env['XDG_SESSION_ID'],'--all'],text=True)
        assert 'Class=user\n' in details and 'Type=wayland\n' in details and 'Service='+context['general_service']+'\n' in details
        (art/'native-user-logind.txt').write_text(details)
        try:until(lambda:all(not Path('/proc/'+str(pid)).exists() for pid in pids.values()),'complete greeter process teardown')
        except BaseException:
            (art/'greeter-processes-remaining.json').write_text(json.dumps(process_records(pids),indent=2)+'\n')
            raise
        assert not list(Path(initial['runtime']).glob('nextspace-bus-*')),'Greeter private bus directory survived handoff'
        control.close();control=None
        desktop=desktop_logout(context,initial) if context['user_desktop'] else None
        if not desktop:context['release'].touch()
        def returned():
            value=json.loads((home/'relay.json').read_text())
            return value if value['session']!=initial['session'] else None
        final=until(returned,'fresh native greeter/compositor after logout')
        assert final['uid']==account.pw_uid and final['session_class']=='greeter'
        control=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET);control.settimeout(5);control.connect(final['control'])
        restored=until(restored_profile if saved_scale else window,'returned native Login panel and saved display profile')
        events=[json.loads(line) for line in (art/'pam-events.jsonl').read_text().splitlines()]
        assert any(e['user']==context['user'] and e['event']=='close_session' and e['euid']==0 for e in events),events
        expected_vt='tty'+str(context['vt']) if context.get('vt') else context['active_vt']
        assert Path('/sys/class/tty/tty0/active').read_text().strip()==expected_vt
        result=dict(real_pam=True,native_greeter=True,owned_compositor=True,real_user_desktop=bool(desktop),user_desktop=desktop,headless_only=not context.get('vt'),
            before=initial,after=final,initial_window=before,restored_window=restored,user=after,actual_runtime=runtime,
            all_old_greeter_processes_reaped=True,private_bus_removed=True,greeter_restarted=True,
            old_greeter_process_count=len(pids),
            old_greeter_processes=pids,
            greeter_has_no_unused_shell_capability=True,
            saved_greeter_profile_scale=saved_scale,
            saved_greeter_profile_restored=bool(saved_scale),initial_profile_window=initial_profile_window,
            greetd_sha256=hashlib.sha256(context['greetd'].read_bytes()).hexdigest(),
            scope='Actual native Gorm UI and greetd/PAM/logind on a headless fixture. Shared supervisor tears down the greeter compositor/bus before a fixture user command runs; logout starts a fresh native greeter. Console/VT/GPU, actual Workspace user desktop, session choice, lock and installed packaging remain open.')
        if desktop:
            user_log=(context['user_home']/'native-user.log').read_text()
            assert 'Workspace finished with exit code: 0' in user_log, 'Workspace did not complete normal logout'
            result['scope']='Actual native Login, real greetd/PAM/logind, owned Workspace user desktop at125%/150%, logout cancellation and ordinary logout and native regreet on a headless fixture. Physical VT/GPU, saved greeter display profile, session selection, lock and installed packaging remain open.'
        if saved_scale:
            result['scope']='Real greetd/PAM/logind and native Login restore the greeter display profile before authentication and after logout. The authenticated user has its own display settings; owned processes and buses are reaped. Headless fixture only; physical VT/GPU, session choice and installed packaging remain open.'
        if context.get('vt'):
            result.update(native_vt=context['vt'],scope='Real greetd/PAM/logind and native Login/Workspace on an isolated Linux VT, with instrumented PAM services and a compositor control relay. Hardware and installed-package qualification require separate runtime identity evidence.')
        return result
    finally:
        if control:control.close()


if __name__=='__main__':
    if sys.argv[1]=='--greeter':greeter(Path(sys.argv[2]),Path(sys.argv[3]),Path(sys.argv[4]))
    elif sys.argv[1]=='--relay':relay(Path(sys.argv[2]),sys.argv[3:])
    elif sys.argv[1]=='--desktop-user':desktop_user(Path(sys.argv[2]),Path(sys.argv[3]),Path(sys.argv[4]),sys.argv[5:])
