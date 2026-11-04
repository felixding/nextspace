#!/usr/bin/env python3
"""Exercise the shared Workspace adapter on a disposable X11 user profile."""
import argparse
import json
import os
import plistlib
from pathlib import Path
import subprocess
import select
from integration import until


def run(workspace, probe, display, artifacts, printing_probe=None, textedit=None, review=None,
        launcher=None, pasteboard_probe=None):
    if not Path('/.dockerenv').exists() or not Path.home().name.startswith('nextspace-x11-'):
        raise RuntimeError('Use a disposable Linux container and a fresh nextspace-x11- user home')
    artifacts.mkdir(parents=True, exist_ok=True)
    legacy = Path.home() / 'Library/Preferences/.NextSpace'
    legacy.mkdir(parents=True, exist_ok=True)
    state = plistlib.loads((Path(workspace).parent / 'Resources/WMState.plist').read_bytes())
    for application in state['Dock']['Applications']:
        if application['Name'] != 'Workspace.GNUstep': application['AutoLaunch'] = 'No'
    (legacy / 'WMState.plist').write_bytes(plistlib.dumps(state))
    env = dict(os.environ, DISPLAY=display, XDG_SESSION_TYPE='x11')
    # The fresh test UID isolates legacy RPC; use the launcher's X11 pasteboard
    # context so automatic storage starts gpbs with its X selection bridge.
    for key in ('NEXTSPACE_SESSION_ID', 'NEXTSPACE_GS_BACKEND', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET', 'NEXTSPACE_SHELL_SOCKET'):
        env.pop(key, None)
    def run_probe(*arguments):
        result = subprocess.run([probe, *arguments, '-GSWorkspaceApplication', 'Workspace'],
                                env=env, capture_output=True, text=True, timeout=15)
        with (artifacts / 'workspace-api.jsonl').open('a') as log:
            log.write(json.dumps(dict(arguments=arguments, status=result.returncode,
                                      stdout=result.stdout, stderr=result.stderr)) + '\n')
        return result
    def query(*arguments):
        result = run_probe(*arguments)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    shell_log = artifacts / 'workspace.log'
    with shell_log.open('w') as log:
        shell = subprocess.Popen([launcher or workspace, *([] if launcher else ['-GSBackend', 'libgnustep-x11']), '-GSTheme', 'NextSpace',
                                  '-RestoreDisplayLayout', 'NO', '-NSUseRunningCopy', 'NO'],
                                 env=env, stdout=log, stderr=log)
    client = None
    def client_window(title='NextSpaceLegacyTest'):
        # WM application icons share the class; only the client has this title.
        result = subprocess.run(['xdotool', 'search', '--name', '^' + title + '$'],
                                env=env, capture_output=True, text=True, timeout=3)
        return result.stdout.splitlines()[0] if result.returncode == 0 and result.stdout.strip() else None
    try:
        def ready():
            assert shell.poll() is None, shell_log.read_text()[-8000:]
            return 'Workspace is ready' in shell_log.read_text()
        until(ready, 'X11 Workspace ready', timeout=30)
        libraries = sorted({line.split()[-1] for line in Path(f'/proc/{shell.pid}/maps').read_text().splitlines()
            if any(name in line for name in ('libgnustep-', 'libobjc.so.', 'libSystemKit.so.', 'libDesktopKit.so.'))})
        assert any('libgnustep-x11' in path for path in libraries), libraries
        assert not any('libgnustep-wayland' in path for path in libraries), libraries
        (artifacts / 'runtime.json').write_text(json.dumps(dict(
            executable=str(Path(f'/proc/{shell.pid}/exe').resolve()), libraries=libraries), indent=2) + '\n')
        if pasteboard_probe:
            # Start storage through NSPasteboard itself, using the installed
            # tool search path and the launcher's unscoped X11 environment.
            with (artifacts / 'pasteboard.log').open('w') as log:
                # Legacy --auto storage exits when its last client closes.
                # Keep the copying application alive while a second reads.
                writer = subprocess.Popen([pasteboard_probe, '--write-hold'], env=env,
                    stdout=subprocess.PIPE, stderr=log, text=True)
                try:
                    assert select.select([writer.stdout], [], [], 15)[0], 'X11 pasteboard writer did not start'
                    assert writer.stdout.readline().strip() == 'Pasteboard data ready'
                    subprocess.run([pasteboard_probe, '--read'], env=env, stdout=log,
                                   stderr=log, check=True, timeout=15)
                    bridge = Path(probe).with_name('x11-probe')
                    bridge_checked = False
                    if bridge.is_file():
                        expected = subprocess.check_output([pasteboard_probe, '--export-text'], env=env, timeout=5)
                        def transfer(mode, path):
                            process = subprocess.Popen([str(bridge), mode, str(path)], env=env,
                                stdout=subprocess.PIPE, stderr=log, text=True)
                            try:
                                def visible_or_finished():
                                    if process.poll() is not None:
                                        assert process.returncode == 0, process.returncode
                                        return True
                                    return client_window('X11ClipboardProbe')
                                identity = until(visible_or_finished, 'legacy clipboard window or completed read')
                                if identity is not True:
                                    subprocess.run(['xdotool', 'windowactivate', '--sync', identity], env=env, check=True, timeout=5)
                            except BaseException:
                                log.write('Clipboard client status: ' + str(process.poll()) + '\n')
                                state = subprocess.run(['xwininfo', '-root', '-tree'], env=env,
                                    capture_output=True, text=True, timeout=3)
                                log.write(state.stdout + state.stderr); log.flush()
                                process.terminate(); process.wait(timeout=5)
                                raise
                            return process
                        destination = artifacts / 'x11-clipboard-export.txt'
                        reader = transfer('--clipboard-read', destination)
                        try:
                            reader.wait(timeout=10)
                            assert reader.returncode == 0 and destination.read_bytes() == expected
                        finally:
                            if reader.poll() is None: reader.terminate(); reader.wait(timeout=5)
                            reader.stdout.close()
                        incoming = artifacts / 'x11-clipboard-import.txt'
                        incoming.write_bytes(b'External X11: ' + expected)
                        provider = transfer('--clipboard-write', incoming)
                        try:
                            assert select.select([provider.stdout], [], [], 5)[0]
                            assert provider.stdout.readline().strip() == 'X11 clipboard source set'
                            def imported():
                                result = subprocess.run([pasteboard_probe, '--export-text'], env=env,
                                    capture_output=True, timeout=5)
                                return result.returncode == 0 and result.stdout == incoming.read_bytes()
                            until(imported, 'X11 selection imported into GNUstep pasteboard')
                            bridge_checked = True
                        finally:
                            if provider.poll() is None: provider.terminate(); provider.wait(timeout=5)
                            provider.stdout.close()
                    (artifacts / 'pasteboard.json').write_text(json.dumps(dict(
                        automatic_start=True, unicode_text=True, binary_data=True,
                        x11_selection_roundtrip=bridge_checked)) + '\n')
                finally:
                    if writer.poll() is None: writer.terminate(); writer.wait(timeout=5)
                    writer.stdout.close()
        assert query('--open', '/tmp')['opened']
        for action, title in [('collapse', 'Uncollapse'), ('expand', 'Collapse'),
                              ('hide', 'Show'), ('show', 'Hide'),
                              ('hide-yard', 'Show'), ('show-yard', 'Hide')]:
            assert query('--dock-action', action)['title'] == title
        preferences = query('--dock-preferences')
        assert preferences['name'] == 'Preferences.GNUstep', preferences
        assert query('--dock-preferences', '/bin/false')['locked']
        edited = query('--dock-preferences')
        assert edited['command'] == '/bin/false' and edited['locked']
        for level in (0, -1000, 5):
            state = query('--dock-level', str(level))
            assert state['level'] == level and state['automatic_enabled'], state
        desktop_initial = query('--desktop-preferences')
        desktop_changed = query('--desktop-preferences', 'desktopsNumber', '3')
        assert len(desktop_changed['names']) == 3
        desktop_changed = query('--desktop-preferences', 'name', 'X11 Desktop')
        assert desktop_changed['names'][desktop_changed['current']] == 'X11 Desktop'
        desktop_changed = query('--desktop-preferences', 'directSwitchKey', '2')
        assert desktop_changed['shortcuts']['Desktop2Key'] == 'Alt+Control+2'
        request = artifacts / 'desktop-request.json'
        def desktop_state(**changes):
            request.write_text(json.dumps(dict(action='desktop-settings', **changes)))
            return query('--display-request', str(request))
        def switch_desktop(key, index):
            subprocess.run(['xdotool', 'key', '--clearmodifiers', key], env=env, check=True, timeout=3)
            return desktop_state()['current'] == index
        until(lambda: switch_desktop('ctrl+alt+2', 1), 'X11 Desktops preference changes the real key grab')
        until(lambda: switch_desktop('ctrl+alt+1', 0), 'return to the first desktop before removing test desktops')
        with (artifacts / 'desktop-guard.log').open('w') as log:
            client = subprocess.Popen(['xmessage', '-title', 'Desktop removal guard', '-buttons', 'Close:0',
                'Keep this window on the middle desktop.'], env=env, stdout=log, stderr=log)
        guard_window = until(lambda: client_window('Desktop removal guard'), 'desktop-removal guard window')
        def guard_desktop():
            return subprocess.check_output(['xprop', '-id', guard_window, '_NET_WM_DESKTOP'], env=env, text=True).strip()
        until(lambda: '_NET_WM_DESKTOP(CARDINAL)' in guard_desktop(), 'managed desktop-removal guard window')
        subprocess.run(['xdotool', 'set_desktop_for_window', guard_window, '1'], env=env, check=True, timeout=3)
        def guard_visible():
            return 'Map State: IsViewable' in subprocess.check_output(['xwininfo', '-id', guard_window], env=env, text=True)
        until(lambda: not guard_visible(), 'guard window moved off the current desktop')
        placed_desktop = guard_desktop()
        before_guard = desktop_state()
        guard_request = artifacts / 'desktop-guard-request.json'
        guard_request.write_text(json.dumps(dict(action='desktop-settings', names=desktop_initial['names'])))
        rejected = run_probe('--display-request', str(guard_request))
        after_guard = desktop_state()
        (artifacts / 'desktop-guard.json').write_text(json.dumps(dict(before=before_guard, after=after_guard,
            returncode=rejected.returncode, placed_desktop=placed_desktop,
            window_desktop=guard_desktop(), visible_after=guard_visible()), indent=2) + '\n')
        assert rejected.returncode == 1, 'Occupied desktop removal was accepted'
        assert after_guard == before_guard, 'Rejected desktop removal partially changed the layout'
        assert placed_desktop.endswith('= 1'), 'Window desktop metadata did not follow its move'
        assert guard_desktop().endswith('= 1'), 'Rejected desktop removal displaced a window'
        client.terminate(); client.wait(timeout=5); client = None
        until(lambda: all(item['NSApplicationName'] != 'Xmessage' for item in query('--list')), 'guard window removed')
        restored = desktop_state(names=desktop_initial['names'], shortcuts=desktop_initial['shortcuts'])
        assert restored['names'] == desktop_initial['names'] and restored['shortcuts'] == desktop_initial['shortcuts']
        aliases = dict(Command='alt', Alt='alt', Control='ctrl', Ctrl='ctrl', Super='super', Alternate='super', Shift='shift')
        previous = desktop_initial['shortcuts']['Desktop1Key']
        if previous != 'None':
            binding = '+'.join(aliases.get(part, part) for part in previous.split('+'))
            until(lambda: switch_desktop(binding, 0), 'X11 desktop bindings restore')
        with (artifacts / 'client.log').open('w') as log:
            client = subprocess.Popen(['xmessage', '-name', 'NextSpaceLegacyTest', '-title', 'NextSpaceLegacyTest',
                                       '-buttons', 'Close:0', '-default', 'Close', 'Legacy lifecycle'], env=env, stdout=log, stderr=log)
        until(lambda: any(item['NSApplicationName'] == 'Xmessage' for item in query('--list')),
              'X11 client registration')
        window = until(client_window, 'mapped Xmessage window')
        subprocess.run(['xdotool', 'windowactivate', '--sync', window], env=env, check=True, timeout=10)
        until(lambda: query('--active').get('NSApplicationName') == 'Xmessage', 'X11 client activation')
        subprocess.run(['xdotool', 'key', '--clearmodifiers', 'Return'], env=env, check=True, timeout=10)
        client.wait(timeout=10)
        assert client.returncode == 0, (artifacts / 'client.log').read_text()
        until(lambda: all(item['NSApplicationName'] != 'Xmessage' for item in query('--list')), 'X11 client removal')
        (artifacts / 'results.json').write_text(json.dumps(dict(preferences=preferences, edited=edited,
            passed=['X11 startup', 'file viewer', 'Dock and IconYard actions', 'Dock preferences edit/reload',
                    'all Dock levels', 'shared Desktops preferences, names/count and real shortcut switching',
                    'occupied desktop removal preserves the complete layout',
                    'legacy client registration, activation and graceful close']), indent=2) + '\n')
        if printing_probe:
            from printing_x11 import run as printing
            for profile in ('portrait','crop','landscape'):
                for unflipped in (False,True):
                    name='printing-'+profile+('-unflipped' if unflipped else '-flipped')
                    printing(printing_probe,env,artifacts/name,unflipped,profile)
                    printing(printing_probe,env,artifacts/(name+'-nested'),unflipped,profile,True,artifacts/name)
        if textedit:
            from printing_textedit import run_x11
            run_x11(textedit,probe,env,artifacts/'printing-textedit')
        if review:
            from review import run_x11
            run_x11(review,probe,env,artifacts/'review')
        print('X11 Workspace, Dock preferences and legacy client lifecycle: PASS')
    except BaseException:
        snapshot = dict(workspace_exit=shell.poll(), windows={})
        root_state = subprocess.run(['xprop', '-root', '_NET_CURRENT_DESKTOP', '_NET_NUMBER_OF_DESKTOPS', '_NET_CLIENT_LIST'],
            env=env, capture_output=True, text=True, timeout=3)
        snapshot['root'] = root_state.stdout
        listing = subprocess.run(['xdotool', 'search', '--all', '--name', '.*'],
            env=env, capture_output=True, text=True, timeout=3)
        for window in listing.stdout.splitlines():
            state = subprocess.run(['xprop', '-id', window, '_NET_WM_DESKTOP', 'WM_NAME', 'WM_CLASS'],
                env=env, capture_output=True, text=True, timeout=3)
            snapshot['windows'][window] = state.stdout
        (artifacts / 'failure.json').write_text(json.dumps(snapshot, indent=2) + '\n')
        raise
    finally:
        if client and client.poll() is None:
            client.terminate(); client.wait(timeout=5)
        if shell.poll() is None:
            shell.terminate()
            try: shell.wait(timeout=5)
            except subprocess.TimeoutExpired:
                shell.kill(); shell.wait(timeout=5)
        subprocess.run([probe, '--cleanup-registry'], env=env, capture_output=True, timeout=10)


def run_as_user(workspace, probe, user, artifacts, printing_probe=None, textedit=None, review=None,
                launcher=None, pasteboard_probe=None):
    if os.geteuid() != 0 or not Path('/.dockerenv').exists() or user != 'nextspace-x11':
        raise RuntimeError('Only the disposable container test user may be launched')
    artifacts.mkdir(parents=True, exist_ok=True)
    read_fd, write_fd = os.pipe()
    with (artifacts / 'xvfb.log').open('w') as log:
        server = subprocess.Popen(['Xvfb', '-displayfd', str(write_fd), '-screen', '0',
                                   '1600x1200x24', '-noreset', '-ac'], pass_fds=[write_fd], stderr=log)
    os.close(write_fd)
    try:
        assert select.select([read_fd], [], [], 10)[0], 'Xvfb did not start'
        number = os.read(read_fd, 64).decode().strip()
        assert number.isdigit(), 'Invalid Xvfb display'
        subprocess.run(['runuser', '-u', user, '--', 'python3', __file__, '--workspace', workspace,
                        '--probe', probe, '--display', ':' + number, '--artifacts', str(artifacts),
                        *(['--printing-probe',printing_probe] if printing_probe else []),
                        *(['--textedit',textedit] if textedit else []),
                        *(['--review',review] if review else []),
                        *(['--launcher',launcher] if launcher else []),
                        *(['--pasteboard-probe',pasteboard_probe] if pasteboard_probe else [])], check=True)
    finally:
        os.close(read_fd)
        if server.poll() is None: server.terminate(); server.wait(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--probe', required=True)
    parser.add_argument('--printing-probe')
    parser.add_argument('--textedit')
    parser.add_argument('--review')
    parser.add_argument('--launcher')
    parser.add_argument('--pasteboard-probe')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--display')
    mode.add_argument('--user')
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    optional = (args.printing_probe, args.textedit, args.review, args.launcher, args.pasteboard_probe)
    if args.user: run_as_user(args.workspace, args.probe, args.user, args.artifacts, *optional)
    else: run(args.workspace, args.probe, args.display, args.artifacts, *optional)
