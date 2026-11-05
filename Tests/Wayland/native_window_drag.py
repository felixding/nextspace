"""Check real AppKit title-bar dragging and zoom restoration under Workspace."""
import json
import time
from integration import until


def check(command, query, window, artifacts):
    wid = window["id"]

    def current():
        return next(w for w in command("windows") if w["id"] == wid)

    def frame(value):
        return {key: value[key] for key in ("x", "y", "width", "height")}

    heads = command("outputs")
    head = max(heads, key=lambda h: max(0, min(window["x"] + window["width"], h["x"] + h["width"]) -
        max(window["x"], h["x"])) * max(0, min(window["y"] + window["height"], h["y"] + h["height"]) -
        max(window["y"], h["y"])))
    original = frame(window)
    # Keep the title bar reachable at the smallest logical output size. Output
    # recovery legitimately relocates a title bar left below a resized display.
    normal = dict(original, x=head["x"] + 40, y=head["y"] + 40)
    assert command(f"move {wid} {normal['x']} {normal['y']}")["ok"]
    until(lambda: frame(current()) == normal, "reachable initial native frame")
    assert command(f"focus {wid}")["ok"]
    number = until(lambda: query("--application-state", "WaylandProbe")["window_number"], "active AppKit document")

    def zoom():
        query("--application-action", "WaylandProbe", "zoom", "--window-number", str(number))

    def scale(density):
        assert command(f"test-scale {head['name']} {density} 10000")["ok"]
        assert command("confirm")["ok"]

    records = []
    button_held = False
    last_title_press = None
    try:
        for density, cancel in [(d, False) for d in (120, 150, 180, 210, 240)] + [(150, True)]:
            scale(density)
            zoom()
            until(lambda: current()["maximized"], "native AppKit maximizes")
            until(lambda: current()["width"] != normal["width"] or current()["height"] != normal["height"],
                  "native maximized backing resize")
            before = current()
            if before.get("server_decorated") and last_title_press is not None:
                # Space separate drag gestures by the session's click interval.
                interval = command("decoration-settings").get("double_click_time", 0) / 1000
                remaining = last_title_press + interval + .02 - time.monotonic()
                if remaining > 0: time.sleep(remaining)
            x, y = before["x"] + before["width"] // 2, before["y"] + 10
            assert command(f"pointer {x} {y}")["ok"]
            last_title_press = time.monotonic()
            assert command("button 272 1")["ok"]
            button_held = True
            until(lambda: command("move-state") == dict(id=wid, mode=1), "AppKit title bar begins compositor move")
            assert command(f"pointer {x+41} {y+29}")["ok"]
            moved = dict(frame(before), x=before["x"] + 41, y=before["y"] + 29)
            until(lambda: frame(current()) == moved and current()["maximized"], "native maximized title-bar drag")
            if cancel:
                for pressed in (1, 0): assert command(f"key 1 {pressed}")["ok"]
                until(lambda: frame(current()) == frame(before) and current()["maximized"], "native Escape restores maximized frame")
            assert command("button 272 0")["ok"]
            button_held = False
            zoom()
            until(lambda: frame(current()) == normal and not current()["maximized"], "AppKit unzoom restores pre-drag floating frame")
            records.append(dict(density=density, cancelled=cancel, before=before, restored=current()))
    except BaseException:
        (artifacts / "native-window-drag-failure.json").write_text(json.dumps(dict(
            records=records, normal=normal, window=current(), move=command("move-state"),
            pointer=command("pointer-focus")), indent=2) + "\n")
        raise
    finally:
        if button_held: command("button 272 0")
        if current()["shaded"]:
            command(f"shade {wid} 0")
            until(lambda: not current()["shaded"], "unshade native fixture during cleanup")
        if current()["maximized"]: zoom()
        scale(head["scale"])
        assert command(f"move {wid} {original['x']} {original['y']}")["ok"]
        until(lambda: frame(current()) == original, "restore native fixture position")
    (artifacts / "native-window-drag.json").write_text(json.dumps(records, indent=2) + "\n")
    return current()
