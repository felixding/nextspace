#!/usr/bin/env python3
"""Preserve Workspace's original permission indicators at native densities."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Packaging/Sources'))
from vector_art import Artwork, DENSITIES, backing_size
from artwork_reference import (
    artwork_original, assert_not_enlarged, assert_svg_representations,
    assert_vector_geometry,
)

SIZES = dict.fromkeys(('PermYes', 'PermNo', 'PermNoChange'), (44, 16))


def compare(original, frames):
    assert frames[0].tobytes() == original.tobytes(), 'Original permission artwork changed'
    assert_not_enlarged(frames, 'continuous permission geometry')


def run(artifacts, source=None, images=None):
    repository = Path(__file__).resolve().parents[2]
    source = source or repository / 'Applications/Workspace/Artwork.svg'
    art = Artwork(source)
    assert_vector_geometry(art.root)
    artifacts.mkdir(parents=True)
    records = []
    for name, logical in SIZES.items():
        original, fixture = artwork_original('workspace-permissions', name)
        frames = [art.render(name, tuple(backing_size(n, d) for n in logical))
                  for d in DENSITIES[:5]]
        compare(original, frames)
        if images:
            assert_svg_representations(art, name, images / (name + '.tiff'), logical)
        shifted = Image.new('RGBA', logical, (170, 170, 170, 255))
        shifted.paste(original, (1, 0))
        palette = original.copy()
        palette.putdata([(85, 85, 85, p[3]) if p[:3] == (0, 0, 0) else p
                         for p in palette.getdata()])
        missing, background = original.copy(), original.copy()
        point = next((x, y) for y in range(logical[1]) for x in range(logical[0])
                     if original.getpixel((x, y))[:3] != (170, 170, 170))
        missing.putpixel(point, (170, 170, 170, 255))
        background.putpixel((0, 0), (171, 171, 171, 255))
        controls = [(label, [image, *frames[1:]]) for label, image in (
            ('shifted', shifted), ('mirrored', ImageOps.mirror(original)),
            ('palette', palette), ('missing-ink', missing), ('background', background))]
        controls.extend((method.name, [original.resize(frame.size, method) for frame in frames])
                        for method in (Image.Resampling.NEAREST, Image.Resampling.LANCZOS))
        for label, candidate in controls:
            try:
                compare(original, candidate)
            except AssertionError:
                pass
            else:
                raise AssertionError('Permission mutation accepted: ' + name + ':' + label)
        for density, frame in zip(DENSITIES[:5], frames):
            frame.save(artifacts / f'{name}-{density}.png')
        records.append(dict(name=name, original_rgba_exact=True,
                            negative_controls=len(controls), original_source_sha256=fixture['source_sha256']))
    result = dict(passed=True, cases=records, original_rgba_exact=3,
                  negative_controls=sum(c['negative_controls'] for c in records),
                  source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  shared_master_sha256=hashlib.sha256(
                      (repository / 'Applications/Artwork/CheckGlyphs.svg').read_bytes()).hexdigest(),
                  submitted_images_verified=images is not None, full_plan_complete=False)
    (artifacts / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('artifacts', 'source', 'images'):
        parser.add_argument('--' + name, type=Path, required=name == 'artifacts')
    args = parser.parse_args()
    result = run(args.artifacts, args.source, args.images)
    print(f"Permissions: {result['original_rgba_exact']} exact originals and "
          f"{result['negative_controls']} negative controls PASS")
