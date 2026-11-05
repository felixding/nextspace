#!/usr/bin/env python3
"""Check native action evidence for one fresh check-forms.py run."""
import argparse
from collections import Counter
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--log', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
rows = [json.loads(line) for line in args.log.read_text().splitlines()]
# The independent RPC probes have their own explicit process identities.
rows = [row for row in rows if row.get('process') not in (0x54455354, 0x494e5054)]
actions = [row for row in rows if row['event'] == 'native-form-action']
presses = [row for row in rows if row['event'] == 'native-form-press']
releases = [row for row in rows if row['event'] == 'native-form-release']
counts = Counter(row['kind'] for row in actions)
assert counts == {1: 6, 2: 6, 3: 4}, counts
assert len(presses) == len(releases) == 19, (len(presses), len(releases))
# Pointer-capture cancellation, removal, and reload must not forward actions.
assert sum(row['actions'] == 0 for row in releases) == 3
assert all(row['count'] >= 1 for row in actions)
result = dict(native_actions=dict(counts), presses=len(presses), releases=len(releases),
              cancelled_gestures=3, passed=True)
args.output.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
