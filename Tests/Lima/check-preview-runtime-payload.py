#!/usr/bin/env python3
"""Reproduce the reported failure and recover the complete real delivery payload."""
import argparse
import hashlib
import importlib.util
import json
import mmap
import os
from pathlib import Path
import stat
import tempfile

from preview_runtime import install_update

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--payload', type=Path, required=True)
parser.add_argument('--old-installer', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
spec = importlib.util.spec_from_file_location('old_runtime_installer', args.old_installer)
old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
manifest = (args.payload/'manifest.json').read_bytes(); records = json.loads(manifest)
reported = 'Workspace.app/Resources/Advanced.wsprefs/Advanced'
expected = next(row['sha256'] for row in records if row['path']==reported)
checks = []


def check(name, value, **details):
    assert value, name
    checks.append(dict(case=name, passed=True, **details))


def independently_verify(root):
    assert (root/'manifest.json').read_bytes()==manifest
    for row in records:
        path = root/row['path']
        if 'link' in row:
            assert path.is_symlink() and os.readlink(path)==row['link'], row['path']
        else:
            assert not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256'], row['path']
            assert stat.S_IMODE(path.stat().st_mode)==stat.S_IMODE((args.payload/row['path']).stat().st_mode), row['path']
    return len(records)


args.output.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='actual-payload-cache-', dir=args.output) as temporary:
    parent = Path(temporary)
    cache = old.install_update(args.payload, parent)
    damaged = cache/reported; damaged.write_bytes(b'corrupt cached Advanced executable')
    try:
        old.install_update(args.payload, parent)
    except RuntimeError as error:
        reproduced = 'Preview runtime file differs:' in str(error) and reported in str(error)
        original_error = str(error)
    else:
        reproduced = False
    check('previous-shipped-installer-reproduces-reported-advanced-failure', reproduced)
    reports = []
    with damaged.open('rb') as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as mapping:
        recovered = install_update(args.payload, parent, report=reports.append)
        check('complete-shipped-runtime-is-recovered', independently_verify(recovered)==len(records), records=len(records))
        check('damaged-cache-and-existing-mapping-are-preserved',
              damaged.read_bytes()==b'corrupt cached Advanced executable' and mapping[:]==damaged.read_bytes())
    check('reported-advanced-executable-matches-shipped-digest', hashlib.sha256((recovered/reported).read_bytes()).hexdigest()==expected,
          sha256=expected)
    check('receipt-records-exact-failed-file', reports[-1]['copied'] and reports[-1]['recovered'] and
          reported in reports[-1]['preserved_invalid_caches'][0]['reason'])
    repeated = install_update(args.payload, parent, report=reports.append)
    check('next-launch-reuses-verified-recovery', repeated==recovered and not reports[-1]['copied'] and
          len(list(parent.glob('browser-density-update-*')))==2)
    (recovered/'Workspace.app/Workspace').unlink()
    second = install_update(args.payload, parent, report=reports.append)
    check('missing-workspace-executable-also-recovers-entire-runtime', second!=recovered and
          independently_verify(second)==len(records), records=len(records))
    check('all-shipped-source-bytes-remain-unchanged', independently_verify(args.payload)==len(records))
    check('no-interrupted-install-scratch-remains', not list(parent.glob('preview-install-*')))
check('temporary-runtime-copies-are-removed', not Path(temporary).exists())
receipt = dict(complete=True, checks=checks, manifest_sha256=hashlib.sha256(manifest).hexdigest(),
               actual_payload=True, records=len(records), previous_error=original_error,
               graphical_vm_run=False, ssh_used=False)
(args.output/'full-payload.json').write_text(json.dumps(receipt, indent=2)+'\n')
print(json.dumps(dict(complete=True, records=len(records), checks=len(checks), actual_payload=True)))
