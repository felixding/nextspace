#!/usr/bin/env python3
"""Verify native actions for one fresh check-form-input.py browser run."""
import argparse
from collections import Counter
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--log', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
rows = [json.loads(line) for line in args.log.read_text().splitlines()]
actions = [row for row in rows if row['event'] == 'native-form-action']
keys = [row for row in rows if row['event'] == 'native-form-key']
presses = [row for row in rows if row['event'] == 'native-form-press']
releases = [row for row in rows if row['event'] == 'native-form-release']
counts = Counter(row['kind'] for row in actions)
assert counts == {1: 5, 2: 5, 3: 5}, counts
assert len(presses) == len(releases) == 3
assert all(row['actions'] == 1 for row in releases)
assert Counter(row['kind'] for row in presses) == {1: 1, 2: 1, 3: 1}
assert Counter(row['result'] for row in keys if row['type'] == 0) == {0: 2, 1: 12, 2: 1, 3: 1}
assert all(row['result'] == 0 for row in keys if row['type'] == 1)

# Every action must be witnessed by a native mouse release or handled keydown
# on the same provider object, with the same action counter. DOM clicks alone
# cannot satisfy this check.
observed = set()
for row in keys + releases:
    if row['event'] == 'native-form-key' and (row['type'] != 0 or row['result'] != 1):
        continue
    observed.add((row['process'], row['control'], row['kind'], row['actions']))
assert all((row['process'], row['control'], row['kind'], row['count']) in observed for row in actions)
result = dict(passed=True, native_actions=dict(counts), keyboard_actions=12,
              mouse_actions=3, next_focus_requests=1, previous_focus_requests=1,
              key_events=len(keys), presses=len(presses), releases=len(releases))
args.output.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
