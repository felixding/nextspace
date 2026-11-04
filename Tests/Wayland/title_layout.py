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
import os
from pathlib import Path
import re
import select
import subprocess

from PIL import Image


def reference_source(repo):
    paths = (repo / "Applications/Workspace/WM/misc.c",
             repo / "Applications/Workspace/WM/core/wfont.c")
    misc, font = (path.read_text() for path in paths)
    notices = "\n".join(text[:text.index("*/") + 2] for text in (misc, font))
    headers = r'''
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/Xft/Xft.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "wfont.h"
#define wmalloc malloc
#define wassertrv(c,r) do { if (!(c)) return (r); } while (0)
'''
    metrics = font[font.index("int WMWidthOfString("):font.index("\nvoid WMDrawString")]
    shorten = misc[misc.index("char *ShrinkString("):misc.index("\nstatic void timeoutHandler")]
    main = r'''
int main(int argc, char **argv) {
  if (argc != 4 && argc != 5) return 2;
  Display *display = XOpenDisplay(NULL); if (!display) return 3;
  WMScreen screen = {.display = display, .screen = DefaultScreen(display)};
  WMFont font = {.screen = &screen};
  font.font = XftFontOpenName(display, screen.screen, argv[3]);
  if (!font.font) return 4;
  char *result = ShrinkString(&font, argv[2], atoi(argv[1]));
  fprintf(stderr, "%d %d %d\n", font.font->ascent + font.font->descent,
    WMWidthOfString(&font, argv[2], strlen(argv[2])),
    WMWidthOfString(&font, result, strlen(result)));
  fwrite(result, 1, strlen(result), stdout);
  if (argc == 5) {
    int number = screen.screen, width = 1602, height = 46;
    Pixmap pixmap = XCreatePixmap(display, RootWindow(display, number), width, height, DefaultDepth(display, number));
    GC gc = XCreateGC(display, pixmap, 0, NULL);
    XSetForeground(display, gc, BlackPixel(display, number));
    XFillRectangle(display, pixmap, gc, 0, 0, width, height);
    XftDraw *draw = XftDrawCreate(display, pixmap, DefaultVisual(display, number), DefaultColormap(display, number));
    XftColor white;
    if (!XftColorAllocName(display, DefaultVisual(display, number), DefaultColormap(display, number), "white", &white)) return 5;
    XftDrawStringUtf8(draw, &white, font.font, 1, 1 + font.font->ascent, (const FcChar8 *)result, strlen(result));
    XImage *image = XGetImage(display, pixmap, 0, 0, width, height, AllPlanes, ZPixmap);
    FILE *file = fopen(argv[4], "wb"); if (!file) return 6;
    fprintf(file, "P6\n%d %d\n255\n", width, height);
    for (int y = 0; y < height; y++) for (int x = 0; x < width; x++) {
      unsigned long pixel = XGetPixel(image, x, y);
      unsigned char rgb[] = {pixel >> 16, pixel >> 8, pixel};
      fwrite(rgb, 1, 3, file);
    }
    fclose(file); XDestroyImage(image);
    XftColorFree(display, DefaultVisual(display, number), DefaultColormap(display, number), &white);
    XftDrawDestroy(draw); XFreeGC(display, gc); XFreePixmap(display, pixmap);
  }
  free(result);
  XftFontClose(display, font.font); XCloseDisplay(display); return 0;
}
'''
    return notices + headers + metrics + shorten + main, {
        str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def check(probe, artifacts, antialiased):
    repo = Path(__file__).resolve().parents[2]
    artifacts.mkdir(parents=True, exist_ok=True)
    source, inputs = reference_source(repo)
    reference_c = artifacts / "legacy-reference.c"
    reference_c.write_text(source)
    reference = artifacts / "legacy-reference"
    flags = subprocess.check_output(["pkg-config", "--cflags", "--libs", "xft", "x11"], text=True).split()
    subprocess.run(["cc", "-std=c11", "-I" + str(repo / "Applications/Workspace/WM/core"),
                    str(reference_c), "-o", str(reference), *flags], check=True)
    metadata = dict(reference_inputs=inputs, probe_sha256=hashlib.sha256(probe.read_bytes()).hexdigest(),
                    reference_font="Helvetica:bold:pixelsize=12:antialias=" + ("true" if antialiased else "false"),
                    legacy_default_font="Helvetica:bold:pixelsize=12:antialias=false",
                    antialiased=antialiased, scope="Logical metrics, tail policy and 1x glyph raster; full frame/preferences parity remains open")
    (artifacts / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    read, write = os.pipe()
    with (artifacts / "xvfb.log").open("w") as log:
        server = subprocess.Popen(["Xvfb", "-displayfd", str(write), "-screen", "0", "800x600x24",
                                   "-nolisten", "tcp"], pass_fds=[write], stdout=log, stderr=log)
    os.close(write)
    rows, raster, defaults, references = [], [], [], []
    try:
        assert select.select([read], [], [], 10)[0], "No reference X display"
        env = dict(os.environ, DISPLAY=":" + os.read(read, 64).decode().strip())
        os.close(read)
        read = None

        def layout(text, limit, density=120, png=None):
            args = [str(probe), str(density), str(limit), text]
            if png or antialiased: args.extend([str(png) if png else "", "1" if antialiased else "0"])
            result = json.loads(subprocess.check_output(args))
            result["text"] = base64.b64decode(result.pop("text_base64")).decode("utf-8")
            return result

        titles = ("WaylandProbe", "AVATAR-ToWA", "file-abcdefghij-long-name.extension",
                  "AppName: document-with-a-long-extension.txt",
                  "Application: /tmp/project/important-file.txt", "A:X", "A thing", "", "X")
        for title in titles:
            default = subprocess.run([str(reference), "10000", title, metadata["legacy_default_font"]],
                                     env=env, capture_output=True, check=True)
            defaults.append(dict(title=title, legacy_metrics=list(map(int, default.stderr.split())),
                                 current=layout(title, 10000)))
            if not antialiased:
                assert defaults[-1]["current"]["width"] == defaults[-1]["legacy_metrics"][1], defaults[-1]
            for limit in (0, 5, 20, 40, 80, 120, 200, 400):
                original = subprocess.run([str(reference), str(limit), title, metadata["reference_font"]],
                                          env=env, capture_output=True, check=True)
                old = original.stdout.decode()
                height, full_width, old_width = map(int, original.stderr.split())
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
            original_png = artifacts / f"reference-{len(references)}.ppm"
            current_png = artifacts / f"current-{len(references)}.png"
            subprocess.run([str(reference), "10000", title, metadata["reference_font"], str(original_png)],
                           env=env, capture_output=True, check=True)
            layout(title, 10000, png=current_png)
            with Image.open(original_png) as original, Image.open(current_png) as actual:
                exact = original.convert("RGB").tobytes() == actual.convert("RGB").tobytes()
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
        malformed = subprocess.check_output([os.fsencode(probe), b"120", b"300", b"bad\xfftitle", b"", b"1" if antialiased else b"0"])
        assert "\ufffd" in base64.b64decode(json.loads(malformed)["text_base64"]).decode("utf-8")
        (artifacts / "results.json").write_text(json.dumps(dict(rows=rows, raster=raster,
            legacy_default_diagnostics=defaults, xft_raster=references), indent=2, ensure_ascii=False) + "\n")
        print(f"Title font/layout: {len(rows)} cases, {len(raster)} densities and {len(references)} exact Xft rasters PASS (antialiased={antialiased})")
    finally:
        (artifacts / "partial-results.json").write_text(json.dumps(dict(rows=rows, raster=raster,
            legacy_default_diagnostics=defaults, xft_raster=references), indent=2, ensure_ascii=False) + "\n")
        if read is not None: os.close(read)
        server.terminate()
        try: server.wait(timeout=5)
        except subprocess.TimeoutExpired: server.kill(); server.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--antialiased", action="store_true")
    args = parser.parse_args()
    check(args.probe.resolve(), args.artifacts.resolve(), args.antialiased)
