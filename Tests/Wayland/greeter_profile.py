#!/usr/bin/env python3
"""Restore real greeter profiles before the supervised Login panel starts."""
import argparse
import array
import json
import os
from pathlib import Path
import plistlib
import pwd
import select
import signal
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid

from gnustep import private_defaults
from integration import until
from login_greeter import at_density
from workspace_power_session import descendants
from PIL import Image
from login_artwork import check_panel


def run(compositor, supervisor, helper, application, artifacts):
    assert os.geteuid() == 0 and Path('/.dockerenv').exists(), 'Use a disposable root Docker container'
    artifacts.mkdir(parents=True)
    home = artifacts / 'nextspace-greeter-home'
    home.mkdir(mode=0o700)
    name = 'nextspace-profile-' + uuid.uuid4().hex[:8]
    subprocess.run(['useradd', '--no-create-home', '--home-dir', str(home), '--shell', '/usr/sbin/nologin', name], check=True)
    account = pwd.getpwnam(name)
    os.chown(home, account.pw_uid, account.pw_gid)
    identity = dict(user=account.pw_uid, group=account.pw_gid, extra_groups=[])
    runtime = Path(tempfile.mkdtemp(prefix='nsgp-')); os.chown(runtime, account.pw_uid, account.pw_gid)
    env = dict(os.environ, HOME=str(home), USER=name, LOGNAME=name, XDG_RUNTIME_DIR=str(runtime),
        WLR_BACKENDS='headless', WLR_HEADLESS_OUTPUTS='2', WLR_RENDERER='pixman',
        NEXTSPACE_GS_BACKEND='wayland', XDG_SESSION_CLASS='greeter', GREETD_SOCK=str(home / 'unused-auth'))
    for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET', 'NEXTSPACE_SHELL_SOCKET'): env.pop(key, None)
    private_defaults(env, home)
    os.chown(env['GNUSTEP_CONFIG_FILE'], account.pw_uid, account.pw_gid)
    candidate = artifacts / 'candidate/bin'; candidate.mkdir(parents=True)
    (candidate / 'nextspace-compositor').symlink_to(compositor)
    relay = artifacts / 'relay.sh'
    relay.write_text('#!/bin/sh\nexec /usr/bin/python3 ' + shlex.quote(str(Path(__file__).with_name('login_native_pam.py'))) +
        ' --relay ' + shlex.quote(str(artifacts)) + ' "$@"\n'); relay.chmod(0o755)
    profile = home / 'Library/Preferences/.NextSpace/WaylandDisplays.plist'
    rows = []

    def save(scale):
        control, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        broker, private = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        control.settimeout(5)
        with (artifacts / ('save-' + str(scale) + '.log')).open('w') as log:
            server = subprocess.Popen([str(compositor), '-c', str(child.fileno()), '-S', str(private.fileno())],
                pass_fds=[child.fileno(), private.fileno()], env=env, stdout=subprocess.PIPE, stderr=log, **identity)
        child.close(); private.close()
        def command(value): control.sendall(value.encode()); return json.loads(control.recv(65536))
        try:
            assert select.select([server.stdout], [], [], 10)[0]
            assert server.stdout.readline().startswith(b'WAYLAND_DISPLAY=')
            heads = command('outputs')
            for index, head in enumerate(heads):
                assert command(f"test-scale {head['name']} {scale} 10000")['ok']; assert command('confirm')['ok']
                assert command(f"output-position {head['name']} {(-1280 if index == 0 else 0)} {-100 if index == 0 else 0}")['ok']
            endpoint, client = socket.socketpair()
            broker.sendmsg([b'C'], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', [endpoint.fileno()]))])
            endpoint.close()
            with (artifacts / ('save-helper-' + str(scale) + '.log')).open('w') as log:
                result = subprocess.run([str(helper), '--save', '--nextspace-shell-fd', str(client.fileno())],
                    pass_fds=[client.fileno()], env=dict(env, NEXTSPACE_SESSION_ID='test-profile-save-' + uuid.uuid4().hex),
                    stdout=subprocess.PIPE, stderr=log, check=True, timeout=15, **identity)
            client.close()
            saved = profile.read_bytes()
            (artifacts / ('saved-' + str(scale) + '.xml')).write_bytes(result.stdout)
            parsed = plistlib.loads(result.stdout)
            assert parsed['Schema'] == 2 and len(parsed['Layout']) == 2
            assert all('Properties' not in head for head in parsed['Layout'])
            return saved, command('outputs'), parsed
        finally:
            if server.poll() is None: command('quit'); server.wait(timeout=5)
            server.stdout.close(); control.close(); broker.close()

    def check(label, expected, program=helper, heads=2):
        case = artifacts / label; case.mkdir()
        capture = case / 'captures'; capture.mkdir(); os.chown(capture, account.pw_uid, account.pw_gid)
        (home / 'relay.json').unlink(missing_ok=True)
        child_env = dict(env, WLR_HEADLESS_OUTPUTS=str(heads), NEXTSPACE_WAYLAND_CAPTURE_DIR=str(capture))
        started = time.monotonic()
        with (case / 'session.log').open('w') as log:
            parent = subprocess.Popen([str(supervisor), '--private-bus', '--compositor', str(relay),
                '--greeter-profile', str(program), '--', str(application), '-GSBackend', 'libgnustep-wayland',
                '-GSTheme', 'NextSpace', '-NSUseRunningCopy', 'NO'],
                env=child_env, stdout=log, stderr=log, start_new_session=True, **identity)
        control = None; row = None
        try:
            def ready():
                assert parent.poll() is None, (case / 'session.log').read_text()[-4000:]
                path = home / 'relay.json'
                return json.loads(path.read_text()) if path.exists() else None
            state = until(ready, 'supervised greeter compositor relay')
            helper_seconds = None
            if label == 'hung-helper':
                marker = home / 'hanging-helper.json'
                timing = until(lambda: json.loads(marker.read_text()) if marker.exists() else None,
                    'hanging display helper startup')
                descriptor = os.pidfd_open(timing['pid'])
                try:
                    assert select.select([descriptor], [], [], 12)[0], 'Display helper exceeded its deadline'
                    # The supervisor's deadline starts at fork, before Python
                    # initialization and this fixture's deliberately late marker.
                    helper_seconds = time.clock_gettime(time.CLOCK_BOOTTIME) - timing['started']
                    assert 9.5 <= helper_seconds < 11.5, helper_seconds
                finally:
                    os.close(descriptor)
            control = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET); control.settimeout(5); control.connect(state['control'])
            def command(value): control.sendall(value.encode()); return json.loads(control.recv(65536))
            def window():
                assert parent.poll() is None
                outputs = command('outputs')
                windows = command('windows')
                (case / 'last-state.json').write_text(json.dumps(dict(outputs=outputs, windows=windows), indent=2) + '\n')
                for w in windows:
                    if w['style'] == 0 and w['visible'] and w['width'] > 300 and at_density(w, expected) and any(
                        (w['x'], w['y']) == (h['x'] + (h['width'] - w['width']) // 2,
                         # AppKit floors the bottom-left origin; the top-left
                         # conversion therefore rounds the vertical half upward.
                         h['y'] + (h['height'] - w['height'] + 1) // 2) for h in outputs): return w
            w = until(window, 'Login buffer at restored density', timeout=20)
            outputs = command('outputs')
            assert all(head['scale'] == expected for head in outputs), outputs
            assert not w['legacy']
            source = capture / f"window-{w['client_id']}-{expected}.png"
            def image():
                try:
                    with Image.open(source) as picture: result = picture.copy()
                    return result if result.size == (w['buffer_width'], w['buffer_height']) else None
                except OSError: return None
            until(image, 'greeter panel pixels at restored density').save(case / 'login-panel.png')
            check_panel(case / 'login-panel.png', application.parent / 'Resources/Login.gorm', expected)
            arguments = subprocess.check_output([sys.executable, '-c',
                'from pathlib import Path; import sys; print((Path("/proc")/sys.argv[1]/"cmdline").read_bytes())', str(w['pid'])], **identity).decode()
            assert '--nextspace-shell-fd' not in arguments
            mapped = subprocess.check_output([sys.executable, '-c',
                'from pathlib import Path; import sys; print((Path("/proc")/sys.argv[1]/"maps").read_text())', str(w['pid'])], **identity)
            (case / 'login-maps.txt').write_bytes(mapped)
            (case / 'profile.plist').write_bytes(profile.read_bytes() if profile.exists() else b'')
            row = dict(case=label, scale=expected, outputs=outputs, window=w,
                preparation_seconds=time.monotonic() - started, greeter_has_no_shell_capability=True)
            if helper_seconds is not None:
                row['helper_timeout_seconds'] = helper_seconds
                row['helper_marker_delay_seconds'] = timing['published'] - timing['started']
            rows.append(row)
            (case / 'results.json').write_text(json.dumps(row, indent=2) + '\n')
        finally:
            owned = descendants(parent.pid)
            if control: control.close()
            graceful = False
            if row is not None and parent.poll() is None:
                # Use Login's normal stop signal before the supervisor reaps
                # its session. Killing a writer can leave GNUstep's directory
                # lock behind and delay the next independent profile case.
                os.kill(w['pid'], signal.SIGQUIT)
                try: graceful = parent.wait(timeout=10) == 0
                except subprocess.TimeoutExpired: pass
            if parent.poll() is None: parent.terminate(); parent.wait(timeout=10)
            until(lambda: all(not Path('/proc/' + str(pid)).exists() for pid in owned), 'supervisor reaps all greeter children')
            assert not list(runtime.glob('nextspace-bus-*'))
            if row is not None:
                assert graceful, 'Login did not stop cleanly'
                lock = home / 'defaults/.lck/.GNUstepDefaults.lck'
                assert not lock.exists(), 'Login left the defaults database locked'
                row['greeter_graceful_exit'] = True
                row['defaults_lock_released'] = True
                (case / 'results.json').write_text(json.dumps(row, indent=2) + '\n')

    try:
        for scale in (120, 150, 180, 210, 240):
            saved, outputs, original = save(scale)
            check('density-' + str(scale), scale)
            actual = rows[-1]['outputs']
            assert [(h['name'], h['x'], h['y']) for h in actual] == [(h['name'], h['x'], h['y']) for h in outputs]
        for label, data in (('malformed', b'broken profile'), ('future-schema', plistlib.dumps(dict(Schema=999, Layout=original['Layout']))),
                ('all-disabled', plistlib.dumps(dict(Schema=2, Layout=[dict(h, Active='NO') for h in original['Layout']])))):
            profile.write_bytes(data); check(label, 120)
        profile.write_bytes(saved); check('disconnected-output', 240, heads=1)
        profile.unlink(); check('missing-profile', 120)
        check('failed-helper', 120, Path('/bin/false'))
        check('missing-helper', 120, artifacts / 'missing-executable')
        hanging = artifacts / 'hanging-helper'
        hanging.write_text('#!/usr/bin/python3\nimport json, os, time\nfrom pathlib import Path\n'
            'ticks = int(Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()[19])\n'
            'started = ticks / os.sysconf("SC_CLK_TCK")\n'
            'time.sleep(1)  # Publish late to exercise startup-inclusive timing.\n'
            'target = Path(os.environ["HOME"], "hanging-helper.json")\n'
            'temporary = target.with_suffix(".tmp")\n'
            'temporary.write_text(json.dumps({"pid": os.getpid(), "started": started, "published": time.clock_gettime(time.CLOCK_BOOTTIME)}))\n'
            'temporary.replace(target)\ntime.sleep(60)\n')
        hanging.chmod(0o755)
        check('hung-helper', 120, hanging)
    finally:
        subprocess.run(['pkill', '-KILL', '-u', name], check=False)
        subprocess.run(['userdel', name], check=True)
        shutil.rmtree(runtime)
    (artifacts / 'results.json').write_text(json.dumps(dict(cases=rows, complete=True, real_pam=False,
        unprivileged_uid=account.pw_uid, account_removed=True), indent=2) + '\n')
    print('Supervised greeter profile restore, safe fallback, native buffers and cleanup: PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('compositor', 'supervisor', 'helper', 'application', 'artifacts'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    run(*[getattr(args, name).resolve() for name in ('compositor', 'supervisor', 'helper', 'application', 'artifacts')])
