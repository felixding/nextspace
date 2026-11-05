#!/usr/bin/env python3
"""Drive the real native Login UI against a synthetic root greetd peer."""
import argparse
from contextlib import contextmanager
import json
import os
import pwd
from pathlib import Path
import select
import socket
import subprocess
import sys
import tempfile
import time
import uuid

from integration import until
from gnustep import private_defaults, remove_test_account
from PIL import Image
from login_artwork import check_panel


def at_density(window,scale):
    return window and window['preferred_scale']==scale and (window['buffer_width'],window['buffer_height']) == (
        (window['width']*scale+60)//120,(window['height']*scale+60)//120)


def run(compositor, application, systemkit, artifacts, scale, extended, deadline, failure, account=None, artwork_check=None):
    assert systemkit.is_file(), 'The selected SystemKit library does not exist'
    uid,gid,home = account if account else (os.getuid(),os.getgid(),str(Path.home()))
    assert uid != 0, 'Run the real greeter as an unprivileged guest user'
    child_identity = dict(user=uid,group=gid,extra_groups=[]) if os.geteuid()==0 else {}
    artifacts.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='nextspace-greeter-') as runtime:
        if os.geteuid()==0:os.chown(runtime,uid,gid)
        endpoint = str(Path(runtime)/'auth')
        success = dict(type='success')
        exchanges = [(dict(type='cancel_session'),success),
            (dict(type='create_session',username='testuser'),dict(type='auth_message',auth_message_type='secret',auth_message='Password:')),
            (dict(type='post_auth_message_response',response='synthetic'),success)]
        if extended:
            message=lambda kind,text:dict(type='auth_message',auth_message_type=kind,auth_message=text)
            exchanges[-1]=(exchanges[-1][0],message('info','100% authenticated'))
            exchanges += [(dict(type='post_auth_message_response'),message('visible','One-time token:')),
                (dict(type='post_auth_message_response',response='token'),message('secret','Second factor:')),
                (dict(type='post_auth_message_response',response='factor'),message('error','Message 100% %@ %s')),
                (dict(type='post_auth_message_response'),success)]
        exchanges += [(dict(type='start_session',cmd=["'/usr/NextSpace/bin/nextspace-wayland-session'"],
                env=['XDG_SESSION_TYPE=wayland','XDG_SESSION_DESKTOP=NextSpace']),success)]
        if deadline:exchanges=[(dict(type='cancel_session'),success)]
        if failure:
            exchanges[-2]=(exchanges[-2][0],dict(type='error',error_type='error',description='Denied 100% %@ %s'))
            exchanges[-1]=(dict(type='cancel_session'),success)
        env = dict(os.environ,XDG_RUNTIME_DIR=runtime,WLR_BACKENDS='headless',WLR_HEADLESS_OUTPUTS='1',WLR_RENDERER='pixman',
            GREETD_SOCK=endpoint,NEXTSPACE_SESSION_ID='test-greeter-'+uuid.uuid4().hex)
        env.update(HOME=home,USER=pwd.getpwuid(uid).pw_name,LOGNAME=pwd.getpwuid(uid).pw_name)
        for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET'):env.pop(key,None)
        private_defaults(env,runtime)
        if os.geteuid()==0:os.chown(env['GNUSTEP_CONFIG_FILE'],uid,gid)
        env['LD_LIBRARY_PATH']=str(systemkit.parent)+':'+env.get('LD_LIBRARY_PATH','')
        captures=artifacts/'captures';captures.mkdir()
        if os.geteuid()==0:os.chown(captures,uid,gid)
        env['NEXTSPACE_WAYLAND_CAPTURE_DIR']=str(captures)
        control,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);control.settimeout(5)
        with (artifacts/'compositor.log').open('w') as errors:
            server=subprocess.Popen([str(compositor),'-c',str(child.fileno())],pass_fds=[child.fileno()],env=env,
                stdout=subprocess.PIPE,stderr=errors,text=True,**child_identity)
        child.close();client=None;service=None
        def command(text):
            control.sendall(text.encode());return json.loads(control.recv(65536))
        try:
            assert select.select([server.stdout],[],[],10)[0]
            line=server.stdout.readline().strip();assert line.startswith('WAYLAND_DISPLAY='),line
            env['WAYLAND_DISPLAY']=line.split('=',1)[1]
            output=command('outputs')[0]['name']
            assert command(f'test-scale {output} {scale} 10000')['ok'];assert command('confirm')['ok']
            with (artifacts/'login.log').open('w') as log:
                client=subprocess.Popen([str(application),'-GSBackend','libgnustep-wayland','-GSTheme','NextSpace'],
                    env=env,stdout=log,stderr=log,**child_identity)
            def window():
                assert client.poll() is None, (artifacts/'login.log').read_text()[-4000:]
                windows=[w for w in command('windows') if w['pid']==client.pid and w['style']==0 and w['visible']]
                return max(windows,key=lambda w:w['width']*w['height']) if windows else None
            def configured():
                w=window()
                return w if at_density(w,scale) else None
            w=until(configured,'real Login preferred-density buffer')
            map_text = subprocess.check_output([sys.executable,'-c',
                'from pathlib import Path; import sys; print(Path("/proc/"+sys.argv[1]+"/maps").read_text())',str(client.pid)],
                text=True,**child_identity) if os.geteuid()==0 else Path(f'/proc/{client.pid}/maps').read_text()
            maps=sorted({line.split()[-1] for line in map_text.splitlines()
                if any(token in line for token in ('libgnustep-base.so.','libgnustep-gui.so.','libgnustep-wayland','libSystemKit.so.','libDesktopKit.so.','libobjc.so.'))})
            assert str(systemkit) in maps,maps
            (artifacts/'runtime.json').write_text(json.dumps(dict(pid=client.pid,executable=str(application),libraries=maps),indent=2)+'\n')
            (artifacts/'initial-window.json').write_text(json.dumps(w,indent=2)+'\n')
            capture=captures/f"window-{w['client_id']}-{scale}.png"
            def image():
                try:
                    with Image.open(capture) as source: result=source.convert('RGBA')
                    return result if result.size==(w['buffer_width'],w['buffer_height']) else None
                except OSError:return None
            until(image,'real Login panel capture').save(artifacts/'login-panel.png')
            if artwork_check is None:
                check_panel(artifacts/'login-panel.png', application.parent/'Resources/Login.gorm', scale)
            else:
                artwork_check(artifacts/'login-panel.png', application.parent/'Resources/Login.gorm', scale,
                    env=env,identity=child_identity,window=w,compositor_pid=server.pid)
            # The UI test needs one panel image. Continuous PNG compression on
            # every animation frame is separate from interaction readiness.
            captures.rename(artifacts/'initial-captures')
            assert command(f"focus {w['id']}")['ok']
            # Start the peer after rendering readiness so its unchanged IPC
            # deadline does not also measure cold toolkit startup and capture.
            with (artifacts/'service.stderr').open('w') as errors:
                service = subprocess.Popen(([] if os.geteuid()==0 else ['sudo','-n'])+
                    [sys.executable,str(Path(__file__).with_name('login_auth.py')),'--server'],
                    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,text=True)
            service.stdin.write(json.dumps(dict(socket=endpoint,uid=uid,gid=gid,exchanges=exchanges,
                wire='delay' if deadline else 'fragmented',trace=str(artifacts/'service-trace.json')))+'\n')
            service.stdin.flush()
            assert select.select([service.stdout],[],[],10)[0]
            assert json.loads(service.stdout.readline())['event'] == 'ready'
            keys=dict(zip('abcdefghijklmnopqrstuvwxyz',[30,48,46,32,18,33,34,35,23,36,37,38,50,49,24,25,16,19,31,20,22,47,17,45,21,44]))
            def key(code):
                assert command(f'key {code} 1')['ok'];time.sleep(.01)
                assert command(f'key {code} 0')['ok'];time.sleep(.01)
            for text in ('testuser','synthetic'):
                for char in text:key(keys[char])
                key(28)
            responsive=None;dialog_scale=scale
            def error_dialog():
                assert client.poll() is None
                return next((p for p in command('windows') if p['pid']==client.pid and p['id']!=w['id'] and
                    p['visible'] and p['focused'] and at_density(p,dialog_scale)),None)
            if deadline:
                changed_scale=180 if scale!=180 else 240
                dialog_scale=changed_scale
                assert command(f'test-scale {output} {changed_scale} 10000')['ok'];assert command('confirm')['ok']
                def redrawn():
                    value=window()
                    return value if value['buffer_width']==(value['width']*changed_scale+60)//120 and value['preferred_scale']==changed_scale else None
                responsive=until(redrawn,'greeter redraws while authentication is waiting')
                until(error_dialog,'bounded login-service failure alert',timeout=35)
                key(28)
                until(lambda: window()['focused'] and not error_dialog(),'greeter focus returns after service timeout')
            if failure:
                until(error_dialog,'literal service-error alert')
                key(28)
                until(lambda: window()['focused'] and not error_dialog(),'greeter focus returns after service rejection')
            if extended:
                previous=set();dialogs=[]
                for text in ('','token','factor',''):
                    def prompt():
                        assert client.poll() is None
                        return next((p for p in command('windows') if p['pid']==client.pid and p['id']!=w['id']
                            and p['id'] not in previous and p['visible'] and p['focused'] and at_density(p,scale)),None)
                    dialog=until(prompt,'PAM conversation alert')
                    previous.add(dialog['id'])
                    dialogs.append(dialog)
                    (artifacts/'dialogs.json').write_text(json.dumps(dialogs,indent=2)+'\n')
                    for char in text:key(keys[char])
                    key(28)
            assert select.select([service.stdout],[],[],15)[0], 'No authenticated session request'
            line=service.stdout.readline()
            if not line:
                (artifacts/'failure-windows.json').write_text(json.dumps(command('windows'),indent=2)+'\n')
                raise AssertionError('Synthetic service exited before completion; see service trace, stderr and failure window snapshot')
            result=json.loads(line);assert result['ok'],result
            trace=json.loads((artifacts/'service-trace.json').read_text())
            transition=None
            for index,event in enumerate(trace):
                if event['event']=='request' and event['request']['type']=='start_session':
                    previous=next(row for row in reversed(trace[:index]) if row['event']=='reply')
                    transition=event['time']-previous['time']
                    assert transition<5, ('Slow post-authentication animation',transition)
            service.stdin.close();assert service.wait(timeout=5)==0
            if not (deadline or failure):assert client.wait(timeout=10)==0
            else:assert client.poll() is None, 'Greeter did not recover from authentication timeout'
            (artifacts/'results.json').write_text(json.dumps(dict(native_login=True,synthetic_auth=True,real_pam=False,
                window=w,service=result,scale=scale,extended_conversation=extended,
                deadline_recovery=deadline,responsive_during_authentication=responsive,
                service_error_recovery=failure,post_authentication_transition_seconds=transition,
                unprivileged_uid=uid,exited_successfully=not (deadline or failure)),indent=2)+'\n')
            print('Native Login UI: '+('responsive deadline/focus recovery' if deadline else
                ('literal service-error/focus recovery' if failure else 'real Gorm panel, keyboard authentication and session request'))+' PASS')
        finally:
            if client and client.poll() is None:client.terminate();client.wait(timeout=5)
            if server.poll() is None:control.sendall(b'quit');server.wait(timeout=5)
            control.close();server.stdout.close()
            if service:
                if not service.stdin.closed:service.stdin.close()
                if service.poll() is None:service.terminate();service.wait(timeout=5)
                service.stdout.close()


