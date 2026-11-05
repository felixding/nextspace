#!/usr/bin/env python3
"""Independently verify odd-size diagnostic PNG channels and alpha rounding."""
import argparse
import json
from pathlib import Path
import subprocess
from PIL import Image


def run(probe, artifacts):
    artifacts.mkdir(parents=True, exist_ok=True)
    for kind in (0, 1):
        path = artifacts / f'pixels-{kind}.png'
        reference = artifacts / f'reference-{kind}.png'
        subprocess.run([str(probe), str(kind), str(path), str(reference)], check=True)
        with Image.open(path) as image:
            assert image.size == (257, 259)
            actual = image.convert('RGBA')
            for y in range(259):
                for x in range(257):
                    alpha = 255 if kind else (x + 3*y) % 256
                    premultiplied = [((value & 255)*alpha + 128)//256 for value in (x, y, x^y)]
                    expected = tuple((value*255 + alpha//2)//alpha if alpha else 0 for value in premultiplied) + (alpha,)
                    assert actual.getpixel((x, y)) == expected, (kind, x, y, actual.getpixel((x, y)), expected)
            with Image.open(reference) as expected:
                assert actual.tobytes() == expected.convert('RGBA').tobytes()
    subprocess.run([str(probe), '2', 'unused', 'unused'], check=True)
    (artifacts / 'results.json').write_text(json.dumps(dict(complete=True, formats=2,
        decoded_pixels=257*259*2, write_failure=True)) + '\n')
    print('Diagnostic capture: 133126 independently decoded RGB/alpha pixels and write failure PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    run(args.probe, args.artifacts)
