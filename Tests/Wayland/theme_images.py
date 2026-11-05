#!/usr/bin/env python3
"""Verify AppKit loads and selects vector theme representations at each density."""
import argparse
import json
import math
from pathlib import Path
import subprocess
from PIL import Image
from cursor_assets import frames
from artwork_reference import assert_not_enlarged
from cursor_fidelity import compare_original

# Original TIFF centimetre-resolution metadata, as decoded by GNUstep.
CONTROL_SIZES = {
    'common_SwitchOff': (15.003418111688841, 15.003418111688841),
    'common_SwitchOn': (15.003418111688841, 15.003418111688841),
    'common_RadioOff': (16.00364598580143, 15.003418111688841),
    'common_RadioOn': (16.00364598580143, 16.00364598580143),
    'common_OpenHandCursor': (23.996999479994628, 23.996999479994628),
}

def run(probe, images, artifacts, cursor_theme=Path('/usr/share/icons/NextSpace'), names=None, originals=None):
    artifacts.mkdir(parents=True)
    originals = originals or Path(__file__).resolve().parents[2] / 'Libraries/gnustep/nextspace-theme/Resources/ThemeImages'
    records = []
    cursors = dict(common_ClosedHandCursor='grabbing', common_OpenHandCursor='hand1',
        common_copyCursor='dnd-copy', common_linkCursor='dnd-link', common_noCursor='dnd-no-drop')
    arrows = tuple('common_Arrow' + direction + state
        for direction in ('Up', 'Down', 'Left', 'Right') for state in ('', 'H'))
    controls = ('common_Dimple','common_DimpleHoriz','common_SwitchOff','common_SwitchOn','common_RadioOn','common_RadioOff')
    images_by_size = {6: controls[:2], 15: controls[2:4], 16: controls[4:5], (16,15): controls[5:], 9: arrows,
        12: ('common_Close', 'common_CloseH', 'common_CloseBroken', 'common_CloseBrokenH', 'common_Miniaturize', 'common_MiniaturizeH'),
        24: tuple(cursors), 64: ('common_Tile',)}
    selected = set(names) if names else None
    assert not selected or not selected - {name for group in images_by_size.values() for name in group}, selected
    for logical, group in images_by_size.items():
        for name in group:
            if selected and name not in selected:
                continue
            points = CONTROL_SIZES.get(name, (logical,logical) if isinstance(logical,int) else logical)
            sizes = tuple(tuple(math.floor(value*scale+.5) for value in points)
                for scale in (1, 1.25, 1.5, 1.75, 2, 3, 4, 5, 6, 7, 8))
            path = images / (name + '.tiff')
            original_fidelity = None
            with Image.open(path) as image:
                assert image.n_frames == len(sizes), path
                for index, size in enumerate(sizes):
                    image.seek(index)
                    assert image.size == size and all(math.isclose(float(dpi),72*pixels/point,abs_tol=.00001)
                        for dpi,pixels,point in zip(image.info['dpi'],size,points)), path
                    if name in controls:
                        alpha = (0,255) if name in ('common_Dimple','common_DimpleHoriz') else (255,255)
                        assert image.convert('RGBA').getextrema()[3] == alpha, (name,size)
                    if name in cursors:
                        rgba = image.convert('RGBa').tobytes()
                        pixels = bytearray(len(rgba))
                        pixels[0::4], pixels[1::4], pixels[2::4], pixels[3::4] = rgba[2::4], rgba[1::4], rgba[0::4], rgba[3::4]
                        assert pixels == frames(cursor_theme / 'cursors' / cursors[name], size[0])[0]['pixels'], (name, size)
                if name in arrows or name in controls:
                    image.seek(0); original = image.convert('RGBA')
                    higher = []
                    for index in range(1,5):
                        image.seek(index); higher.append(image.convert('RGBA'))
                    # Aligned rectangles legitimately equal nearest scaling at
                    # 200%; fractional densities still distinguish fresh geometry.
                    assert_not_enlarged([original, *higher], name)
                if name in cursors:
                    reference = artifacts / (name + '-original.png')
                    original = subprocess.run([str(probe), '--image-reference',
                        str(originals / (name + '.tiff')), str(reference)],
                        capture_output=True, text=True, timeout=15)
                    (artifacts / (name + '-original.log')).write_text(original.stdout + original.stderr)
                    assert original.returncode == 0, (name,original.stderr)
                    selection = json.loads(original.stdout)
                    assert all(math.isclose(selection['representations'][0]['logical_'+axis],point,abs_tol=.00001)
                        for axis,point in zip(('width','height'),points)), selection
                    image.seek(0)
                    def associated(value):
                        value = value.convert('RGBa')
                        return Image.frombytes('RGBA',value.size,value.tobytes())
                    with Image.open(reference) as original_image:
                        original_fidelity = compare_original(associated(original_image),associated(image),cursors[name])
            process = subprocess.run([str(probe), '--image-density', str(path)],
                capture_output=True, text=True, timeout=15)
            (artifacts / (name + '.log')).write_text(process.stdout + process.stderr)
            assert process.returncode == 0, (name, process.stdout, process.stderr)
            result = json.loads(process.stdout)
            assert result['ok'] and [(rep['width'],rep['height']) for rep in result['representations']] == list(sizes), result
            for rep in result['representations']:
                assert all(math.isclose(rep['logical_'+axis],point,abs_tol=.00001)
                    for axis,point in zip(('width','height'),points)), rep
            for selection, size in zip(result['density_selections'], sizes):
                assert (selection['width'],selection['height']) == size, selection
            assert len(result['density_selections']) == len(sizes), result
            records.append(dict(name=name,original_fidelity=original_fidelity, **result))
    (artifacts / 'results.json').write_text(json.dumps(dict(cases=records, complete=True,
        full_library=selected is None), indent=2) + '\n')
    cursor_checks = sum(row['name'] in cursors for row in records)*11
    print(f'Vector theme images: {len(records)*11} AppKit density selections and {cursor_checks} cursor pixel comparisons PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', required=True)
    parser.add_argument('--images', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--cursor-theme', type=Path, default=Path('/usr/share/icons/NextSpace'))
    parser.add_argument('--image', action='append', help='Select a reconstructed image; omit for the complete library')
    parser.add_argument('--originals', type=Path, help='Original theme resources for design comparisons')
    args = parser.parse_args()
    run(args.probe, args.images, args.artifacts, args.cursor_theme, args.image, args.originals)
