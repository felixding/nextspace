#!/usr/bin/env python3
"""Real unprivileged PAM unlock, confined to an explicitly disposable container."""
import argparse
import array
import hashlib
import json
import os
from pathlib import Path
import pwd
import secrets
import select
import signal
import socket
import struct
import string
import subprocess
import uuid

from integration import read_json_lines, until

KEYS = dict(zip('qwertyuiopasdfghjklzxcvbnm',
                (16,17,18,19,20,21,22,23,24,25,30,31,32,33,34,35,36,37,38,44,45,46,47,48,49,50)))



def type_password(command, value):
    for key in [*(KEYS[letter] for letter in value),28]:
        for pressed in (1,0):assert command(f'key {key} {pressed}')['ok']


def runtime_snapshot(pid, identity):
    # Read with the tested account's credentials; container root need not have
    # ptrace privileges over a process running under a different UID.
    code='''import hashlib,json,sys
from pathlib import Path
pid=int(sys.argv[1])
paths=sorted({row.split()[-1] for row in Path(f'/proc/{pid}/maps').read_text().splitlines()
 if any(name in row for name in ('libwlroots-','libwayland-','libcairo.so.','libxkbcommon.so.','libsystemd.so.','libpam.so.','/security/pam_'))})
print(json.dumps(dict(executable=str(Path(f'/proc/{pid}/exe').resolve()),
 libraries={path:hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in paths})))'''
    return json.loads(subprocess.check_output(['/usr/bin/python3','-c',code,str(pid)],text=True,timeout=5,**identity))


