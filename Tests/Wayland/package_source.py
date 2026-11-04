#!/usr/bin/env python3
"""Rebuild a package from its source archive with downloads blocked."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Packaging/Debian'))
from common import source_digest


def unpack_source(archive, receipt, destination):
    """Verify and unpack the exact source inputs named by a package receipt."""
    original = json.loads(receipt.read_text())
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == original['source_sha256']
    destination.mkdir(parents=True)
    with tarfile.open(archive) as package:
        package.extractall(destination, filter='data')
    repo = destination / 'nextspace'
    manifest = repo / 'build-inputs.json'
    inputs = json.loads(manifest.read_text()) if manifest.exists() else original['inputs']
    assert inputs == original['inputs'], 'Source manifest differs from its receipt'
    files = {str(path.relative_to(repo)): path for path in repo.rglob('*') if path.is_file() or path.is_symlink()}
    files.pop('build-inputs.json', None)
    assert set(files) == set(inputs), 'Source archive has missing or unrecorded inputs'
    for relative, path in files.items():
        assert path.is_file() and path.resolve().is_relative_to(repo), relative
        assert source_digest(path) == inputs[relative], relative
    return repo, original


def run(archive, receipt, work, version, desktop=False):
    work.mkdir(parents=True)
    repo, original = unpack_source(archive, receipt, work / 'unpacked')
    blocked = work / 'blocked-downloads'
    blocked.mkdir()
    curl = blocked / 'curl'
    curl.write_text('#!/bin/sh\necho "Unexpected source download" >&2\nexit 99\n')
    curl.chmod(0o755)
    env = dict(os.environ, PATH=str(blocked) + ':' + os.environ['PATH'])
    for key in ('http_proxy', 'https_proxy', 'all_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY'):
        env[key] = 'http://127.0.0.1:9'
    for key in ('no_proxy', 'NO_PROXY'): env[key] = ''
    env.pop('LD_LIBRARY_PATH', None)
    output = work / 'packages'
    recipe = 'build-desktop.py' if desktop else 'build-wayland.py'
    with (work / 'rebuild.log').open('w') as log:
        subprocess.run(['python3', str(repo / 'Packaging/Debian' / recipe), '--repo', str(repo),
            '--build-dir', str(work / 'build'), '--output', str(output), '--version', version],
            env=env, stdout=log, stderr=log, check=True)
    result = json.loads(((output / ('nextspace-desktop_' + version + '.json')) if desktop else
        next(output.glob('*.json'))).read_text())
    assert result['inputs'] == original['inputs'], 'Source rebuild changed its inputs'
    binaries = dict(packages=result['packages']) if desktop else dict(
        binary=result['binary'], binary_sha256=result['binary_sha256'])
    (work / 'results.json').write_text(json.dumps(dict(source_inputs=len(result['inputs']),
        inputs_identical=True, downloads_blocked=True, version=version, **binaries), indent=2) + '\n')
    print('Source archive rebuild: identical inputs and blocked downloads PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--desktop', action='store_true', help='Rebuild the complete desktop in a fresh disposable root builder')
    parser.add_argument('--extract-only', action='store_true', help='Only verify and unpack the receipt sources into work-dir')
    args = parser.parse_args()
    if args.extract_only:
        repo, original = unpack_source(args.archive.resolve(), args.receipt.resolve(), args.work_dir.resolve())
        assert original['version'] == args.version, 'Source receipt version differs from the requested cohort'
        print(repo)
    else:
        run(args.archive.resolve(), args.receipt.resolve(), args.work_dir.resolve(), args.version, args.desktop)
