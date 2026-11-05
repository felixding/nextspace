#!/usr/bin/env python3
"""Check the six original stripe phases and their continuous diagonal master."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image, ImageChops, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Packaging/Sources"))
from vector_art import Artwork
from artwork_reference import (
    artwork_original,
    assert_not_enlarged,
    assert_svg_representations,
    assert_vector_geometry,
)

PHASES = (9, 5, 1, 9, 5, 1)
SIZES = {"common_ProgressIndeterminate_" + str(i): (24, 24) for i in range(1, 7)}
PIXEL_SIZES = (24, 30, 36, 42, 48, 192)


def compare(original, frames):
    assert frames[0].size == original.size
    assert frames[0].tobytes() == original.tobytes(), (
        "Original stripe phase or color changed"
    )
    assert_not_enlarged(frames, "continuous diagonal progress stripes")


def run(artifacts, source=None, images=None):
    repository = Path(__file__).resolve().parents[2]
    source = source or repository / "Libraries/gnustep/Artwork.svg"
    artwork = Artwork(source)
    assert_vector_geometry(artwork.root)
    artifacts.mkdir(parents=True)
    records = []
    for name, size in SIZES.items():
        original, fixture = artwork_original("progress-stripes", name)
        frames = [artwork.render(name, (pixels, pixels)) for pixels in PIXEL_SIZES]
        compare(original, frames)
        if images:
            assert_svg_representations(artwork, name, images / (name + ".tiff"), size)
        low = frames[0]
        wrong_gray = low.copy()
        wrong_gray.paste(
            (170, 170, 170, 255), (0, 0, 24, 24), low.convert("RGB").convert("L")
        )
        opaque = low.copy()
        opaque.putpixel((12, 12), (0, 0, 0, 0))
        candidates = [
            ("shifted-phase", ImageChops.offset(low, 1, 0)),
            ("wrong-direction", ImageOps.mirror(low)),
            ("wrong-gray", wrong_gray),
            ("lost-opacity", opaque),
        ]
        controls = [
            (label, [candidate, *frames[1:]]) for label, candidate in candidates
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
                raise AssertionError("Progress mutation accepted: " + label)
        for pixels, frame in zip(PIXEL_SIZES, frames):
            frame.save(artifacts / f"{name}-{pixels}.png")
        records.append(
            dict(
                name=name,
                original_source_sha256=fixture["source_sha256"],
                original_pixels_identical=True,
                negative_controls=len(controls),
            )
        )
    result = dict(
        passed=True,
        cases=records,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        master_sha256=hashlib.sha256(
            (source.parent / "ProgressStripes.svg").read_bytes()
        ).hexdigest(),
        fractional_rasterization_verified=True,
        submitted_images_verified=images is not None,
        full_plan_complete=False,
    )
    (artifacts / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        "Progress artwork: six exact stripe phases and continuous diagonals PASS.",
        flush=True,
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("artifacts", "source", "images"):
        parser.add_argument("--" + name, type=Path, required=name == "artifacts")
    args = parser.parse_args()
    run(args.artifacts, args.source, args.images)
