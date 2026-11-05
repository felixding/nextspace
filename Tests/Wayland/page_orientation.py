"""Keep the original page silhouettes, frames, palette and miniature print layout."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image, ImageDraw, ImageOps, ImageStat

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Packaging/Sources"))
from vector_art import Artwork
from artwork_reference import (
    artwork_original,
    assert_not_enlarged,
    assert_svg_representations,
    assert_vector_geometry,
    regional_error,
)

GEOMETRY = {
    "page_portrait": dict(
        paper=(8, 2, 32, 43),
        photo=(12, 12, 11, 9),
        header=(9, 5, 30, 5),
        columns=[(10, 24, 13, 18), (25, 12, 12, 30)],
    ),
    "page_landscape": dict(
        paper=(2, 7, 43, 32),
        photo=(5, 16, 11, 9),
        header=(3, 10, 41, 5),
        columns=[(4, 27, 12, 10), (18, 16, 12, 21), (32, 16, 11, 21)],
    ),
}
SIZES = {name: (48, 48) for name in GEOMETRY}


def points(rect):
    x, y, width, height = rect
    return [(px, py) for py in range(y, y + height) for px in range(x, x + width)]


def border(rect):
    x, y, width, height = rect
    return [
        (px, py)
        for px, py in points(rect)
        if px in (x, x + width - 1) or py in (y, y + height - 1)
    ]


def box(rect):
    x, y, width, height = rect
    return (x, y, x + width, y + height)


def compare(original, low, high, name):
    assert original.size == low.size == (48, 48)
    assert original.getchannel("A").tobytes() == low.getchannel("A").tobytes(), (
        "Paper/shadow geometry changed"
    )
    whole = regional_error(original, low, points((0, 0, 48, 48)))
    assert whole["mean"] <= 4 and whole["rms"] <= 10, (
        "Paper composition/palette changed",
        name,
        whole,
    )
    design = GEOMETRY[name]
    for part, value in [("paper", 63), ("photo", 79)]:
        assert all(
            low.getpixel(p) == original.getpixel(p) == (value, value, value, 255)
            for p in border(design[part])
        ), (name, part, "Square frame changed")
    x, y, width, height = design["photo"]
    photo = regional_error(original, low, points((x + 1, y + 1, width - 2, height - 2)))
    assert photo["mean"] <= 8 and photo["rms"] <= 12, (
        "Grayscale photograph changed",
        name,
        photo,
    )
    header = regional_error(original, low, points(design["header"]))
    assert header["mean"] <= 18 and header["rms"] <= 28, (
        "Header lighting/print changed",
        name,
        header,
    )
    columns = []
    for rect in design["columns"]:
        before = ImageStat.Stat(original.crop(box(rect)).convert("RGB"))
        after = ImageStat.Stat(low.crop(box(rect)).convert("RGB"))
        assert max(abs(a - b) for a, b in zip(before.mean, after.mean)) <= 3, (
            name,
            "Column ink density changed",
            before.mean,
            after.mean,
        )
        assert all(
            0.75 * a <= b <= 1.25 * a for a, b in zip(before.stddev, after.stddev)
        ), (name, "Column contrast changed", before.stddev, after.stddev)
        columns.append(
            dict(
                original_mean=before.mean,
                reconstructed_mean=after.mean,
                original_contrast=before.stddev,
                reconstructed_contrast=after.stddev,
            )
        )
    assert_not_enlarged([low, high], name)
    return dict(
        original_alpha_identical=True,
        square_frames_identical=True,
        whole=whole,
        photo=photo,
        header=header,
        columns=columns,
    )


def run(artifacts, source=None, images=None):
    repository = Path(__file__).resolve().parents[2]
    source = source or repository / "Libraries/gnustep/Artwork.svg"
    artwork = Artwork(source)
    assert_vector_geometry(artwork.root)
    artifacts.mkdir(parents=True)
    records = []
    for name, size in SIZES.items():
        original, fixture = artwork_original("page-orientation", name)
        low = artwork.render(name, size)
        high = artwork.render(name, (384, 384))
        result = compare(original, low, high, name)
        if images:
            assert_svg_representations(artwork, name, images / (name + ".tiff"), size)
        changed = []
        shifted = Image.new("RGBA", size)
        shifted.paste(low, (1, 0))
        changed.extend(
            [("shifted", shifted, high), ("mirrored", ImageOps.mirror(low), high)]
        )
        for label, rect, fill in [
            ("frame", GEOMETRY[name]["paper"], (85, 85, 85, 255)),
            ("missing-photo", GEOMETRY[name]["photo"], (255, 255, 255, 255)),
            ("missing-header", GEOMETRY[name]["header"], (234, 234, 234, 255)),
            ("flat-print", GEOMETRY[name]["columns"][0], (226, 226, 226, 255)),
        ]:
            candidate = low.copy()
            candidate.paste(fill, box(rect))
            changed.append((label, candidate, high))
        candidate = low.copy()
        x, y, w, h = GEOMETRY[name]["photo"]
        candidate.paste((0, 0, 255, 255), (x + 1, y + 1, x + w - 1, y + h - 1))
        changed.append(("unrelated-photo", candidate, high))
        candidate = low.copy()
        for p in points((0, 0, 48, 48)):
            if 0 < candidate.getpixel(p)[3] < 255:
                candidate.putpixel(p, (0, 0, 0, 0))
        changed.append(("missing-shadow", candidate, high))
        for method in (Image.Resampling.NEAREST, Image.Resampling.LANCZOS):
            changed.append(
                (method.name + "-enlargement", low, low.resize(high.size, method))
            )
        for label, candidate, enlarged in changed:
            try:
                compare(original, candidate, enlarged, name)
            except AssertionError:
                pass
            else:
                raise AssertionError("Page mutation accepted: " + label)
        low.save(artifacts / (name + "-base.png"))
        high.save(artifacts / (name + "-high.png"))
        records.append(
            dict(
                name=name,
                design=result,
                original_source_sha256=fixture["source_sha256"],
                negative_controls=len(changed),
            )
        )
    result = dict(
        passed=True,
        cases=records,
        negative_controls=sum(r["negative_controls"] for r in records),
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        master_sha256=hashlib.sha256(
            (source.parent / "PageOrientation.svg").read_bytes()
        ).hexdigest(),
        submitted_images_verified=images is not None,
        original_microscopic_wording_recovered=False,
        full_plan_complete=False,
    )
    (artifacts / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        "Page orientation: exact silhouettes/frames, original palette/layout and twenty negative controls PASS."
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("artifacts", "source", "images"):
        parser.add_argument("--" + name, type=Path, required=name == "artifacts")
    args = parser.parse_args()
    run(args.artifacts, args.source, args.images)
