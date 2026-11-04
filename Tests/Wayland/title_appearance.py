#!/usr/bin/env python3
"""Qualify trusted title preferences against original Xft glyph pixels."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import tempfile
import uuid

from PIL import Image
from integration import until
from shell import Shell
from title_layout import reference_source

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
JUSTIFICATIONS = ("center", "left", "right")


def check_legacy(compositor, shell_probe, artifacts):
    artifacts.mkdir(parents=True)
    rows = []
    with tempfile.TemporaryDirectory(prefix="nextspace-old-title-shell-") as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS="headless",
                   WLR_HEADLESS_OUTPUTS="1", WLR_RENDERER="pixman")
        for key in ("DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET"):
            env.pop(key, None)
        control, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        broker, broker_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        control.settimeout(5)
        with (artifacts / "compositor.log").open("w") as log:
            server = subprocess.Popen([compositor, "-c", str(child.fileno()), "-S", str(broker_child.fileno())],
                env=env, pass_fds=[child.fileno(), broker_child.fileno()], stdout=subprocess.PIPE, stderr=log, text=True)
        child.close()
        broker_child.close()
        owners = []
        try:
            assert select.select([server.stdout], [], [], 10)[0]
            line = server.stdout.readline().strip()
            assert line.startswith("WAYLAND_DISPLAY="), line
            env["WAYLAND_DISPLAY"] = line.split("=", 1)[1]
            for mode in range(4):
                owner = Shell(shell_probe, broker, env, artifacts, mode, workspace_mode=mode)
                owners.append(owner)
                owner.send(json.dumps(dict(action="title-appearance", settings=dict(
                    font=PROFILES[0][0], antialiased=False, justification="center"))))
                result = owner.wait(lambda: next((e for e in owner.events if e["event"] == "title-appearance"), None),
                                    "older-compositor appearance fallback")
                assert not result["queued"] and result["synchronized"], result
                control.sendall(b"decoration-settings")
                state = json.loads(control.recv(65536))
                assert "title_appearance" not in state, "Expected the frozen older compositor"
                assert server.poll() is None
                rows.append(dict(mode=mode, result=result, prior_settings=state))
                owner.stop()
        finally:
            for owner in owners:
                if owner.process.poll() is None: owner.stop()
            if server.poll() is None: server.terminate()
            try: server.wait(timeout=5)
            except subprocess.TimeoutExpired: server.kill(); server.wait(timeout=5)
            control.close()
            broker.close()
    (artifacts / "results.json").write_text(json.dumps(dict(rows=rows,
        compositor=str(Path(compositor).resolve()), compositor_sha256=hashlib.sha256(Path(compositor).read_bytes()).hexdigest(),
        client_sha256=hashlib.sha256(Path(shell_probe).read_bytes()).hexdigest()), indent=2) + "\n")
    print(f"Older compositor title-appearance fallback: {len(rows)} run-loop modes PASS")


def run(compositor, shell_probe, workspace_shell_probe, gui_probe, artifacts):
    artifacts.mkdir(parents=True)
    frames = artifacts / "frames"
    frames.mkdir()
    repo = Path(__file__).resolve().parents[2]
    source, inputs = reference_source(repo)
    (artifacts / "legacy-reference.c").write_text(source)
    flags = subprocess.check_output(["pkg-config", "--cflags", "--libs", "xft", "x11"], text=True).split()
    reference = artifacts / "legacy-reference"
    subprocess.run(["cc", "-std=c11", "-I" + str(repo / "Applications/Workspace/WM/core"),
                    str(artifacts / "legacy-reference.c"), "-o", str(reference), *flags], check=True)
    (artifacts / "reference-inputs.json").write_text(json.dumps(inputs, indent=2) + "\n")
    rows, checks, owners, processes = [], [], [], []
    stopped = False
    client = None
    with tempfile.TemporaryDirectory(prefix="nextspace-title-appearance-") as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS="headless",
                   WLR_HEADLESS_OUTPUTS="2", WLR_RENDERER="pixman",
                   NEXTSPACE_COMPOSITOR_CAPTURE_DIR=str(frames.resolve()))
        for key in ("DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET"):
            env.pop(key, None)
        control, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        broker, broker_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        control.settimeout(5)
        with (artifacts / "compositor.log").open("w") as log:
            server = subprocess.Popen([compositor, "-c", str(child.fileno()), "-S", str(broker_child.fileno())],
                env=env, pass_fds=[child.fileno(), broker_child.fileno()], stdout=subprocess.PIPE, stderr=log, text=True)
        processes.append(server)
        child.close()
        broker_child.close()
        read, write = os.pipe()
        with (artifacts / "xvfb.log").open("w") as log:
            xserver = subprocess.Popen(["Xvfb", "-displayfd", str(write), "-screen", "0", "1600x1200x24",
                                       "-nolisten", "tcp"], pass_fds=[write], stdout=log, stderr=log)
        processes.append(xserver)
        os.close(write)

        def command(value):
            assert server.poll() is None, "Compositor exited"
            control.sendall(value.encode())
            return json.loads(control.recv(65536))

        def appearance():
            return command("decoration-settings")["title_appearance"]

        def connect(workspace_mode=None, version=16):
            owner = Shell(workspace_shell_probe if workspace_mode is not None else shell_probe,
                          broker, env, artifacts, len(owners), version, workspace_mode)
            owners.append(owner)
            return owner

        def send(owner, pattern, antialiased, justification):
            if owner.workspace:
                before = len(owner.events)
                owner.send(json.dumps(dict(action="title-appearance", settings=dict(
                    font=pattern, antialiased=antialiased, justification=JUSTIFICATIONS[justification]))))
                result = owner.wait(lambda: next((e for e in owner.events[before:] if e["event"] == "title-appearance"), None),
                                    "Workspace title-appearance reply")
                assert result["queued"] and result["synchronized"], result
            else:
                owner.send(f"title-appearance {int(antialiased)} {justification} {pattern}")
                owner.snapshot()

        def window():
            assert client.poll() is None, "AppKit client exited"
            return next((w for w in command("windows") if w["pid"] == client.pid and w["style"] == 15), None)

        def pause_client():
            nonlocal stopped
            os.kill(client.pid, signal.SIGSTOP)
            until(lambda: "State:\tT" in Path(f"/proc/{client.pid}/status").read_text(), "client actually stopped")
            stopped = True

        try:
            assert select.select([server.stdout], [], [], 10)[0]
            line = server.stdout.readline().strip()
            assert line.startswith("WAYLAND_DISPLAY="), line
            env["WAYLAND_DISPLAY"] = line.split("=", 1)[1]
            assert select.select([read], [], [], 10)[0]
            reference_env = dict(env, DISPLAY=":" + os.read(read, 64).decode().strip())
            os.close(read)
            read = None
            references = []
            for index, (pattern, antialiased) in enumerate(PROFILES):
                effective = ":antialias=true" in pattern or (":antialias=" not in pattern and antialiased)
                font = pattern if ":antialias=" in pattern else pattern + (":antialias=true" if effective else ":antialias=false")
                path = artifacts / f"xft-{index}.ppm"
                result = subprocess.run([str(reference), "10000", "WaylandProbe", font, str(path)],
                                        env=reference_env, capture_output=True, check=True)
                height, width, _ = map(int, result.stderr.split())
                with Image.open(path) as image:
                    bounds = image.getbbox()
                    glyphs = image.crop(bounds).copy()
                references.append(dict(effective=effective, height=height, width=width,
                                       bounds=bounds, glyphs=glyphs))
            (artifacts / "reference-metrics.json").write_text(json.dumps([
                {key: value for key, value in row.items() if key != "glyphs"} for row in references], indent=2) + "\n")
            target = command("outputs")[0]["name"]
            assert command(f"output-position {target} -1600 -200")["ok"]
            with (artifacts / "probe.log").open("w") as log, (artifacts / "probe.stderr").open("w") as errors:
                client = subprocess.Popen([gui_probe, "-GSBackend", "libgnustep-wayland", "-GSTheme", "NextSpace",
                    "-GSWaylandServerDecorations", "YES"],
                    env=dict(env, NEXTSPACE_SESSION_ID="test-" + str(uuid.uuid4())), stdout=log, stderr=errors)
            processes.append(client)
            current = until(window, "native decorated title document")
            libraries = sorted({line.split()[-1] for line in Path(f"/proc/{client.pid}/maps").read_text().splitlines()
                if any(name in line for name in ("libgnustep-base.so.", "libgnustep-gui.so.", "libgnustep-wayland-"))})
            (artifacts / "runtime.json").write_text(json.dumps(libraries, indent=2) + "\n")
            owner = connect()

            def capture(profile, justification, density, label):
                reference_value = references[profile]
                state = appearance()
                (artifacts / "current-case.json").write_text(json.dumps(dict(profile=profile,
                    justification=justification, density=density, label=label, state=state), indent=2) + "\n")
                assert state["antialiased"] == reference_value["effective"] and state["justification"] == justification, state
                edge = lambda n: (n * density + 60) // 120
                path = frames / f"frame-{current['id']}-{density}.png"
                def read_title():
                    try:
                        with Image.open(path) as image:
                            if image.size != (edge(801), edge(23)): return None
                            return image.convert("RGB").crop((edge(23), edge(2), edge(778), edge(21)))
                    except OSError:
                        return None
                title = until(read_title, "compositor title capture")
                name = f"{label}-{density}-{profile}-{justification}.png"
                title.save(artifacts / name)
                bounds = title.getbbox()
                assert bounds, (profile, justification, density)
                glyphs = title.crop(bounds)
                if density == 120:
                    assert glyphs.size == reference_value["glyphs"].size and glyphs.tobytes() == reference_value["glyphs"].tobytes(), (
                        profile, "actual frame differs from original Xft glyphs", bounds, reference_value["bounds"])
                reference_width = reference_value["bounds"][2] - reference_value["bounds"][0]
                assert abs(glyphs.width - reference_width * density / 120) <= 2, (profile, density, glyphs.size, reference_width)
                center = (bounds[0] + bounds[2]) / 2
                if justification == 0: assert abs(center - title.width / 2) < edge(4), (state, bounds)
                elif justification == 1: assert bounds[0] < edge(10), (state, bounds)
                else: assert title.width - bounds[2] < edge(10), (state, bounds)
                rows.append(dict(label=label, density=density, profile=profile, justification=justification,
                    state=state, bounds=bounds, xft_width=reference_value["width"], client_stopped=stopped,
                    sha256=hashlib.sha256(title.tobytes()).hexdigest(), capture=name))
                (artifacts / "partial-results.json").write_text(json.dumps(dict(rows=rows, checks=checks), indent=2) + "\n")

            for density in (120, 150, 180, 210, 240):
                assert command(f"test-scale {target} {density} 10000")["ok"]
                assert command("confirm")["ok"]
                output = next(h for h in command("outputs") if h["name"] == target)
                assert command(f"move {current['id']} {output['x'] + 20} {output['y'] + 20}")["ok"]
                until(lambda: window()["preferred_scale"] == density and
                      window()["buffer_width"] == (801 * density + 60) // 120, "native document density")
                assert command(f"focus {current['id']}")["ok"]
                pause_client()
                for profile, (pattern, antialiased) in enumerate(PROFILES):
                    for justification in range(3):
                        send(owner, pattern, antialiased, justification)
                        capture(profile, justification, density, "protocol")
                os.kill(client.pid, signal.SIGCONT)
                stopped = False

            saved = appearance()
            owner.stop()
            legacy_owner = connect(version=15)
            assert appearance() == saved, "Title preferences lost across older-shell replacement"
            legacy_owner.stop()
            checks.append("v15 shell replacement preserves appearance")
            for mode in range(4):
                owner = connect(workspace_mode=mode)
                pause_client()
                for profile, justification in ((2, 1), (3, 2), (0, 0)):
                    send(owner, *PROFILES[profile], justification)
                    capture(profile, justification, 240, f"workspace-{mode}")
                before = appearance()
                for settings in ({}, dict(font="", antialiased=False, justification="center"),
                                 dict(font="Helvetica", antialiased=False, justification="invalid")):
                    start = len(owner.events)
                    owner.send(json.dumps(dict(action="title-appearance", settings=settings)))
                    result = owner.wait(lambda: next((e for e in owner.events[start:] if e["event"] == "title-appearance"), None),
                                        "invalid Workspace appearance reply")
                    assert not result["queued"] and appearance() == before, result
                checks.append(f"Workspace mode{mode}: settings and invalid-input rejection")
                os.kill(client.pid, signal.SIGCONT)
                stopped = False
                owner.stop()
            owner = connect()
            before = appearance()
            for request in ("title-appearance 2 0 Helvetica:bold:pixelsize=12",
                            "title-appearance 0 3 Helvetica:bold:pixelsize=12",
                            "title-appearance 0 0 Helvetica:bold:pixelsize=600"):
                owner.send(request)
                owner.snapshot()
                assert appearance() == before, (request, appearance(), before)
            checks.append("invalid protocol appearance values preserve state")
            owner.stop()
            (artifacts / "results.json").write_text(json.dumps(dict(rows=rows, checks=checks), indent=2) + "\n")
            print(f"Native title appearance: {len(rows)} snapshots and {len(checks)} protocol/client checks PASS")
        finally:
            if read is not None: os.close(read)
            if stopped and client and client.poll() is None: os.kill(client.pid, signal.SIGCONT)
            for owner in owners:
                if owner.process.poll() is None: owner.stop()
            for process in reversed(processes):
                if process.poll() is None: process.terminate()
            for process in reversed(processes):
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
            control.close()
            broker.close()
            (artifacts / "partial-results.json").write_text(json.dumps(dict(rows=rows, checks=checks), indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("compositor", "shell-probe", "workspace-shell-probe", "gui-probe"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--legacy-compositor")
    args = parser.parse_args()
    run(args.compositor, args.shell_probe, args.workspace_shell_probe, args.gui_probe, args.artifacts.resolve())
    if args.legacy_compositor:
        check_legacy(args.legacy_compositor, args.workspace_shell_probe, args.artifacts.resolve() / "legacy-v15")
