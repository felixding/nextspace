#!/usr/bin/env python3
"""Measure ordinary NSMatrix radio behavior with real Wayland seat input."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import socket
import sys

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Wayland'))
from gnustep import headless_session, process_runtime
from integration import until
from text_input import Client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('probe', 'compositor', 'capture-probe', 'backend-bundle', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    rows, screenshots = [], []

    def check(name, passed, **evidence):
        row = dict(case=name, passed=bool(passed), **evidence)
        rows.append(row)
        (args.output / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
        assert passed, row

    broker, peer = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    environment = dict(GNUSTEP_CONFIG_FILE='/Library/Preferences/GNUstep.conf',
                       LD_LIBRARY_PATH='/Library/Libraries:/usr/NextSpace/lib',
                       WLR_HEADLESS_OUTPUTS='1')
    try:
        with headless_session(args.compositor, args.output, extra_env=environment,
                              shell_broker=peer) as (env, command):
            peer.close()
            for key in ('LD_PRELOAD', 'NEXTSPACE_NATIVE_UI_PROVIDER'):
                env.pop(key, None)
            bundles = Path(env['XDG_RUNTIME_DIR']) / 'empty-library/Bundles'
            bundles.mkdir(parents=True)
            (bundles / args.backend_bundle.name).symlink_to(args.backend_bundle.resolve(), target_is_directory=True)
            capture = Client(str(args.capture_probe), None, env, args.output, 'capture', broker, b'V')
            probe = None
            try:
                output = command('outputs')[0]['name']
                for density in (120, 240):
                    assert command(f'test-scale {output} {density} 10000')['ok']
                    assert command('confirm')['ok']
                    directory = args.output / str(density)
                    directory.mkdir()
                    probe = Client(str(args.probe), None, env, directory, 'reference',
                                   ready_event='model', arguments=['-GSBackend', 'wayland', '-GSTheme', 'NextSpace'])
                    (directory / 'runtime.json').write_text(json.dumps(process_runtime(probe.process.pid), indent=2) + '\n')

                    def window():
                        return next((w for w in command('windows') if w['pid'] == probe.process.pid and w['visible']), None)

                    current = until(window, 'native radio reference window')
                    assert command(f"move {current['id']} 40 40")['ok']
                    assert command(f"focus {current['id']}")['ok']
                    objects = None

                    def request(text, event):
                        probe.pump()
                        start = len(probe.events)
                        probe.send(text)
                        return probe.wait(event, start)

                    def inspect(name, state, selected, key_cell, actions, responder='matrix'):
                        actual = {k: state[k] for k in ('selected', 'key_cell', 'actions', 'responder')}
                        expected = dict(selected=selected, key_cell=key_cell, actions=actions, responder=responder)
                        check(name, actual == expected and state['same_cells'] and state['matrix_class'] == 'NSMatrix'
                              and state['cell_objects'] == objects
                              and len(set(objects)) == len(objects)
                              and [c['state'] for c in state['states']] == [int(i == selected) for i in range(len(objects))],
                              density=density, actual=actual, expected=expected)
                        return state

                    def model(name, nrows=4, columns=1, selected=0, focused=0, disabled=2, tab=1):
                        nonlocal objects
                        state = request(f'model {nrows} {columns} {selected} {focused} {disabled} {tab}', 'model')
                        objects = state['cell_objects']
                        return inspect(name, state, selected, focused, 0)

                    def key(name, code, selected, focused, actions, modifier=None, responder='matrix'):
                        probe.pump()
                        start = len(probe.events)
                        try:
                            if modifier:
                                assert command(f'key {modifier} 1')['ok']
                            for down in (1, 0):
                                assert command(f'key {code} {down}')['ok']
                            state = probe.wait('release', start)
                        finally:
                            if modifier:
                                assert command(f'key {modifier} 0')['ok']
                        return inspect(name, state, selected, focused, actions, responder)

                    def pointer(name, start_index, end_index, selected, focused, actions):
                        state = request('sync', 'sync')
                        current = window()

                        def move(index):
                            if index is None:
                                x, y = -20, -20
                            else:
                                x, y, width, height = state['frames'][index]
                                x += width / 2
                                y += height / 2
                            assert command(f"pointer {round(current['x'] + x)} {round(current['y'] + y)}")['ok']

                        probe.pump()
                        begin = len(probe.events)
                        move(start_index)
                        assert command('button 272 1')['ok']
                        move(end_index)
                        assert command('button 272 0')['ok']
                        probe.wait('pointer', begin)
                        return inspect(name, request('sync', 'sync'), selected, focused, actions)

                    def screenshot(name):
                        request('draw', 'draw')
                        current = until(lambda: (w if (w := window()) and
                            w['buffer_width'] == round(w['frame_width'] * density / 120) and
                            w['buffer_height'] == round(w['frame_height'] * density / 120) else None),
                            'native reference backing density')
                        assert command('pointer 800 600')['ok']
                        raw = directory / (name + '.raw')
                        start = len(capture.events)
                        capture.send('capture ' + output + ' ' + str(raw))
                        frame = capture.wait('frame', start)
                        desktop = Image.frombytes('RGBA' if frame['format'] == 0 else 'RGB',
                            (frame['width'], frame['height']), raw.read_bytes(), 'raw',
                            'BGRA' if frame['format'] == 0 else 'BGRX', frame['stride'],
                            -1 if frame['flags'] & 1 else 1).convert('RGB')
                        desktop.save(directory / (name + '-desktop.png'))
                        raw.unlink()
                        left, top = round(current['x'] * density / 120), round(current['y'] * density / 120)
                        image = desktop.crop((left, top, left + current['buffer_width'], top + current['buffer_height']))
                        image.save(directory / (name + '-window.png'))
                        check(name + '-real-desktop-image', len(image.getcolors(image.width * image.height)) > 5,
                              density=density, size=image.size)
                        screenshots.append(dict(name=name, density=density, window=current, frame=frame,
                            sha256=hashlib.sha256(image.tobytes()).hexdigest()))
                        (args.output / 'screenshots.json').write_text(json.dumps(screenshots, indent=2) + '\n')

                    model('vertical-model')
                    screenshot('vertical-initial')
                    key('down-skips-disabled', 108, 2, 2, 1)
                    screenshot('vertical-native-arrow')
                    key('down-selects-last', 108, 3, 3, 2)
                    key('down-does-not-wrap', 108, 3, 3, 2)
                    key('up-selects-previous', 103, 2, 2, 3)
                    key('up-skips-disabled', 103, 0, 0, 4)
                    key('up-does-not-wrap', 103, 0, 0, 4)
                    key('vertical-right-falls-through', 106, 0, 0, 4)
                    key('vertical-left-falls-through', 105, 0, 0, 4)
                    key('space-sends-native-action', 57, 0, 0, 5)

                    model('horizontal-model', 1, 4)
                    key('horizontal-down-boundary', 108, 0, 0, 0)
                    key('horizontal-up-boundary', 103, 0, 0, 0)
                    key('right-skips-disabled', 106, 2, 2, 1)
                    key('right-selects-last', 106, 3, 3, 2)
                    key('right-does-not-wrap', 106, 3, 3, 2)
                    key('left-selects-previous', 105, 2, 2, 3)
                    key('left-skips-disabled', 105, 0, 0, 4)
                    key('left-does-not-wrap', 105, 0, 0, 4)
                    screenshot('horizontal-native-group')

                    model('grid-model', 2, 2)
                    key('grid-down-selects-row', 108, 2, 2, 1)
                    key('grid-right-selects-column', 106, 3, 3, 2)
                    key('grid-up-disabled-column', 103, 3, 3, 2)
                    key('grid-left-selects-column', 105, 2, 2, 3)
                    key('grid-up-selects-row', 103, 0, 0, 4)
                    key('grid-right-disabled-row', 106, 0, 0, 4)

                    model('shift-model')
                    key('shift-down-focus-without-selection', 108, 0, 2, 1, modifier=42)
                    screenshot('native-focus-separate-from-selection')
                    key('shift-down-next-focus', 108, 0, 3, 2, modifier=42)
                    key('shift-down-boundary', 108, 0, 3, 2, modifier=42)
                    key('space-selects-native-key-cell', 57, 3, 3, 3)

                    # Physical Meta maps to GNUstep Alternate. Physical Alt+Up/
                    # Down are desktop raise/lower shortcuts in this session.
                    model('alternate-model')
                    alternate = key('native-alternate-can-focus-disabled-cell', 108, 0, 1, 1, modifier=125)
                    check('alternate-modifier-observed', alternate['modifiers'] == 1 << 19, density=density)
                    key('native-alternate-space-retains-selection', 57, 0, 1, 2, modifier=125)

                    model('empty-model', selected=-1, focused=-1)
                    key('space-with-no-key-cell-does-nothing', 57, -1, -1, 0)
                    key('empty-down-selects-first-native-cell', 108, 0, 0, 1)
                    model('empty-selected-explicit-focus', selected=-1, focused=2)
                    key('empty-selection-space-uses-focus', 57, 2, 2, 1)
                    model('all-disabled-model', focused=-1, disabled=15)
                    key('all-disabled-down-does-nothing', 108, 0, -1, 0)
                    key('all-disabled-space-does-nothing', 57, 0, -1, 0)

                    for tab in (0, 1):
                        model(f'tab-model-{tab}', tab=tab)
                        key(f'tab-leaves-matrix-{tab}', 15, 0, 0, 0, responder='next')
                        key(f'backtab-restores-matrix-{tab}', 15, 0, 0, 0, modifier=42)
                        key(f'return-does-not-activate-radio-{tab}', 28, 0, 0, 0)

                    model('changed-enabled-model')
                    state = request('enabled 2 0', 'enabled')
                    inspect('disabled-model-update-is-silent', state, 0, 0, 0)
                    key('down-uses-updated-disabled-cells', 108, 3, 3, 1)
                    request('enabled 2 1', 'enabled')
                    key('up-uses-restored-enabled-cell', 103, 2, 2, 2)

                    model('pointer-model')
                    pointer('native-click-selects-cell', 2, 2, 2, 2, 1)
                    pointer('native-click-selected-cell-sends-action', 2, 2, 2, 2, 2)
                    pointer('native-disabled-click-retains-selection-and-sends-group-action', 1, 1, 2, 2, 3)
                    screenshot('pointer-native-selection')
                    model('pointer-drag-model')
                    pointer('native-drag-to-other-member-restores-selection', 0, 3, 0, 0, 1)
                    pointer('native-outside-release-restores-selection', 2, None, 0, 0, 2)
                    probe.send('quit')
                    check('native-reference-clean-exit', probe.process.wait(timeout=5) == 0, density=density)
                    probe.stop()
                    probe = None
            finally:
                if probe:
                    probe.stop()
                capture.stop()
                (args.output / 'cleanup.json').write_text(json.dumps(dict(
                    capture_exit=capture.process.returncode, reference_stopped=probe is None), indent=2) + '\n')
    finally:
        broker.close()
        peer.close()
    print(json.dumps(dict(checks=len(rows), desktop_images=len(screenshots))))


if __name__ == '__main__':
    main()
