#!/usr/bin/env python3
"""Keep all four stepper states faithful while rendering their vector geometry."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import (artwork_original, assert_not_enlarged,
    assert_svg_representations, assert_vector_geometry)

SIZES = {'common_Stepper' + direction + state: (18, 13)
    for direction in ('Up', 'Down') for state in ('', 'Highlighted')}


def compare(original, low, high):
    assert low.size == original.size
    assert low.tobytes() == original.tobytes(), 'The original stepper design changed'
    assert_not_enlarged([low, high], 'stepper geometry')


def run(artifacts, source=None, images=None):
    repository = Path(__file__).resolve().parents[2]
    source = source or repository / 'Libraries/gnustep/Artwork.svg'
    artwork = Artwork(source)
    assert_vector_geometry(artwork.root)
    artifacts.mkdir(parents=True)
    records = []
    for name, size in SIZES.items():
        original, fixture = artwork_original('steppers', name)
        low, high = artwork.render(name, size), artwork.render(name, (144, 104))
        compare(original, low, high)
        if images:
            assert_svg_representations(artwork, name, images / (name + '.tiff'), size)
        shifted = Image.new('RGBA', size)
        shifted.paste(low, (1, 0))
        face = low.copy()
        face.putpixel((3, 5), (85, 85, 85, 255))
        arrow = low.copy()
        color = (255, 255, 255, 255) if name.endswith('Highlighted') else (170, 170, 170, 255)
        arrow.paste(color, (5, 2, 12, 10))
        border = low.copy()
        border.paste((0, 0, 0, 0), (1, 0, 2, 13))
        opaque = low.copy()
        opaque.putalpha(255)
        mutations = [('shifted', shifted, high), ('mirrored', ImageOps.mirror(low), high),
            ('wrong-face', face, high), ('missing-arrow', arrow, high),
            ('missing-border', border, high), ('opaque-padding', opaque, high)]
        for method in (Image.Resampling.NEAREST, Image.Resampling.LANCZOS):
            mutations.append((method.name.lower() + '-enlargement', low, low.resize(high.size, method)))
        for label, candidate, enlarged in mutations:
            try:
                compare(original, candidate, enlarged)
            except AssertionError:
                pass
            else:
                raise AssertionError('Stepper mutation accepted: ' + label)
        low.save(artifacts / (name + '-base.png'))
        high.save(artifacts / (name + '-high.png'))
        records.append(dict(name=name, original_source_sha256=fixture['source_sha256'],
            original_pixels_identical=True, negative_controls=len(mutations)))
    result = dict(passed=True, cases=records,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        master_sha256=hashlib.sha256((source.parent / 'StepperButtons.svg').read_bytes()).hexdigest(),
        submitted_images_verified=images is not None, full_plan_complete=False)
    (artifacts / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Stepper artwork: four exact original designs and continuous density-specific geometry PASS.', flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('artifacts', 'source', 'images'):
        parser.add_argument('--' + name, type=Path, required=name == 'artifacts')
    args = parser.parse_args()
    run(args.artifacts, args.source, args.images)
