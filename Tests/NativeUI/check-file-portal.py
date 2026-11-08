#!/usr/bin/env python3
"""Exercise the shared FileChooser through an owned real portal frontend.

Requires run-frontend-fixture.py --file-portal --hold. Uses real seat keys;
no native panel method is replaced or invoked by the test controller.
"""
import argparse
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import sys
import time
from gi.repository import Gio, GLib

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--fixture', type=Path, required=True)
args = parser.parse_args()
root = args.fixture
env = dict(os.environ, **json.loads((root/'runtime.json').read_text()))
os.environ['DBUS_SESSION_BUS_ADDRESS'] = env['DBUS_SESSION_BUS_ADDRESS']
portal_pid = next(json.loads(row)['pid'] for row in (root/'file-portal.jsonl').read_text().splitlines()
                  if json.loads(row)['event'] == 'ready')
results = []
children = []
files = root/'files'
files.mkdir(exist_ok=True)
for name in ('alpha.txt', 'beta.txt', 'gamma.bin'):
    (files/name).write_text('Owned portal trial\n')


def command(value):
    with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as connection:
        connection.settimeout(10)
        connection.connect(str(root/'control.sock'))
        connection.send(json.dumps(dict(command=value)).encode())
        return json.loads(connection.recv(1048576))


def panels():
    return [window for window in command('windows')
            if window['pid'] == portal_pid and window['visible'] and window['level'] > 0]


def until(predicate, label):
    deadline = time.monotonic()+10
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(.02)
    raise AssertionError(label)


def check(label, value):
    assert value, label
    results.append(dict(case=label, passed=True))
    print(json.dumps(results[-1]), flush=True)


def key(code):
    for state in (1, 0):
        assert command(f'key {code} {state}')['ok']


def show_panel(label):
    windows = until(panels, label)
    window = windows[0]
    # xdg_foreign parent import and cross-client activation remain unqualified.
    # Explicit owned-compositor focus isolates native panel behavior here.
    assert command('focus '+str(window['id']))['ok']
    until(lambda: any(item['focused'] for item in panels()), 'panel focus failed')
    return window


def type_name(value):
    for code in (30, 37):  # The native editor supplies Emacs beginning/kill-line.
        for event in ('key 29 1', f'key {code} 1', f'key {code} 0', 'key 29 0'):
            assert command(event)['ok']
    codes = dict(zip('qwertyuiopasdfghjklzxcvbnm', [*range(16,26), *range(30,39), *range(44,51)]))
    codes['.'] = 52
    for letter in value:
        key(codes[letter])


def receive(process):
    deadline = time.monotonic()+15
    data = bytearray()
    while time.monotonic() < deadline:
        assert select.select([process.stdout], [], [], max(0, deadline-time.monotonic()))[0], 'client response timeout'
        byte = os.read(process.stdout.fileno(), 1)
        assert byte, (process.poll(), process.stderr.read().decode())
        if byte == b'\n':
            return json.loads(data)
        data.extend(byte)
    raise AssertionError('client response timeout')


def start(method='OpenFile', **options):
    options.setdefault('current_folder', ('ay', list(str(files).encode()+b'\0')))
    process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('file-portal-client.py')),
        method, '--options', json.dumps(options)], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, bufsize=0)
    children.append(process)
    request = receive(process)
    assert request['event'] == 'request', request
    return process


def finish(process, response, suffix=None):
    reply = receive(process)
    assert reply['event'] == 'response' and reply['result'][0] == response, reply
    if suffix:
        assert reply['result'][1]['uris'] == [(files/suffix).as_uri()], reply
    process.wait(timeout=5)
    assert process.returncode == 0, process.stderr.read().decode()
    until(lambda: not panels(), 'native panel remained visible')
    return reply['result'][1]


try:
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    try:
        bus.call_sync('org.freedesktop.impl.portal.desktop.nextspace', '/org/freedesktop/portal/desktop',
            'org.freedesktop.impl.portal.FileChooser', 'OpenFile',
            GLib.Variant('(osssa{sv})', ('/org/freedesktop/portal/desktop/request/spoof/one',
                'org.trusted.application', '', 'Spoofed picker', {})), None, Gio.DBusCallFlags.NONE, 3000, None)
        raise AssertionError('Direct untrusted backend call was accepted')
    except GLib.Error as error:
        check('untrusted-backend-call-rejected', 'AccessDenied' in error.message and not panels())

    process = start()
    show_panel('open panel did not appear')
    process.stdin.write(b'close\n')
    check('public-request-close-replied-during-native-modal-loop', receive(process)['event'] == 'closed')
    process.wait(timeout=5)
    until(lambda: not panels(), 'Close did not cancel the native modal session')
    check('request-close-removed-native-panel', True)

    process = start()
    window = show_panel('second open panel did not appear')
    for event in (f"pointer {window['x']+window['width']-126} {window['y']+window['height']-29}", 'button 272 1', 'button 272 0'):
        assert command(event)['ok']
    finish(process, 1)
    check('native-cancel-button-cancellation', True)

    process = start(filters=('a(sa(us))', [['Text', [[0, '*.txt']]], ['All', [[0, '*']]]]),
        choices=('a(ssa(ss)s)', [['encoding', 'Encoding', [['utf8', 'UTF-8'], ['latin1', 'Latin-1']], 'utf8'],
                                 ['readonly', 'Read only', [], 'true']]))
    show_panel('filtered open panel did not appear')
    type_name('alpha.txt')
    key(28)
    result = finish(process, 0, 'alpha.txt')
    check('native-selection-filter-and-choice-identities-returned',
          result['choices'] == [['encoding', 'utf8'], ['readonly', 'true']]
          and result['current_filter'] == ['Text', [[0, '*.txt']]])

    process = start('SaveFile', current_name=('s', 'new.txt'))
    show_panel('save panel did not appear')
    key(28)
    finish(process, 0, 'new.txt')
    check('native-save-panel-returned-uri-without-writing-file', not (files/'new.txt').exists())

    process = start('SaveFile', current_name=('s', 'alpha.txt'))
    show_panel('overwrite save panel did not appear')
    key(28)
    until(lambda: len(panels()) >= 2, 'native overwrite alert did not appear')
    process.stdin.write(b'close\n')
    assert receive(process)['event'] == 'closed'
    process.wait(timeout=5)
    until(lambda: not panels(), 'Close left a nested native overwrite alert')
    check('request-close-cancelled-original-nested-overwrite-alert', True)

    process = start('SaveFiles', files=('aay', [list(b'one.txt\0'), list(b'two.txt\0')]))
    show_panel('native batch folder panel did not appear')
    key(28)
    result = finish(process, 0)
    check('batch-save-used-native-folder-panel-and-preserved-order',
          result['uris'] == [(files/'one.txt').as_uri(), (files/'two.txt').as_uri()])

    process = start()
    show_panel('caller-exit panel did not appear')
    process.terminate()
    process.wait(timeout=5)
    until(lambda: not panels(), 'frontend did not withdraw the departed caller request')
    check('caller-exit-withdrew-native-panel', True)
finally:
    for process in children:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
    (root/'file-portal-checks.json').write_text(json.dumps(results, indent=2)+'\n')
