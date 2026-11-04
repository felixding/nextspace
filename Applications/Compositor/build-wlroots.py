#!/usr/bin/env python3
"""Build the checksum-pinned wlroots dependency for NEXTSPACE."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes(root):
    return {str(path.relative_to(root)): digest(path) for path in sorted(root.rglob('*'))
            if path.is_file() and path.name != '.nextspace-source.json'}


def build(repo, destination, prefix='/usr/local', libdir='lib', install=True,
          destdir=None, update_loader_cache=False):
    destination.mkdir(parents=True, exist_ok=True)
    if update_loader_cache and (destdir or not install):
        raise ValueError('Loader cache updates require an unstaged installation')
    package = json.loads((repo / 'Protocols/manifest.json').read_text())['wlroots']
    archive = destination / ('wlroots-' + package['version'] + '.tar.bz2')
    if not archive.exists():
        bundled = repo / 'sources' / archive.name
        if bundled.is_file(): shutil.copyfile(bundled, archive)
        else: subprocess.run(['curl', '-fLsS', package['source'], '-o', str(archive)], check=True)
    assert digest(archive) == package['sha256'], 'wlroots archive checksum'
    patches = package.get('patches', [])
    for patch in patches:
        assert digest(repo / patch['path']) == patch['sha256'], patch['path']
    key = hashlib.sha256(json.dumps(package, sort_keys=True).encode()).hexdigest()[:16]
    source = destination / ('wlroots-source-' + key)
    marker = source / '.nextspace-source.json'
    if source.exists():
        assert marker.is_file() and json.loads(marker.read_text()) == source_hashes(source), 'Modified wlroots source cache'
    else:
        with tempfile.TemporaryDirectory(prefix='wlroots-unpack-', dir=destination) as temporary:
            root = Path(temporary) / 'source'
            root.mkdir()
            subprocess.run(['tar', 'xf', str(archive), '--strip-components=1', '-C', str(root)], check=True)
            for patch in patches:
                with (repo / patch['path']).open('rb') as content:
                    subprocess.run(['patch', '--batch', '--forward', '-p1'], cwd=root, stdin=content, check=True)
            (root / '.nextspace-source.json').write_text(json.dumps(source_hashes(root), sort_keys=True) + '\n')
            root.rename(source)
    shutil.copyfile(marker, destination / 'wlroots-source-hashes.json')
    build_key = hashlib.sha256(json.dumps([key, prefix, libdir]).encode()).hexdigest()[:16]
    output = destination / ('wlroots-build-' + build_key)
    configure = ['meson', 'setup'] + (['--reconfigure'] if output.exists() else [])
    subprocess.run(configure + [str(output), str(source), '--wrap-mode=nodownload', '--prefix=' + prefix, '--libdir=' + libdir,
        '-Dexamples=false', '-Dxwayland=disabled', '-Drenderers=gles2', '-Dbackends=drm,libinput',
        '-Dallocators=gbm', '-Dsession=enabled', '-Dlibliftoff=enabled', '-Dcolor-management=disabled'], check=True)
    subprocess.run(['meson', 'compile', '-C', str(output), '-j', os.environ.get('JOBS', '4')], check=True)
    if install:
        command = ['meson', 'install', '-C', str(output)]
        if destdir: command += ['--destdir', str(destdir)]
        subprocess.run(command, check=True)
        if update_loader_cache: subprocess.run(['ldconfig'], check=True)
    result = dict(source=str(source), build=str(output), prefix=prefix, libdir=libdir,
        pkgconfig=str(output / 'meson-uninstalled'), library_dir=str(output), installed=install,
        destdir=str(destdir) if destdir else None)
    (destination / 'wlroots-build.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repo', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--prefix', default='/usr/local')
    parser.add_argument('--libdir', default='lib')
    parser.add_argument('--no-install', action='store_true')
    parser.add_argument('--destdir', type=Path)
    parser.add_argument('--update-loader-cache', action='store_true')
    args = parser.parse_args()
    build(args.repo.resolve(), args.destination.resolve(), args.prefix, args.libdir,
          not args.no_install, args.destdir.resolve() if args.destdir else None, args.update_loader_cache)
