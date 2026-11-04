"""Preserve operation glyph silhouettes, bevels, materials and ruler marks."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET

from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Packaging/Sources'))
from artwork_reference import alpha_geometry, artwork_original, assert_not_enlarged, assert_vector_geometry, regional_error
from vector_art import Artwork

NAMES = ('MiniCopy', 'MiniMove', 'MiniLink', 'MiniDelete', 'MiniChmoder', 'MiniSizing', 'MiniDisk')


def compare(name, original, frames):
    low = frames[0]
    if name == 'MiniDisk':
        geometry = alpha_geometry(original, low)
        assert geometry['original_bounds'] == geometry['reconstructed_bounds']
        assert geometry['shape_overlap'] >= .98 and geometry['alpha_rms_difference'] <= 14
        assert .98 <= geometry['reconstructed_coverage'] / geometry['original_coverage'] <= 1.02
        assert max(abs(a-b) for a,b in zip(geometry['original_center'], geometry['reconstructed_center'])) <= .06
        regions = {
            'hub': [(x,y) for y in range(6,10) for x in range(6,10)],
            'face': [(x,y) for y in range(16) for x in range(16) if 3.5**2 <= (x-7.5)**2+(y-7.5)**2 <= 6.5**2],
            'rim': [(x,y) for y in range(16) for x in range(16) if original.getpixel((x,y))[3] and (x-7.5)**2+(y-7.5)**2 > 6.5**2],
        }
        for region, mean, rms, bias in [('face',10,15,4), ('hub',16,24,8), ('rim',18,25,5)]:
            error = regional_error(original, low, regions[region])
            assert error['mean'] <= mean and error['rms'] <= rms and error['channel_mean_difference'] <= bias, (region, error)
    elif name != 'MiniSizing':
        assert low.tobytes() == original.tobytes(), (name, 'Original RGBA changed')
    else:
        assert low.getchannel('A').tobytes() == original.getchannel('A').tobytes(), 'Ruler footprint changed'
        for y in (1, 3, 5, 7, 9, 11, 13):
            marks = lambda image: [x for x in range(4, 12) if max(image.getpixel((x, y))[:3]) < 150]
            assert marks(low) == marks(original), ('Ruler tick position or length changed', y)
        face = [(x, y) for y in (2, 4, 6, 8, 10, 12, 14) for x in range(4, 12)]
        bevel = [(x, 0) for x in range(3, 12)] + [(3, y) for y in range(1, 15)]
        for region in (face, bevel):
            error = regional_error(original, low, region)
            assert error['mean'] <= 6 and error['rms'] <= 8 and error['channel_mean_difference'] <= 5, ('Ruler material changed', error)
        edge = [(12, y) for y in range(1, 16)] + [(x, 15) for x in range(3, 13)] + [(12, 0)]
        assert all(low.getpixel(p) == original.getpixel(p) for p in edge), 'Ruler bevel boundary changed'
    assert_not_enlarged(frames, name)


def verify(art, repository):
    assert_vector_geometry(art.root)
    records = []
    for name in NAMES:
        original, fixture = artwork_original('workspace-operations', name, repository)
        assert fixture['logical_size'] == [16, 16]
        if name == 'MiniCopy':
            assert hashlib.sha256((repository / fixture['identical_original_alias']).read_bytes()).hexdigest() == fixture['source_sha256']
        frames = [art.render(name, (n, n)) for n in (16, 20, 24, 28, 32)]
        compare(name, original, frames)
        shifted = Image.new('RGBA', (16, 16))
        shifted.paste(frames[0], (1, 0))
        mutations = [('shift', shifted), ('mirror', ImageOps.mirror(frames[0]))]
        if name == 'MiniDisk':
            gray = ImageOps.grayscale(frames[0]).convert('RGBA')
            gray.putalpha(frames[0].getchannel('A'))
            mutations.extend([('gray-surface', gray), ('wrong-optical-phase', frames[0].transpose(Image.Transpose.ROTATE_90))])
        else:
            point = next((x, y) for y in range(16) for x in range(16) if frames[0].getpixel((x, y))[3])
            palette, alpha = frames[0].copy(), frames[0].copy()
            palette.putpixel(point, (255, 0, 255, 255))
            alpha.putpixel(point, (*alpha.getpixel(point)[:3], 85))
            mutations.extend([('palette', palette), ('alpha', alpha)])
        if name == 'MiniSizing':
            for label, color, box in [('missing-tick', (255, 196, 145, 255), (9, 5, 12, 6)),
                                      ('long-quarter-tick', (76, 68, 51, 255), (8, 3, 12, 4)),
                                      ('gray-wood', (220, 220, 220, 255), (4, 2, 12, 3))]:
                altered = frames[0].copy()
                altered.paste(color, box)
                mutations.append((label, altered))
        candidates = [(label, [low, *frames[1:]]) for label, low in mutations]
        for method in (Image.Resampling.NEAREST, Image.Resampling.LANCZOS):
            candidates.append((method.name, [frames[0], *(frames[0].resize(f.size, method) for f in frames[1:])]))
        if name == 'MiniDisk':
            for label, mask in [('missing-hub', 'url(#hub-matte)'), ('missing-rim', 'url(#rim-matte)')]:
                tree = ET.ElementTree(ET.fromstring(ET.tostring(art.root)))
                parent = next(n for n in tree.getroot().iter() if any(child.get('mask') == mask for child in n))
                parent.remove(next(child for child in parent if child.get('mask') == mask))
                with tempfile.TemporaryDirectory(prefix='nextspace-disc-control-') as directory:
                    path = Path(directory) / 'control.svg'
                    tree.write(path, encoding='unicode')
                    altered = Artwork(path)
                    candidates.append((label, [altered.render(name, (n,n)) for n in (16,20,24,28,32)]))
        for label, candidate in candidates:
            try:
                compare(name, original, candidate)
            except AssertionError:
                pass
            else:
                raise AssertionError((name, 'Mutation accepted', label))
        records.append(dict(name=name, original_rgba_exact=name not in ('MiniSizing', 'MiniDisk'), original_alpha_exact=name != 'MiniDisk',
                            negative_controls=len(candidates), original_source_sha256=fixture['source_sha256']))
    return dict(passed=True, exact_original_rgba_designs=5, ruler_seven_mark_footprints_exact=True,
                ruler_material_preserved=True, disc_shape_and_material_preserved=True,
                negative_controls=sum(r['negative_controls'] for r in records),
                cases=records, full_plan_complete=False)


def run(artifacts):
    repository = Path(__file__).resolve().parents[2]
    art = Artwork(repository / 'Applications/Artwork/Operations.svg')
    result = verify(art, repository)
    artifacts.mkdir(parents=True)
    (artifacts / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Operation artwork: five exact designs and faithful ruler/disc geometry and materials PASS', flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    run(parser.parse_args().artifacts)
