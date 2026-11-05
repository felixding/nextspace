#!/usr/bin/env python3
"""Check production Login panel geometry and animations on native Wayland."""
import argparse
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import tempfile
import time
import uuid

from PIL import Image
from integration import read_json_lines, until


def run(compositor, probe, image, artifacts):
    artifacts.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='nextspace-login-window-') as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS='headless',
            WLR_HEADLESS_OUTPUTS='2', WLR_RENDERER='pixman', NEXTSPACE_SESSION_ID=str(uuid.uuid4()))
        for name in ('DISPLAY', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET'): env.pop(name, None)
        control, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        control.settimeout(5)
        with (artifacts/'compositor.log').open('w') as errors:
            server = subprocess.Popen([compositor, '-c', str(child.fileno())], pass_fds=[child.fileno()],
                env=env, stdout=subprocess.PIPE, stderr=errors, text=True)
        child.close()
        client = None
        def command(text):
            control.sendall(text.encode())
            return json.loads(control.recv(65536))
        try:
            assert select.select([server.stdout], [], [], 10)[0]
            line = server.stdout.readline().strip()
            assert line.startswith('WAYLAND_DISPLAY='), line
            env['WAYLAND_DISPLAY'] = line.split('=', 1)[1]
            captures = artifacts/'captures'; captures.mkdir()
            commands = artifacts/'commands.json'
            env.update(LOGIN_WINDOW_COMMANDS=str(commands), LOGIN_WINDOW_IMAGE=str(image),
                NEXTSPACE_WAYLAND_CAPTURE_DIR=str(captures))
            with (artifacts/'probe.log').open('w') as log, (artifacts/'probe.stderr').open('w') as errors:
                client = subprocess.Popen([probe, '-GSBackend', 'libgnustep-wayland', '-GSTheme', 'NextSpace'],
                    env=env, stdout=log, stderr=errors)
            def rows():
                assert client.poll() is None, f'Login panel exited: {client.returncode}'
                return read_json_lines(artifacts/'probe.log', '{')
            until(lambda: rows(), 'Login panel readiness')
            def window():
                return next((w for w in command('windows') if w['pid'] == client.pid), None)
            until(window, 'native Login mapping')
            libraries = sorted({line.split()[-1] for line in Path(f'/proc/{client.pid}/maps').read_text().splitlines()
                if any(token in line for token in ('libgnustep-base.so.', 'libgnustep-gui.so.', 'libgnustep-wayland', 'libobjc.so.'))})
            (artifacts/'runtime.json').write_text(json.dumps(dict(pid=client.pid, executable=probe, libraries=libraries), indent=2)+'\n')
            sequence, records = 0, []
            def action(name, accept):
                nonlocal sequence
                started = time.monotonic()
                sequence += 1
                temporary = commands.with_suffix('.tmp')
                temporary.write_text(json.dumps(dict(sequence=sequence, action=name)))
                temporary.replace(commands)
                widths, positions = set(), set()
                def finished():
                    current = window()
                    widths.add(current['width']); positions.add((current['x'],current['y']))
                    observed = [r for r in rows() if r['sequence'] == sequence]
                    completed = next((r for r in observed if r['event'] == name), None)
                    if not completed or not observed or observed[-1]['event'] != 'state': return None
                    latest = dict(observed[-1], before=completed['before'])
                    return latest if accept(latest) else None
                row = until(finished, 'Login '+name, timeout=20)
                row['observed_widths'] = sorted(widths)
                row['observed_positions'] = sorted(positions)
                row['duration_seconds'] = time.monotonic() - started
                return row
            output = command('outputs')[0]['name']
            for scale in (120, 150, 180, 210, 240):
                assert command(f'test-scale {output} {scale} 10000')['ok']
                assert command('confirm')['ok']
                head = next(h for h in command('outputs') if h['name'] == output)
                w = window()
                assert command(f"move {w['id']} {head['x'] + 50} {head['y'] + 50}")['ok']
                until(lambda: window()['preferred_scale'] == scale, 'Login density')
                heads = command('outputs')
                bottom = max(h['y'] + h['height'] for h in heads)
                expected_frame = [head['x'] + 50, bottom - head['y'] - 50 - 240, 400, 240]
                expected_screen = [head['x'], bottom - head['y'] - head['height'], head['width'], head['height']]
                action('state', lambda row: row['frame'] == expected_frame and row['screen'] == expected_screen)
                def centered(row):
                    x,y,width,height = row['frame']; sx,sy,sw,sh = row['screen']
                    return [x,y] == [(sx+sw/2-width/2)//1, (sy+sh/2-height/2)//1]
                row = action('center', centered)
                x,y,width,height = row['frame']; sx,sy,sw,sh = row['screen']
                assert [x,y] == [(sx+sw/2-width/2)//1, (sy+sh/2-height/2)//1], row
                assert row['style'] == 0 and row['autoresizes'] and row['scale'] == scale/120, row
                records.append(row)
                capture = captures/f"window-{row['number']}-{scale}.png"
                until(capture.exists, 'Login buffer capture')
                def captured():
                    try:
                        with Image.open(capture) as source:
                            candidate = source.convert('RGBA')
                        return candidate if candidate.size == ((400*scale+60)//120,(240*scale+60)//120) else None
                    except OSError: return None
                baseline = until(captured, 'Login buffer dimensions')
                baseline.save(artifacts/f'panel-{scale}.png')
                for name in ('shake', 'shrink'):
                    row = action(name, lambda r: all(r[key] == r['before'][key] for key in ('frame','bounds','field')))
                    for key in ('frame','bounds','field'): assert row[key] == row['before'][key], row
                    assert row['autoresizes'], row
                    assert row['duration_seconds'] < 5, (name, scale, row)
                    if name == 'shrink': assert len(row['observed_widths']) > 1, row
                    else: assert len(row['observed_positions']) > 1, row
                    until(lambda: window()['width'] == 400 and window()['height'] == 240, 'Login frame restored')
                    final = until(captured, 'Login buffer restored')
                    final.save(artifacts/f'{name}-{scale}.png')
                    assert final.tobytes() == baseline.tobytes(), (name, scale, row)
                    records.append(row)
            (artifacts/'results.json').write_text(json.dumps(records, indent=2)+'\n')
            print(f'Native Login window: {len(records)} scale/animation checks PASS')
        finally:
            if client and client.poll() is None:
                client.terminate(); client.wait(timeout=5)
            if server.poll() is None:
                control.sendall(b'quit'); server.wait(timeout=5)
            control.close(); server.stdout.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('compositor','probe','image','artifacts'): p.add_argument('--'+name, type=Path, required=True)
    args = p.parse_args()
    run(str(args.compositor.resolve()), str(args.probe.resolve()), args.image.resolve(), args.artifacts.resolve())
