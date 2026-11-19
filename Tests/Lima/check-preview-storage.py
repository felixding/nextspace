#!/usr/bin/env python3
"""Exercise low-space cleanup, active-data protection and failed resource writes."""
import argparse
from contextlib import ExitStack
import errno
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

import preview_storage as storage
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Libraries/NativeUI/Bridge'))
import private_webui

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', required=True, type=Path)
args = parser.parse_args()
checks = []


def check(name, passed):
    checks.append(dict(case=name, passed=bool(passed)))
    assert passed, name


def closed(base, name, *, clean=True, live=False):
    root = base / ('macbook-preview-' + name)
    runtime = root / 'runtime'
    for child in ('firefox-profile', 'chromium-profile', 'cache'):
        folder = runtime / child
        folder.mkdir(parents=True)
        (folder / 'disposable').write_bytes(b'x' * 4096)
    (root / 'owner.json').write_text(json.dumps(dict(uid=os.getuid(), pid=12345678)))
    (root / 'cleanup.json').write_text(json.dumps(dict(session_exit=0, browser_exits=[0, -15], live=[42] if live else [],
        errors=[] if clean else ['uncertain'], detached_processes=dict(remaining=[]))))
    (root / 'evidence.png').write_bytes(b'preserve evidence')
    return root


def runtime(base, data):
    manifest = json.dumps([dict(path='library', sha256=hashlib.sha256(data).hexdigest())]).encode()
    root = base / ('browser-density-update-' + hashlib.sha256(manifest).hexdigest()[:16])
    root.mkdir()
    (root / 'manifest.json').write_bytes(manifest)
    (root / 'library').write_bytes(data)
    return root


