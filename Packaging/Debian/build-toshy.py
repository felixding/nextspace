#!/usr/bin/env python3
"""Build the optional Toshy compatibility mapper from the upstream release."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

from common import fetch, write_binary

PACKAGE = 'nextspace-toshy'
TAG = 'Toshy_v26.11.0'
REVISION = 'c76b5ec702e188a793c542e940d4e066d838c654'
SHA256 = '6a87d489ad8b19d3b21faa1e68e94139b8d9c8f95fa722cad292d45dd675d441'
XWAYKEYZ = '3895ab4c5f29f6415cdfc66b4ad53b76db2fb090'
ARCHIVE = f'Toshy-{TAG}.tar.gz'
SOURCE = f'https://codeload.github.com/RedBearAK/Toshy/tar.gz/refs/tags/{TAG}'
PYTHON_SOURCES = (
    ('appdirs-1.4.4', 'appdirs.py',
     'https://files.pythonhosted.org/packages/d7/d8/05696357e0311f5b5c316d7b95f46c669dd9c15aaeecbb48c7d0aeb88c40/',
     '7d5d0167b2b1ba821647616af46a749d1c653740dd0d2415100fe26e27afdf41'),
    ('inotify_simple-1.3.5', 'inotify_simple.py',
     'https://files.pythonhosted.org/packages/51/41/59ca6011f5463d5e5eefcfed2e7fe470922d3a958b7f3aad95eda208d7d3/',
     '8440ffe49c4ae81a8df57c1ae1eb4b6bfa7acb830099bfb3e305b383005cc128'),
)


def build(repo, work, output, version, cache):
    subprocess.run(['dpkg', '--validate-version', version], check=True)
    work.mkdir(parents=True)
    cache.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    archive = fetch(repo, cache, ARCHIVE, SOURCE, SHA256)
    stage = work / 'stage'
    package_dir = stage / 'usr/NextSpace/libexec/nextspace-toshy'
    package_dir.mkdir(parents=True)
    with tarfile.open(archive) as source:
        source.extractall(work, filter='data')
    upstream = work / f'Toshy-{TAG}'
    vendored = upstream / 'vendors/xwaykeyz-main'
    if f'sha={XWAYKEYZ}' not in (vendored / '.vendored-ref').read_text().splitlines():
        raise ValueError('Toshy archive does not contain the pinned xwaykeyz revision')
    upstream.rename(package_dir / 'upstream')
    modules = package_dir / 'python'
    modules.mkdir()
    for distribution, module, url, checksum in PYTHON_SOURCES:
        filename = distribution + '.tar.gz'
        with tarfile.open(fetch(repo, cache, filename, url + filename, checksum)) as source:
            source.extractall(work, filter='data')
        shutil.copyfile(work / distribution / module, modules / module)
        license_file = next((work / distribution).glob('LICENSE*'))
        shutil.copyfile(license_file, modules / (distribution + '-LICENSE'))
    local = repo / 'Libraries/Toshy'
    for name in ('configuration.py', 'nextspace-toshy'):
        shutil.copyfile(local / name, package_dir / name)
    (package_dir / PACKAGE).chmod(0o755)
    bin_dir = stage / 'usr/NextSpace/bin'
    bin_dir.mkdir()
    (bin_dir / PACKAGE).symlink_to(f'../libexec/{PACKAGE}/{PACKAGE}')
    docs = stage / 'usr/share/doc' / PACKAGE
    docs.mkdir(parents=True)
    pin = dict(tag=TAG, revision=REVISION, sha256=SHA256, url=SOURCE, xwaykeyz=XWAYKEYZ,
               python={name: checksum for name, _, _, checksum in PYTHON_SOURCES})
    (docs / 'upstream.json').write_text(json.dumps(pin, indent=2) + '\n')
    shutil.copyfile(repo / 'docs/Toshy-Keyboard-Shortcuts.md', docs / 'README.md')
    dependencies = ('nextspace-wayland-compositor, gnustep-base-runtime, python3, python3-dbus, '
                    'python3-evdev, python3-gi, gir1.2-glib-2.0, python3-i3ipc, '
                    'python3-ordered-set, python3-psutil, '
                    'python3-pywayland, python3-watchdog, python3-xkbcommon')
    name = f'{PACKAGE}_{version}_all'
    result = write_binary(stage, output / (name + '.deb'), dict(
        Package=PACKAGE, Version=version, Architecture='all', Section='utils', Priority='optional',
        Maintainer='NEXTSPACE local build <root@localhost>', Depends=dependencies),
        'Toshy shortcut compatibility for NEXTSPACE Wayland\n'
        'Uses the bundled xwaykeyz mapper and private keyboard focus context.')
    (output / (name + '.json')).write_text(json.dumps(dict(result, upstream=pin), indent=2) + '\n')
    return result['binary']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    print(build(args.repo.resolve(), args.build_dir.resolve(), args.output.resolve(),
                args.version, args.cache.resolve()))
