#!/usr/bin/env python3
"""Compare owned original/native browser fixtures using real seat input.

Launch both fixtures with identical options except NEXTSPACE_CHROMIUM_NUMBERS or NEXTSPACE_FIREFOX_NUMBERS:
0 for --baseline, 1 for --native. Neither browser executable is rebuilt.
"""
import argparse
import json
from pathlib import Path

from native_number_fields import ChromiumNumbers, FirefoxNumbers

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline', required=True, type=Path)
parser.add_argument('--native', required=True, type=Path)
parser.add_argument('--output', required=True, type=Path)
parser.add_argument('--native-pixels', action='store_true', help='Compare Firefox components with independent GNUstep controls')
parser.add_argument('--engine', choices=['chromium', 'firefox'], default='chromium')
parser.add_argument('--baseline-port', type=int, default=2844)
parser.add_argument('--native-port', type=int, default=2843)
args = parser.parse_args()
if args.native_pixels and args.engine != 'firefox':
    parser.error('--native-pixels currently requires --engine firefox')
if args.engine == 'firefox':
    trial = FirefoxNumbers(args.native, args.native_port)
    original = FirefoxNumbers(args.baseline, args.baseline_port, geometry_from=args.native)
    try:
        reference = original.semantic_trials()
    finally:
        original.close()
else:
    reference = ChromiumNumbers(args.baseline).semantic_trials()
    trial = ChromiumNumbers(args.native)
try:
    for name, model in trial.semantic_trials().items():
        trial.check('original-number-semantics-'+name, model == reference[name])
    if args.native_pixels:
        trial.native_pixel_trials()
    trial.native_editor_trials()
    trial.repeat_trial()
    trial.lifecycle_trials()
    trial.arrow_trial()
finally:
    args.output.write_text(json.dumps(dict(reference=reference, results=trial.results), indent=2)+'\n')
    if args.engine == 'firefox':
        trial.close()
