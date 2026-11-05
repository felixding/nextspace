#!/usr/bin/env python3
"""Check native provider models/lifecycle for a fresh check-progress.py run."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--log', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--animated', action='store_true', help='Include the optional native indeterminate binding')
args = parser.parse_args()
rows = [json.loads(line) for line in args.log.read_text().splitlines()]
created = [r for r in rows if r['event']=='native-form-control']
models = [r for r in rows if r['event']=='native-progress-model']
destroyed = [r for r in rows if r['event']=='native-progress-destroy']
expected_created,expected_models,expected_destroyed=(20,25,11) if args.animated else (18,22,10)
assert len(created)==expected_created and all(r['kind']==5 for r in created), created
assert len(models)==expected_models and len(destroyed)==expected_destroyed
assert not any(r['event'] in ('native-form-action','native-form-press','native-form-key','native-form-focus') for r in rows)
identities = {(r['process'],r['control']) for r in created}
released = {(r['process'],r['control']) for r in destroyed}
assert len(identities)==expected_created and len(released)==expected_destroyed and released < identities
assert {r['value'] for r in models} == {0,.3,1,.5,.61,.8}
assert sum(r['width']==320 and r['height']==17 for r in models)==2
assert all((r['process'],r['control']) in identities for r in models)
result = dict(passed=True, created=len(created), destroyed=len(destroyed), current_document_controls=len(identities-released),
              model_updates=len(models), native_actions=0, native_input_requests=0)
args.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
