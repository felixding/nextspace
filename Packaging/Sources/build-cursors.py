#!/usr/bin/env python3
"""Build native Xcursor representations from the authored SVG masters."""
import argparse
import json
import os
from pathlib import Path
import shutil
import struct
from vector_art import Artwork, backing_sizes, premultiplied_bgra
from watch_artwork import validate as validate_watch

IMAGE = 0xfffd0002
SIZES = backing_sizes(24)


def representations(cursor, artwork, logical):
    chunks = []
    for size in SIZES:
        edge = lambda value: (value * size + logical // 2) // logical
        for frame in cursor['frames']:
            pixels = premultiplied_bgra(artwork.render(frame['symbol'], size))
            chunks.append((size, struct.pack('<9I', 36, IMAGE, size, 1, size, size,
                edge(cursor['hotspot'][0]), edge(cursor['hotspot'][1]), frame['duration_ms']) + pixels))
    offset = 16 + 12 * len(chunks)
    toc = bytearray()
    for size, chunk in chunks:
        toc.extend(struct.pack('<3I', IMAGE, size, offset))
        offset += len(chunk)
    return struct.pack('<4I', 0x72756358, 16, 0x10000, len(chunks)) + toc + b''.join(
        chunk for _, chunk in chunks)


def install(source, destination, reconstructed_only=False):
    specification = json.loads((source / 'scalable/cursors.json').read_text())
    assert specification['version'] == 1 and specification['logical_size'] == 24
    artwork = Artwork(source / 'scalable/cursors.svg')
    validate_watch(artwork.root)
    if reconstructed_only:
        install_original(source, destination)
    destination.mkdir(parents=True, exist_ok=True)
    for name in ('index.theme', 'cursor.theme', 'scalable/cursors.svg', 'scalable/cursors.json'):
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target)
    cursors = destination / 'cursors'
    cursors.mkdir(exist_ok=True)
    names = set()
    rendered = 0
    for cursor in specification['cursors']:
        aliases = [cursor['name'], *cursor['aliases']]
        for name in aliases:
            assert name and Path(name).name == name and name not in names, name
            names.add(name)
        reconstructed = all(artwork.symbols[frame['symbol']].get('data-reconstructed') == 'true'
            for frame in cursor['frames'])
        if reconstructed_only and not reconstructed:
            continue
        rendered += 1
        for name in aliases:
            target = cursors / name
            if target.exists() or target.is_symlink():
                target.unlink()
            if name == cursor['name']:
                target.write_bytes(representations(cursor, artwork, specification['logical_size']))
            else:
                original = source / 'cursors' / name
                assert original.is_symlink() and original.resolve() == (source / 'cursors' / cursor['name']).resolve(), name
                target.symlink_to(original.readlink())
    print(f'Native cursor theme: {rendered} vector designs, {len(names)} names, {len(SIZES)} backing sizes')


def install_original(source, destination):
    """Install the original cursor bytes and aliases without a redraw."""
    destination.mkdir(parents=True, exist_ok=True)
    for name in ('index.theme', 'cursor.theme'):
        shutil.copy2(source / name, destination / name)
    cursors = destination / 'cursors'
    cursors.mkdir(exist_ok=True)
    for original in (source / 'cursors').iterdir():
        target = cursors / original.name
        if target.is_symlink() or (original.is_symlink() and target.exists()):
            target.unlink()
        if original.is_symlink():
            target.symlink_to(os.readlink(original))
        else:
            shutil.copy2(original, target)
    print('Original NextSpace cursor artwork installed; HiDPI replacement pending')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--original', action='store_true', help='Preserve original artwork instead of rendering draft SVGs')
    selection.add_argument('--reconstructed-only', action='store_true',
        help='Render reconstructed designs and preserve the original files for other cursors')
    args = parser.parse_args()
    destination = Path(os.environ.get('DESTDIR', '/')) / 'usr/share/icons/NextSpace'
    if args.original:
        install_original(args.source, destination)
    else:
        install(args.source, destination, args.reconstructed_only)
