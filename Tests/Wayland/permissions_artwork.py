"""Exercise original permission artwork in Workspace's real UNIX Permissions Inspector."""
import json
import math
from pathlib import Path
import subprocess
from PIL import Image, ImageChops, ImageFilter
from application_artwork import placed_reference, representations
from integration import until
from permission_fidelity import run as fidelity

NAMES = dict(check='PermYes', cross='PermNo', dash='PermNoChange')


def compare_cells(state, window, actual, density, images, artifacts):
    vx, vy, width, height = state['view']
    column_width, row_height = int(width / 3), int(height / 3)
    factor = density / 120
    comparisons = []
    for row, permission in enumerate((2, 1, 0)):
        for column, user in enumerate((6, 3, 0)):
            bit = 1 << (user + permission)
            key = 'dash' if state['nochange'] & bit else 'check' if state['mode'] & bit else 'cross'
            # WMPermissions is flipped; compositeToPoint anchors an upright image.
            x = vx + column_width * (column + .5) - 22
            y = vy + height - (row_height * (row + .5) + 8)
            origin = x * factor, (window['height'] - y - 16) * factor
            left, top = map(math.floor, origin)
            size = (math.ceil(origin[0] - left + 44 * factor),
                    math.ceil(origin[1] - top + 16 * factor))
            offset = origin[0] - left, origin[1] - top
            directory = artifacts / f'{row}-{column}'
            directory.mkdir(parents=True)
            crop = actual.crop((left, top, left + size[0], top + size[1]))
            expected = placed_reference(images[key], offset,
                Image.new('RGBA', size, (170, 170, 170, 255)), directory, density,
                size=(44 * factor, 16 * factor), pad=True,
                clip=(*offset, 44 * factor, 16 * factor))
            # The 44-point images overlap the table's 40-point cells. The table
            # border is drawn afterward; compare the symbol plus one pixel halo.
            mask = ImageChops.difference(expected.convert('RGB'),
                Image.new('RGB', size, (170, 170, 170))).convert('L')
            mask = mask.point(lambda value: 255 if value else 0).filter(ImageFilter.MaxFilter(3))
            difference = Image.composite(ImageChops.difference(crop, expected),
                                        Image.new('RGBA', size), mask)
            maximum = max(high for _, high in difference.getextrema())
            crop.save(directory / 'actual.png')
            expected.save(directory / 'expected.png')
            mask.save(directory / 'mask.png')
            assert maximum <= 1, (density, row, column, key, maximum)
            pixels = sum(mask.histogram()[1:])
            assert pixels > 0
            comparisons.append(dict(row=row, column=column, key=key,
                                    maximum=maximum, ink_and_halo_pixels=pixels))
    return comparisons


def run(command, env, probe, density_probe, owner, artifacts):
    artifacts.mkdir(parents=True)
    fixture = artifacts / 'fixture'
    fixture.mkdir()
    modes = dict(first=0o644, second=0o600)
    for name, mode in modes.items():
        path = fixture / (name + '.txt')
        path.write_text('Native permission indicators\n')
        path.chmod(mode)

    def query(action='state'):
        result = subprocess.run([str(probe), '--workspace-permissions', str(fixture.resolve()), action],
                                env=env, capture_output=True, text=True, timeout=15)
        with (artifacts / 'queries.jsonl').open('a') as log:
            log.write(json.dumps(dict(action=action, returncode=result.returncode,
                                      stdout=result.stdout, stderr=result.stderr)) + '\n')
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    state = query('init')
    assert state['view_class'] == 'WMPermissions' and state['displays_execute'] and state['editable']
    resources = {item['key']: Path(item['resource']) for item in state['images']}
    fidelity(artifacts / 'source-fidelity', images=resources['check'].parent)
    images, records = {}, {}
    for key, name in NAMES.items():
        directory = artifacts / name
        directory.mkdir()
        images[key], records[key] = representations(density_probe, resources[key], directory, (44, 16))
    target = command('outputs')[0]
    cases = []
    for index, density in enumerate((120, 150, 180, 210, 240)):
        directory = artifacts / str(density)
        directory.mkdir()
        assert command(f"test-scale {target['name']} {density} 15000")['ok']
        assert command('confirm')['ok']
        target = next(head for head in command('outputs') if head['name'] == target['name'])
        state = query('init')
        window = next(w for w in command('windows') if w['pid'] == owner and w['client_id'] == state['window'])
        assert command(f"move {window['id']} {target['x']+10} {target['y']+10}")['ok']
        capture = Path(env['NEXTSPACE_WAYLAND_CAPTURE_DIR']) / f"window-{state['window']}-{density}.png"
        capture.unlink(missing_ok=True)
        state = query()

        def captured():
            current = next(w for w in command('windows') if w['pid'] == owner and w['client_id'] == state['window'])
            if current['preferred_scale'] != density:
                return None
            try:
                with Image.open(capture) as image:
                    if image.size != (current['buffer_width'], current['buffer_height']):
                        return None
                    return current, image.convert('RGBA')
            except OSError:
                return None

        window, actual = until(captured, 'Inspector permission native buffer')
        actual.save(directory / 'window.png')
        assert state['nochange'] == 0o44 and state['mode'] & 0o777 == 0o600, state
        comparisons = compare_cells(state, window, actual, density,
                                    {key: frames[index] for key, frames in images.items()}, directory)
        x, y, width, height = state['view']
        px = window['x'] + x + int(width / 3) * 1.5
        py = window['y'] + window['height'] - y - height + int(height / 3) * 1.5
        assert command(f'pointer {round(px)} {round(py)}')['ok']
        assert command('button 272')['ok']
        changed = until(lambda: (row := query()) and row['mode'] == (state['mode'] ^ 0o20) and row,
                        'permission cell pointer toggle')
        assert command('button 272')['ok']
        restored = until(lambda: (row := query()) and row['mode'] == state['mode'] and row,
                         'permission cell pointer restoration')
        assert state['nochange'] == changed['nochange'] == restored['nochange']
        cases.append(dict(density=density, state=state, window=window,
                          comparisons=comparisons, changed=changed, restored=restored))
    for name, mode in modes.items():
        assert (fixture / (name + '.txt')).stat().st_mode & 0o777 == mode
    # Reload the original selection before closing the edited Inspector.
    query('init')
    assert command(f"close {window['id']}")['ok']
    until(lambda: not any(w['id'] == window['id'] and w['visible']
                          for w in command('windows')), 'permission Inspector closed')
    result = dict(passed=True, cases=cases, resources=records,
                  native_cell_comparisons=45, actual_pointer_actions=10,
                  fixture_file_modes_unchanged=True, inspector_closed=True,
                  full_plan_complete=False)
    (artifacts / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    return result
