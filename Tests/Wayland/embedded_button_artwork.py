"""Check real Compute Size, Find and queued Stop buttons at every density."""
import hashlib
import json
from pathlib import Path
import subprocess

from PIL import Image
from application_artwork import representations
from artwork_reference import assert_svg_representations
from folder_artwork import compare_icon
from integration import until
from vector_art import Artwork


def run(command, env, application, probe, density_probe, workspace_art, owner, artifacts):
    artifacts.mkdir(parents=True)
    from embedded_button_fidelity import run as fidelity
    design = fidelity(artifacts / 'fidelity')
    fixture = (artifacts / 'fixture').resolve()
    fixture.mkdir()
    (fixture / 'Folder').mkdir()
    payload = b'Owned size fixture\n'
    (fixture / 'Folder/data.txt').write_bytes(payload)
    for name in ('first.txt', 'second.txt'):
        (fixture / name).write_text('Owned filename search fixture\n')
    finder_art = Artwork(Path(__file__).resolve().parents[2] / 'Applications/Artwork/Finder.svg')
    resources = application.parent / 'Resources'
    inputs = {
        'ComputeSize': (workspace_art, resources / 'Inspectors.bundle/Resources/English.lproj/FileAttributesInspector.gorm/computeSize.tiff'),
        'ComputeSizeDisabled': (workspace_art, resources / 'Inspectors.bundle/Resources/English.lproj/FileAttributesInspector.gorm/computeSizeD.tiff'),
        'Find': (finder_art, resources / 'English.lproj/Finder.gorm/find.tiff'),
        'Stop': (finder_art, resources / 'English.lproj/Finder.gorm/stop.tiff'),
    }
    frames, receipts = {}, {}
    for name, (art, resource) in inputs.items():
        directory = artifacts / 'resources' / name
        directory.mkdir(parents=True)
        assert_svg_representations(art, name, resource, (61, 48))
        frames[name], metadata = representations(density_probe, resource, directory, (61, 48))
        receipts[name] = dict(source=str(resource), sha256=hashlib.sha256(resource.read_bytes()).hexdigest(), metadata=metadata)

    def query(kind, density):
        result = subprocess.run([str(probe), '--workspace-embedded-images', str(fixture), kind],
                                env=env, capture_output=True, text=True, timeout=20)
        with (artifacts / 'queries.jsonl').open('a') as log:
            log.write(json.dumps(dict(kind=kind, density=density, returncode=result.returncode,
                                      stdout=result.stdout, stderr=result.stderr)) + '\n')
        assert result.returncode == 0, result.stderr
        state = json.loads(result.stdout)
        expected = [[61, 48], [76, 60], [92, 72], [107, 84], [122, 96]]
        assert state['representations'] == state['alternate_representations'] == expected
        return state

    def window(state):
        return next(w for w in command('windows') if w['pid'] == owner and w['client_id'] == state['window'])

    def placed(kind, density):
        state = query(kind, density)
        w = window(state)
        # Keep the control clear of Workspace's floating menu and Inspector.
        assert command(f"move {w['id']} {target['x']+240} {target['y']+100}")['ok']
        until(lambda: window(state)['preferred_scale'] == density, 'button density')
        return query(kind, density)

    def click(state, action, density):
        w = window(state)
        assert command(f"focus {w['id']}")['ok']
        x, y, width, height = state['button_base']
        point = round(w['x'] + x + width / 2), round(w['y'] + w['height'] - y - height / 2)
        assert command(f'pointer {point[0]} {point[1]}')['ok']
        try:
            assert command('button 272 1')['ok']
        finally:
            assert command('button 272 0')['ok']
        clicks.append(dict(density=density, action=action, pointer=point))
        (artifacts / 'pointer-actions.json').write_text(json.dumps(clicks, indent=2) + '\n')

    def capture(kind, name, state, density, index):
        directory = artifacts / str(density) / name
        directory.mkdir(parents=True)
        path = Path(env['NEXTSPACE_WAYLAND_CAPTURE_DIR']) / f"window-{state['window']}-{density}.png"
        path.unlink(missing_ok=True)
        state = query(kind, density)

        def pixels():
            w = window(state)
            try:
                with Image.open(path) as image:
                    if image.size != (w['buffer_width'], w['buffer_height']):
                        return None
                    return w, image.convert('RGBA')
            except OSError:
                return None

        w, actual = until(pixels, 'actual button canvas')
        actual.save(directory / 'window.png')
        art, resource = inputs[name]
        comparison = compare_icon(art, frames[name][index], name, state['image'], w,
            actual, density, directory / 'image', background=Image.new('RGBA', actual.size, (170, 170, 170, 255)),
            scan_aligned=True, resource=resource)
        canvases.append(dict(density=density, name=name, state=state, window=w, comparison=comparison))

    target = command('outputs')[0]
    original_density = target['scale']
    cases, clicks, canvases = [], [], []
    try:
        for index, density in enumerate((120, 150, 180, 210, 240)):
            assert command(f"test-scale {target['name']} {density} 15000")['ok'] and command('confirm')['ok']
            state = placed('compute-folder', density)
            assert state['enabled'] and not state['size_text']
            capture('compute-state', 'ComputeSize', state, density, index)
            click(state, 'compute-size', density)

            def computed():
                state = query('compute-state', density)
                return state if state['enabled'] and not state['size_pending'] and state['size_text'] == f'{len(payload)} Bytes' else None

            state = until(computed, 'Compute Size worker result', timeout=20)
            cases.append(dict(density=density, action='compute-size', state=state))
            state = placed('compute-file', density)
            assert not state['enabled']
            capture('compute-state', 'ComputeSizeDisabled', state, density, index)
            state = placed('finder-setup', density)
            assert state['scope_paths'] == [str(fixture)] and state['image_above']
            capture('finder-state', 'Find', state, density, index)
            click(state, 'find-owned-file', density)

            def found():
                state = query('finder-state', density)
                assert state['scope_paths'] == [str(fixture)]
                return state if state['queue_count'] == 0 and state['image_above'] and state['results'] == [str(fixture / 'first.txt')] else None

            state = until(found, 'bounded filename search', timeout=20)
            cases.append(dict(density=density, action='find-owned-file', state=state))
            state = query('finder-pause', density)
            assert state['queue_suspended'] and state['queue_count'] == 0
            click(state, 'queue-owned-search', density)

            def queued():
                state = query('finder-state', density)
                return state if state['queue_suspended'] and state['queue_count'] == 1 and state['image_only'] else None

            busy = until(queued, 'queued search Stop state', timeout=15)
            capture('finder-state', 'Stop', busy, density, index)
            click(busy, 'stop-queued-search', density)
            query('finder-resume', density)

            def stopped():
                state = query('finder-state', density)
                return state if not state['queue_suspended'] and state['queue_count'] == 0 and state['image_above'] and not state['results'] else None

            state = until(stopped, 'cancelled search and restored Find image', timeout=15)
            cases.append(dict(density=density, action='stop-queued-search', state=state, busy=busy))
            (artifacts / 'cases.json').write_text(json.dumps(cases, indent=2) + '\n')
    finally:
        assert command(f"test-scale {target['name']} {original_density} 15000")['ok'] and command('confirm')['ok']
    assert (fixture / 'Folder/data.txt').read_bytes() == payload
    result = dict(passed=True, resources=receipts, cases=cases, canvases=canvases, fidelity=design,
        native_image_comparisons=len(canvases), actual_pointer_actions=len(clicks),
        owned_search_scope_only=True, queued_cancellation_tested=True,
        running_worker_cancellation_qualified=False, full_plan_complete=False)
    (artifacts / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Compute Size, Find and queued Stop: 20 native images and 20 pointer actions PASS', flush=True)
    return result
