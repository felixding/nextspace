"""Snapshot installed paths for the native desktop package lifecycle."""
import hashlib
import os


def snapshot(paths):
    result = {}
    for path in paths:
        if not path.exists() and not path.is_symlink():
            result[str(path)] = None
        else:
            for entry in sorted(path.rglob('*')) if path.is_dir() else [path]:
                if entry.is_symlink(): result[str(entry)] = 'link:' + os.readlink(entry)
                elif entry.is_file(): result[str(entry)] = hashlib.sha256(entry.read_bytes()).hexdigest()
    return result
