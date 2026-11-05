#!/usr/bin/env python3
"""Test-only bitmap references from the existing NSScroller bridge (requires Pillow)."""
import argparse
import ctypes as C
from pathlib import Path
from PIL import Image
from helper import Bitmap

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--library', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args, backend_arguments = parser.parse_known_args()
args.output.mkdir(parents=True, exist_ok=True)
native = C.CDLL(str(args.library.resolve()))
native.nxs_scroller_create.argtypes = [C.c_int, C.c_void_p, C.c_void_p, C.c_void_p]
native.nxs_scroller_create.restype = C.c_void_p
native.nxs_scroller_sync.argtypes = [C.c_void_p] + [C.c_double] * 7 + [C.c_int]
native.nxs_scroller_draw.argtypes = [C.c_void_p, C.c_double]
native.nxs_scroller_draw.restype = Bitmap
native.nxs_scroller_destroy.argtypes = [C.c_void_p]
for name, horizontal, length, total, page in [
    ('disabled-horizontal', 1, 332, 332, 332),
    ('disabled-vertical', 0, 152, 152, 152),
    ('enabled-horizontal', 1, 332, 600, 332),
    ('enabled-vertical', 0, 152, 1200, 152),
]:
    control = native.nxs_scroller_create(horizontal, None, None, None)
    if not control:
        raise RuntimeError('Native control initialization failed')
    try:
        native.nxs_scroller_sync(control, length, 0, total, page, 40, page * .875, 0, 1)
        bitmap = native.nxs_scroller_draw(control, 1)
        pixels = C.string_at(bitmap.pixels, bitmap.stride * bitmap.height)
        Image.frombytes('RGBA', (bitmap.width, bitmap.height), pixels, 'raw', 'BGRA', bitmap.stride).save(args.output / (name + '.png'))
    finally:
        native.nxs_scroller_destroy(control)
