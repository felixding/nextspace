#!/usr/bin/env python3
"""Keep Page Layout usable across logical work areas without changing its document geometry."""
import argparse
import json
import subprocess
from pathlib import Path
from PIL import Image, ImageChops
from gnustep import headless_session, pasteboard_storage, process_runtime
from integration import until, read_json_lines

def run(compositor, probe, pasteboard_server, pasteboard_probe, artifacts):
    root = artifacts
    root.mkdir(parents=True)
    records = []
    original_constraints = None
    for name, height, sequence, code in [('large', 1800, [120, 150, 180, 210, 240, 120], 38), ('live', 1200, [120, 150, 180, 210, 240, 120], 38), ('small', 918, [240], 38), ('sheet', 918, [240], 31)]:
        directory = root / name
        directory.mkdir()
        snapshots = []
        with headless_session(compositor, directory / 'session') as (env, command):
            target = command('outputs')[0]
            assert command(f"resize-output {target['name']} 1600 {height}")['ok']
            assert command(f"test-scale {target['name']} {sequence[0]} 15000")['ok']
            assert command('confirm')['ok']
            with pasteboard_storage(pasteboard_server, pasteboard_probe, env, directory):
                with (directory / 'probe.log').open('w') as log, (directory / 'probe.stderr').open('w') as err:
                    process = subprocess.Popen([str(probe), '-GSBackend', 'libgnustep-wayland', '-GSTheme', 'NextSpace'], env=env, stdout=log, stderr=err)

                def windows():
                    assert process.poll() is None, (directory / 'probe.stderr').read_text()[-3000:]
                    return [w for w in command('windows') if w['pid'] == process.pid]

                def events():
                    return read_json_lines(directory / 'probe.log', '{')

                def key(number):
                    assert command(f'key {number} 1')['ok']
                    assert command(f'key {number} 0')['ok']
                try:
                    until(lambda: any((e.get('event') == 'ready' for e in events())), 'printing event loop')
                    main = until(lambda: next((w for w in windows() if w['title'] == 'PrintingProbe' and not w['style'] & 64 and w['width'] > 200), None), 'printing document')
                    output = next((o for o in command('outputs') if o['name'] == target['name']))
                    assert command(f"move {main['id']} {output['x'] + 30} {output['y'] + 30}")['ok']
                    until(lambda: next((w for w in windows() if w['id'] == main['id'] and w['preferred_scale'] == sequence[0] and (w['buffer_width'] == (w['width'] * sequence[0] + 60) // 120)), None), 'parent document on tested output')
                    before = {w['id'] for w in windows()}
                    assert command(f"focus {main['id']}")['ok']
                    key(code)
                    panel = until(lambda: next((w for w in windows() if w['id'] not in before and w['width'] > 200), None), 'Page Layout', timeout=20)
                    (directory / 'runtime.json').write_text(json.dumps(process_runtime(process.pid), indent=2) + '\n')

                    def metadata():
                        count = len(events())
                        key(50)
                        return until(lambda: next((e for e in events()[count:] if e.get('event') == 'panel-control' and e.get('metadata_request')), None), 'requested readonly Cancel geometry')
                    for index, density in enumerate(sequence):
                        assert command(f"test-scale {target['name']} {density} 15000")['ok']
                        assert command('confirm')['ok']
                        output = next((o for o in command('outputs') if o['name'] == target['name']))
                        assert command(f"move {panel['id']} {output['x'] + 10} {output['y'] + 10}")['ok']

                        def rendered():
                            current = next((w for w in windows() if w['id'] == panel['id']), None)
                            if not current or current['preferred_scale'] != density or current['height'] > output['height'] or (current['width'] > output['width']):
                                return None
                            picture = directory / 'session/captures' / f"window-{current['client_id']}-{density}.png"
                            try:
                                with Image.open(picture) as image:
                                    if image.size != (current['buffer_width'], current['buffer_height']):
                                        return None
                                    colors = image.convert('RGB').getcolors(image.width * image.height)
                                    white = next((n for n, c in colors if c == (255, 255, 255)), 0)
                                    if white < 5000 * (density / 120) ** 2:
                                        return None
                                return (current, picture)
                            except OSError:
                                return None
                        current, picture = until(rendered, 'entire panel fits the logical work area', timeout=20)
                        controls = metadata()
                        if len(sequence) > 1:
                            controls = until(lambda: (m if (m := metadata())['key_window'] else None),
                                'client key-window focus before pixel comparison', timeout=20)
                        # The geometry reply follows a synchronous full panel draw/flush.
                        current, picture = until(rendered, 'completed focused Page Layout pixels', timeout=20)
                        expected = 645 > output['height'] or 317 > output['width']
                        assert (controls['content_class'] == 'NSScrollView') == expected, (name, density, controls, output)
                        assert (controls['document_width'], controls['document_height']) == (315, 621), controls
                        path = directory / f'{index}-{density}.png'
                        path.write_bytes(picture.read_bytes())
                        snapshots.append(path)
                        records.append(dict(case=name, density=density, window=current, controls=controls, output=output))
                    if len(sequence) > 1:
                        with Image.open(snapshots[0]) as a, Image.open(snapshots[-1]) as b:
                            assert a.size == b.size
                            maximum = max((v[1] for v in ImageChops.difference(a.convert('RGBA'), b.convert('RGBA')).getextrema()))
                            assert maximum <= 1, ('ordinary layout failed exact restoration', name, maximum)
                        (directory / 'restoration.json').write_text(json.dumps(dict(maximum_channel_difference=maximum, original_size_restored=True), indent=2) + '\n')

                    def reachable(row):
                        return row['y'] >= 0 and row['y'] + row['height'] <= row['content_height']
                    direction = 5
                    distance = lambda row: max(0, -row['y']) + max(0, row['y'] + row['height'] - row['content_height'])
                    for attempt in range(12):
                        if reachable(controls):
                            break
                        assert controls['scroll_width'] > 0, controls
                        x = current['x'] + current['frame_left'] + controls['scroll_x'] + controls['scroll_width'] / 2
                        y = current['y'] + current['frame_top'] + (controls['scroll_y'] + controls['scroll_height'] / 2 if controls['content_flipped'] else controls['content_height'] - controls['scroll_y'] - controls['scroll_height'] / 2)
                        assert command(f'pointer {round(x)} {round(y)}')['ok']
                        previous = distance(controls)
                        assert command('scroll ' + str(direction))['ok']
                        controls = metadata()
                        if distance(controls) >= previous:
                            direction = -direction
                    assert reachable(controls), controls
                    x = current['x'] + current['frame_left'] + controls['x'] + controls['width'] / 2
                    y = current['y'] + current['frame_top'] + (controls['y'] + controls['height'] / 2 if controls['content_flipped'] else controls['content_height'] - controls['y'] - controls['height'] / 2)
                    assert output['x'] <= x < output['x'] + output['width'] and output['y'] <= y < output['y'] + output['height']
                    assert command(f'pointer {round(x)} {round(y)}')['ok']
                    assert command('button 272')['ok']
                    until(lambda: any((e.get('event') == 'panel' and e.get('kind') == ('s' if name == 'sheet' else 'l') and (e.get('result') == 0) for e in events())), 'ordinary Cancel ends modal/sheet')
                    restored = next((e for e in reversed(events()) if e.get('event') == 'page-layout-restored'))
                    restored = {key: value for key, value in restored.items() if key != 'event'}
                    assert restored['content_class'] != 'NSScrollView'
                    assert (restored['width'], restored['height'], restored['document_width'], restored['document_height']) == (317, 645, 315, 621)
                    if original_constraints is None:
                        original_constraints = restored
                    assert restored == original_constraints, restored
                    until(lambda: not any(w['id'] == panel['id'] and w['visible'] for w in windows()), 'closed modal surface is hidden')
                    until(lambda: any(w['id'] == main['id'] and w['focused'] for w in windows()), 'focus returns to the document')
                    (directory / 'result.json').write_text(json.dumps(dict(passed=True, scroll_attempts=attempt, cancel=controls, native_appkit_panel=True), indent=2) + '\n')
                except BaseException:
                    (directory / 'failure.json').write_text(json.dumps(dict(windows=command('windows'), records=records), indent=2) + '\n')
                    raise
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=5)
    (root / 'result.json').write_text(json.dumps(dict(passed=True, cases=records, ordinary_geometry_and_pixels_restored=True, live_changes=True, small_mode=True, sheet=True, full_plan_complete=False), indent=2) + '\n')
    print('Real GUI Page Layout: normal appearance, live scale fitting, small desktop and sheet cancellation PASS', flush=True)
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('compositor', 'probe', 'pasteboard-server', 'pasteboard-probe', 'artifacts'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    run(args.compositor.resolve(), args.probe.resolve(), args.pasteboard_server.resolve(), args.pasteboard_probe.resolve(), args.artifacts.resolve())
