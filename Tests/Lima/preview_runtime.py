"""Verify and publish preview runtime caches without modifying an existing cache."""
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid

_CACHE = re.compile(r'(browser-density-update-[0-9a-f]{16})(?:-recovery-[0-9a-f]{12})?\Z')


def cache_key(manifest):
    return 'browser-density-update-' + hashlib.sha256(manifest).hexdigest()[:16]


def cache_family(name):
    match = _CACHE.fullmatch(name)
    return match.group(1) if match else None


def manifest_records(manifest):
    records = json.loads(manifest)
    if not isinstance(records, list):
        raise ValueError('Invalid preview runtime manifest')
    seen = set()
    for row in records:
        if not isinstance(row, dict) or not isinstance(row.get('path'), str):
            raise ValueError('Invalid preview runtime manifest entry')
        relative = Path(row['path'])
        if (relative.is_absolute() or '..' in relative.parts or not relative.parts or
                relative.as_posix() != row['path'] or row['path'] in seen):
            raise ValueError('Invalid preview runtime manifest path')
        seen.add(row['path'])
        if 'link' in row:
            if not isinstance(row['link'], str) or 'sha256' in row:
                raise ValueError('Invalid preview runtime link')
            target = Path(row['link'])
            if target.is_absolute() or '..' in target.parts:
                raise ValueError('Preview runtime links must remain inside the cache')
        elif not isinstance(row.get('sha256'), str) or not re.fullmatch('[0-9a-f]{64}', row['sha256']):
            raise ValueError('Invalid preview runtime digest')
    return records


def verify_runtime(root, manifest, records):
    root = Path(root)
    try:
        marker = root / 'manifest.json'
        if marker.is_symlink() or marker.read_bytes() != manifest:
            raise RuntimeError('Preview runtime manifest differs: ' + str(marker))
        for row in records:
            relative = Path(row['path']); path = root / relative
            if any((root / parent).is_symlink() for parent in relative.parents):
                raise RuntimeError('Preview runtime directory is a link: ' + str(path))
            if 'link' in row:
                if not path.is_symlink() or os.readlink(path) != row['link']:
                    raise RuntimeError('Preview runtime link differs: ' + str(path))
            elif path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
                raise RuntimeError('Preview runtime file differs: ' + str(path))
    except OSError as error:
        raise RuntimeError('Preview runtime is incomplete: ' + str(error.filename)) from error


def _owned_directory(path):
    if path.is_symlink() or not path.is_dir() or path.stat().st_uid != os.getuid():
        raise RuntimeError('Preview runtime directory has a different owner or type: ' + str(path))


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        try:
            os.fsync(descriptor)
        except OSError as error:
            if error.errno not in (errno.EINVAL, errno.ENOTSUP):
                raise
    finally:
        os.close(descriptor)


def _sync_copy(root, records):
    # Force delayed allocation/write errors before publishing the directory.
    for name in ['manifest.json', *[row['path'] for row in records if 'link' not in row]]:
        with (root / name).open('rb') as source:
            os.fsync(source.fileno())
    for directory, children, files in os.walk(root, topdown=False, followlinks=False):
        _sync_directory(directory)


def install_update(payload, parent=None, report=None):
    payload = Path(payload)
    manifest = (payload / 'manifest.json').read_bytes()
    records = manifest_records(manifest)
    parent = Path('/var/tmp/nextspace-native-ui') if parent is None else Path(parent)
    _owned_directory(parent)
    canonical = parent / cache_key(manifest)
    invalid = []

    def finish(stage, *, copied):
        if report:
            report(dict(stage=str(stage), manifest_sha256=hashlib.sha256(manifest).hexdigest(),
                        records=len(records), copied=copied, recovered=stage != canonical,
                        preserved_invalid_caches=invalid))
        return stage

    candidates = [canonical, *sorted(parent.glob(canonical.name + '-recovery-*'))]
    for stage in candidates:
        if not stage.exists() and not stage.is_symlink():
            continue
        if cache_family(stage.name) != canonical.name:
            continue
        _owned_directory(stage)
        try:
            verify_runtime(stage, manifest, records)
        except RuntimeError as error:
            invalid.append(dict(path=str(stage), reason=str(error)))
        else:
            return finish(stage, copied=False)

    # Validate source bytes before touching any installation. Damaged caches
    # stay intact, including caches still mapped by another process.
    verify_runtime(payload, manifest, records)
    with tempfile.TemporaryDirectory(prefix='preview-install-', dir=parent) as scratch:
        temporary = Path(scratch) / 'runtime'
        shutil.copytree(payload, temporary, symlinks=True)
        _sync_copy(temporary, records)
        verify_runtime(temporary, manifest, records)
        stage = canonical
        if stage.exists() or stage.is_symlink():
            stage = parent / (canonical.name + '-recovery-' + uuid.uuid4().hex[:12])
        try:
            temporary.rename(stage)
        except OSError as error:
            if error.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                raise
            _owned_directory(stage)
            verify_runtime(stage, manifest, records)
            return finish(stage, copied=False)
        _sync_directory(parent)
    verify_runtime(stage, manifest, records)
    return finish(stage, copied=True)
