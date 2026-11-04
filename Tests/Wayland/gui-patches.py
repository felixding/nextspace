#!/usr/bin/env python3
"""Check clean application, repeat application and false cache-marker rejection."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile


def run(repo, archive):
    helper = repo / "Libraries/gnustep/patches/apply-gui-patches.sh"
    first_patch = repo / "Libraries/gnustep/libs-gui_NSApplication.patch"
    with tempfile.TemporaryDirectory(prefix="nextspace-patches-") as temporary:
        root = Path(temporary)
        subprocess.run(["tar", "xzf", str(archive), "--strip-components=1", "-C", str(root)], check=True)
        original = (root / "Source/NSApplication.m").read_bytes()
        marker = root / ".nextspace-patches" / (first_patch.name + ".sha256")
        marker.parent.mkdir()
        marker.write_text(hashlib.sha256(first_patch.read_bytes()).hexdigest() + "\n")
        result = subprocess.run(["sh", str(helper), str(root), "1"], capture_output=True)
        assert result.returncode != 0, "A marker must not bless unpatched sources"
        assert (root / "Source/NSApplication.m").read_bytes() == original
        marker.unlink()
        subprocess.run(["sh", str(helper), str(root), "1"], check=True, capture_output=True)
        header = root / "Headers/Additions/GNUstepGUI/GSPasteboardServer.h"
        assert "GSPasteboardDidChangeNotification" in header.read_text()
        before = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in root.rglob("*") if p.is_file()}
        subprocess.run(["sh", str(helper), str(root), "1"], check=True, capture_output=True)
        after = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in root.rglob("*") if p.is_file()}
        assert before == after, "Applying the same GUI series twice must preserve all sources"
    print("GUI clean patches, idempotence and invalid-marker rejection: PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", type=Path)
    parser.add_argument("archive", type=Path)
    arguments = parser.parse_args()
    run(arguments.repo, arguments.archive)
