#!/usr/bin/env python3
"""Check real animated cursor buffers in every AppKit run loop and density."""
import argparse
import json
import os
from pathlib import Path
import select
import socket
import struct
import subprocess
import tempfile
import time

from gnustep import private_defaults, process_runtime
from integration import until
from text_input import stop_process


FRAMES = ((24, 24, 3, 5, 100, 0xffff0000),
          (26, 22, 4, 6, 170, 0xff00ff00),
          (22, 26, 6, 7, 230, 0xff0000ff))


def observe_asset(command, path, scale, trace_path):
    """Match actual native cursor buffers, geometry and hotspots to an asset."""
    from cursor_assets import frames
    size = (24 * scale + 60) // 120
    base, dense = frames(path, 24), frames(path, size)
    assert len(base) == len(dense), (path, scale)
    expected = {frame['pixels_hash']: (logical, frame) for logical, frame in zip(base, dense)}
    seen, trace = {}, []
    def ready():
        state = command('cursor-state')
        trace.append(state)
        pair = expected.get(state.get('pixels_hash'))
        if pair:
            logical, frame = pair
            assert tuple(state[key] for key in ('width', 'height', 'hotspot_x', 'hotspot_y')) == tuple(
                logical[key] for key in ('width', 'height', 'hotspot_x', 'hotspot_y')), state
            assert (state['buffer_width'], state['buffer_height']) == (frame['width'], frame['height']), state
            seen[state['pixels_hash']] = state
        return len(seen) == len(expected)
    try:
        until(ready, 'NextSpace cursor artwork and animation')
    finally:
        trace_path.write_text(json.dumps(trace, indent=2)+'\n')
    return list(seen.values())


def write_cursor(path, frames):
    """Small Xcursor fixture; only the file format is shared with X11."""
    chunks = []
    for size in (24, 30, 36, 42, 48):
        for width, height, x, y, delay, color in frames:
            edge = lambda value: (value * size + 12) // 24
            width = edge(width); height = edge(height)
            chunks.append((size, struct.pack('<9I', 36, 0xfffd0002,
                size, 1, width, height, edge(x), edge(y), delay) +
                struct.pack('<I', color) * (width * height)))
    offset = 16 + 12 * len(chunks)
    toc = bytearray()
    for size, data in chunks:
        toc.extend(struct.pack('<3I', 0xfffd0002, size, offset))
        offset += len(data)
    path.parent.mkdir(parents=True)
    path.write_bytes(struct.pack('<4I', 0x72756358, 16, 0x10000, len(chunks)) + toc +
        b''.join(data for _, data in chunks))


