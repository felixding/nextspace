#!/usr/bin/env python3
"""Compare native font selection/substitution with the original Xft path."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess

from PIL import Image

PROFILES = (
    "Helvetica:bold:pixelsize=12",
    "Helvetica:bold:pixelsize=12:antialias=false",
    "Helvetica:bold:pixelsize=12:antialias=true",
    "DejaVu Sans:postscriptname=DejaVuSans-Bold:pixelsize=14:antialias=false:embeddedbitmap=true",
    "Helvetica:bold:size=12:dpi=96",
    "Helvetica:bold:pixelsize=12:hinting=false:hintstyle=0",
    "Helvetica:bold:pixelsize=12:autohint=true:hintstyle=3",
    "Helvetica:bold:pixelsize=12:embeddedbitmap=false",
    "DejaVu Sans:file=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:pixelsize=12",
)


def check(probe, artifacts):
    artifacts.mkdir(parents=True)
    repo = Path(__file__).resolve().parents[2]
    reference = artifacts / "xft-font-probe"
    flags = subprocess.check_output(["pkg-config", "--cflags", "--libs", "xft", "x11", "fontconfig"], text=True).split()
    subprocess.run(["cc", "-std=c11", str(repo / "Tests/Wayland/xft-font-probe.c"), "-o", str(reference), *flags], check=True)
    config_source = Path("/etc/fonts/fonts.conf")
    metadata = dict(probe=str(probe), probe_sha256=hashlib.sha256(probe.read_bytes()).hexdigest(),
                    system_fontconfig=str(config_source), system_fontconfig_sha256=hashlib.sha256(config_source.read_bytes()).hexdigest())
    (artifacts / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    read, write = os.pipe()
    with (artifacts / "xvfb.log").open("w") as log:
        server = subprocess.Popen(["Xvfb", "-displayfd", str(write), "-screen", "0", "1600x1200x24",
                                   "-nolisten", "tcp"], pass_fds=[write], stdout=log, stderr=log)
    os.close(write)
    rows = []
    try:
        assert select.select([read], [], [], 10)[0], "No Xft reference display"
        env = dict(os.environ, DISPLAY=":" + os.read(read, 64).decode().strip())
        os.close(read)
        read = None
        for mode in ("default", "force-off", "force-on", "no-hint"):
            directory = artifacts / mode
            directory.mkdir()
            edit = "" if mode == "default" else (
                '<match target="pattern"><edit name="antialias" mode="assign"><bool>' +
                ("true" if mode == "force-on" else "false") + '</bool></edit></match>')
            if mode == "no-hint":
                edit = ('<match target="pattern"><edit name="hinting" mode="assign"><bool>false</bool></edit>'
                        '<edit name="hintstyle" mode="assign"><const>hintnone</const></edit></match>')
            config = directory / "fonts.conf"
            config.write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig>' +
                              '<include>/etc/fonts/fonts.conf</include>' + edit + '</fontconfig>\n')
            scenario_env = dict(env, FONTCONFIG_FILE=str(config))
            for profile, pattern in enumerate(PROFILES):
                for fallback in (False, True):
                    for text in ("WaylandProbe", "AVATAR-ToWA"):
                        stem = f"{profile}-{int(fallback)}-{text}"
                        expected_png = directory / (stem + "-xft.ppm")
                        expected = json.loads(subprocess.check_output([str(reference), pattern, str(int(fallback)), text,
                                                                      str(expected_png)], env=scenario_env))
                        with Image.open(expected_png) as image:
                            expected_image = image.convert("RGB")
                        logical = None
                        for density in (120, 150, 180, 210, 240):
                            actual_png = directory / f"{stem}-{density}.png"
                            actual = json.loads(subprocess.check_output([str(probe), pattern, str(int(fallback)), str(density),
                                                                        text, str(actual_png)], env=scenario_env))
                            actual["font"] = base64.b64decode(actual.pop("font_base64")).decode()
                            row = dict(mode=mode, profile=profile, pattern=pattern, fallback=fallback,
                                       text=text, density=density, expected=expected, actual=actual)
                            (artifacts / "current-case.json").write_text(json.dumps(row, indent=2) + "\n")
                            assert all(actual[key] == expected[key] for key in ("antialiased", "width", "height")), row
                            if logical is None: logical = actual
                            assert actual == logical, row
                            if density == 120:
                                with Image.open(actual_png) as image:
                                    assert image.convert("RGB").tobytes() == expected_image.tobytes(), row
                            rows.append(row)
        fallback = []
        for density in (120, 150, 180, 210, 240):
            image = artifacts / f"fallback-{density}.png"
            actual = json.loads(subprocess.check_output([str(probe), PROFILES[0], "0", str(density), "A語", str(image)], env=env))
            assert actual["unknown_glyphs"] == 0, actual
            fallback.append(dict(density=density, actual=actual))
        (artifacts / "fallback-results.json").write_text(json.dumps(fallback, indent=2) + "\n")
        (artifacts / "results.json").write_text(json.dumps(rows, indent=2) + "\n")
        print(f"Fontconfig substitutions and legacy AA fallback: {len(rows)} native/Xft density cases PASS")
    finally:
        (artifacts / "partial-results.json").write_text(json.dumps(rows, indent=2) + "\n")
        if read is not None: os.close(read)
        server.terminate()
        try: server.wait(timeout=5)
        except subprocess.TimeoutExpired: server.kill(); server.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    check(args.probe.resolve(), args.artifacts.resolve())
