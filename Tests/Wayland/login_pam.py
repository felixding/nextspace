#!/usr/bin/env python3
"""Opt-in greetd/PAM lifecycle checks in an owned disposable systemd guest."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import secrets
import select
import shutil
import shlex
import signal
import string
import subprocess
import sys
import time
import uuid


def until(check, description, timeout=20):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        value = check()
        if value: return value
        time.sleep(0.05)
    raise AssertionError('Timed out: '+description)


def identity():
    names = ('HOME','USER','LOGNAME','SHELL','GREETD_SOCK','XDG_RUNTIME_DIR','XDG_SESSION_ID',
        'XDG_SESSION_CLASS','XDG_SESSION_TYPE','XDG_SESSION_DESKTOP','NEXTSPACE_PAM_SENTINEL')
    return dict(pid=os.getpid(), uid=os.getuid(), euid=os.geteuid(), gid=os.getgid(),
        groups=os.getgroups(), sid=os.getsid(0), environment={key:os.environ[key] for key in names if key in os.environ})


def fixture_mode():
    mode = sys.argv[1]
    destination = Path(sys.argv[2])
    if mode == '--pam-event':
        row = dict(user=os.environ.get('PAM_USER'), event=os.environ.get('PAM_TYPE'),
            euid=os.geteuid(), time=time.time())
        with destination.open('a') as log: log.write(json.dumps(row)+'\n')
    elif mode == '--greeter':
        destination.write_text(json.dumps(identity(), indent=2)+'\n')
        while True: signal.pause()
    elif mode in ('--user','--user-agent'):
        row = identity(); row['arguments'] = sys.argv[4:]
        destination.write_text(json.dumps(row, indent=2)+'\n')
        if mode=='--user-agent':
            from lock_logind_guest import user_agent
            user_agent(destination.parent,Path(sys.argv[3]))
        else:until(lambda: Path(sys.argv[3]).exists(), 'user release', 60)
    else: raise ValueError(mode)


def run(greetd, probe, wrapper, artifacts, disposable_guest, native_directory=None, user_desktop=False,
        logout_keyboard=False, user_hook=None, vt=None, kernel_input=None):
    assert disposable_guest and os.geteuid() == 0, 'Requires explicit disposable-guest opt-in and root'
    assert not user_desktop or native_directory, 'The user desktop check requires a prepared native greeter candidate'
    assert not logout_keyboard or user_desktop, 'Keyboard logout requires the actual user desktop check'
    assert not user_hook or native_directory is None,'The user hook uses the standalone PAM handoff fixture'
    assert Path('/run/systemd/system').is_dir(), 'Requires a running systemd/logind guest'
    active_vt = Path('/sys/class/tty/tty0/active').read_text().strip()
    assert vt is None or (native_directory and 1 <= vt <= 63 and active_vt != 'tty'+str(vt)), 'Use an unused VT for the native fixture'
    assert not kernel_input or (vt and user_desktop), 'Kernel input requires the native desktop on an isolated VT'
    artifacts.mkdir(parents=True)
    os.chmod(artifacts, 0o755)
    shutil.copy2(Path(__file__).resolve(), artifacts/'source.py')
    token = uuid.uuid4().hex[:10]
    greeter, user, group = 'nsg'+token, 'nsu'+token, 'nst'+token
    unit = 'nextspace-pam-'+token
    general_service, greeter_service = unit, unit+'-greeter'
    services = [Path('/etc/pam.d')/name for name in (general_service,greeter_service)]
    for path in services: assert not path.exists()
    created_users, created_group, started = [], False, False
    endpoint, socket_identity = None, None
    command = lambda args, **kwargs: subprocess.run(args, check=True, capture_output=True, text=True, **kwargs)
    secret = ''.join(secrets.choice(string.ascii_lowercase) for _ in range(32)) if native_directory or user_hook else secrets.token_urlsafe(32)
    records, runtimes = [], {}
    try:
        command(['groupadd', group]); created_group = True
        for name in (greeter, user):
            home = artifacts/name
            command(['useradd', '--no-create-home', '--home-dir', str(home), '--shell', '/bin/sh',
                *(['--groups',group+(',video,input' if vt else '')] if name == user else
                  ['--groups','video,input'] if vt else []), name])
            created_users.append(name)
            account = pwd.getpwnam(name)
            home.mkdir(mode=0o700); os.chown(home,account.pw_uid,account.pw_gid)
        command(['chpasswd'], input=user+':'+secret+'\n')
        hook = f'session optional pam_exec.so /usr/bin/python3 {shlex.quote(str(Path(__file__).resolve()))} --pam-event {shlex.quote(str(artifacts/"pam-events.jsonl"))}\n'
        # greetd0.10.3 always supplies seat0. Headless PAM must clear that seat
        # and give logind VT0 rather than pretending to own the active console.
        headless_env = artifacts/'headless-pam.conf'
        headless_env.write_text(f'XDG_SEAT DEFAULT=seat0 OVERRIDE=seat0\nXDG_VTNR DEFAULT={vt} OVERRIDE={vt}\n' if vt else
            'XDG_SEAT DEFAULT="" OVERRIDE=""\nXDG_VTNR DEFAULT=0 OVERRIDE=0\n')
        if native_directory:
            with headless_env.open('a') as stream:stream.write('XDG_SESSION_TYPE DEFAULT=wayland OVERRIDE=wayland\n')
        prepare = 'session required pam_env.so conffile='+str(headless_env)+' readenv=0\n'
        services[0].write_text('@include common-auth\n@include common-account\n'+prepare+'@include common-session\n'+hook)
        services[1].write_text('auth required pam_permit.so\naccount required pam_permit.so\nsession required pam_unix.so\n'+prepare+'session optional pam_systemd.so\n'+hook)
        for path in services:
            os.chmod(path,0o644)
            (artifacts/(path.name+'.pam')).write_text(path.read_text())
        greeter_home = artifacts/greeter; user_home = artifacts/user
        cfg = artifacts/'greetd.toml'
        greeter_command = shlex.join([sys.executable, str(Path(__file__).resolve()), '--greeter', str(greeter_home/'identity.json')])
        native_context = None
        if native_directory:
            from login_native_pam import prepare as prepare_native
            native_context = dict(root=native_directory,artifacts=artifacts,greeter=greeter,user=user,group=group,
                greeter_home=greeter_home,user_home=user_home,secret=secret,general_service=general_service,
                active_vt=active_vt,pam_driver=Path(__file__).resolve(),user_desktop=user_desktop,
                logout_keyboard=logout_keyboard,vt=vt,kernel_input=kernel_input)
            greeter_command = shlex.join(prepare_native(native_context))
        terminal = f'vt = {vt}\nswitch = true\n' if vt else 'vt = "none"\nswitch = false\n'
        cfg.write_text('[terminal]\n'+terminal+'[general]\nsource_profile = false\n'+
            f'runfile = "{artifacts}/greetd.run"\nservice = "{general_service}"\n[default_session]\n'+
            f'user = "{greeter}"\nservice = "{greeter_service}"\ncommand = {json.dumps(greeter_command)}\n')
        started = True
        command(['systemd-run','--quiet','--unit='+unit,'--property=KillMode=control-group',
            '--property=TimeoutStopSec=5s','--property=LimitCORE=0',str(greetd),'-c',str(cfg)])
        daemon_pid = int(command(['systemctl','show',unit,'--property=MainPID','--value']).stdout.strip())
        assert daemon_pid > 0
        # greetd0.10.3 accepts --socket-path but does not consume its value.
        # Discover its owned endpoint, then verify the greeter got that address.
        endpoint = Path('/run/greetd-'+str(daemon_pid)+'.sock')
        until(lambda:(greeter_home/'identity.json').exists(), 'greeter PAM session')
        before = json.loads((greeter_home/'identity.json').read_text())
        greeter_account = pwd.getpwnam(greeter); user_account = pwd.getpwnam(user)
        assert before['uid'] == before['euid'] == greeter_account.pw_uid and before['uid'] != 0, before
        assert before['environment']['GREETD_SOCK'] == str(endpoint), before
        socket_identity = endpoint.stat()
        assert socket_identity.st_uid == greeter_account.pw_uid, socket_identity
        greeter_details = command(['loginctl','show-session',before['environment']['XDG_SESSION_ID'],'--all']).stdout
        (artifacts/'greeter-logind-session.txt').write_text(greeter_details)
        assert 'Class=greeter\n' in greeter_details and 'Service='+greeter_service+'\n' in greeter_details
        (artifacts/'greeter-before.json').write_text(json.dumps(before,indent=2)+'\n')
        if native_context:
            from login_native_pam import drive
            native_context.update(before=before,greetd=greetd)
            result=drive(native_context)
            (artifacts/'results.json').write_text(json.dumps(result,indent=2)+'\n')
            print('Native Login real PAM/UI: compositor ownership, authentication, user handoff and logout/regreet PASS')
            return
        def exchange(name, password, ending):
            replies = []
            with (artifacts/(name+'.stderr')).open('w') as errors:
                process = subprocess.Popen(['/bin/sh',str(wrapper),str(probe),str(endpoint),'--stream'],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, text=True,
                    user=greeter_account.pw_uid, group=greeter_account.pw_gid, extra_groups=[],
                    env=dict(os.environ, HOME=str(greeter_home), USER=greeter, LOGNAME=greeter))
            def request(step):
                process.stdin.write(json.dumps(step)+'\n'); process.stdin.flush()
                assert select.select([process.stdout],[],[],35)[0], 'No Foundation client response'
                line = process.stdout.readline()
                assert secret not in line, 'Secret reached fixture output'
                assert line, 'PAM transport ended without a response; use the stream-capable LoginSessionProbe'
                reply = json.loads(line)
                replies.append(reply)
                assert 'reply' in reply, reply
                return reply['reply']
            try:
                first = request(dict(operation='begin',user=user))
                assert first['type'] == 'auth_message' and first['auth_message_type'] == 'secret', first
                libraries = sorted({line.split()[-1] for line in Path(f'/proc/{process.pid}/maps').read_text().splitlines()
                    if 'libgnustep-base.so.' in line or 'libobjc.so.' in line})
                assert all(any(token in name for name in libraries) for token in ('libgnustep-base.so.','libobjc.so.')), libraries
                status = Path(f'/proc/{process.pid}/status').read_text().splitlines()
                uids = next(line.split()[1:] for line in status if line.startswith('Uid:'))
                assert all(int(uid) == greeter_account.pw_uid for uid in uids), uids
                runtimes[name] = dict(pid=process.pid, executable=str(Path(f'/proc/{process.pid}/exe').resolve()),
                    uids=uids, libraries={path:hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in libraries})
                (artifacts/(name+'-runtime.json')).write_text(json.dumps(runtimes[name],indent=2)+'\n')
                reply = request(dict(operation='respond',response=password))
                while reply['type'] == 'auth_message':
                    assert reply['auth_message_type'] in ('info','error'), reply
                    reply = request(dict(operation='respond'))
                for step in ending: request(step)
                process.stdin.close()
                assert process.wait(timeout=5) == 0
            finally:
                if not process.stdin.closed: process.stdin.close()
                if process.poll() is None: process.terminate(); process.wait(timeout=5)
                process.stdout.close()
            assert secret not in (artifacts/(name+'.stderr')).read_text(), 'Secret reached client diagnostics'
            (artifacts/(name+'.json')).write_text(json.dumps(replies,indent=2)+'\n')
            records.append(dict(name=name, replies=replies))
            return replies
        cancel = dict(operation='cancel')
        def rejected(rows):
            assert rows[-3]['reply']['error_type'] == 'auth_error', rows
            # greetd clears configuring before cancelling its PAM worker. An
            # already-exited worker can return a generic cancellation error.
            # A second cancellation must be an idle success, and the next
            # independent authentication must work without restarting greetd.
            reply = rows[-2]['reply']
            assert reply['type'] == 'success' or (reply['type'] == 'error' and reply['error_type'] == 'error'), rows
            assert rows[-1]['reply']['type'] == 'success', rows
        rows = exchange('wrong-password', 'wrong-'+secrets.token_urlsafe(16), [cancel,cancel])
        rejected(rows)
        rows = exchange('authenticated-cancel', secret, [cancel])
        assert rows[-2]['reply']['type'] == rows[-1]['reply']['type'] == 'success', rows
        command(['chage','--expiredate','0',user])
        rows = exchange('expired-account', secret, [cancel,cancel])
        rejected(rows)
        command(['chage','--expiredate','-1',user])
        release = artifacts/'release-user'
        literal = ['space value',"a'b",'日本語','$(touch forbidden)','`touch forbidden`','; touch forbidden']
        arguments = [sys.executable,str(Path(__file__).resolve()),'--user-agent' if user_hook else '--user',str(user_home/'identity.json'),str(release),*literal]
        rows = exchange('start-session', secret, [dict(operation='start',arguments=arguments,
            environment=['XDG_SESSION_TYPE=wayland','XDG_SESSION_CLASS=user','XDG_SESSION_DESKTOP=NextSpace',
                'NEXTSPACE_PAM_SENTINEL='+token])])
        assert rows[-2]['reply']['type'] == rows[-1]['reply']['type'] == 'success', rows
        until(lambda:(user_home/'identity.json').exists(), 'authenticated user launch')
        after = json.loads((user_home/'identity.json').read_text())
        assert after['uid'] == after['euid'] == user_account.pw_uid and after['uid'] != 0, after
        assert after['gid'] == user_account.pw_gid and pwd.getpwnam(user).pw_gid in after['groups'], after
        import grp
        assert grp.getgrnam(group).gr_gid in after['groups'], after
        assert after['arguments'] == literal and not (user_home/'forbidden').exists(), after
        env = after['environment']
        assert env['HOME'] == str(user_home) and env['USER'] == env['LOGNAME'] == user, after
        assert env['XDG_SESSION_TYPE'] == 'wayland' and 'XDG_SESSION_CLASS' not in env, after
        assert env['XDG_SESSION_DESKTOP'] == 'NextSpace' and env['NEXTSPACE_PAM_SENTINEL'] == token, after
        assert 'GREETD_SOCK' not in env, after
        assert Path(env['XDG_RUNTIME_DIR']).stat().st_uid == user_account.pw_uid, after
        assert not Path('/proc/'+str(before['pid'])).exists(), 'Previous greeter survived user handoff'
        session = env['XDG_SESSION_ID']
        details = command(['loginctl','show-session',session,'--all']).stdout
        (artifacts/'user-logind-session.txt').write_text(details)
        assert 'Class=user\n' in details and 'Type=wayland\n' in details and 'Service='+general_service+'\n' in details
        (artifacts/'user-session.json').write_text(json.dumps(after,indent=2)+'\n')
        user_checks=user_hook(dict(user=user,user_account=user_account,user_home=user_home,secret=secret,
            environment=env,artifacts=artifacts,session=session,details=details)) if user_hook else None
        release.touch()
        def returned():
            value = json.loads((greeter_home/'identity.json').read_text())
            return value if value['pid'] != before['pid'] else None
        returned_greeter = until(returned, 'greeter restart after logout')
        assert returned_greeter['uid'] == greeter_account.pw_uid
        (artifacts/'greeter-after.json').write_text(json.dumps(returned_greeter,indent=2)+'\n')
        events = [json.loads(line) for line in (artifacts/'pam-events.jsonl').read_text().splitlines()]
        assert any(e['user']==user and e['event']=='open_session' for e in events), events
        assert any(e['user']==user and e['event']=='close_session' for e in events), events
        assert all(e['euid']==0 for e in events), events
        assert Path('/sys/class/tty/tty0/active').read_text().strip() == active_vt, 'Test changed the active VT'
        result = dict(cases=records, greeter_uid=greeter_account.pw_uid, user_uid=user_account.pw_uid,
            user_checks=user_checks,
            actual_client_runtimes=runtimes,
            vt='none', headless_pam_environment=True, original_active_vt=active_vt,
            greetd_sha256=hashlib.sha256(greetd.read_bytes()).hexdigest(),
            probe_sha256=hashlib.sha256(probe.read_bytes()).hexdigest(), real_pam=True,
            scope='Extracted greetd binary, real PAM password/account checks, unprivileged client, credential/group handoff, headless logind environment, close_session and greeter restart. Fixture PAM clears the seat and uses VT0; a fixture user command runs. No native greeter, console/VT, GPU or full desktop handoff qualification.')
        (artifacts/'results.json').write_text(json.dumps(result,indent=2)+'\n')
        print('Native Login PAM: password rejection, account expiry, cancellation, user handoff and logout PASS')
    finally:
        if started:
            stopped = subprocess.run(['systemctl','stop',unit],capture_output=True)
            # An exited transient unit may already have been unloaded.
            if stopped.returncode not in (0,5): stopped.check_returncode()
            journal = subprocess.run(['journalctl','-u',unit,'--no-pager'],capture_output=True,text=True)
            (artifacts/'greetd-journal.log').write_text(journal.stdout)
            subprocess.run(['systemctl','reset-failed',unit],check=False,capture_output=True)
        if endpoint and socket_identity and endpoint.exists():
            current = endpoint.stat()
            assert (current.st_dev,current.st_ino) == (socket_identity.st_dev,socket_identity.st_ino)
            endpoint.unlink()
        for path in services: path.unlink(missing_ok=True)
        for name in reversed(created_users):
            subprocess.run(['loginctl','terminate-user',name],check=False,capture_output=True)
            until(lambda: subprocess.run(['userdel',name],capture_output=True).returncode == 0,
                'temporary account cleanup '+name)
        if created_group: command(['groupdel',group])
        if vt:
            from vt_switch import activate
            activate(int(active_vt.removeprefix('tty')))
            assert Path('/sys/class/tty/tty0/active').read_text().strip() == active_vt
        (artifacts/'cleanup.json').write_text(json.dumps(dict(users_removed=created_users,
            pam_services_removed=all(not path.exists() for path in services), unit_stopped=True),indent=2)+'\n')


if __name__ == '__main__':
    if sys.argv[1:2] and sys.argv[1] in ('--greeter','--user','--user-agent','--pam-event'): fixture_mode()
    else:
        p = argparse.ArgumentParser(description=__doc__)
        p.add_argument('--disposable-guest',action='store_true')
        p.add_argument('--native-greeter',type=Path,help='Prepared public candidate directory for real native greeter ownership tests')
        p.add_argument('--user-desktop',action='store_true',help='Exercise the actual Workspace user desktop with the native greeter')
        p.add_argument('--logout-keyboard',action='store_true',help='Confirm logout with Return after cancelling once')
        p.add_argument('--vt',type=int,help='Use an unused real VT and DRM/libinput instead of the headless backend')
        p.add_argument('--kernel-input',nargs=2,metavar=('KEYBOARD','POINTER'),help='Clone these input devices to check kernel keyboard VT switching')
        for name in ('greetd','probe','wrapper','artifacts'):p.add_argument('--'+name,type=Path,required=True)
        args = p.parse_args()
        run(args.greetd.resolve(),args.probe.resolve(),args.wrapper.resolve(),args.artifacts.resolve(),args.disposable_guest,
            args.native_greeter.resolve() if args.native_greeter else None,args.user_desktop,args.logout_keyboard,
            vt=args.vt,kernel_input=args.kernel_input)
