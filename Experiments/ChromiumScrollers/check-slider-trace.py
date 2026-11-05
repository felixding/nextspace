#!/usr/bin/env python3
"""Verify native callbacks for one fresh check-sliders.py fixture run."""
import argparse
from collections import defaultdict
import json
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--log',type=Path,required=True)
p.add_argument('--references',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
rows=[json.loads(line) for line in a.log.read_text().splitlines()]
live=set();active=None;key_values=defaultdict(list);mouse_actions=0;presses=releases=0
for row in rows:
    event=row['event'];identity=(row.get('process'),row.get('control'))
    if event=='native-form-control':
        assert row['kind']==4 and identity not in live,row
        live.add(identity)
    elif event=='native-form-press':
        assert identity in live and active is None,row
        active=identity;presses+=1
    elif event=='native-form-release':
        assert identity==active,row
        active=None;releases+=1
    elif event=='native-form-action':
        assert identity in live and row['kind']==4 and row['action']==2,row
        if active==identity:mouse_actions+=1
        else:key_values[identity].append(row['value'])
expected=[tuple(item['value'] for item in control['keys']) for control in
          json.loads((a.references/'results.json').read_text()) if 'keys' in control]
assert sorted(tuple(values) for values in key_values.values())==sorted(expected),key_values
assert active is None and presses==releases==2,(active,presses,releases)
assert mouse_actions==4,mouse_actions
assert any(row['event']=='native-slider-step' and row['step']==20 for row in rows)
result=dict(passed=True,native_value_changed_actions=16+mouse_actions,
            native_keyboard_actions=16,native_mouse_actions=mouse_actions,
            native_presses=presses,native_releases=releases,
            native_key_values_match_direct_provider=True)
a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
