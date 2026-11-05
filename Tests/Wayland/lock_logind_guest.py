#!/usr/bin/env python3
"""Exercise real logind locking inside login_pam.py's owned greetd/PAM session."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid

from integration import until
from lock_pam import run_supervised
import login_pam


def write_json(path, value):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value)+'\n');temporary.replace(path)


def user_agent(home, release):
    """Run test commands as children of the authenticated user, in its scope."""
    request=home/'agent-request.json';response=home/'agent-response.json'
    process=None;token=None;deadline=time.monotonic()+300
    try:
        while not release.exists():
            assert time.monotonic()<deadline,'PAM user-agent deadline'
            if process and process.poll() is not None:
                write_json(response,dict(token=token,pid=process.pid,returncode=process.returncode));process=None
            if request.exists():
                assert process is None,'An owned user command is already running'
                command=json.loads(request.read_text());request.unlink();token=command['token']
                with open(command['log'],'a') as log:
                    process=subprocess.Popen(command['arguments'],env=command['environment'],stdin=subprocess.DEVNULL,
                        stdout=log,stderr=log,start_new_session=True)
                write_json(response,dict(token=token,pid=process.pid,returncode=None))
            time.sleep(.02)
    finally:
        if process and process.poll() is None:
            os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)


class UserSessionProcess:
    stdin=stdout=None
    def __init__(self, context, arguments, environment, log, check_inhibitor=False):
        self.home=context['user_home'];self.token=uuid.uuid4().hex;self.returncode=None
        self.response=self.home/'agent-response.json'
        log.touch();os.chown(log,context['user_account'].pw_uid,context['user_account'].pw_gid)
        write_json(self.home/'agent-request.json',dict(token=self.token,arguments=arguments,environment=environment,log=str(log)))
        row=until(lambda:self.status(),'PAM-owned supervisor child')
        self.pid=row['pid']
        self.path=self.call('/org/freedesktop/login1','org.freedesktop.login1.Manager','GetSessionByPID','u',str(self.pid))
        self.session=self.property('Id')
        assert self.session==context['session'],(self.session,context['session'])
        actual_uid=subprocess.check_output(['loginctl','show-session',self.session,'--property=User','--value'],text=True).strip()
        assert int(actual_uid)==context['user_account'].pw_uid,actual_uid
        self.evidence=dict(supervisor_pid=self.pid,session=self.session,path=self.path,uid=int(actual_uid),
            inherited_session_verified=True,locked_hints=[])
        if check_inhibitor:
            value=until(lambda:next((row for row in inhibitors() if row[0]=='sleep' and row[1]=='NEXTSPACE'
                and row[3]=='delay' and row[4]==int(actual_uid) and row[5]==self.pid),None),'real logind sleep delay inhibitor')
            self.evidence['sleep_delay_inhibitor']=dict(zip(('what','who','why','mode','uid','pid'),value))
    def status(self):
        if not self.response.exists():return None
        value=json.loads(self.response.read_text())
        return value if value['token']==self.token else None
    def poll(self):
        value=self.status()
        self.returncode=value['returncode'] if value else None
        return self.returncode
    def terminate(self):
        if self.poll() is None:os.kill(self.pid,signal.SIGTERM)
    def wait(self, timeout=5):
        deadline=time.monotonic()+timeout
        while self.poll() is None:
            if time.monotonic()>=deadline:raise subprocess.TimeoutExpired('PAM user supervisor',timeout)
            time.sleep(.02)
        return self.returncode
    def call(self,path,interface,method,*arguments):
        output=subprocess.check_output(['busctl','--system','call','org.freedesktop.login1',path,interface,method,*arguments],text=True,timeout=5).strip()
        return json.loads(output.split(' ',1)[1]) if output else None
    def property(self,name):
        output=subprocess.check_output(['busctl','--system','get-property','org.freedesktop.login1',self.path,
            'org.freedesktop.login1.Session',name],text=True,timeout=5).strip()
        return json.loads(output.split(' ',1)[1])
    def lock_via_logind(self):
        subprocess.run(['loginctl','lock-session',self.session],check=True,capture_output=True,timeout=5)
    def signal_unlock(self):
        subprocess.run(['loginctl','unlock-session',self.session],check=True,capture_output=True,timeout=5)
    def check_locked_hint(self, expected):
        until(lambda:self.property('LockedHint')==expected,'real logind LockedHint '+str(expected))
        self.evidence['locked_hints'].append(expected)


def inhibitors():
    output=subprocess.check_output(['busctl','--system','--json=short','call','org.freedesktop.login1',
        '/org/freedesktop/login1','org.freedesktop.login1.Manager','ListInhibitors'],text=True,timeout=5)
    return json.loads(output)['data'][0]


def validate(context,candidate,check_inhibitor=False):
    artifacts=context['artifacts']/'lock-session';artifacts.mkdir()
    account=context['user_account'];home=context['user_home'];runtime=Path(context['environment']['XDG_RUNTIME_DIR'])
    assert runtime.stat().st_uid==account.pw_uid
    env=dict(context['environment'],PATH='/usr/NextSpace/bin:/usr/local/bin:/usr/bin:/bin',
        LD_LIBRARY_PATH=str(candidate/'lib')+':/usr/NextSpace/lib:/usr/local/lib',
        WLR_BACKENDS='headless',WLR_HEADLESS_OUTPUTS='2',WLR_RENDERER='pixman')
    identity=dict(user=account.pw_uid,group=account.pw_gid,extra_groups=[],start_new_session=True)
    processes=[]
    try:
        run_supervised(str(candidate/'build/nextspace-session'),str(candidate/'build/nextspace-compositor'),
            '/usr/bin/swaylock',artifacts,home,runtime,env,identity,context['secret'],processes,
            session_factory=lambda args,environment,log:UserSessionProcess(context,args,environment,log,check_inhibitor))
        result=json.loads((artifacts/'results.json').read_text())
        assert result['real_logind']['locked_hints']==[True,False]*5
        assert result['real_logind']['session']==context['session']
        if check_inhibitor:
            until(lambda:all(row[5]!=result['real_logind']['supervisor_pid'] for row in inhibitors()),'sleep inhibitor removed with owned supervisor')
            result['real_logind']['sleep_delay_removed']=True
            (artifacts/'results.json').write_text(json.dumps(result,indent=2)+'\n')
        return result
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                process.wait(timeout=5)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('candidate','greetd','probe','wrapper','artifacts'):parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--disposable-guest',action='store_true')
    parser.add_argument('--check-sleep-inhibitor',action='store_true')
    args=parser.parse_args()
    login_pam.run(args.greetd.resolve(),args.probe.resolve(),args.wrapper.resolve(),args.artifacts.resolve(),
        args.disposable_guest,user_hook=lambda context:validate(context,args.candidate.resolve(),args.check_sleep_inhibitor))
