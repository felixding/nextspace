#!/usr/bin/env python3
"""Render SVG image symbols as TIFF representations at 100–200% density."""
import argparse
from pathlib import Path
from vector_art import Artwork, SVG, write_resource_images


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reconstructed-only', action='store_true',
        help='Render only symbols reconstructed against the original design')
    args = parser.parse_args()
    artwork = Artwork(args.source)
    args.output.mkdir(parents=True, exist_ok=True)
    count = 0
    for name, symbol in artwork.symbols.items():
        if symbol.tag != f'{{{SVG}}}symbol':
            continue
        if args.reconstructed_only and symbol.get('data-reconstructed') != 'true':
            continue
        x, y, width, height = map(float, symbol.get('viewBox').split())
        assert x == y == 0 and width > 0 and height > 0, name
        filenames = symbol.get('data-files')
        filenames = filenames.split() if filenames else [symbol.get('data-file', name + '.tiff')]
        write_resource_images(artwork, name, args.output, filenames, (width, height))
        count += 1
    assert count or args.reconstructed_only, 'The SVG must define image symbols with logical view boxes'
    print(f'Vector images: {count} designs, 5 backing densities')


if __name__ == '__main__':
    main()
