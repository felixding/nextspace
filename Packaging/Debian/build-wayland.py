#!/usr/bin/env python3
"""Build an opt-in compositor package with its private pinned wlroots library."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

from common import digest, source_digest, snapshot_sources, run, source_files as collect_sources, write_binary

PACKAGE = 'nextspace-wayland-compositor'
PREFIX = 'usr/NextSpace'
LIBDIR = 'lib/nextspace-wayland'
LAUNCHERS = ('nextspace-wayland-session', 'nextspace-wayland-greeter', 'nextspace-wayland-locker',
    'nextspace-wayland-capture')
SOURCE_DIRS = ('Applications/Compositor', 'Applications/Session', 'Protocols',
    'Libraries/gnustep/back/Source/wayland/protocols',
    'Libraries/gnustep/nextspace-theme/Resources/ThemeImages',
    'Tests/Wayland', 'Tests/GNUstep-GUI', 'Packaging/Debian')


def source_files(repo):
    return collect_sources(repo, SOURCE_DIRS,
        ['LICENSE', 'Libraries/gnustep/back/Source/cairo/WaylandCapture.h',
         'Libraries/gnustep/gnustep-gui-images.tar.gz',
         'Applications/Artwork/CheckGlyphs.svg',
         'Packaging/Sources/vector_art.py',
         'Libraries/gnustep/Artwork.svg',
         'Libraries/gnustep/SliderKnobs.svg',
         'Libraries/gnustep/PageOrientation.svg',
         'Libraries/gnustep/TabEdges.svg',
         'Libraries/gnustep/StepperButtons.svg',
         'Libraries/gnustep/RulerMarkers.svg',
         'Libraries/gnustep/ProgressSpinners.svg',
         'Libraries/gnustep/ProgressStripes.svg',
         'Applications/Artwork/Fonts/TeXGyreHeros/GUST-FONT-LICENSE.txt',
         *['OS/Linux/usr/NextSpace/bin/' + name for name in LAUNCHERS]])


def build(repo, work, output, version, maintainer, dependency):
    subprocess.run(['dpkg', '--validate-version', version], check=True)
    if '\n' in maintainer or '\r' in maintainer:
        raise ValueError('Maintainer must be one control-field line')
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    files = source_files(repo)
    expected = {name: source_digest(path) for name, path in files.items()}
    with (work / 'dependency-build.log').open('w') as log:
        run([sys.executable, str(repo / 'Applications/Compositor/build-wlroots.py'),
             str(repo), str(dependency), '--prefix', '/' + PREFIX, '--libdir', LIBDIR, '--no-install'], log)
    metadata = json.loads((dependency / 'wlroots-build.json').read_text())
    manifest = json.loads((repo / 'Protocols/manifest.json').read_text())['wlroots']
    upstream = dependency / ('wlroots-' + manifest['version'] + '.tar.bz2')
    files['sources/' + upstream.name] = upstream
    expected['sources/' + upstream.name] = manifest['sha256']
    assert all(source_digest(path) == expected[name] for name, path in files.items()), 'Build inputs changed'
    key = hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest()[:16]
    build_root = work / key
    source = build_root / 'source'
    if not source.exists():
        snapshot_sources(files, source, expected)
    assert all(source_digest(source / name) == value for name, value in expected.items()), 'Modified source snapshot'
    stage = build_root / 'stage'
    build_dir = build_root / 'build'
    env = dict(os.environ, PKG_CONFIG_PATH=metadata['pkgconfig'])
    env.pop('LD_LIBRARY_PATH', None)
    with (build_root / 'stage-build.log').open('w') as log:
        setup = ['meson', 'setup'] + (['--reconfigure'] if build_dir.exists() else [])
        run(setup + [str(build_dir), str(source / 'Applications/Compositor'), '--wrap-mode=nodownload', '--prefix=/' + PREFIX,
            '-Dwlroots_rpath=$ORIGIN/../' + LIBDIR], log, env=env)
        run(['meson', 'compile', '-C', str(build_dir), '-j', os.environ.get('JOBS', '4')], log, env=env)
        run(['meson', 'test', '-C', str(build_dir), '--print-errorlogs'], log, env=env)
        run(['meson', 'install', '-C', metadata['build'], '--destdir', str(stage)], log, env=env)
        run(['meson', 'install', '-C', str(build_dir), '--destdir', str(stage)], log, env=env)
    architecture = subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip()
    name = f'{PACKAGE}_{version}_{architecture}'
    binary_package = output / (name + '.deb')
    source_package = output / (name + '.source.tar.gz')
    if binary_package.exists() or source_package.exists():
        raise FileExistsError('Package output already exists: ' + name)
    with tempfile.TemporaryDirectory(prefix='deb-', dir=build_root) as temporary:
        temporary = Path(temporary)
        package = temporary / PACKAGE
        private_library = 'libwlroots-' + '.'.join(manifest['version'].split('.')[:2]) + '.so'
        payload = [PREFIX + '/bin/' + name for name in ('nextspace-compositor', 'nextspace-session', *LAUNCHERS)]
        payload.append(PREFIX + '/' + LIBDIR + '/' + private_library)
        for relative in payload:
            target = package / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(stage / relative, target)
        docs = package / 'usr/share/doc' / PACKAGE
        docs.mkdir(parents=True)
        shutil.copy2(source / 'LICENSE', docs / 'LICENSE.nextspace')
        shutil.copy2(Path(metadata['source']) / 'LICENSE', docs / 'LICENSE.wlroots')
        (docs / 'build-inputs.json').write_text(json.dumps(expected, indent=2) + '\n')
        debian = temporary / 'debian'
        debian.mkdir()
        (debian / 'control').write_text(f'Source: {PACKAGE}\nSection: x11\nPriority: optional\nMaintainer: {maintainer}\n\n'
            f'Package: {PACKAGE}\nArchitecture: any\nDescription: NEXTSPACE Wayland compositor and supervisor\n')
        abi = '.'.join(manifest['version'].split('.')[:2])
        overrides = debian / 'shlibs.local'
        overrides.write_text(f'libwlroots {abi} {PACKAGE} (= {version})\n')
        dependencies = subprocess.check_output(['dpkg-shlibdeps', '-O', '-L' + str(overrides),
            '-l' + str(package / PREFIX / LIBDIR), '-x' + PACKAGE,
            *['-e' + str(package / relative) for relative in payload[:2] + payload[-1:]]],
            cwd=temporary, text=True, stderr=subprocess.PIPE).strip()
        assert dependencies.startswith('shlibs:Depends='), dependencies
        dependencies = dependencies.split('=', 1)[1] + ', dbus-daemon, swaylock (>= 1.8.2)'
        built = write_binary(package, binary_package, dict(Package=PACKAGE, Version=version, Architecture=architecture,
            Section='x11', Priority='optional', Maintainer=maintainer, Depends=dependencies),
            'NEXTSPACE Wayland compositor and supervised sessions\n'
            'Wayland compositor and session supervisor for an existing NEXTSPACE\n'
            'installation, including a private pinned wlroots library.')
        payload_hashes = built['payload_hashes']
    with tarfile.open(source_package, 'w:gz') as archive:
        inputs = source / 'build-inputs.json'
        inputs.write_text(json.dumps(expected, indent=2) + '\n')
        archive.add(inputs, arcname='nextspace/build-inputs.json')
        for relative in expected:
            archive.add(source / relative, arcname='nextspace/' + relative)
    result = dict(package=PACKAGE, version=version, architecture=architecture,
        binary=str(binary_package), binary_sha256=digest(binary_package),
        source=str(source_package), source_sha256=digest(source_package),
        build=str(build_root), dependencies=dependencies, payload_hashes=payload_hashes, inputs=expected)
    (output / (name + '.json')).write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--maintainer', default='NEXTSPACE local build <root@localhost>')
    parser.add_argument('--dependency-cache', type=Path)
    args = parser.parse_args()
    result = build(args.repo.resolve(), args.build_dir.resolve(), args.output.resolve(), args.version,
                   args.maintainer, (args.dependency_cache or args.build_dir / 'wlroots').resolve())
    print(json.dumps({key: result[key] for key in
        ('package', 'version', 'architecture', 'binary', 'binary_sha256', 'source', 'source_sha256')}, indent=2))
