#!/usr/bin/env python3
"""Check logical title metrics, original tail policy and density-specific ink.

Both the legacy monochrome default and optional antialiasing are checked.
Generated original-code references are GPL, not linked into the MIT compositor.
"""
import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

from PIL import Image
from title_reference import Reference, TITLES, LIMITS



def check(probe, artifacts, antialiased):
    repo = Path(__file__).resolve().parents[2]
    artifacts.mkdir(parents=True, exist_ok=True)
    reference = Reference(repo)
    metadata = dict(**reference.metadata, probe_sha256=hashlib.sha256(probe.read_bytes()).hexdigest(),
                    reference_font="Helvetica:bold:pixelsize=12:antialias=" + ("true" if antialiased else "false"),
                    legacy_default_font="Helvetica:bold:pixelsize=12:antialias=false",
                    antialiased=antialiased, scope="Logical metrics, tail policy and original 1x glyph raster")
    (artifacts / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    rows, raster, defaults, references = [], [], [], []
    try:
        def layout(text, limit, density=120, png=None):
            args = [str(probe), str(density), str(limit), text]
            if png or antialiased: args.extend([str(png) if png else "", "1" if antialiased else "0"])
            result = json.loads(subprocess.check_output(args))
            result["text"] = base64.b64decode(result.pop("text_base64")).decode("utf-8")
            return result

        for title in TITLES:
            default = reference.get(metadata["legacy_default_font"], title)
            defaults.append(dict(title=title, legacy_metrics=default["metrics"],
                                 current=layout(title, 10000)))
            if not antialiased:
                assert defaults[-1]["current"]["width"] == defaults[-1]["legacy_metrics"][1], defaults[-1]
            for limit in LIMITS:
                original = reference.get(metadata["reference_font"], title, limit)
                old = original["text"]
                height, full_width, old_width = original["metrics"]
                full = layout(title, 10000)
                assert (full["width"], full["height"]) == (full_width, height), (title, full, full_width, height)
                first = layout(title, limit)
                if first["text"] != old:
                    # Original byte binary search can leave one character unused.
                    # Accept only a longer fitting tail with the same prefix.
                    assert "..." in first["text"] and "..." in old, (title, limit, first, old)
                    prefix, tail = first["text"].split("...", 1)
                    old_prefix, old_tail = old.split("...", 1)
                    assert prefix == old_prefix and tail.endswith(old_tail) and len(tail) > len(old_tail), (title, limit, first, old)
                    assert first["width"] <= limit, (title, limit, first)
                for density in (120, 150, 180, 210, 240):
                    actual = layout(title, limit, density)
                    assert actual == first, (title, limit, density, actual, first)
                    rows.append(dict(title=title, limit=limit, density=density, current=actual,
                                     legacy_text=old, legacy_width=old_width))
            current_png = artifacts / f"current-{len(references)}.png"
            original = reference.image(reference.get(metadata["reference_font"], title))
            original.save(artifacts / f"reference-{len(references)}.png")
            layout(title, 10000, png=current_png)
            with Image.open(current_png) as actual:
                exact = original.tobytes() == actual.convert("RGB").tobytes()
            references.append(dict(title=title, exact=exact))
            assert exact, (title, "original Xft glyph pixels differ", antialiased)

        # Explicit Unicode clusters: shortening must not split a combining mark,
        # a flag pair or an emoji ZWJ sequence. The Xft byte truncator is not the
        # oracle for these cases.
        for cluster in ("e\u0301", "語", "👩\u200d💻", "🇯🇵"):
            title = cluster * 20
            for limit in (0, 20, 40, 80, 120):
                first = layout(title, limit)
                assert first["text"] == title or re.fullmatch(r"\.\.\.(?:" + re.escape(cluster) + ")*", first["text"]), first
                assert first["width"] <= limit or first["text"] == "...", first
                for density in (120, 150, 180, 210, 240):
                    actual = layout(title, limit, density)
                    assert actual == first, (title, density, actual, first)
                    rows.append(dict(title=title, limit=limit, density=density, current=actual))

        base_ink_width = None
        for density in (120, 150, 180, 210, 240):
            png = artifacts / f"ink-{density}.png"
            result = layout("WaylandProbe", 300, density, png)
            with Image.open(png) as image:
                ink = image.convert("RGB").getbbox()
            assert ink is not None
            scale = density / 120
            if base_ink_width is None: base_ink_width = ink[2] - ink[0]
            assert abs((ink[2] - ink[0]) - base_ink_width * scale) <= 2, (density, result, ink)
            assert ink[3] <= math.ceil((result["height"] + 1) * scale), (density, result, ink)
            raster.append(dict(density=density, ink=ink, metrics=result))
        # Malformed application titles must become valid UTF-8 before shaping.
        malformed = subprocess.check_output([str(probe).encode(), b"120", b"300", b"bad\xfftitle", b"", b"1" if antialiased else b"0"])
        assert "\ufffd" in base64.b64decode(json.loads(malformed)["text_base64"]).decode("utf-8")
        (artifacts / "results.json").write_text(json.dumps(dict(rows=rows, raster=raster,
            legacy_default_diagnostics=defaults, xft_raster=references), indent=2, ensure_ascii=False) + "\n")
        print(f"Title font/layout: {len(rows)} cases, {len(raster)} densities and {len(references)} exact Xft rasters PASS (antialiased={antialiased})")
    finally:
        (artifacts / "partial-results.json").write_text(json.dumps(dict(rows=rows, raster=raster,
            legacy_default_diagnostics=defaults, xft_raster=references), indent=2, ensure_ascii=False) + "\n")



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--antialiased", action="store_true")
    args = parser.parse_args()
    check(args.probe.resolve(), args.artifacts.resolve(), args.antialiased)
