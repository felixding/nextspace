"""Read original Window Maker title references without an X server."""
import hashlib
import json
from pathlib import Path
import subprocess

from PIL import Image

TITLES = ("WaylandProbe", "AVATAR-ToWA", "file-abcdefghij-long-name.extension",
          "AppName: document-with-a-long-extension.txt",
          "Application: /tmp/project/important-file.txt", "A:X", "A thing", "", "X")
LIMITS = (0, 5, 20, 40, 80, 120, 200, 400)
PROFILES = (
    ("Helvetica:bold:pixelsize=12", False),
    ("Helvetica:bold:pixelsize=12", True),
    ("DejaVu Sans:postscriptname=DejaVuSans-Bold:pixelsize=14:antialias=false:embeddedbitmap=true", True),
    ("DejaVu Sans:postscriptname=DejaVuSans-Bold:pixelsize=15:antialias=true:embeddedbitmap=false", False),
    ("DejaVu Sans Mono:bold:pixelsize=14:antialias=true", False),
    ("Helvetica:bold:size=12:dpi=96:antialias=false", False),
    ("Helvetica:bold:pixelsize=12:hinting=false:hintstyle=0", False),
    ("Helvetica:bold:pixelsize=12:autohint=true:hintstyle=3", True),
    ("DejaVu Sans:file=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:pixelsize=12", False),
)


def effective_pattern(pattern, antialiased):
    effective = ":antialias=true" in pattern or (":antialias=" not in pattern and antialiased)
    return pattern if ":antialias=" in pattern else pattern + (":antialias=true" if effective else ":antialias=false")


def key(pattern, text, limit):
    return json.dumps([pattern, text, limit], ensure_ascii=False, separators=(",", ":"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def font_signature(pattern):
    fields = ("file", "index", "antialias", "hinting", "hintstyle", "autohint",
              "embeddedbitmap", "rgba", "lcdfilter")
    values = subprocess.check_output(["fc-match", "-f",
        "".join("%{" + field + "}\\n" for field in fields), pattern], text=True).splitlines()
    assert len(values) == len(fields), (pattern, values)
    return {"font_sha256": sha(Path(values[0])), "options": dict(zip(fields[1:], values[1:]))}


class Reference:
    def __init__(self, repo):
        self.directory = repo / "Tests/Wayland/fixtures/title-reference"
        manifest = self.directory / "manifest.json"
        self.data = json.loads(manifest.read_text())
        assert self.data["format"] == 1
        for name, digest in self.data["sources"].items():
            assert sha(repo / name) == digest, ("Original title source changed", name)
        for name, digest in self.data["files"].items():
            relative = Path(name)
            assert not relative.is_absolute() and ".." not in relative.parts
            assert sha(self.directory / relative) == digest, ("Title reference changed", name)
        self.checked_fonts = set()
        self.metadata = {"reference_inputs": self.data["sources"],
                         "reference_manifest_sha256": sha(manifest),
                         "reference_manifest": str(manifest.relative_to(repo))}

    def get(self, pattern, text, limit=10000):
        if pattern not in self.checked_fonts:
            actual = font_signature(pattern)
            expected = self.data["fonts"][pattern]
            assert actual == expected, ("Reference font/substitution changed", pattern, actual, expected)
            self.checked_fonts.add(pattern)
        return self.data["records"][key(pattern, text, limit)]

    def image(self, record):
        with Image.open(self.directory / record["image"]) as image:
            return image.convert("RGB")
