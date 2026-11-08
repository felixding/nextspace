#!/usr/bin/env python3
"""Verify original browser file inputs consume the shared native portal.

Uses an owned frontend fixture, real seat input and the browser's own File API.
Focus assistance is recorded separately; it does not qualify parent import.
"""
import argparse
import json
from pathlib import Path
import socket
import sys
import time
from PIL import Image

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--fixture', type=Path, required=True)
parser.add_argument('--engine', choices=['firefox', 'chromium'], required=True)
parser.add_argument('--port', type=int)
args = parser.parse_args()
root = args.fixture
repo = Path(__file__).resolve().parents[2]
results = []
assisted = []
portal_pid = next(json.loads(row)['pid'] for row in (root/'file-portal.jsonl').read_text().splitlines()
                  if json.loads(row)['event'] == 'ready')
owned = Path('/var/tmp/nxs-file-test.txt')
payload = 'Owned native file dialog fixture\n'
owned.write_text(payload)


def command(value):
    with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as connection:
        connection.settimeout(20)
        connection.connect(str(root/'control.sock'))
        connection.send(json.dumps(dict(command=value)).encode())
        return json.loads(connection.recv(1048576))


def until(predicate, label):
    deadline = time.monotonic()+15
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.02)
    raise AssertionError(label)


def check(label, value):
    assert value, label
    results.append(dict(case=label, passed=True))
    print(json.dumps(results[-1]), flush=True)


def key(code):
    for state in (1, 0):
        assert command(f'key {code} {state}')['ok']


def type_text(value):
    for code in (30, 37):
        for event in ('key 29 1', f'key {code} 1', f'key {code} 0', 'key 29 0'):
            assert command(event)['ok']
    codes = dict(zip('qwertyuiopasdfghjklzxcvbnm', [*range(16,26), *range(30,39), *range(44,51)]))
    codes.update({'/':53, '-':12, '.':52})
    for letter in value:
        key(codes[letter])


def panel():
    return next((window for window in command('windows') if window['pid'] == portal_pid
                 and window['visible'] and window['level'] > 0), None)


def show_panel(label):
    window = until(lambda: (item if (item := panel()) and item['buffer_width'] == item['width'] and item['buffer_height'] == item['height'] else None), 'native panel did not finish presenting')
    if not window['focused']:
        assisted.append(label)
        assert command('focus '+str(window['id']))['ok']
        until(lambda: panel() and panel()['focused'], 'native panel focus failed')
    return window


def capture(name):
    reply = command('capture '+command('outputs')[0]['name'])
    event = reply['event']
    Image.frombytes('RGB', (event['width'], event['height']), Path(reply['path']).read_bytes(),
                    'raw', 'BGRX', event['stride']).save(root/name)


browser_pid = json.loads((root/'launch.json').read_text())['pids'][-1]
client = None
if args.engine == 'firefox':
    sys.path.insert(0, str(repo/'Experiments/FirefoxNativeUI'))
    from marionette import Marionette
    client = Marionette(args.port)
    client.command('WebDriver:NewSession', {'capabilities': {'alwaysMatch': {}}})
    def js(script):
        return client.command('WebDriver:ExecuteScript', dict(script='return ('+script+')', args=[]))['value']
    client.command('WebDriver:Navigate', dict(url=(repo/'Tests/Wayland/native-file-fields.html').as_uri()))
else:
    def cdp(method, params=None, target=True):
        request = dict(method=method, params=params or {})
        if target:
            request['sessionId'] = session
        response = command('cdp '+json.dumps(request))
        assert 'error' not in response, response
        return response['result']
    page = next(item for item in cdp('Target.getTargets', target=False)['targetInfos'] if item['type'] == 'page')
    session = cdp('Target.attachToTarget', dict(targetId=page['targetId'], flatten=True), False)['sessionId']
    def js(script):
        result = cdp('Runtime.evaluate', dict(expression=script, returnByValue=True))
        assert 'exceptionDetails' not in result, result
        return result['result'].get('value')
    cdp('Page.navigate', dict(url=(repo/'Tests/Wayland/native-file-fields.html').as_uri()))


def click_field(identifier):
    window = next(window for window in command('windows') if window['pid'] == browser_pid and window['level'] == 0)
    assert command('focus '+str(window['id']))['ok']
    if args.engine == 'firefox':
        origin = js('[mozInnerScreenX,mozInnerScreenY]')
    else:
        inside = js('({height:innerHeight,scale:devicePixelRatio})')
        assert inside['scale'] == 1
        origin = [window['x']+(window['frame_left'] if window['server_decorated'] else 0),
                  window['y']+(window['frame_top'] if window['server_decorated'] else 0)
                  +window['surface_height']-inside['height']]
    box = js('document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()')
    for event in (f"pointer {round(origin[0]+box['x']+min(10,box['width']/2))} {round(origin[1]+box['y']+box['height']/2)}",
                  'button 272 1', 'button 272 0'):
        assert command(event)['ok']


try:
    until(lambda: js('document.title') == 'Native file fields', 'browser fixture did not load')
    click_field('single')
    show_panel('first-open')
    capture('native-file-panel-desktop.png')
    type_text(str(owned))
    key(28)
    time.sleep(.1)
    if panel():
        type_text(owned.name)
        key(28)
    until(lambda: js('single.files.length') == 1, 'native file did not reach the web page')
    selected = js('Array.from(single.files,file=>({name:file.name,size:file.size,type:file.type}))')
    check('native-panel-returned-original-browser-file-object',
          selected == [dict(name=owned.name, size=len(payload.encode()), type='text/plain')])
    events = js('events')
    check('original-browser-trusted-input-and-change-events',
          [event['type'] for event in events] == ['input', 'change'] and all(event['trusted'] for event in events))
    js('single.files[0].text().then(value=>window.fileText=value)')
    until(lambda: js('window.fileText') == payload, 'selected file payload differs')
    check('browser-read-the-selected-file-payload', True)
    capture('native-file-selected-desktop.png')
    click_field('single')
    window = show_panel('reopen')
    cancel_clicks = 0
    for attempt in range(2):
        window = panel()
        if not window:
            break
        for event in (f"pointer {window['x']+window['width']-126} {window['y']+window['height']-29}",
                      'button 272 1', 'button 272 0'):
            assert command(event)['ok']
        cancel_clicks += 1
        time.sleep(.2)
    until(lambda: not panel(), 'native Cancel left the panel visible')
    until(lambda: len(js('events')) == 3, 'browser cancel event missing')
    check('native-cancel-preserved-selection-and-original-trusted-event',
          js('events[2].type') == 'cancel' and js('events[2].trusted')
          and js('single.files[0].name') == owned.name)
finally:
    if client:
        client.close()
    (root/'browser-file-checks.json').write_text(json.dumps(dict(engine=args.engine, results=results,
        focus_assistance=assisted, cancel_clicks=locals().get('cancel_clicks'), parent_import_qualified=False), indent=2)+'\n')
