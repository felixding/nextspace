#!/usr/bin/env python3
"""Verify RGB artwork references selected by the actual GNUstep image reader."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

from PIL import Image
from PIL.TiffImagePlugin import AppendingTiffWriter


def alpha_geometry(original, actual):
    """Measure silhouette, ink coverage and alignment against a pinned original."""
    assert original.size==actual.size
    before,after=original.getchannel('A'),actual.getchannel('A')
    points=[(x,y) for y in range(original.height) for x in range(original.width)]
    values=[[image.getpixel(p) for p in points] for image in (before,after)]
    mass=[sum(v) for v in values];assert all(mass),'Artwork must have visible ink'
    masks=[{p for p,v in zip(points,row) if v>=128} for row in values]
    centers=[[sum(p[axis]*v for p,v in zip(points,row))/total for axis in (0,1)] for row,total in zip(values,mass)]
    return dict(shape_overlap=len(masks[0]&masks[1])/len(masks[0]|masks[1]),
        original_bounds=before.getbbox(),reconstructed_bounds=after.getbbox(),
        original_coverage=mass[0]/255,reconstructed_coverage=mass[1]/255,
        original_center=centers[0],reconstructed_center=centers[1],
        alpha_rms_difference=math.sqrt(sum((a-b)**2 for a,b in zip(*values))/len(points)))


def assert_not_enlarged(frames, name):
    """Reject bitmap enlargement using visible, premultiplied pixels."""
    assert len(frames) > 1, name
    for method in (Image.Resampling.NEAREST, Image.Resampling.LANCZOS):
        assert any(frames[0].resize(frame.size, method).convert('RGBa').tobytes() !=
            frame.convert('RGBa').tobytes() for frame in frames[1:]), name


def artwork_original(group, name, repository=None):
    """Load the pinned RGB original after checking both resource hashes."""
    repository = repository or Path(__file__).resolve().parents[2]
    references = repository / 'Tests/Wayland/artwork-originals'
    fixture = json.loads((references/'manifest.json').read_text())[group]['cases'][name]
    source, reference = repository/fixture['source'], references/fixture['png']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == fixture['source_sha256'], name
    assert hashlib.sha256(reference.read_bytes()).hexdigest() == fixture['png_sha256'], name
    with Image.open(reference) as image:
        return image.convert('RGBA'), fixture


def preferences_original(module, repository=None):
    return artwork_original('preferences', module, repository)


def assert_curve_arguments(root):
    """Reject incomplete Bezier commands that SVG renderers silently truncate."""
    commands='MmLlHhVvCcSsQqTtAaZz'
    number=r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
    arity={'C':6,'S':4,'Q':4,'T':2}
    for node in root.iter():
        if node.tag.rsplit('}',1)[-1]!='path':
            continue
        for command,data in re.findall('(['+commands+'])([^'+commands+']*)',node.get('d','')):
            count=arity.get(command.upper())
            if count is None:
                continue
            values=re.findall(number,data)
            assert values and len(values)%count==0 and not re.sub(number,'',data).strip(' \t\r\n,'), \
                ('Incomplete SVG curve',node.get('id'),command,data)


def assert_vector_geometry(root):
    assert not any(node.tag.rsplit('}',1)[-1] in ('image','foreignObject') for node in root.iter()),'Artwork must remain vector geometry'
    assert_curve_arguments(root)


def regional_error(original, actual, region):
    """Compare visible associated-alpha colors in a nonempty pixel region."""
    points=list(region)
    assert points, 'An artwork comparison needs pixels'
    before,after=original.convert('RGBa').load(),actual.convert('RGBa').load()
    delta=[abs(a-b) for p in points for a,b in zip(before[p],after[p])]
    channel=max(abs(sum(before[p][c]-after[p][c] for p in points))/len(points) for c in range(3))
    return dict(mean=sum(delta)/len(delta),rms=(sum(d*d for d in delta)/len(delta))**.5,
        maximum=max(delta),channel_mean_difference=channel)


def assert_svg_representations(artwork, name, source, logical):
    """Verify the submitted TIFF's pixels and logical size at each target scale."""
    from vector_art import DENSITIES, backing_size
    with Image.open(source) as image:
        assert image.n_frames == 5, ('Backing representations missing', source)
        for index, density in enumerate(DENSITIES[:5]):
            image.seek(index)
            expected = artwork.render(name, tuple(backing_size(value,density) for value in logical))
            assert image.size == expected.size, (name, density, image.size)
            assert all(math.isclose(dpi,72*count/points,abs_tol=.00001)
                for dpi,count,points in zip(image.info['dpi'],expected.size,logical)), (name,density)
            assert image.convert('RGBA').tobytes() == expected.tobytes(), (name,density,'TIFF differs from SVG')


