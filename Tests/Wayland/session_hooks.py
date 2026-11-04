#!/usr/bin/env python3
"""Check legacy user hooks around the actual native supervisor in a disposable container."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import pwd
import signal
import subprocess
import tempfile
import uuid

from integration import read_json_lines, until


def run(supervisor, compositor, helper, shell_probe, artifacts):
    assert os.geteuid() == 0 and Path('/.dockerenv').exists()
    artifacts.mkdir(parents=True)
    account = 'nshook' + uuid.uuid4().hex[:8]
    with tempfile.TemporaryDirectory(prefix='nextspace-session-hooks-') as scratch:
        scratch = Path(scratch)
        scratch.chmod(0o755)
        home = scratch / 'home'
        subprocess.run(['useradd', '--no-create-home', '--home-dir', str(home), '--shell', '/bin/sh', account], check=True)
        owner = pwd.getpwnam(account)
        try:
            home.mkdir(mode=0o700)
            runtime = home / 'runtime'; runtime.mkdir(mode=0o700)
            preferences = home / 'Library/Preferences/.NextSpace/Login'
            preferences.parent.mkdir(parents=True)
            script = home / 'record.py'
            script.write_text('''import json,os,signal,socket,sys,time
from pathlib import Path
path=Path.home()/'events.jsonl'
row=dict(phase=sys.argv[1],arguments=sys.argv[2:],uid=os.getuid(),pid=os.getpid(),
    environment={key:os.environ.get(key) for key in ('HOME','XDG_SESSION_CLASS','XDG_SESSION_TYPE',
        'WAYLAND_DISPLAY','DISPLAY','GREETD_SOCK','WAYLAND_SOCKET','NEXTSPACE_SESSION_ID')})
try:
    with socket.socket(socket.AF_UNIX) as connection:
        connection.connect(str(Path(os.environ['XDG_RUNTIME_DIR'])/os.environ['WAYLAND_DISPLAY']))
    row['native_display_available']=True
except OSError:row['native_display_available']=False
with path.open('a') as log:log.write(json.dumps(row)+'\\n')
if sys.argv[1]=='login' and os.environ.get('NEXTSPACE_HOOK_CASE')=='blocked':
    signal.signal(signal.SIGTERM,signal.SIG_IGN)
    while True:time.sleep(.1)
if sys.argv[1]=='login' and os.environ.get('NEXTSPACE_HOOK_CASE')=='failed':sys.exit(7)
''')
            logout = home / 'logout hook'
            logout.write_text('#!/bin/sh\nexec /usr/bin/python3 "'+str(script)+'" logout\n')
            logout.chmod(0o700)
            for path in [home, *home.rglob('*')]: os.chown(path, owner.pw_uid, owner.pw_gid)
            environment = dict(os.environ, HOME=str(home), USER=account, LOGNAME=account,
                XDG_RUNTIME_DIR=str(runtime), XDG_SESSION_CLASS='user', WLR_BACKENDS='headless',
                WLR_HEADLESS_OUTPUTS='2', WLR_RENDERER='pixman')
            for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','GREETD_SOCK','NEXTSPACE_SESSION_ID'):
                environment.pop(key, None)
            events = home / 'events.jsonl'
            def read_events():
                return [json.loads(line) for line in events.read_text().splitlines()] if events.exists() else []
            configuration = dict(LoginHook=['/usr/bin/python3',str(script),'login','literal $(false); 日本語'],
                                 LogoutHook=str(logout))
            records = []
            for case in ('normal','compositor-loss','failed','blocked'):
                directory = artifacts / case; directory.mkdir()
                events.unlink(missing_ok=True)
                data = plistlib.dumps(configuration); preferences.write_bytes(data)
                with (directory/'stdout.log').open('w') as out, (directory/'stderr.log').open('w') as err:
                    process = subprocess.Popen([str(supervisor),'--compositor',str(compositor),
                        '--session-hook',str(helper),'--',str(shell_probe)],
                        env=dict(environment,NEXTSPACE_HOOK_CASE=case),user=owner.pw_uid,group=owner.pw_gid,
                        extra_groups=[],cwd=home,stdin=subprocess.PIPE,stdout=out,stderr=err,text=True)
                observed = set()
                def children():
                    ids = [int(pid) for pid in Path(f'/proc/{process.pid}/task/{process.pid}/children').read_text().split()]
                    observed.update(ids)
                    return ids
                def ready(count=1):
                    assert process.poll() is None, (directory/'stderr.log').read_text()
                    return sum(row.get('event')=='ready' for row in read_json_lines(directory/'stdout.log','{')) >= count
                try:
                    until(lambda:any(row['phase']=='login' for row in read_events()), 'user LoginHook runs')
                    if case == 'blocked':
                        children(); process.terminate()
                    else:
                        until(ready, 'native shell starts after LoginHook')
                        def actor(path):
                            return next(pid for pid in children() if
                                Path(f'/proc/{pid}/comm').read_text().strip()==path.name[:15])
                        if case == 'normal':
                            os.kill(actor(shell_probe), signal.SIGKILL)
                            until(lambda:ready(2), 'shell restarts without repeating LoginHook')
                            children()
                        if case == 'compositor-loss': os.kill(actor(compositor),signal.SIGKILL)
                        else: process.stdin.write('quit\n');process.stdin.flush()
                    process.wait(timeout=15)
                    expected = {'normal':0,'compositor-loss':1,'failed':7,'blocked':0}[case]
                    assert process.returncode==expected,(case,process.returncode,(directory/'stderr.log').read_text())
                    rows=read_events()
                    assert [row['phase'] for row in rows]==['login','logout'],rows
                    assert rows[0]['arguments']==['literal $(false); 日本語']
                    assert all(row['uid']==owner.pw_uid for row in rows)
                    for row in rows:
                        env=row['environment']
                        assert env['HOME']==str(home) and env['XDG_SESSION_CLASS']=='user'
                        assert env['XDG_SESSION_TYPE']=='wayland' and env['NEXTSPACE_SESSION_ID'].startswith('wayland-')
                        assert env['DISPLAY'] is None and env['GREETD_SOCK'] is None and env['WAYLAND_SOCKET'] is None
                    assert rows[0]['environment']['WAYLAND_DISPLAY']
                    assert rows[0]['native_display_available']
                    assert rows[1]['native_display_available']==(case!='compositor-loss')
                    assert preferences.read_bytes()==data
                    observed.update(row['pid'] for row in rows)
                    assert all(not Path(f'/proc/{pid}').exists() for pid in observed)
                    if case=='blocked':
                        assert not any(row.get('event')=='ready' for row in read_json_lines(directory/'stdout.log','{'))
                    (directory/'events.json').write_text(json.dumps(rows,indent=2)+'\n')
                    records.append(dict(case=case,returncode=process.returncode,observed_pids_reaped=sorted(observed)))
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:process.wait(timeout=10)
                        except subprocess.TimeoutExpired:process.kill();process.wait()
                    process.stdin.close()
            # Original OpenStep preferences and empty hooks remain supported.
            direct = []
            for content, code in [(b'{ LoginHook = ""; }',0),(b'{ LoginHook = (); }',0),
                                  (plistlib.dumps({'LoginHook':[1]}),2),
                                  (plistlib.dumps({'LoginHook':False}),2)]:
                preferences.write_bytes(content)
                value=subprocess.run([str(helper),'LoginHook'],env=environment,user=owner.pw_uid,
                    group=owner.pw_gid,extra_groups=[],cwd=home,capture_output=True,timeout=10)
                assert value.returncode==code,(content,value.stderr)
                direct.append(dict(preferences_sha256=hashlib.sha256(content).hexdigest(),returncode=code))
            refused=subprocess.run([str(helper),'LoginHook'],capture_output=True,timeout=10,
                preexec_fn=lambda:os.seteuid(owner.pw_uid))
            assert refused.returncode==1 and b'matching user credentials' in refused.stderr
            result=dict(passed=True,cases=records,empty_and_invalid_profiles=direct,mismatched_credentials_rejected=True,
                user_profile_unchanged=True,headless_only=True,real_pam_tested=False,full_plan_complete=False,
                executables={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (supervisor,compositor,helper,shell_probe)})
            (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
            print('Native user hooks: ordering, shell restart, compositor loss, failure and cancellation PASS')
        finally:
            subprocess.run(['userdel',account],check=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable-container',action='store_true',required=True)
    for name in ('supervisor','compositor','helper','shell-probe','artifacts'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    run(args.supervisor.resolve(),args.compositor.resolve(),args.helper.resolve(),args.shell_probe.resolve(),args.artifacts.resolve())
