#!/usr/bin/env python3
"""Verify actual AppKit fullscreen layout, backing, input and restoration."""
import argparse
import json
import os
from pathlib import Path
import re
import select
import socket
import subprocess
import tempfile
import uuid

from PIL import Image
from integration import read_json_lines, until


def run(compositor, gui_probe, application_probe, artifacts):
    artifacts.mkdir(parents=True)
    rows = []
    rect = lambda value: tuple(map(float, re.findall(r"-?\d+(?:\.\d+)?", value)))
    frame = lambda w: tuple(w[k] for k in ("x", "y", "width", "height"))
    with tempfile.TemporaryDirectory(prefix="nextspace-native-fullscreen-") as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS="headless",
                   WLR_HEADLESS_OUTPUTS="2", WLR_RENDERER="pixman")
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

            def head():
                return next(h for h in command("outputs") if h["name"] == target)

            def scale(density):
                assert command(f"test-scale {target} {density} 10000")["ok"]
                assert command("confirm")["ok"]

            for decorated, transparent in ((False, False), (True, False), (True, True)):
                directory = artifacts / ("transparent" if transparent else "server" if decorated else "client")
                directory.mkdir()
                client_env = dict(env, NEXTSPACE_SESSION_ID="test-" + str(uuid.uuid4()),
                                  NEXTSPACE_WAYLAND_CAPTURE_DIR=str(directory.resolve()))
                path = directory / "probe.log"
                with path.open("w") as log, (directory / "probe.stderr").open("w") as errors:
                    client = subprocess.Popen([gui_probe, "-GSBackend", "libgnustep-wayland", "-GSTheme", "NextSpace",
                        "-GSWaylandServerDecorations", "YES" if decorated else "NO",
                        "-TransparentWindow", "YES" if transparent else "NO"],
                        env=client_env, stdout=log, stderr=errors)

                def window():
                    assert client.poll() is None, f"AppKit probe exited: {client.returncode}"
                    return next((w for w in command("windows") if w["pid"] == client.pid and
                                 w["title"] == "WaylandProbe" and w["style"] == 15), None)

                def events():
                    return read_json_lines(path, '{"event":')

                def query(action=None):
                    args = [application_probe, "--application-action" if action else "--application-state", "WaylandProbe"]
                    if action: args.append(action)
                    args += ["--window-number", str(window()["client_id"])]
                    result = subprocess.run(args, env=client_env, capture_output=True, text=True, timeout=10)
                    assert result.returncode == 0, (args, result.stdout, result.stderr)
                    return json.loads(result.stdout)

                def fullscreen(density):
                    h = head(); size = (h["width"], h["height"])
                    w = window()
                    if not w["fullscreen"] or frame(w) != frame(h): return None
                    if w["server_decorated"] or "viewport_source" in w: return None
                    if (w["surface_width"], w["surface_height"]) != size: return None
                    if (w["buffer_width"], w["buffer_height"]) != tuple((s * density + 60) // 120 for s in size): return None
                    state = query()
                    if not state["style_mask"] & (1 << 14): return None
                    if rect(state["frame"]) != rect(state["screen_frame"]): return None
                    if rect(state["content_rect"]) != rect(state["frame"]): return None
                    if any(rect(state[key]) != (0, 0, *size) for key in ("content_view_frame", "content_view_bounds")): return None
                    if state["backing_scale"] != density / 120: return None
                    return dict(window=w, appkit=state)

                try:
                    w = until(window, "AppKit fullscreen fixture")
                    assert w["server_decorated"] == decorated, w
                    for density in (120, 150, 180, 210, 240):
                        scale(density)
                        h = head()
                        assert command(f"move {w['id']} {h['x'] + 50} {h['y'] + 50}")["ok"]
                        until(lambda: window()["preferred_scale"] == density, "normal native density")
                        for maximized in (False, True):
                            if maximized:
                                query("zoom")
                                until(lambda: window()["maximized"] and frame(window()) == frame(head()), "initial AppKit zoom")
                            def aligned():
                                w = window(); state = query()
                                bottom = max(o["y"] + o["height"] for o in command("outputs"))
                                return state if rect(state["frame"]) == (w["x"], bottom - w["y"] - w["height"],
                                    w["width"], w["height"]) else None
                            before = until(aligned, "AppKit floating/maximized geometry acknowledged")
                            before_window = window()
                            query("fullscreen")
                            current = until(lambda: fullscreen(density), "AppKit fullscreen frame/content/backing contract")
                            assert current["window"]["maximized"] == maximized
                            # Test both former frame bands as real client content.
                            for x, y in ((100, 12), (100, h["height"] - 4)):
                                count = len(events())
                                assert command(f"pointer {h['x'] + x} {h['y'] + y}")["ok"]
                                assert command("button 272")["ok"]
                                until(lambda: any(e["event"] == "click" and (e["x"], e["y"]) ==
                                    (x, h["height"] - y) for e in events()[count:]), "fullscreen content input")
                            capture = directory / f"window-{window()['client_id']}-{density}.png"
                            def complete_image():
                                try:
                                    with Image.open(capture) as source: image = source.convert("RGBA")
                                except OSError: return None
                                if image.size != (window()["buffer_width"], window()["buffer_height"]): return None
                                background = image.getpixel((100, 2))
                                if background[3] != (0 if transparent else 255): return None
                                if transparent:
                                    sample = image.getpixel((round(30 * density / 120), round((h["height"] - 230) * density / 120)))
                                    if sample != (255, 0, 0, 128): return None
                                return image if all(image.getpixel(p) == background for p in (
                                    (0, 0), (image.width - 1, 0), (0, image.height - 1),
                                    (image.width - 1, image.height - 1))) else None
                            image = until(complete_image, "fullscreen content reaches every backing edge")
                            image.save(directory / f"fullscreen-{density}-zoom-{int(maximized)}.png")
                            # A real AppKit popup must retain its content-relative input.
                            assert command(f"pointer {h['x'] + 270} {h['y'] + h['height'] - 476}")["ok"]
                            assert command("button 272")["ok"]
                            popup = until(lambda: next(iter(command("popups")), None), "fullscreen AppKit popup")
                            assert (popup["width"], popup["height"]) == (200, 120), popup
                            assert command(f"pointer {popup['x'] + 95} {popup['y'] + 85}")["ok"]
                            assert command("button 272")["ok"]
                            until(lambda: not command("popups"), "fullscreen popup close")
                            changed = 180 if density == 150 else 150
                            scale(changed)
                            until(lambda: fullscreen(changed), "fullscreen live density change")
                            scale(density)
                            until(lambda: fullscreen(density), "fullscreen density restoration")
                            query("fullscreen")
                            def restored():
                                w = window()
                                if w["fullscreen"] or frame(w) != frame(before_window): return None
                                state = query()
                                keys = ("frame", "content_rect", "content_view_frame", "content_view_bounds", "style_mask")
                                return state if all(state[k] == before[k] for k in keys) else None
                            restored_state = until(restored, "exact AppKit fullscreen restoration")
                            assert window()["server_decorated"] == decorated
                            assert window()["maximized"] == maximized
                            rows.append(dict(decorated=decorated, transparent=transparent, density=density, maximized=maximized,
                                before=before, fullscreen=current, restored=restored_state, popup=popup))
                            (artifacts / "partial-results.json").write_text(json.dumps(rows, indent=2) + "\n")
                            if maximized:
                                query("zoom")
                                until(lambda: not window()["maximized"], "final AppKit unzoom")
                    if transparent:
                        normal = window()
                        query("fullscreen")
                        until(lambda: fullscreen(density), "native fullscreen before output removal")
                        removed = target
                        assert command(f"remove-output {removed}")["ok"]
                        remaining = command("outputs")[0]
                        target = remaining["name"]
                        recovered = until(lambda: fullscreen(remaining["scale"]), "AppKit fullscreen recovers after output removal")
                        assert not recovered["window"]["maximized"]
                        query("fullscreen")
                        until(lambda: not window()["fullscreen"] and (window()["width"], window()["height"]) ==
                            (normal["width"], normal["height"]), "floating size survives fullscreen output removal")
                        restored_state = until(aligned, "AppKit floating geometry after output removal")
                        assert restored_state["style_mask"] == 15
                        (artifacts / "hotplug.json").write_text(json.dumps(dict(removed=removed,
                            recovered=recovered, restored=restored_state, window=window()), indent=2) + "\n")
                    libraries = sorted({line.split()[-1] for line in Path(f"/proc/{client.pid}/maps").read_text().splitlines()
                        if any(name in line for name in ("libgnustep-base.so.", "libgnustep-gui.so.", "libgnustep-wayland-"))})
                    (directory / "runtime.json").write_text(json.dumps(libraries, indent=2) + "\n")
                except BaseException:
                    failure = dict(windows=command("windows"), outputs=command("outputs"), events=events()[-10:])
                    try: failure["appkit"] = query()
                    except BaseException as error: failure["appkit_error"] = repr(error)
                    (directory / "failure.json").write_text(json.dumps(failure, indent=2) + "\n")
                    raise
                finally:
                    if client.poll() is None: client.terminate()
                    client.wait(timeout=5)
        finally:
            if server.poll() is None: server.terminate()
            server.wait(timeout=5)
            control.close(); server.stdout.close()
    (artifacts / "results.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(f"AppKit fullscreen layout, input, popup, backing, restoration and hotplug: {len(rows)} cases PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compositor", required=True)
    parser.add_argument("--gui-probe", required=True)
    parser.add_argument("--application-probe", required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    run(**vars(parser.parse_args()))
