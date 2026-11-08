#!/usr/bin/env python3
"""Compare owned original/native Chromium fixtures using real seat input.

Launch both fixtures with identical options except NEXTSPACE_CHROMIUM_NUMBERS:
0 for --baseline, 1 for --native. Neither browser executable is rebuilt.
"""
import argparse
import json
from pathlib import Path

from native_number_fields import ChromiumNumbers

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline', required=True, type=Path)
parser.add_argument('--native', required=True, type=Path)
parser.add_argument('--output', required=True, type=Path)
args = parser.parse_args()
reference = ChromiumNumbers(args.baseline).semantic_trials()
trial = ChromiumNumbers(args.native)
try:
    for name, model in trial.semantic_trials().items():
        trial.check('original-number-semantics-'+name, model == reference[name])
    trial.native_editor_trials()
    trial.repeat_trial()
    trial.lifecycle_trials()
    trial.arrow_trial()
finally:
    args.output.write_text(json.dumps(dict(reference=reference, results=trial.results), indent=2)+'\n')
