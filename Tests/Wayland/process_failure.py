#!/usr/bin/env python3
"""Require usable failure stacks in the disposable Linux test environment."""
import argparse
import json
from pathlib import Path
import subprocess

from gnustep import capture_process_failure


def run(artifacts):
    artifacts.mkdir(parents=True)
    process = subprocess.Popen(['sleep', '30'])
    try:
        capture_process_failure(process, artifacts, 'sleep')
        state = json.loads((artifacts / 'sleep.json').read_text())
        assert process.poll() is None, 'Debugger did not leave the owned fixture running'
        assert state['debugger']['available'], 'Install gdb in the test environment'
        assert state['debugger']['backtrace_collected'], (
            'No usable stack; disposable Docker runners require --cap-add=SYS_PTRACE.\n'
            + (artifacts / 'sleep-backtrace.log').read_text())
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)
    completed = subprocess.Popen(['true'])
    assert completed.wait(timeout=5) == 0
    capture_process_failure(completed, artifacts, 'completed')
    state = json.loads((artifacts / 'completed.json').read_text())
    assert state['returncode'] == 0 and 'debugger' not in state
    result = dict(passed=True, live_process_stack_collected=True,
                  debugger_detached=True, completed_process_not_attached=True)
    (artifacts / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Process failure diagnostics: live stack and detached fixture PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifacts', type=Path, required=True)
    run(parser.parse_args().artifacts)
