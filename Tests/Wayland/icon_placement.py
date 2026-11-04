"""Real AppKit icon tracking and compositor-owned logical placement."""
import json
import time
from integration import until


def track(command, icon, point, cancel=False, restart=None):
    def at(point):
        current = icon()
        return current and (current["x"], current["y"]) == point

    current = until(icon, "application icon ready for tracking")
    assert command(f"focus {current['id']}")["ok"]
    start = current["x"] + 32, current["y"] + 32
    time.sleep(0.35)  # End the preceding double-click interval.
    assert command(f"pointer {start[0]} {start[1]}")["ok"]
    def exposed():
        assert command(f"raise {current['id']}")["ok"]
        return command(f"hit {start[0]} {start[1]}")["id"] == current["id"]
    until(exposed, "expose the IconYard tile above ordinary document windows")
    assert command("button 272 1")["ok"]
    assert command(f"pointer {start[0] + 2} {start[1] + 2}")["ok"]
    time.sleep(0.05)
    assert command("move-state")["id"] == 0, "A small logical jitter must not start icon movement"
    assert command(f"pointer {start[0] + 16} {start[1] + 12}")["ok"]
    until(lambda: command("move-state")["id"] == current["id"], "serial-validated icon grab")
    if restart:
        restart()
        assert command("move-state")["id"] == current["id"], "Shell replacement preserves an active icon grab"
    assert command(f"pointer {point[0] + 32} {point[1] + 32}")["ok"]
    until(lambda: at(point), "compositor moves the icon with the logical pointer")
    if cancel:
        assert command("key 1 1")["ok"]
        assert command("key 1 0")["ok"]
    assert command("button 272 0")["ok"]
    until(lambda: command("move-state")["id"] == 0, "interactive icon grab finishes")
    return current


def check(command, query, pid, artifacts, restart=None):
    def icon():
        return next((w for w in command("windows") if w["pid"] == pid and w["style"] & 64), None)

    def primary():
        name = next(o["name"] for o in query("--display-state")["heads"] if o["primary"])
        return next(o for o in command("outputs") if o["name"] == name)

    def at(point):
        current = icon()
        return current if current and (current["x"], current["y"]) == point else None

    def pinned_at(point):
        # The hidden Workspace placeholder moves only after the shell has saved
        # the drop, so this also acknowledges the asynchronous end event.
        return at(point) and any(w["pid"] != pid and w["title"] == "WaylandProbe" and
            w["style"] & 64 and not w["presented"] and (w["x"], w["y"]) == point
            for w in command("windows"))

    def drag(point, cancel=False, restart=None):
        return track(command, icon, point, cancel, restart)

    records = []
    original = {o["name"]: o["scale"] for o in command("outputs")}
    for scale in (120, 150, 180, 210, 240):
        for output in command("outputs"):
            assert command(f"test-scale {output['name']} {scale} 10000")["ok"]
            assert command("confirm")["ok"]
        output = primary()
        pinned = output["x"] + output["width"] - 64, output["y"] + 64
        try:
            until(lambda: pinned_at(pinned), "pinned icon follows density without changing its logical slot")
        except AssertionError:
            (artifacts / "icon-placement-failure.json").write_text(json.dumps(dict(
                scale=scale, expected=pinned, windows=command("windows"), outputs=command("outputs"),
                undocked=query("--undocked")), indent=2) + "\n")
            raise
        free = output["x"] + 80, output["y"] + 100
        drag(free, cancel=True)
        until(lambda: at(pinned), "Escape restores the Dock icon and its settings")
        drag(free)
        until(lambda: at(free), "dragging out of Dock retains the running icon in IconYard")
        until(lambda: any(a["Name"] == "WaylandProbe.GNUstep" for a in query("--undocked")), "drag removes the pin")
        moved = free[0] + 40, free[1] + 50
        drag(moved, restart=restart if scale == 150 else None)
        until(lambda: at(moved), "free IconYard position survives shell placement notifications")
        until(lambda: query("--read-dock")["positions"].get("WaylandProbe") == dict(X=120, Y=150),
              "free logical position is saved before shell replacement")
        if restart and scale == 120:
            restart()
            until(lambda: at(moved), "free IconYard placement survives Workspace replacement")
        second = pinned[0], output["y"] + 192
        drag(second)
        until(lambda: pinned_at(second), "drag pins the running application in a new Dock slot")
        until(lambda: all(a["Name"] != "WaylandProbe.GNUstep" for a in query("--undocked")), "drag adds one pin")
        drag(pinned)
        until(lambda: pinned_at(pinned), "drag restores the original Dock slot")
        swapped = pinned[0], output["y"] + 128
        drag(swapped)
        until(lambda: pinned_at(swapped), "drag swaps two unlocked Dock slots")
        drag(pinned)
        until(lambda: pinned_at(pinned), "drag restores both swapped slots")
        records.append(dict(scale=scale, pinned=pinned, free=moved, pid=pid))
    for name, scale in original.items():
        assert command(f"test-scale {name} {scale} 10000")["ok"]
        assert command("confirm")["ok"]
    output = primary()
    until(lambda: pinned_at((output["x"] + output["width"] - 64, output["y"] + 64)),
          "Dock placement acknowledges the restored density")
    (artifacts / "icon-placement.json").write_text(json.dumps(records, indent=2) + "\n")