def run_supervised(supervisor, compositor, locker, artifacts, home, runtime, env, identity, secret, processes,
        logind_probe=None, session_factory=None):
    listener=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
    address=runtime/'control';listener.bind(str(address));listener.listen(1);listener.settimeout(10)
    os.chown(address,identity['user'],identity['group'])
    mock=None
    if logind_probe:
        def start_bus(label):
            with (artifacts/(label+'.log')).open('w') as log:
                process=subprocess.Popen(['dbus-daemon','--session','--nofork','--nopidfile',
                    '--address=unix:path='+str(runtime/'system-bus'),'--print-address=1'],
                    env=env,stdout=subprocess.PIPE,stderr=log,text=True,**identity)
            processes.append(process)
            assert select.select([process.stdout],[],[],5)[0]
            value=process.stdout.readline().strip();assert value.startswith('unix:path=')
            # This owned fixture deliberately restarts its daemon. Keep the
            # stable socket address rather than pinning the first daemon GUID.
            return process,value.split(',guid=',1)[0]
        bus,bus_address=start_bus('system-bus')
        env=dict(env,DBUS_SYSTEM_BUS_ADDRESS=bus_address,XDG_SESSION_ID='forged-not-the-current-session',
            NEXTSPACE_LOCK_PIXEL_CHECK='1')
        def start_service(label,arguments=()):
            path=artifacts/(label+'.jsonl')
            with path.open('w') as log,(artifacts/(label+'.stderr')).open('w') as errors:
                service=subprocess.Popen([logind_probe,*arguments],env=dict(env,DBUS_SESSION_BUS_ADDRESS=bus_address),
                    stdin=subprocess.PIPE,stdout=log,stderr=errors,text=True,**identity)
            processes.append(service)
            until(lambda:any(row['event']=='ready' for row in read_json_lines(path)),'owned '+label+' service')
            return service,path
        mock,mock_path=start_service('logind');spoof,_=start_service('spoof',['spoof'])
        previous_mock_events=[]
        def mock_events():return read_json_lines(mock_path)
        def send_service(service,value):service.stdin.write(value+'\n');service.stdin.flush()
    pidfile=home/'locker.pid';mode=home/'locker.mode';launches=home/'locker-launches.jsonl'
    wrapper=home/'compositor.py';shell=home/'workspace';locker_wrapper=home/'locker.py'
    wrapper.write_text('#!/usr/bin/python3\nimport os,socket,sys\ns=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)\n'+
        's.connect('+repr(str(address))+')\nos.set_inheritable(s.fileno(),True)\n'+
        'os.execv('+repr(compositor)+',['+repr(compositor)+',"-c",str(s.fileno()),*sys.argv[1:]])\n')
    shell.write_text('#!/bin/sh\nexec /bin/sleep infinity\n')
    locker_wrapper.write_text('#!/usr/bin/python3\nimport json,os,signal\nfrom pathlib import Path\n'+
        'pidfile=Path('+repr(str(pidfile))+')\ntmp=pidfile.with_suffix(".new")\ntmp.write_text(str(os.getpid()))\nos.replace(tmp,pidfile)\n'+
        'with open('+repr(str(launches))+',"a") as log:log.write(json.dumps(dict(pid=os.getpid()))+"\\n")\n'+
        'mode=Path('+repr(str(mode))+')\nvalue=mode.read_text() if mode.exists() else ""\n'+
        'if value=="exit-zero":raise SystemExit(0)\n'+
        'if value=="hang":\n while True:signal.pause()\n'+
        'os.execv('+repr(locker)+',['+repr(locker)+',"--config","/dev/null","--color","303030"])\n')
    for path in (wrapper,shell,locker_wrapper):path.chmod(0o755)
    log_path=artifacts/'session.log'
    arguments=[supervisor,'--compositor',str(wrapper),'--locker',str(locker_wrapper),'--',str(shell)]
    if session_factory:session=session_factory(arguments,env,log_path)
    else:
        with log_path.open('w') as log:
            session=subprocess.Popen(arguments,env=env,stdout=subprocess.PIPE,stderr=log,text=True,**identity)
    processes.append(session)
    control=None
    def alive():assert session.poll() is None,log_path.read_text()[-4000:]
    try:
        control,_=listener.accept();control.settimeout(5)
        compositor_pid,peer_uid,_=struct.unpack('3i',control.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        assert peer_uid==identity['user']
        def command(value):
            alive();control.sendall(value.encode());return json.loads(control.recv(65536))
        def state():return command('lock-state')
        until(lambda:command('outputs'),'supervised compositor outputs')
        if mock:
            lookup=until(lambda:next((row for row in mock_events() if row['event']=='lookup'),None),'logind session lookup')
            assert lookup['pid']==session.pid,lookup
            send_service(mock,'other');send_service(spoof,'lock')
            send_service(spoof,'prepare')
            until(lambda:any(row.get('command')=='other' for row in mock_events()),'wrong-session signal sent')
            until(lambda:any(row.get('command')=='lock' for row in read_json_lines(artifacts/'spoof.jsonl')),'wrong-sender signal sent')
            until(lambda:any(row.get('command')=='prepare' for row in read_json_lines(artifacts/'spoof.jsonl')),'wrong-sender suspend signal sent')
            import time
            time.sleep(.2)
            assert not state()['locked'],'Wrong session or sender triggered locking'
        def mapped(exclude=None):
            alive()
            current=state();rows=command('lock-surfaces')
            if not current['locked'] or not current['acknowledged'] or not rows or not all(row['mapped'] for row in rows):return None
            pid=int(pidfile.read_text()) if pidfile.exists() else 0
            if not pid or pid==exclude:return None
            status=Path(f'/proc/{pid}/status').read_text()
            fields={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in status.splitlines() if ':' in line}
            assert set(map(int,fields['Uid'].split()))=={identity['user']}
            assert int(fields['PPid'])==session.pid
            assert int(fields['SigBlk'],16)&(1<<(signal.SIGUSR1-1))
            return dict(pid=pid,surfaces=rows,state=current)
        def request():os.kill(session.pid,signal.SIGUSR1);return until(mapped,'supervised locker mapped')
        records=[];runtimes={}
        for scale in (120,150,180,210,240):
            for head in command('outputs'):
                assert command(f"test-scale {head['name']} {scale} 10000")['ok'];assert command('confirm')['ok']
            if mock and scale==150:
                send_service(mock,'deny');until(lambda:mock_events()[-1].get('deny_hints') is True,'hint denial configured')
            if mock and scale==120:
                send_service(mock,'lock');current=until(mapped,'logind-owned session Lock signal')
            elif scale==120 and hasattr(session,'lock_via_logind'):
                session.lock_via_logind();current=until(mapped,'real logind session Lock signal')
            elif scale==150:
                for key in (29,56,38):assert command(f'key {key} 1')['ok']
                for key in (38,56,29):assert command(f'key {key} 0')['ok']
                current=until(mapped,'physical Ctrl-Alt-L lock')
            else:current=request()
            if mock:
                until(lambda:mock_events() and mock_events()[-1].get('locked') is True,'logind locked hint after compositor acknowledgement')
                send_service(mock,'unlock')
                until(lambda:mock_events()[-1].get('command')=='unlock','logind Unlock signal sent')
                time.sleep(.1);assert state()['locked'],'Logind signal bypassed PAM'
            if hasattr(session,'check_locked_hint'):
                session.check_locked_hint(True)
                session.signal_unlock()
                import time
                time.sleep(.1);assert state()['locked'],'Real logind signal bypassed PAM'
            os.kill(current['pid'],signal.SIGUSR1)
            until(lambda:'0000000000000200' in Path(f"/proc/{current['pid']}/status").read_text(),'blocked locker unlock signal')
            assert state()['locked'] and not state()['desktop_visible']
            failures=log_path.read_text().count('pam_authenticate failed: invalid credentials')
            type_password(command,'wrong')
            until(lambda:log_path.read_text().count('pam_authenticate failed: invalid credentials')>failures,'supervised PAM rejection')
            assert state()['locked']
            if not runtimes:
                runtimes=dict(supervisor=runtime_snapshot(session.pid,identity),
                    compositor=runtime_snapshot(compositor_pid,identity),locker=runtime_snapshot(current['pid'],identity))
                children=Path(f"/proc/{current['pid']}/task/{current['pid']}/children").read_text().split()
                assert len(children)==1,children
                runtimes['pam_backend']=runtime_snapshot(int(children[0]),identity)
                assert any('/security/pam_unix.so' in path for path in runtimes['pam_backend']['libraries'])
            type_password(command,secret)
            until(lambda:not state()['locked'] and state()['desktop_visible'],'supervised PAM unlock')
            until(lambda:not Path(f"/proc/{current['pid']}").exists(),'supervisor reaps unlocked locker')
            if mock:until(lambda:mock_events()[-1].get('locked') is False,'logind unlocked hint after authenticated unlock')
            if hasattr(session,'check_locked_hint'):session.check_locked_hint(False)
            if mock and scale==150:
                until(lambda:'Hint denied 100% %@ %s' in log_path.read_text(),'nonfatal logind hint denial')
                send_service(mock,'allow');until(lambda:mock_events()[-1].get('deny_hints') is False,'hint acceptance restored')
            records.append(dict(scale=scale,trigger='logind signal' if scale==120 and (mock or session_factory) else 'physical shortcut' if scale==150 else 'supervisor signal',
                wrong_password_rejected=True,locker_signal_blocked=True,unlocked=True))
        sleep_evidence=None
        if mock:
            # Queue both notifications while the supervisor is stopped so the
            # final preparing state must win in one bus-dispatch iteration.
            os.kill(session.pid,signal.SIGSTOP)
            try:
                send_service(mock,'resume-prepare')
                until(lambda:any(row.get('command')=='resume-prepare' for row in mock_events()),'queued resume/sleep notifications')
            finally:os.kill(session.pid,signal.SIGCONT)
            current=until(mapped,'locker after queued resume/sleep notifications')
            assert state()['sleep_guard'],'Queued resume cleared a newer sleep guard'
            send_service(mock,'resume');until(lambda:not state()['sleep_guard'],'resume after queued notifications')
            assert state()['locked']
            type_password(command,secret);until(lambda:not state()['locked'],'PAM after queued notification recovery')
            until(lambda:not Path(f"/proc/{current['pid']}").exists(),'queued-notification locker reaped')
            def latest_inhibitor(after=0):
                return next((row for row in reversed(mock_events()) if row['event']=='inhibitor' and row['id']>after),None)
            def released(identifier):
                return next((row for row in mock_events() if row['event']=='inhibitor-released' and row['id']==identifier),None)
            inhibitor=until(latest_inhibitor,'initial logind delay inhibitor')['id']
            previous_pid=current['pid'];mode.write_text('hang');send_service(mock,'prepare')
            until(lambda:state()['sleep_guard'] and state()['locked'],'suspend guard set before locker is ready')
            until(lambda:released(inhibitor),'inhibitor released after blank frames with hung locker',timeout=5)
            protected=state();assert not protected['desktop_visible'] and not protected['active'] and protected['pending_outputs']==0
            assert protected['sleep_protected_ms']>0 and released(inhibitor)['monotonic_ms']>=protected['sleep_protected_ms']
            first_release=released(inhibitor)['monotonic_ms']
            blank={head['name']:command('output-pixels '+head['name']) for head in command('outputs')}
            assert all(row['epoch']==protected['epoch'] and row['black']==row['width']*row['height'] for row in blank.values()),blank
            hung=until(lambda:int(pidfile.read_text()) if int(pidfile.read_text())!=previous_pid else None,'hung locker launched')
            status=Path(f'/proc/{hung}/status').read_text()
            assert f'PPid:\t{session.pid}\n' in status
            os.kill(hung,0) # The inhibitor must not be inherited by this live child.
            send_service(mock,'resume');until(lambda:not state()['sleep_guard'],'resume removes only the suspend guard')
            assert state()['locked'] and not state()['desktop_visible']
            inhibitor=until(lambda:latest_inhibitor(inhibitor),'delay inhibitor reacquired after resume')['id']
            mode.unlink();os.kill(hung,signal.SIGKILL)
            current=until(lambda:mapped(hung),'PAM locker after simulated resume')
            type_password(command,secret);until(lambda:not state()['locked'],'PAM unlock after simulated resume')
            until(lambda:not Path(f"/proc/{current['pid']}").exists(),'resumed locker reaped')
            send_service(mock,'prepare');current=until(mapped,'locker under second suspend guard')
            until(lambda:released(inhibitor),'second suspend delay released after protection',timeout=5)
            before=log_path.read_text().count('Locker exited with 0')
            type_password(command,secret)
            until(lambda:log_path.read_text().count('Locker exited with 0')>before,'authenticated locker exits while suspend guard stays set')
            assert state()['sleep_guard'] and state()['locked'] and not state()['desktop_visible']
            replacement=until(lambda:mapped(current['pid']),'replacement locker while preparing sleep')
            send_service(mock,'resume');until(lambda:not state()['sleep_guard'],'second resume guard removed')
            assert state()['locked']
            until(lambda:latest_inhibitor(inhibitor),'second resume reacquires delay inhibitor')
            type_password(command,secret);until(lambda:not state()['locked'],'fresh authentication after guarded unlock')
            until(lambda:not Path(f"/proc/{replacement['pid']}").exists(),'second resumed locker reaped')
            sleep_evidence=dict(blank=blank,inhibitor_not_inherited=True,guarded_authentication_stays_locked=True,
                queued_resume_prepare_guarded=True,
                resume_stays_locked=True,delay_reacquired=True,protected_at=protected['sleep_protected_ms'],
                released_at=first_release,real_suspend=False)
        current=request();os.kill(current['pid'],signal.SIGKILL)
        replacement=until(lambda:mapped(current['pid']),'automatic locker crash recovery')
        assert replacement['state']['locked'] and not replacement['state']['desktop_visible']
        type_password(command,secret);until(lambda:not state()['locked'],'restarted locker PAM unlock')
        until(lambda:not Path(f"/proc/{replacement['pid']}").exists(),'restarted locker reaped')
        mode.write_text('exit-zero');before=len(launches.read_text().splitlines())
        os.kill(session.pid,signal.SIGUSR1)
        until(lambda:'Locker repeatedly failed' in log_path.read_text(),'bounded failed locker retries')
        assert len(launches.read_text().splitlines())==before+3
        assert state()['locked'] and not state()['desktop_visible'] and not state()['active']
        mode.unlink();current=request();type_password(command,secret)
        until(lambda:not state()['locked'],'manual retry authenticates after repeated failure')
        until(lambda:not Path(f"/proc/{current['pid']}").exists(),'manual recovery locker reaped')
        mode.write_text('hang');os.kill(session.pid,signal.SIGUSR1)
        until(lambda:'Locker startup timed out' in log_path.read_text(),'ten-second locker startup deadline',timeout=15)
        assert state()['locked'] and not state()['desktop_visible']
        mode.unlink();current=until(mapped,'automatic retry after hung locker')
        type_password(command,secret);until(lambda:not state()['locked'],'PAM unlock after startup timeout')
        if mock:
            until(lambda:not Path(f"/proc/{current['pid']}").exists(),'locker reaped before bus loss')
            previous_pid=current['pid'];inhibitor=until(latest_inhibitor,'inhibitor before bus loss')['id']
            mode.write_text('hang')
            bus.terminate();bus.wait(timeout=5)
            until(lambda:'Logind connection lost' in log_path.read_text(),'owned system bus loss detected')
            until(lambda:state()['sleep_guard'] and state()['locked'],'monitor loss locks an unlocked desktop')
            until(lambda:released(inhibitor),'retained inhibitor released after bus-loss protection',timeout=5)
            protected=state()
            assert protected['sleep_protected_ms']>0 and released(inhibitor)['monotonic_ms']>=protected['sleep_protected_ms']
            assert protected['pending_outputs']==0
            assert state()['locked'] and state()['sleep_guard'] and not state()['desktop_visible']
            sleep_evidence.update(bus_loss_protected_at=protected['sleep_protected_ms'],bus_loss_released_at=released(inhibitor)['monotonic_ms'])
            hung=until(lambda:int(pidfile.read_text()) if int(pidfile.read_text())!=previous_pid else None,'hung child after bus loss')
            assert f'PPid:\t{session.pid}\n' in Path(f'/proc/{hung}/status').read_text()
            mode.unlink();os.kill(hung,signal.SIGKILL)
            current=until(lambda:mapped(hung),'locker after monitor-loss blanking')
            before=log_path.read_text().count('Locker exited with 0')
            type_password(command,secret)
            until(lambda:log_path.read_text().count('Locker exited with 0')>before,'PAM cannot bypass guard after bus loss')
            assert state()['locked'] and state()['sleep_guard']
            current=until(lambda:mapped(current['pid']),'locker recovery while system bus is absent')
            previous_mock_events+=mock_events()
            bus,_=start_bus('system-bus-restarted');mock,mock_path=start_service('logind-restarted')
            until(lambda:not state()['sleep_guard'],'trusted reconnected logind confirms awake state')
            assert state()['locked']
            until(lambda:any(row.get('locked') is True for row in mock_events()),'locked hint republished after system bus restart')
            type_password(command,secret);until(lambda:not state()['locked'],'PAM unlock after logind bus reconnect')
            until(lambda:not Path(f"/proc/{current['pid']}").exists(),'locker reaped after bus loss')
            until(lambda:not Path(f"/proc/{current['pid']}").exists(),'locker reaped before owner restart')
            mock.terminate();mock.wait(timeout=5);previous_mock_events+=mock_events()
            until(lambda:state()['sleep_guard'] and state()['locked'],'owner loss locks an otherwise unlocked desktop')
            mock,mock_path=start_service('logind-owner-restarted')
            until(lambda:not state()['sleep_guard'],'new logind owner confirms resume')
            assert state()['locked']
            current=until(mapped,'locker after owner restart')
            until(lambda:any(row.get('locked') is True for row in mock_events()),'hint republished after logind owner restart')
            type_password(command,secret);until(lambda:not state()['locked'],'PAM unlock after logind owner restart')
        session.terminate();session.wait(timeout=5);assert session.returncode==0,log_path.read_text()
        for row in launches.read_text().splitlines():assert not Path('/proc/'+str(json.loads(row)['pid'])).exists()
        result=dict(densities=records,crash_recovery=True,zero_exit_does_not_unlock=True,bounded_retries=3,
            manual_recovery=True,startup_timeout_recovery=True,session_cleanup=True,locker_sha256=hashlib.sha256(Path(locker).read_bytes()).hexdigest(),
            runtime=runtimes,
            fake_logind=dict(pid_lookup_verified=True,wrong_session_ignored=True,wrong_sender_ignored=True,
                unauthenticated_unlock_ignored=True,hint_denial_nonfatal=True,bus_loss_keeps_lock=True,
                explicit_lock_after_bus_loss=True,bus_restart_recovery=True,owner_restart_recovery=True,
                events=previous_mock_events+mock_events()) if mock else None,
            real_logind=getattr(session,'evidence',None),
            sleep=sleep_evidence,
            scope='Real unprivileged PAM through the actual supervisor and compositor. Physical/logind/suspend/installed session remain unqualified.')
        (artifacts/'results.json').write_text(json.dumps(result,indent=2)+'\n')
        print('Supervised PAM lock: five densities, shortcut, signal blocking and failure recovery PASS')
    except BaseException:
        if control:
            try:
                (artifacts/'failure.json').write_text(json.dumps(dict(state=state(),outputs=command('outputs'),
                    session_pid=session.pid,log=log_path.read_text()),indent=2)+'\n')
            except (OSError,ValueError,AssertionError):pass
        raise
    finally:
        listener.close()
        if control:control.close()


def run(compositor, locker, artifacts, disposable, supervisor=None, logind_probe=None):
    assert disposable and os.geteuid()==0 and Path('/.dockerenv').exists(), 'Requires explicit disposable-container opt-in and root'
    artifacts.mkdir(parents=True); artifacts.chmod(0o755)
    account_name='nsl'+uuid.uuid4().hex[:10]
    secret=''.join(secrets.choice(string.ascii_lowercase) for _ in range(24))
    command=lambda args,**kw:subprocess.run(args,check=True,capture_output=True,text=True,**kw)
    processes=[];created=False;control=broker=None
    try:
        home=artifacts/'home'
        command(['useradd','--no-create-home','--home-dir',str(home),'--shell','/bin/sh',account_name]);created=True
        account=pwd.getpwnam(account_name)
        command(['chpasswd'],input=account_name+':'+secret+'\n')
        home.mkdir(mode=0o700);os.chown(home,account.pw_uid,account.pw_gid)
        runtime=home/'runtime';runtime.mkdir(mode=0o700);os.chown(runtime,account.pw_uid,account.pw_gid)
        env=dict(os.environ,HOME=str(home),USER=account_name,LOGNAME=account_name,XDG_RUNTIME_DIR=str(runtime),
            WLR_BACKENDS='headless',WLR_HEADLESS_OUTPUTS='2',WLR_RENDERER='pixman')
        for name in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','DBUS_SESSION_BUS_ADDRESS'):env.pop(name,None)
        identity=dict(user=account.pw_uid,group=account.pw_gid,extra_groups=[],start_new_session=True)
        if supervisor:
            run_supervised(supervisor,compositor,locker,artifacts,home,runtime,env,identity,secret,processes,logind_probe)
            return
        control,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);control.settimeout(5)
        broker,peer=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
        with (artifacts/'compositor.log').open('w') as log:
            server=subprocess.Popen([compositor,'-c',str(child.fileno()),'-S',str(peer.fileno())],
                pass_fds=[child.fileno(),peer.fileno()],env=env,stdout=subprocess.PIPE,stderr=log,text=True,**identity)
        processes.append(server);child.close();peer.close()
        def control_command(value):
            control.sendall(value.encode());return json.loads(control.recv(65536))
        def state():return control_command('lock-state')
        assert select.select([server.stdout],[],[],10)[0]
        line=server.stdout.readline().strip();assert line.startswith('WAYLAND_DISPLAY='),line
        env['WAYLAND_DISPLAY']=line.split('=',1)[1]
        def start_locker(label):
            endpoint,connection=socket.socketpair()
            broker.sendmsg([b'L'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[endpoint.fileno()]))]);endpoint.close()
            ready,notify=os.pipe2(os.O_CLOEXEC)
            path=artifacts/(label+'.log')
            with path.open('w') as log:
                process=subprocess.Popen([locker,'--config','/dev/null','--color','303030','--ready-fd',str(notify)],
                    pass_fds=[connection.fileno(),notify],env=dict(env,WAYLAND_SOCKET=str(connection.fileno())),
                    stdout=log,stderr=log,**identity)
            processes.append(process);connection.close();os.close(notify)
            try:
                assert select.select([ready],[],[],10)[0],path.read_text()
                assert os.read(ready,1)==b'\n',path.read_text()
            finally:os.close(ready)
            assert state()['locked'] and state()['acknowledged'] and not state()['desktop_visible']
            def mapped_surfaces():
                rows=control_command('lock-surfaces')
                return rows if len(rows)==len(control_command('outputs')) and all(row['mapped'] for row in rows) else None
            surfaces=until(mapped_surfaces,'actual mapped PAM locker surfaces')
            status=Path(f'/proc/{process.pid}/status').read_text()
            uid_line=next(row for row in status.splitlines() if row.startswith('Uid:'))
            assert set(map(int,uid_line.split()[1:]))=={account.pw_uid}
            return process,path,surfaces
        records=[]
        for scale in (120,150,180,210,240):
            for head in control_command('outputs'):
                assert control_command(f"test-scale {head['name']} {scale} 10000")['ok'];assert control_command('confirm')['ok']
            process,path,surfaces=start_locker('density-'+str(scale))
            type_password(control_command,'wrong')
            until(lambda:'pam_authenticate failed: invalid credentials' in path.read_text(),'actual PAM rejection')
            assert process.poll() is None and state()['locked'] and not state()['desktop_visible']
            type_password(control_command,secret)
            until(lambda:process.poll() is not None,'PAM locker success')
            assert process.returncode==0,path.read_text()
            until(lambda:not state()['locked'] and state()['desktop_visible'],'PAM-authenticated unlock')
            records.append(dict(scale=scale,uid=account.pw_uid,surfaces=surfaces,wrong_password_rejected=True,unlocked=True))
        process,path,surfaces=start_locker('crashed')
        os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
        until(lambda:state()['locked'] and not state()['active'],'PAM locker crash remains locked')
        replacement,path,surfaces=start_locker('recovered')
        type_password(control_command,secret);until(lambda:replacement.poll() is not None,'replacement PAM unlock')
        assert replacement.returncode==0,path.read_text()
        until(lambda:not state()['locked'],'PAM recovered unlock')
        server.terminate();server.wait(timeout=5);assert server.returncode==0
        record=dict(densities=records,crash_recovery=True,
            locker_sha256=hashlib.sha256(Path(locker).read_bytes()).hexdigest(),
            pam_policy=Path('/etc/pam.d/swaylock').read_text(),account=account_name,
            scope='Disposable headless Linux account; real PAM rejection and success. No host account, physical display or installed session qualification.')
        (artifacts/'results.json').write_text(json.dumps(record,indent=2)+'\n')
        print('Unprivileged PAM locker: five densities, rejected passwords and crash recovery PASS')
    finally:
        for process in reversed(processes):
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            process.wait(timeout=5)
            if process.stdout:process.stdout.close()
            if process.stdin:process.stdin.close()
        if control:control.close()
        if broker:broker.close()
        if created:command(['userdel',account_name])
        try:pwd.getpwnam(account_name)
        except KeyError:(artifacts/'cleanup.json').write_text('{"account_removed":true}\n')
        else:raise AssertionError('Disposable locker account remains')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--compositor',required=True)
    parser.add_argument('--locker',default='/usr/bin/swaylock');parser.add_argument('--artifacts',required=True,type=Path)
    parser.add_argument('--supervisor')
    parser.add_argument('--logind-probe')
    parser.add_argument('--disposable-container',action='store_true');args=parser.parse_args()
    if args.logind_probe and not args.supervisor:parser.error('--logind-probe requires --supervisor')
    run(args.compositor,args.locker,args.artifacts,args.disposable_container,args.supervisor,args.logind_probe)
