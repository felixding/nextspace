"""Exercise Konsole, Kate and Mousepad through the ordinary preview seat."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from desktop_input import Desktop


def until(read, predicate, label, seconds=12):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = read()
        if predicate(value):
            return value
        time.sleep(.08)
    raise AssertionError((label, value))


def run(root):
    desktop = Desktop(root)
    modifier = desktop.command_modifier()
    assert modifier == 56, 'Left Alt is GNUstep’s default Command modifier'
    report = root / 'ordinary-toolkit-shortcuts.json'
    checks = []

    def save(complete=False):
        report.write_text(json.dumps(dict(complete=complete, checks=checks), indent=2) + '\n')

    def passed(label):
        checks.append(dict(case=label, passed=True))
        save()

    def windows():
        return desktop.command('windows')

    def app_windows(app):
        return [w for w in windows() if w['app_id'] == app and w['visible'] and
                w['level'] == 0 and w['appmenu_path']]

    def app_window(app):
        return app_windows(app)[0]

    def activate(app):
        window = app_window(app)
        if not window['focused']:
            icon = next(w for w in windows() if w['app_id'] == 'org.nextspace.Workspace'
                        and w['visible'] and w['title'] == app)
            desktop.double_click(icon['x'] + icon['width']/2, icon['y'] + icon['height']/2)
            window = until(lambda: app_window(app), lambda w: w['focused'], app + ' focus')
        return window

    def key(code, command=modifier, *, shifted=False):
        desktop.chord(code, command, *((42,) if shifted else ()))

    def type_text(value):
        codes = dict(zip('qwertyuiopasdfghjklzxcvbnm', [*range(16, 26), *range(30, 39), *range(44, 51)]))
        codes.update(dict(zip('1234567890', range(2, 12))))
        codes.update({' ': 57, '/': 53, '.': 52, '-': 12})
        for character in value:
            if character == '_':
                desktop.chord(codes['-'], 42)
            else:
                desktop.key(codes[character])

    def choice(serial):
        return serial['owned'] and not serial['pending']

    workspace = next(w for w in windows() if w['app_id'] == 'org.nextspace.Workspace'
                     and w['title'] == 'File Viewer')
    stage = Path(json.loads((root/'runtime-install.json').read_text())['stage'])
    probe = stage / 'native-ui/native-pasteboard-probe'
    allowed = {'GNUSTEP_CONFIG_FILE', 'NEXTSPACE_SESSION_ID', 'XDG_RUNTIME_DIR', 'LD_LIBRARY_PATH'}
    env = dict(os.environ)
    for entry in (Path('/proc') / str(workspace['pid']) / 'environ').read_bytes().split(b'\0'):
        name, _, value = entry.partition(b'=')
        if os.fsdecode(name) in allowed:
            env[os.fsdecode(name)] = os.fsdecode(value)
    assert env['XDG_RUNTIME_DIR'] == str(root / 'runtime')

    def activate_workspace():
        receiver = next(w for w in windows() if w['visible'] and w['pid'] == workspace['pid']
                        and w['title'] == 'Workspace' and w['style'] == 64)
        desktop.double_click(receiver['x'] + receiver['width']/2, receiver['y'] + receiver['height']/2)
        until(lambda: any(w['pid'] == workspace['pid'] and w['focused'] for w in windows()),
              bool, 'Workspace takes keyboard focus')

    def select_and_copy(expected, label, screenshot=None):
        original = desktop.command('selection-state')['serial']
        key(30)
        if screenshot:
            desktop.capture(screenshot)
        key(46)
        until(lambda: desktop.command('selection-state'),
              lambda serial: serial['serial'] != original and choice(serial), label + ' clipboard offer')
        # A real native window imports the external Wayland offer for GPBS.
        activate_workspace()

        def copied():
            value = subprocess.run([probe, '--export-text'], env=env, capture_output=True, text=True, timeout=5)
            return value.stdout if value.returncode == 0 else None

        until(lambda: copied() == expected, bool, label)
        passed(label)

    def find(app, phrase):
        activate(app)
        key(33, shifted=app == 'org.kde.konsole')
        type_text(phrase)
        desktop.chord(30, 29)
        type_text('start')
        desktop.chord(18, 29)
        type_text('end')
        expected = 'start' + phrase + 'end'
        select_and_copy(expected, app + ' Control moves within the Find field and Command selects',
                        'toolkit-find-' + app)
        activate(app)
        key(30)
        type_text('replace')
        key(30)
        key(47)
        select_and_copy(expected, app + ' pastes over selected Find text after switching apps')
        activate(app)
        desktop.key(1)

    def konsole_shells(window):
        pid = window['pid']
        return set(Path(f'/proc/{pid}/task/{pid}/children').read_text().split())

    def launch_konsole():
        running = {w['pid'] for w in app_windows('org.kde.konsole')}
        activate_workspace()
        desktop.chord(38, modifier, 42)  # Workspace > Tools > Launcher…
        until(lambda: any(w['title'] == 'Run Command' and w['focused'] for w in windows()),
              bool, 'Workspace launcher opens and takes focus')
        type_text('/usr/bin/konsole')
        desktop.key(1)  # The Workspace launcher uses Escape for path completion.
        desktop.key(28)
        window = until(lambda: next((w for w in app_windows('org.kde.konsole')
                                     if w['pid'] not in running), None),
                       bool, 'installed Konsole opens from Workspace')
        module = stage / 'toolkit-ui/qt6/generic/libnextspace-qt-scrollbars.so'
        assert str(module) in Path(f"/proc/{window['pid']}/maps").read_text(), module
        desktop.click(window['x'] + 140, window['y'] + 118)
        initial = until(lambda: konsole_shells(window), bool, 'installed Konsole shell starts')
        # Compositor test input bypasses the hardware mapper. Exercise the
        # app's registered Command alias here and the physical chord in Lima.
        key(20, shifted=True)
        until(lambda: konsole_shells(window), lambda current: len(current - initial) == 1,
              'installed Konsole opens a tab with its registered shortcut')
        key(17, shifted=True)
        until(lambda: konsole_shells(window), lambda current: current == initial,
              'installed Konsole closes the new tab with its registered shortcut')
        key(17, shifted=True)
        until(lambda: app_windows('org.kde.konsole'),
              lambda rows: {w['pid'] for w in rows} == running, 'installed Konsole closes')
        passed('Konsole launched from Workspace inherits native shortcuts')

    try:
        konsole = activate('org.kde.konsole')
        desktop.click(konsole['x'] + 160, konsole['y'] + 140)

        def shells():
            return konsole_shells(konsole)

        original = shells()
        assert original, 'Konsole’s original terminal is running'
        for side, command in [('left', modifier), ('right', 100)]:
            key(20, command, shifted=True)
            until(shells, lambda current: len(current - original) == 1, 'one new Konsole tab')
            if side == 'left':
                desktop.capture('toolkit-konsole-new-tab')
            assert len(shells() - original) == 1
            key(17, command, shifted=True)
            until(shells, lambda current: current == original, 'only the new Konsole tab closes')
            passed(f'Konsole opens and closes one tab with {side} Shift+Command')
        find('org.kde.konsole', 'toolkit')

        # Observe actual PTY bytes, including an escape prefix that a shell
        # might interpret without displaying anything at its prompt.
        raw = root / 'toolkit-pty.py'
        raw.write_text('''import os, select, sys, termios, tty
from pathlib import Path
root = Path(__file__).parent
fd = sys.stdin.fileno()
old = termios.tcgetattr(fd)
try:
    tty.setraw(fd)
    (root / 'toolkit-pty-ready').touch()
    data = bytearray()
    while select.select([fd], [], [], 8)[0]:
        byte = os.read(fd, 1)
        if not byte or byte == b'q':
            break
        data.extend(byte)
    (root / 'toolkit-pty-bytes').write_bytes(data)
finally:
    termios.tcsetattr(fd, termios.TCSADRAIN, old)
''')
        konsole = activate('org.kde.konsole')
        desktop.click(konsole['x'] + 163, konsole['y'] + 140)
        desktop.chord(22, 29)  # Clear the test shell's current prompt line.
        type_text('python3 ' + str(raw))
        desktop.key(28)
        until((root/'toolkit-pty-ready').exists, bool, 'PTY test reader ready')
        key(46, shifted=True)
        desktop.key(16)
        readback = root/'toolkit-pty-bytes'
        until(readback.exists, bool, 'PTY test reader finished')
        assert readback.read_bytes() == b'', readback.read_bytes()
        passed('Konsole Shift+Command+C with no selection sends zero PTY bytes')

        shell = next(iter(original))
        foreground = Path(f'/proc/{shell}/task/{shell}/children')
        type_text('sleep 20')
        desktop.key(28)
        until(foreground.read_text, str.strip, 'Konsole terminal foreground process started')
        desktop.chord(46, 29)
        until(foreground.read_text, lambda value: not value.strip(), 'Konsole Ctrl+C interrupts foreground process')
        passed('Konsole Ctrl+C interrupts the foreground command')

        mousepad = activate('mousepad')
        key(49)
        until(lambda: app_window('mousepad')['title'], lambda title: 'Untitled 1' in title, 'Mousepad new tab')
        key(17)
        until(lambda: app_window('mousepad')['title'], lambda title: title == mousepad['title'], 'Mousepad closes new tab')
        passed('Mousepad opens a document with Command+N and closes it with Command+W')

        document = (root / 'Toolkit preview.txt').read_text()
        select_and_copy(document, 'Mousepad document Select All and Copy')
        find('mousepad', 'preview')

        activate('org.kde.kate')
        select_and_copy(document, 'Kate document Select All and Copy')
        find('org.kde.kate', 'nextspace')
        launch_konsole()
        save(True)
        print(report.read_text(), end='')
    except Exception:
        save()
        desktop.capture('toolkit-shortcut-failure')
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    run(parser.parse_args().root)
