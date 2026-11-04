#!/usr/bin/env python3
"""Protect the original Workspace check mark and its continuous beveled strokes."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Packaging/Sources"))
from vector_art import Artwork
from artwork_reference import (
    artwork_original,
    assert_not_enlarged,
    assert_svg_representations,
    assert_vector_geometry,
)

SIZES = {"CheckMark": (10, 10)}
PIXEL_SIZES = (10, 13, 15, 18, 20, 80)


def compare(original, frames):
    assert frames[0].tobytes() == original.tobytes(), (
        "The original Workspace check mark changed"
    )
    assert_not_enlarged(frames, "continuous beveled check strokes")


def run(artifacts, source=None, images=None):
    repository = Path(__file__).resolve().parents[2]
    source = source or repository / "Applications/Workspace/Artwork.svg"
    artwork = Artwork(source)
    assert_vector_geometry(artwork.root)
    artifacts.mkdir(parents=True)
    original, fixture = artwork_original("workspace-checkmark", "CheckMark")
    frames = [artwork.render("CheckMark", (pixels, pixels)) for pixels in PIXEL_SIZES]
    compare(original, frames)
    if images:
        assert_svg_representations(
            artwork, "CheckMark", images / "CheckMark.tiff", (10, 10)
        )
    low = frames[0]
    shifted = Image.new("RGBA", (10, 10))
    shifted.paste(low, (1, 0))
    opaque, shade, tip, stem = (low.copy() for _ in range(4))
    opaque.putalpha(255)
    shade.putpixel((9, 1), (85, 85, 85, 255))
    tip.putpixel((9, 1), (0, 0, 0, 0))
    stem.paste((0, 0, 0, 0), (0, 3, 2, 6))
    controls = [
        (label, [picture, *frames[1:]])
        for label, picture in (
            ("shifted", shifted),
            ("mirrored", ImageOps.mirror(low)),
            ("lost-transparency", opaque),
            ("wrong-shade", shade),
            ("missing-shadow-tip", tip),
            ("missing-stem", stem),
        )
    ]
    for method in (Image.Resampling.NEAREST, Image.Resampling.LANCZOS):
        controls.append(
            (
                method.name.lower() + "-enlargement",
                [low.resize(frame.size, method) for frame in frames],
            )
        )
    for label, candidate in controls:
        try:
            compare(original, candidate)
        except AssertionError:
            pass
        else:
            raise AssertionError("CheckMark mutation accepted: " + label)
    for pixels, frame in zip(PIXEL_SIZES, frames):
        frame.save(artifacts / f"CheckMark-{pixels}.png")
    result = dict(
        passed=True,
        original_pixels_identical=True,
        negative_controls=len(controls),
        original_source_sha256=fixture["source_sha256"],
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        shared_master_sha256=hashlib.sha256(
            (repository / "Applications/Artwork/CheckGlyphs.svg").read_bytes()
        ).hexdigest(),
        submitted_images_verified=images is not None,
        full_plan_complete=False,
    )
    (artifacts / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        "Workspace CheckMark: exact original pixels and eight negative controls PASS",
        flush=True,
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("artifacts", "source", "images"):
        parser.add_argument("--" + name, type=Path, required=name == "artifacts")
    args = parser.parse_args()
    run(args.artifacts, args.source, args.images)
