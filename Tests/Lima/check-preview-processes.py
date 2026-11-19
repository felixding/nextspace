#!/usr/bin/env python3
"""Verify private-preview cleanup preserves another session's processes."""
import argparse,json,os,select,subprocess,sys,tempfile
from pathlib import Path
from preview_processes import reap_preview_processes

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
checks=[];children=[]
def check(name,passed):
    checks.append(dict(case=name,passed=bool(passed)))
    assert passed,name
try:
    with tempfile.TemporaryDirectory(prefix='preview-cleanup-check-') as scratch:
        root=Path(scratch)
        runtimes=[]
        for name in ('macbook-preview-owned','macbook-preview-other'):
            p=root/name/'runtime';p.mkdir(parents=True);runtimes.append(p)
        for runtime,ignore in [(runtimes[0],False),(runtimes[0],True),(runtimes[1],False)]:
            code=('import signal,time;'+('signal.signal(signal.SIGTERM,signal.SIG_IGN);' if ignore else '')+
                  'print("ready",flush=True);time.sleep(60)')
            child=subprocess.Popen([sys.executable,'-c',code],env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime)),stdout=subprocess.PIPE,text=True)
            children.append(child)
            assert select.select([child.stdout],[],[],5)[0] and child.stdout.readline().strip()=='ready'
        receipt=reap_preview_processes(runtimes[0],grace=.2)
        for child in children[:2]:child.wait(timeout=3)
        check('matching-preview-processes-exit',all(child.returncode is not None for child in children[:2]))
        check('stubborn-preview-process-is-reaped',children[1].pid in receipt['forced'])
        check('other-session-is-preserved',children[2].poll() is None)
        check('no-private-preview-survivors',not receipt['remaining'])
        check('repeated-cleanup-is-idempotent',not reap_preview_processes(runtimes[0],grace=.1)['terminated'])
        rejected=False
        try:reap_preview_processes(root)
        except ValueError:rejected=True
        check('unscoped-directory-is-rejected',rejected)
finally:
    for child in children:
        if child.poll() is None:child.kill();child.wait()
    (args.output/'results.json').write_text(json.dumps(checks,indent=2)+'\n')
print(json.dumps(dict(passed=len(checks))))
