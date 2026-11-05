#!/usr/bin/env python3
"""Keep OpenUp's long P/L bars, ampersand and seven-letter miniature caption."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import artwork_original, assert_curve_arguments, assert_not_enlarged, assert_svg_representations

PARTS = (
    ('P', (0, 0, 84, 19), .98),
    ('ampersand', (84, 1, 97, 13), .80),
    ('L', (98, 0, 184, 19), 1),
    ('S', (68, 13, 74, 19), .70),
    ('Y', (74, 13, 77, 19), .70),
    ('small-S', (77, 13, 81, 19), .70),
    ('T', (81, 13, 85, 19), .70),
    ('E', (85, 13, 88, 19), .70),
    ('M', (88, 13, 93, 19), .70),
    ('last-S', (93, 13, 97, 19), .70),
)


def compare(original, low, high):
    assert original.size == low.size == (184, 19) and high.size == (1472, 152)
    assert original.getchannel('A').getbbox() == low.getchannel('A').getbbox(), 'Logo footprint changed'
    records = []
    for name, box, minimum in PARTS:
        left, top, right, bottom = box
        points = [(x, y) for y in range(top, bottom) for x in range(left, right)
                  if name != 'P' or y < 12 or x < 68]
        a, b = [[image.getpixel(p)[3] for p in points] for image in (original, low)]
        mass, weight = sum(a), sum(b)
        assert mass and weight, ('Logo part missing', name)
        ratio = weight / mass
        overlap = sum(min(x, y) for x, y in zip(a, b)) / sum(max(x, y) for x, y in zip(a, b))
        delta = [sum(p[c] * v for p, v in zip(points, b)) / weight -
                 sum(p[c] * v for p, v in zip(points, a)) / mass for c in (0, 1)]
        assert overlap >= minimum and abs(ratio - 1) <= .05 and max(map(abs, delta)) <= .3, \
            ('Logo contour, weight or placement changed', name, overlap, ratio, delta)
        color = (98, 13, 19) if name in ('P', 'ampersand', 'L') else (0, 0, 0)
        # The original reader unpremultiplies quantized alpha. Compare weighted
        # color to avoid magnifying rounding in nearly transparent edge pixels.
        mean = [sum(low.getpixel(p)[c] * v for p, v in zip(points, b)) / weight for c in range(3)]
        assert max(abs(x-y) for x, y in zip(mean, color)) <= 1, ('Logo color changed', name)
        if name == 'L':
            assert original.getchannel('A').crop(box).tobytes() == low.getchannel('A').crop(box).tobytes(), 'L bar geometry changed'
        assert_not_enlarged([low.crop(box), high.crop(tuple(v * 8 for v in box))], name)
        records.append(dict(name=name, box=box, weighted_overlap=overlap, ink_ratio=ratio, center_delta=delta))
    assert_not_enlarged([low, high], 'OpenUp narrow logo')
    return records


def run(artifacts, source=None, image=None):
    source = source or Path(__file__).resolve().parents[2] / 'Applications/OpenUp/Artwork.svg'
    art = Artwork(source)
    assert_curve_arguments(art.root)
    node = art.symbols['narrow']
    assert node.get('data-reconstructed') == 'true' and node.get('data-logical-size') == '184 19'
    original, fixture = artwork_original('openup', 'narrow')
    low, high = [art.render('narrow', size) for size in ((184, 19), (1472, 152))]
    records = compare(original, low, high)
    if image:
        assert_svg_representations(art, 'narrow', image, (184, 19))
    shifted = Image.new('RGBA', low.size)
    shifted.paste(low, (1, 0))
    opaque = low.copy(); opaque.putalpha(255)
    r, g, b, a = low.split()
    mutations = [('shifted', shifted, high), ('mirrored', ImageOps.mirror(low), high),
                 ('opaque', opaque, high), ('wrong-palette', Image.merge('RGBA', (b, g, r, a)), high)]
    for name, box, _ in PARTS:
        missing = low.copy(); missing.paste((0, 0, 0, 0), box)
        mutations.append(('missing-' + name, missing, high))
    for method in (Image.Resampling.NEAREST, Image.Resampling.LANCZOS):
        mutations.append((method.name.lower() + '-enlargement', low, low.resize(high.size, method)))
        for name, box, _ in PARTS:
            enlarged = high.copy()
            enlarged.paste(low.crop(box).resize(((box[2]-box[0])*8, (box[3]-box[1])*8), method),
                           (box[0]*8, box[1]*8))
            mutations.append((method.name.lower() + '-' + name + '-enlargement', low, enlarged))
    rejected = []
    for label, candidate, big in mutations:
        try:
            compare(original, candidate, big)
        except AssertionError:
            rejected.append(label)
        else:
            raise AssertionError('Logo mutation accepted: ' + label)
    artifacts.mkdir(parents=True)
    low.save(artifacts / 'narrow-184.png'); high.save(artifacts / 'narrow-1472.png')
    result = dict(passed=True, parts=records, negative_controls=rejected,
                  source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  original_source_sha256=fixture['source_sha256'], original_font_recovered=False,
                  native_display_qualified=False, full_plan_complete=False)
    (artifacts / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print('OpenUp logo: ten shape/letter parts and %d negative controls PASS.' % len(rejected))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--image', type=Path)
    args = parser.parse_args()
    run(args.artifacts, args.source, args.image)
