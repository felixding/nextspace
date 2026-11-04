"""Check vector provenance, cursor metadata and genuine density representations."""
from pathlib import Path
import json
import struct
import xml.etree.ElementTree as ET


def pixels_hash(pixels):
    """Match the compositor's hash of associated-alpha ARGB buffer bytes."""
    value = 14695981039346656037
    for byte in pixels:
        value = ((value ^ byte) * 1099511628211) & 0xffffffffffffffff
    return f'{value:016x}'


def frames(path, size):
    data = Path(path).read_bytes()
    magic, header, version, count = struct.unpack_from('<4I', data)
    assert magic == 0x72756358 and version == 0x10000
    result = []
    for index in range(count):
        kind, nominal, offset = struct.unpack_from('<3I', data, header + 12 * index)
        assert kind == 0xfffd0002
        if nominal != size:
            continue
        length, kind, nominal, version, width, height, x, y, delay = struct.unpack_from('<9I', data, offset)
        assert length == 36 and version == 1
        pixels = data[offset + length:offset + length + width * height * 4]
        assert len(pixels) == width * height * 4
        result.append(dict(width=width, height=height, hotspot_x=x, hotspot_y=y,
            delay=delay, pixels=pixels, pixels_hash=pixels_hash(pixels)))
    assert result, (path, size)
    return result


def validate(theme, original=None):
    from PIL import Image, ImageChops
    sizes = (24, 30, 36, 42, 48, 72, 96, 120, 144, 168, 192)
    theme = Path(theme)
    specification = json.loads((theme / 'scalable/cursors.json').read_text())
    assert specification['version'] == 1 and specification['logical_size'] == 24
    source = (theme / 'scalable/cursors.svg').read_text()
    root = ET.fromstring(source)
    ids = [node.get('id') for node in root.iter() if node.get('id')]
    assert len(set(ids)) == len(ids) and root.get('viewBox') == '0 0 24 24'
    for node in root.iter():
        assert node.tag.rsplit('}', 1)[-1].lower() not in ('image', 'feimage', 'foreignobject', 'text')
        for attribute, value in node.attrib.items():
            if attribute.rsplit('}', 1)[-1] == 'href':
                assert value.startswith('#') and value[1:] in ids, value
            assert 'url(' not in value or 'url(#' in value, value
    assert '@import' not in source and 'data:' not in source
    names = set()
    metadata = ('width', 'height', 'hotspot_x', 'hotspot_y', 'delay')
    for cursor in specification['cursors']:
        path = theme / 'cursors' / cursor['name']
        assert path.is_file() and not path.is_symlink(), path
        for name in [cursor['name'], *cursor['aliases']]:
            assert name and Path(name).name == name and name not in names, name
            names.add(name)
            alias = theme / 'cursors' / name
            assert alias.resolve() == path.resolve(), alias
        base = frames(path, 24)
        if original:
            legacy = frames(Path(original) / 'cursors' / path.name, 24)
            assert [[frame[key] for key in metadata] for frame in base] == [
                [frame[key] for key in metadata] for frame in legacy], path.name
        for size in sizes:
            variants = frames(path, size)
            assert len(variants) == len(cursor['frames']), (path, size)
            for master, actual in zip(cursor['frames'], variants):
                edge = lambda value: (value * size + 12) // 24
                assert master['symbol'] in ids and (actual['width'], actual['height']) == (size, size)
                assert (actual['hotspot_x'], actual['hotspot_y'], actual['delay']) == (
                    edge(cursor['hotspot'][0]), edge(cursor['hotspot'][1]), master['duration_ms']), (path, size)
                b, g, r, alpha = (actual['pixels'][index::4] for index in range(4))
                assert any(alpha) and all(max(channels[:3]) <= channels[3] for channels in zip(b, g, r, alpha)), path
    assert names == {path.name for path in (theme / 'cursors').iterdir()}
    quality = []
    for name in ('left_ptr', 'hand1', 'hand2', 'grabbing', 'zoom-in', 'watch'):
        small, large = frames(theme / 'cursors' / name, 24), frames(theme / 'cursors' / name, 192)
        for base, actual in zip(small, large):
            low = Image.frombytes('RGBA', (24, 24), base['pixels'], 'raw', 'BGRA')
            high = Image.frombytes('RGBA', (192, 192), actual['pixels'], 'raw', 'BGRA')
            differences = {}
            for label, method in (('nearest', Image.Resampling.NEAREST), ('lanczos', Image.Resampling.LANCZOS)):
                diff = ImageChops.difference(high, low.resize(high.size, method))
                differences[label] = sum(any(pixel) for pixel in diff.getdata())
                assert differences[label] > 192, (name, label, differences)
            assert len(set(high.getchannel('A').getdata())) > 16, name
            quality.append(dict(name=name, different_pixels=differences))
    return dict(names=len(names), masters=len(specification['cursors']), sizes=list(sizes),
        legacy_metadata_compared=original is not None, vector_artwork=True, density_checks=quality)
