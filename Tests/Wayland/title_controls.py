#!/usr/bin/env python3
"""Compare production Cairo title paths with the shared SVG at every density."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from PIL import Image
from artwork_reference import assert_not_enlarged
from artwork_fidelity import GLYPHS

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'Packaging/Sources'))
from vector_art import Artwork, DENSITIES, backing_size


def run(probe, artifacts):
    probe = probe.resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    art = Artwork(REPO / 'Libraries/gnustep/nextspace-theme/Resources/ThemeImages/WindowControls.svg')
    records = []
    for index, name in enumerate(GLYPHS):
        frames = []
        for density in DENSITIES:
            size = backing_size(12, density)
            expected = art.render(name, size)
            center = expected.getpixel((size // 2, size // 2))
            if 'Broken' in name or 'Miniaturize' in name:
                assert center == ((255, 255, 255, 255) if name.endswith('H') else (0, 0, 0, 0))
            else:
                assert center == ((85, 85, 85, 255) if name.endswith('H') else (0, 0, 0, 255))
            frames.append(expected)
            for x, y in ((0, 0), (1, 3), (783, 5)):
                path = artifacts / f'{name}-{density}-{x}-{y}.png'
                subprocess.run([str(probe), str(index), str(density), str(x), str(y), str(path)], check=True)
                with Image.open(path) as source:
                    actual = source.convert('RGBA')
                assert actual.size == expected.size
                assert actual.getchannel('A').tobytes() == expected.getchannel('A').tobytes(), (name, density, x, y)
                assert actual.convert('RGBa').tobytes() == expected.convert('RGBa').tobytes(), (name, density, x, y)
                records.append(dict(symbol=name, density=density, origin=[x, y], pixels_exact=True))
        assert_not_enlarged(frames, name)
    report = dict(passed=True, cases=records, original_fidelity_qualified=False,
        scope='Production Cairo/SVG equivalence and enlargement rejection; original fidelity checked separately')
    (artifacts / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'Title controls: {len(records)} exact Cairo/SVG comparisons PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    options = parser.parse_args()
    run(options.probe, options.artifacts)
