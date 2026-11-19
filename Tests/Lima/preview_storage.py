"""Bounded preview storage; reclaim only verified, closed NEXTSPACE data."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from preview_runtime import cache_family, cache_key, manifest_records, verify_runtime

STORAGE = Path('/var/tmp/nextspace-native-ui')


def scan_references(storage, uid):
    """Return only referenced preview paths, never process environment contents."""
    candidates = [*storage.glob('macbook-preview-*'), *storage.glob('browser-density-update-*')]
    protected = set()
    live = set()
    uncertain = False
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        references = []
        try:
            if process.stat().st_uid != uid:
                continue
            live.add(int(process.name))
            for name in ('cmdline', 'environ', 'maps'):
                references.append((process / name).read_bytes())
            for link in [process / 'exe', process / 'cwd', *list((process / 'fd').iterdir())]:
                try:
                    references.append(os.fsencode(os.readlink(link)))
                except FileNotFoundError:
                    pass
        except (FileNotFoundError, ProcessLookupError):
            pass
        except PermissionError:
            uncertain = True
        finally:
            for candidate in candidates:
                if any(os.fsencode(candidate) in value for value in references):
                    protected.add(str(candidate))
    return dict(live=sorted(live), protected=sorted(protected), uncertain=uncertain)


def process_references(storage=STORAGE):
    storage = Path(storage)
    receipt = scan_references(storage, os.getuid())
    if receipt['uncertain'] and os.getuid() != 0:
        # Privilege-separated SSH processes can deny their own user's /proc
        # reads. The existing sudo entitlement supplies a read-only inventory;
        # only matching preview paths and live PIDs leave that process.
        try:
            result = subprocess.run(['sudo', '-n', '/usr/bin/python3', str(Path(__file__).resolve()),
                '--process-references', str(os.getuid()), str(storage)],
                capture_output=True, text=True, timeout=20, check=True)
            receipt = json.loads(result.stdout)
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return set(receipt['live']), lambda path: str(path) in receipt['protected'], receipt['uncertain']


def owned_directory(path, device):
    return (not path.is_symlink() and path.is_dir() and
            path.stat().st_uid == os.getuid() and path.stat().st_dev == device)


def same_filesystem_tree(path, device):
    for root, directories, files in os.walk(path, followlinks=False):
        for name in directories + files:
            item = Path(root) / name
            if not item.is_symlink() and item.stat().st_dev != device:
                return False
    return True


def verified_runtime(path):
    """An install cache is disposable only if its complete manifest still matches."""
    manifest = (path / 'manifest.json').read_bytes()
    if cache_family(path.name) != cache_key(manifest):
        return False
    records = manifest_records(manifest)
    verify_runtime(path, manifest, records)
    expected = {'manifest.json'}
    for row in records:
        relative = Path(row['path'])
        expected.add(relative.as_posix())
        expected.update(p.as_posix() for p in relative.parents if str(p) != '.')
    return all(p.relative_to(path).as_posix() in expected for p in path.rglob('*'))


def closed_receipt(receipt):
    """Recognize the three teardown formats actually shipped with the preview."""
    if not isinstance(receipt, dict):
        return False
    original = {'session_exit', 'browser_exits', 'live'}
    reaper = original | {'detached_processes'}
    current = reaper | {'errors'}
    if set(receipt) not in (original, reaper, current):
        return False
    if (type(receipt['session_exit']) is not int or receipt['live'] != [] or
            not isinstance(receipt['browser_exits'], list) or
            any(type(value) is not int for value in receipt['browser_exits'])):
        return False
    if 'detached_processes' in receipt:
        detached = receipt['detached_processes']
        if not isinstance(detached, dict) or detached.get('remaining') != []:
            return False
    return receipt.get('errors', []) == []


def cleanup_closed_previews(storage=STORAGE, keep_runtime=None):
    storage = Path(storage)
    keep_runtime = Path(keep_runtime) if keep_runtime is not None else None
    if storage.is_symlink() or storage.stat().st_uid != os.getuid():
        raise ValueError('Preview storage has a different owner')
    before = shutil.disk_usage(storage).free
    device = storage.stat().st_dev
    live, in_use, uncertain = process_references(storage)
    deleted = []
    if not uncertain:
        for root in sorted(storage.glob('macbook-preview-*')):
            if not owned_directory(root, device) or in_use(root):
                continue
            try:
                receipt = json.loads((root / 'cleanup.json').read_text())
                owner = json.loads((root / 'owner.json').read_text())
                if (owner['uid'] != os.getuid() or owner['pid'] in live or
                        not closed_receipt(receipt)):
                    continue
                runtime = root / 'runtime'
                if not owned_directory(runtime, device):
                    continue
                for name in ('firefox-profile', 'chromium-profile', 'cache'):
                    item = runtime / name
                    if owned_directory(item, device) and same_filesystem_tree(item, device):
                        shutil.rmtree(item)
                        deleted.append(str(item))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        for root in sorted(storage.glob('browser-density-update-*')):
            if (cache_family(root.name) is None or
                    (keep_runtime is not None and cache_family(root.name) == cache_family(keep_runtime.name)) or
                    not owned_directory(root, device) or in_use(root)):
                continue
            try:
                if same_filesystem_tree(root, device) and verified_runtime(root):
                    shutil.rmtree(root)
                    deleted.append(str(root))
            except (OSError, ValueError, KeyError, TypeError, RuntimeError):
                continue
    after = shutil.disk_usage(storage).free
    return dict(before_free_bytes=before, after_free_bytes=after,
                reclaimed_bytes=max(0, after - before), deleted=deleted,
                uncertain_process_access=uncertain)


def ensure_preview_space(payload, resource_packs, storage=STORAGE):
    storage = Path(storage)
    if storage.is_symlink() or storage.stat().st_uid != os.getuid():
        raise ValueError('Preview storage has a different owner')
    manifest = (payload / 'manifest.json').read_bytes()
    keep = storage / cache_key(manifest)
    # Patched resources can grow. Include both their private copies, a possible
    # new runtime install, and space for browser profiles/logs before any GUI.
    required = 512 * 1024**2 + 2 * sum(Path(p).stat().st_size for p in resource_packs)
    if not keep.exists():
        required += sum(p.stat().st_size for p in payload.rglob('*') if p.is_file() and not p.is_symlink())
    required = max(1024**3, required)
    before = shutil.disk_usage(storage).free
    receipt = dict(before_free_bytes=before, after_free_bytes=before,
                   reclaimed_bytes=0, deleted=[], uncertain_process_access=False)
    if before < required:
        receipt = cleanup_closed_previews(storage, keep)
    receipt.update(required_free_bytes=required, complete=receipt['after_free_bytes'] >= required)
    if not receipt['complete']:
        raise RuntimeError('Not enough free space inside the preview VM: '
                           f"{receipt['after_free_bytes'] / 1024**2:.0f} MiB free; "
                           f"{required / 1024**2:.0f} MiB required after safe cleanup. "
                           'The desktop was not started; uncertain files were preserved.')
    return receipt


if __name__ == '__main__':
    if len(sys.argv) != 4 or sys.argv[1] != '--process-references' or os.getuid() != 0:
        raise SystemExit('This entry point only inventories preview process references.')
    uid = int(sys.argv[2]); storage = Path(sys.argv[3])
    if not storage.is_absolute() or storage.is_symlink() or storage.stat().st_uid != uid:
        raise SystemExit('Preview storage has a different owner')
    print(json.dumps(scan_references(storage, uid)))
