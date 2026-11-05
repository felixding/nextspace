#!/usr/bin/env python3
"""Render references directly through NativeUI's public ABI, without Chromium."""
import argparse
import ctypes as C
import json
from pathlib import Path
from PIL import Image
from helper import Bitmap, Pump, Response
from native_controls import NativeControlServer, ControlConfig, ControlChanged

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--library', type=Path, required=True)
parser.add_argument('--controls', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args, _ = parser.parse_known_args()
args.output.mkdir(parents=True, exist_ok=True)
native = C.CDLL(str(args.library))
# Reuse only the C ABI declarations; no helper transport or browser participates.
api = NativeControlServer(native, Bitmap, Response, Pump, lambda _: None, [],
                          lambda *_: None, lambda: True, lambda *_, **__: None)
results = []
for item in json.loads(args.controls.read_text()):
    def save_image(suffix=''):
        image = native.nxs_control_draw(pointer, 1)
        assert image.pixels and image.stride == image.width * 4
        pixels = C.string_at(image.pixels, image.stride * image.height)
        Image.frombytes('RGBA', (image.width, image.height), pixels, 'raw', 'BGRA').save(args.output / (item['id'] + suffix + '.png'))
        return image
    def release(_):
        save_image('-pressed')
        native.nxs_control_send(pointer, 1, item['width'] / 2, item['height'] / 2, 0)
    pump = Pump(release)
    pointer = native.nxs_control_create(item['kind'], ControlChanged(), pump, None)
    assert pointer
    try:
        title = item['title'].encode('utf-8')
        config = ControlConfig(C.sizeof(ControlConfig), item['width'], item['height'],
                               0, 1, item['state'], item['enabled'], item['state'], 0, title)
        assert native.nxs_control_sync(pointer, C.byref(config))
        image = save_image()
        preferred = native.nxs_control_size(pointer)
        results.append(dict(id=item['id'], size=[image.width, image.height],
                            preferred=[preferred.width, preferred.height]))
        if item['enabled']:
            native.nxs_control_track(pointer, item['width'] / 2, item['height'] / 2, 0)
    finally:
        assert native.nxs_control_destroy(pointer)
(args.output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results))
