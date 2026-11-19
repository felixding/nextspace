#!/usr/bin/env python3
"""Exercise the existing review/update/launch chain with a strict Lima stand-in.

Only temporary Downloads/VM paths are substituted; HOME is never overridden.
The stand-in rejects edits of running instances exactly as the real CLI does.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--original-launcher',required=True,type=Path)
p.add_argument('--previous-launcher',type=Path)
p.add_argument('--output',required=True,type=Path)
a=p.parse_args()
repo=Path(__file__).resolve().parents[2]
update=repo/'.build/native-ui/browser-density-update'
legacy=a.original_launcher.read_text()
rows=[]
def check(case,passed):
    rows.append(dict(case=case,passed=bool(passed)))
    assert passed,case

def executable(path,source):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(source);path.chmod(0o755)

with tempfile.TemporaryDirectory(prefix='nextspace-review-regression-') as temporary:
    root=Path(temporary);package=root/'package/nextspace-browser-controls-update'
    package.mkdir(parents=True)
    for name in ['Update.command','repair-preview-launcher.sh']:
        shutil.copy2(update/name,package/name)
    (package/'project').mkdir()
    (package/'project/review-payload.txt').write_text('qualified fixture payload\n')
    capacity=package/'project/Tests/Lima/preview-capacity.sh';capacity.parent.mkdir(parents=True)
    shutil.copy2(repo/'Tests/Lima/preview-capacity.sh',capacity)
    records=[]
    for path in sorted(package.rglob('*')):
        if path.is_file():records.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+str(path.relative_to(package))+'\n')
    (package/'MANIFEST.sha256').write_text(''.join(records))
    remote=root/'remote';remote.mkdir();archive=remote/'nextspace-browser-controls-update.tar.gz'
    with tarfile.open(archive,'w:gz') as t:t.add(package,arcname=package.name)
    (remote/(archive.name+'.sha256')).write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
    fake=root/'bin';fake.mkdir()
    executable(fake/'uname','#!/bin/sh\nif [ "$1" = -m ]; then echo arm64; else exec /usr/bin/uname "$@"; fi\n')
    executable(fake/'stat','#!'+sys.executable+'''\nimport os,sys
from pathlib import Path
if sys.argv[1:3]==['-f','%z'] and Path(sys.argv[3]).name=='disk':
 print(Path(os.environ['NXS_REVIEW_ACTUAL_DISK']).read_text().strip())
else:os.execv('/usr/bin/stat',['stat',*sys.argv[1:]])
''')
    executable(fake/'df','#!/bin/sh\nprintf "Filesystem 1024-blocks Used Available Capacity Mounted\\n/dev/fixture 16777216 0 8388608 0%% /fixture\\n"\n')
    executable(fake/'scp','#!'+sys.executable+'''\nimport os,sys,shutil
from pathlib import Path
assert len(sys.argv)==4,sys.argv
for source in sys.argv[1:3]:
 assert source.startswith('home:/Users/felixding/projects/nextspace/.build/native-ui/'),source
 shutil.copy2(Path(os.environ['NXS_REVIEW_REMOTE'])/Path(source).name,sys.argv[3])
''')
    lima='#!'+sys.executable+'''\nimport json,os,sys
from pathlib import Path
args=sys.argv[1:]
if args[:1]==['--tty=false']:args=args[1:]
state=Path(os.environ['NXS_REVIEW_STATE']);current=state.read_text().strip()
with Path(os.environ['NXS_REVIEW_LOG']).open('a') as f:f.write(json.dumps(dict(arguments=args,state=current))+'\\n')
if args[0]=='list':
 assert args[1]=='--format' and args[3:]==['nextspace-gui'],args
 values={'{{.Status}}':current,'{{.VMType}}':'vz','{{.Dir}}':str(Path(os.environ['LIMA_HOME'])/'nextspace-gui'),
         '{{.Disk}}':Path(os.environ['NXS_REVIEW_CONFIGURED_DISK']).read_text().strip()}
 print(values[args[2]])
elif args[0]=='edit':
 if current=='Running':sys.exit('FATA[0000] cannot edit a running instance')
 assert current=='Stopped',args
 if args[1:]==['nextspace-gui','--disk','28']:
  Path(os.environ['NXS_REVIEW_CONFIGURED_DISK']).write_text(str(28*1024**3))
 else:
  assert args[1:3]==['nextspace-gui','--set'],args
  assert '"mountPoint": "/workspace"' in args[3] and '"/home/felixding.guest"' in args[3]
elif args[0]=='start':
 assert current=='Stopped' and args[1:]==['nextspace-gui'];state.write_text('Running')
 Path(os.environ['NXS_REVIEW_ACTUAL_DISK']).write_text(Path(os.environ['NXS_REVIEW_CONFIGURED_DISK']).read_text())
elif args[0]=='stop':
 assert current=='Running' and args[1:]==['nextspace-gui'];state.write_text('Stopped')
elif args[0]=='shell':
 assert current=='Running' and args[1:4]==['--workdir','/','nextspace-gui'],args
 if args[4:]==['python3','-']:
  script=sys.stdin.read();assert 'preview_identity' in script or 'End the preview' in script
 else:
  assert args[4:]==['sudo','-n','/usr/bin/setpriv','--reuid=501','--regid=44','--init-groups','--reset-env','--','python3','/workspace/.build/native-ui/macbook-preview.py'],args
else:raise AssertionError(args)
'''
    def fixture(name,state,source=legacy):
        folder=root/name;downloads=folder/'Downloads';support=downloads/'nextspace-preview-support'
        instance=downloads/'nextspace-lima/nextspace-gui';keys=downloads/'nextspace-lima/_config'
        instance.mkdir(parents=True);keys.mkdir();support.mkdir(parents=True)
        (support/'project').mkdir();(support/'project/unrelated.txt').write_text('preserve existing state\n')
        disk=b'preserve this existing VM disk\n';(instance/'disk').write_bytes(disk)
        expected=hashlib.sha256(disk).hexdigest()+'  disk\n';(support/'VM-DISK.sha256').write_text(expected)
        (instance/'.preview-disk-verified').write_text(expected)
        for part in ['lima.yaml','vz-efi','vz-identifier','cidata.iso','lima-version']:(instance/part).write_text('existing '+part+'\n')
        for part in ['user','user.pub']:
            destination=support/'vm-state/_config'/part;destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_text('fixture identity '+part+'\n');shutil.copy2(destination,keys/part)
        launcher=support/'Start.command'
        launcher.write_text(source.replace('vm_home="$HOME/Downloads/nextspace-lima"','vm_home='+json.dumps(str(downloads/'nextspace-lima')))+'\n# Preserve this local customization.\n')
        launcher.chmod(0o751)
        executable(support/'NEXTSPACE Preview.app/Contents/MacOS/limactl',lima)
        review=folder/'Review.command'
        review.write_text((repo/'Tests/Lima/Review.command').read_text().replace('downloads="$HOME/Downloads"','downloads='+json.dumps(str(downloads))))
        status=folder/'state';status.write_text(state);log=folder/'calls.jsonl'
        actual=folder/'actual-disk';actual.write_text(str(24*1024**3))
        configured=folder/'configured-disk';configured.write_text(str(24*1024**3))
        env=dict(os.environ,PATH=str(fake)+':'+os.environ['PATH'],NXS_REVIEW_STATE=str(status),
                 NXS_REVIEW_LOG=str(log),NXS_REVIEW_REMOTE=str(remote),
                 NXS_REVIEW_ACTUAL_DISK=str(actual),NXS_REVIEW_CONFIGURED_DISK=str(configured))
        saved={str(path.relative_to(downloads)):path.read_bytes() for path in [instance/'disk',keys/'user',keys/'user.pub',instance/'vz-identifier']}
        return downloads,support,launcher,review,status,log,env,saved
    d,s,l,r,status,log,env,saved=fixture('old-running','Running')
    failed=subprocess.run(['/bin/bash',str(l)],env=env,capture_output=True,text=True)
    check('original-launcher-reproduces-running-instance-error',failed.returncode!=0 and 'cannot edit a running instance' in failed.stderr)
    for initial in ['Running','Stopped']:
        d,s,l,r,status,log,env,saved=fixture(initial.lower(),initial)
        if initial=='Stopped':(d/'nextspace-lima/nextspace-gui/.preview-disk-verified').unlink()
        result=subprocess.run(['/bin/bash',str(r)],env=env,capture_output=True,text=True,timeout=30)
        (root/(initial+'.stdout')).write_text(result.stdout);(root/(initial+'.stderr')).write_text(result.stderr)
        check(initial+'-existing-review-command-completes',result.returncode==0)
        calls=[json.loads(line) for line in log.read_text().splitlines()]
        operations=[c['arguments'][0] for c in calls]
        check(initial+'-only-stopped-vm-is-edited',operations.count('edit')==2 and all(c['state']=='Stopped' for c in calls if c['arguments'][0]=='edit'))
        check(initial+'-capacity-growth-restarts-only-the-project-vm',operations.count('start')==1 and operations.count('stop')==int(initial=='Running'))
        check(initial+'-approved-capacity-is-applied-before-launch',Path(env['NXS_REVIEW_ACTUAL_DISK']).read_text()==str(28*1024**3))
        check(initial+'-existing-preview-entry-is-launched',calls[-1]['arguments'][-1]=='/workspace/.build/native-ui/macbook-preview.py')
        check(initial+'-disk-and-identity-are-preserved',all((d/rel).read_bytes()==value for rel,value in saved.items()))
        check(initial+'-unrelated-launcher-and-project-state-preserved','# Preserve this local customization.' in l.read_text() and (s/'project/unrelated.txt').read_text()=='preserve existing state\n' and stat.S_IMODE(l.stat().st_mode)==0o751)
        check(initial+'-verified-project-update-installed',(s/'project/review-payload.txt').read_text()=='qualified fixture payload\n')
        prior=l.read_bytes();repeat=subprocess.run(['/bin/bash',str(r)],env=env,capture_output=True,text=True,timeout=30)
        check(initial+'-repeat-review-is-idempotent',repeat.returncode==0 and l.read_bytes()==prior)
        repeated=[json.loads(line) for line in log.read_text().splitlines()][len(calls):]
        check(initial+'-repeat-review-does-not-resize-or-restart-again',all(c['arguments'][0] not in ('edit','stop','start') for c in repeated))
    if a.previous_launcher:
        d,s,l,r,status,log,env,saved=fixture('previous-launcher','Running',a.previous_launcher.read_text())
        result=subprocess.run(['/bin/bash',str(r)],env=env,capture_output=True,text=True,timeout=30)
        check('previously-patched-launcher-upgrades-through-the-same-command',result.returncode==0 and
              '# Apply the approved one-time NEXTSPACE disk expansion.' in l.read_text())
        check('previously-patched-launcher-retains-customization-and-vm-data',
              '# Preserve this local customization.' in l.read_text() and all((d/rel).read_bytes()==value for rel,value in saved.items()))
        prior=l.read_bytes();calls_before=len(log.read_text().splitlines())
        result=subprocess.run(['/bin/bash',str(r)],env=env,capture_output=True,text=True,timeout=30)
        repeated=[json.loads(line) for line in log.read_text().splitlines()[calls_before:]]
        check('previously-patched-launcher-remains-idempotent',result.returncode==0 and l.read_bytes()==prior and
              all(c['arguments'][0] not in ('edit','stop','start') for c in repeated))
    unknown=root/'unknown.command';unknown.write_text('#!/bin/sh\necho custom launcher\n');before=unknown.read_bytes()
    result=subprocess.run(['/bin/sh',str(repo/'Tests/Lima/repair-preview-launcher.sh'),str(unknown)],capture_output=True,text=True)
    check('unrecognized-launcher-is-preserved',result.returncode!=0 and unknown.read_bytes()==before)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(dict(complete=True,checks=rows),indent=2)+'\n')
print(json.dumps(dict(passed=len(rows))))
