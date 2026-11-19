#!/usr/bin/env python3
"""Drop actual native replies; recover ownership without replaying input/UI."""
import argparse,json,os,resource,subprocess,tempfile,time
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
for name in ('build','library','output'):p.add_argument('--'+name,required=True,type=Path)
p.add_argument('--previous-transport',type=Path)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
repo=Path(__file__).resolve().parents[2];headers=repo/'Libraries/NativeUI'
phases=[('after',a.build/'native-ui/native-input-receipt-probe')]
if a.previous_transport:
    old=a.output/'previous-input-receipt-probe'
    subprocess.run(['cc','-O2','-UNDEBUG','-Wno-unused-function','-I'+str(headers),
        str(Path(__file__).with_name('input-receipt-probe.c')),
        '-DNXS_TEST_TRANSPORT="'+str(a.previous_transport.resolve())+'"',
        '-DNXS_TEST_OLD_TRANSPORT','-o',str(old),'-pthread'],check=True)
    phases[:0]=[('before',old.resolve()),('before-press',old.resolve())]
results=[]
for phase,probe in phases:
    out=a.output/phase;out.mkdir();marker=out/'unused-bitmap-fault'
    with tempfile.TemporaryDirectory(prefix='nxs-input-receipts-') as temporary:
        endpoint=Path(temporary)/'controls.sock'
        env=dict(os.environ,NEXTSPACE_NATIVE_UI_TEST_FAULT=str(marker.resolve()))
        with (out/'helper.jsonl').open('w') as log,(out/'helper.stderr').open('w') as error:
            child=subprocess.Popen(['python3',str(Path(__file__).with_name('snapshot-fault-helper.py')),
                '--library',str(a.library),'--socket',str(endpoint),'-GSBackend','wayland'],env=env,stdout=log,stderr=error)
        try:
            deadline=time.monotonic()+30
            while not endpoint.exists():
                assert child.poll() is None and time.monotonic()<deadline,'Native helper startup'
                time.sleep(.02)
            r=subprocess.run([str(probe),str(endpoint),str(out.resolve())]+(['--press-only'] if phase=='before-press' else []),env=env,capture_output=True,text=True,timeout=90)
            (out/'probe.stdout').write_text(r.stdout);(out/'probe.stderr').write_text(r.stderr)
            rows=[json.loads(v) for v in r.stdout.splitlines() if v.startswith('{')]
            if phase.startswith('before'):
                case='lost-native-press-reply-recovers-tracking-owner' if phase=='before-press' else 'lost-native-open-reply-retains-original-picker'
                assert r.returncode!=0 and rows and rows[-1]==dict(case=case,passed=False),(r.returncode,r.stdout,r.stderr)
                results.append(dict(phase=phase,old_transport_fails_ownership_recovery=True,case=case))
            else:
                assert r.returncode==0,(r.returncode,r.stdout,r.stderr)
                assert rows and all(v.get('passed') for v in rows)
                events=[json.loads(v) for v in (out/'helper.jsonl').read_text().splitlines() if v.startswith('{')]
                dropped={v['operation'] for v in events if v.get('event')=='test-native-input-reply-withheld'}
                assert dropped=={2,14,59,66},dropped
                results.append(dict(phase=phase,passed=rows[-1]['passed'],faults_observed=sorted(dropped)))
        finally:
            forced=False;child.terminate()
            try:child.wait(timeout=8)
            except subprocess.TimeoutExpired:forced=True;child.kill();child.wait()
            (out/'cleanup.json').write_text(json.dumps(dict(pid=child.pid,exit_code=child.poll(),forced=forced,live=child.poll() is None),indent=2)+'\n')
            assert child.poll() is not None
(a.output/'results.json').write_text(json.dumps(dict(complete=True,runs=results),indent=2)+'\n')
print(json.dumps(dict(complete=True,runs=results)))
