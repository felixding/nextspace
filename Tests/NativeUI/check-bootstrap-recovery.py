#!/usr/bin/env python3
"""Check a real Firefox parent's feature bindings after a lost startup reply."""
import argparse
import json
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('root',type=Path)
p.add_argument('--phase',required=True,choices=('before','after'))
p.add_argument('--fault',choices=('capability','scroller-layout'),default='capability')
a=p.parse_args()
launch=json.loads((a.root/'launch.json').read_text())
pid=launch['pids'][-1]
events=[json.loads(line) for line in (a.root/'helper.jsonl').read_text().splitlines() if line.startswith('{')]
fault_event='test-bootstrap-capability-reply-withheld' if a.fault=='capability' else 'test-bootstrap-scroller-layout-failed'
faults=[e for e in events if e.get('event')==fault_event]
assert len(faults)==1,('fault was not applied exactly once',faults)
if a.fault=='capability' or a.phase=='before':
    assert faults[0]['pid']==pid,('fault did not target the browser parent',faults,pid)
log='\n'.join(line for line in (a.root/'hook.log').read_text().splitlines() if line.startswith(str(pid)+' '))
features={name:message in log for name,message in {
    'color':'native Gecko color binding installed',
    'text':'native Gecko text bindings installed',
    'address':'native Gecko frontend text binding installed',
    'menu_keys':'native Gecko global menu key binding installed',
}.items()}
expected=all(features.values()) if a.phase=='after' else not any(features.values())
result=dict(phase=a.phase,pid=pid,fault=a.fault,fault_pid=faults[0]['pid'],features=features,
            negative_control_reproduced=a.phase=='before' and expected,
            recovery_verified=a.phase=='after' and expected,passed=expected)
(a.root/'bootstrap-recovery.json').write_text(json.dumps(result,indent=2)+'\n')
assert expected,result
print(json.dumps(result))
