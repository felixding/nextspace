#!/usr/bin/env python3
"""Compare native title states with independently rendered AppKit frames."""
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
from integration import read_json_lines, until

BEVEL_BOXES = dict(top=(40, 0, 65, 3), bottom=(40, 20, 65, 23),
                   left=(0, 3, 3, 20), right=(798, 3, 801, 20))

def title_bevel(title, density):
    edge = lambda value: (value * density + 60) // 120
    return {name: hashlib.sha256(title.crop(tuple(edge(v) for v in box)).tobytes()).hexdigest()
            for name, box in BEVEL_BOXES.items()}


def matches_bevel(title, reference, density):
    # Use the actual 1x AppKit cells, as for frame controls. Fractional CSD
    # edges accumulate antialiasing across focus repaints and are not stable.
    edge = lambda value: (value * density + 60) // 120
    for left, top, right, bottom in BEVEL_BOXES.values():
        for y in range(top, bottom):
            for x in range(left, right):
                expected = reference.getpixel((x, y))
                pixels = title.crop((edge(x), edge(y), edge(x + 1), edge(y + 1)))
                if pixels.getextrema() != tuple((c, c) for c in expected): return False
    return True


def run(compositor, gui_probe, registry_probe, artifacts, reference_only=False, transparent=False):
    artifacts.mkdir(parents=True)
    captures = artifacts / "frames"
    captures.mkdir()
    rows, references, bevel_references = [], {}, {}
    # The pinned AppKit enum is key=0, normal=1, main=2.
    colors = {0: 0, 1: 170, 2: 85}
    with tempfile.TemporaryDirectory(prefix="nextspace-title-states-") as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS="headless",
                   WLR_HEADLESS_OUTPUTS="2", WLR_RENDERER="pixman",
                   NEXTSPACE_COMPOSITOR_CAPTURE_DIR=str(captures.resolve()))
        for name in ("DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET"):
            env.pop(name, None)
        control, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        control.settimeout(5)
        with (artifacts / "compositor.log").open("w") as log:
            server = subprocess.Popen([compositor, "-c", str(child.fileno())],
                pass_fds=[child.fileno()], env=env, stdout=subprocess.PIPE, stderr=log, text=True)
        child.close()

        def command(value):
            control.sendall(value.encode())
            return json.loads(control.recv(65536))

        try:
            assert select.select([server.stdout], [], [], 10)[0]
            line = server.stdout.readline().strip()
            assert line.startswith("WAYLAND_DISPLAY="), line
            env["WAYLAND_DISPLAY"] = line.split("=", 1)[1]
            target = command("outputs")[0]["name"]
            assert command(f"output-position {target} -1600 -200")["ok"]
            for decorated in ((False,) if reference_only else (False, True)):
                directory = artifacts / ("server" if decorated else "client")
                directory.mkdir()
                client_env = dict(env, NEXTSPACE_SESSION_ID="test-" + str(uuid.uuid4()),
                                  NEXTSPACE_WAYLAND_CAPTURE_DIR=str(directory.resolve()))
                path = directory / "probe.log"
                with path.open("w") as log, (directory / "probe.stderr").open("w") as errors:
                    client = subprocess.Popen([gui_probe, "-GSBackend", "libgnustep-wayland", "-GSTheme", "NextSpace",
                        "-GSWaylandServerDecorations", "YES" if decorated else "NO",
                        "-TransparentWindow", "YES" if transparent else "NO"],
                        env=client_env, stdout=log, stderr=errors)
                foreign = None
                stopped = False

                def window():
                    assert client.poll() is None, f"AppKit probe exited: {client.returncode}"
                    return next((w for w in command("windows") if w["pid"] == client.pid and w["style"] == 15), None)

                def events():
                    return read_json_lines(path, '{"event":')

                def appkit_state(state, selected=None):
                    number = (selected or window())["client_id"]
                    def current():
                        latest = next((e for e in reversed(events()) if e["event"] == "title-state" and
                            e["window"] == number), None)
                        return latest if latest and latest["state"] == state and (state != 0 or latest["key"]) else None
                    return until(current, f"AppKit title state {state}")

                def foreign_focus(label):
                    nonlocal foreign
                    with (directory / f"foreign-{density}-{label}.log").open("w") as log:
                        foreign = subprocess.Popen([registry_probe, "--window", "TitleStateForeign"],
                            env=env, stdout=log, stderr=log)
                    until(lambda: any(t["title"] == "TitleStateForeign" and t["focused"] for t in command("windows")),
                          "another application takes focus")

                def close_foreign():
                    nonlocal foreign
                    foreign.terminate(); foreign.wait(timeout=5); foreign = None

                def snapshot(state, label, observed=None):
                    q = appkit_state(state if observed is None else observed)
                    w = window()
                    edge = lambda value: (value * density + 60) // 120
                    source = captures / f"frame-{w['id']}-{density}.png" if decorated else (
                        directory / f"window-{w['client_id']}-{density}.png")
                    expected = references.get((density, state))
                    def matches():
                        try:
                            with Image.open(source) as image:
                                if transparent and not decorated:
                                    assert image.mode == "RGBA" and image.getextrema()[3][0] == 0, "Transparent backing lost alpha"
                                title = image.convert("RGB").crop((0, 0, edge(801), edge(23)))
                        except OSError: return None
                        if title.size != (edge(801), edge(23)): return None
                        body = title.crop((edge(40), edge(5), edge(65), edge(18))).getextrema()
                        text = title.crop((edge(230), edge(4), edge(570), edge(19))).getextrema()
                        bevel = title_bevel(title, density)
                        if decorated:
                            if (body, text) != expected or not matches_bevel(title, bevel_references[state], density): return None
                        elif body != ((colors[state], colors[state]),) * 3:
                            return None
                        return title, body, text, bevel
                    title, body, text, bevel = until(matches, f"{'server' if decorated else 'AppKit'} {label} title pixels")
                    assert text == (((0, 255) if state == 0 else (0, 170) if state == 1 else (85, 255)),) * 3, text
                    if not decorated:
                        references[density, state] = body, text
                        if density == 120: bevel_references[state] = title
                    title.save(directory / f"{density}-{label}.png")
                    rows.append(dict(decorated=decorated, density=density, label=label,
                        transparent=transparent, title_state=state, body=body, text=text, bevel=bevel, appkit=q, window=w))
                    (artifacts / "partial-results.json").write_text(json.dumps(rows, indent=2) + "\n")

                try:
                    w = until(window, "native title-state document")
                    assert w["server_decorated"] == decorated
                    for density in (120, 150, 180, 210, 240):
                        assert command(f"test-scale {target} {density} 10000")["ok"]
                        assert command("confirm")["ok"]
                        h = next(h for h in command("outputs") if h["name"] == target)
                        assert command(f"move {w['id']} {h['x'] + 20} {h['y'] + 20}")["ok"]
                        until(lambda: window()["preferred_scale"] == density and window()["buffer_width"] == (801 * density + 60) // 120,
                              "title-state document backing density")
                        assert command(f"focus {w['id']}")["ok"]
                        snapshot(0, "key")
                        foreign_focus("normal")
                        snapshot(1, "normal")
                        close_foreign()
                        assert command(f"focus {w['id']}")["ok"]
                        appkit_state(0)
                        button = next(e for e in events() if e["event"] == "show-modal")
                        w = window()
                        assert command(f"pointer {w['x'] + int(button['x'])} {w['y'] + w['height'] - int(button['y'])}")["ok"]
                        assert command("button 272")["ok"]
                        panel = until(lambda: next((t for t in command("windows") if t["pid"] == client.pid and
                            t["title"] == "Wayland modal panel" and t["focused"]), None), "real AppKit panel takes key focus")
                        assert appkit_state(0, panel)["key"]
                        snapshot(2, "main")
                        if decorated:
                            assert window()["client_title_state"] == 2
                            os.kill(client.pid, signal.SIGSTOP); stopped = True
                            foreign_focus("stopped")
                            snapshot(1, "main-stopped-foreign", observed=2)
                            assert window()["client_title_state"] == 2 and window()["title_state"] == 1
                            close_foreign()
                            assert command(f"focus {panel['id']}")["ok"]
                            snapshot(2, "main-stopped-restored")
                            os.kill(client.pid, signal.SIGCONT); stopped = False
                        button = [e for e in events() if e["event"] == "modal-button"][-1]
                        assert command(f"pointer {panel['x'] + int(button['x'])} {panel['y'] + panel['height'] - int(button['y'])}")["ok"]
                        assert command("button 272")["ok"]
                        until(lambda: not any(t["title"] == "Wayland modal panel" for t in command("windows")), "modal panel closes")
                        until(lambda: window()["focused"], "document receives key focus again")
                        snapshot(0, "key-restored")
                    mappings = sorted({line.split()[-1] for line in Path(f"/proc/{client.pid}/maps").read_text().splitlines()
                        if any(s in line for s in ("libgnustep-base.so.", "libgnustep-gui.so.", "libgnustep-wayland-"))})
                    (directory / "runtime.json").write_text(json.dumps(mappings, indent=2) + "\n")
                except BaseException:
                    failure = dict(windows=command("windows"), events=events()[-10:])
                    (directory / "failure.json").write_text(json.dumps(failure, indent=2) + "\n")
                    raise
                finally:
                    if stopped and client.poll() is None: os.kill(client.pid, signal.SIGCONT)
                    if foreign and foreign.poll() is None: foreign.terminate(); foreign.wait(timeout=5)
                    if client.poll() is None: client.terminate()
                    client.wait(timeout=5)
        finally:
            if server.poll() is None: server.terminate()
            server.wait(timeout=5)
            control.close(); server.stdout.close()
    (artifacts / "results.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(f"AppKit normal/main/key title state and pixel parity: {len(rows)} snapshots PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compositor", required=True)
    parser.add_argument("--gui-probe", required=True)
    parser.add_argument("--registry-probe", required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--reference-only", action="store_true")
    parser.add_argument("--transparent", action="store_true", help="Also preserve transparent window backing alpha")
    run(**vars(parser.parse_args()))
