"""Preserve Workspace's preference resize artwork and actual drag/revert behavior."""
import hashlib
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageOps
from application_artwork import image_view_clip, representations
from artwork_reference import artwork_original, assert_not_enlarged, assert_svg_representations, assert_vector_geometry
from folder_artwork import compare_icon
from integration import until
from vector_art import Artwork, backing_size

MODULES = (('BrowserPrefs', 'Browser', ('rightArr',)),
           ('IconPrefs', 'IconView', ('leftArr', 'rightArr')),
           ('ShelfPrefs', 'Shelf', ('leftArr', 'rightArr')))


def symbol_for(outlet):
    return 'SizerLeft' if outlet == 'leftArr' else 'SizerRight'


def verify(art, repository):
    assert_vector_geometry(art.root)
    records = []
    for name in ('SizerLeft', 'SizerRight'):
        original, fixture = artwork_original('workspace-sizers', name, repository)
        assert original.getchannel('A').getextrema() == (255, 255)
        frames = [art.render(name, (backing_size(9,d), backing_size(15,d))) for d in (120,150,180,210,240)]

        def compare(candidate):
            assert candidate[0].tobytes() == original.tobytes(), 'Original resize-arrow RGBA changed'
            assert_not_enlarged(candidate, name)

        compare(frames)
        shifted = Image.new('RGBA', original.size)
        shifted.paste(original, (1, 0))
        gray = original.copy()
        gray.putpixel((0 if name == 'SizerRight' else 8, 0), (85,85,85,255))
        candidates = [('shift', [shifted, *frames[1:]]), ('mirror', [ImageOps.mirror(original), *frames[1:]]),
                      ('wrong-edge-color', [gray, *frames[1:]])]
        for method in (Image.Resampling.NEAREST, Image.Resampling.LANCZOS):
            candidates.append((method.name, [original, *(original.resize(frame.size, method) for frame in frames[1:])]))
        for label, candidate in candidates:
            try:
                compare(candidate)
            except AssertionError:
                pass
            else:
                raise AssertionError(('Resize-arrow source mutation accepted', name, label))
        records.append(dict(name=name, original_rgba_exact=True, original_source_sha256=fixture['source_sha256'],
                            negative_controls=len(candidates)))
    return dict(passed=True, original_rgba_exact=True, negative_controls=sum(r['negative_controls'] for r in records), cases=records)


