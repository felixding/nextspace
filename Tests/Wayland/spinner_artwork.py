#!/usr/bin/env python3
"""Preserve the original stepped disk, measured outline and eight spin phases."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image, ImageChops, ImageFilter, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Packaging/Sources"))
from vector_art import Artwork
from artwork_reference import (
    artwork_original,
    assert_not_enlarged,
    assert_svg_representations,
    assert_vector_geometry,
)

SIZES = {"common_ProgressSpinning_" + str(i): (32, 32) for i in range(1, 9)}
PIXEL_SIZES = (32, 40, 48, 56, 64, 256)


def compare(original, frames, diagonal):
    low = frames[0]
    assert low.size == original.size == (32, 32)
    if not diagonal:
        assert low.tobytes() == original.tobytes(), "Original cardinal spinner changed"
        metrics = dict(all_original_rgba_pixels_identical=True)
    else:
        # The four original diagonal rasters have different one-pixel resampling
        # fringes. Preserve every certain interior pixel, measured coverage and
        # outline; do not turn those legacy fringes into enlarged pixel cells.
        alpha_before, alpha_after = original.getchannel("A"), low.getchannel("A")
        assert set(alpha_after.getdata()) == {0, 255}
        assert alpha_before.getbbox() == alpha_after.getbbox()
        assert (
            sum(a > 0 for a in alpha_before.getdata())
            == sum(a > 0 for a in alpha_after.getdata())
            == 802
        )
        outline_changes = sum(
            a != b for a, b in zip(alpha_before.getdata(), alpha_after.getdata())
        )
        assert outline_changes <= 2, "Original diagonal silhouette changed"
        for mask, other in ((alpha_before, alpha_after), (alpha_after, alpha_before)):
            assert (
                ImageChops.subtract(
                    mask, other.filter(ImageFilter.MaxFilter(3))
                ).getbbox()
                is None
            )
        for axis in (0, 1):
            old = sum(
                (x if axis == 0 else y)
                for y in range(32)
                for x in range(32)
                if original.getpixel((x, y))[3]
            )
            new = sum(
                (x if axis == 0 else y)
                for y in range(32)
                for x in range(32)
                if low.getpixel((x, y))[3]
            )
            assert abs(old - new) <= 1, "Original disk centroid moved"
        certain = 0
        certain_max = 0
        for y in range(1, 31):
            for x in range(1, 31):
                color = original.getpixel((x, y))
                if all(
                    original.getpixel((x + dx, y + dy)) == color
                    for dx in (-1, 0, 1)
                    for dy in (-1, 0, 1)
                ):
                    difference = max(
                        abs(a - b) for a, b in zip(color, low.getpixel((x, y)))
                    )
                    certain_max = max(certain_max, difference)
                    assert difference <= 1, "Original spinner interior changed"
                    certain += 1
        assert certain >= 600
        delta = ImageChops.difference(original.convert("RGBa"), low.convert("RGBa"))
        mean = sum(sum(p) for p in delta.getdata()) / (32 * 32 * 4)
        assert mean <= 2.5, "Diagonal raster-edge error exceeded its measured bound"
        metrics = dict(
            all_original_rgba_pixels_identical=False,
            certain_original_pixels=certain,
            maximum_certain_channel_difference=certain_max,
            silhouette_changed_pixels=outline_changes,
            support_pixels=802,
            mean_associated_rgba_error=mean,
        )
    assert_not_enlarged(frames, "continuous stepped spinner geometry")
    return metrics


def run(artifacts, source=None, images=None):
    repository = Path(__file__).resolve().parents[2]
    source = source or repository / "Libraries/gnustep/Artwork.svg"
    artwork = Artwork(source)
    assert_vector_geometry(artwork.root)
    artifacts.mkdir(parents=True)
    records = []
    for index, (name, size) in enumerate(SIZES.items(), 1):
        original, fixture = artwork_original("progress-spinners", name)
        frames = [artwork.render(name, (pixels, pixels)) for pixels in PIXEL_SIZES]
        metrics = compare(original, frames, index % 2 == 0)
        if images:
            assert_svg_representations(artwork, name, images / (name + ".tiff"), size)
        low = frames[0]
        shifted = Image.new("RGBA", size)
        shifted.paste(low, (1, 0))
        opaque = low.copy()
        opaque.putalpha(255)
        inverted = ImageOps.invert(low.convert("RGB")).convert("RGBA")
        inverted.putalpha(low.getchannel("A"))
        missing = low.copy()
        missing.paste((0, 0, 0, 0), (8, 8, 24, 24))
        controls = [
            (label, [candidate, *frames[1:]])
            for label, candidate in (
                ("shifted", shifted),
                ("mirrored", ImageOps.mirror(low)),
                ("lost-transparency", opaque),
                ("reversed-ink", inverted),
                ("missing-stepped-cut", missing),
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
                compare(original, candidate, index % 2 == 0)
            except AssertionError:
                pass
            else:
                raise AssertionError("Spinner mutation accepted: " + label)
        for pixels, frame in zip(PIXEL_SIZES, frames):
            frame.save(artifacts / f"{name}-{pixels}.png")
        records.append(
            dict(
                name=name,
                original_source_sha256=fixture["source_sha256"],
                negative_controls=len(controls),
                **metrics,
            )
        )
    result = dict(
        passed=True,
        cases=records,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        master_sha256=hashlib.sha256(
            (source.parent / "ProgressSpinners.svg").read_bytes()
        ).hexdigest(),
        exact_original_cardinal_states=4,
        diagonal_differences_confined_to_original_raster_edges=True,
        fractional_rasterization_verified=True,
        submitted_images_verified=images is not None,
        full_plan_complete=False,
    )
    (artifacts / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        "Spinner artwork: exact cardinal states and protected original diagonal contours PASS.",
        flush=True,
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("artifacts", "source", "images"):
        parser.add_argument("--" + name, type=Path, required=name == "artifacts")
    args = parser.parse_args()
    run(args.artifacts, args.source, args.images)
