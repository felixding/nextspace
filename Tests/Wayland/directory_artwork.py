"""Exercise the production directory icons with real, cancelled file drags."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

from PIL import Image
from application_artwork import representations
from artwork_reference import assert_svg_representations
from directory_fidelity import verify
from folder_artwork import compare_icon
from integration import read_json_lines, until
from gnustep import process_runtime
from vector_art import Artwork


def run(command, env, application, probe, density_probe, art, owner, artifacts,
        neighbors, source_window, drag_log, drag_source, desktopkit_resources):
    artifacts.mkdir(parents=True)
    repository = Path(__file__).resolve().parents[2]
    fidelity = verify(art, repository)
    root_closed = Artwork(repository/'Applications/Artwork/Root.svg')
    root_open = Artwork(repository/'Applications/Artwork/RootStates.svg')
    roles = (
        ('home', ['--workspace-home'], art, 'Home', art, 'HomeHover', 'NXHomeDirectory.tiff', 'openHome.tiff'),
        ('root', ['--workspace-root'], root_closed, 'root', root_open, 'RootOpen', 'NXRoot.tiff', 'openRoot.tiff'),
        ('neighborhood', ['--workspace-folders', str(neighbors.parent), 'closed', neighbors.name],
         art, 'Neighbor', art, 'NeighborOpen', 'neighbor.tiff', 'openNeighbor.tiff'))
    resources, resource_paths = {}, {}
    for role, arguments, closed_art, closed_symbol, open_art, open_symbol, closed_name, open_name in roles:
        for renderer, symbol, filename in ((closed_art, closed_symbol, closed_name), (open_art, open_symbol, open_name)):
            directory_root = desktopkit_resources if filename in ('NXHomeDirectory.tiff', 'NXRoot.tiff') else application.parent/'Resources'
            path = directory_root/filename
            resource_paths[filename] = path
            directory = artifacts/'resources'/role/symbol
            directory.mkdir(parents=True)
            assert_svg_representations(renderer, symbol, path, (48, 48))
            frames, metadata = representations(density_probe, path, directory, (48, 48))
            resources[filename] = dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), metadata=metadata)
    (artifacts/'resources.json').write_text(json.dumps(resources, indent=2)+'\n')
    before = drag_source.read_bytes()
    target = command('outputs')[0]
    cases, drags = [], []

    def query(arguments):
        started = time.monotonic()
        result = subprocess.run([str(probe), *arguments], env=env, capture_output=True, text=True, timeout=25)
        with (artifacts/'queries.jsonl').open('a') as log:
            log.write(json.dumps(dict(arguments=arguments, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr, elapsed_seconds=time.monotonic()-started))+'\n')
        if result.returncode != 0:
            process = Path('/proc') / str(owner)
            failure = dict(arguments=arguments, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
            if process.exists():
                failure['workspace_runtime'] = process_runtime(owner)
                failure['workspace_status'] = (process / 'status').read_text()
                failure['workspace_wait'] = (process / 'wchan').read_text()
            failure['windows'] = command('windows')
            (artifacts / 'failed-query.json').write_text(json.dumps(failure, indent=2) + '\n')
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    def window(state):
        return next(w for w in command('windows') if w['pid'] == owner and w['client_id'] == state['window'])

    try:
        for density in (120, 150, 180, 210, 240):
            assert command(f"test-scale {target['name']} {density} 15000")['ok'] and command('confirm')['ok']
            for role, arguments, closed_art, closed_symbol, open_art, open_symbol, closed_name, open_name in roles:
                sample = artifacts/str(density)/role
                sample.mkdir(parents=True)
                state = query(arguments)
                assert len(state['images']) == 1
                w = window(state)
                assert command(f"move {w['id']} {target['x']+240} {target['y']+100}")['ok']
                until(lambda: window(state)['preferred_scale'] == density, 'directory icon density')
                for phase in ('closed', 'hover', 'restored'):
                    directory = sample/phase
                    directory.mkdir()
                    if phase == 'hover':
                        began = len([r for r in read_json_lines(drag_log) if r['event'] == 'drag-begin'])
                        ended = len([r for r in read_json_lines(drag_log) if r['event'] == 'drag-end'])
                        source = next(w for w in command('windows') if w['id'] == source_window['id'])
                        assert command(f"focus {source['id']}")['ok']
                        x, y = source['x']+50, source['y']+100
                        assert command(f'pointer {x} {y}')['ok'] and command(f'hit {x} {y}')['id'] == source['id']
                        assert command('button 272 1')['ok']
                        until(lambda: len([r for r in read_json_lines(drag_log) if r['event'] == 'drag-begin']) > began, 'directory drag begins')
                        until(lambda: command('drag-state')['active'], 'directory drag transport')
                        w = window(state)
                        x, y, width, height = state['images'][0]['base']
                        x, y = round(w['x']+x+width/2), round(w['y']+w['height']-y-height/2)
                        hit = command(f'hit {x} {y}')
                        (directory/'target-hit.json').write_text(json.dumps(hit, indent=2)+'\n')
                        assert hit['id'] == w['id']
                        assert command(f'pointer {x} {y}')['ok']
                    elif phase == 'restored':
                        assert command('key 1 1')['ok'] and command('key 1 0')['ok']
                        until(lambda: not command('drag-state')['active'], 'directory drag cancels')
                        assert command('button 272 0')['ok']
                        until(lambda: len([r for r in read_json_lines(drag_log) if r['event'] == 'drag-end']) > ended, 'directory source cancellation')
                        event = [r for r in read_json_lines(drag_log) if r['event'] == 'drag-end'][-1]
                        assert not event['action']
                        drags.append(dict(role=role, density=density, begin_index=began, end_index=ended, event=event))
                    renderer, symbol, filename = (open_art, open_symbol, open_name) if phase == 'hover' else (closed_art, closed_symbol, closed_name)
                    state = until(lambda: (lambda s: s if Path(s['images'][0]['resource']).name == filename else None)(query(arguments)), 'production directory icon transition')
                    capture = Path(env['NEXTSPACE_WAYLAND_CAPTURE_DIR'])/f"window-{state['window']}-{density}.png"
                    capture.unlink(missing_ok=True)
                    state = query(arguments)

                    def pixels():
                        w = window(state)
                        try:
                            with Image.open(capture) as image:
                                if image.size == (w['buffer_width'], w['buffer_height']):
                                    return w, image.convert('RGBA')
                        except OSError:
                            return None

                    w, actual = until(pixels, 'directory image canvas')
                    actual.save(directory/'window.png')
                    frame = renderer.render(symbol, (48*density//120, 48*density//120))
                    comparison = compare_icon(renderer, frame, symbol, state['images'][0], w, actual, density,
                        directory/'image', resource=resource_paths[filename])
                    drag = command('drag-state')
                    assert drag['active'] == (phase == 'hover')
                    if phase == 'hover':
                        assert drag['target'] == w['id'] and drag['action'] == 1
                    cases.append(dict(role=role, density=density, phase=phase, symbol=symbol, state=state,
                                      window=w, comparison=comparison, drag=drag))
                    (artifacts/'cases.json').write_text(json.dumps(cases, indent=2)+'\n')
        assert drag_source.read_bytes() == before and not any(neighbors.iterdir())
    finally:
        command('key 1 1')
        command('key 1 0')
        command('button 272 0')
        assert command(f"test-scale {target['name']} {target['scale']} 15000")['ok'] and command('confirm')['ok']
    result = dict(passed=True, source_fidelity=fidelity, native_image_comparisons=len(cases),
                  actual_file_drag_cancellations=len(drags), source_file_preserved=True, drags=drags,
                  cases=cases, resources=resources, full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print('Directory states: 45 native canvases and 15 real drag cancellations PASS', flush=True)
    return result
