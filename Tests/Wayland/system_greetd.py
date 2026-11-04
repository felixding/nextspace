#!/usr/bin/env python3
"""Opt-in installed greetd/PAM/DRM login, cancelled logout and fresh greeter test.

Run as root in an idle disposable systemd Linux guest. This temporarily creates
accounts, a greeter-only PAM service and a runtime greetd unit override, and
restores Login preferences, the disabled service and the foreground VT. The
ordinary user's PAM service remains greetd. Protocol diagnostics start only
after authentication; no password input or greeter protocol is logged.
"""
from pathlib import Path
import argparse, fcntl, hashlib, json, os, plistlib, pwd, secrets, shlex, stat, string, subprocess, sys, time, uuid

def main(args):
    assert sys.platform == 'linux' and os.geteuid() == 0
    assert Path('/run/systemd/system').is_dir(), 'Requires systemd as PID 1'
    assert 1 <= args.vt <= 63
    for path in (args.probe, args.stderr_trace, args.keyboard, args.pointer):
        assert path.exists(), path
    versions = {}
    for package in ('nextspace-runtime', 'nextspace-session-wayland', 'nextspace-wayland-compositor'):
        version = subprocess.check_output(['dpkg-query', '-W', '-f=${Version}', package], text=True)
        versions[package] = version
        if args.version:
            assert version == args.version, (package, version)
    root = args.artifacts.resolve()
    root.mkdir(parents=True)
    root.chmod(493)

    def run(args, check=True):
        return subprocess.run(args, capture_output=True, text=True, check=check, timeout=35).stdout.strip()
    assert os.geteuid() == 0 and run(['systemctl', 'is-active', 'greetd'], False) == 'inactive' and (run(['systemctl', 'is-enabled', 'greetd'], False) == 'disabled')
    assert not run(['pgrep', '-x', 'greetd'], False)
    original_pam = Path('/etc/pam.d/greetd').read_bytes()
    original = Path('/etc/greetd/config.toml').read_bytes()
    oldvt = int(Path('/sys/class/tty/tty0/active').read_text().strip()[3:])
    assert oldvt != args.vt
    token = uuid.uuid4().hex[:8]
    greeter = 'nsdm' + token
    user = greeter
    pam = Path('/etc/pam.d') / ('nextspace-greeter-' + token)
    drop = Path('/run/systemd/system/greetd.service.d/nextspace-test.conf')
    assert not pam.exists() and (not drop.exists())
    created = False
    user_created = False
    pref_written = False
    pref = Path('/usr/NextSpace/Preferences/Login')
    pref_data = None
    pref_mode = None
    started = time.time()
    result = dict(packages=versions, validation={str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__), args.probe, args.stderr_trace)})

    def user_hooks(expected):
        if not args.user_hooks:
            return None
        rows = [json.loads(line) for line in hook_log.read_text().splitlines()] if hook_log.exists() else []
        assert [row['hook'] for row in rows] == expected, rows
        for row in rows:
            assert row['uid'] == row['euid'] == user_account.pw_uid
            assert row['session_class'] == 'user' and row['session_type'] == 'wayland'
            assert row['display_unset'] and row['compositor_running']
        assert not rows or not rows[0]['workspace_running'], rows
        assert hook_profile.read_bytes() == hook_preferences
        return rows

    def exercise_login(root, greeter, account, user, secret, user_account, user_capture, probe):
        from linux_input import Input
        from integration import until

        def actor(name, uid):
            for p in Path('/proc').iterdir():
                if not p.name.isdigit():
                    continue
                try:
                    if (p / 'exe').resolve().name != name or int((p / 'status').read_text().split('Uid:')[1].split()[0]) != uid:
                        continue
                    env = dict((x.split('=', 1) for x in (p / 'environ').read_bytes().decode().split('\x00') if '=' in x))
                    return (int(p.name), env)
                except (OSError, ValueError):
                    pass
            return None
        initial = until(lambda: actor('Login', account.pw_uid), 'installed initial greeter')
        device = Input(str(args.keyboard), str(args.pointer), root)
        record = {}
        try:
            device.text(user + '\n')
            time.sleep(0.2)
            device.text(secret + '\n')
            pid, env = until(lambda: actor('Workspace', user_account.pw_uid), 'ordinary PAM login starts installed Workspace', timeout=40)
            (root / 'user-environment.json').write_text(json.dumps({k: env.get(k) for k in ('HOME', 'USER', 'LOGNAME', 'SHELL', 'GNUSTEP_CONFIG_FILE', 'XDG_RUNTIME_DIR', 'XDG_SESSION_ID')}, indent=2) + '\n')
            assert env.get('HOME') == user_account.pw_dir, (env.get('HOME'), user_account.pw_dir)
            assert env['XDG_SESSION_CLASS'] == 'user' and env['XDG_SESSION_TYPE'] == 'wayland' and ('DISPLAY' not in env) and ('GREETD_SOCK' not in env)
            assert Path(env['XDG_RUNTIME_DIR']).stat().st_uid == user_account.pw_uid
            state = run(['loginctl', 'show-session', env['XDG_SESSION_ID'], '-p', 'Type', '-p', 'Class', '-p', 'Seat', '-p', 'VTNr', '-p', 'Active'])
            assert 'Type=wayland' in state and 'Class=user' in state and ('Seat=seat0' in state) and ('VTNr=' + str(args.vt) in state) and ('Active=yes' in state)
            until(lambda: not Path('/proc/' + str(initial[0])).exists(), 'initial greeter is reaped')
            checkpoint = dict(workspace_pid=pid, user_uid=user_account.pw_uid, user_logind=state, initial_greeter_reaped=True, runtime_owner=user_account.pw_uid, display_unset=True, greetd_socket_unset=True, native_rendering_ready=False)
            (root / 'authenticated-session.json').write_text(json.dumps(checkpoint, indent=2) + '\n')
            (root / 'user-logind.txt').write_text(state + '\n')

            def native_ready():
                assert Path('/proc/' + str(pid)).exists(), 'Workspace exited before its native buffer'
                maps = Path('/proc/' + str(pid) + '/maps').read_text()
                (root / 'workspace-maps.txt').write_text(maps)
                assert 'libgnustep-x11-' not in maps, 'Workspace loaded the X11 backend'
                if 'libgnustep-wayland' not in maps:
                    return None
                from PIL import Image
                for picture in user_capture.glob('*.png'):
                    try:
                        with Image.open(picture) as image:
                            image.verify()
                        return picture
                    except (OSError, ValueError):
                        pass
                return None
            picture = until(native_ready, 'installed Workspace commits a native buffer', timeout=30)
            (root / 'workspace-first-buffer.png').write_bytes(picture.read_bytes())
            checkpoint['native_rendering_ready'] = True
            (root / 'authenticated-session.json').write_text(json.dumps(checkpoint, indent=2) + '\n')
            user_hooks(['LoginHook'])

            def query(*args):
                result = subprocess.run([str(probe), *args], env=env, user=user_account.pw_uid, group=user_account.pw_gid, extra_groups=[], cwd=user_account.pw_dir, capture_output=True, text=True, timeout=10)
                with (root / 'workspace-queries.jsonl').open('a') as log:
                    log.write(json.dumps(dict(arguments=args, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)) + '\n')
                return json.loads(result.stdout) if result.returncode == 0 else None

            def active():
                value = query('--application-action', 'Workspace', 'activate')
                assert not value or value.get('window_role') == 'main', 'Incorrect validation probe'
                return value if value and value.get('active') and value.get('key') and value.get('window_number') else None
            startup = {}
            for name in ('Preferences', 'TimeMon'):
                child = until(lambda: actor(name, user_account.pw_uid), 'stock autolaunch starts ' + name, timeout=40)

                def started():
                    value = query('--application-state', name)
                    return value if value and value.get('window_role') == 'main' and (name != 'Preferences' or value.get('window_number')) else None
                startup_state = until(started, 'stock ' + name + ' finishes GUI initialization', timeout=30)
                startup[name] = dict(pid=child[0], state=startup_state)
            (root / 'stock-autolaunch.json').write_text(json.dumps(startup, indent=2) + '\n')
            main = until(active, 'Workspace main window receives normal activation', timeout=30)
            (root / 'workspace-main-state.json').write_text(json.dumps(main, indent=2) + '\n')
            from PIL import Image, ImageChops
            reference = Path(__file__).with_name('fixtures') / 'greetd/logout-100.png'
            with Image.open(reference) as image:
                expected = image.convert('RGBA')
            assert expected.size == (360, 201)
            solid = Image.new('RGBA', expected.size, (255, 0, 0, 255))
            assert ImageChops.difference(solid.convert('RGB'), expected.convert('RGB')).getbbox()
            (root / 'readiness-negative-control.json').write_text(json.dumps(dict(same_alpha_solid_rejected=True, comparison='Static RGB dialog content plus actual keyboard focus'), indent=2) + '\n')
            (root / 'logout-reference.png').write_bytes(reference.read_bytes())
            previous = {}
            from wayland_trace import native_window_focus

            def save_dialog(label):

                def rendered():
                    for picture in user_capture.glob('*.png'):
                        if picture.stat().st_mtime_ns <= previous.get(picture.name, 0):
                            continue
                        try:
                            with Image.open(picture) as image:
                                actual = image.convert('RGBA')
                            if actual.size == expected.size and (not ImageChops.difference(actual.crop((0, 24, 360, 162)).convert('RGB'), expected.crop((0, 24, 360, 162)).convert('RGB')).getbbox()):
                                trace = user_capture / 'protocol' / (str(pid) + '.log')
                                state = native_window_focus(trace.read_text(errors='replace') if trace.exists() else '', int(picture.stem.split('-')[1]))
                                if state['focused']:
                                    (root / (label + '-focus.json')).write_text(json.dumps(state, indent=2) + '\n')
                                    return picture
                        except OSError:
                            pass
                    return None
                picture = until(rendered, 'native Log Out dialog body matches the observed reference', timeout=25)
                (root / (label + '.png')).write_bytes(picture.read_bytes())
                (root / (label + '.json')).write_text(json.dumps(dict(capture=str(picture), reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(), reference_body_pixels_match=True, modal_rpc_used=False), indent=2) + '\n')

            def logout_key():
                until(active, 'activate Workspace for normal logout')
                device.key(56, 1)
                device.key(16, 1)
                device.key(16, 0)
                device.key(56, 0)
            previous = {p.name: p.stat().st_mtime_ns for p in user_capture.glob('*.png')}
            logout_key()
            save_dialog('logout-cancel-dialog')
            device.key(1, 1)
            device.key(1, 0)

            def cancelled():
                value = query('--application-state', 'Workspace', '--modal-window')
                return value if value and value.get('window_role') == 'modal' and (not value['window_number']) else None
            until(cancelled, 'logout cancellation closes the actual modal')
            assert actor('Workspace', user_account.pw_uid)[0] == pid
            user_hooks(['LoginHook'])
            previous = {p.name: p.stat().st_mtime_ns for p in user_capture.glob('*.png')}
            logout_key()
            save_dialog('logout-confirm-dialog')
            greeter_before = {p.name: p.stat().st_mtime_ns for p in (root / 'captures').glob('*.png')}
            device.text('\n')
            final = until(lambda: (lambda value: value if value and value[0] != initial[0] else None)(actor('Login', account.pw_uid)), 'ordinary logout returns to installed greeter', timeout=35)
            until(lambda: not Path('/proc/' + str(pid)).exists(), 'Workspace is reaped after logout')
            for item in startup.values():
                until(lambda: not Path('/proc/' + str(item['pid'])).exists(), 'autolaunched application is reaped after logout')
            assert final[1]['NEXTSPACE_SESSION_ID'] != initial[1]['NEXTSPACE_SESSION_ID'] and final[1]['DBUS_SESSION_BUS_ADDRESS'] != initial[1]['DBUS_SESSION_BUS_ADDRESS']
            from login_artwork import check_panel

            def returned_panel():
                for picture in (root / 'captures').glob('*.png'):
                    if picture.stat().st_mtime_ns <= greeter_before.get(picture.name, 0):
                        continue
                    try:
                        check_panel(picture, Path('/usr/NextSpace/Apps/Login.app/Resources/Login.gorm'), 120)
                        return picture
                    except (AssertionError, OSError):
                        pass
                return None
            picture = until(returned_panel, 'returned installed Login panel renders', timeout=25)
            (root / 'returned-login-panel.png').write_bytes(picture.read_bytes())
            returned_state = run(['loginctl', 'show-session', final[1]['XDG_SESSION_ID'], '-p', 'Type', '-p', 'Class', '-p', 'Seat', '-p', 'VTNr', '-p', 'Active'])
            assert all((v in returned_state for v in ('Type=wayland', 'Class=greeter', 'Seat=seat0', 'VTNr=' + str(args.vt), 'Active=yes'))), returned_state
            (root / 'returned-greeter-logind.txt').write_text(returned_state + '\n')
            hooks = user_hooks(['LoginHook', 'LogoutHook'])
            if hooks is not None:
                (root / 'user-hooks.json').write_text(json.dumps(dict(passed=True, events=hooks,
                    cancelled_logout_did_not_run_hook=True, preferences_preserved=True), indent=2) + '\n')
            record = dict(passed=True, modal_native_capture_readiness_verified=True, returned_login_panel_rendered=True, actual_standard_user_pam_service='greetd', kernel_keyboard_input=True, initial_greeter_pid=initial[0], workspace_pid=pid, returned_greeter_pid=final[0], user_uid=user_account.pw_uid, user_logind=state, logout_cancelled_then_confirmed=True, initial_greeter_and_workspace_reaped=True, separate_greeter_session_and_bus=True, private_compositor_relay=False, physical_gpu_qualified=False, full_plan_complete=False)
            record['user_hooks_tested'] = hooks is not None
            (root / 'login-cycle.json').write_text(json.dumps(record, indent=2) + '\n')
            return record
        finally:
            device.close()
    try:
        home = root / 'home'
        run(['useradd', '--system', '--no-create-home', '--home-dir', str(home), '--shell', '/usr/sbin/nologin', user])
        created = True
        account = pwd.getpwnam(user)
        home.mkdir(mode=448)
        os.chown(home, account.pw_uid, account.pw_gid)
        capture = root / 'captures'
        capture.mkdir(mode=448)
        os.chown(capture, account.pw_uid, account.pw_gid)
        pam.write_text('auth requisite pam_succeed_if.so user = ' + user + '\nauth required pam_permit.so\naccount requisite pam_succeed_if.so user = ' + user + '\naccount required pam_permit.so\nsession required pam_unix.so\nsession required pam_systemd.so class=greeter type=wayland\n')
        pam.chmod(420)
        (root / 'greeter.pam').write_bytes(pam.read_bytes())
        user = 'nsu' + token
        user_home = root / 'user-home'
        run(['useradd', '--no-create-home', '--home-dir', str(user_home), '--shell', '/bin/sh', user])
        user_created = True
        user_account = pwd.getpwnam(user)
        user_home.mkdir(mode=448)
        os.chown(user_home, user_account.pw_uid, user_account.pw_gid)
        if args.user_hooks:
            hook_log = user_home / 'session-hooks.jsonl'
            hook_script = user_home / 'Session Hook.py'
            hook_script.write_text('''from pathlib import Path
import json, os, sys
def running(name):
    for process in Path('/proc').iterdir():
        try:
            if process.name.isdigit() and process.stat().st_uid == os.getuid() and (process/'exe').resolve(strict=True).name == name:
                return True
        except OSError:
            pass
    return False
with open(sys.argv[2], 'a') as output:
    output.write(json.dumps(dict(hook=sys.argv[1], uid=os.getuid(), euid=os.geteuid(),
        session_class=os.environ.get('XDG_SESSION_CLASS'), session_type=os.environ.get('XDG_SESSION_TYPE'),
        display_unset='DISPLAY' not in os.environ, compositor_running=running('nextspace-compositor'),
        workspace_running=running('Workspace'))) + '\\n')
''')
            hook_profile = user_home / 'Library/Preferences/.NextSpace/Login'
            hook_profile.parent.mkdir(parents=True)
            hook_preferences = plistlib.dumps({name: ['/usr/bin/python3', str(hook_script), name,
                str(hook_log)] for name in ('LoginHook', 'LogoutHook')})
            hook_profile.write_bytes(hook_preferences)
            for path in user_home.rglob('*'):
                os.chown(path, user_account.pw_uid, user_account.pw_gid)
        secret = ''.join((secrets.choice(string.ascii_lowercase) for _ in range(32)))
        subprocess.run(['chpasswd'], input=user + ':' + secret + '\n', text=True, capture_output=True, check=True)
        user_capture = root / 'user-captures'
        user_capture.mkdir(mode=448)
        os.chown(user_capture, user_account.pw_uid, user_account.pw_gid)
        trace_dir = user_capture / 'protocol'
        trace_dir.mkdir(mode=448)
        os.chown(trace_dir, user_account.pw_uid, user_account.pw_gid)
        assert not pref.is_symlink()
        pref_data = pref.read_bytes() if pref.exists() else None
        pref_mode = stat.S_IMODE(pref.stat().st_mode) if pref.exists() else None
        backup = root / 'login-preferences-original'
        if pref_data is not None:
            backup.write_bytes(pref_data)
            backup.chmod(384)
        (root / 'login-preferences-original.json').write_text(json.dumps(dict(existed=pref_data is not None, mode=pref_mode, sha256=hashlib.sha256(pref_data).hexdigest() if pref_data is not None else None), indent=2) + '\n')
        pref_written = True
        pref.parent.mkdir(parents=True, exist_ok=True)
        pref.write_bytes(plistlib.dumps(dict(NativeSessionCommand=['/bin/sh', '-c', 'exec ' + shlex.join(['/usr/bin/env', 'WAYLAND_DEBUG=client', 'LD_PRELOAD=' + str(args.stderr_trace.resolve()), 'NEXTSPACE_TEST_STDERR_DIR=' + str(trace_dir), 'WLR_RENDERER=pixman', 'LIBSEAT_BACKEND=logind', 'NEXTSPACE_WAYLAND_CAPTURE_DIR=' + str(user_capture), '/usr/NextSpace/bin/nextspace-wayland-session']) + ' >' + shlex.quote(str(user_capture / 'session.log')) + ' 2>&1'])))
        pref.chmod(420)
        pref_written = True
        command = shlex.join(['/usr/bin/env', 'WLR_RENDERER=pixman', 'LIBSEAT_BACKEND=logind', 'NEXTSPACE_WAYLAND_CAPTURE_DIR=' + str(capture), '/usr/NextSpace/bin/nextspace-wayland-greeter'])
        cfg = root / 'greetd.toml'
        cfg.write_text('[terminal]\nvt = ' + str(args.vt) + '\nswitch = true\n[general]\nsource_profile = false\nservice = "greetd"\nrunfile = "' + str(root / 'greetd.run') + '"\n[default_session]\nuser = "' + greeter + '"\nservice = "' + pam.name + '"\ncommand = ' + json.dumps(command) + '\n')
        drop.parent.mkdir(parents=True, exist_ok=True)
        drop.write_text('[Service]\nExecStart=\nExecStart=/usr/sbin/greetd -c ' + str(cfg) + '\n')
        run(['systemctl', 'daemon-reload'])
        run(['systemctl', 'start', 'greetd'])
        from login_artwork import check_panel
        picture = None
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline and picture is None:
            for p in capture.glob('*.png'):
                try:
                    check_panel(p, Path('/usr/NextSpace/Apps/Login.app/Resources/Login.gorm'), 120)
                    picture = p
                    break
                except (AssertionError, OSError):
                    pass
            if picture is None:
                time.sleep(0.05)
        assert picture, 'No matching installed Login panel'
        (root / 'login-panel.png').write_bytes(picture.read_bytes())
        actors = {}
        for p in Path('/proc').iterdir():
            if not p.name.isdigit():
                continue
            try:
                exe = (p / 'exe').resolve(strict=True)
                if str(exe).startswith('/usr/NextSpace/') and int((p / 'status').read_text().split('Uid:')[1].split()[0]) == account.pw_uid:
                    raw = dict((x.split('=', 1) for x in (p / 'environ').read_bytes().decode().split('\x00') if '=' in x))
                    actors[p.name] = dict(executable=str(exe), sha256=hashlib.sha256(exe.read_bytes()).hexdigest(), environment={k: raw[k] for k in ('XDG_SESSION_CLASS', 'XDG_SESSION_TYPE', 'WAYLAND_DISPLAY', 'XDG_RUNTIME_DIR', 'NEXTSPACE_SESSION_ID', 'DBUS_SESSION_BUS_ADDRESS') if k in raw}, display_unset='DISPLAY' not in raw)
            except (OSError, ValueError):
                pass
        sessions = []
        for line in run(['loginctl', 'list-sessions', '--no-legend']).splitlines():
            fields = line.split()
            if len(fields) > 1 and fields[1] == str(account.pw_uid):
                sessions.append(run(['loginctl', 'show-session', fields[0], '-p', 'Type', '-p', 'Class', '-p', 'Seat', '-p', 'VTNr', '-p', 'Active', '-p', 'TTY']))
        assert any(('Class=greeter' in s and 'Seat=seat0' in s and ('Active=yes' in s) for s in sessions)), sessions
        assert any((Path(a['executable']).name == 'Login' and a['environment'].get('XDG_SESSION_TYPE') == 'wayland' and a['display_unset'] for a in actors.values())), actors
        assert Path('/sys/class/tty/tty0/active').read_text().strip() == 'tty' + str(args.vt)
        result.update(passed=True, greeter_user=greeter, uid=account.pw_uid, actors=actors, logind_sessions=sessions, active_vt=args.vt, actual_systemd_greetd_service=True, software_renderer=True, real_user_authentication_tested=False, full_plan_complete=False)
        result['login_cycle'] = exercise_login(root, greeter, account, user, secret, user_account, user_capture, args.probe.resolve())
        result['real_user_authentication_tested'] = result['login_cycle']['passed']
    except BaseException as error:
        result.update(passed=False, error=repr(error))
        raise
    finally:
        run(['systemctl', 'stop', 'greetd'], False)
        (root / 'journal.log').write_text(run(['journalctl', '-u', 'greetd', '--since', '@' + str(int(started)), '--no-pager'], False))
        if created:
            result['remaining_defaults_locks'] = [str(p.relative_to(root)) for p in (root / 'home').rglob('*.lck') if p.name != '.lck']

        def remove_account(name):
            run(['loginctl', 'terminate-user', name], False)
            run(['pkill', '-KILL', '-u', name], False)
            attempts = []
            for attempt in range(20):
                value = subprocess.run(['userdel', name], capture_output=True, text=True, timeout=10)
                attempts.append(dict(returncode=value.returncode, stderr=value.stderr))
                if value.returncode == 0:
                    break
                time.sleep(0.25)
            (root / (name + '-cleanup.json')).write_text(json.dumps(attempts, indent=2) + '\n')
        if created:
            remove_account(greeter)
        if user_created:
            remove_account(user)
        if pref_written:
            if pref_data is None:
                pref.unlink(missing_ok=True)
            else:
                pref.write_bytes(pref_data)
                pref.chmod(pref_mode)
        if drop.exists():
            drop.unlink()
        if pam.exists():
            pam.unlink()
        run(['systemctl', 'daemon-reload'], False)
        with open('/dev/tty0', 'rb') as tty:
            fcntl.ioctl(tty, 22022, oldvt)
            fcntl.ioctl(tty, 22023, oldvt)
        result.update(ordinary_pam_unchanged=Path('/etc/pam.d/greetd').read_bytes() == original_pam, preferences_restored=not pref.exists() if pref_data is None else pref.read_bytes() == pref_data and stat.S_IMODE(pref.stat().st_mode) == pref_mode, temporary_accounts_removed=all((not run(['getent', 'passwd', name], False) for name in (greeter, user))), configuration_restored=Path('/etc/greetd/config.toml').read_bytes() == original, service_inactive=run(['systemctl', 'is-active', 'greetd'], False) == 'inactive', service_disabled=run(['systemctl', 'is-enabled', 'greetd'], False) == 'disabled', foreground_vt_restored=Path('/sys/class/tty/tty0/active').read_text().strip() == 'tty' + str(oldvt))
        (root / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    assert result['ordinary_pam_unchanged'] and result['preferences_restored'] and result['temporary_accounts_removed'] and result['configuration_restored'] and result['service_inactive'] and result['service_disabled'] and result['foreground_vt_restored']
    print('Installed native greeter/systemd/logind VT smoke: PASS')
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable-guest', action='store_true', required=True)
    for name in ('artifacts', 'probe', 'stderr-trace', 'keyboard', 'pointer'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--vt', type=int, default=8)
    parser.add_argument('--version')
    parser.add_argument('--user-hooks', action='store_true', help='Verify user-owned login/logout hooks through ordinary PAM login.')
    main(parser.parse_args())
