#!/usr/bin/env python3
"""Exercise real native buffers, scale transitions, input and rollback."""
import argparse
import base64
import json
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from pasteboard import install_service, remove_service
from applications import run as run_applications
from session import run as run_session
from gnustep import capture_process_failure, process_runtime


def read_json_lines(path, prefix=None):
    """Read complete event records; malformed newline-terminated JSON is fatal."""
    path = Path(path)
    lines = path.read_bytes().split(b"\n")
    if lines[-1]:
        trace = path.with_name(path.name + ".partial-read.json")
        if not trace.exists():
            trace.write_text(json.dumps(dict(complete_records=len(lines) - 1,
                partial=lines[-1].decode("utf-8", errors="backslashreplace")), indent=2) + "\n")
    marker = prefix.encode() if prefix is not None else None
    return [json.loads(line) for line in lines[:-1] if marker is None or line.startswith(marker)]


def until(check, description, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.02)
    raise AssertionError(f"Timed out: {description}")



def submitted_image_pixels(rgb, pattern, logical_size, scale):
    """Check actual submitted vector, bitmap-density and cropped-opacity pixels."""
    width, height = logical_size
    assert rgb.size == ((width * scale + 60) // 120, (height * scale + 60) // 120), rgb.size
    x = round(pattern["x"] * scale / 120)
    y = round((height - pattern["y"] - 16) * scale / 120)
    size = 16 * scale // 120
    direct_x = x + 40 * scale // 120
    image = rgb.crop((x, y, x + size, y + size))
    direct = rgb.crop((direct_x, y, direct_x + size, y + size))
    # Exclude only the outer pixel, where image-boundary clip
    # coverage differs from a primitive without an image clip.
    interior = (1, 1, size - 1, size - 1)
    assert image.crop(interior).tobytes() == direct.crop(interior).tobytes(), f"Vector image resampled at {scale}/120"
    low, high = image.convert("L").getextrema()
    assert low < 20 and high >= 100, f"Missing vector pixels at {scale}/120: {low, high}"
    def sample(dx, dy):
        return rgb.getpixel((round((pattern["x"] + dx) * scale / 120),
            round((height - pattern["y"] - dy) * scale / 120)))
    assert sample(24, 4) == ((255, 0, 0) if scale == 120 else (0, 0, 255)), "Wrong backing-density representation"
    if scale > 120:
        assert all(abs(c - 85) <= 1 for c in sample(88, 8)), "Vector image opacity outside cropped line"
        assert all(abs(c - 213) <= 1 for c in sample(82, 8)), "Cropped vector line lost density or opacity"
    return dict(scale=scale, vector_matches_direct=True)

def run(compositor, probe, artifacts, protocol_mode="native", registry_probe=None, pasteboard_probe=None, pasteboard_server=None, comparators=(), applications=None, workspace_probe=None, primary_selection=False, server_frames=False, during_upgrade=None):
    artifacts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nextspace-runtime-") as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS="headless",
                   WLR_HEADLESS_OUTPUTS="2", WLR_RENDERER="pixman")
        env.pop("DISPLAY", None)
        env.pop("WAYLAND_DISPLAY", None)
        env["NEXTSPACE_WAYLAND_CAPTURE_DIR"] = str(artifacts.resolve())
        if server_frames:
            frames = artifacts / "server-frames"
            frames.mkdir()
            env["NEXTSPACE_COMPOSITOR_CAPTURE_DIR"] = str(frames.resolve())
        control, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        control.settimeout(5)
        with (artifacts / "compositor.log").open("w") as log:
            switches = {"native": [], "no-fractional": ["-F"], "no-viewporter": ["-V"],
                        "no-placement": ["-A"], "surface-v1": ["-1"],
                        "surface-v1-no-viewporter": ["-1", "-V"]}[protocol_mode]
            server = subprocess.Popen([compositor, "-c", str(child.fileno()), *switches],
                pass_fds=[child.fileno()], env=env, stdout=subprocess.PIPE,
                stderr=log, text=True)
            child.close()
            client = None
            occluder = None
            storage = None
            service_bundle = None

            def command(text):
                control.sendall(text.encode())
                return json.loads(control.recv(65536))

            try:
                assert select.select([server.stdout], [], [], 10)[0], "No compositor socket"
                line = server.stdout.readline().strip()
                assert line.startswith("WAYLAND_DISPLAY="), line
                env["WAYLAND_DISPLAY"] = line.split("=", 1)[1]
                (artifacts / "compositor-runtime.json").write_text(json.dumps(process_runtime(server.pid), indent=2) + "\n")
                if pasteboard_probe and pasteboard_server:
                    env["NEXTSPACE_SESSION_ID"] = str(uuid.uuid4())
                    with (artifacts / "gpbs.log").open("w") as log:
                        storage = subprocess.Popen([pasteboard_server, "--no-fork"], env=env, stdout=log, stderr=log)
                    until(lambda: subprocess.run([pasteboard_probe, "--ping"], env=env).returncode == 0,
                          "native pasteboard storage")
                    service_bundle = install_service(pasteboard_probe, env)
                outputs = command("outputs")
                assert len(outputs) == 2, outputs
                target = max(outputs, key=lambda o: o["x"])["name"]
                origin = min(outputs, key=lambda o: o["x"])
                with (artifacts / "probe.log").open("w") as stdout, (artifacts / "probe-errors.log").open("w") as stderr:
                    client = subprocess.Popen([probe, "-GSBackend", "libgnustep-wayland", "-GSTheme", "NextSpace",
                                               "-PointerButtonProbe", "YES" if protocol_mode == "native" else "NO"],
                                              env=env, stdout=stdout, stderr=stderr)

                def window():
                    return next((w for w in command("windows") if w["title"] == "WaylandProbe"
                                 and (w["width"], w["height"]) == (801, 601)), None)

                w = until(window, "native GNUstep window")
                wid = w["id"]
                if server_frames:
                    maps = Path(f"/proc/{client.pid}/maps").read_text().splitlines()
                    libraries = sorted({line.split()[-1] for line in maps if
                        "libgnustep-base.so." in line or "libgnustep-gui.so." in line or "libgnustep-wayland" in line})
                    assert any("libgnustep-wayland" in path for path in libraries), libraries
                    (artifacts / "native-runtime.json").write_text(json.dumps(dict(pid=client.pid,
                        libraries=libraries), indent=2) + "\n")

                def effective_scale(scale):
                    if "-1" in switches and "-V" in switches:
                        return 120
                    return ((scale + 119) // 120) * 120 if "-F" in switches or "-V" in switches else scale

                def dimensions(scale):
                    w = window()
                    scale = effective_scale(scale)
                    expected = ((801 * scale + 60) // 120, (601 * scale + 60) // 120)
                    return w and (w["width"], w["height"]) == (801, 601) and (
                        w["buffer_width"], w["buffer_height"]) == expected

                until(lambda: dimensions(120), "initial 100% buffer")
                (artifacts / "client-runtime.json").write_text(json.dumps(process_runtime(client.pid), indent=2) + "\n")
                if during_upgrade:
                    before = dict(compositor=process_runtime(server.pid), client=process_runtime(client.pid))
                    for name, pid in (('compositor', server.pid), ('client', client.pid)):
                        (artifacts / (name + '-maps-before-upgrade.txt')).write_text(Path(f'/proc/{pid}/maps').read_text())
                    during_upgrade()
                    assert server.poll() is None and client.poll() is None and window()['id'] == wid
                    for name, pid in (('compositor', server.pid), ('client', client.pid)):
                        (artifacts / (name + '-maps-after-upgrade.txt')).write_text(Path(f'/proc/{pid}/maps').read_text())
                    (artifacts / 'live-upgrade-runtime.json').write_text(json.dumps(dict(before=before,
                        after=dict(compositor=process_runtime(server.pid), client=process_runtime(client.pid))), indent=2) + '\n')
                results = []
                for scale in (150, 180, 210, 240, 120, 180, 120, 180):
                    assert command(f"test-scale {target} {scale} 10000")["ok"]
                    assert command("confirm")["ok"]
                    output = next(o for o in command("outputs") if o["name"] == target)
                    assert command(f"move {wid} {output['x'] + 10} {output['y'] + 10}")["ok"]
                    until(lambda: dimensions(scale), f"{scale}/120 native buffer")
                    # Surface-local input must remain in logical units.
                    assert command(f"pointer {output['x'] + 210} {output['y'] + 310}")["ok"]
                    assert command("button 272")["ok"]
                    results.append(dict(scale=scale, window=window()))
                    assert command(f"move {wid} {origin['x'] + 10} {origin['y'] + 10}")["ok"]
                    until(lambda: dimensions(120), "return to 100% output")
                if server_frames:
                    from PIL import Image
                    for row in results:
                        w, density = row["window"], effective_scale(row["scale"])
                        assert w["server_decorated"] and w["frame_top"] > 0, w
                        left, top, right, bottom = (w["frame_" + k] for k in ("left", "top", "right", "bottom"))
                        assert (w["surface_width"], w["surface_height"]) == (801 - left - right, 601 - top - bottom), w
                        edge = lambda v: (v * density + 60) // 120
                        source = [edge(left), edge(top), edge(801 - right) - edge(left), edge(601 - bottom) - edge(top)]
                        assert w["viewport_source"] == source, w
                        with Image.open(frames / f"frame-{wid}-{density}.png") as png:
                            assert png.size == (edge(801), edge(top))
                            # Aliased NeXT titles can use just four colors.
                            # Exclude the bevel and controls to require actual title ink.
                            title = png.crop((edge(40), edge(3), edge(761), edge(top - 3))).convert("L")
                            low, high = title.getextrema()
                            assert high - low > 100, "Missing title glyphs"
                    (artifacts / "native-server-frames.json").write_text(json.dumps(results, indent=2) + "\n")
                # Leave the window on the scaled output for the rollback checks.
                output = next(o for o in command("outputs") if o["name"] == target)
                assert command(f"move {wid} {output['x'] + 10} {output['y'] + 10}")["ok"]
                until(lambda: dimensions(180), "return to 150% output")

                # Unconfirmed output settings revert in the compositor.
                assert command(f"test-scale {target} 240 200")["ok"]
                until(lambda: next(o for o in command("outputs") if o["name"] == target)["scale"] == 180,
                      "timeout rollback")
                until(lambda: dimensions(180), "native redraw after rollback")
                assert not command(f"test-scale {target} 0 1000")["ok"]
                assert not command("confirm")["ok"]

                def events():
                    assert client.poll() is None, f"Native client exited unexpectedly: {client.returncode}"
                    return read_json_lines(artifacts / "probe.log", '{"event":')

                until(lambda: len([e for e in events() if e["event"] == "click"]) >= 8, "logical pointer delivery")
                clicks = [e for e in events() if e["event"] == "click"]
                assert all(e["x"] == 200 and e["y"] == 301 for e in clicks), clicks
                if protocol_mode == "native":
                    from pointer_buttons import check
                    (artifacts / "pointer-buttons.json").write_text(json.dumps(
                        check(command, events, until, wid, target, dimensions), indent=2) + "\n")
                scales = [e for e in events() if e["event"] == "scale"]
                glyphs = [e for e in events() if e["event"] == "glyph-advance"]
                readbacks = [e for e in events() if e["event"] == "readback"]
                assert readbacks and all(e["ok"] for e in readbacks), readbacks
                images = [e for e in events() if e["event"] == "image-subview"]
                assert images and all(e["ok"] for e in images), images
                assert glyphs and all(e["x"] == 47 and e["y"] == 320 for e in glyphs), glyphs
                assert all(e["roundtrip"] for e in scales), scales
                expected_scales = {effective_scale(s) / 120 for s in (120, 150, 180, 210, 240)}
                assert expected_scales <= {e["scale"] for e in scales}, scales
                assert expected_scales <= {e["scale"] for e in readbacks}, readbacks
                vectors = [e for e in events() if e["event"] == "vector-image"]
                assert vectors and all(e["ok"] and e["density_rep"] for e in vectors), vectors
                assert expected_scales <= {e["scale"] for e in vectors}, vectors
                # Inspect the submitted buffer as well as AppKit readback; a
                # stale allocated view gstate can make readback falsely pass.
                from PIL import Image
                pattern = next(e for e in events() if e["event"] == "pixel-pattern")
                pixels = []
                for scale in sorted({effective_scale(s) for s in (120, 150, 180, 210, 240)}):
                    path = artifacts / f"window-{pattern['window']}-{scale}.png"
                    with Image.open(path) as png:
                        rgb = png.convert("RGB")
                    pixels.append(submitted_image_pixels(rgb, pattern, (801, 601), scale))
                (artifacts / "image-pixels.json").write_text(json.dumps(pixels, indent=2) + "\n")
                # Cursor buffers and hotspots have independent surface coordinates.
                assert command(f"focus {wid}")["ok"]
                assert command(f"pointer {output['x'] + 210} {output['y'] + 310}")["ok"]
                def cursor_key(code):
                    assert command(f"key {code} 1")["ok"]
                    assert command(f"key {code} 0")["ok"]

                cursor_key(10)  # Custom vector image: 19x17, hotspot (3,5).
                cursor_results = []
                for scale in (120, 150, 180, 210, 240):
                    assert command(f"test-scale {target} {scale} 10000")["ok"]
                    assert command("confirm")["ok"]
                    until(lambda: dimensions(scale), "cursor output scale")
                    expected = ((19 * effective_scale(scale) + 60) // 120,
                                (17 * effective_scale(scale) + 60) // 120)
                    state = until(lambda: (s if (s := command("cursor-state")).get("buffer_width") == expected[0]
                        and s.get("buffer_height") == expected[1] else None), "cursor rerender at new density")
                    assert (state["width"], state["height"], state["hotspot_x"], state["hotspot_y"]) == (19, 17, 3, 5), state
                    assert state["samples"] == [0xff00ff00, 0xff00ff00, 0xffff0000, 0xffff0000], state
                    cursor_results.append(dict(scale=scale, cursor=state))
                # The cursor follows its own output while its window spans both.
                assert command(f"move {wid} {output['x'] - 400} 10")["ok"]
                until(lambda: dimensions(120), "spanning cursor test window")
                for x, scale in ((output["x"] - 300, 120), (output["x"] + 100, 240)):
                    assert command(f"pointer {x} 310")["ok"]
                    expected = ((19 * effective_scale(scale) + 60) // 120,
                                (17 * effective_scale(scale) + 60) // 120)
                    try:
                        state = until(lambda: (s if (s := command("cursor-state")).get("buffer_width") == expected[0]
                            and s.get("buffer_height") == expected[1] else None), "independent mixed-output cursor")
                    except AssertionError:
                        (artifacts / "cursor-failure.json").write_text(json.dumps(dict(
                            cursor=command("cursor-state"), outputs=command("outputs"), window=window(), pointer_x=x, expected=expected), indent=2))
                        raise
                    assert dimensions(120), "Cursor output changed the window backing"
                    cursor_results.append(dict(pointer_x=x, cursor=state))
                assert command(f"move {wid} {output['x'] + 10} 10")["ok"]
                assert command(f"pointer {output['x'] + 210} 310")["ok"]
                cursor_key(8)  # Hide; density changes must not reveal it.
                until(lambda: not command("cursor-state")["visible"], "cursor hide")
                assert command(f"test-scale {target} 180 10000")["ok"]
                assert command("confirm")["ok"]
                until(lambda: dimensions(180), "hidden cursor scale")
                assert not command("cursor-state")["visible"]
                cursor_key(9)
                until(lambda: command("cursor-state")["visible"], "cursor unhide")
                cursor_key(11)
                arrow = until(lambda: (s if (s := command("cursor-state")).get("width") not in (None, 19)
                    else None), "restore themed arrow")
                for scale in (120, 150, 180, 210, 240, 180):
                    assert command(f"test-scale {target} {scale} 10000")["ok"]
                    assert command("confirm")["ok"]
                    until(lambda: dimensions(scale), "themed cursor output scale")
                    state = until(lambda: (s if (s := command("cursor-state")).get("buffer_width", 0) >=
                        arrow["width"] * effective_scale(scale) / 120 else None), "themed cursor density")
                    assert tuple(state[k] for k in ("width", "height", "hotspot_x", "hotspot_y")) == tuple(
                        arrow[k] for k in ("width", "height", "hotspot_x", "hotspot_y")), state
                    cursor_results.append(dict(scale=scale, themed_cursor=state))
                (artifacts / "cursors.json").write_text(json.dumps(cursor_results, indent=2) + "\n")
                # Keep the special-key assertions independent of cursor controls.
                cursor_event_count = len([e for e in events() if e["event"] == "key"])
                if protocol_mode == "native":
                    assert command(f"focus {wid}")["ok"]
                    def key(code, pressed):
                        assert command(f"key {code} {int(pressed)}")["ok"]

                    for code in (28, 14, 103, 105, 106, 108, 102, 107, 104, 109, 111, 59, 1):
                        key(code, True); key(code, False)
                    expected = [13, 127, 0xF700, 0xF702, 0xF703, 0xF701, 0xF729,
                                0xF72B, 0xF72C, 0xF72D, 0xF728, 0xF704, 27]
                    until(lambda: len([e for e in events() if e["event"] == "key"]) >= cursor_event_count + len(expected),
                          "native special keys")
                    assert [e["character"] for e in events() if e["event"] == "key"][cursor_event_count:] == expected
                    key(42, True); key(30, True); key(30, False); key(42, False)
                    until(lambda: any(e["event"] == "key" and e["character"] == 65 and
                                      e["modifiers"] & (1 << 17) for e in events()), "shifted UTF-8 key")
                    key(29, True); key(46, True); key(46, False); key(29, False)
                    until(lambda: any(e["event"] == "key" and e["character"] == 3 and e["plain"] == 99 and
                                      e["modifiers"] & (1 << 18) for e in events()), "control modifier mapping")
                    key(30, True)
                    until(lambda: len([e for e in events() if e["event"] == "key" and e["repeat"]]) >= 3,
                          "native keyboard repeat")
                    key(30, False)
                    time.sleep(0.1)  # Drain events generated before the release.
                    count = len([e for e in events() if e["event"] == "key"])
                    time.sleep(0.2)
                    assert len([e for e in events() if e["event"] == "key"]) == count, "Repeat continued after release"
                    # A compositor move must update the AppKit frame, not only pixels.
                    until(lambda: any(e["event"] == "move" and e["x"] == output["x"] + 10
                                      and e["y"] == 589 for e in events()), "authoritative AppKit position")
                    def by_id():
                        return next(w for w in command("windows") if w["id"] == wid)

                    assert command(f"resize {wid} 800 600")["ok"]
                    until(lambda: (by_id()["width"], by_id()["height"]) == (800, 600), "configure resize")
                    # Test the two sides of the largest-area decision, then an exact tie.
                    for offset, width in ((-399, 1200), (-401, 800)):
                        assert command(f"move {wid} {output['x'] + offset} 10")["ok"]
                        until(lambda: by_id()["buffer_width"] == width, "spanning output preference")
                    assert command(f"move {wid} {output['x'] - 400} 10")["ok"]
                    tie_scale = by_id()["preferred_scale"]
                    assert tie_scale in (120, 180)
                    tie_width = 800 * tie_scale // 120
                    until(lambda: by_id()["buffer_width"] == tie_width, "initial tie render")
                    for x in (origin["x"] + 10, output["x"] + 10):
                        assert command(f"move {wid} {x} 10")["ok"]
                        width = 800 if x == origin["x"] + 10 else 1200
                        until(lambda: by_id()["buffer_width"] == width, "fully moved before tie")
                        assert command(f"move {wid} {output['x'] - 400} 10")["ok"]
                        assert by_id()["preferred_scale"] == tie_scale, "Tie policy changed with movement history"
                        until(lambda: by_id()["buffer_width"] == tie_width, "stable tie policy")
                    assert command(f"resize {wid} 801 601")["ok"]
                    assert command(f"move {wid} {output['x'] + 10} 10")["ok"]
                    until(lambda: dimensions(180), "restored size after spanning tests")
                    place = next(e for e in events() if e["event"] == "placement-button")
                    assert command(f"pointer {output['x'] + 10 + int(place['x'])} {611 - int(place['y'])}")["ok"]
                    assert command("button 272")["ok"]
                    until(lambda: any(e["event"] == "placement-request" for e in events()), "application placement request")
                    until(lambda: window()["y"] == 0, "application placement response")
                    placed = window()
                    assert any(o["x"] <= placed["x"] < o["x"] + o["width"] for o in command("outputs")), placed
                    # Open a real AppKit popup near the physical output's right edge.
                    parent_x = output["x"] + output["width"] - 811
                    assert command(f"move {wid} {parent_x} 10")["ok"]
                    if registry_probe:
                        with (artifacts / "popup-occluder.log").open("w") as log:
                            occluder = subprocess.Popen([registry_probe, "--window", "FloatingPopupOccluder", "2"],
                                env=env, stdout=log, stderr=log)
                        occluder_window = until(lambda: next((w for w in command("windows")
                            if w["title"] == "FloatingPopupOccluder"), None), "floating popup occluder")
                        assert command(f"move {occluder_window['id']} 0 0")["ok"]
                        assert command(f"focus {wid}")["ok"]
                    button = next(e for e in events() if e["event"] == "popup-button")
                    assert command(f"pointer {parent_x + int(button['x'])} {611 - int(button['y'])}")["ok"]
                    assert command("button 272")["ok"]

                    def popup():
                        return next(iter(command("popups")), None)

                    def ready_popup():
                        p = popup()
                        return p if p and p["buffer_width"] == 300 else None

                    p = until(ready_popup, "native fractional popup")
                    assert (p["width"], p["height"], p["buffer_height"]) == (200, 120, 180), p
                    assert output["x"] <= p["x"] <= output["x"] + output["width"] - p["width"], p
                    def popup_position_matches(p):
                        bottom = max(o["y"] + o["height"] for o in command("outputs"))
                        return any(e == dict(event="popup-move", x=p["x"], y=bottom - p["y"] - p["height"])
                                   for e in events())

                    until(lambda: popup_position_matches(p), "AppKit popup edge adjustment")
                    assert command(f"move {wid} {parent_x - 30} 50")["ok"]
                    moved_popup = until(lambda: popup() if popup()["x"] == p["x"] - 30 else None,
                                        "popup follows moved parent")
                    assert moved_popup["y"] == p["y"] + 40, moved_popup
                    until(lambda: popup_position_matches(moved_popup), "AppKit popup follows parent")
                    p = moved_popup
                    if occluder:
                        assert command(f"move {occluder_window['id']} {p['x'] + 70} {p['y'] + 60}")["ok"]
                        hit = command(f"hit {p['x'] + 95} {p['y'] + 85}")
                        assert hit == dict(id=wid, popup=True), "A document popup must stay above floating windows"
                    assert command(f"pointer {p['x'] + 95} {p['y'] + 85}")["ok"]
                    assert command("button 272")["ok"]
                    until(lambda: not command("popups"), "popup close")
                    if occluder:
                        occluder.terminate(); occluder.wait(timeout=5)
                        occluder = None
                    # Dynamic output metadata may arrive after preferred-output.
                    for _ in range(3):
                        before = {o["name"] for o in command("outputs")}
                        assert command("add-output")["ok"]
                        added = next(o for o in command("outputs") if o["name"] not in before)
                        assert command(f"test-scale {added['name']} 210 10000")["ok"]
                        assert command("confirm")["ok"]
                        added = next(o for o in command("outputs") if o["name"] == added["name"])
                        assert command(f"move {wid} {added['x'] + 10} {added['y'] + 10}")["ok"]
                        until(lambda: dimensions(210), "new output native redraw")
                        until(lambda: any(e["event"] == "screen" and e["x"] == added["x"] for e in events()),
                              "AppKit screen transition to added output")
                        screen_events = len([e for e in events() if e["event"] == "screen"])
                        assert command(f"test-scale {added['name']} 240 10000")["ok"]
                        assert command(f"remove-output {added['name']}")["ok"]
                        assert not command("confirm")["ok"], "Removed output retained pending settings"
                        until(lambda: by_id()["x"] != added["x"] + 10, "window recovered from removed output")
                        until(lambda: len([e for e in events() if e["event"] == "screen"]) > screen_events,
                              "AppKit screen notification after unplug")
                        assert command(f"move {wid} {output['x'] + 10} 10")["ok"]
                        until(lambda: dimensions(180), "original output after hotplug")
                if protocol_mode == "native":
                    assert command(f"focus {wid}")["ok"]
                    assert command(f"pointer {output['x'] + 210} 310")["ok"]
                    assert command("button 272")["ok"]
                    key(34, True); key(34, False)
                    until(lambda: any(e["event"] == "grid-enabled" for e in events()), "logical cell grid enabled")
                    assert command(f"resize {wid} 329 283")["ok"]
                    until(lambda: (by_id()["width"], by_id()["height"]) == (324, 270), "cell-aligned configure response")
                    assert (by_id()["buffer_width"], by_id()["buffer_height"]) == (486, 405)
                    key(49, True); key(49, False)
                    until(lambda: any(e["event"] == "grid-disabled" for e in events()), "cell grid disabled")
                    assert command(f"resize {wid} 801 601")["ok"]
                    until(lambda: dimensions(180), "restored geometry after grid test")
                    def click_fixture(event):
                        point = next(e for e in events() if e["event"] == event)
                        w = by_id()
                        assert command(f"pointer {w['x'] + int(point['x'])} {w['y'] + w['height'] - int(point['y'])}")["ok"]
                        assert command("button 272")["ok"]

                    click_fixture("show-menu")
                    def named_window(title):
                        return next((w for w in command("windows") if w["title"] == title and w["visible"]), None)

                    menu = until(lambda: named_window("Wayland detached menu"), "native detached menu")
                    assert not menu["accepts_focus"] and by_id()["focused"], menu
                    item = next(e for e in events() if e["event"] == "menu-item")
                    assert command(f"pointer {menu['x'] + int(item['x'])} {menu['y'] + menu['height'] - int(item['y'])}")["ok"]
                    assert command("button 272")["ok"]
                    until(lambda: any(e["event"] == "menu-action" for e in events()), "detached menu action")
                    assert by_id()["focused"], "Menu stole document keyboard focus"
                    click_fixture("show-modal")
                    panel = until(lambda: named_window("Wayland modal panel"), "native modal panel")
                    until(lambda: named_window("Wayland modal panel")["focused"], "modal keyboard focus")
                    item = next(e for e in events() if e["event"] == "modal-button")
                    assert command(f"pointer {panel['x'] + int(item['x'])} {panel['y'] + panel['height'] - int(item['y'])}")["ok"]
                    assert command("button 272")["ok"]
                    until(lambda: any(e["event"] == "modal-finished" for e in events()), "modal run loop completion")
                    until(lambda: by_id()["focused"], "document focus after modal closes")
                    click_fixture("show-nested")
                    menu = until(lambda: named_window("Wayland nested menu"), "nested menu root")
                    until(lambda: len([e for e in events() if e["event"] == "nested-item"]) == 3,
                          "nested menu item coordinates")
                    items = sorted((e for e in events() if e["event"] == "nested-item"), key=lambda e: e["depth"])
                    try:
                        for depth, item in enumerate(items):
                            assert command(f"pointer {menu['x'] + int(item['x'])} {menu['y'] + menu['height'] - int(item['y'])}")["ok"]
                            if depth == 0:
                                assert command("button 272 1")["ok"]
                            if depth < 2:
                                popups = until(lambda: (p if len(p := command("popups")) == depth + 1 else None),
                                               f"nested menu depth {depth + 1}")
                                menu = popups[0]
                            assert by_id()["focused"], "Nested menu stole document keyboard focus"
                        until(lambda: any(e["event"] == "nested-leaf-highlight" for e in events()),
                              "nested leaf highlighted before release")
                    finally:
                        assert command("button 272 0")["ok"]
                    until(lambda: any(e["event"] == "nested-menu-action" for e in events()), "nested menu action")
                    until(lambda: not command("popups") and not named_window("Wayland nested menu"),
                          "nested menus close in order")
                    mini_results = []
                    image_point = next(e for e in events() if e["event"] == "image-point")
                    def image_button_at_scale(scale):
                        path = artifacts / f"window-{pattern['window']}-{scale}.png"
                        try:
                            with Image.open(path) as image:
                                return image.convert("RGB").getpixel((round(image_point["x"] * scale / 120),
                                    round((601 - image_point["y"]) * scale / 120))) == (255, 0, 0)
                        except OSError:
                            return False
                    mini_button = next(e for e in events() if e["event"] == "minimize")
                    for scale, restored_scale in zip((120, 150, 180, 210, 240), (150, 180, 210, 240, 120)):
                        assert command(f"test-scale {target} {scale} 10000")["ok"]
                        assert command("confirm")["ok"]
                        assert command(f"move {wid} {output['x'] + 10} 10")["ok"]
                        until(lambda: dimensions(scale), "document density before miniaturization")
                        before = len([e for e in events() if e["event"] == "mini-state"])
                        handled = len([e for e in events() if e["event"] == "mouse-handled"])
                        w = by_id()
                        assert command(f"pointer {w['x'] + int(mini_button['x'])} {w['y'] + w['height'] - int(mini_button['y'])}")["ok"]
                        assert command("button 272")["ok"]
                        until(lambda: by_id()["minimized"] and not by_id()["focused"], "native miniaturization")
                        until(lambda: len([e for e in events() if e["event"] == "mini-state"]) > before and
                              [e for e in events() if e["event"] == "mini-state"][-1]["minimized"],
                              "AppKit miniaturized state")
                        until(lambda: len([e for e in events() if e["event"] == "mouse-handled"]) > handled,
                              "miniaturize button finishes tracking before restoration")
                        assert command(f"hit {w['x'] + 400} {w['y'] + 300}")["id"] != wid
                        assert command(f"test-scale {target} {restored_scale} 10000")["ok"]
                        assert command("confirm")["ok"]
                        assert command(f"minimize {wid} 0")["ok"]
                        until(lambda: len([e for e in events() if e["event"] == "mini-state"]) >= before + 2 and
                              not [e for e in events() if e["event"] == "mini-state"][-1]["minimized"],
                              "AppKit restored state")
                        until(lambda: dimensions(restored_scale), "native density after restoring retained window")
                        until(lambda: image_button_at_scale(restored_scale), "retained image button redraws after restoring")
                        assert command(f"focus {wid}")["ok"]
                        mini_results.append(dict(scale=scale, restored_scale=restored_scale, window=by_id()))
                    (artifacts / "miniaturization.json").write_text(json.dumps(mini_results, indent=2) + "\n")
                    assert [e["minimized"] for e in events() if e["event"] == "mini-notification"] == [True, False] * 5
                    assert command(f"test-scale {target} 180 10000")["ok"]
                    assert command("confirm")["ok"]
                    until(lambda: dimensions(180), "document restored after miniaturization matrix")
                    shade_results = []
                    for scale in (120, 150, 180, 210, 240):
                        assert command(f"test-scale {target} {scale} 10000")["ok"]
                        assert command("confirm")["ok"]
                        assert command(f"move {wid} {output['x'] + 10} 10")["ok"]
                        until(lambda: dimensions(scale), "density before shading")
                        w = by_id()
                        assert w["client_id"] == pattern["window"] and w["title_height"] > 0, w
                        assert command(f"pointer {w['x'] + 400} {w['y'] + 300}")["ok"]
                        assert command(f"shade {wid} 1")["ok"]
                        assert by_id()["shaded"] and dimensions(scale)
                        assert command(f"hit {w['x'] + 400} {w['y'] + 5}")["id"] == wid
                        assert command(f"hit {w['x'] + 400} {w['y'] + 300}")["id"] != wid
                        assert command("pointer-focus")["id"] != wid
                        assert command(f"shade {wid} 0")["ok"]
                        assert not by_id()["shaded"] and dimensions(scale)
                        assert command(f"hit {w['x'] + 400} {w['y'] + 300}")["id"] == wid
                        assert command("pointer-focus")["id"] == wid
                        until(lambda: image_button_at_scale(scale), "retained content after unshading")
                        shade_results.append(dict(scale=scale, window=by_id()))
                    (artifacts / "shading.json").write_text(json.dumps(shade_results, indent=2) + "\n")
                    assert command(f"test-scale {target} 180 10000")["ok"]
                    assert command("confirm")["ok"]
                    until(lambda: dimensions(180), "document restored after shading matrix")
                if registry_probe and pasteboard_probe:
                    with (artifacts / "services.log").open("w") as log:
                        subprocess.run([pasteboard_probe, "--service", "-GSBackend", "libgnustep-wayland",
                                        "-GSTheme", "NextSpace"], env=env, stdout=log, stderr=log, check=True, timeout=10)
                    until(lambda: any(e["event"] == "service" for e in events()), "native Services round trip")
                    # Copy in AppKit, then read using an independent protocol client.
                    assert command(f"focus {wid}")["ok"]
                    assert command(f"pointer {output['x'] + 210} 310")["ok"]
                    assert command("button 272")["ok"]
                    previous_selection = command("selection-state")["serial"]
                    copies = sum(e["event"] == "clipboard-copy" for e in events())
                    key(46, True); key(46, False)
                    until(lambda: sum(e["event"] == "clipboard-copy" for e in events()) > copies, "native clipboard copy")
                    until(lambda: command("selection-state")["serial"] != previous_selection and
                          "org.nextspace.test.binary" in command("selection"), "new native clipboard offer")
                    (artifacts / "native-copy-publication.json").write_text(json.dumps(dict(
                        previous_serial=previous_selection, selection=command("selection-state"),
                        mimes=command("selection")), indent=2) + "\n")
                    copied = artifacts / "native-copy.txt"
                    expected = "Native:日本語\n" + "clipboard:日本語\n" * 6000
                    with (artifacts / "clipboard-reader.log").open("w") as log:
                        reader = subprocess.Popen([registry_probe, "--clipboard-read", str(copied)], env=env, stdout=log, stderr=log)
                    try:
                        until(lambda: reader.poll() is not None, "independent clipboard read")
                        assert reader.returncode == 0
                        assert copied.read_text() == expected, "Native clipboard UTF-8 transfer changed"
                    finally:
                        if reader.poll() is None: reader.terminate(); reader.wait(timeout=5)
                    external = artifacts / "external-copy.txt"
                    external.write_text("External:日本語\n" * 6000)
                    @contextmanager
                    def protocol_source(mode, path, logname):
                        previous = {w["id"] for w in command("windows")}
                        with (artifacts / logname).open("w") as log:
                            writer = subprocess.Popen([registry_probe, mode, str(path)], env=env, stdout=log, stderr=log)
                        try:
                            def clipboard_window():
                                assert writer.poll() is None, "Protocol source exited before mapping"
                                return next((w for w in command("windows") if w["title"] == "ClipboardProbe"
                                             and w["id"] not in previous), None)
                            yield writer, until(clipboard_window, "independent clipboard source")
                        except BaseException:
                            try:
                                (artifacts / (logname + ".failure.json")).write_text(json.dumps(dict(
                                    windows=command("windows"), move=command("move-state"),
                                    drag=command("drag-state"), selection=command("selection-state"),
                                    source_exit=writer.poll()), indent=2) + "\n")
                            except (OSError, ValueError):
                                pass
                            raise
                        finally:
                            if writer.poll() is None:
                                writer.terminate(); writer.wait(timeout=5)

                    with protocol_source("--clipboard-write", external, "clipboard-writer.log") as (writer, cw):
                        assert command(f"focus {cw['id']}")["ok"]
                        key(57, True); key(57, False)
                        until(lambda: "Clipboard source set" in (artifacts / "clipboard-writer.log").read_text(), "external source selection")
                        assert command(f"focus {wid}")["ok"]
                        until(lambda: subprocess.run([pasteboard_probe, "--text-file", str(external)], env=env).returncode == 0,
                              "external clipboard imported into GNUstep storage")
                        until(lambda: command("selection-state")["owned"], "compositor clipboard snapshot")
                    subprocess.run([pasteboard_probe, "--text-file", str(external)], env=env, check=True)
                    persisted = artifacts / "clipboard-after-owner-exit.txt"
                    subprocess.run([registry_probe, "--clipboard-read", str(persisted)], env=env, check=True, timeout=10)
                    assert persisted.read_bytes() == external.read_bytes(), "Selection disappeared with its producer"
                    with protocol_source("--clipboard-stall", external, "clipboard-stall.log") as (writer, cw):
                        assert command(f"focus {cw['id']}")["ok"]
                        # Queue enter/leave while AppKit cannot consume them.
                        # Stale focus events must not reactivate the native app,
                        # and expired selection offers must not empty storage.
                        previous_events = len(events())
                        client.send_signal(signal.SIGSTOP)
                        try:
                            assert os.WIFSTOPPED(os.waitpid(client.pid, os.WUNTRACED)[1])
                            for _ in range(3):
                                assert command(f"focus {wid}")["ok"]
                                assert command(f"focus {cw['id']}")["ok"]
                        finally:
                            client.send_signal(signal.SIGCONT)
                        assert command(f"test-scale {target} 210 10000")["ok"]
                        assert command("confirm")["ok"]
                        until(lambda: dimensions(210), "native redraw after queued focus changes")
                        if effective_scale(210) != effective_scale(180):
                            until(lambda: any(e["event"] == "scale" and e["scale"] == effective_scale(210) / 120
                                             for e in events()[previous_events:]), "native event loop after focus changes")
                        assert next(w for w in command("windows") if w["id"] == cw["id"])["focused"], \
                            "Queued native focus events reactivated an unfocused window"
                        subprocess.run([pasteboard_probe, "--text-file", str(external)], env=env, check=True)
                        (artifacts / "focus-lifecycle.json").write_text(json.dumps(dict(
                            queued_transitions=6, focused=cw["id"], native=wid,
                            clipboard_preserved=True), indent=2) + "\n")
                        assert command(f"test-scale {target} 180 10000")["ok"]
                        assert command("confirm")["ok"]
                        until(lambda: dimensions(180), "density after queued focus changes")
                        key(1, True); key(1, False)
                        until(lambda: "Clipboard source cleared" in (artifacts / "clipboard-stall.log").read_text(),
                              "explicit clipboard clear")
                        until(lambda: not command("selection"), "cleared compositor clipboard")
                        assert command(f"focus {wid}")["ok"]
                        until(lambda: subprocess.run([pasteboard_probe, "--empty"], env=env).returncode == 0,
                              "external clipboard clear reaches GNUstep storage")
                        assert command(f"focus {cw['id']}")["ok"]
                        key(57, True); key(57, False)
                        until(lambda: command("selection-state")["pending"], "stalled clipboard capture")
                        assert command(f"test-scale {target} 210 10000")["ok"]
                        assert command("confirm")["ok"]
                        until(lambda: dimensions(210), "UI redraw during stalled clipboard capture")
                        until(lambda: not command("selection-state")["pending"], "clipboard capture deadline")
                        state = command("selection-state")
                        assert not state["owned"] and state["bytes"] == 0 and writer.poll() is None, state
                        (artifacts / "clipboard-timeout.json").write_text(json.dumps(state, indent=2) + "\n")
                    assert command(f"test-scale {target} 180 10000")["ok"]
                    assert command("confirm")["ok"]
                    until(lambda: dimensions(180), "density after stalled clipboard source")
                for toolkit, executable in comparators:
                    toolkit_env = dict(env, GDK_BACKEND="wayland", GSK_RENDERER="cairo", GTK_A11Y="none",
                                       QT_QPA_PLATFORM="wayland", QT_QUICK_BACKEND="software")
                    path = artifacts / f"{toolkit}.log"
                    with path.open("w") as log, (artifacts / f"{toolkit}-errors.log").open("w") as errors:
                        # Allocate GTK's menu button before opening the popover.
                        args = [executable, "--popup-controls"] if toolkit == "GtkProbe" else [executable]
                        comparator = subprocess.Popen(args, env=toolkit_env, stdout=log, stderr=errors)
                    try:
                        def comparator_events(event):
                            return [row for row in read_json_lines(path) if row["event"] == event]

                        def comparator_key(code, control=False):
                            keys = [(code, 1), (code, 0)]
                            if control: keys = [(29, 1), *keys, (29, 0)]
                            for key_code, pressed in keys:
                                assert command(f"key {key_code} {pressed}")["ok"]

                        def comparator_window():
                            return next((w for w in command("windows") if w["title"] == toolkit), None)
                        def comparator_popup_trial(bounds, x, y, dx, dy):
                            assert command(f"move {cid} {x} {y}")["ok"]
                            parent = comparator_window()
                            assert (parent["x"], parent["y"]) == (x, y), parent
                            assert command(f"focus {cid}")["ok"]
                            activations = len(comparator_events("popup-activate"))
                            comparator_key(25)  # p: open the toolkit's native popup.

                            def comparator_popup():
                                popups = command("popups")
                                if len(popups) != 1: return None
                                popup = popups[0]
                                if (popup["width"], popup["height"]) != (200, 120): return None
                                expected = tuple((popup[n] * scale + 60) // 120 for n in ("width", "height"))
                                return popup if (popup["buffer_width"], popup["buffer_height"]) == expected else None

                            popup = until(comparator_popup, f"{toolkit} native popup at {scale}/120")
                            assert bounds["x"] <= popup["x"] <= bounds["x"] + bounds["width"] - popup["width"], popup
                            assert bounds["y"] <= popup["y"] <= bounds["y"] + bounds["height"] - popup["height"], popup
                            assert command(f"move {cid} {x + dx} {y + dy}")["ok"]
                            moved = until(lambda: next((p for p in command("popups") if
                                (p["x"], p["y"]) == (popup["x"] + dx, popup["y"] + dy)), None),
                                f"{toolkit} popup follows its parent")
                            px, py = moved["x"] + moved["width"] // 2, moved["y"] + moved["height"] // 2
                            assert command(f"hit {px} {py}") == dict(id=cid, popup=True)
                            assert command(f"pointer {px} {py}")["ok"]
                            assert command("button 272")["ok"]
                            until(lambda: len(comparator_events("popup-activate")) == activations + 1,
                                  f"{toolkit} popup action")
                            until(lambda: not command("popups"), f"{toolkit} popup cleanup")
                            return dict(parent=parent, output=bounds, initial=popup, moved=moved, action_activated=True)

                        cw = until(comparator_window, f"{toolkit} native window")
                        cid = cw["id"]
                        for scale in (120, 150, 180, 210, 240):
                            assert command(f"test-scale {target} {scale} 10000")["ok"]
                            assert command("confirm")["ok"]
                            assert command(f"move {cid} {output['x'] + 10} 10")["ok"]
                            def comparator_dimensions():
                                cw = comparator_window()
                                return cw if cw and (cw["width"], cw["height"], cw["buffer_width"], cw["buffer_height"]) == (
                                    801, 601, (801 * scale + 60) // 120, (601 * scale + 60) // 120) else None
                            cw = until(comparator_dimensions, f"{toolkit} native {scale}/120 buffer")
                            assert not cw["legacy"], cw
                            assert command(f"pointer {cw['x'] + 200} {cw['y'] + 300}")["ok"]
                            assert command("button 272")["ok"]
                            trial = dict(toolkit=toolkit, scale=scale, window=cw)
                            if registry_probe and pasteboard_probe:
                                # A distinct offer per density prevents stale data from passing.
                                copy_count = (120, 150, 180, 210, 240).index(scale) + 1
                                text = (f"{toolkit}:{copy_count}:日本語\n" * 4096).encode()
                                expected_file = artifacts / f"{toolkit}-clipboard-{scale}.txt"
                                expected_file.write_bytes(text)
                                previous_serial = command("selection-state")["serial"]
                                assert command(f"focus {cid}")["ok"]
                                comparator_key(46, control=True)
                                until(lambda: any(row["count"] == copy_count for row in
                                    comparator_events("clipboard-copy")), f"{toolkit} clipboard copy")
                                until(lambda: command("selection-state")["serial"] != previous_serial,
                                      f"{toolkit} fresh clipboard offer")
                                assert command(f"focus {wid}")["ok"]
                                until(lambda: subprocess.run([pasteboard_probe, "--text-file", str(expected_file)],
                                    env=env, capture_output=True).returncode == 0,
                                    f"{toolkit} clipboard imported into AppKit")

                                previous_serial = command("selection-state")["serial"]
                                copies = sum(e["event"] == "clipboard-copy" for e in events())
                                comparator_key(46)
                                until(lambda: sum(e["event"] == "clipboard-copy" for e in events()) > copies,
                                      "native clipboard copy for comparator")
                                until(lambda: command("selection-state")["serial"] != previous_serial and
                                    "org.nextspace.test.binary" in command("selection"), "fresh AppKit clipboard offer")
                                assert command(f"focus {cid}")["ok"]
                                pastes = len(comparator_events("clipboard-paste"))
                                comparator_key(47, control=True)
                                until(lambda: len(comparator_events("clipboard-paste")) > pastes,
                                      f"AppKit clipboard pasted in {toolkit}")
                                pasted = base64.b64decode(comparator_events("clipboard-paste")[-1]["base64"], validate=True)
                                assert pasted == (artifacts / "native-copy.txt").read_bytes(), f"{toolkit} changed clipboard bytes"
                                trial["clipboard"] = dict(to_native_bytes=len(text), from_native_bytes=len(pasted))
                            current_output = next(o for o in command("outputs") if o["name"] == target)
                            edge_x = current_output["x"] + max(0, current_output["width"] - cw["width"])
                            edge_y = current_output["y"] + max(0, current_output["height"] - cw["height"])
                            trial["popup"] = comparator_popup_trial(current_output, edge_x, edge_y, -20, -20)
                            # Keep the menu-bearing edge visible while the parent center is off-screen.
                            left = min(command("outputs"), key=lambda o: o["x"])
                            previous_scale = left["scale"]
                            assert command(f"test-scale {left['name']} {scale} 10000")["ok"]
                            assert command("confirm")["ok"]
                            heads = command("outputs")
                            left = next(o for o in heads if o["name"] == left["name"])
                            partial = comparator_popup_trial(left, left["x"] - 700,
                                left["y"] + max(0, left["height"] - cw["height"]), 20, -20)
                            parent = partial["parent"]
                            cx, cy = parent["x"] + parent["width"] / 2, parent["y"] + parent["height"] / 2
                            assert not any(o["x"] <= cx < o["x"] + o["width"] and o["y"] <= cy < o["y"] + o["height"] for o in heads)
                            assert parent["x"] < left["x"] < parent["x"] + parent["width"]
                            trial["partial_parent_popup"] = partial
                            assert command(f"test-scale {left['name']} {previous_scale} 10000")["ok"]
                            assert command("confirm")["ok"]
                            results.append(trial)
                            assert command(f"move {cid} 10 10")["ok"]
                        until(lambda: len(comparator_events("click")) >= 5, f"{toolkit} logical clicks")
                        assert comparator_events("click") == [
                            dict(event="click", x=200, y=300)] * 5
                        assert command(f"close {cid}")["ok"]
                        until(lambda: comparator.poll() is not None, f"{toolkit} close")
                        assert comparator.returncode == 0
                    except BaseException:
                        diagnostic = dict(windows=command("windows"), popups=command("popups"),
                                          outputs=command("outputs"), exit_code=comparator.poll())
                        for name in ("status", "wchan"):
                            try:
                                diagnostic[name] = Path(f"/proc/{comparator.pid}/{name}").read_text()
                            except OSError:
                                pass
                        (artifacts / f"{toolkit}-failure.json").write_text(json.dumps(diagnostic, indent=2) + "\n")
                        raise
                    finally:
                        if comparator.poll() is None: comparator.terminate(); comparator.wait(timeout=5)
                    assert command(f"test-scale {target} 180 10000")["ok"]
                    assert command("confirm")["ok"]
                    output = next(o for o in command("outputs") if o["name"] == target)
                    assert command(f"move {wid} {output['x'] + 10} {output['y'] + 10}")["ok"]
                    try:
                        until(lambda: dimensions(180), "GNUstep density restored after comparator")
                    except BaseException:
                        (artifacts / f"{toolkit}-restore-failure.json").write_text(json.dumps(dict(
                            windows=command("windows"), outputs=command("outputs")), indent=2) + "\n")
                        raise
                if applications:
                    results.extend(run_applications(command, env, artifacts, applications, until))
                    # Application trials can change either output's geometry.
                    output = next(o for o in command("outputs") if o["name"] == target)
                    assert command(f"move {wid} {output['x'] + 10} {output['y'] + 10}")["ok"]
                    until(lambda: dimensions(180), "GNUstep fixture after real application trials")
                if workspace_probe:
                    run_session(workspace_probe, env, artifacts)
                if protocol_mode == "native":
                    def resources():
                        process = Path(f"/proc/{client.pid}")
                        return dict(fds=len(list((process / "fd").iterdir())),
                                    shm=sum("memfd:nextspace-buffer" in line for line in (process / "maps").read_text().splitlines()))
                    before = resources()
                    for _ in range(32):
                        assert command(f"move {wid} 10 10")["ok"]
                        until(lambda: dimensions(120), "stress move to 100%")
                        assert command(f"move {wid} {output['x'] + 10} 10")["ok"]
                        until(lambda: dimensions(180), "stress move to 150%")
                    until(lambda: resources()["shm"] <= before["shm"] + 3, "retired shm mappings released")
                    after = resources()
                    assert after["fds"] <= before["fds"] + 1, (before, after)
                    (artifacts / "resources.json").write_text(json.dumps(dict(before=before, after=after, transitions=64), indent=2) + "\n")
                    with (artifacts / "close-on-scale.log").open("w") as log, (artifacts / "close-on-scale-errors.log").open("w") as errors:
                        close_captures = artifacts / "close-on-scale"
                        close_captures.mkdir(exist_ok=True)
                        close_env = dict(env, NEXTSPACE_WAYLAND_CAPTURE_DIR=str(close_captures.resolve()))
                        closer = subprocess.Popen([probe, "-GSBackend", "libgnustep-wayland", "-GSTheme", "NextSpace",
                                                   "-CloseOnScale", "YES", "-NSUseRunningCopy", "NO"], env=close_env, stdout=log, stderr=errors)
                    try:
                        def close_window():
                            return next((w for w in command("windows") if w["title"] == "WaylandCloseProbe" and w["width"] == 801), None)
                        cw = until(close_window, "close-on-scale fixture")
                        assert command(f"move {cw['id']} {output['x'] + 10} 10")["ok"]
                        until(lambda: close_window()["buffer_width"] == 1202, "close fixture on 150% output")
                        assert command(f"test-scale {target} 240 10000")["ok"]
                        assert command("confirm")["ok"]
                        until(lambda: closer.poll() is not None, "close during backing callback")
                        assert closer.returncode == 0
                        assert '"event":"closed-during-scale"' in (artifacts / "close-on-scale.log").read_text()
                        assert not close_window()
                    finally:
                        if closer.poll() is None: closer.terminate(); closer.wait(timeout=5)
                    assert command(f"test-scale {target} 180 10000")["ok"]
                    assert command("confirm")["ok"]
                    until(lambda: dimensions(180), "main window after another window closes during scaling")
                if primary_selection:
                    from primary_selection import check
                    check(command, env, registry_probe, pasteboard_probe, artifacts, wid, target, dimensions,
                          protocol_source, key, events, expected)
                (artifacts / "results.json").write_text(json.dumps(results, indent=2) + "\n")
                if protocol_mode == "native":
                    if registry_probe and pasteboard_probe:
                        previous_selection = command("selection-state")["serial"]
                        w = window()
                        assert command(f"focus {wid}")["ok"]
                        assert command(f"pointer {w['x'] + 200} {w['y'] + 300}")["ok"]
                        assert command("button 272")["ok"]
                        key(46, True); key(46, False)
                        until(lambda: command("selection-state")["serial"] != previous_selection and
                              command("selection-state")["owned"], "native clipboard retained before exit")
                    assert command(f"test-scale {target} 240 10000")["ok"]
                    until(lambda: dimensions(240), "unconfirmed settings before controller failure")
                    until(lambda: next((e["scale"] for e in reversed(events()) if e["event"] == "scale"), None) == 2,
                          "unconfirmed backing notification before controller failure")
                    rollback_start = len(events())
                    control.close()
                    until(lambda: any(e["event"] == "scale" and e["scale"] == 1.5 and e["roundtrip"]
                                      for e in events()[rollback_start:]), "rollback after controller disconnect")
                    assert server.poll() is None, "Controller failure killed the compositor"
                    if registry_probe and pasteboard_probe:
                        client.terminate(); client.wait(timeout=5)
                        persisted = artifacts / "native-clipboard-after-owner-exit.txt"
                        subprocess.run([registry_probe, "--clipboard-read", str(persisted)], env=env, check=True, timeout=10)
                        assert persisted.read_text() == expected
                        binary = artifacts / "native-binary-after-owner-exit.bin"
                        subprocess.run([registry_probe, "--clipboard-read", str(binary), "org.nextspace.test.binary"],
                                       env=env, check=True, timeout=10)
                        assert binary.read_bytes() == bytes((0, 1, 127, 128, 254, 255))
                else:
                    w = window()
                    close = next(e for e in events() if e["event"] == "close-button")
                    assert command(f"pointer {w['x'] + int(close['x'])} {w['y'] + 601 - int(close['y'])}")["ok"]
                    assert command("button 272")["ok"]
                    until(lambda: client.poll() is not None, "native window close")
                    assert client.returncode == 0, f"Native client exit: {client.returncode}"
                print(f"GNUstep {protocol_mode}: densities, repeated moves, logical input and timeout rollback PASS")
            finally:
                primary_failure = sys.exc_info()[1]
                cleanup_errors = []

                def cleanup(action):
                    try:
                        action()
                    except Exception as error:
                        cleanup_errors.append(error)

                def stop(process, name):
                    if process and process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            try:
                                capture_process_failure(process, artifacts, 'failure-' + name + '-shutdown')
                            finally:
                                process.kill(); process.wait(timeout=5)
                            raise

                if server.poll() is None and control.fileno() >= 0:
                    cleanup(lambda: (artifacts / "final-state.json").write_text(json.dumps(
                        dict(outputs=command("outputs"), windows=command("windows")), indent=2) + "\n"))
                if client:
                    (artifacts / "client-exit-before-cleanup.txt").write_text(str(client.poll()) + "\n")
                for process, name in ((client, 'client'), (occluder, 'occluder'), (storage, 'pasteboard')):
                    cleanup(lambda process=process, name=name: stop(process, name))
                if service_bundle:
                    cleanup(lambda: remove_service(service_bundle, env))
                if server.poll() is None:
                    if control.fileno() >= 0:
                        cleanup(lambda: command("quit"))
                    else:
                        server.terminate()
                    cleanup(lambda: server.wait(timeout=5))
                    cleanup(lambda: stop(server, 'compositor'))
                control.close()
                if cleanup_errors:
                    (artifacts / 'cleanup-errors.json').write_text(json.dumps(
                        [repr(error) for error in cleanup_errors], indent=2) + '\n')
                    if primary_failure is None:
                        raise cleanup_errors[0]
                if primary_failure is None:
                    assert server.returncode == 0, f"Compositor exit: {server.returncode}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--compositor", required=True)
    parser.add_argument("--probe", required=True)
    parser.add_argument("--artifacts", type=Path, default=Path("/tmp/nextspace-wayland-results"))
    parser.add_argument("--protocol-mode", choices=["native", "no-fractional", "no-viewporter", "no-placement",
                                                   "surface-v1", "surface-v1-no-viewporter"], default="native")
    parser.add_argument("--registry-probe")
    parser.add_argument("--pasteboard-probe")
    parser.add_argument("--pasteboard-server")
    parser.add_argument("--gtk-probe")
    parser.add_argument("--qt-probe")
    parser.add_argument("--terminal")
    parser.add_argument("--textedit")
    parser.add_argument("--review")
    parser.add_argument("--review-probe", help="Exercise Review's existing multipage and zoom controls through WorkspaceProbe")
    parser.add_argument("--timemon")
    parser.add_argument("--workspace-probe")
    parser.add_argument("--primary-selection", action="store_true")
    parser.add_argument("--server-frames", action="store_true", help="Require native server frames and inspect the actual cropped viewport and compositor title buffers")
    args = parser.parse_args()
    run(args.compositor, args.probe, args.artifacts, args.protocol_mode, args.registry_probe, args.pasteboard_probe, args.pasteboard_server,
        [(name, path) for name, path in (("GtkProbe", args.gtk_probe), ("QtProbe", args.qt_probe)) if path],
        dict(terminal=args.terminal, textedit=args.textedit, review=args.review, timemon=args.timemon,
             pasteboard=args.pasteboard_probe, review_probe=args.review_probe)
            if args.terminal or args.textedit or args.review or args.timemon else None, args.workspace_probe, args.primary_selection, args.server_frames)
