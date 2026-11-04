"""Assemble the native Wayland runtime and session packages."""
from pathlib import Path
import re
import plistlib
import shutil
import subprocess
import tempfile

from common import write_binary

CORE = 'nextspace-runtime'
WAYLAND = 'nextspace-session-wayland'
LOADER_PATH = '/usr/NextSpace/lib:/Library/Libraries'


def elf_files(root):
    for path in sorted(root.rglob('*')):
        if path.is_file() and not path.is_symlink():
            with path.open('rb') as stream:
                if stream.read(4) == b'\x7fELF':
                    yield path


def copy_stage(source, target):
    shutil.copytree(source, target, symlinks=True)


def dependencies(root, siblings, package, version, maintainer):
    libraries = {}
    directories = set()
    for name, tree in siblings.items():
        for path in elf_files(tree):
            directories.add(str(path.parent))
            dynamic = subprocess.check_output(['readelf', '-d', str(path)], text=True)
            match = re.search(r'\(SONAME\).*?\[([^\]]+)\]', dynamic)
            if not match:
                continue
            soname = re.fullmatch(r'(.+)\.so\.(.+)', match[1])
            if soname:
                key = (soname[1], soname[2])
                if key in libraries and libraries[key] != name:
                    raise ValueError('Duplicate packaged library: ' + match[1])
                libraries[key] = name
    with tempfile.TemporaryDirectory(prefix='nextspace-shlibs-') as directory:
        temporary = Path(directory)
        debian = temporary / 'debian'; debian.mkdir()
        (debian / 'control').write_text(f'Source: {package}\nSection: x11\nPriority: optional\nMaintainer: {maintainer}\n\n'
            f'Package: {package}\nArchitecture: any\nDescription: NEXTSPACE desktop\n')
        overrides = debian / 'shlibs.local'
        overrides.write_text(''.join(f'{library} {abi} {owner} (= {version})\n'
            for (library, abi), owner in sorted(libraries.items())))
        command = ['dpkg-shlibdeps', '-O', '-L' + str(overrides), '-x' + package]
        command += ['-l' + value for value in sorted(directories)]
        command += ['-e' + str(path) for path in elf_files(root)]
        result = subprocess.run(command, cwd=temporary, text=True, capture_output=True)
        (root.parent / (package + '-shlibdeps.log')).write_text(result.stdout + result.stderr)
        result.check_returncode()
        assert result.stdout.startswith('shlibs:Depends='), result.stdout
        return result.stdout.strip().split('=', 1)[1]


def assemble(repo, stage, wayland_stage, work, output, version, maintainer):
    """Assemble only in a new directory; installation belongs to disposable tests."""
    subprocess.run(['dpkg', '--validate-version', version], check=True)
    work.mkdir(parents=True)
    output.mkdir(parents=True, exist_ok=True)
    trees = {name: work / name for name in (CORE, WAYLAND)}
    for source, name in ((stage, CORE), (wayland_stage, WAYLAND)):
        copy_stage(source, trees[name])
    core, wayland = (trees[name] for name in (CORE, WAYLAND))
    # The profile helper is built from Workspace's shared connection but belongs
    # to the optional native desktop, alongside its backend and pasteboard tool.
    for name in ('nextspace-display-profile', 'nextspace-screencast-chooser', 'nextspace-session-hook'):
        helper = Path('usr/NextSpace/bin') / name
        (wayland / helper).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(core / helper, wayland / helper)
    for relative in ('usr/NextSpace/share/nextspace-wayland/portal/nextspace-wlr.conf',
                     'usr/share/xdg-desktop-portal/nextspace-portals.conf',
                     'usr/share/xdg-desktop-portal/portals/nextspace-wlr.portal'):
        target = wayland / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / 'OS/Linux' / relative, target)
    entry = 'usr/share/wayland-sessions/nextspace.desktop'
    target = wayland / entry
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(repo / 'OS/Linux' / entry, target)
    preferences = core / 'Library/Preferences'
    preferences.mkdir(parents=True, exist_ok=True)
    defaults = plistlib.loads((repo / 'Libraries/gnustep/GlobalDefaults.plist').read_bytes())
    defaults['GSBackend'] = 'wayland'
    (preferences / 'GlobalDefaults.plist').write_bytes(plistlib.dumps(defaults, sort_keys=False))
    images = core / 'Library/Images'; images.mkdir(parents=True, exist_ok=True)
    shutil.copy2(core / 'Library/Themes/NextSpace.theme/Resources/ThemeImages/common_Tile.tiff', images / 'common_Tile.tiff')
    fonts = core / 'etc/fonts/conf.d/25-nextspace-fonts.conf'
    fonts.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(repo / 'OS/Linux/etc/fonts/conf.d/25-nextspace-fonts.conf', fonts)
    # Prefix libraries resolve through their own ELF search paths. Leave the
    # distribution's loader configuration and GNUstep runtime in place.
    for path in (core / 'etc/ld.so.conf.d').glob('*'):
        path.unlink()
    for tree in trees.values():
        for binary in elf_files(tree):
            subprocess.run(['patchelf', '--set-rpath', LOADER_PATH, str(binary)], check=True)
    architecture = subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip()
    results = []
    for name, tree in trees.items():
        depends = dependencies(tree, trees, name, version, maintainer)
        extra = ('fonts-dejavu-core, fonts-noto-cjk, xcursor-themes, unzip, arj, lhasa, macutils' if name == CORE else
            f'{CORE} (= {version}), nextspace-wayland-compositor (= {version}), adwaita-icon-theme, '
            'xdg-desktop-portal (>= 1.20), pipewire (>= 1.4), wireplumber (>= 0.5)')
        depends = ', '.join(dict.fromkeys(part.strip() for value in (depends, extra) for part in value.split(',') if part.strip()))
        description = {CORE: 'NEXTSPACE shared toolkit, frameworks and applications',
            WAYLAND: 'NEXTSPACE native Wayland desktop backend and session'}[name]
        output_file = output / f'{name}_{version}_{architecture}.deb'
        result = write_binary(tree, output_file, dict(Package=name, Version=version, Architecture=architecture,
            Section='x11', Priority='optional', Maintainer=maintainer, Depends=depends), description,
            ['/Library/Preferences/GNUstep.conf', '/Library/Preferences/GlobalDefaults.plist',
             '/etc/fonts/conf.d/25-nextspace-fonts.conf'] if name == CORE else ())
        results.append(dict(result, package=name, version=version, architecture=architecture, dependencies=depends))
    return results
