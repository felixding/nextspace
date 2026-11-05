"""Check real file/media operation rows and safe Stop at each native density."""
import hashlib
import json
from pathlib import Path
import subprocess

from PIL import Image
from application_artwork import representations
from artwork_reference import assert_svg_representations
from folder_artwork import compare_icon
from integration import until
from operation_fidelity import NAMES, verify
from vector_art import Artwork


def run(command, env, application, probe, density_probe, owner, artifacts):
    artifacts.mkdir(parents=True)
    repository = Path(__file__).resolve().parents[2]
    art = Artwork(repository / 'Applications/Artwork/Operations.svg')
    fidelity = verify(art, repository)
    resources, frames = {}, {}
    for symbol in NAMES:
        node = art.symbols[symbol]
        for relative in (node.get('data-files') or node.get('data-file')).split():
            name = Path(relative).stem
            path = application.parent / 'Resources' / (name + '.tiff')
            directory = artifacts / 'resources' / name
            directory.mkdir(parents=True)
            assert_svg_representations(art, symbol, path, (16, 16))
            images, metadata = representations(density_probe, path, directory, (16, 16))
            frames[symbol] = images
            resources[name] = dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), metadata=metadata)
    assert resources['miniCopy']['sha256'] == resources['miniDuplicate']['sha256']
    fixture = (artifacts / 'fixture').resolve()
    (fixture / 'source').mkdir(parents=True)
    (fixture / 'target').mkdir()
    source, destination = b'Owned copy source\n', b'Preserved destination\n'
    (fixture / 'source/first.txt').write_bytes(source)
    (fixture / 'target/first.txt').write_bytes(destination)

    def query(action, density):
        result = subprocess.run([str(probe), '--workspace-bg-mini', str(fixture), action, kind],
                                env=env, capture_output=True, text=True, timeout=20)
        with (artifacts / 'queries.jsonl').open('a') as log:
            log.write(json.dumps(dict(operation=kind, action=action, density=density, returncode=result.returncode,
                                      stdout=result.stdout, stderr=result.stderr)) + '\n')
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    def window(state):
        return next(w for w in command('windows') if w['pid'] == owner and w['client_id'] == state['window'])

    def capture_row(state, symbol, index, density, directory):
        w = window(state)
        assert command(f"move {w['id']} {target['x']+240} {target['y']+100}")['ok']
        until(lambda: window(state)['preferred_scale'] == density, 'background row density')
        capture = Path(env['NEXTSPACE_WAYLAND_CAPTURE_DIR']) / f"window-{state['window']}-{density}.png"
        capture.unlink(missing_ok=True)
        state = query('state', density)

        def pixels():
            w = window(state)
            try:
                with Image.open(capture) as image:
                    if image.size == (w['buffer_width'], w['buffer_height']):
                        return w, image.convert('RGBA')
            except OSError:
                return None

        w, actual = until(pixels, 'live operation row canvas')
        actual.save(directory / 'window.png')
        comparison = compare_icon(art, frames[symbol][index], symbol, state['image'], w,
            actual, density, directory / 'image',
            background=Image.new('RGBA', actual.size, (255, 255, 255, 255)), scan_aligned=True,
            resource=application.parent / 'Resources' / (symbol[0].lower() + symbol[1:] + '.tiff'))
        return state, w, comparison

    target = command('outputs')[0]
    cases, clicks, media_cases = [], [], []
    try:
        for kind, operation_type in (('Copy', 1), ('Move', 3), ('Link', 4)):
            operation_directory = artifacts / kind
            operation_directory.mkdir()
            for index, density in enumerate((120, 150, 180, 210, 240)):
                directory = operation_directory / str(density)
                directory.mkdir()
                worker = None
                try:
                    assert command(f"test-scale {target['name']} {density} 15000")['ok'] and command('confirm')['ok']
                    query('start', density)

                    def ready():
                        state = query('state', density)
                        return state if state['operation_count'] == 1 and state['state'] == 3 else None

                    state = until(ready, 'real operation conflict', timeout=20)
                    worker = state['worker_pid']
                    assert worker > 0 and state['type'] == operation_type
                    state, w, comparison = capture_row(state, 'Mini' + kind, index, density, directory)
                    x, y, width, height = state['stop_button']
                    point = round(w['x'] + x + width / 2), round(w['y'] + w['height'] - y - height / 2)
                    assert command(f"focus {w['id']}")['ok'] and command(f'pointer {point[0]} {point[1]}')['ok']
                    try:
                        assert command('button 272 1')['ok']
                    finally:
                        assert command('button 272 0')['ok']
                    clicks.append(dict(operation=kind, density=density, action='stop-conflict', pointer=point))
                    (artifacts / 'pointer-actions.json').write_text(json.dumps(clicks, indent=2) + '\n')
                    until(lambda: query('state', density)['operation_count'] == 0, 'Operation stopped by its real button', timeout=20)
                    until(lambda: not Path('/proc/' + str(worker)).exists(), 'FileMover worker reaped', timeout=10)
                    assert (fixture / 'source/first.txt').read_bytes() == source
                    assert (fixture / 'target/first.txt').read_bytes() == destination
                    cases.append(dict(operation=kind, operation_type=operation_type, density=density, state=state, window=w, comparison=comparison,
                                      worker_reaped=True, original_files_preserved=True))
                    (artifacts / 'cases.json').write_text(json.dumps(cases, indent=2) + '\n')
                finally:
                    query('cancel', density)
                    until(lambda: query('state', density)['operation_count'] == 0, 'Owned operation cleanup', timeout=20)
                    if worker is not None:
                        until(lambda: not Path('/proc/' + str(worker)).exists(), 'owned worker cleanup', timeout=10)
        for kind, operation_type in (('Mount', 7), ('Unmount', 8), ('Eject', 9)):
            operation_directory = artifacts / kind
            operation_directory.mkdir()
            for index, density in enumerate((120, 150, 180, 210, 240)):
                directory = operation_directory / str(density)
                directory.mkdir()
                try:
                    assert command(f"test-scale {target['name']} {density} 15000")['ok'] and command('confirm')['ok']
                    query('start', density)
                    state = until(lambda: (lambda s: s if s['operation_count'] == 1 and s['state'] == 1 else None)(
                        query('state', density)), 'real Mounter row')
                    assert state['class'] == 'Mounter' and state['type'] == operation_type
                    assert state['source'] == '/dev/nextspace-artwork-fixture'
                    assert not state['kernel_device_operation_requested']
                    state, w, comparison = capture_row(state, 'MiniDisk', index, density, directory)
                    media_cases.append(dict(operation=kind, operation_type=operation_type, density=density,
                                            state=state, window=w, comparison=comparison))
                    (artifacts / 'media-cases.json').write_text(json.dumps(media_cases, indent=2) + '\n')
                finally:
                    query('cancel', density)
                    until(lambda: query('state', density)['operation_count'] == 0, 'owned Mounter cleanup', timeout=10)
    finally:
        assert command(f"test-scale {target['name']} {target['scale']} 15000")['ok'] and command('confirm')['ok']
    result = dict(passed=True, source_fidelity=fidelity, resources=resources, cases=cases, media_cases=media_cases,
        original_copy_rgba_exact=True, native_image_comparisons=len(cases) + len(media_cases),
        actual_pointer_stop_actions=len(clicks), actual_media_row_cases=len(media_cases),
        kernel_device_operations_requested=False,
        all_workers_reaped=True, source_and_destination_preserved=True, full_plan_complete=False)
    (artifacts / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Operation rows: thirty native canvases and fifteen safe Stop actions PASS', flush=True)
    return result
