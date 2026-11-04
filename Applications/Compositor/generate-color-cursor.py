#!/usr/bin/env python3
"""Compile the shared magnifier artwork for the compositor's color picker."""
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Packaging/Sources'))
from vector_art import Artwork, DENSITIES, backing_size, premultiplied_bgra


def main(destination, source):
    artwork = Artwork(source)
    assert artwork.symbols['MagnifyGlass'].get('data-reconstructed') == 'true'
    lines = ['/* Generated from Artwork.svg#MagnifyGlass; do not edit. */']
    for density in DENSITIES:
        size = backing_size(32, density)
        data = premultiplied_bgra(artwork.render('MagnifyGlass', size))
        pixels = struct.unpack('<' + 'I' * (size * size), data)
        lines.append(f'static uint32_t color_cursor_{density}[] = {{')
        for start in range(0, len(pixels), 8):
            lines.append('  ' + ','.join(f'0x{v:08x}' for v in pixels[start:start+8]) + ',')
        lines.append('};')
    lines += ['static const struct { int density, size; uint32_t *pixels; } color_cursors[] = {']
    for density in DENSITIES:
        lines.append(f'  {{{density}, {backing_size(32, density)}, color_cursor_{density}}},')
    lines += ['};']
    Path(destination).write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    main(*sys.argv[1:])
