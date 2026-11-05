#!/usr/bin/env python3
"""Verify Login's vector-derived pixels and AppKit density selection."""
import argparse
import json
import math
from pathlib import Path
import subprocess
from PIL import Image


def check_panel(capture, images, scale):
    """Catch embedded Gorm bitmaps even when the loose TIFF files are sharp."""
    with Image.open(capture) as image:
        actual = image.convert('RGB')
    expected_size = tuple((value * scale + 60) // 120 for value in (462, 260))
    assert actual.size == expected_size, (actual.size, expected_size)
    if scale in (120, 240):
        with Image.open(images / 'Panel.tiff') as image:
            image.seek(0 if scale == 120 else 4)
            reference = image.convert('RGB')
        # This region contains only the wordmark, away from the hostname field.
        box = tuple(value * scale // 120 for value in (105, 10, 355, 70))
        # The existing Gorm image view starts at logical x=1, y=0.
        inset = scale // 120
        source_box = (box[0] - inset, box[1], box[2] - inset, box[3])
        assert actual.crop(box).tobytes() == reference.crop(source_box).tobytes(), 'Login still draws archived or enlarged panel artwork'


def run(probe, images, artifacts):
    artifacts.mkdir(parents=True)
    records = []
    dimensions = dict(Panel=(462, 260), Fields=(328, 63), FieldNames=(115, 63),
        powerbuttonup=(48, 48), powerbuttondown=(48, 48),
        restartbuttonup=(48, 48), restartbuttondown=(48, 48))
    for name, logical in dimensions.items():
        path = images / (name + '.tiff')
        sizes = [tuple((value * density + 60) // 120 for value in logical)
            for density in (120, 150, 180, 210, 240)]
        with Image.open(path) as image:
            assert image.n_frames == 5, path
            base = image.convert('RGBA')
            for index, size in enumerate(sizes):
                image.seek(index)
                assert image.size == size, (path, index, image.size)
                assert all(math.isclose(dpi, 72*pixels/points, abs_tol=0.00001)
                    for dpi, pixels, points in zip(image.info['dpi'], size, logical)), path
            if name != 'Fields':
                high = image.convert('RGBA').tobytes()
                for method in (Image.Resampling.NEAREST, Image.Resampling.LANCZOS):
                    assert high != base.resize(sizes[-1], method).tobytes(), (name, method)
        process = subprocess.run([str(probe), '--image-density', str(path)],
            capture_output=True, text=True, timeout=15)
        (artifacts / (name + '.log')).write_text(process.stdout + process.stderr)
        assert process.returncode == 0, (name, process.stderr)
        result = json.loads(process.stdout)
        assert result['ok'] and len(result['representations']) == 5, result
        assert len(result['density_selections']) == 11, result
        for rep, size in zip(result['representations'], sizes):
            assert (rep['width'], rep['height']) == size, rep
            assert all(math.isclose(rep['logical_' + axis], points, abs_tol=0.001)
                for axis, points in zip(('width', 'height'), logical)), rep
        for selection, size in zip(result['density_selections'], sizes):
            assert (selection['width'], selection['height']) == size, (name, selection, size)
        records.append(dict(name=name, **result))
    (artifacts / 'results.json').write_text(json.dumps(dict(cases=records, complete=True), indent=2) + '\n')
    print('Vector Login artwork: 35 AppKit density selections and independent high-density pixels PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--images', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    run(args.probe, args.images, args.artifacts)
