"""Preserve the original button geometry, glass, materials and Stop lettering."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Packaging/Sources'))
from artwork_reference import artwork_original, assert_not_enlarged, assert_vector_geometry
from nextspirit_art import NextSpiritArtwork
from vector_art import Artwork, backing_size


def compare_find(original, low, high):
    assert low.getbbox() == original.getbbox()
    anchors = ((24, 8), (31, 9), (25, 12), (16, 15), (20, 21))
    assert all(low.getpixel(point) == original.getpixel(point) for point in anchors)
    assert all(high.getpixel((x * 8 + 4, 36 * 8 + 4)) == original.getpixel((x, 36)) for x in range(40, 46))
    coverage = lambda image: sum(value * count for value, count in enumerate(image.getchannel('A').histogram()))
    assert .98 <= coverage(low) / coverage(original) <= 1.02
    assert_not_enlarged([low, high], 'continuous Finder geometry')


def run(artifacts):
    repository = Path(__file__).resolve().parents[2]
    source = repository / 'Applications/Artwork/Finder.svg'
    finder = Artwork(source)
    assert_vector_geometry(finder.root)
    artifacts.mkdir(parents=True)
    originals = {name: artwork_original('workspace-embedded', name)[0] for name in ('Find', 'Stop', 'ComputeSize', 'ComputeSizeDisabled')}
    frames = {name: [finder.render(name, (61, 48)), finder.render(name, (488, 384))] for name in ('Find', 'Stop')}
    compare_find(originals['Find'], *frames['Find'])
    assert frames['Stop'][0].tobytes() == originals['Stop'].tobytes()
    assert_not_enlarged(frames['Stop'], 'continuous Stop geometry')
    rejected = []
    for name in ('Find', 'Stop'):
        low, high = frames[name]
        shifted = Image.new('RGBA', low.size)
        shifted.paste(low, (1, 0))
        assert shifted.getbbox() != originals[name].getbbox()
        rejected.append(name + '-shift')
        for method in (Image.Resampling.NEAREST, Image.Resampling.LANCZOS):
            try:
                assert_not_enlarged([low, low.resize(high.size, method)], name)
            except AssertionError:
                rejected.append(name + '-' + method.name)
            else:
                raise AssertionError('Enlarged artwork accepted')
        for density in (120, 150, 180, 210, 240):
            finder.render(name, tuple(backing_size(axis, density) for axis in (61, 48))).save(artifacts / f'{name}-{density}.png')
    workspace = NextSpiritArtwork(repository / 'Applications/Artwork/NeXTSpirit', 'workspace_icons')
    for density in (120, 150, 180, 210, 240):
        size = tuple(backing_size(axis, density) for axis in (61, 48))
        normal = workspace.render('ComputeSize', size)
        disabled = workspace.render('ComputeSizeDisabled', size)
        assert disabled.getchannel('A').tobytes() == normal.getchannel('A').point(lambda alpha: round(alpha * 103 / 255)).tobytes()
        for name, image in (('ComputeSize', normal), ('ComputeSizeDisabled', disabled)):
            if density == 120 and name == 'ComputeSize':
                assert image.getbbox() == originals[name].getbbox()
            image.save(artifacts / f'{name}-{density}.png')
    result = dict(passed=True, original_stop_rgba_exact=True, exact_find_glass_anchors=5,
        exact_high_resolution_handle_materials=6, original_compute_normal_occupied_bounds=True,
        disabled_opacity_preserved=True, negative_controls=rejected,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), full_plan_complete=False)
    (artifacts / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    run(parser.parse_args().artifacts)
    print('Compute/Find/Stop geometry, materials, opacity and six negative controls PASS')
