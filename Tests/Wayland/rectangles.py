#!/usr/bin/env python3
"""Check native UI rectangle pixels without changing explicit path antialiasing."""
import argparse
import json
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import tempfile
import uuid
from PIL import Image
from gnustep import private_defaults, process_runtime
from integration import read_json_lines, until

NAMES = ('bezier-rectangle', 'curve', 'rotation', 'fractional-rectangle',
         'scaling', 'translation', 'ui-rectangle')


def run(compositor, probe, artifacts, pasteboard_server, pasteboard_probe,
        backend='libgnustep-wayland', reference=None, baseline=False):
    artifacts.mkdir(parents=True)
    rows = []
    with tempfile.TemporaryDirectory(prefix='nextspace-rectangles-') as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS='headless',
            WLR_HEADLESS_OUTPUTS='2', WLR_RENDERER='pixman', NEXTSPACE_SESSION_ID=str(uuid.uuid4()),
            NEXTSPACE_WAYLAND_CAPTURE_DIR=str(artifacts.resolve()))
        for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET'): env.pop(key, None)
        private_defaults(env, runtime)
        control, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        control.settimeout(5)
        with (artifacts / 'compositor.log').open('w') as log:
            server = subprocess.Popen([compositor, '-c', str(child.fileno())], env=env,
                pass_fds=[child.fileno()], stdout=subprocess.PIPE, stderr=log, text=True)
        child.close()
        client = storage = None
        def command(value):
            control.sendall(value.encode()); return json.loads(control.recv(65536))
        try:
            assert select.select([server.stdout], [], [], 10)[0]
            line = server.stdout.readline().strip(); assert line.startswith('WAYLAND_DISPLAY=')
            env['WAYLAND_DISPLAY'] = line.split('=', 1)[1]
            with (artifacts / 'pasteboard.log').open('w') as log:
                storage = subprocess.Popen([pasteboard_server, '--no-fork'], env=env, stdout=log, stderr=log)
            def storage_ready():
                assert storage.poll() is None, (artifacts / 'pasteboard.log').read_text()
                return subprocess.run([pasteboard_probe, '--ping'], env=env,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
            until(storage_ready, 'private session pasteboard storage')
            with (artifacts / 'probe.log').open('w') as log:
                client = subprocess.Popen([probe, '-GSBackend', backend, '-GSTheme', 'NextSpace',
                    '-PathRasterProbe', 'YES'], env=env, stdout=log, stderr=log)
            def window():
                assert client.poll() is None, (artifacts / 'probe.log').read_text()[-4000:]
                return next((w for w in command('windows') if w['pid'] == client.pid and
                    w['visible'] and w['title'] == 'WaylandProbe' and w['width'] > 700), None)
            until(window, 'native path raster window')
            (artifacts / 'runtime.json').write_text(json.dumps(process_runtime(client.pid), indent=2) + '\n')
            target = min(command('outputs'), key=lambda h: h['x'])['name']
            generation = 0
            for scale in (120, 150, 180, 210, 240):
                assert command(f'test-scale {target} {scale} 10000')['ok']; assert command('confirm')['ok']
                head = next(h for h in command('outputs') if h['name'] == target)
                w = window(); assert command(f"move {w['id']} {head['x'] + 10} {head['y'] + 10}")['ok']
                def capture():
                    current = window()
                    if not current or current['preferred_scale'] != scale: return None
                    path = artifacts / f"window-{current['client_id']}-{scale}.png"
                    try:
                        with Image.open(path) as image: picture = image.convert('RGB')
                    except OSError: return None
                    if picture.size != (current['buffer_width'], current['buffer_height']): return None
                    x = round((current['frame_left'] + 760) * scale / 120)
                    y = round((current['height'] - current['frame_bottom'] - 70) * scale / 120)
                    return picture if picture.getpixel((x, y)) == ((255, 0, 0) if generation % 2 else (0, 255, 0)) else None
                picture = until(capture, 'actual raster generation at native density')
                w = window(); assert not w['legacy']
                assert command(f"focus {w['id']}")['ok']
                clicks = len([e for e in read_json_lines(artifacts / 'probe.log', '{') if e['event'] == 'click'])
                assert command(f"pointer {w['x'] + w['frame_left'] + 10} {w['y'] + w['frame_top'] + 10}")['ok']
                assert command('button 272')['ok']
                until(lambda: len([e for e in read_json_lines(artifacts / 'probe.log', '{')
                    if e['event'] == 'click']) > clicks, 'path view receives input focus')
                def tiles(picture):
                    result = {}
                    for row, antialias in enumerate((True, False)):
                        for kind, name in enumerate(NAMES):
                            x, y = 20 + 100 * kind, 60 + 100 * row
                            box = tuple(round(value * scale / 120) for value in (
                                w['frame_left'] + x, w['height'] - w['frame_bottom'] - y - 70,
                                w['frame_left'] + x + 70, w['height'] - w['frame_bottom'] - y))
                            result[(name, antialias)] = picture.crop(box)
                    return result
                original = tiles(picture)
                for (name, antialias), tile in original.items():
                    filename = f'{scale}-{name}-{int(antialias)}.png'; tile.save(artifacts / filename)
                    pixels = list(tile.getdata()); gray = sum(0 < r < 255 for r, g, b in pixels)
                    assert all(r == g == b for r, g, b in pixels), (name, scale)
                    assert (0, 0, 0) in pixels and (255, 255, 255) in pixels
                    if name != 'ui-rectangle':
                        assert (gray > 0) == antialias, (name, antialias, scale, gray)
                        if reference:
                            with Image.open(reference / filename) as prior:
                                assert tile.tobytes() == prior.convert('RGB').tobytes(), (name, antialias, scale)
                    elif not baseline:
                        assert gray == 0, (name, antialias, scale, gray)
                    rows.append(dict(scale=scale, shape=name, antialias=antialias, gray_pixels=gray))
                for _ in range(2):
                    generation += 1
                    assert command('key 19 1')['ok']; assert command('key 19 0')['ok']
                    repainted = tiles(until(capture, 'new raster generation after repaint'))
                    assert all(repainted[key].tobytes() == value.tobytes() for key, value in original.items()), scale
            (artifacts / 'results.json').write_text(json.dumps(dict(cases=rows, repaints=10,
                explicit_paths_unchanged=reference is not None, baseline=baseline), indent=2) + '\n')
            print('Native rectangle pixels, explicit path antialiasing and repeated repaint: PASS')
        except BaseException:
            (artifacts / 'failure.json').write_text(json.dumps(dict(windows=command('windows'),
                outputs=command('outputs'), rows=rows), indent=2) + '\n')
            raise
        finally:
            if client and client.poll() is None: client.terminate(); client.wait(timeout=5)
            if storage and storage.poll() is None: storage.terminate(); storage.wait(timeout=5)
            if server.poll() is None: command('quit'); server.wait(timeout=5)
            server.stdout.close(); control.close()
            marker = ('NEXTSPACE_SESSION_ID=' + env['NEXTSPACE_SESSION_ID']).encode()
            for path in Path('/proc').glob('[0-9]*/environ'):
                try:
                    if marker in path.read_bytes().split(b'\0'): os.kill(int(path.parent.name), signal.SIGTERM)
                except (OSError, ProcessLookupError): pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compositor', required=True); parser.add_argument('--probe', required=True)
    parser.add_argument('--pasteboard-server', required=True); parser.add_argument('--pasteboard-probe', required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--backend', default='libgnustep-wayland')
    parser.add_argument('--reference', type=Path); parser.add_argument('--baseline', action='store_true')
    args = parser.parse_args()
    run(args.compositor, args.probe, args.artifacts, args.pasteboard_server, args.pasteboard_probe,
        args.backend, args.reference, args.baseline)
