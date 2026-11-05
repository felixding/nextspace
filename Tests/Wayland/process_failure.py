#!/usr/bin/env python3
"""Require usable failure stacks in the disposable Linux test environment."""
import argparse
import json
from pathlib import Path
import select
import subprocess
import sys

from gnustep import capture_process_failure, process_runtime


def mapped_resources(artifacts):
    """A library-like filename must not make mapped data a shared library."""
    artifacts.mkdir(parents=True)
    resource = artifacts / 'mapped-data.so'
    resource.write_bytes(b'Not an ELF library\n' * 256)
    paths = [str(resource.resolve()), '/etc/ld.so.cache']
    code = ('import mmap,sys,time; files=[open(p,"rb") for p in sys.argv[1:]]; '
            'maps=[mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) for f in files]; '
            'print("ready",flush=True); time.sleep(30)')
    process = subprocess.Popen([sys.executable, '-c', code, *paths], stdout=subprocess.PIPE, text=True)
    try:
        assert select.select([process.stdout], [], [], 5)[0], 'Mapped-resource fixture did not become ready'
        assert process.stdout.readline().strip() == 'ready'
        runtime = process_runtime(process.pid)
        (artifacts / 'runtime.json').write_text(json.dumps(runtime, indent=2) + '\n')
        assert not set(paths).intersection(runtime['libraries']), runtime['libraries']
        assert any(Path(path).name.startswith('libc.so') for path in runtime['libraries'])
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)
        process.stdout.close()
    return dict(non_elf_mappings_excluded=True, real_shared_libraries_retained=True)


def run(artifacts):
    artifacts.mkdir(parents=True)
    mappings = mapped_resources(artifacts / 'mapped-resources')
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
                  debugger_detached=True, completed_process_not_attached=True, **mappings)
    (artifacts / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Process failure diagnostics: live stack and detached fixture PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifacts', type=Path, required=True)
    run(parser.parse_args().artifacts)
