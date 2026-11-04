#!/usr/bin/env python3
"""Build the pinned native Wayland desktop in a fresh container."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

from common import digest, fetch, source_digest, source_files, snapshot_sources
from desktop import CORE, assemble

SOURCE_DIRS = ('Applications', 'Frameworks', 'Libraries/gnustep', 'Libraries/libcorefoundation',
    'OS/Linux', 'Packaging/Debian', 'Packaging/Sources', 'Packaging/Patches', 'Protocols', 'Tests/Wayland', 'Tests/GNUstep-GUI')


def build(repo, work, output, version, maintainer):
    if not Path('/.dockerenv').is_file() or os.geteuid() != 0 or os.environ.get('NEXTSPACE_DESKTOP_BUILD_DISPOSABLE') != '1':
        raise RuntimeError('Use a fresh root Docker builder with NEXTSPACE_DESKTOP_BUILD_DISPOSABLE=1')
    if Path('/usr/NextSpace').exists():
        raise RuntimeError('The desktop builder must start without an installed NEXTSPACE prefix')
    subprocess.run(['dpkg', '--validate-version', version], check=True)
    work.mkdir(parents=True)
    output.mkdir(parents=True, exist_ok=True)
    cache = work / 'archives'; cache.mkdir()
    files = source_files(repo, SOURCE_DIRS, ['LICENSE'])
    native = json.loads((repo / 'Tests/Wayland/native-stack-sources.json').read_text())
    for name, package in native.items():
        relative = 'sources/native/' + name + '.tar.gz'
        files[relative] = fetch(repo, cache, relative,
            'https://codeload.github.com/' + package['repository'] + '/tar.gz/' + package['revision'], package['sha256'])
    manifest = json.loads((repo / 'Protocols/manifest.json').read_text())
    for archive in manifest['macutils']['archives']:
        relative = 'sources/' + archive['name']
        files[relative] = fetch(repo, cache, relative, archive['source'], archive['sha256'])
    portal = manifest['desktop_portal']
    relative = 'sources/xdg-desktop-portal-wlr-' + portal['version'] + '.tar.gz'
    files[relative] = fetch(repo, cache, relative, portal['source'], portal['sha256'])
    gui = manifest['gnustep_gui']
    files['sources/gui.tar.gz'] = fetch(repo, cache, 'sources/gui.tar.gz',
        'https://codeload.github.com/gnustep/libs-gui/tar.gz/' + gui['commit'], gui['sha256'])
    wlroots = manifest['wlroots']
    relative = 'sources/wlroots-' + wlroots['version'] + '.tar.bz2'
    files[relative] = fetch(repo, cache, relative, wlroots['source'], wlroots['sha256'])
    expected = {name: source_digest(path) for name, path in sorted(files.items())}
    snapshot = work / 'source'
    snapshot_sources(files, snapshot, expected)
    inputs = snapshot / 'build-inputs.json'
    inputs.write_text(json.dumps(expected, indent=2) + '\n')
    runtime = work / 'runtime'
    env = dict(os.environ)
    for key in ('LD_LIBRARY_PATH', 'GNUSTEP_CONFIG_FILE', 'GNUSTEP_MAKEFILES', 'NEXTSPACE_STAGE_ROOT'):
        env.pop(key, None)
    with (work / 'runtime-build.log').open('w') as log:
        subprocess.run(['sh', str(snapshot / 'Packaging/Sources/build-native-runtime.sh'), str(runtime)],
            env=env, stdout=log, stderr=log, check=True)
    assert all(source_digest(snapshot / name) == value for name, value in expected.items()), 'Source snapshot changed'
    docs = runtime / 'stage/usr/share/doc' / CORE
    docs.mkdir(parents=True)
    shutil.copy2(snapshot / 'LICENSE', docs / 'LICENSE.nextspace')
    shutil.copy2(inputs, docs / 'build-inputs.json')
    licenses = docs / 'upstream-licenses'; licenses.mkdir()
    for name, directory in [('gui', runtime / 'gui'), *[(name, runtime / 'native-sources' / name) for name in native]]:
        for path in directory.iterdir():
            if path.is_file() and path.name.upper().startswith(('LICENSE', 'COPYING', 'COPYRIGHT')):
                shutil.copy2(path, licenses / (name + '-' + path.name))
    shutil.copy2(runtime / 'macutils/licenses/copyright', licenses / 'macutils-copyright')
    packages = assemble(snapshot, runtime / 'stage', runtime / 'stage-wayland',
        work / 'assembled', output, version, maintainer)
    with (work / 'compositor-build.log').open('w') as log:
        subprocess.run([sys.executable, str(snapshot / 'Packaging/Debian/build-wayland.py'), '--repo', str(snapshot),
            '--build-dir', str(work / 'compositor'), '--output', str(output), '--version', version, '--maintainer', maintainer],
            env=env, stdout=log, stderr=log, check=True)
    source = output / ('nextspace-desktop_' + version + '.source.tar.gz')
    if source.exists():
        raise FileExistsError(source)
    with tarfile.open(source, 'w:gz') as archive:
        archive.add(inputs, arcname='nextspace/build-inputs.json')
        for relative in expected:
            archive.add(snapshot / relative, arcname='nextspace/' + relative)
    result = dict(version=version, inputs=expected, packages=packages, source=str(source),
        source_sha256=digest(source), build=str(work), compositor_receipt=str(output /
            ('nextspace-wayland-compositor_' + version + '_' + packages[0]['architecture'] + '.json')),
        source_replay_verified=False, full_plan_complete=False)
    (output / ('nextspace-desktop_' + version + '.json')).write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--maintainer', default='NEXTSPACE local build <root@localhost>')
    args = parser.parse_args()
    result = build(args.repo.resolve(), args.build_dir.resolve(), args.output.resolve(), args.version, args.maintainer)
    print(json.dumps({key: result[key] for key in ('version', 'source', 'source_sha256')}, indent=2))
