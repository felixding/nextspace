#!/usr/bin/env python3
"""Exercise native rendering through an already-running Workspace display service."""
import argparse
import json
import os
import re
from pathlib import Path
import subprocess
from PIL import Image
from integration import read_json_lines, until
from display_service import DisplayService


def run(probe, workspace_probe, artifacts, mode=None, zoom_application=None, fullscreen=False, window_number=None):
    artifacts.mkdir(parents=True)
    captures = artifacts / "captures"
    captures.mkdir(exist_ok=True)
    display = DisplayService(workspace_probe, artifacts / "request.json")
    query, request = display.query, display.request
    settings, preview, apply = display.settings, display.preview, display.apply

    initial = query("--display-state")
    assert not initial["pending"] and initial["heads"], initial
    original = initial["heads"]
    assert sum(bool(h["enabled"]) for h in original) == 1, "Use a single enabled output for this fixture"
    primary = next(h for h in original if h["primary"] and h["enabled"])
    chosen_mode = None
    if mode:
        width, height = map(int, mode.split("x"))
        chosen_mode = next(m for m in primary["modes"]
                           if (m["width"], m["height"]) == (width, height))
    zoom_window = None
    assert not fullscreen or zoom_application, "Fullscreen checks need --zoom-application"
    if zoom_application:
        zoom_window = window_number or query("--application-state", zoom_application)["window_number"]
        assert zoom_window, "Activate the selected application's document before starting the zoom check"

    def application(action=None):
        arguments = ["--application-action", zoom_application, action] if action else ["--application-state", zoom_application]
        return query(*arguments, "--window-number", str(zoom_window))

    def layout(scale, transform=None):
        proposal = [dict(h) for h in original]
        head = next(h for h in proposal if h["id"] == primary["id"])
        if chosen_mode:
            head.update({k: chosen_mode[k] for k in ("width", "height", "refresh")})
        head["scale"] = scale
        if transform is not None:
            head["transform"] = transform
        return proposal

    def restored():
        state = query("--display-state")
        return not state["pending"] and settings(state["heads"]) == settings(original)

    def zoom():
        before = application()
        toggled = False
        try:
            application("zoom")
            toggled = True
            def contained():
                state = application()
                frame = list(map(float, re.findall(r"-?\d+(?:\.\d+)?", state["frame"])))
                work = list(map(float, re.findall(r"-?\d+(?:\.\d+)?", state["visible_frame"])))
                return state if len(frame) == len(work) == 4 and state["zoomed"] != before["zoomed"] and (
                    frame[0] >= work[0] and frame[1] >= work[1] and
                    frame[0] + frame[2] <= work[0] + work[2] and
                    frame[1] + frame[3] <= work[1] + work[3]) else None
            state = until(contained, "native application zoom respects the logical work area")
        except BaseException:
            (artifacts / "zoom-failure.json").write_text(json.dumps(dict(before=before,
                current=application()), indent=2) + "\n")
            raise
        finally:
            if toggled:
                application("zoom")
                until(lambda: all(application()[key] == before[key] for key in ("frame", "zoomed")),
                      "native application zoom restores its floating frame")
        return dict(application=zoom_application, before=before, zoomed=state)

    def toggle_fullscreen():
        before = application()
        assert not before["style_mask"] & (1 << 14), before
        toggled = False
        try:
            application("fullscreen")
            toggled = True
            def filled():
                state = application()
                if not state["style_mask"] & (1 << 14): return None
                if state["frame"] != state["screen_frame"] or state["content_rect"] != state["frame"]: return None
                frame = list(map(float, re.findall(r"-?\d+(?:\.\d+)?", state["frame"])))
                bounds = list(map(float, re.findall(r"-?\d+(?:\.\d+)?", state["content_view_bounds"])))
                return state if bounds == [0, 0, frame[2], frame[3]] else None
            state = until(filled, "native application fullscreen fills its logical screen")
        except BaseException:
            (artifacts / "fullscreen-failure.json").write_text(json.dumps(dict(before=before,
                current=application()), indent=2) + "\n")
            raise
        finally:
            if toggled:
                application("fullscreen")
                keys = ("frame", "content_rect", "content_view_frame", "content_view_bounds", "style_mask", "zoomed")
                def recovered():
                    current = application()
                    return all(current[key] == before[key] for key in keys)
                until(recovered, "native application fullscreen restores its frame and content")
        return dict(application=zoom_application, before=before, fullscreen=state)

    client = None
    records = []
    rotations = []
    try:
        with (artifacts / "probe.log").open("w") as log:
            client = subprocess.Popen([probe, "-GSTheme", "NextSpace", "-NSUseRunningCopy", "NO"],
                env=dict(os.environ, NEXTSPACE_WAYLAND_CAPTURE_DIR=str(captures.resolve())), stdout=log, stderr=log)

        def events():
            assert client.poll() is None, f"Native client exited: {client.returncode}"
            return read_json_lines(artifacts / "probe.log", '{"event":')

        pattern = until(lambda: next((e for e in events() if e["event"] == "pixel-pattern"), None),
                        "native fixture maps on the live display")
        for scale in (120, 150, 180, 210, 240):
            state = apply(layout(scale))
            actual = next(h for h in state["heads"] if h["id"] == primary["id"])
            assert actual["scale"] == scale, actual
            if chosen_mode:
                assert all(actual[k] == chosen_mode[k] for k in ("width", "height", "refresh")), actual
            until(lambda: any(e["event"] == "scale" and abs(e["scale"] - scale / 120) < 0.001
                              and (e["width"], e["height"]) == (801, 601) and e["roundtrip"]
                              for e in events()), "stable logical geometry at the live display density")
            path = captures / f"window-{pattern['window']}-{scale}.png"

            def rendered():
                try:
                    with Image.open(path) as image:
                        return image.size == ((801 * scale + 60) // 120, (601 * scale + 60) // 120)
                except OSError:
                    return False

            until(rendered, "native backing pixels at the live display density")
            for kind in ("vector-image", "readback"):
                until(lambda: any(e["event"] == kind and abs(e["scale"] - scale / 120) < 0.001
                                  and e["ok"] for e in events()), f"{kind} on the live display")
            record = dict(scale=scale, output=actual, capture=path.name)
            if zoom_application:
                until(lambda: application()["backing_scale"] == scale / 120, "native application backing density")
                record["zoom"] = zoom()
            if fullscreen: record["fullscreen"] = toggle_fullscreen()
            records.append(record)
            print(f"Live display {scale}/120: PASS", flush=True)
        for transform in range(8):
            state = apply(layout(180, transform))
            actual = next(h for h in state["heads"] if h["id"] == primary["id"])
            width, height = actual["width"], actual["height"]
            if transform % 2:
                width, height = height, width
            assert (actual["logical_width"], actual["logical_height"]) == (width * 120 // 180, height * 120 // 180)
            assert client.poll() is None
            rotations.append(actual)
        apply(original)
        changed = preview(layout(150, 1))
        assert request("cancel", token=changed["token"])["status"] == 3
        until(restored, "explicit cancellation restores the live display")
        preview(layout(210, 3), timeout=1000)
        until(restored, "compositor deadline restores the live display")
        print("Live display rotation, cancel and deadline rollback: PASS", flush=True)
    finally:
        try:
            restored = apply(original)
            (artifacts / "restored.json").write_text(json.dumps(restored, indent=2) + "\n")
        finally:
            if client and client.poll() is None:
                client.terminate()
                client.wait(timeout=10)
    (artifacts / "results.json").write_text(json.dumps(dict(initial=initial, trials=records,
        rotations=rotations, rollback=["cancel", "deadline"]), indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", required=True)
    parser.add_argument("--workspace-probe", required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--mode", help="Temporary primary mode, for example 2560x1600")
    parser.add_argument("--zoom-application", help="Also check the initially active native document's zoom and frame restoration")
    parser.add_argument("--fullscreen", action="store_true", help="Also check that application's fullscreen and exact restoration")
    parser.add_argument("--window-number", type=int, help="Select the native document explicitly when its application is inactive")
    run(**vars(parser.parse_args()))
