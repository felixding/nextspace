#!/usr/bin/env python3
"""Check pinned Base patch application, idempotence and cache rejection."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

repo, archive = map(Path, sys.argv[1:])
package = json.loads((repo / "Tests/Wayland/native-stack-sources.json").read_text())["base"]
assert hashlib.sha256(archive.read_bytes()).hexdigest() == package["sha256"]
helper = repo.resolve() / "Libraries/gnustep/patches/apply-base-patches.sh"
with tempfile.TemporaryDirectory(prefix="nextspace-base-patches-") as directory:
    root = Path(directory)
    names=('NSDistributedNotificationCenter.m','NSMessagePortNameServer.m','NSRunLoop.m')
    with tarfile.open(archive) as files:
        for name in names:
            source=root/'Source'/name;source.parent.mkdir(exist_ok=True)
            member,=[m for m in files.getmembers() if m.name.endswith('/Source/'+name)]
            source.write_bytes(files.extractfile(member).read())

    def run(success, mode="apply"):
        result = subprocess.run(["sh", str(helper), str(root), mode], capture_output=True, text=True)
        assert (result.returncode == 0) == success, result.stdout + result.stderr

    run(False, "check")
    run(True)
    patched = {name:(root/"Source"/name).read_bytes() for name in names}
    run(True)
    run(True, "check")
    assert {name:(root/"Source"/name).read_bytes() for name in names} == patched
    for name in ('base-notification-connect','base-message-port-lock','base-run-loop-invalid-timers'):
        marker=root/'.nextspace-patches'/(name+'.sha256')
        correct=marker.read_bytes();marker.write_text('stale\n');run(False);marker.write_bytes(correct)
    source.write_text("invalid cached Base source\n")
    run(False,"check")
print("Base patch application, idempotence and stale/invalid cache rejection: PASS")
