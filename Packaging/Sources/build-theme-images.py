#!/usr/bin/env python3
"""Rasterize shared vector theme artwork at each backing density."""
import argparse
from pathlib import Path
from vector_art import Artwork, backing_sizes, write_tiff


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cursors', type=Path, help='Shared cursor SVG master for application fallback images')
    parser.add_argument('--reconstructed-only', action='store_true',
        help='Render only symbols reconstructed against the original design')
    args = parser.parse_args()
    artwork = Artwork(args.source)
    args.output.mkdir(parents=True, exist_ok=True)
    count = 0
    arrows = tuple('common_Arrow' + direction + state
        for direction in ('Up', 'Down', 'Left', 'Right') for state in ('', 'H'))
    for logical, names in ((6, ('common_Dimple', 'common_DimpleHoriz')),
            (15, ('common_SwitchOff', 'common_SwitchOn')), (16, ('common_RadioOn',)),
            ((16, 15), ('common_RadioOff',)), (9, arrows),
            (12, ('common_Close', 'common_CloseH', 'common_CloseBroken', 'common_CloseBrokenH', 'common_Miniaturize', 'common_MiniaturizeH')),
            (64, ('common_Tile',))):
        for name in names:
            if args.reconstructed_only and artwork.symbols[name].get('data-reconstructed') != 'true':
                continue
            write_tiff(artwork, name, args.output / (name + '.tiff'), logical)
            count += 1
    if args.cursors:
        artwork = Artwork(args.cursors)
        for name, symbol in (('common_ClosedHandCursor', 'grabbing'), ('common_OpenHandCursor', 'hand1'),
                ('common_copyCursor', 'dnd-copy'), ('common_linkCursor', 'dnd-link'), ('common_noCursor', 'dnd-no-drop')):
            if args.reconstructed_only and artwork.symbols[symbol].get('data-reconstructed') != 'true':
                continue
            write_tiff(artwork, symbol, args.output / (name + '.tiff'), 24)
            count += 1
    print(f'Native vector theme images: {count} designs, {len(backing_sizes(12))} backing sizes')


if __name__ == '__main__':
    main()