def run(compositor, probe, artifacts, theme=Path('/usr/share/icons/NextSpace')):
    artifacts.mkdir(parents=True)
    themes = artifacts / 'themes'
    write_cursor(themes / 'Animated/cursors/left_ptr', FRAMES)
    (themes / 'default').symlink_to('Animated', target_is_directory=True)
    write_cursor(themes / 'Alternate/cursors/left_ptr', ((24, 24, 2, 4, 0, 0xff00ffff),))
    results = []
    with tempfile.TemporaryDirectory(prefix='nextspace-cursors-') as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS='headless',
            WLR_RENDERER='pixman', WLR_HEADLESS_OUTPUTS='2', XCURSOR_PATH=str(themes.resolve()),
            XCURSOR_THEME='Animated')
        for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET'):
            env.pop(key, None)
        private_defaults(env, runtime)
        control, peer = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        control.settimeout(5)
        server = client = None

        def command(text):
            control.sendall(text.encode())
            return json.loads(control.recv(65536))

        def key(code):
            assert command(f'key {code} 1')['ok']
            assert command(f'key {code} 0')['ok']

        def start_client(label, settings, mode=0):
            nonlocal client
            with (artifacts / (label + '.log')).open('w') as log:
                client = subprocess.Popen([probe, '-GSBackend', 'libgnustep-wayland',
                    '-GSTheme', 'NextSpace', '-CursorProbe', 'YES', '-CursorRunLoopMode', str(mode)],
                    env=settings, stdout=log, stderr=log)
            window = until(lambda: next((w for w in command('windows') if w['pid'] == client.pid and
                w['buffer_width'] == 801), None), 'cursor probe first buffer')
            assert command(f"move {window['id']} {target['x'] + 10} 10")['ok']
            assert command(f"focus {window['id']}")['ok']
            assert command(f"pointer {target['x'] + 210} 310")['ok']
            key(11)

        def asset_frames(path, scale):
            return observe_asset(command, path, scale,
                artifacts / ('asset-' + path.name + '-' + str(scale) + '.json'))

        def observe(scale):
            seen = {}
            trace = []
            start = time.monotonic()
            while time.monotonic() - start < 2:
                state = command('cursor-state')
                trace.append(dict(time=time.monotonic() - start, cursor=state))
                if state.get('visible') and state.get('samples'):
                    color = state['samples'][0]
                    frame = next((f for f in FRAMES if f[-1] == color), None)
                    if frame:
                        width, height, x, y, _, _ = frame
                        edge = lambda value: (value * scale + 60) // 120
                        expected = (width, height, edge(width), edge(height), x, y)
                        actual = tuple(state[k] for k in ('width', 'height', 'buffer_width',
                            'buffer_height', 'hotspot_x', 'hotspot_y'))
                        # Scale/viewport changes are asynchronous; retain the
                        # transition, but qualify only the requested density.
                        if actual == expected:
                            assert state['samples'] == [color] * 4, state
                            seen[color] = state
                if len(seen) == len(FRAMES):
                    return trace
                time.sleep(0.01)
            (artifacts / 'animation-failure.json').write_text(json.dumps(trace, indent=2) + '\n')
            (artifacts / 'failure-state.json').write_text(json.dumps(dict(windows=command('windows'),
                outputs=command('outputs'), runtime=process_runtime(client.pid)), indent=2) + '\n')
            raise AssertionError(f'Cursor frames missing at scale {scale}: {list(seen)}')

        try:
            with (artifacts / 'compositor.log').open('w') as log:
                server = subprocess.Popen([compositor, '-c', str(peer.fileno())], env=env,
                    pass_fds=[peer.fileno()], stdout=subprocess.PIPE, stderr=log, text=True)
            peer.close()
            assert select.select([server.stdout], [], [], 10)[0]
            env['WAYLAND_DISPLAY'] = server.stdout.readline().strip().split('=', 1)[1]
            outputs = command('outputs')
            target = max(outputs, key=lambda output: output['x'])
            (artifacts / 'compositor-runtime.json').write_text(json.dumps(process_runtime(server.pid), indent=2))
            for mode in range(4):
                start_client(f'client-{mode}', env, mode)
                for scale in (120, 150, 180, 210, 240, 120):
                    assert command(f"test-scale {target['name']} {scale} 10000")['ok']
                    assert command('confirm')['ok']
                    results.append(dict(mode=mode, scale=scale, frames=observe(scale)))
                key(8)  # Hide; the animation must not reveal it again.
                until(lambda: not command('cursor-state')['visible'], 'hide animated cursor')
                time.sleep(0.6)
                assert not command('cursor-state')['visible']
                key(9)
                observe(120)
                key(10)  # Switching to a custom image cancels theme animation.
                custom = until(lambda: (s if (s := command('cursor-state')).get('width') == 19 else None),
                    'custom cursor')
                time.sleep(0.6)
                state = command('cursor-state')
                assert (state['width'], state['height'], state['samples']) == (19, 17, custom['samples'])
                key(11)
                observe(120)
                assert command('pointer 900 700')['ok']
                time.sleep(0.2)
                assert client.poll() is None
                assert command(f"pointer {target['x'] + 210} 310")['ok']
                observe(120)
                (artifacts / f'client-{mode}-runtime.json').write_text(json.dumps(process_runtime(client.pid), indent=2))
                stop_process(client); client = None
            # A second explicit theme must override the default theme.
            alternate = dict(env, XCURSOR_THEME='Alternate')
            start_client('alternate', alternate)
            state = until(lambda: (s if (s := command('cursor-state')).get('samples') == [0xff00ffff] * 4 else None),
                'explicit cursor theme')
            assert (state['width'], state['height'], state['hotspot_x'], state['hotspot_y']) == (24, 24, 2, 4)
            stop_process(client); client = None
            from cursor_assets import validate
            artwork = validate(theme)
            assets = []
            start_client('nextspace', dict(env, XCURSOR_THEME='NextSpace', XCURSOR_PATH=str(theme.parent.resolve())))
            for code, name in ((11, 'left_ptr'), (23, 'xterm'), (35, 'hand'), (19, 'sb_h_double_arrow'),
                               (46, 'crosshair'), (24, 'grab'), (25, 'grabbing'), (50, 'context-menu')):
                key(code)
                for scale in (120, 150, 180, 210, 240):
                    assert command(f"test-scale {target['name']} {scale} 10000")['ok']
                    assert command('confirm')['ok']
                    assets.append(dict(name=name, scale=scale, frames=asset_frames(theme / 'cursors' / name, scale)))
            stop_process(client); client = None
            busy = themes / 'Busy/cursors/left_ptr'
            busy.parent.mkdir(parents=True)
            busy.symlink_to((theme / 'cursors/watch').resolve())
            assert command(f"test-scale {target['name']} 120 10000")['ok']
            assert command('confirm')['ok']
            start_client('busy', dict(env, XCURSOR_THEME='Busy'))
            for scale in (120, 150, 180, 210, 240):
                assert command(f"test-scale {target['name']} {scale} 10000")['ok']
                assert command('confirm')['ok']
                assets.append(dict(name='watch', scale=scale, frames=asset_frames(theme / 'cursors/watch', scale)))
            (artifacts / 'assets-runtime.json').write_text(json.dumps(process_runtime(client.pid), indent=2))
            (artifacts / 'results.json').write_text(json.dumps(dict(complete=True, animation=results,
                alternate=state, artwork=artwork, assets=assets), indent=2) + '\n')
            print('Native cursors: four run loops, five densities, theme override, 40 static and five animated artwork cases PASS')
        finally:
            if client:
                stop_process(client)
            if server:
                if server.poll() is None:
                    command('quit'); server.wait(timeout=5)
                server.stdout.close()
            control.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compositor', required=True)
    parser.add_argument('--probe', required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--theme', type=Path, default=Path('/usr/share/icons/NextSpace'))
    args = parser.parse_args()
    run(args.compositor, args.probe, args.artifacts, args.theme)
