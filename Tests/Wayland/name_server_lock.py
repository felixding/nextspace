#!/usr/bin/env python3
"""Prove exclusion, crash recovery, exec isolation and real port registrations."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import tempfile
import time


def run(probe,artifacts):
    artifacts.mkdir(parents=True)
    libc=ctypes.CDLL(None);previous=ctypes.c_int()
    assert libc.prctl(37,ctypes.byref(previous),0,0,0)==0
    assert libc.prctl(36,1,0,0,0)==0 # Own the fixture's orphaned exec child.
    with tempfile.TemporaryDirectory(prefix='nextspace-name-lock-') as runtime:
        env=dict(os.environ,TMPDIR=runtime)
        with (artifacts/'holder.log').open('w') as log:
            holder=subprocess.Popen([probe,'--hold'],env=env,stdout=subprocess.PIPE,stderr=log,text=True)
        child=None;jobs=[]
        try:
            assert select.select([holder.stdout],[],[],10)[0]
            ready=json.loads(holder.stdout.readline());child=ready['child']
            libraries=sorted({line.split()[-1] for line in Path(f'/proc/{holder.pid}/maps').read_text().splitlines()
                if 'libgnustep-base.so' in line})
            runtime_libraries={name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in libraries}
            blocked=subprocess.run([probe,'--try'],env=env,capture_output=True,text=True,timeout=5)
            assert blocked.returncode==2,blocked.stdout+blocked.stderr
            os.kill(holder.pid,signal.SIGKILL);holder.wait(timeout=5)
            assert Path(f'/proc/{child}').exists(),'Exec child must remain alive during recovery'
            started=time.monotonic()
            recovered=subprocess.run([probe,'--try'],env=env,capture_output=True,text=True,timeout=5)
            elapsed=time.monotonic()-started
            (artifacts/'recovery.stderr').write_text(recovered.stderr)
            assert recovered.returncode==0 and json.loads(recovered.stdout)['locked'] and elapsed<1,(elapsed,recovered.stderr)
            jobs=[subprocess.Popen([probe,'--register'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                  for _ in range(8)]
            for process in jobs:
                output,error=process.communicate(timeout=20)
                assert process.returncode==0 and json.loads(output)==dict(registered=100),error
            (artifacts/'results.json').write_text(json.dumps(dict(exclusion=True,killed_holder_recovered=True,
                exec_child_retained_no_lock=True,recovery_seconds=elapsed,concurrent_registrations=800,
                runtime_libraries=runtime_libraries),indent=2)+'\n')
            print('Native name-server lock: exclusion, process-death/exec recovery and 800 concurrent registrations PASS')
        finally:
            for process in jobs:
                if process.poll() is None:process.kill();process.wait(timeout=5)
                process.stdout.close();process.stderr.close()
            if holder.poll() is None:holder.kill();holder.wait(timeout=5)
            holder.stdout.close()
            if child:
                try:os.kill(child,signal.SIGKILL);os.waitpid(child,0)
                except ProcessLookupError:pass
            assert libc.prctl(36,previous.value,0,0,0)==0


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--probe',required=True);p.add_argument('--artifacts',type=Path,required=True)
    run(**vars(p.parse_args()))
