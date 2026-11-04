#!/usr/bin/env python3
"""Exercise public AppKit document state and compare native frame controls."""
import argparse
import json
import os
from pathlib import Path
import select
import shutil
import socket
import subprocess
import tempfile
import uuid

from PIL import Image
from integration import read_json_lines, until
from gnustep import process_runtime


def matches_control(candidate, reference, scale, left=782):
    if candidate is None:
        return False
    edge = lambda value: (value * scale + 60) // 120
    if candidate.size != (edge(801), edge(23)):
        return False
    # Compare the real AppKit control rendered at this density, including its
    # vector diagonals. Enlarging the 1x reference would hide HiDPI regressions.
    actual = candidate.crop((edge(left), edge(4), edge(left + 14), edge(18)))
    return actual.size == reference.size and actual.tobytes() == reference.tobytes()


def run(compositor, gui_probe, application_probe, artifacts):
    artifacts.mkdir(parents=True)
    references, records = {}, []
    with tempfile.TemporaryDirectory(prefix="nextspace-native-frames-") as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS="headless",
                   WLR_HEADLESS_OUTPUTS="2", WLR_RENDERER="pixman")
        for name in ("DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET"):
            env.pop(name, None)
        captures = artifacts / "captures"
        captures.mkdir()
        env["NEXTSPACE_COMPOSITOR_CAPTURE_DIR"] = str(captures.resolve())
        control, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        control.settimeout(5)
        with (artifacts / "compositor.log").open("w") as log:
            server = subprocess.Popen([compositor, "-c", str(child.fileno())],
                pass_fds=[child.fileno()], env=env, stdout=subprocess.PIPE, stderr=log, text=True)
        child.close()

        def command(text):
            control.sendall(text.encode())
            return json.loads(control.recv(65536))

        try:
            assert select.select([server.stdout], [], [], 10)[0], "No compositor socket"
            line = server.stdout.readline().strip()
            assert line.startswith("WAYLAND_DISPLAY="), line
            env["WAYLAND_DISPLAY"] = line.split("=", 1)[1]
            (artifacts / "compositor-runtime.json").write_text(
                json.dumps(process_runtime(server.pid), indent=2) + "\n")
            output = command("outputs")[0]["name"]
            # Retain an independent AppKit-rendered reference before testing SSD.
            for decorated, initial, deferred in ((False, False, False), (True, False, False),
                                                 (True, True, False), (True, True, True)):
                label = "server" if decorated else "client"
                if initial:
                    label += "-edited" + ("-deferred" if deferred else "")
                directory = artifacts / label
                directory.mkdir()
                client_env = dict(env, NEXTSPACE_SESSION_ID=str(uuid.uuid4()),
                                  NEXTSPACE_WAYLAND_CAPTURE_DIR=str(directory.resolve()))
                with (directory / "probe.log").open("w") as log, (directory / "probe.stderr").open("w") as errors:
                    client = subprocess.Popen([gui_probe, "-GSBackend", "libgnustep-wayland", "-GSTheme", "NextSpace",
                        "-GSWaylandServerDecorations", "YES" if decorated else "NO",
                        "-DocumentEdited", "YES" if initial else "NO", "-DeferredWindow", "YES" if deferred else "NO",
                        "-CloseDelegateProbe", "YES"],
                        env=client_env, stdout=log, stderr=errors)

                def window():
                    assert client.poll() is None, f"AppKit probe exited: {client.returncode}"
                    return next((w for w in command("windows") if w["pid"] == client.pid
                                 and w["title"] == "WaylandProbe" and w["style"] == 15), None)

                def query(action=None):
                    w = window()
                    args = [application_probe, "--application-action" if action else "--application-state", "WaylandProbe"]
                    if action:
                        args.append(action)
                    args += ["--window-number", str(w["client_id"])]
                    try:
                        result = subprocess.run(args, env=client_env, capture_output=True, text=True, timeout=10)
                    except subprocess.TimeoutExpired:
                        (directory / "timeout-request.json").write_text(json.dumps(dict(
                            arguments=args, window=w, client_pid=client.pid, compositor_pid=server.pid), indent=2) + "\n")
                        if shutil.which("gdb"):
                            for name, process in (("client", client), ("compositor", server)):
                                if process.poll() is None:
                                    with (directory / f"timeout-{name}.log").open("w") as log:
                                        subprocess.run(["gdb", "--batch", "-p", str(process.pid), "-ex", "thread apply all bt"],
                                            stdout=log, stderr=log, timeout=10)
                        raise
                    assert result.returncode == 0, (args, result.stdout, result.stderr)
                    return json.loads(result.stdout)

                def image(path):
                    try:
                        with Image.open(path) as source:
                            return source.convert("RGB")
                    except OSError:
                        return None

                try:
                    w = until(window, "AppKit document window")
                    assert w["server_decorated"] == decorated, w
                    assert query()["document_edited"] == initial
                    if decorated:
                        until(lambda: window().get("document_edited") == initial, "initial edited state")
                    assert command(f"focus {w['id']}")["ok"]
                    libraries = sorted({line.split()[-1] for line in Path(f"/proc/{client.pid}/maps").read_text().splitlines()
                        if "libgnustep-base.so." in line or "libgnustep-gui.so." in line or "libgnustep-wayland" in line})
                    (directory / "runtime.json").write_text(json.dumps(libraries, indent=2) + "\n")
                    (directory / "full-runtime.json").write_text(
                        json.dumps(process_runtime(client.pid), indent=2) + "\n")
                    for scale in ((120, 150, 180, 210, 240) if not initial else (120,)):
                        assert command(f"test-scale {output} {scale} 10000")["ok"]
                        assert command("confirm")["ok"]
                        head = next(h for h in command("outputs") if h["name"] == output)
                        assert command(f"move {w['id']} {head['x'] + 10} {head['y'] + 10}")["ok"]
                        until(lambda: window()["preferred_scale"] == scale, "native density")
                        number = window()["client_id"]
                        surface = directory / f"window-{number}-{scale}.png"
                        title = captures / f"frame-{w['id']}-{scale}.png" if decorated else surface
                        until(lambda: image(title), "title capture")
                        if initial:
                            until(lambda: matches_control(image(title), references["edited-normal", scale], scale),
                                  "edited indicator before first mapping")
                            records.append(dict(kind=label + "-initial", scale=scale, window=window()))
                        for edited in (False, True):
                            state = query("edited" if edited else "clean")
                            assert state["document_edited"] == edited, state
                            if decorated:
                                until(lambda: window().get("document_edited") == edited, "server document-edited metadata")
                            for control_name, left in (("close", 782), ("miniaturize", 4)):
                                for pressed in (False, True):
                                    key = ("" if control_name == "close" else "miniaturize-") + f"{'edited' if edited else 'clean'}-{'pressed' if pressed else 'normal'}"
                                    if decorated:
                                        current = window()
                                        assert command(f"pointer {current['x'] + left + 7} {current['y'] + 11}")["ok"]
                                        if pressed:
                                            assert command("button 272 1")["ok"]
                                    else:
                                        query(control_name + ("-highlight" if pressed else "-unhighlight"))
                                    def captured():
                                        candidate = image(title)
                                        if candidate is None:
                                            return None
                                        if decorated and not matches_control(candidate, references[key, scale], scale, left):
                                            return None
                                        return candidate
                                    try:
                                        result = until(captured, f"{label} {key} at {scale}/120")
                                        result.save(directory / f"{key}-{scale}.png")
                                        if not decorated:
                                            edge = lambda value: (value * scale + 60) // 120
                                            references[key, scale] = result.crop((edge(left), edge(4), edge(left + 14), edge(18)))
                                        records.append(dict(kind=label, scale=scale, control=control_name, edited=edited, pressed=pressed, window=window()))
                                    finally:
                                        if decorated and pressed:
                                            # Release outside the control so the document survives.
                                            current = window()
                                            command(f"pointer {current['x'] + 100} {current['y'] + 11}")
                                            command("button 272 0")
                        query("clean")
                    if decorated and not initial:
                        for hide, restore, flag in (("hide", "unhide", "visible"),
                                                    ("miniaturize", "deminiaturize", "minimized"),
                                                    ("order-out", "order-front", "visible")):
                            query(hide)
                            until(lambda: window()[flag] == (flag == "minimized"), hide)
                            query("edited")
                            until(lambda: window()["document_edited"], "edited while hidden")
                            query(restore)
                            until(lambda: window()["visible"] and not window()["minimized"], restore)
                            # Restoration must invalidate the cached title even without a new client title.
                            until(lambda: matches_control(image(title), references["edited-normal", scale], scale),
                                  "restored edited control")
                            records.append(dict(kind=hide + "-restore", window=window()))
                            query("clean")
                    (directory / "state.json").write_text(json.dumps(query(), indent=2) + "\n")
                    if decorated and not initial:
                        query("edited")
                        current = window()
                        until(lambda: window()["document_edited"], "edited before close request")
                        def events():
                            return read_json_lines(directory / "probe.log", '{"event":')
                        assert command(f"pointer {current['x'] + current['width'] - 11} {current['y'] + 11}")["ok"]
                        command("button 272")
                        until(lambda: any(e["event"] == "close-request" and e["denied"] for e in events()),
                              "AppKit delegate vetoes edited close")
                        assert window()["visible"] and query()["document_edited"]
                        records.append(dict(kind="edited-close-veto", window=window()))
                        command("button 272")
                        until(lambda: any(e["event"] == "window-close" for e in events()), "AppKit accepts edited close")
                        until(lambda: not any(w["id"] == current["id"] for w in command("windows")), "closed surface removed")
                        records.append(dict(kind="edited-close-accepted"))
                except BaseException:
                    (directory / "failure-windows.json").write_text(json.dumps(command("windows"), indent=2) + "\n")
                    raise
                finally:
                    if client.poll() is None:
                        client.terminate()
                    client.wait(timeout=5)
        finally:
            if server.poll() is None:
                server.terminate()
            server.wait(timeout=5)
            control.close(); server.stdout.close()
    (artifacts / "results.json").write_text(json.dumps(records, indent=2) + "\n")
    print(json.dumps(dict(document_frame_trials=len(records))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compositor", required=True)
    parser.add_argument("--gui-probe", required=True)
    parser.add_argument("--application-probe", required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    run(args.compositor, args.gui_probe, args.application_probe, args.artifacts)
