#!/usr/bin/env python3
"""Launch one isolated Chromium instance with the opt-in native scrollbar experiment."""
import argparse
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

EXPECTED = '7bcc9f719bc77d34358194026b4f148a468e97e4ddc45366e6ce02c119fb9bd1'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--chromium', type=Path, required=True)
parser.add_argument('--native-library', type=Path, required=True)
parser.add_argument('--hook', type=Path, required=True)
parser.add_argument('--backend', help='Optional GNUstep backend name, passed only to the helper')
parser.add_argument('--native-views', action='store_true',
                    help='Enable the experimental native address field and its required form/text bindings')
parser.add_argument('--log-directory', type=Path, required=True)
parser.add_argument('arguments', nargs=argparse.REMAINDER)
args = parser.parse_args()
for path in (args.chromium, args.native_library, args.hook):
    if not path.is_file():
        parser.error(f'Missing file: {path}')
with args.chromium.open('rb') as source:
    digest = hashlib.file_digest(source, 'sha256').hexdigest()
if digest != EXPECTED:
    parser.error('Unsupported Chromium executable; this experiment is pinned to one build')
args.log_directory.mkdir(parents=True, exist_ok=True)
arguments = args.arguments[1:] if args.arguments[:1] == ['--'] else args.arguments
if any(x.startswith(('--no-sandbox', '--user-data-dir', '--single-process')) for x in arguments):
    parser.error('Keep the sandbox and the isolated profile managed by this launcher')
helper = browser = None
exit_code = 1

def terminate(process):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()

def interrupted(signum, frame):
    raise KeyboardInterrupt

signal.signal(signal.SIGTERM, interrupted)
with tempfile.TemporaryDirectory(prefix='nxs-chromium-') as temporary:
    root = Path(temporary)
    endpoint = root / 'native.sock'
    environment = dict(os.environ)
    environment.pop('LD_PRELOAD', None)
    helper_command = [sys.executable, str(Path(__file__).with_name('helper.py')),
                      '--library', str(args.native_library.resolve()), '--socket', str(endpoint)]
    if args.backend:
        helper_command += ['-GSBackend', args.backend]
    with (args.log_directory / 'native.jsonl').open('w') as helper_log, \
         (args.log_directory / 'helper.stderr').open('w') as helper_errors, \
         (args.log_directory / 'chromium.stderr').open('w') as browser_errors:
        try:
            helper = subprocess.Popen(helper_command, env=environment, stdout=helper_log, stderr=helper_errors)
            deadline = time.monotonic() + 30
            while not endpoint.exists() and helper.poll() is None and time.monotonic() < deadline:
                time.sleep(.02)
            if not endpoint.exists() or helper.poll() is not None:
                raise RuntimeError('Native helper did not start; inspect helper.stderr')
            environment.update(LD_PRELOAD=str(args.hook.resolve()),
                               NEXTSPACE_CHROMIUM_SOCKET=str(endpoint),
                               NEXTSPACE_CHROMIUM_LOG=str((args.log_directory / 'hook.log').resolve()))
            if args.native_views:
                environment.update(NEXTSPACE_CHROMIUM_FORMS='1', NEXTSPACE_CHROMIUM_INPUT='1',
                                   NEXTSPACE_CHROMIUM_TEXT='1', NEXTSPACE_CHROMIUM_VIEWS='1')
            command = [str(args.chromium.resolve()), '--ozone-platform=wayland', '--gtk-version=4',
                       '--disable-gpu',
                       '--disable-features=OverlayScrollbar', '--no-first-run', '--no-default-browser-check',
                       '--user-data-dir=' + str(root / 'profile')] + arguments
            browser = subprocess.Popen(command, env=environment, stderr=browser_errors)
            exit_code = browser.wait()
        except KeyboardInterrupt:
            exit_code = 130
        finally:
            terminate(browser)
            terminate(helper)
sys.exit(exit_code)
