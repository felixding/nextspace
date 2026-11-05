#!/usr/bin/env python3
"""Check the installed backend against an independent headless compositor."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from gnustep import capture_frame, private_defaults, process_runtime
from integration import read_json_lines, submitted_image_pixels, until


def stop(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def runtime_record(pid):
    record = process_runtime(pid)
    record["hashes"] = {
        name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
        for name in {record["executable"], *record["libraries"]}
    }
    return record


def run(probe, root, weston="weston", wayland_info="wayland-info"):
    root.mkdir(parents=True)
    probe = probe.resolve()
    records = []
    for scale in (1, 2):
        artifacts = root / f"scale-{scale}"
        artifacts.mkdir()
        with tempfile.TemporaryDirectory(prefix="nextspace-weston-") as runtime:
            env = dict(
                os.environ,
                XDG_RUNTIME_DIR=runtime,
                NEXTSPACE_SESSION_ID=Path(runtime).name,
            )
            for name in ("DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET", "LD_PRELOAD"):
                env.pop(name, None)
            private_defaults(env, runtime)
            (artifacts / "GNUstep.conf").write_bytes(
                Path(env["GNUSTEP_CONFIG_FILE"]).read_bytes()
            )
            command = [
                weston,
                "--no-config",
                "--backend=headless",
                "--renderer=pixman",
                "--socket=nextspace-fallback",
                "--width=1920",
                "--height=1440",
                f"--scale={scale}",
                "--idle-time=0",
            ]
            server = client = None
            try:
                with (artifacts / "weston.log").open("w") as log:
                    server = subprocess.Popen(command, env=env, stdout=log, stderr=log)

                def ready(server=server, artifacts=artifacts, runtime=runtime):
                    assert server.poll() is None, (artifacts / "weston.log").read_text()
                    return Path(runtime, "nextspace-fallback").is_socket()

                until(ready, "Weston socket")
                env["WAYLAND_DISPLAY"] = "nextspace-fallback"
                info = subprocess.run(
                    [wayland_info],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                )
                (artifacts / "wayland-info.txt").write_text(info.stdout)
                (artifacts / "wayland-info-errors.txt").write_text(info.stderr)
                assert "nextspace_application_v1" not in info.stdout
                assert "nextspace_shell_v1" not in info.stdout
                assert "zxdg_decoration_manager_v1" not in info.stdout
                env["NEXTSPACE_WAYLAND_CAPTURE_DIR"] = str(artifacts)
                env["WAYLAND_DEBUG"] = "client"
                with (
                    (artifacts / "probe.log").open("w") as log,
                    (artifacts / "probe-errors.log").open("w") as errors,
                ):
                    client = subprocess.Popen(
                        [
                            str(probe),
                            "-GSBackend",
                            "libgnustep-wayland",
                            "-GSTheme",
                            "NextSpace",
                        ],
                        env=env,
                        stdout=log,
                        stderr=errors,
                    )

                def rendered(client=client, artifacts=artifacts, scale=scale):
                    assert client.poll() is None, (
                        artifacts / "probe-errors.log"
                    ).read_text()[-4000:]
                    events = read_json_lines(artifacts / "probe.log", '{"event":')
                    reports = [
                        e
                        for e in events
                        if e["event"] == "scale" and e["scale"] == scale
                    ]
                    if not reports:
                        return None
                    for path in artifacts.glob(f"window-*-{scale * 120}.png"):
                        frame = capture_frame(path, (801 * scale, 601 * scale))
                        if frame:
                            return events, frame

                events, frame = until(
                    rendered,
                    f"{scale * 100}% independent-compositor native buffer",
                    timeout=20,
                )
                reports = [
                    e for e in events if e["event"] == "scale" and e["scale"] == scale
                ]
                assert reports and all(
                    e["width"] == 801 and e["height"] == 601 and e["roundtrip"]
                    for e in reports
                )
                assert any(
                    e["event"] == "readback" and e["scale"] == scale and e["ok"]
                    for e in events
                )
                assert any(
                    e["event"] == "vector-image"
                    and e["scale"] == scale
                    and e["ok"]
                    and e["density_rep"]
                    for e in events
                )
                assert any(
                    e["event"] == "image-subview" and e["scale"] == scale and e["ok"]
                    for e in events
                )
                pattern = next(e for e in events if e["event"] == "pixel-pattern")
                submitted_image_pixels(
                    frame["image"].convert("RGB"), pattern, (801, 601), scale * 120
                )
                trace = (artifacts / "probe-errors.log").read_text()
                assert re.search(r"xdg_toplevel[#@][0-9]+", trace) and re.search(
                    r"wl_surface[#@][0-9]+", trace
                )
                assert "nextspace_application_v1#" not in trace
                assert "nextspace_shell_v1#" not in trace
                assert "get_toplevel_decoration" not in trace
                record = {
                    "scale_percent": scale * 100,
                    "logical_size": [801, 601],
                    "buffer_pixels": list(frame["image"].size),
                    "client": runtime_record(client.pid),
                    "server": runtime_record(server.pid),
                    "probe_sha256": hashlib.sha256(probe.read_bytes()).hexdigest(),
                    "full_client_frame": True,
                    "missing_private_extensions": True,
                    "backing_roundtrip": True,
                    "submitted_pattern_pixels": True,
                    "native_frame": str(frame["path"].relative_to(root)),
                    "commands": command,
                    "globals": info.stdout,
                }
                (artifacts / "runtime.json").write_text(
                    json.dumps(record, indent=2) + "\n"
                )
                records.append(record)
            finally:
                stop(client)
                stop(server)

    (root / "result.json").write_text(
        json.dumps(
            {
                "passed": True,
                "cases": records,
                "input_workflows_qualified": False,
                "fractional_density_qualified": False,
                "foreign_desktop_shell_qualified": False,
                "physical_gpu_qualified": False,
                "full_plan_complete": False,
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps({"passed": True, "cases": len(records)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--weston", default="weston")
    parser.add_argument("--wayland-info", default="wayland-info")
    args = parser.parse_args()
    run(args.probe, args.artifacts.resolve(), args.weston, args.wayland_info)
