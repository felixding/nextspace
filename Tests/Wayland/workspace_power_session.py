#!/usr/bin/env python3
"""Exercise real supervisor teardown after native power UI on an owned fake bus."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shlex
import signal
import socket
import subprocess

from integration import until
from workspace_power import check,owned_bus


def descendants(pid):
    parents={}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdecimal():continue
        try:
            fields=dict(line.split(':',1) for line in (entry/'status').read_text().splitlines() if ':' in line)
            parents[int(entry.name)]=int(fields['PPid'])
        except (OSError,KeyError,ValueError):pass
    owned={pid}
    while True:
        found={child for child,parent in parents.items() if parent in owned}
        if found<=owned:return owned
        owned|=found


class WorkspaceProcess:
    def __init__(self,parent,pid,record,runtime):
        self.parent=parent;self.pid=pid;self.record=record;self.runtime=runtime
    @property
    def returncode(self):return self.parent.returncode
    def poll(self):return self.parent.poll()
    def wait(self,timeout=10):
        owned=descendants(self.parent.pid)
        code=self.parent.wait(timeout=timeout)
        until(lambda:all(not Path('/proc/'+str(pid)).exists() for pid in owned),'supervisor reaps its complete process tree')
        assert not list(self.runtime.glob('nextspace-bus-*')),'Supervisor private bus directory survived power exit'
        self.record.update(returncode=code,owned_processes=sorted(owned),all_reaped=True,private_bus_removed=True)
        return code


def run(candidate,artifacts,expected_session):
    assert os.geteuid()!=0,'Run in the authenticated disposable PAM user scope'
    own_scope=Path('/proc/self/cgroup').read_text()
    assert '/session-'+expected_session+'.scope' in own_scope,own_scope
    artifacts.mkdir(parents=True)
    home=Path.home();runtime=Path(os.environ['XDG_RUNTIME_DIR'])
    assert runtime.stat().st_uid==os.getuid()
    legacy=home/'Library/Preferences/.NextSpace';legacy.mkdir(parents=True,exist_ok=True)
    state=plistlib.loads((candidate/'candidate/Workspace.app/Resources/WMState.plist').read_bytes())
    for entry in state['Dock']['Applications']:entry['AutoLaunch']='No'
    (legacy/'WMState.plist').write_bytes(plistlib.dumps(state))
    relay=home/'power-relay.sh'
    relay.write_text('#!/bin/sh\nexec /usr/bin/python3 '+shlex.quote(str(candidate/'source/Tests/Wayland/login_native_pam.py'))+
        ' --relay '+shlex.quote(str(candidate))+' "$@"\n');relay.chmod(0o755)
    environment=dict(os.environ,WLR_BACKENDS='headless',WLR_HEADLESS_OUTPUTS='2',WLR_RENDERER='pixman',
        NEXTSPACE_GS_BACKEND='wayland-title-state')
    parent=None;control=None;current=None;records=[]
    def command(value):
        assert parent.poll() is None,'Supervisor exited before UI completion'
        control.sendall(value.encode());return json.loads(control.recv(65536))
    def start():
        nonlocal parent,control,current
        if parent:assert parent.poll() is not None
        if control:control.close()
        metadata=home/'relay.json';metadata.unlink(missing_ok=True)
        log_path=artifacts/f'session-{len(records)}.log'
        with log_path.open('w') as log:
            parent=subprocess.Popen([str(candidate/'candidate/bin/nextspace-session'),'--private-bus',
                '--compositor',str(relay),'--locker','/usr/bin/swaylock','--',str(candidate/'workspace.py'),
                '-GSBackend','libgnustep-wayland-title-state','-GSTheme','NextSpace','-NSUseRunningCopy','NO'],
                env=environment,stdout=log,stderr=log,start_new_session=True)
        def ready():
            assert parent.poll() is None
            if not metadata.exists():return None
            row=json.loads(metadata.read_text())
            return row if row['supervisor_pid']==parent.pid else None
        row=until(ready,'actual supervisor compositor relay',timeout=30)
        def workspace_ready():
            assert parent.poll() is None,log_path.read_text()[-4000:]
            return 'Workspace is ready' in log_path.read_text()
        until(workspace_ready,'supervised Workspace initialization',timeout=30)
        control=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET);control.settimeout(5);control.connect(row['control'])
        binary=(candidate/'candidate/Workspace.app/Workspace').resolve()
        def actor():
            for window in command('windows'):
                try:executable=Path(f"/proc/{window['pid']}/exe").resolve(strict=True)
                except FileNotFoundError:continue
                if executable==binary and window['visible']:return window['pid']
        pid=until(actor,'actual supervised Workspace',timeout=30)
        actual=dict(value.split('=',1) for value in Path(f'/proc/{pid}/environ').read_bytes().decode().split('\0') if '=' in value)
        for name in ('NEXTSPACE_SESSION_ID','DBUS_SESSION_BUS_ADDRESS','WAYLAND_DISPLAY','XDG_SESSION_TYPE'):
            environment[name]=actual[name]
        (artifacts/f'initial-windows-{len(records)}.json').write_text(json.dumps(command('windows'),indent=2)+'\n')
        application=subprocess.run([str(candidate/'candidate/bin/WorkspaceProbe'),'--application-state','Workspace'],
            env=environment,capture_output=True,text=True,timeout=10)
        (artifacts/f'application-state-{len(records)}.json').write_text(json.dumps(dict(returncode=application.returncode,
            stdout=application.stdout,stderr=application.stderr),indent=2)+'\n')
        opened=subprocess.run([str(candidate/'candidate/bin/WorkspaceProbe'),'--open','/tmp','-GSWorkspaceApplication','Workspace'],
            env=environment,capture_output=True,text=True,timeout=10)
        (artifacts/f'open-viewer-{len(records)}.json').write_text(json.dumps(dict(returncode=opened.returncode,
            stdout=opened.stdout,stderr=opened.stderr),indent=2)+'\n')
        assert opened.returncode==0 and json.loads(opened.stdout)['opened'],opened.stderr
        assert Path(f'/proc/{pid}/cgroup').read_text()==own_scope
        assert Path(f'/proc/{parent.pid}/cgroup').read_text()==own_scope
        libraries=sorted({line.split()[-1] for line in Path(f'/proc/{pid}/maps').read_text().splitlines()
            if any(name in line for name in ('libgnustep-','libobjc.so.','libSystemKit.so.','libDesktopKit.so.'))})
        assert any('libgnustep-wayland' in path for path in libraries)
        record=dict(supervisor_pid=parent.pid,workspace_pid=pid,uid=os.getuid(),cgroup=own_scope,
            session=actual['NEXTSPACE_SESSION_ID'],private_bus=actual['DBUS_SESSION_BUS_ADDRESS'],
            libraries={path:hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in libraries})
        records.append(record);current=WorkspaceProcess(parent,pid,record,runtime)
    try:
        with owned_bus(artifacts) as (service,address):
            environment.update(DBUS_SYSTEM_BUS_ADDRESS=address,NEXTSPACE_POWER_TEST_BUS=address)
            start()
            check(service,environment,command,lambda:current,start,str(candidate/'candidate/bin/WorkspaceProbe'),artifacts/'ui')
        assert len(records)==3 and all(row.get('returncode')==129 and row['all_reaped'] and row['private_bus_removed'] for row in records)
        (artifacts/'sessions.json').write_text(json.dumps(dict(sessions=records,expected_pam_session=expected_session,
            actual_power_calls=False),indent=2)+'\n')
        print('PAM-owned native power UI, supervisor exit129 and complete child/private-bus cleanup: PASS')
    finally:
        if control:control.close()
        if parent and parent.poll() is None:
            parent.terminate()
            try:parent.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(parent.pid,signal.SIGKILL);parent.wait(timeout=5)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,required=True);parser.add_argument('--artifacts',type=Path,required=True)
    parser.add_argument('--expected-session',required=True)
    args=parser.parse_args();run(args.candidate,args.artifacts,args.expected_session)
