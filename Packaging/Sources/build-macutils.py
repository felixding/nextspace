#!/usr/bin/env python3
"""Build OpenUp's pinned extractor with portable CRC tables."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile


def build(repo, work, output):
    sys.path.insert(0, str(repo / 'Packaging/Debian'))
    from common import digest, fetch
    specification = json.loads((repo / 'Protocols/manifest.json').read_text())['macutils']
    work.mkdir(parents=True)
    cache = work / 'archives'
    cache.mkdir()
    archives = [fetch(repo, cache, 'sources/' + entry['name'], entry['source'], entry['sha256'])
                for entry in specification['archives']]
    source = work / 'source'
    source.mkdir()
    with tarfile.open(archives[0]) as archive:
        archive.extractall(source, filter='data')
    tree = source / 'macutils'
    with tarfile.open(archives[1]) as archive:
        archive.extractall(tree, filter='data')
    with (work / 'build.log').open('w') as log:
        patches = [tree / 'debian/patches' / name for name in
                   (tree / 'debian/patches/series').read_text().splitlines()]
        for entry in specification['patches']:
            patch = repo / entry['path']
            if digest(patch) != entry['sha256']:
                raise ValueError('Extractor patch checksum: ' + entry['path'])
            patches.append(patch)
        for patch in patches:
            subprocess.run(['patch', '--batch', '--forward', '-p1', '-i', str(patch)],
                           cwd=tree, stdout=log, stderr=subprocess.STDOUT, check=True)
        subprocess.run(['make', '-j' + os.environ.get('JOBS', '2')],
                       cwd=tree, stdout=log, stderr=subprocess.STDOUT, check=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tree / 'macunpack/macunpack', output)
    output.chmod(0o755)
    licenses = work / 'licenses'
    licenses.mkdir()
    shutil.copy2(tree / 'debian/copyright', licenses / 'copyright')
    (work / 'result.json').write_text(json.dumps(dict(version=specification['version'],
        source_archives={path.name: digest(path) for path in archives},
        patches={str(path): digest(path) for path in patches}, output_sha256=digest(output)), indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.repo.resolve(), args.build.resolve(), args.output.resolve())
