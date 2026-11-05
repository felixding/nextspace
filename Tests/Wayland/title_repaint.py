#!/usr/bin/env python3
"""Require identical AppKit key titles before and after a focus round trip."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops


def run(artifacts):
    records = json.loads((artifacts / "results.json").read_text())
    results = []
    for density in (120, 150, 180, 210, 240):
        pair = [next(r for r in records if not r["decorated"] and r["density"] == density
                     and r["label"] == label) for label in ("key", "key-restored")]
        assert all(r["appkit"]["key"] and r["title_state"] == 0 for r in pair), pair
        assert all(pair[0]["window"][k] == pair[1]["window"][k]
                   for k in ("frame_width", "frame_height", "buffer_width", "buffer_height", "style")), pair
        paths = [artifacts / "client" / f"{density}-{label}.png" for label in ("key", "key-restored")]
        images = []
        for path in paths:
            with Image.open(path) as image:
                images.append(image.convert("RGBA"))
        assert images[0].size == images[1].size
        difference = ImageChops.difference(*images)
        extrema = difference.getextrema()
        results.append(dict(density=density, identical=all(bounds == (0, 0) for bounds in extrema),
            difference_extrema=extrema, rgb_difference_bounds=difference.convert("RGB").getbbox(),
            pixel_hashes=[hashlib.sha256(image.tobytes()).hexdigest() for image in images]))
    (artifacts / "repaint-results.json").write_text(json.dumps(results, indent=2) + "\n")
    failed = [row["density"] for row in results if not row["identical"]]
    assert not failed, f"AppKit key title changes after focus restoration at densities: {failed}"
    print("AppKit retained key-title repaint: all five densities PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True, help="Completed title_states.py captures")
    run(**vars(parser.parse_args()))
