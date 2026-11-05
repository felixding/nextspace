#!/usr/bin/env python3
"""Opt-in live DRM/libinput test using disposable Linux uinput devices.

Run only in the dedicated validation desktop with an idle Terminal shell.
The injector needs access to /dev/uinput and the selected source devices.
It never grabs or writes to those source devices. Test text creates unique
markers under /tmp; display and fullscreen settings are restored on exit.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import select
import subprocess
import sys
import time
import uuid

from display_service import DisplayService
from integration import until


def inject(paths):
    from evdev import InputDevice, UInput, ecodes as e
    import os
    sources, devices, pressed = [], {}, set()
    try:
        for kind, path in zip(('keyboard', 'pointer'), paths):
            source = InputDevice(path)
            sources.append(source)
            devices[kind] = UInput.from_device(source, name='NEXTSPACE validation ' + kind)
        assert set(devices) == {'keyboard', 'pointer'}
        subprocess.run(['udevadm', 'settle'], check=True)
        print(json.dumps(dict(event='ready', pid=os.getpid(), devices={name: device.device.path for name, device in devices.items()},
            sources=[dict(path=source.path, name=source.name, capabilities=source.capabilities()) for source in sources])), flush=True)
        for line in sys.stdin:
            request = json.loads(line)
            if request.get('quit'): break
            for kind, event_type, code, value in request['events']:
                devices[kind].write(event_type, code, value)
                if event_type == e.EV_KEY:
                    if value: pressed.add((kind, code))
                    else: pressed.discard((kind, code))
                devices[kind].syn()
            print(json.dumps(dict(event='sent', count=len(request['events']))), flush=True)
    finally:
        for kind, code in pressed:
            devices[kind].write(e.EV_KEY, code, 0)
            devices[kind].syn()
        for device in devices.values(): device.close()
        for source in sources: source.close()


class Input:
    def __init__(self, keyboard, pointer, artifacts):
        self.log = (artifacts / 'injector.log').open('w')
        self.process = subprocess.Popen(['sudo', '-n', sys.executable, str(Path(__file__).resolve()),
            '--injector', keyboard, pointer], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log, text=True)
        try:
            self.ready = self.reply()
            assert self.ready['event'] == 'ready', self.ready
            # udev has processed the devices; allow the compositor to dispatch hotplug.
            time.sleep(1)
        except BaseException:
            self.close()
            raise

    def reply(self):
        assert select.select([self.process.stdout], [], [], 10)[0], 'Input helper did not reply'
        line = self.process.stdout.readline()
        assert line, 'Input helper exited; see injector.log'
        return json.loads(line)

    def send(self, events):
        self.process.stdin.write(json.dumps(dict(events=events)) + '\n')
        self.process.stdin.flush()
        assert self.reply()['event'] == 'sent'

    def key(self, code, value):
        self.send([('keyboard', 1, code, value)])
        # A receipt acknowledges injection, not the compositor's event dispatch.
        time.sleep(0.01)

    def text(self, text):
        codes = dict(zip('qwertyuiopasdfghjklzxcvbnm', [*range(16, 26), *range(30, 39), *range(44, 51)]))
        codes.update(dict(zip('1234567890', range(2, 12))))
        codes.update({' ':57, '-':12, '/':53, '\n':28, '.':52})
        for character in text:
            if character == '>':
                self.key(42, 1); self.key(52, 1); self.key(52, 0); self.key(42, 0)
            else:
                self.key(codes[character], 1); self.key(codes[character], 0)

    def click(self, point, head):
        bounds = self.ready['sources'][1]['capabilities']['3']
        axes = {code: limits for code, limits in bounds}
        events = []
        for code, coordinate, origin, extent in ((0, point[0], head['x'], head['logical_width']),
                                                 (1, point[1], head['y'], head['logical_height'])):
            low, high = axes[code][1:3]
            assert origin <= coordinate < origin + extent, (point, head)
            events.append(('pointer', 3, code, round(low + (coordinate - origin) * (high - low) / extent)))
        self.send(events)
        self.send([('pointer', 1, 272, 1), ('pointer', 1, 272, 0)])

    def close(self):
        try:
            if self.process.poll() is None:
                self.process.stdin.write('{"quit":true}\n'); self.process.stdin.flush()
        except BrokenPipeError:
            pass
        finally:
            self.process.stdin.close()
            self.process.wait(timeout=10)
            self.process.stdout.close(); self.log.close()


def run(workspace_probe, keyboard, pointer, artifacts, mode, snapshot_scales):
    artifacts.mkdir(parents=True)
    display = DisplayService(workspace_probe, artifacts / 'request.json')
    initial = display.query('--display-state')
    assert not initial['pending'] and sum(bool(h['enabled']) for h in initial['heads']) == 1
    primary = next(h for h in initial['heads'] if h['primary'] and h['enabled'])
    width, height = map(int, mode.split('x'))
    chosen = next(m for m in primary['modes'] if (m['width'], m['height']) == (width, height))
    number = display.query('--application-state', 'Terminal')['window_number']
    assert number, 'The dedicated desktop needs an idle Terminal document'
    def app(action=None):
        args = ['--application-action', 'Terminal', action] if action else ['--application-state', 'Terminal']
        return display.query(*args, '--window-number', str(number))
    original = app()
    assert not original['style_mask'] & (1 << 14)
    rect = lambda text: list(map(float, re.findall(r'-?\d+(?:\.\d+)?', text)))
    records, injector = [], None
    restored = False
    try:
        injector = Input(keyboard, pointer, artifacts)
        for density in (120, 150, 180, 210, 240):
            layout = [dict(h) for h in initial['heads']]
            head = next(h for h in layout if h['id'] == primary['id'])
            head.update({key: chosen[key] for key in ('width', 'height', 'refresh')})
            head.update(scale=density, transform=0)
            state = display.apply(layout)
            head = next(h for h in state['heads'] if h['id'] == primary['id'])
            until(lambda: app()['backing_scale'] == density / 120, 'live Terminal density')
            for full in (False, True):
                before = app()
                if full:
                    app('fullscreen')
                    def filled():
                        value = app()
                        return value if value['style_mask'] & (1 << 14) and value['frame'] == value['screen_frame'] else None
                    until(filled, 'live fullscreen fills the logical screen')
                value = app()
                x, y, w, h = rect(value['frame'])
                sx, sy, sw, sh = rect(value['screen_frame'])
                injector.click((x + w / 2, sy + sh - y - h / 2), head)
                def focused():
                    value = app()
                    return value if value['active'] and value['key'] and value['main'] else None
                focused_value = until(focused, 'kernel pointer focuses the live Terminal')
                marker = Path('/tmp/nextspace-kernel-input-' + uuid.uuid4().hex)
                injector.text('echo nextspacekernelinput > ' + str(marker) + '\n')
                until(lambda: marker.exists() and marker.read_text() == 'nextspacekernelinput\n', 'kernel keyboard reaches live PTY')
                records.append(dict(density=density, fullscreen=full, state=focused_value,
                    marker=str(marker), text=marker.read_text(), key_event_interval=0.01))
                (artifacts / 'partial-results.json').write_text(json.dumps(records, indent=2) + '\n')
                if full and density in snapshot_scales:
                    (artifacts / 'snapshot-ready.json').write_text(json.dumps(dict(density=density, state=app()), indent=2) + '\n')
                    until(lambda: (artifacts / f'continue-{density}').exists(), 'host screenshot acknowledgement', timeout=45)
                if full:
                    app('fullscreen')
                    keys = ('frame', 'content_rect', 'content_view_frame', 'content_view_bounds', 'style_mask')
                    until(lambda: all(app()[key] == before[key] for key in keys), 'exact live fullscreen restoration')
    except BaseException:
        (artifacts / 'failure.json').write_text(json.dumps(dict(application=app(), display=display.query('--display-state'),
            records=records), indent=2) + '\n')
        raise
    finally:
        try:
            if app()['style_mask'] & (1 << 14): app('fullscreen')
            display.apply(initial['heads'])
            until(lambda: display.settings(display.query('--display-state')['heads']) == display.settings(initial['heads']),
                  'original live display settings restored')
            restored = True
        finally:
            if injector: injector.close()
    assert restored and len(records) == 10
    record = dict(records=records, original_application=original, restored_application=app(),
        initial_display=initial, restored_display=display.query('--display-state'), devices=injector.ready,
        display_restored=restored, source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='Guest kernel uinput -> libinput -> compositor -> native Terminal. Synthetic Linux devices; physical host input and GPUs remain unqualified.')
    (artifacts / 'results.json').write_text(json.dumps(record, indent=2) + '\n')
    print('Live Linux input: ten normal/fullscreen PTY trials across five densities PASS')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--injector':
        inject(sys.argv[2:])
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--workspace-probe', required=True)
        parser.add_argument('--keyboard', required=True)
        parser.add_argument('--pointer', required=True)
        parser.add_argument('--artifacts', type=Path, required=True)
        parser.add_argument('--mode', default='2560x1600')
        parser.add_argument('--snapshot-scales', type=int, nargs='*', default=[])
        run(**vars(parser.parse_args()))
