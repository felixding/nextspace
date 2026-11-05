#!/usr/bin/env python3
"""Verify event delivery through nested and selective AppKit waits."""
import argparse
import json
from pathlib import Path
import select
import subprocess

from gnustep import headless_session, process_runtime


def run(compositor, probe, artifacts):
    with headless_session(compositor, artifacts) as (env, command):
        with (artifacts/'probe.stderr').open('w') as errors:
            client = subprocess.Popen([str(probe), '-GSBackend', 'libgnustep-wayland',
                '-GSTheme', 'NextSpace'], env=env, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=errors)
        try:
            assert select.select([client.stdout], [], [], 10)[0], 'No event probe handshake'
            first = client.stdout.readline()
            ready = json.loads(first)
            assert ready['ready'] and ready['pid'] == client.pid, ready
            (artifacts/'runtime.json').write_text(json.dumps(process_runtime(client.pid), indent=2)+'\n')
            output, _ = client.communicate(b'\n', timeout=10)
            (artifacts/'probe.log').write_bytes(first+output)
            assert client.returncode == 0, (artifacts/'probe.stderr').read_text()
            result = json.loads(output)
            assert result['passed'] and len(result['cases']) == 6, result
            (artifacts/'results.json').write_text(json.dumps(result, indent=2)+'\n')
            print('Nested/selective AppKit event delivery: six cases PASS', flush=True)
            return result
        finally:
            if client.poll() is None:
                client.kill()
                client.communicate()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('compositor','probe','artifacts'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    run(args.compositor.resolve(), args.probe.resolve(), args.artifacts.resolve())
