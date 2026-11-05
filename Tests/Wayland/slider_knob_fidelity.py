"""Preserve both original slider knobs while rendering genuine backing pixels."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image, ImageChops, ImageDraw, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import artwork_original, assert_not_enlarged, assert_svg_representations, assert_vector_geometry

SIZES = {'common_SliderHoriz': (19, 14), 'common_SliderVert': (14, 19)}


def compare(original, low, high, name):
    size = SIZES[name]
    assert original.size == low.size == size
    assert high.size == tuple(v * 8 for v in size)
    assert low.getchannel('A').tobytes() == original.getchannel('A').tobytes()
    maximum = max(hi for lo, hi in ImageChops.difference(original, low).getextrema())
    assert maximum <= 1, (name, 'bevel, grip or palette changed', maximum)
    assert_not_enlarged([low, high], name)
    points = [(9 * 8 + 4, y) for y in range(92, 100)] if name.endswith('Horiz') else [
        (x, 9 * 8 + 4) for x in range(92, 100)]
    assert len({high.getpixel(point) for point in points}) >= 6, 'Grip end retains raster steps'
    return dict(maximum_original_channel_difference=maximum, alpha_identical=True,
                genuine_subpixel_grip_lighting=True)


def run(artifacts, source=None, images=None):
    repository = Path(__file__).resolve().parents[2]
    source = source or repository / 'Libraries/gnustep/Artwork.svg'
    artwork = Artwork(source)
    assert_vector_geometry(artwork.root)
    artifacts.mkdir(parents=True)
    cases = []
    for name, size in SIZES.items():
        original, fixture = artwork_original('slider-knobs', name)
        low = artwork.render(name, size)
        high = artwork.render(name, tuple(v * 8 for v in size))
        result = compare(original, low, high, name)
        if images:
            assert_svg_representations(artwork, name, images / (name + '.tiff'), size)
        shifted = Image.new('RGBA', size)
        shifted.paste(low, (1, 0))
        solid = Image.new('RGBA', size, (170, 170, 170, 255))
        missing = low.copy()
        box = (8, 1, 9, 12) if name.endswith('Horiz') else (1, 8, 12, 9)
        ImageDraw.Draw(missing).rectangle(box, fill=(170, 170, 170, 255))
        mutations = [('shifted', shifted, high), ('mirrored', ImageOps.mirror(low), high),
                     ('same-alpha-solid', solid, high), ('missing-grip', missing, high)]
        for method in (Image.Resampling.NEAREST, Image.Resampling.LANCZOS):
            mutations.append((method.name.lower() + '-enlargement', low, low.resize(high.size, method)))
        rejected = []
        for label, candidate, enlarged in mutations:
            try:
                compare(original, candidate, enlarged, name)
            except AssertionError:
                rejected.append(label)
            else:
                raise AssertionError('Slider knob mutation accepted: ' + name + ' ' + label)
        low.save(artifacts / (name + '-base.png'))
        high.save(artifacts / (name + '-high.png'))
        cases.append(dict(name=name, design=result, rejected_mutations=rejected,
                          original_source_sha256=fixture['source_sha256']))
    result = dict(passed=True, cases=cases, negative_controls=sum(len(c['rejected_mutations']) for c in cases),
                  source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  master_sha256=hashlib.sha256((source.parent / 'SliderKnobs.svg').read_bytes()).hexdigest(),
                  submitted_images_verified=images is not None, native_consumer_qualified=False,
                  full_plan_complete=False)
    (artifacts / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Slider knobs: two original designs and twelve negative controls PASS')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('artifacts', 'source', 'images'):
        parser.add_argument('--' + name, type=Path, required=name == 'artifacts')
    args = parser.parse_args()
    run(args.artifacts, args.source, args.images)
