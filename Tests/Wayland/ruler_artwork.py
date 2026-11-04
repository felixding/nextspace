#!/usr/bin/env python3
"""Preserve original ruler marker geometry, alpha and fractional rasterization."""
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

SIZES = {'common_' + kind + 'TabStop': (8, 8)
    for kind in ('Left', 'Right', 'Center', 'Decimal')}
PIXEL_SIZES = (8, 10, 12, 14, 16, 64)


def compare(original, frames):
    assert frames[0].size == original.size
    assert frames[0].tobytes() == original.tobytes(), 'The original ruler marker changed'
    # Straight strokes aligned to logical pixels legitimately match nearest
    # enlargement at integer scales. Fractional scales distinguish the source.
    assert_not_enlarged(frames, 'ruler marker geometry')


def run(artifacts, source=None, images=None):
    repository = Path(__file__).resolve().parents[2]
    source = source or repository / 'Libraries/gnustep/Artwork.svg'
    artwork = Artwork(source)
    assert_vector_geometry(artwork.root)
    artifacts.mkdir(parents=True)
    records = []
    for name, size in SIZES.items():
        original, fixture = artwork_original('ruler-markers', name)
        frames = [artwork.render(name, (pixels, pixels)) for pixels in PIXEL_SIZES]
        compare(original, frames)
        if images:
            assert_svg_representations(artwork, name, images / (name + '.tiff'), size)
        low = frames[0]
        shifted = Image.new('RGBA', size)
        shifted.paste(low, (1, 0))
        stem, footer, color, opaque = [low.copy() for _ in range(4)]
        stem.paste((0, 0, 0, 0), (3, 2, 4, 5))
        footer.paste((0, 0, 0, 0), (0, 5, 8, 6))
        color.putpixel((3, 2), (255, 255, 255, 255))
        opaque.putalpha(255)
        mutations = [('shifted', shifted), ('mirrored', ImageOps.mirror(low)),
            ('missing-stem', stem), ('missing-foot', footer),
            ('wrong-color', color), ('opaque-padding', opaque)]
        if name == 'common_DecimalTabStop':
            contrast = low.copy()
            contrast.paste((0, 0, 0, 255), (3, 2, 4, 5))
            mutations.append(('lost-decimal-contrast', contrast))
        candidates = [(label, [candidate, *frames[1:]]) for label, candidate in mutations]
        for method in (Image.Resampling.NEAREST, Image.Resampling.LANCZOS):
            candidates.append((method.name.lower() + '-enlargement',
                [low.resize(frame.size, method) for frame in frames]))
        for label, candidate in candidates:
            try:
                compare(original, candidate)
            except AssertionError:
                pass
            else:
                raise AssertionError('Ruler mutation accepted: ' + label)
        for pixels, frame in zip(PIXEL_SIZES, frames):
            frame.save(artifacts / f'{name}-{pixels}.png')
        records.append(dict(name=name, original_source_sha256=fixture['source_sha256'],
            original_pixels_identical=True, negative_controls=len(candidates)))
    result = dict(passed=True, cases=records,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        master_sha256=hashlib.sha256((source.parent / 'RulerMarkers.svg').read_bytes()).hexdigest(),
        fractional_rasterization_verified=True, submitted_images_verified=images is not None,
        full_plan_complete=False)
    (artifacts / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Ruler artwork: four exact original markers and fractional vector geometry PASS.', flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('artifacts', 'source', 'images'):
        parser.add_argument('--' + name, type=Path, required=name == 'artifacts')
    args = parser.parse_args()
    run(args.artifacts, args.source, args.images)
