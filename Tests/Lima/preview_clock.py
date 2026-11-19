#!/usr/bin/env python3
"""Keep the preview VM's existing network time service as its clock owner."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

UNIT='lima-guestagent.service'
TIMEKEEPER='systemd-timesyncd.service'
POLICY=Path('/etc/systemd/system')/(UNIT+'.d')/'20-nextspace-preview-clock.conf'
CONTENTS='[Service]\nCapabilityBoundingSet=~CAP_SYS_TIME\n'
SYS_TIME=1<<25

def output(*args):
    return subprocess.check_output(args,text=True).strip()

def agent():
    pid=int(output('systemctl','show','-p','MainPID','--value',UNIT))
    if not pid:return None
    try:
        root=Path('/proc')/str(pid)
        if b'lima-guestagent' not in (root/'cmdline').read_bytes():
            raise RuntimeError('The preview agent service has an unexpected owner')
        fields=dict(line.split(':',1) for line in (root/'status').read_text().splitlines() if ':' in line)
        return dict(pid=pid,can_set_clock=bool((int(fields['CapEff'],16)|int(fields['CapBnd'],16))&SYS_TIME))
    except FileNotFoundError:return None

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepare',action='store_true')
    args=p.parse_args()
    assert sys.platform.startswith('linux') and Path('/var/tmp/nextspace-native-ui').is_dir(), 'Run only inside the NEXTSPACE preview VM'
    assert output('systemctl','is-active',TIMEKEEPER)=='active', 'The preview network time service must be active'
    before=agent();assert before,'The preview guest agent is not running'
    changed=restarted=False
    if args.prepare:
        assert os.geteuid()==0,'Preparing the preview clock requires the existing VM sudo access'
        assert not POLICY.is_symlink() and not POLICY.parent.is_symlink(),'Unexpected preview clock policy link'
        if POLICY.exists():
            assert POLICY.read_text()==CONTENTS,'Preserving an unexpected existing preview clock policy'
        else:
            POLICY.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
            POLICY.write_text(CONTENTS);POLICY.chmod(0o644);changed=True
            subprocess.run(['systemctl','daemon-reload'],check=True)
        if before['can_set_clock']:
            # Lima2.2.1 sends a timestamp captured before its RPC. Delayed
            # delivery repeatedly steps the clock backward despite NTP.
            # Keep the agent's other roles and the existing NTP service.
            subprocess.run(['systemctl','restart',UNIT],check=True)
            restarted=True
    assert POLICY.is_file() and POLICY.read_text()==CONTENTS,'The preview clock policy is not installed'
    end=time.monotonic()+15
    while True:
        current=agent()
        if current and not current['can_set_clock']:break
        assert time.monotonic()<end,'The preview agent can still reset the clock'
        time.sleep(.05)
    print(json.dumps(dict(complete=True,timekeeper=TIMEKEEPER,policy=str(POLICY),
                          agent_pid=current['pid'],agent_can_set_clock=False,
                          policy_installed=changed,agent_restarted=restarted)))

if __name__=='__main__':main()
