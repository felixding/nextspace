#!/usr/bin/env python3
"""Check provider invalidations/lifecycle for a fresh check-animation.py run."""
import argparse
import json
from pathlib import Path

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--log',type=Path,required=True)
parser.add_argument('--hook-log',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
rows=[json.loads(line) for line in args.log.read_text().splitlines()]
live=set();created=destroyed=invalidations=0;generations={};animated=set();observed=set()
for row in rows:
    event=row['event']
    assert event not in ('native-form-action','native-form-press','native-form-key','native-form-focus'),row
    key=(row.get('process'),row.get('control'))
    if event=='native-form-control':
        assert row['kind']==5 and key not in live,row
        live.add(key);created+=1
    elif event=='native-progress-model':
        assert key in live,row
        if row['indeterminate']:animated.add(key)
    elif event=='native-progress-destroy':
        assert key in live,row
        live.remove(key);destroyed+=1
    elif event=='native-form-invalidation':
        assert key in live,row
        assert row['generation']==generations.get(row['process'],0)+1,row
        generations[row['process']]=row['generation'];observed.add(key);invalidations+=1
assert created==8 and destroyed==5 and len(live)==3,(created,destroyed,live)
assert animated<=observed and len(animated)==6 and invalidations>=48
hook=args.hook_log.read_text()
assert 'native invalidation applied on renderer thread' in hook
result=dict(passed=True,created=created,destroyed=destroyed,current_document_controls=len(live),
            invalidations=invalidations,animated_objects=len(animated),native_actions=0,
            renderer_thread_handoff=True)
args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