def run(probe, artifacts, expert=None, preferences=False, login=False, sound_controls=False, folders=False, root=False, terminal_strips=False, recycler=False, terminal_footer=False, textedit=False, review=False, openup=False, timemon=False, color_panel=False):
    artifacts.mkdir(parents=True)
    records = []

    def export(source, name):
        target = artifacts / (name + '.png')
        process = subprocess.run([str(probe), '--image-reference', str(source), str(target)],
            capture_output=True, text=True, timeout=15)
        (artifacts / (name + '.log')).write_text(process.stdout + process.stderr)
        assert process.returncode == 0, (source, process.stderr)
        metadata = json.loads(process.stdout)
        assert metadata['ok'] and target.is_file(), metadata
        records.append(dict(source=str(source), reference=target.name, **metadata))
        return Image.open(target).convert('RGBA'), metadata

    color = Image.new('RGBA', (12, 8))
    for rgba, box in zip(((0,0,0,0), (153,51,204,85), (51,153,102,170), (238,119,17,255)),
            ((0,0,6,4), (6,0,12,4), (0,4,6,8), (6,4,12,8))):
        color.paste(rgba, box)
    source = artifacts / 'alpha-source.png'
    color.save(source)
    actual, _ = export(source, 'alpha-reference')
    assert actual.size == color.size and actual.tobytes() == color.tobytes()

    # Equal dimensions cannot distinguish grayscale and color representations.
    for reverse in (False, True):
        name = 'color-first' if reverse else 'color-last'
        source = artifacts / (name + '.tiff')
        frames = [Image.new('L', color.size, 102), color]
        with source.open('w+b') as output:
            writer = AppendingTiffWriter(output)
            for frame in reversed(frames) if reverse else frames:
                frame.save(writer, format='TIFF', dpi=(72,72))
                writer.newFrame()
            writer.close()
            del writer
        actual, metadata = export(source, name)
        assert len(metadata['representations']) == 2, metadata
        assert metadata['density_selections'][0]['representation_index'] == (0 if reverse else 1), metadata
        assert actual.tobytes() == color.tobytes()

    if expert:
        actual, metadata = export(expert, 'expert-reference')
        assert actual.size == (60,49), actual.size
        assert metadata['density_selections'][0]['representation_index'] == 1, metadata
        expected = [(51,51,0,255), (51,68,68,255), (187,153,34,255), (187,204,187,255)]
        assert [actual.getpixel((x,y)) for y in (12,36) for x in (15,45)] == expected

    for group, enabled in (('preferences', preferences), ('login', login), ('sound_controls', sound_controls), ('folders', folders), ('root', root), ('terminal-strips', terminal_strips), ('recycler', recycler), ('terminal-footer', terminal_footer), ('textedit', textedit), ('review', review), ('openup', openup), ('timemon', timemon), ('color-panel', color_panel)):
        if not enabled:
            continue
        repository = Path(__file__).resolve().parents[2]
        references = Path(__file__).with_name('artwork-originals')
        definition = json.loads((references/'manifest.json').read_text())[group]
        fixtures = definition['cases']
        for name, fixture in fixtures.items():
            source = repository/fixture['source']
            expected, _ = artwork_original(group, name, repository)
            actual, metadata = export(source, group+'-'+name)
            assert actual.size == expected.size and actual.tobytes() == expected.tobytes(), name
            for key in ('representations','density_selections'):
                assert metadata[key] == fixture['selection'][key], (name,key,metadata[key])
        for name, alias in definition.get('aliases', {}).items():
            source = repository/alias['source']
            assert hashlib.sha256(source.read_bytes()).hexdigest() == alias['source_sha256'], name
            expected, _ = artwork_original(group, alias['reference'], repository)
            actual, metadata = export(source, group+'-'+name)
            assert actual.size == expected.size and actual.tobytes() == expected.tobytes(), name
            for key in ('representations','density_selections'):
                assert metadata[key] == alias['selection'][key], (name,key,metadata[key])

    (artifacts / 'results.json').write_text(json.dumps(dict(cases=records, complete=True), indent=2) + '\n')
    print(f'Artwork references: {len(records)} RGB selection and alpha checks PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--expert', type=Path, help='Original Preferences Expert TIFF')
    parser.add_argument('--preferences', action='store_true', help='Verify all ten device-selected Preferences originals')
    parser.add_argument('--login', action='store_true', help='Verify all seven device-selected Login originals')
    parser.add_argument('--sound-controls', action='store_true', help='Verify the four original Sound mixer images')
    parser.add_argument('--folders', action='store_true', help='Verify selected folder originals and every shared resource path')
    parser.add_argument('--root', action='store_true', help='Verify the DesktopKit and theme root computer originals')
    parser.add_argument('--terminal-strips', action='store_true', help='Verify both Terminal animation originals and their Gorm copies')
    parser.add_argument('--recycler', action='store_true', help='Verify the original Recycler occupied bounds and colors')
    parser.add_argument('--terminal-footer', action='store_true', help='Verify the Terminal footer and its Gorm copy')
    parser.add_argument('--textedit', action='store_true', help='Verify the five original TextEdit resources')
    parser.add_argument('--review', action='store_true', help='Verify the twelve original Review resources')
    parser.add_argument('--timemon', action='store_true', help='Verify the original TimeMon pause image and its Gorm alias')
    parser.add_argument('--openup', action='store_true', help='Verify the three original OpenUp resources')
    parser.add_argument('--color-panel', action='store_true', help='Verify the seven pinned shared color-panel originals')
    args = parser.parse_args()
    run(args.probe.resolve(), args.artifacts.resolve(), args.expert.resolve() if args.expert else None,
        args.preferences, args.login, args.sound_controls, args.folders, args.root, args.terminal_strips, args.recycler, args.terminal_footer, args.textedit, args.review, args.openup, args.timemon, args.color_panel)
