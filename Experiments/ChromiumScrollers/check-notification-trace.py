#!/usr/bin/env python3
"""Verify native-window actions and measured handoff to the real renderer."""
import argparse,json,re
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
for key in ('helper-log','hook-log','output'):p.add_argument('--'+key,type=Path,required=True)
p.add_argument('--process',type=int,required=True)
a=p.parse_args();rows=[json.loads(line) for line in a.helper_log.read_text().splitlines()]
rows=[row for row in rows if row.get('process')==a.process]
applied={}
for match in re.finditer(r'native popup action applied process=(\d+) control=(\d+) actions=(\d+) time_ns=(\d+)',a.hook_log.read_text()):
    process,control,count,timestamp=map(int,match.groups())
    if process==a.process:applied[(control,count)]=timestamp
actions=[]
for index,row in enumerate(rows):
    if row['event']!='native-form-action':continue
    assert row['kind']==6 and row['action']==2
    following=[]
    for later in rows[index+1:]:
        if later['event']=='native-notifier' and later['operation']==16:break
        following.append(later)
    # A browser-forwarded key or mouse tracking release has its own transport
    # record. These actions instead came through native window event dispatch.
    assert not any(item['event'] in ('native-form-key','native-form-press','native-form-release') for item in following)
    elapsed=(applied[(row['control'],row['count'])]-row['monotonic_ns'])/1e6
    assert 0<=elapsed<250,elapsed
    actions.append(dict(value=row['value'],milliseconds=elapsed))
assert [row['value'] for row in actions]==[1,2,0],actions
registrations=[row for row in rows if row['event']=='native-notifier']
assert all(row['accepted'] for row in registrations)
opened=sum(row['operation']==15 for row in registrations)
assert opened>=3
assert sum(row['operation']==16 for row in registrations)==opened and registrations[-1]['active']==0
result=dict(passed=True,native_window_actions=actions,maximum_milliseconds=max(row['milliseconds'] for row in actions),notifiers_released=True)
a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
