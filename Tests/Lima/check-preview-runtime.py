#!/usr/bin/env python3
"""Exercise verified cache reuse, recovery and interrupted installs on real files."""
import argparse
import errno
import hashlib
import importlib.util
import json
import mmap
import os
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--installer', required=True, type=Path)
parser.add_argument('--output', required=True, type=Path)
args = parser.parse_args()
spec = importlib.util.spec_from_file_location('preview_runtime_installer', args.installer)
compatibility = importlib.util.module_from_spec(spec); spec.loader.exec_module(compatibility)
import preview_runtime as module
checks = []


def check(name, value):
    assert value, name
    checks.append(dict(case=name, passed=True))


def rejected(source, parent):
    try:
        compatibility.install_update(source, parent)
    except (RuntimeError, ValueError):
        return True
    return False


with tempfile.TemporaryDirectory(prefix='nxs-preview-runtime-') as temporary:
    root = Path(temporary); source = root/'source'; source.mkdir(); parent = root/'installed'; parent.mkdir()
    data = b'qualified runtime'; (source/'library').write_bytes(data); (source/'alias').symlink_to('library')
    records = [dict(path='library', sha256=hashlib.sha256(data).hexdigest()), dict(path='alias', link='library')]
    (source/'manifest.json').write_text(json.dumps(records)+'\n')
    reports = []
    stage = compatibility.install_update(source, parent, report=reports.append)
    check('first-install-preserves-files-and-links', (stage/'library').read_bytes()==data and os.readlink(stage/'alias')=='library')
    (source/'library').unlink()
    check('valid-cache-does-not-reread-unused-source-files', compatibility.install_update(source, parent)==stage)
    (source/'library').write_bytes(data)
    (stage/'library').write_bytes(b'cached corruption')
    with (stage/'library').open('rb') as file, mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as mapping:
        repaired = compatibility.install_update(source, parent, report=reports.append)
        check('corrupt-cache-creates-verified-recovery', repaired!=stage and (repaired/'library').read_bytes()==data)
        check('old-cache-and-active-mapping-are-preserved', (stage/'library').read_bytes()==b'cached corruption' and mapping[:]==b'cached corruption')
    check('repair-receipt-identifies-preserved-failure', reports[-1]['recovered'] and reports[-1]['copied'] and
          'library' in reports[-1]['preserved_invalid_caches'][0]['reason'])
    check('verified-recovery-is-reused-without-more-copies', compatibility.install_update(source, parent)==repaired and
          len(list(parent.glob('browser-density-update-*')))==2)
    (repaired/'alias').unlink(); (repaired/'alias').symlink_to('wrong')
    repaired_link = compatibility.install_update(source, parent)
    check('incorrect-cached-link-is-recovered', repaired_link!=repaired and os.readlink(repaired_link/'alias')=='library')
    check('incorrect-old-link-is-preserved', os.readlink(repaired/'alias')=='wrong')
    (repaired_link/'library').unlink()
    missing_file = compatibility.install_update(source, parent)
    check('missing-cached-file-is-recovered', missing_file!=repaired_link and (missing_file/'library').read_bytes()==data)
    (missing_file/'manifest.json').write_text('corrupt manifest')
    missing_manifest = compatibility.install_update(source, parent)
    check('incorrect-cached-manifest-is-recovered', missing_manifest!=missing_file)

    fresh = root/'fresh'; fresh.mkdir(); (source/'library').write_bytes(b'corrupt source')
    check('corrupt-source-is-rejected', rejected(source, fresh))
    check('failed-source-verification-publishes-nothing', not list(fresh.iterdir()))
    invalid = root/'invalid'; invalid.mkdir()
    cache = invalid/stage.name; shutil.copytree(stage, cache, symlinks=True)
    check('corrupt-source-does-not-replace-existing-bad-cache', rejected(source, invalid) and
          (cache/'library').read_bytes()==b'cached corruption' and len(list(invalid.iterdir()))==1)
    (source/'library').write_bytes(data)

    alias = root/'parent-alias'; alias.symlink_to(parent, target_is_directory=True)
    check('symlinked-install-parent-is-rejected', rejected(source, alias))
    invalid_alias = root/'invalid-alias'; invalid_alias.mkdir()
    (invalid_alias/stage.name).symlink_to(source, target_is_directory=True)
    check('symlinked-installation-is-rejected', rejected(source, invalid_alias) and (source/'library').read_bytes()==data)

    interrupted = root/'interrupted'; interrupted.mkdir()
    copytree = shutil.copytree
    def failed_copy(src, target, **options):
        Path(target).mkdir(); (Path(target)/'partial').write_bytes(b'partial')
        raise OSError(errno.ENOSPC, 'fixture disk full')
    with patch.object(module.shutil, 'copytree', failed_copy):
        try:compatibility.install_update(source, interrupted)
        except OSError as error:failed = error.errno==errno.ENOSPC
        else:failed = False
    check('disk-full-copy-removes-unpublished-scratch', failed and not list(interrupted.iterdir()))
    with patch.object(module, '_sync_copy', side_effect=OSError(errno.ENOSPC, 'fixture flush failure')):
        try:compatibility.install_update(source, interrupted)
        except OSError as error:failed = error.errno==errno.ENOSPC
        else:failed = False
    check('delayed-write-failure-publishes-no-cache', failed and not list(interrupted.iterdir()))
    def damaged_copy(src, target, **options):
        value = copytree(src, target, **options); (Path(target)/'library').write_bytes(b'damaged during copy'); return value
    with patch.object(module.shutil, 'copytree', damaged_copy):
        check('damaged-copy-fails-before-publication', rejected(source, interrupted) and not list(interrupted.iterdir()))

    malformed = root/'malformed'; malformed.mkdir()
    (malformed/'manifest.json').write_text(json.dumps([dict(path='../outside', sha256=hashlib.sha256(data).hexdigest())]))
    check('manifest-path-escape-is-rejected', rejected(malformed, interrupted) and not list(interrupted.iterdir()))
    check('successful-installs-leave-no-install-scratch', not list(parent.glob('preview-install-*')))

args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(checks, indent=2)+'\n')
print(json.dumps(dict(passed=len(checks))))