def run(command, env, application, probe, density_probe, owner, artifacts):
    artifacts.mkdir(parents=True)
    repository = Path(__file__).resolve().parents[2]
    art = Artwork(repository / 'Applications/Artwork/Sizers.svg')
    fidelity = verify(art, repository)
    from example_fidelity import verify as verify_example
    example_fidelity = verify_example(repository)
    example_art = Artwork(repository/'Applications/Artwork/GNUstepExample.svg')
    example_path = application.parent/'Resources/GNUstep48x48.tiff'
    example_directory = artifacts/'resources/GNUstepExample'
    example_directory.mkdir(parents=True)
    assert_svg_representations(example_art, 'GNUstepExample', example_path, (48, 48))
    example_frames, example_metadata = representations(density_probe, example_path, example_directory, (48, 48))
    resources, frames = {}, {}
    for module, bundle, outlets in MODULES:
        for outlet in outlets:
            symbol = symbol_for(outlet)
            path = application.parent / f'Resources/{bundle}.wsprefs/Resources/English.lproj/{module}.gorm/sizer{symbol[5:]}.tiff'
            directory = artifacts / 'resources' / module / outlet
            directory.mkdir(parents=True)
            assert_svg_representations(art, symbol, path, (9, 15))
            images, metadata = representations(density_probe, path, directory, (9, 15))
            resources[(module, outlet)] = path
            frames[symbol] = images
            (directory / 'resource.json').write_text(json.dumps(dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), metadata=metadata), indent=2) + '\n')

    def query(name):
        result = subprocess.run([str(probe), '--workspace-preference-images', name],
                                env=env, capture_output=True, text=True, timeout=25)
        with (artifacts / 'queries.jsonl').open('a') as log:
            log.write(json.dumps(dict(module=name, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)) + '\n')
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    def window(state):
        return next(w for w in command('windows') if w['pid'] == owner and w['client_id'] == state['window'])

    def point(state, rect):
        w = window(state)
        x, y, width, height = rect
        return round(w['x']+x+width/2), round(w['y']+w['height']-y-height/2)

    def click(state, rect):
        w = window(state)
        x, y = point(state, rect)
        assert command(f"focus {w['id']}")['ok'] and command(f'pointer {x} {y}')['ok']
        try:
            assert command('button 272 1')['ok']
        finally:
            assert command('button 272 0')['ok']

    target = command('outputs')[0]
    cases, actions = [], []
    try:
        for index, density in enumerate((120,150,180,210,240)):
            assert command(f"test-scale {target['name']} {density} 15000")['ok'] and command('confirm')['ok']
            for name, bundle, outlets in MODULES:
                directory = artifacts / str(density) / name
                directory.mkdir(parents=True)
                state = query(name)
                w = window(state)
                assert command(f"move {w['id']} {target['x']+240} {target['y']+100}")['ok']
                until(lambda: window(state)['preferred_scale'] == density, 'preference density')
                if state['revert_enabled']:
                    click(state, state['revert_button'])
                    until(lambda: not query(name)['revert_enabled'], 'initial preference revert')
                capture = Path(env['NEXTSPACE_WAYLAND_CAPTURE_DIR']) / f"window-{state['window']}-{density}.png"
                capture.unlink(missing_ok=True)
                state = query(name)

                def pixels():
                    w = window(state)
                    try:
                        with Image.open(capture) as image:
                            if image.size == (w['buffer_width'], w['buffer_height']):
                                return w, image.convert('RGBA')
                    except OSError:
                        return None

                w, actual = until(pixels, 'preference image canvas')
                actual.save(directory / 'window.png')
                if name in ('IconPrefs', 'ShelfPrefs'):
                    examples = [v for v in state['images'] if v['name'] == 'NSImageView' and v['logical'] == [48,48]]
                    assert len(examples) == 1 and Path(examples[0]['resource']).name == example_path.name
                    comparison = compare_icon(example_art, example_frames[index], 'GNUstepExample', examples[0],
                        w, actual, density, directory/'example', resource=example_path)
                    cases.append(dict(module=name, density=density, symbol='GNUstepExample', view=examples[0], window=w, comparison=comparison))
                views = [v for v in state['images'] if v['name'] == 'NXTSizer']
                assert {v['outlet'] for v in views} == set(outlets)
                for view in views:
                    symbol = symbol_for(view['outlet'])
                    # Clear all opaque image pixels; retain neighboring controls
                    # outside this artwork qualification only as backdrop.
                    backdrop = actual.copy()
                    edges = image_view_clip(view['visible'], w['height'], density)
                    backdrop.paste((170,170,170,255), tuple(round(edge) for edge in edges))
                    comparison = compare_icon(art, frames[symbol][index], symbol, view, w, actual, density,
                        directory / view['outlet'], scan_aligned=True, resource=resources[(name, view['outlet'])], background=backdrop)
                    cases.append(dict(module=name, density=density, outlet=view['outlet'], view=view, window=w, comparison=comparison))
                (artifacts / 'cases.json').write_text(json.dumps(cases, indent=2) + '\n')
                for outlet in outlets:
                    before = query(name)
                    view = next(v for v in before['images'] if v.get('outlet') == outlet)
                    x, y = point(before, view['view_base'])
                    delta = 8 if outlet == 'leftArr' or name == 'BrowserPrefs' else -8
                    assert command(f"focus {w['id']}")['ok'] and command(f'pointer {x} {y}')['ok']
                    try:
                        assert command('button 272 1')['ok']
                        assert command(f'pointer {x+delta} {y}')['ok']
                    finally:
                        assert command('button 272 0')['ok']

                    def moved():
                        state = query(name)
                        current = next(v for v in state['images'] if v.get('outlet') == outlet)
                        return state if current['view_base'][0] != view['view_base'][0] and state['revert_enabled'] else None

                    after = until(moved, 'real resize arrow drag')
                    current = next(v for v in after['images'] if v.get('outlet') == outlet)
                    assert current['view_base'][0] - view['view_base'][0] == delta
                    click(after, after['revert_button'])
                    restored = until(lambda: (lambda s: s if not s['revert_enabled'] else None)(query(name)), 'real Revert click')
                    for old in [v for v in before['images'] if v.get('outlet')]:
                        new = next(v for v in restored['images'] if v.get('outlet') == old['outlet'])
                        assert new['view_base'] == old['view_base']
                    actions.append(dict(module=name, density=density, outlet=outlet, pointer=[x,y], delta=delta,
                                        before=before, after=after, restored=restored))
                    (artifacts / 'actions.json').write_text(json.dumps(actions, indent=2) + '\n')
    finally:
        assert command(f"test-scale {target['name']} {target['scale']} 15000")['ok'] and command('confirm')['ok']
    result = dict(passed=True, source_fidelity=fidelity, native_image_comparisons=len(cases),
                  example_fidelity=example_fidelity, example_metadata=example_metadata,
                  actual_drag_and_revert_pairs=len(actions), cases=cases, resource_aliases=len(resources)+1, full_plan_complete=False)
    (artifacts / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Preference artwork: 35 native canvases and 25 drag/Revert pairs PASS', flush=True)
    return result
