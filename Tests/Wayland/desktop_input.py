"""Real desktop seat input and compositor capture, without client focus assistance."""
import json
from pathlib import Path
import plistlib
import socket
import time
from PIL import Image


class Desktop:
    def __init__(self, root):
        self.root = Path(root)

    def command(self, value):
        with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as peer:
            peer.settimeout(12)
            peer.connect(str(self.root / 'control.sock'))
            peer.send(json.dumps({'command': value}).encode())
            return json.loads(peer.recv(1048576))

    def click(self, x, y):
        assert self.command('pointer %d %d' % (x, y))['ok']
        for state in (1, 0):
            assert self.command('button 272 %d' % state)['ok']
            time.sleep(.08)

    def double_click(self, x, y):
        # A single request preserves the gesture's event timestamps. Separate
        # requests can be split by expensive frames even when both are queued
        # before reading replies. GNUstep still recognizes the actual clicks.
        assert self.command('pointer %d %d' % (x, y))['ok']
        reply = self.command('clicks 272 2')
        assert reply['ok']
        return reply

    def key(self, code):
        for state in (1, 0):
            assert self.command('key %d %d' % (code, state))['ok']
            time.sleep(.08)

    def command_modifier(self):
        defaults = self.root / 'runtime/defaults/NSGlobalDomain.plist'
        settings = plistlib.loads(defaults.read_bytes()) if defaults.is_file() else {}
        key = settings.get('GSFirstCommandKey', 'Alt_L')
        return {'Alt_L': 56, 'Alt_R': 100, 'Control_L': 29, 'Control_R': 97,
                'Super_L': 125, 'Super_R': 126, 'Meta_L': 125, 'Meta_R': 126}[key]

    def chord(self, code, *modifiers):
        pressed = []
        try:
            for key in modifiers:
                assert self.command(f'key {key} 1')['ok']
                pressed.append(key)
            self.key(code)
        finally:
            for key in reversed(pressed):
                assert self.command(f'key {key} 0')['ok']

    def capture(self, name):
        output = self.command('outputs')[0]
        raw = self.root / (name + '.raw')
        before = len((self.root / 'capture.jsonl').read_text().splitlines())
        with (self.root / 'capture.fifo').open('w') as fifo:
            fifo.write('capture %s %s\n' % (output['name'], raw))
        started = time.monotonic()
        deadline = started + 12
        observed = []
        while time.monotonic() < deadline:
            frames = []
            for line in (self.root / 'capture.jsonl').read_text().splitlines()[before:]:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue  # The capture process may still be appending a line.
                if row.get('event') == 'frame':
                    frames.append(row)
            if frames:
                observed = frames
                frame = frames[-1]
                data = raw.read_bytes() if raw.exists() else b''
                if len(data) == frame['stride'] * frame['height'] and any(data):
                    path = self.root / (name + '.png')
                    Image.frombytes('RGBA' if frame['format'] == 0 else 'RGB',
                        (frame['width'], frame['height']), data, 'raw',
                        'BGRA' if frame['format'] == 0 else 'BGRX', frame['stride'],
                        -1 if frame['flags'] & 1 else 1).convert('RGB').save(path)
                    raw.unlink()
                    return path
            time.sleep(.05)
        diagnostic = dict(name=name, elapsed_seconds=time.monotonic()-started,
            before_lines=before, frames=observed,
            log=(self.root/'capture.jsonl').read_text(),
            raw_size=raw.stat().st_size if raw.exists() else None)
        (self.root/(name+'-capture-failure.json')).write_text(json.dumps(diagnostic,indent=2)+'\n')
        raise TimeoutError('complete compositor frame')
