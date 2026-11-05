"""Real D-Bus activation checks for native supervisor cases."""
import ast
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import time


def prepare(artifacts):
    directory = artifacts / 'activation'
    services = directory / 'data/dbus-1/services'
    services.mkdir(parents=True)
    source = Path(__file__).with_name('session-activation-probe.c')
    probe = directory / 'session-activation-probe'
    flags = subprocess.check_output(['pkg-config', '--cflags', '--libs', 'gio-2.0'], text=True).split()
    subprocess.run(['cc', '-std=c11', str(source), '-o', str(probe), *flags], check=True)
    (services / 'org.nextspace.ValidationEnvironment.service').write_text(
        '[D-BUS Service]\nName=org.nextspace.ValidationEnvironment\nExec=' + shlex.quote(str(probe.resolve())) + ' --stubborn\n')
    (directory / 'metadata.json').write_text(json.dumps(dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        probe_sha256=hashlib.sha256(probe.read_bytes()).hexdigest()), indent=2) + '\n')
    return dict(XDG_DATA_HOME=str((directory / 'data').resolve()))


def check(environment, artifacts, inherited_marker, runtime):
    actual = subprocess.check_output(['gdbus', 'call', '--session', '--dest', 'org.nextspace.ValidationEnvironment',
        '--object-path', '/org/nextspace/ValidationEnvironment',
        '--method', 'org.nextspace.ValidationEnvironment.GetEnvironment'],
        env=dict(os.environ, DBUS_SESSION_BUS_ADDRESS=environment['DBUS_SESSION_BUS_ADDRESS']), text=True, timeout=10)
    value = ast.literal_eval(actual)[0]
    for name in ('NEXTSPACE_SESSION_ID', 'WAYLAND_DISPLAY', 'DBUS_SESSION_BUS_ADDRESS'):
        assert value[name] == environment[name], (name, value, environment)
    assert value['NEXTSPACE_GS_BACKEND'] == value['XDG_SESSION_TYPE'] == 'wayland', value
    assert value['XDG_SESSION_DESKTOP'] == 'NextSpace' and value['XDG_CURRENT_DESKTOP'] == 'NEXTSPACE'
    assert value['DESKTOP_SESSION'] == 'nextspace-wayland' and value['DBUS_STARTER_BUS_TYPE'] == 'session'
    assert value['XDG_SESSION_CLASS'] == 'user'
    assert value['XCURSOR_THEME'] == (os.environ.get('XCURSOR_THEME') or 'NextSpace'), value
    assert value['XDG_RUNTIME_DIR'] == runtime, value
    assert (Path(runtime) / value['WAYLAND_DISPLAY']).is_socket(), value
    for name in ('XAUTHORITY', 'WAYLAND_SOCKET', 'NEXTSPACE_SHELL_SOCKET', 'GREETD_SOCK'): assert name not in value, value
    assert 'DISPLAY' not in value, value
    assert str(inherited_marker.resolve()) not in value['OPEN_FDS'], value
    (artifacts / 'activation/results.json').write_text(json.dumps(value, indent=2) + '\n')
    return int(value['PROBE_PID'])


def failures(supervisor, compositor, shell_probe, env, artifacts):
    for program, hang in (('dbus-daemon', False), ('dbus-update-activation-environment', False),
                          ('dbus-update-activation-environment', True)):
        directory = artifacts / ('failed-' + program + ('-timeout' if hang else ''))
        directory.mkdir()
        if hang:
            script = directory / program
            script.write_text('#!/bin/sh\nsleep 60 &\nprintf "%s\\n" "$!" > ' +
                              shlex.quote(str((directory / 'child-pid').resolve())) + '\nwait\n')
            script.chmod(0o700)
        else:
            (directory / program).symlink_to('/bin/false')
        started = time.monotonic()
        result = subprocess.run([supervisor, '--private-bus', '--compositor', compositor, '--', shell_probe],
            env=dict(env, PATH=str(directory.resolve()) + ':' + env['PATH']), capture_output=True, timeout=15)
        (directory / 'stderr.log').write_bytes(result.stderr)
        assert result.returncode == 1 and b'"event":"ready"' not in result.stdout, result.stdout
        expected = b'Cannot start a private D-Bus session' if program == 'dbus-daemon' else b'Cannot publish'
        assert expected in result.stderr, result.stderr
        assert not list(Path(env['XDG_RUNTIME_DIR']).glob('nextspace-bus-*')), 'Failed startup left a private bus directory'
        if hang:
            assert b'publication timed out' in result.stderr and time.monotonic() - started < 12
            pid = int((directory / 'child-pid').read_text())
            assert not Path(f'/proc/{pid}').exists(), 'Timed-out publisher descendant escaped cleanup'
