#!/usr/bin/env python3
"""Exercise the actual host capacity script using a local Lima stand-in."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', required=True, type=Path)
args = parser.parse_args()
script = Path(__file__).with_name('preview-capacity.sh')
GIB = 1024**3
checks = []


def check(name, passed):
    assert passed, name
    checks.append(dict(case=name, passed=True))


with tempfile.TemporaryDirectory(prefix='nextspace-capacity-regression-') as temporary:
    base = Path(temporary).resolve()
    tools = base / 'bin'; tools.mkdir()
    lima = tools / 'limactl'
    lima.write_text('#!' + sys.executable + '''
import json,os,sys
from pathlib import Path
p=Path(os.environ['NXS_CAPACITY_FIXTURE']);v=json.loads(p.read_text())
a=sys.argv[1:]
if a[:1]==['--tty=false']:a=a[1:]
assert os.environ['LIMA_HOME']==str(Path(v['instance']).parent)
v['calls'].append(a)
if a[:2]==['list','--format'] and a[3:]==['nextspace-gui']:
 values={'{{.Status}}':v['state'],'{{.VMType}}':v.get('type','vz'),
         '{{.Dir}}':v.get('dir',v['instance']),'{{.Disk}}':str(v['configured'])}
 print(values[a[2]])
elif a==['stop','nextspace-gui']:
 if not v.get('stop_failed'):v['state']='Stopped'
elif a==['edit','nextspace-gui','--disk','28']:
 assert v['state']=='Stopped'
 v['configured']=(27 if v.get('wrong_capacity') else 28)*1024**3
 Path(v['instance'],'lima.yaml').write_text('disk: '+str(v['configured']//1024**3)+'GiB\\n')
else:raise AssertionError(a)
p.write_text(json.dumps(v))
''')
    lima.chmod(0o755)
    df = tools / 'df'
    df.write_text('#!' + sys.executable + '''
import json,os
from pathlib import Path
v=json.loads(Path(os.environ['NXS_CAPACITY_FIXTURE']).read_text())
print('Filesystem 1024-blocks Used Available Capacity Mounted')
print('/dev/fixture 16777216 0 '+str(v['free']//1024)+' 0% /fixture')
''')
    df.chmod(0o755)

    def fixture(name, *, actual=24, configured=24, free=8*GIB, state='Running', **extra):
        parent = base / name; parent.mkdir()
        instance = parent / 'nextspace-gui'; instance.mkdir()
        with (instance / 'disk').open('wb') as f:
            f.write(b'preserve original VM data'); f.truncate(actual * GIB)
        (instance / 'lima.yaml').write_text('disk: '+str(configured)+'GiB\n')
        (instance / 'vz-identifier').write_bytes(b'preserve VM identity')
        receipt = parent / 'state.json'
        receipt.write_text(json.dumps(dict(instance=str(instance), configured=configured*GIB,
            free=free, state=state, calls=[], **extra)))
        env = dict(os.environ, PATH=str(tools)+':'+os.environ['PATH'], NXS_CAPACITY_FIXTURE=str(receipt))
        return instance, receipt, env

    def run(data):
        instance, receipt, env = data
        result = subprocess.run(['/bin/sh', str(script), str(lima), str(instance)],
                                env=env, text=True, capture_output=True, timeout=20)
        return result, json.loads(receipt.read_text())

    data = fixture('running'); result, value = run(data); instance = data[0]
    check('running-preview-stops-before-capacity-edit', result.returncode==0 and
          value['calls'].index(['stop','nextspace-gui']) < value['calls'].index(['edit','nextspace-gui','--disk','28']))
    check('approved-target-is-retained', value['configured']==28*GIB and value['state']=='Stopped')
    with (instance / 'disk').open('rb') as f:
        prefix = f.read(25)
    check('original-disk-and-identity-are-preserved', prefix==b'preserve original VM data' and
          (instance/'disk').stat().st_size==24*GIB and (instance/'vz-identifier').read_bytes()==b'preserve VM identity')
    check('original-configuration-is-backed-up',
          (instance/'lima.yaml.before-preview-disk-growth').read_text()=='disk: 24GiB\n')
    result, repeated = run(data)
    check('interrupted-restart-is-idempotent', result.returncode==0 and
          repeated['calls'].count(['edit','nextspace-gui','--disk','28'])==1)

    for name, values in [('already-expanded',dict(actual=28,configured=28,free=0)),
                         ('larger',dict(actual=32,configured=32,free=0))]:
        data = fixture(name, **values); result, value = run(data)
        check(name+'-is-not-resized-or-interrupted', result.returncode==0 and not value['calls'])

    data = fixture('low-host', free=6*GIB-1024); result, value = run(data)
    check('host-space-guard-precedes-all-mutations', result.returncode!=0 and
          all(c[0]=='list' for c in value['calls']) and '6144 MiB' in result.stderr)
    data = fixture('exact-budget', free=6*GIB, state='Stopped'); result, value = run(data)
    check('exact-host-budget-is-accepted', result.returncode==0 and ['stop','nextspace-gui'] not in value['calls'])

    for name, values in [('wrong-type',dict(type='qemu')), ('wrong-path',dict(dir=str(base))),
                         ('broken',dict(state='Broken')), ('failed-stop',dict(stop_failed=True))]:
        data = fixture(name, **values); result, value = run(data)
        check(name+'-prevents-disk-edit', result.returncode!=0 and
              ['edit','nextspace-gui','--disk','28'] not in value['calls'])

    data = fixture('different-backup', state='Stopped')
    (data[0]/'lima.yaml.before-preview-disk-growth').write_text('preserve another backup\n')
    result, value = run(data)
    check('different-configuration-backup-is-preserved', result.returncode!=0 and
          (data[0]/'lima.yaml.before-preview-disk-growth').read_text()=='preserve another backup\n' and
          ['edit','nextspace-gui','--disk','28'] not in value['calls'])

    data = fixture('larger-pending', configured=32, free=10*GIB, state='Stopped'); result, value = run(data)
    check('larger-existing-pending-target-is-not-lowered', result.returncode==0 and value['configured']==32*GIB and
          ['edit','nextspace-gui','--disk','28'] not in value['calls'])

    data = fixture('qcow'); (data[0]/'disk').write_bytes(b'QFI\xfb'); result, value = run(data)
    check('non-raw-disk-is-preserved', result.returncode!=0 and not value['calls'])
    data = fixture('symlink'); target=data[0].parent/'other.disk';target.write_bytes(b'preserve')
    (data[0]/'disk').unlink();(data[0]/'disk').symlink_to(target);result, value=run(data)
    check('symlink-disk-target-is-preserved', result.returncode!=0 and target.read_bytes()==b'preserve')
    check('no-ssh-shell-start-or-delete-is-used-by-repair', all(c[0] in ('list','stop','edit') for c in repeated['calls']))

args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(dict(complete=True, checks=checks, real_vm_changed=False), indent=2)+'\n')
print(json.dumps(dict(passed=len(checks), real_vm_changed=False)))
