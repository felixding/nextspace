"""Preserve the original tab highlights and beveled edges with continuous curves."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image, ImageFilter, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import (alpha_geometry, artwork_original, assert_not_enlarged,
    assert_svg_representations, assert_vector_geometry, regional_error)

SIZES = {'common_Tab' + orientation + state: (13, 18 if orientation else 17)
    for orientation in ('', 'Down') for state in ('SelectedLeft', 'SelectedRight',
        'UnSelectedLeft', 'UnSelectedRight', 'UnSelectedJunction',
        'SelectedToUnSelectedJunction', 'UnSelectedToSelectedJunction')}
EXACT = {'common_Tab' + state for state in ('SelectedLeft', 'UnSelectedLeft',
    'DownSelectedLeft', 'DownSelectedRight', 'DownUnSelectedRight')}
EXACT_ALPHA = EXACT | {'common_TabDown' + state for state in ('UnSelectedLeft',
    'SelectedToUnSelectedJunction', 'UnSelectedToSelectedJunction')}
QUALIFIED_BEVELS = {'common_Tab' + state for state in ('UnSelectedRight',
    'UnSelectedJunction', 'SelectedToUnSelectedJunction')}


def compare(original, low, high):
    assert low.size == original.size
    assert low.tobytes() == original.tobytes(), 'The original tab highlight changed'
    assert_not_enlarged([low, high], 'tab curve')


def on_control(image):
    background = Image.new('RGBA', image.size, (170, 170, 170, 255))
    background.alpha_composite(image)
    return background


def compare_bevel(name, original, low, high):
    assert low.size == original.size == SIZES[name]
    assert_not_enlarged([low, high], name)
    if name in EXACT_ALPHA:
        assert low.getchannel('A').tobytes() == original.getchannel('A').tobytes(), \
            'The original silhouette or soft shadow tip changed'
    before, after = on_control(original), on_control(low)
    points = [(x, y) for y in range(original.height) for x in range(13)
        if original.getpixel((x, y))[3] or low.getpixel((x, y))[3]]
    error = regional_error(before, after, points)
    assert error['mean'] <= 9 and error['rms'] <= 16 and error['maximum'] <= 64, error
    assert error['channel_mean_difference'] <= 3, error
    geometry = alpha_geometry(original, low)
    coverage = geometry['reconstructed_coverage'] / geometry['original_coverage']
    assert .85 <= coverage <= 1.15, geometry
    assert geometry['original_bounds'] == geometry['reconstructed_bounds'], geometry

    # Compare the original dark edge independently of the low-resolution
    # transparent fringe. Its centre must stay within a quarter logical pixel.
    centres, darkness = [], []
    # Previously qualified full-height shadows retain their original test.
    # Partial junction shadows use rows with an opaque black original anchor,
    # avoiding the neighboring white branch and the translucent gray cap.
    anchor_rows = range(3, 16) if name in QUALIFIED_BEVELS else [
        y for y in range(original.height) if any(
            original.getpixel((x, y)) == (0, 0, 0, 255) for x in range(13))]
    assert anchor_rows, name
    for image in (before, after):
        rows, ink = [], 0
        for y in anchor_rows:
            weights = [max(0, 170 - sum(image.getpixel((x, y))[:3]) / 3) for x in range(13)]
            squared = [v * v for v in weights]
            assert sum(squared) > 0, (name, y)
            rows.append(sum((x + .5) * v for x, v in enumerate(squared)) / sum(squared))
            ink += sum(weights)
        centres.append(rows)
        darkness.append(ink)
    displacement = [abs(a - b) for a, b in zip(*centres)]
    assert max(displacement) <= .25 and sum(displacement) / len(displacement) <= .15, displacement
    assert .85 <= darkness[1] / darkness[0] <= 1.15, darkness
    cap = next((x, y) for y in range(original.height) for x in range(13)
        if original.getpixel((x, y))[3] == 255)
    assert max(abs(a - b) for a, b in zip(before.getpixel(cap)[:3],
        after.getpixel(cap)[:3])) <= 24, 'The beveled cap changed'
    for y in range(9):
        for x in range(13):
            reference, actual = before.getpixel((x, y)), after.getpixel((x, y))
            if sum(reference[:3]) / 3 >= 215:
                assert max(abs(a - b) for a, b in zip(reference[:3], actual[:3])) <= 20, \
                    ('The neighboring tab highlight changed', name, x, y, reference, actual)
    if name in ('common_TabUnSelectedRight', 'common_TabUnSelectedJunction'):
        assert all(low.getpixel((x, 16)) == (255, 255, 255, 255) for x in range(13)), \
            'The unselected tab baseline changed'
    elif name == 'common_TabSelectedToUnSelectedJunction':
        assert max(abs(a - b) for a, b in zip(before.getpixel((12, 16))[:3],
            after.getpixel((12, 16))[:3])) <= 24, 'The shadow tail changed'
    elif name in ('common_TabDownUnSelectedLeft', 'common_TabDownUnSelectedJunction'):
        assert all(low.getpixel((x, 0)) == (85, 85, 85, 255) for x in range(13)), \
            'The bottom tab border changed'
    return dict(visible_color_error=error, alpha_geometry=geometry,
        maximum_dark_edge_displacement=max(displacement),
        mean_dark_edge_displacement=sum(displacement) / len(displacement),
        dark_edge_ink_ratio=darkness[1] / darkness[0])


def run(artifacts, source=None, images=None):
    repository = Path(__file__).resolve().parents[2]
    source = source or repository / 'Libraries/gnustep/Artwork.svg'
    artwork = Artwork(source)
    assert_vector_geometry(artwork.root)
    artifacts.mkdir(parents=True)
    records = []
    for name, size in SIZES.items():
        original, fixture = artwork_original('tabs', name)
        low = artwork.render(name, size)
        high = artwork.render(name, tuple(v * 8 for v in size))
        exact = name in EXACT
        def check(candidate, enlarged):
            return compare(original, candidate, enlarged) if exact else compare_bevel(name, original, candidate, enlarged)
        fidelity = check(low, high)
        if images:
            assert_svg_representations(artwork, name, images / (name + '.tiff'), size)
        shifted = Image.new('RGBA', size)
        shifted.paste(low, (1, 0))
        gray = low.copy()
        cap = next((x, y) for y in range(size[1]) for x in range(13)
            if original.getpixel((x, y))[3] == 255)
        gray.putpixel(cap, (160, 160, 160, 255))
        mutations = [('shifted', shifted, high), ('mirrored', ImageOps.mirror(low), high),
            ('gray-highlight', gray, high)]
        if not exact:
            thick = low.copy()
            thick.putalpha(low.getchannel('A').filter(ImageFilter.MaxFilter(3)))
            faded = low.copy()
            faded.paste((170, 170, 170, 255), (0, 2, 13, size[1] - 1))
            opaque = on_control(low)
            footer = low.copy()
            last = original.getchannel('A').getbbox()[3]
            footer.paste((0, 0, 0, 0), (0, last - 2, 13, last))
            mutations.extend([('thick-shadow', thick, high), ('missing-shadow', faded, high),
                ('opaque-background', opaque, high), ('missing-footer', footer, high)])
            if 'Junction' in name:
                missing = low.copy()
                missing.paste((0, 0, 0, 0), (7, 0, 13, 9))
                mutations.append(('missing-neighbor', missing, high))
        for method in (Image.Resampling.NEAREST, Image.Resampling.LANCZOS):
            mutations.append((method.name.lower() + '-enlargement', low, low.resize(high.size, method)))
        for label, candidate, enlarged in mutations:
            try:
                check(candidate, enlarged)
            except AssertionError:
                pass
            else:
                raise AssertionError('Tab mutation accepted: ' + label)
        low.save(artifacts / (name + '-base.png'))
        high.save(artifacts / (name + '-high.png'))
        records.append(dict(name=name, original_source_sha256=fixture['source_sha256'],
            original_pixels_identical=exact, fidelity=fidelity, negative_controls=len(mutations)))
    result = dict(passed=True, cases=records, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        submitted_images_verified=images is not None, full_plan_complete=False)
    (artifacts / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Tab artwork: fourteen original tab states and continuous density-specific geometry PASS.')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('artifacts', 'source', 'images'):
        parser.add_argument('--' + name, type=Path, required=name == 'artifacts')
    args = parser.parse_args()
    run(args.artifacts, args.source, args.images)