@contextmanager
def greeter_account(application, artifacts):
    """Own an unprivileged greeter account inside a disposable test container."""
    if os.geteuid()!=0:
        yield os.getuid(),os.getgid(),str(Path.home())
        return
    assert Path('/.dockerenv').exists(), 'Automatic test-account setup is limited to disposable Docker containers'
    rejected=subprocess.run([str(application)],env=dict(os.environ,GREETD_SOCK='/tmp/nextspace-root-greeter-rejected'),
        capture_output=True,text=True,timeout=5)
    assert rejected.returncode==1 and 'unprivileged account' in rejected.stderr, rejected.stderr
    name='nextspace-login-'+uuid.uuid4().hex[:10]
    with tempfile.TemporaryDirectory(prefix='nextspace-login-home-') as home:
        subprocess.run(['useradd','--no-create-home','--home-dir',home,'--shell','/usr/sbin/nologin',name],check=True)
        account=pwd.getpwnam(name);os.chown(home,account.pw_uid,account.pw_gid)
        try:yield account.pw_uid,account.pw_gid,home
        finally:
            cleanup=remove_test_account(name,account.pw_uid,artifacts)
            if artifacts.is_dir():
                (artifacts/'account-cleanup.json').write_text(json.dumps(dict(cleanup,
                    root_greeter_rejected=True),indent=2)+'\n')


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('compositor','application','systemkit','artifacts'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--scale',type=int,choices=(120,150,180,210,240),default=120)
    p.add_argument('--extended',action='store_true')
    p.add_argument('--deadline',action='store_true')
    p.add_argument('--failure',action='store_true')
    args=p.parse_args()
    assert sum((args.extended,args.deadline,args.failure))<=1
    arguments=(args.compositor.resolve(),args.application.resolve(),args.systemkit.resolve(),args.artifacts.resolve(),args.scale,args.extended,args.deadline,args.failure)
    with greeter_account(args.application.resolve(),args.artifacts) as account:
        run(*arguments,account=account)
