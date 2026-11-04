#!/usr/bin/env python3
"""Install, upgrade and remove the compositor package beside an X11 reference."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import select
import shlex
import socket
import subprocess
import tempfile
import time

from integration import until
from gnustep import process_runtime

PACKAGE = 'nextspace-wayland-compositor'


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


def fallback(workspace, probe, candidate, artifacts, launcher=None, pasteboard_probe=None):
    artifacts.mkdir()
    home = artifacts / 'nextspace-x11-profile'
    home.mkdir(mode=0o700)
    env = dict(os.environ)
    if candidate:
        library = artifacts / 'system-library'
        (library / 'Preferences').mkdir(parents=True)
        config_source = Path(env.get('GNUSTEP_CONFIG_FILE', '/Library/Preferences/GNUstep.conf')).read_text()
        setting = next(line.split('=', 1)[1] for line in config_source.splitlines()
                       if line.startswith('GNUSTEP_SYSTEM_LIBRARY='))
        original = Path(shlex.split(setting, comments=True)[0])
        for entry in original.iterdir():
            if entry.name not in ('Preferences', 'Frameworks', 'Bundles', 'Themes', 'Images'):
                (library / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())
        for entry in (original / 'Preferences').glob('*'):
            (library / 'Preferences' / entry.name).symlink_to(entry)
        for name, target in (('Frameworks', candidate / 'Frameworks'),
                ('Images', candidate / 'Frameworks/DesktopKit.framework/Resources/Images'),
                ('Bundles/libgnustep-x11-032.bundle', candidate / 'libgnustep-x11-032.bundle'),
                ('Themes/NextSpace.theme', candidate / 'NextSpace.theme')):
            path = library / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(target, target_is_directory=True)
        config = artifacts / 'GNUstep.conf'
        config.write_text(config_source + '\nGNUSTEP_USER_CONFIG_FILE=\nGNUSTEP_SYSTEM_LIBRARY=' + str(library) + '\n')
        env.update(GNUSTEP_CONFIG_FILE=str(config),
                   LD_LIBRARY_PATH=str(candidate / 'lib') + ':/usr/NextSpace/lib:/usr/local/lib')
    name = 'nextspace-x11'
    try: pwd.getpwnam(name)
    except KeyError: pass
    else: raise RuntimeError('Reserved test account already exists')
    subprocess.run(['useradd', '--no-create-home', '--home-dir', str(home), '--shell', '/usr/sbin/nologin', name], check=True)
    account = pwd.getpwnam(name)
    results = artifacts / 'results'
    results.mkdir()
    os.chown(home, account.pw_uid, account.pw_gid)
    os.chown(results, account.pw_uid, account.pw_gid)
    bus = None
    try:
        with (artifacts / 'bus.log').open('w') as log:
            bus = subprocess.Popen(['dbus-daemon', '--system', '--nofork', '--nopidfile',
                '--address=unix:path=' + str(artifacts / 'bus')], stdout=log, stderr=log)
        until(lambda: (artifacts / 'bus').exists(), 'owned X11 reference bus')
        env['DBUS_SYSTEM_BUS_ADDRESS'] = 'unix:path=' + str(artifacts / 'bus')
        with (artifacts / 'run.log').open('w') as log:
            subprocess.run(['python3', str(Path(__file__).with_name('x11-workspace.py')),
                '--workspace', str(workspace), '--probe', str(probe), '--user', name,
                '--artifacts', str(results),
                *(['--launcher', str(launcher)] if launcher else []),
                *(['--pasteboard-probe', str(pasteboard_probe)] if pasteboard_probe else [])],
                env=env, stdout=log, stderr=log, check=True)
        assert len(json.loads((results / 'results.json').read_text())['passed']) == 8
    finally:
        if bus and bus.poll() is None: bus.terminate(); bus.wait(timeout=5)
        subprocess.run(['pkill', '-TERM', '-u', name], check=False)
        time.sleep(0.2)
        subprocess.run(['pkill', '-KILL', '-u', name], check=False)
        subprocess.run(['userdel', name], check=True)
        (artifacts / 'cleanup.json').write_text(json.dumps(dict(account_removed=True,
            bus_reaped=bus is None or bus.poll() is not None), indent=2) + '\n')


def native(probe, artifacts, during_upgrade=None):
    artifacts.mkdir()
    binary = Path('/usr/NextSpace/bin/nextspace-compositor')
    library = '/usr/NextSpace/lib/nextspace-wayland/libwlroots-0.18.so'
    with tempfile.TemporaryDirectory(prefix='nextspace-package-runtime-') as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS='headless',
                   WLR_HEADLESS_OUTPUTS='2', WLR_RENDERER='pixman')
        for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET', 'LD_LIBRARY_PATH'): env.pop(key, None)
        control, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        control.settimeout(5)
        with (artifacts / 'compositor.log').open('w') as log:
            server = subprocess.Popen([str(binary), '-x', '-c', str(child.fileno())], env=env,
                pass_fds=[child.fileno()], stdout=subprocess.PIPE, stderr=log, text=True)
        child.close()
        client = None
        def command(value):
            control.sendall(value.encode())
            return json.loads(control.recv(65536))
        try:
            assert select.select([server.stdout], [], [], 10)[0]
            line = server.stdout.readline().strip()
            assert line.startswith('WAYLAND_DISPLAY='), line
            env['WAYLAND_DISPLAY'] = line.split('=', 1)[1]
            mapped = process_runtime(server.pid)
            assert library in mapped['libraries'], mapped
            (artifacts / 'runtime.json').write_text(json.dumps(mapped, indent=2) + '\n')
            until(lambda: command('x-display')['ready'], 'packaged managed Xwayland')
            with (artifacts / 'client.log').open('w') as log:
                client = subprocess.Popen([str(probe), '--small-fullscreen', 'PackagedNative'], env=env, stdout=log, stderr=log)
            def window():
                assert client.poll() is None
                return next((w for w in command('windows') if w['title'] == 'PackagedNative'), None)
            window_state = until(window, 'packaged native protocol window')
            assert not window_state['legacy'] and window_state['fullscreen']
            head = next(o['name'] for o in command('outputs') if o['x'] <= window_state['x'] < o['x'] + o['width'])
            records = []
            for phase in ('before', 'after') if during_upgrade else ('current',):
                if phase == 'after':
                    identity = window()['id']
                    during_upgrade()
                    assert server.poll() is None and window()['id'] == identity
                    (artifacts / 'maps-after-upgrade.txt').write_text(Path(f'/proc/{server.pid}/maps').read_text())
                for scale in (120, 150, 180, 210, 240):
                    assert command(f'test-scale {head} {scale} 10000')['ok']
                    assert command('confirm')['ok']
                    output = next(o for o in command('outputs') if o['name'] == head)
                    until(lambda: (window()['x'], window()['y']) ==
                        (output['x'] + (output['width'] - 64) // 2, output['y'] + (output['height'] - 64) // 2),
                        'packaged fullscreen placement after density change')
                    records.append(dict(scale=scale, phase=phase, window=window()))
            assert command(f"close {window()['id']}")['ok']
            client.wait(timeout=5)
            assert client.returncode == 0
            (artifacts / 'results.json').write_text(json.dumps(records, indent=2) + '\n')
        finally:
            if client and client.poll() is None: client.terminate(); client.wait(timeout=5)
            if server.poll() is None: command('quit'); server.wait(timeout=5)
            server.stdout.close(); control.close()
        assert server.returncode == 0
        with (artifacts / 'session.log').open('w') as log:
            subprocess.run(['/usr/NextSpace/bin/nextspace-wayland-session', '--compositor', str(binary),
                '--', '/bin/true'], env=env, stdout=log, stderr=log, check=True, timeout=20)
        owned = []
        for process in Path('/proc').iterdir():
            if not process.name.isdigit(): continue
            try:
                if ('XDG_RUNTIME_DIR=' + runtime).encode() in (process / 'environ').read_bytes().split(b'\0'):
                    owned.append(int(process.name))
            except (FileNotFoundError, PermissionError, ProcessLookupError): pass
        assert not owned, owned


def run(packages, workspace, workspace_probe, candidate, native_probe, artifacts):
    if not Path('/.dockerenv').exists() or os.geteuid() != 0 or os.environ.get('NEXTSPACE_PACKAGE_TEST_DISPOSABLE') != '1':
        raise RuntimeError('Use a fresh disposable container with NEXTSPACE_PACKAGE_TEST_DISPOSABLE=1')
    artifacts.mkdir(parents=True)
    for package in packages:
        assert subprocess.check_output(['dpkg-deb', '-f', str(package), 'Package'], text=True).strip() == PACKAGE
    versions = [subprocess.check_output(['dpkg-deb', '-f', str(p), 'Version'], text=True).strip() for p in packages]
    subprocess.run(['dpkg', '--compare-versions', versions[0], 'lt', versions[1]], check=True)
    installed = subprocess.run(['dpkg-query', '-W', '-f=${Status}', PACKAGE], capture_output=True, text=True)
    assert 'install ok installed' not in installed.stdout
    paths = [Path('/usr/share/xsessions'), Path('/etc/greetd/config.toml'), Path('/etc/systemd/system/display-manager.service'),
             Path('/usr/local/lib/libwlroots-0.18.so')]
    if candidate: paths.append(candidate)
    before = snapshot(paths)
    (artifacts / 'fallback-before.json').write_text(json.dumps(before, indent=2) + '\n')
    fallback(workspace, workspace_probe, candidate, artifacts / 'before')
    def install(index, name):
        with (artifacts / (name + '.log')).open('w') as log:
            subprocess.run(['apt-get', '-y', '--no-install-recommends', 'install', str(packages[index])],
                env=dict(os.environ, DEBIAN_FRONTEND='noninteractive'), stdout=log, stderr=log, check=True)
        assert subprocess.check_output(['dpkg-query', '-W', '-f=${Version}', PACKAGE], text=True) == versions[index]
        assert snapshot(paths) == before, 'Package changed the X11 reference'
    install(0, 'installed')
    fallback(workspace, workspace_probe, candidate, artifacts / 'installed-x11')
    native(native_probe, artifacts / 'installed-native', during_upgrade=lambda: install(1, 'upgraded'))
    native(native_probe, artifacts / 'upgraded-native')
    fallback(workspace, workspace_probe, candidate, artifacts / 'upgraded-x11')
    with (artifacts / 'removed.log').open('w') as log:
        subprocess.run(['dpkg', '--remove', PACKAGE], stdout=log, stderr=log, check=True)
    assert not Path('/usr/NextSpace/bin/nextspace-compositor').exists()
    assert not Path('/usr/NextSpace/lib/nextspace-wayland/libwlroots-0.18.so').exists()
    assert snapshot(paths) == before
    fallback(workspace, workspace_probe, candidate, artifacts / 'removed-x11')
    (artifacts / 'results.json').write_text(json.dumps(dict(versions=versions, installed=True, upgraded=True,
        removed=True, live_upgrade=True, x11_groups=32, native_density_checks=15, x11_reference_unchanged=True), indent=2) + '\n')
    print('Debian install/live-upgrade/remove, private runtime, native placement15 and X11 workflow32 checks: PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packages', type=Path, nargs=2, required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--workspace-probe', type=Path, required=True)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--native-probe', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    run(args.packages, args.workspace, args.workspace_probe, args.candidate, args.native_probe, args.artifacts)
