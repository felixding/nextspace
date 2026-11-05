#!/usr/bin/env python3
"""Verify native popup callbacks from one check-control-popup.py run."""
import argparse
import json
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--log',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
rows=[json.loads(line) for line in a.log.read_text().splitlines()]
rows=[r for r in rows if r.get('process')==0x504f5055]
created=[r for r in rows if r['event']=='native-form-control']
destroyed=[r for r in rows if r['event']=='native-popup-destroy']
assert len(created)==len(destroyed)==1 and created[0]['kind']==6
actions=[r for r in rows if r['event']=='native-form-action']
assert [(r['kind'],r['action'],r['count'],r['value']) for r in actions]==[(6,2,1,3),(6,2,2,4)],actions
presses=[r for r in rows if r['event']=='native-form-press']
releases=[r for r in rows if r['event']=='native-form-release']
assert len(presses)==len(releases)==1 and releases[0]['actions']==2
models=[r for r in rows if r['event']=='native-popup-model']
assert [(r['count'],r['selected']) for r in models]==[(5,0),(5,0),(5,4),(5,0)],models
result=dict(passed=True,native_controls=1,native_destructions=1,native_value_changed_actions=2,
    keyboard_selection=3,mouse_selection=4,native_presses=1,native_releases=1,model_updates=4)
a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