test_parent = storage.STORAGE if storage.STORAGE.is_dir() else None
with tempfile.TemporaryDirectory(prefix='preview-storage-check-', dir=test_parent) as directory:
    base = Path(directory)
    clean = closed(base, 'clean')
    active = closed(base, 'active')
    failed = closed(base, 'uncertain', clean=False)
    live = closed(base, 'live', live=True)
    unknown = base / 'other-project'; unknown.mkdir()
    (unknown / 'keep').write_text('untouched')
    (base / 'macbook-preview-link').symlink_to(unknown, target_is_directory=True)
    old = runtime(base, b'old runtime')
    current = runtime(base, b'current runtime')
    mapped = runtime(base, b'mapped runtime')
    altered = runtime(base, b'altered runtime')
    (altered / 'extra-user-file').write_text('preserve')
    corrupt = runtime(base, b'corrupt runtime')
    (corrupt / 'library').write_bytes(b'changed')
    protected = {str(active), str(mapped)}
    with patch.object(storage, 'process_references', return_value=(set(), lambda p: str(p) in protected, False)):
        receipt = storage.cleanup_closed_previews(base, current)
    check('closed-profiles-and-cache-removed', not (clean / 'runtime/firefox-profile').exists() and len(receipt['deleted']) == 4)
    check('verification-evidence-preserved', (clean / 'evidence.png').read_bytes() == b'preserve evidence')
    check('live-referenced-session-preserved', (active / 'runtime/firefox-profile').exists())
    check('uncertain-or-incomplete-cleanup-preserved', (failed / 'runtime/cache').exists() and (live / 'runtime/cache').exists())
    check('unrelated-and-symlink-target-preserved', (unknown / 'keep').read_text() == 'untouched')
    check('obsolete-verified-runtime-removed', not old.exists())
    check('current-and-mapped-runtimes-preserved', current.exists() and mapped.exists())
    check('unknown-and-corrupt-runtime-files-preserved', altered.exists() and corrupt.exists())
    retired = runtime(base, b'retired recovered runtime')
    retired_recovery = retired.with_name(retired.name+'-recovery-111111111111')
    retired.rename(retired_recovery)
    current_recovery = current.with_name(current.name+'-recovery-222222222222')
    shutil.copytree(current, current_recovery)
    with patch.object(storage, 'process_references', return_value=(set(), lambda p: str(p) in protected, False)):
        receipt = storage.cleanup_closed_previews(base, current)
    check('obsolete-verified-recovery-cache-is-reclaimable', not retired_recovery.exists())
    check('current-manifest-recovery-cache-is-preserved', current.exists() and current_recovery.exists())
    with patch.object(storage, 'process_references', return_value=(set(), lambda p: False, True)):
        receipt = storage.cleanup_closed_previews(base, current)
    check('uncertain-process-access-prevents-deletion', not receipt['deleted'] and active.exists())
    if Path('/proc').is_dir():
        child = subprocess.Popen([sys.executable, '-c', 'import time;print("ready",flush=True);time.sleep(30)'],
            env=dict(os.environ, NEXTSPACE_STORAGE_FIXTURE=str(active)), stdout=subprocess.PIPE, text=True)
        try:
            assert select.select([child.stdout], [], [], 5)[0] and child.stdout.readline().strip() == 'ready'
            pids, in_use, _ = storage.process_references(base)
            check('real-live-process-reference-detected', child.pid in pids and in_use(active))
            receipt = storage.cleanup_closed_previews(base, current)
            check('real-live-process-profile-survives-cleanup', (active / 'runtime/firefox-profile').exists() and child.poll() is None)
        finally:
            child.terminate(); child.wait(timeout=5)
    free = type('Usage', (), {'free': 0})()
    with patch.object(storage.shutil, 'disk_usage', return_value=free), \
            patch.object(storage, 'process_references', return_value=(set(), lambda p: False, True)):
        try:
            storage.ensure_preview_space(current, [current / 'library'], base)
        except RuntimeError as error:
            rejected = 'desktop was not started' in str(error)
        else:
            rejected = False
    check('insufficient-space-fails-before-gui', rejected)
    recoverable = closed(base, 'recoverable')
    available = storage.shutil.disk_usage(base)
    with patch.object(storage, 'process_references', return_value=(set(), lambda p: False, False)), \
            patch.object(storage.shutil, 'disk_usage', side_effect=[free, free, available]):
        recovered = storage.ensure_preview_space(current, [current / 'library'], base)
    check('preflight-remeasures-space-after-scoped-cleanup', recovered['complete'] and
          not (recoverable / 'runtime/firefox-profile').exists())

    original = closed(base, 'original-format')
    transitional = closed(base, 'reaper-format')
    incomplete = closed(base, 'original-incomplete')
    unknown_format = closed(base, 'unknown-format')
    referenced = closed(base, 'original-referenced')
    original_receipt = dict(session_exit=0, browser_exits=[0, -15, 0, -15], live=[])
    for folder in (original, referenced):
        (folder / 'cleanup.json').write_text(json.dumps(original_receipt))
    (transitional / 'cleanup.json').write_text(json.dumps(dict(original_receipt,
        detached_processes=dict(terminated=[], forced=[], remaining=[]))))
    (incomplete / 'cleanup.json').write_text(json.dumps(dict(original_receipt, browser_exits=[0, None])))
    (unknown_format / 'cleanup.json').write_text(json.dumps(dict(original_receipt, unrecognized=True)))
    with patch.object(storage, 'process_references', return_value=(set(), lambda p: p == referenced, False)):
        receipt = storage.cleanup_closed_previews(base, current)
    check('original-shipped-preview-receipt-reclaims-closed-profiles',
          not (original / 'runtime/firefox-profile').exists() and (original / 'evidence.png').exists())
    check('shipped-reaper-receipt-without-errors-field-reclaims-closed-profiles',
          not (transitional / 'runtime/firefox-profile').exists())
    check('legacy-incomplete-and-unknown-receipts-preserved',
          (incomplete / 'runtime/firefox-profile').exists() and (unknown_format / 'runtime/firefox-profile').exists())
    check('legacy-referenced-profile-preserved', (referenced / 'runtime/firefox-profile').exists())
    check('missing-teardown-fields-are-not-treated-as-clean', not storage.closed_receipt(dict(session_exit=0, live=[])))
    check('legacy-live-owner-is-not-treated-as-closed', not storage.closed_receipt(dict(original_receipt, live=[42])))

    app = base / 'app'; app.mkdir()
    executable = app / 'browser'; executable.write_bytes(b'unchanged executable')
    (app / 'resources.pak').write_bytes(b'original resource')
    private = base / 'private'; private.mkdir()
    with ExitStack() as lifetime:
        root = private_webui.private_application(executable, {'resources.pak': b'patched resource'}, lifetime, private)
        check('successful-copy-reuses-original-executable', root.joinpath('browser').stat().st_ino == executable.stat().st_ino)
        check('successful-copy-patches-only-private-resource', root.joinpath('resources.pak').read_bytes() == b'patched resource' and (app / 'resources.pak').read_bytes() == b'original resource')
    check('normal-lifetime-removes-private-resource-copy', not root.exists())
    with ExitStack() as lifetime, patch.object(private_webui.shutil, 'disk_usage', return_value=free):
        try:
            private_webui.private_application(executable, {'resources.pak': b'patched'}, lifetime, private)
        except OSError as error:
            rejected = error.errno == errno.ENOSPC
        else:
            rejected = False
        check('private-copy-preflight-creates-no-scratch', rejected and not list(private.iterdir()))
    write_bytes = Path.write_bytes
    def full_disk(path, value):
        if path.name == 'resources.pak' and path.parent.name.startswith('webui-'):
            write_bytes(path, b'partial')
            raise OSError(errno.ENOSPC, 'fixture disk full')
        return write_bytes(path, value)
    with ExitStack() as lifetime, patch.object(Path, 'write_bytes', full_disk):
        try:
            private_webui.private_application(executable, {'resources.pak': b'patched'}, lifetime, private)
        except OSError as error:
            rejected = error.errno == errno.ENOSPC
        else:
            rejected = False
        check('write-exhaustion-removes-partial-copy-immediately', rejected and not list(private.iterdir()))

args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(checks, indent=2) + '\n')
print(json.dumps(dict(passed=len(checks))))
