#!/usr/bin/env python3
"""Qualify the bitmap formats advertised by Review against independent pixels."""
import argparse
import json
from pathlib import Path
import subprocess
from PIL import Image
from PIL.TiffImagePlugin import AppendingTiffWriter
from artwork_reference import run as image_references


def save_formats(source, artifacts):
    with Image.open(source) as original:
        image = original.convert('RGB')
    paths = []
    for extension in ('tiff', 'jpg', 'gif'):
        path = artifacts / ('image.' + extension)
        image.save(path)
        paths.append(path)
    indexed = image.quantize(colors=16)
    colors = indexed.getpalette()
    color_count = len(colors) // 3
    indices = list(indexed.getdata())
    symbols = 'abcdefghijklmnop'
    path = artifacts / 'image.xpm'
    lines = ['/* XPM */', 'static char *pixels[] = {', f'"{image.width} {image.height} {color_count} 1",']
    lines += [f'"{symbol} c #{colors[index*3]:02x}{colors[index*3+1]:02x}{colors[index*3+2]:02x}",'
        for index, symbol in enumerate(symbols[:color_count])]
    lines += ['"' + ''.join(symbols[value] for value in indices[row*image.width:(row+1)*image.width]) +
        ('",' if row < image.height-1 else '"') for row in range(image.height)]
    path.write_text('\n'.join(lines) + '\n};\n')
    return [*paths, path]


def density_rounding(probe, artifacts):
    records = []
    fixtures = (
        ('strip', (2, 1), ((2, 1), (3, 1), (3, 2), (4, 2)),
            ((2, 1), (3, 1), (3, 2), (4, 2), (4, 2))),
        ('square', (2, 2), ((2, 2), (3, 3), (4, 4)),
            ((2, 2), (3, 3), (3, 3), (4, 4), (4, 4))),
        ('rectangle', (2, 3), ((2, 3), (3, 4), (3, 5), (4, 5), (4, 6)),
            ((2, 3), (3, 4), (3, 5), (4, 5), (4, 6))),
        ('precision', (66, 57), ((66,57),(83,71),(99,86),(116,100),(132,114)),
            ((66,57),(83,71),(99,86),(116,100),(132,114))),
    )
    for name, logical, sizes, expected in fixtures:
        for reverse in (False, True):
            case = name + ('-reverse' if reverse else '-forward')
            path = artifacts / (case + '.tiff')
            with path.open('w+b') as output:
                writer = AppendingTiffWriter(output)
                for width, height in reversed(sizes) if reverse else sizes:
                    image = Image.new('RGBA', (width, height), (255, 0, 0, 255))
                    image.save(writer, format='TIFF', dpi=(72*width/logical[0], 72*height/logical[1]))
                    writer.newFrame()
                writer.close()
                del writer
            process = subprocess.run([str(probe), '--image-density', str(path)],
                capture_output=True, text=True, timeout=15)
            (artifacts / (case + '.log')).write_text(process.stdout + process.stderr)
            assert process.returncode == 0, (case, process.stderr)
            result = json.loads(process.stdout)
            assert all(abs(rep['logical_width'] - logical[0]) < 0.001 and
                abs(rep['logical_height'] - logical[1]) < 0.001 for rep in result['representations']), (case, result)
            selections = result['density_selections'][:5]
            assert [row['scale'] for row in selections] == [1, 1.25, 1.5, 1.75, 2], result
            assert [(row['width'], row['height']) for row in selections] == list(expected), (case, result)
            records.append(dict(case=case, **result))
    return records


def run(probe, artifacts):
    artifacts.mkdir(parents=True)
    source = artifacts / 'image.png'
    image = Image.new('RGB', (513, 387))
    for color, box in zip(((255,0,0), (0,255,0), (0,0,255), (255,255,0)),
            ((0,0,256,193), (256,0,513,193), (0,193,256,387), (256,193,513,387))):
        image.paste(color, box)
    image.save(source)
    records = []
    for path in [source, *save_formats(source, artifacts)]:
        process = subprocess.run([str(probe), '--decode-image', str(path)], capture_output=True, text=True, timeout=15)
        (artifacts / (path.suffix[1:] + '.log')).write_text(process.stdout + process.stderr)
        assert process.returncode == 0, (path, process.stdout, process.stderr)
        result = json.loads(process.stdout)
        assert result['ok'] and len(result['representations']) == 1, result
        actual = result['representations'][0]
        assert (actual['width'], actual['height']) == (513, 387), result
        with Image.open(path) as decoded:
            decoded = decoded.convert('RGBA')
            expected = [decoded.getpixel(((2*x+1)*decoded.width//4, (2*y+1)*decoded.height//4))
                for y in range(2) for x in range(2)]
        assert all(abs(value-reference) <= 1 for sample, reference_sample in zip(actual['samples'], expected)
            for value, reference in zip(sample, reference_sample)), (path, actual, expected)
        assert any('libgnustep-gui.so.' in value for value in result['libraries']), result
        records.append(dict(format=path.suffix[1:], **result))
        (artifacts / 'results.json').write_text(json.dumps(dict(cases=records, complete=False), indent=2) + '\n')
    invalid = []
    for length in range(4):
        path = artifacts / f'truncated-{length}.png'
        path.write_bytes(b'\x89PNG'[:length])
        process = subprocess.run([str(probe), '--decode-image', str(path)], capture_output=True, text=True, timeout=15)
        assert process.returncode == 1, (path, process.stdout, process.stderr)
        result = json.loads(process.stdout)
        assert not result['ok'] and not result['representations'], result
        invalid.append(dict(length=length, stderr=process.stderr, **result))
    density_cases = density_rounding(probe, artifacts)
    image_references(probe, artifacts / 'references')
    (artifacts / 'results.json').write_text(json.dumps(dict(cases=records, invalid_cases=invalid, density_cases=density_cases,
        reference_exports_checked=True, complete=True), indent=2) + '\n')
    print('Review PNG/TIFF/JPEG/GIF/XPM pixels, odd dimensions and truncated-input rejection: PASS')
    print('Image density: rounded dimensions, ties and TIFF precision in both representation orders PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    run(args.probe, args.artifacts)
