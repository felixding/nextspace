#!/usr/bin/env python3
"""Require normal compositor shutdown while font workers are running."""
import argparse
import json
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import tempfile


def run(compositor, artifacts):
    artifacts.mkdir(parents=True, exist_ok=True)
    results = []
    for attempt in range(3):
        for termination in (signal.SIGTERM, signal.SIGINT):
            name = f"{termination.name}-{attempt}"
            with tempfile.TemporaryDirectory(prefix="nextspace-shutdown-") as runtime:
                env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS="headless",
                           WLR_HEADLESS_OUTPUTS="2", WLR_RENDERER="pixman")
                for key in ("DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET"):
                    env.pop(key, None)
                control, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
                control.settimeout(5)
                with (artifacts / f"{name}.log").open("w") as log:
                    process = subprocess.Popen([compositor, "-c", str(child.fileno())],
                        env=env, pass_fds=[child.fileno()], stdout=subprocess.PIPE, stderr=log, text=True)
                child.close()
                try:
                    assert select.select([process.stdout], [], [], 10)[0], "No compositor socket"
                    assert process.stdout.readline().startswith("WAYLAND_DISPLAY=")
                    control.sendall(b"outputs")
                    assert len(json.loads(control.recv(65536))) == 2
                    tasks = [dict(line.split(":", 1) for line in (task / "status").read_text().splitlines()
                                  if line.startswith(("Name:", "Pid:", "SigBlk:")))
                             for task in Path(f"/proc/{process.pid}/task").iterdir()]
                    process.send_signal(termination)
                    code = process.wait(timeout=5)
                    results.append(dict(signal=termination.name, attempt=attempt, returncode=code, tasks=tasks))
                    (artifacts / "results.json").write_text(json.dumps(results, indent=2) + "\n")
                    assert code == 0, f"{name}: compositor exited with {code}"
                finally:
                    if process.poll() is None:
                        process.kill(); process.wait(timeout=5)
                    process.stdout.close(); control.close()
    print(f"Compositor signal shutdown: {len(results)} checks passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--compositor", required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    arguments = parser.parse_args()
    run(arguments.compositor, arguments.artifacts)