def check_locked(command, icon):
    before = until(icon, "locked Dock icon is mapped")
    time.sleep(0.35)
    assert command(f"pointer {before['x'] + 32} {before['y'] + 32}")["ok"]
    assert command("button 272 1")["ok"]
    assert command(f"pointer {before['x'] - 80} {before['y'] + 80}")["ok"]
    time.sleep(0.1)
    until(lambda: command("move-state")["id"] == 0, "locked Dock icon cancels the interactive grab")
    assert command("button 272 0")["ok"]
    def restored():
        current = icon()
        return current and (current["x"], current["y"]) == (before["x"], before["y"])
    until(restored, "locked pin keeps its slot")


def check_mini(command, query, pid, artifacts):
    def document():
        return next((w for w in command("windows") if w["pid"] == pid and w["width"] > 100 and
                     w["title"] == "WaylandProbe"), None)

    def mini():
        return next((w for w in command("windows") if w["pid"] == pid and w["style"] & 128 and w["visible"]), None)

    original = {o["name"]: o["scale"] for o in command("outputs")}
    records = []
    for scale in (120, 180, 240):
        for output in command("outputs"):
            assert command(f"test-scale {output['name']} {scale} 10000")["ok"]
            assert command("confirm")["ok"]
        main = document()
        assert command(f"minimize {main['id']} 1")["ok"]
        current = until(mini, "AppKit creates a native miniwindow icon")
        name = next(o["name"] for o in query("--display-state")["heads"] if o["primary"])
        output = next(o for o in command("outputs") if o["name"] == name)
        point = output["x"] + 300, output["y"] + 250
        track(command, mini, point)
        key = "WaylandProbe/Mini/" + current["title"]
        until(lambda: query("--read-dock")["positions"].get(key) == dict(X=300, Y=250),
              "miniwindow icon uses the same persistent logical tracker")
        current = mini()
        assert (current["buffer_width"], current["buffer_height"]) == (64 * scale // 120,) * 2
        records.append(dict(scale=scale, icon=current))
        def completed_clicks():
            return sum(1 for log in artifacts.glob("workspace*.log") for line in log.read_text().splitlines()
                if line.startswith('{"event":"mouse-handled"') and
                (event := json.loads(line))["window"] == current["client_id"] and event["clicks"] >= 2)
        handled = completed_clicks()
        time.sleep(0.35)
        assert command(f"pointer {point[0] + 32} {point[1] + 32}")["ok"]
        assert command("button 272")["ok"]
        assert command("button 272")["ok"]
        until(lambda: completed_clicks() > handled, "miniwindow double-click handler finishes")
        until(lambda: not mini() and document() and not document()["minimized"],
              "double-clicking the moved miniwindow restores the native document")
    for name, scale in original.items():
        assert command(f"test-scale {name} {scale} 10000")["ok"]
        assert command("confirm")["ok"]
    (artifacts / "miniwindow-placement.json").write_text(json.dumps(records, indent=2) + "\n")
    return document()


def check_foreign(command, query, icon, pid, artifacts):
    name = next(o["name"] for o in query("--display-state")["heads"] if o["primary"])
    output = next(o for o in command("outputs") if o["name"] == name)
    free = output["x"] + 240, output["y"] + 300
    track(command, icon, free)
    names = ("GtkProbe.GNUstep", "gtk-probe.GNUstep")
    until(lambda: any(a["Name"] in names for a in query("--undocked")), "foreign application unpinned")
    until(lambda: icon() and (icon()["x"], icon()["y"]) == free,
          "foreign application receives one IconYard tile at its saved drop position")
    assert len([w for w in command("windows") if w["title"] in ("GtkProbe", "gtk-probe") and w["style"] & 64]) == 1
    current = icon()
    time.sleep(0.35)
    assert command(f"pointer {free[0] + 32} {free[1] + 32}")["ok"]
    assert command("button 272")["ok"]
    assert command("button 272")["ok"]
    until(lambda: any(w["pid"] == pid and w["focused"] for w in command("windows")),
          "IconYard double-click activates the same foreign application")
    pinned = output["x"] + output["width"] - 64, output["y"] + 128
    track(command, icon, pinned)
    until(lambda: all(a["Name"] not in names for a in query("--undocked")), "foreign application pinned from IconYard")
    until(lambda: icon() and (icon()["x"], icon()["y"]) == pinned, "new launcher occupies the selected logical slot")
    assert any(w["pid"] == pid for w in command("windows")), "Pinning must preserve the existing process"
    (artifacts / "foreign-icon-placement.json").write_text(json.dumps(dict(pid=pid, free=current, pinned=icon()), indent=2) + "\n")
