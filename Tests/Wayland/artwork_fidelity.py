#!/usr/bin/env python3
"""Check reconstructed theme artwork against the original resources."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tarfile

from PIL import Image, ImageChops
from artwork_reference import assert_not_enlarged

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'Packaging/Sources'))
from vector_art import Artwork, backing_size

GLYPHS = ('common_Close', 'common_CloseH', 'common_CloseBroken', 'common_CloseBrokenH', 'common_Miniaturize', 'common_MiniaturizeH')


def run(artifacts, source=None, reference_probe=None):
    originals = REPO / 'Libraries/gnustep/nextspace-theme/Resources/ThemeImages'
    source = source or originals / 'WindowControls.svg'
    artwork = Artwork(source)
    references = REPO / 'Tests/Wayland/artwork-originals'
    pinned = json.loads((references / 'manifest.json').read_text())['cases']
    artifacts.mkdir(parents=True, exist_ok=True)
    records = []
    reconstructed = [name for name, node in artwork.symbols.items() if node.get('data-reconstructed') == 'true']
    for name in dict.fromkeys((*GLYPHS, *reconstructed)):
        path = originals / (name + '.tiff')
        original_resource = str(path.relative_to(REPO))
        if not path.is_file():
            filename = name + '.tiff'
            assert Path(filename).name == filename, name
            archive = REPO / 'Libraries/gnustep/gnustep-gui-images.tar.gz'
            with tarfile.open(archive) as resources:
                member = resources.getmember(filename)
                assert member.isfile(), filename
                data = resources.extractfile(member).read()
            path = artifacts / 'original-resources' / filename
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(data)
            original_resource = str(archive.relative_to(REPO)) + '#' + filename
        selection = None
        if reference_probe:
            process = subprocess.run([str(reference_probe), '--image-reference', str(path),
                str(artifacts / (name + '-original.png'))], capture_output=True, text=True, timeout=15)
            assert process.returncode == 0, (name, process.stderr)
            selection = json.loads(process.stdout)
            reference = artifacts / (name + '-original.png')
        else:
            fixture = pinned[name]
            assert fixture['source'] == original_resource
            assert hashlib.sha256(path.read_bytes()).hexdigest() == fixture['source_sha256'], name
            reference = references / (name + '.png')
            assert hashlib.sha256(reference.read_bytes()).hexdigest() == fixture['png_sha256'], name
            selection = fixture['selection']
        with Image.open(reference) as image:
            original = image.convert('RGBA')
        replacement = artwork.render(name, original.size)
        tolerance = 1 if name == 'common_Tile' else 0
        if name in reconstructed:
            if selection:
                index = selection['density_selections'][0]['representation_index']
                rep = selection['representations'][index]
                node = artwork.symbols[name]
                logical = tuple(map(float, node.get('data-logical-size', '').split() or node.get('viewBox').split()[2:]))
                assert all(math.isclose(value, rep['logical_'+axis], abs_tol=.00001)
                    for value, axis in zip(logical, ('width','height'))), (name, logical, rep)
            assert original.getchannel('A').tobytes() == replacement.getchannel('A').tobytes()
            higher = [artwork.render(name, tuple(backing_size(points, density) for points in original.size))
                for density in (150,180,210,240)]
            assert_not_enlarged([replacement, *higher], name)
        # Check alpha separately and composite onto both extremes. RGB under a
        # fully transparent pixel is not visible artwork and need not match.
        differences = [ImageChops.difference(original.getchannel('A'), replacement.getchannel('A'))]
        for value in (0, 255):
            background = Image.new('RGBA', original.size, (value, value, value, 255))
            differences.append(ImageChops.difference(
                Image.alpha_composite(background, original).convert('RGB'),
                Image.alpha_composite(background, replacement).convert('RGB')))
        maximum = max(max(difference.getextrema()) if difference.mode == 'L'
            else max(high for low, high in difference.getextrema()) for difference in differences)
        original.save(artifacts / (name + '-original.png'))
        replacement.save(artifacts / (name + '-vector.png'))
        records.append(dict(symbol=name, original_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            original_resource=original_resource,
            size=list(original.size), maximum_channel_difference=maximum, tolerance=tolerance,
            original_selection=selection))
    report = dict(purpose='Original-artwork fidelity, not HiDPI or full-library qualification',
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        reference_method='live GNUstep export' if reference_probe else 'pinned GNUstep export; source SHA-256 verified',
        cases=records, passed=all(row['maximum_channel_difference'] <= row['tolerance'] for row in records))
    (artifacts / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    assert report['passed'], records
    print(f'Original artwork fidelity: {len(GLYPHS)} title glyphs match exactly at 100%')
    if 'common_Tile' in reconstructed:
        print('Original tile: alpha matches exactly, continuous gradient differs by at most one channel level')
    print(f'Reconstructed theme symbols checked against originals: {len(reconstructed)}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--source', type=Path, help='Alternative theme artwork for fidelity checks')
    parser.add_argument('--reference-probe', type=Path, help='Export device-selected RGB references, including packed TIFFs')
    args = parser.parse_args()
    run(args.artifacts, args.source, args.reference_probe)
