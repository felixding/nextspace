#!/usr/bin/env python3
"""Record the source inputs used by a Wayland validation run."""
import hashlib
import json
from pathlib import Path
import sys

repo, destination = map(Path, sys.argv[1:])
roots = ("Applications/Artwork", "Applications/Compositor", "Applications/Session", "Applications/Terminal", "Applications/TextEdit", "Applications/Review", "Applications/TimeMon", "Applications/Preferences", "Applications/OpenUp", "Applications/Login", "Applications/Workspace",
         "Frameworks/SystemKit", "Frameworks/DesktopKit", "Frameworks/SoundKit", "Libraries/gnustep",
         "Libraries/libcorefoundation", "Protocols", "Packaging/Sources", "Tests/GNUstep-GUI", "Tests/Wayland",
         "OS/Linux/usr/NextSpace/bin", "OS/Linux/usr/share/icons/NextSpace")
excluded = {".git", "obj", "generated", ".wayland-generated", "__pycache__", "autom4te.cache"}
hashes = {}
for root in roots:
    for path in sorted((repo / root).rglob("*")):
        relative = path.relative_to(repo)
        if path.is_file() and not excluded.intersection(relative.parts):
            hashes[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
destination.write_text(json.dumps(hashes, indent=2, sort_keys=True) + "\n")
