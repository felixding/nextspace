#!/usr/bin/env python3
"""Native host startup policy, peer credentials and bounded failure cleanup."""
import argparse
import json
import os
from pathlib import Path
import select
import subprocess
import tempfile
import time

p=argparse.ArgumentParser(description=__doc__)
for key in ['supervisor','compositor','shell-probe','output']:p.add_argument('--'+key,type=Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);rows=[]
def check(case,passed,**data):
    rows.append(dict(case=case,passed=bool(passed),**data));(a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
for mode in ['without-private-bus','greeter','failed-host','foreign-listener']:
    out=a.output/mode;out.mkdir()
    with tempfile.TemporaryDirectory(prefix='native-ui-failure-') as runtime:
        env=dict(os.environ,XDG_RUNTIME_DIR=runtime,XDG_SESSION_CLASS='greeter' if mode=='greeter' else 'user',WLR_BACKENDS='headless',WLR_RENDERER='pixman')
        for name in ['DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','LD_PRELOAD']:env.pop(name,None)
        host='/bin/false'
        if mode=='foreign-listener':
            script=out/'foreign-host';script.write_text('''#!/usr/bin/python3
import os,socket,time
from pathlib import Path
pid=os.fork()
if not pid:
 s=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET);s.bind(os.environ['NEXTSPACE_NATIVE_UI_SOCKET']);os.chmod(os.environ['NEXTSPACE_NATIVE_UI_SOCKET'],0o600);s.listen(30)
 Path('''+repr(str(out/'listening'))+''').write_text(str(os.getpid()))
 while True:time.sleep(1)
else:os.waitpid(pid,0)
''');script.chmod(0o700);host=str(script)
        args=[str(a.supervisor),*(['--private-bus'] if mode!='without-private-bus' else []),
            '--native-ui-host',host,'--compositor',str(a.compositor),'--',str(a.shell_probe)]
        if mode in ['without-private-bus','greeter']:
            result=subprocess.run(args,env=env,capture_output=True,text=True,timeout=5)
            (out/'stderr').write_text(result.stderr)
            check(mode+'-rejected-before-display',result.returncode==1 and 'requires a private authenticated user bus' in result.stderr and 'WAYLAND_DISPLAY=' not in result.stdout)
            continue
        session=subprocess.Popen(args,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(out/'stderr').open('w'))
        os.set_blocking(session.stdout.fileno(),False);pending=b'';events=[];lines=[];observed={session.pid}
        def pump():
            global pending
            while select.select([session.stdout],[],[],0)[0]:
                data=os.read(session.stdout.fileno(),65536)
                if not data:break
                pending+=data
                while b'\n' in pending:
                    line,pending=pending.split(b'\n',1);text=line.decode(errors='replace');lines.append(text)
                    if text.startswith('{'):
                        try:events.append(json.loads(text))
                        except ValueError:pass
            (out/'stdout').write_text('\n'.join(lines)+'\n')
            return events
        def wait(predicate,timeout=10):
            end=time.monotonic()+timeout
            while True:
                pump()
                if predicate():return
                assert session.poll() is None,(session.returncode,(out/'stderr').read_text())
                assert time.monotonic()<end,lines[-10:]
                time.sleep(.02)
        def children():
            ids={session.pid};changed=True
            while changed:
                before=len(ids)
                for pid in list(ids):
                    try:ids.update(int(v) for v in Path('/proc',str(pid),'task',str(pid),'children').read_text().split())
                    except OSError:pass
                changed=before!=len(ids)
            observed.update(ids)
        try:
            if mode=='failed-host':
                wait(lambda:any(e.get('event')=='ready' and 'windows' in e for e in events))
                check('three-failed-hosts-disable-optional-service',(out/'stderr').read_text().count('Native UI host exited with 1.')==3 and 'continuing without it' in (out/'stderr').read_text())
                directories=list(Path(runtime).glob('nextspace-native-ui-*'));assert len(directories)==1
                check('failed-host-leaves-no-listening-endpoint',not (directories[0]/'controls').exists())
                protected=out/'protected';protected.mkdir();(protected/'keep').write_text('Preserve this file\n')
                (directories[0]/'outside-link').symlink_to(protected,target_is_directory=True)
                children();session.stdin.write(b'quit\n');session.stdin.flush()
                session.wait(timeout=15);pump()
                check('failed-host-keeps-desktop-and-normal-exit',session.returncode==0)
                check('runtime-cleanup-does-not-follow-symlinks',(protected/'keep').read_text()=='Preserve this file\n' and not directories[0].exists())
            else:
                wait(lambda:(out/'listening').exists())
                # Give the real supervisor multiple polls after the foreign
                # listener becomes live. Matching uid/path alone is insufficient.
                end=time.monotonic()+.5
                while time.monotonic()<end:pump();time.sleep(.02)
                check('different-listener-pid-is-not-ready',not any(e.get('event')=='ready' and 'windows' in e for e in events) and not any(l.startswith('NEXTSPACE_NATIVE_UI_SOCKET=') for l in lines))
                children();session.terminate();session.wait(timeout=15);pump()
                check('foreign-listener-session-cleans-runtime',session.returncode==0 and not list(Path(runtime).glob('nextspace-native-ui-*')))
        finally:
            if session.poll() is None:
                children();session.terminate()
                try:session.wait(timeout=15)
                except subprocess.TimeoutExpired:session.kill();session.wait(timeout=5)
            live=[]
            for pid in observed:
                try:
                    if Path('/proc',str(pid),'stat').read_text().rsplit(') ',1)[1].split()[0] not in ['Z','X']:live.append(pid)
                except FileNotFoundError:pass
            (out/'cleanup.json').write_text(json.dumps(dict(pids=sorted(observed),live=live),indent=2)+'\n');assert not live,live
print(json.dumps(dict(passed=len(rows))))
