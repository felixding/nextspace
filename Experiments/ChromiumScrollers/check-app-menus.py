#!/usr/bin/env python3
"""Exercise the pinned Chromium menu model through physical native menu input.

The coordinates below are observed test-fixture positions at scale 1, with the
English menu and default native font. They are not used by the adapter or UI.
Run after check-text-commands.py, on the same owned test-text.html fixture.
"""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import time

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--ssh-config', type=Path, required=True)
p.add_argument('--session', required=True)
p.add_argument('--cdp', default='9941')
p.add_argument('--guest-cdp', type=int, default=9241)
p.add_argument('--fixture', required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--opened', action='store_true', help='Menu already opened in the owned fixture')
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
ssh = ['ssh', '-F', str(a.ssh_config), 'lima-nextspace-gui']
ab = ['agent-browser', '--session', a.session, '--cdp', a.cdp]
rows = []


def remote(code):
    return json.loads(subprocess.check_output(ssh + [shlex.join(['python3', '-c', code])], text=True))


def control(command):
    return remote("import socket,json\nwith socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:\n s.settimeout(15);s.connect(" + repr(a.fixture + '/control.sock') + ");s.send(json.dumps(dict(command=" + repr(command) + ")).encode());print(s.recv(65536).decode())")


def js(code):
    return json.loads(subprocess.check_output(ab + ['eval', code], text=True))


def wait(read, predicate):
    deadline = time.monotonic() + 8
    while True:
        value = read()
        if predicate(value):
            return value
        assert time.monotonic() < deadline, value
        time.sleep(.025)


def check(case, condition, **evidence):
    rows.append(dict(case=case, passed=bool(condition), **evidence))
    (a.output / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
    assert condition, rows[-1]


def click(x, y):
    assert control(f'pointer {x} {y}')['ok']
    assert control('button 272')['ok']


def leaf(root_y, x, y):
    assert control(f'pointer 50 {root_y}')['ok']
    assert control('button 272 1')['ok']
    try:
        popup = wait(lambda: control('popups'), bool)
        assert len(popup) == 1 and popup[0]['x'] == 156, popup
        assert control(f'pointer {x} {y}')['ok']
        # A compositor acknowledgment precedes AppKit hit testing. A captured
        # frame waits for actual native rendering before releasing the button.
        assert control('capture HEADLESS-1')['event']['event'] == 'frame'
    finally:
        assert control('button 272 0')['ok']


def pages():
    return remote("import json,urllib.request\nprint(json.dumps([p for p in json.load(urllib.request.urlopen('http://127.0.0.1:" + str(a.guest_cdp) + "/json/list')) if p['type']=='page']))")


def logs():
    return remote('import json;from pathlib import Path\nprint(json.dumps((Path(' + repr(a.fixture) + ")/'hook.log').read_text()))")


launch = remote('from pathlib import Path\nprint((Path(' + repr(a.fixture) + ")/'launch.json').read_text())")
check('owned-fixture', js('location.href') == launch['command'][-1] and js('document.title') == 'Blink native text transport')
browser = next(w for w in control('windows') if w['pid'] == launch['pids'][-1] and w['visible'])
assert control(f"move {browser['id']} 350 80")['ok']
assert control(f"focus {browser['id']}")['ok']
trace_start = len(logs())
if not a.opened:
    click(1195, 143)
trace = wait(logs, lambda s: 'app-menu-native ' in s)
model = [dict(t.split('=', 1) for t in line.split()[2:]) for line in trace.splitlines() if ' app-menu-item ' in line]
check('actual-model-projected', len(model) == 88 and any(bytes.fromhex(i['title_hex']).decode() == 'Find and edit' for i in model), count=len(model))
menus = [w for w in control('windows') if w['pid'] == launch['pids'][-2] and w['visible']]
check('detached-native-window', len(menus) == 1 and menus[0]['level'] == 20 and not menus[0]['accepts_focus'], windows=menus)
prior = pages()
click(55, 32)
after = wait(pages, lambda ps: len(ps) == len(prior) + 1)
check('native-new-tab', len(after) == len(prior) + 1, before=len(prior), after=len(after))
# Select the first, original fixture tab using its visible tab strip.
click(495, 100)
check('fixture-selected', js('location.href') == launch['command'][-1])
check('initial-zoom', js('devicePixelRatio') == 1)
leaf(312, 220, 52)
zoom = wait(lambda: js('devicePixelRatio'), lambda v: abs(v - 1.1) < .0001)
check('native-button-model-zoom-in', abs(zoom - 1.1) < .0001, device_pixel_ratio=zoom)
leaf(312, 220, 32)
zoom = wait(lambda: js('devicePixelRatio'), lambda v: v == 1)
check('native-button-model-zoom-out', zoom == 1, device_pixel_ratio=zoom)
subprocess.check_call(ab + ['click', '#normal'])
js('(()=>{normal.value="Native menu copy";normal.setSelectionRange(0,16);window.__menuEvents=[];for(const type of ["copy","cut","paste","input","beforeinput"])normal.addEventListener(type,e=>__menuEvents.push({type:e.type,trusted:e.isTrusted,inputType:e.inputType??null}));return true})()')
leaf(392, 200, 92)
events = wait(lambda: js('__menuEvents'), lambda es: any(e['type'] == 'copy' for e in es))
check('native-copy-trusted', events == [dict(type='copy', trusted=True, inputType=None)], events=events)
check('native-copy-preserves-model', js('({value:normal.value,start:normal.selectionStart,end:normal.selectionEnd})') == dict(value='Native menu copy', start=0, end=16))
leaf(392, 200, 72)
wait(lambda: js('normal.value'), lambda v: v == '')
check('native-cut', js('normal.value') == '')
leaf(392, 200, 112)
wait(lambda: js('normal.value'), lambda v: v == 'Native menu copy')
events = js('__menuEvents')
check('native-paste-engine-events', [e['type'] for e in events] == ['copy','cut','beforeinput','input','paste','beforeinput','input'] and all(e['trusted'] for e in events) and [e['inputType'] for e in events if e['type'] == 'input'] == ['deleteByCut','insertFromPaste'], events=events)
js('document.execCommand("undo");true')
check('native-paste-preserves-engine-undo', js('normal.value') == '')
js('document.execCommand("undo");true')
check('native-cut-preserves-engine-undo', js('normal.value') == 'Native menu copy')
prior = pages()
for command in ['key 56 1', 'key 20 1', 'key 20 0', 'key 56 0']:
    assert control(command)['ok']
after = wait(pages, lambda ps: len(ps) == len(prior) + 1)
check('native-command-key-from-text-field', len(after) == len(prior) + 1, before=len(prior), after=len(after))
click(495, 100)
previous_bindings = logs().count(' app-menu-native ')
click(1195, 143)
wait(logs, lambda s: s.count(' app-menu-native ') == previous_bindings + 1)
menus = wait(lambda: [w for w in control('windows') if w['pid'] == launch['pids'][-2] and w['visible']], lambda ws: len(ws) == 1)
check('native-menu-replacement', len(menus) == 1, windows=menus)
check('browser-alive', remote('import os,json\nos.kill(' + str(launch['pids'][-1]) + ',0);print("true")'))
trace = logs()
helper = remote('import json;from pathlib import Path\nprint(json.dumps((Path(' + repr(a.fixture) + ")/'helper.jsonl').read_text()))")
check('no-menu-callback-expiry', 'native-menu-command-failed' not in helper and 'native callback ' not in trace[trace_start:])
(a.output / 'hook.log').write_text(trace)
(a.output / 'helper.jsonl').write_text(helper)
(a.output / 'windows.json').write_text(json.dumps(control('windows'), indent=2) + '\n')
print(json.dumps(dict(checks=len(rows), passed=sum(r['passed'] for r in rows))))
