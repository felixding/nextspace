#!/usr/bin/env python3
"""Capture original title metrics and pixels; optional X11 reference tooling only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import tempfile

from PIL import Image
from title_reference import TITLES, LIMITS, PROFILES, effective_pattern, font_signature, key, sha

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


def generate(repo, output):
    output.mkdir(parents=True, exist_ok=False)
    source, inputs = reference_source(repo)
    reference_c = output / "legacy-reference.c"
    reference_c.write_text(source)
    records, fonts, files = {}, {}, {}
    with tempfile.TemporaryDirectory(prefix="nextspace-original-titles-") as temporary:
        work = Path(temporary)
        reference = work / "reference"
        flags = subprocess.check_output(["pkg-config", "--cflags", "--libs", "xft", "x11"], text=True).split()
        subprocess.run(["cc", "-std=c11", "-I" + str(repo / "Applications/Workspace/WM/core"),
                        str(reference_c), "-o", str(reference), *flags], check=True)
        read, write = os.pipe()
        with (work / "xvfb.log").open("w") as log:
            server = subprocess.Popen(["Xvfb", "-displayfd", str(write), "-screen", "0", "1600x1200x24",
                                       "-nolisten", "tcp"], pass_fds=[write], stdout=log, stderr=log)
        os.close(write)
        try:
            assert select.select([read], [], [], 10)[0], "Original Xft reference display not ready"
            env = dict(os.environ, DISPLAY=":" + os.read(read, 64).decode().strip())
            cases = [(f"Helvetica:bold:pixelsize=12:antialias={aa}", text, limit)
                     for aa in ("false", "true") for text in TITLES for limit in (*LIMITS, 10000)]
            cases += [(effective_pattern(pattern, aa), "WaylandProbe", 10000) for pattern, aa in PROFILES]
            for pattern, text, limit in cases:
                identity = key(pattern, text, limit)
                if identity in records:
                    continue
                fonts.setdefault(pattern, font_signature(pattern))
                ppm = work / "original.ppm"
                command = [str(reference), str(limit), text, pattern]
                if limit == 10000:
                    command.append(str(ppm))
                result = subprocess.run(command, env=env, capture_output=True, check=True)
                row = {"text": result.stdout.decode(), "metrics": list(map(int, result.stderr.split()))}
                assert len(row["metrics"]) == 3
                if limit == 10000:
                    filename = "glyph-" + hashlib.sha256(identity.encode()).hexdigest()[:16] + ".png"
                    with Image.open(ppm) as image:
                        image.save(output / filename)
                    row["image"] = filename
                    files[filename] = sha(output / filename)
                records[identity] = row
        finally:
            os.close(read)
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
    files[reference_c.name] = sha(reference_c)
    versions = {name: subprocess.check_output(["pkg-config", "--modversion", name], text=True).strip()
                for name in ("xft", "fontconfig", "freetype2")}
    data = {"format": 1, "sources": inputs, "files": files, "fonts": fonts, "records": records,
            "generation": {"libraries": versions, "xvfb_sha256": sha(Path(shutil.which("Xvfb"))),
                "description": "Unmodified original Window Maker width/shortening code and Xft rendering; no native compositor output is used."}}
    (output / "manifest.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"records": len(records), "rasters": len(files) - 1, "fonts": len(fonts)}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.repo.resolve(), args.output.resolve())
