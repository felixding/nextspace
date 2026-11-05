"""Primary-selection transfers reuse the clipboard fixtures and wire bridge."""
import json
import subprocess
from integration import until


def check(command, env, registry, pasteboard, artifacts, wid, target, dimensions, protocol_source, key, events, clipboard_expected):
    assert registry and pasteboard
    original = next(o["scale"] for o in command("outputs") if o["name"] == target)
    expected = "Primary:日本語\n" + "selection:日本語\n" * 6000
    external = artifacts / "primary-external.txt"
    external.write_text("Primary outside:日本語\n" * 6000)
    records = []

    def imported(path):
        result = subprocess.run([pasteboard, "--primary-text-file", str(path)], env=env,
                                capture_output=True, timeout=10)
        assert result.returncode in (0, 1), ("Primary-selection probe failed; rebuild the fixture", result.returncode,
                                            result.stderr.decode(errors="replace"))
        return result.returncode == 0

    def unchanged(stage):
        after = subprocess.run([pasteboard, "--export-text"], env=env, capture_output=True)
        if (after.returncode, after.stdout) != (before.returncode, before.stdout):
            (artifacts / "clipboard-after-primary.txt").write_bytes(after.stdout)
            (artifacts / "primary-clipboard-failure.json").write_text(json.dumps(dict(stage=stage,
                before_status=before.returncode, after_status=after.returncode,
                before_bytes=len(before.stdout), after_bytes=len(after.stdout),
                selection=command("selection"), state=command("selection-state")), indent=2) + "\n")
            try:
                subprocess.run([registry, "--clipboard-read", str(artifacts / "clipboard-canonical-after-primary.txt")],
                    env=env, check=False, timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except subprocess.TimeoutExpired:
                pass
            raise AssertionError(f"Primary selection changed the clipboard during {stage}")

    def focus_native():
        assert command(f"focus {wid}")["ok"]
        w = next(w for w in command("windows") if w["id"] == wid)
        assert command(f"pointer {w['x'] + 200} {w['y'] + 300}")["ok"]
        assert command("button 272")["ok"]

    # Establish and independently read the clipboard before testing the other
    # channel. Earlier integration transfers may still have queued imports.
    focus_native()
    serial = command("selection-state")["serial"]
    key(46, True); key(46, False)
    until(lambda: command("selection-state")["serial"] != serial and command("selection-state")["owned"],
          "clipboard baseline is retained by the compositor")
    canonical = artifacts / "clipboard-canonical-before-primary.txt"
    subprocess.run([registry, "--clipboard-read", str(canonical)], env=env, check=True, timeout=15,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert canonical.read_text() == clipboard_expected
    until(lambda: subprocess.run([pasteboard, "--text-file", str(canonical)], env=env).returncode == 0,
          "clipboard storage matches its independently read baseline")
    before = subprocess.run([pasteboard, "--export-text"], env=env, capture_output=True)
    (artifacts / "clipboard-before-primary.txt").write_bytes(before.stdout)

    def click_handled_since(index, x, y):
        return any(e["event"] == "mouse-handled" and (e["x"], e["y"]) == (x, y) for e in events()[index:])

    try:
        for scale in (120, 180, 240):
            assert command(f"test-scale {target} {scale} 10000")["ok"]
            assert command("confirm")["ok"]
            until(lambda: dimensions(scale), "primary-selection source density")
            focus_native()
            key(25, True); key(25, False)
            until(lambda: any(m.endswith("-primary") for m in command("primary-selection")), "native primary offer")
            if scale == 120:
                retained = command("primary-selection-state")
                with protocol_source("--primary-invalid", external, "primary-invalid.log") as (writer, cw):
                    assert command(f"focus {cw['id']}")["ok"]
                    key(57, True); key(57, False)
                    until(lambda: "Invalid primary request processed" in (artifacts / "primary-invalid.log").read_text(),
                          "invalid primary request reaches the server")
                    assert command("primary-selection-state") == retained, "An unknown serial cannot replace primary ownership"
            destination = artifacts / f"primary-native-{scale}.txt"
            subprocess.run([registry, "--primary-read", str(destination)], env=env, check=True, timeout=15,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            assert destination.read_text() == expected
            with protocol_source("--primary-write", external, f"primary-writer-{scale}.log") as (writer, cw):
                assert command(f"focus {cw['id']}")["ok"]
                key(57, True); key(57, False)
                until(lambda: command("primary-selection") == ["text/plain;charset=utf-8"], "independent primary offer")
                focus_native()
                until(lambda: imported(external),
                      "independent primary selection imports into GNUstep")
            until(lambda: not command("primary-selection"), "primary ownership ends with its source")
            until(lambda: subprocess.run([pasteboard, "--primary-empty"], env=env).returncode == 0,
                  "focused native receiver imports primary clearing")
            unchanged(f"density-{scale}")
            records.append(dict(scale=scale, native_bytes=destination.stat().st_size, external_bytes=external.stat().st_size))
        focus_native()
        field = next(e for e in events() if e["event"] == "text-field")
        field_text = "Selection, keyboard input and text metrics"
        w = next(w for w in command("windows") if w["id"] == wid)
        start = int(w["x"] + field["start_x"]), int(w["y"] + w["height"] - field["start_y"])
        end = int(w["x"] + field["end_x"]), int(w["y"] + w["height"] - field["end_y"])
        index = len(events())
        assert command(f"pointer {start[0]} {start[1]}")["ok"]
        assert command("button 272")["ok"]
        until(lambda: click_handled_since(index, field["start_x"], field["start_y"]),
              "field editor completes its initial click")
        index = len(events())
        assert command(f"pointer {end[0]} {end[1]}")["ok"]
        assert command("button 272 1")["ok"]
        assert command(f"pointer {start[0]} {start[1]}")["ok"]
        assert command("button 272 0")["ok"]
        until(lambda: click_handled_since(index, field["end_x"], field["end_y"]),
              "field editor completes a batched drag and release")
        until(lambda: any(m.endswith("-primary") for m in command("primary-selection")),
              "selecting real NSTextField text publishes the first primary selection")
        selected = artifacts / "primary-field-selection.txt"
        subprocess.run([registry, "--primary-read", str(selected)], env=env, check=True, timeout=15,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        assert selected.read_text() == field_text
        middle = artifacts / "primary-middle-input.txt"; middle.write_text("Middle:日本語")
        with protocol_source("--primary-write", middle, "primary-middle-writer.log") as (writer, cw):
            assert command(f"focus {cw['id']}")["ok"]
            key(57, True); key(57, False)
            assert command(f"focus {wid}")["ok"]
            until(lambda: imported(middle),
                  "external primary selection arrives before middle click")
            index = len(events())
            assert command(f"pointer {start[0]} {start[1]}")["ok"]
            assert command("button 272")["ok"]
            until(lambda: click_handled_since(index, field["start_x"], field["start_y"]),
                  "middle-click destination has a live field editor")
            # The bezel forwards left clicks, while middle clicks must hit the
            # actual NSTextView field editor inside it.
            assert command(f"pointer {start[0] + 20} {start[1]}")["ok"]
            assert command("button 274")["ok"]
            until(lambda: any(e["event"] == "field-text" and e["text"] == "Middle:日本語" + field_text for e in events()),
                  "real NSTextField middle-click pastes the external primary selection")
        unchanged("field")
        (artifacts / "primary-selection.json").write_text(json.dumps(dict(scales=records,
            first_selection=selected.read_text(), middle_click=True, invalid_serial=True), indent=2) + "\n")
    finally:
        assert command(f"test-scale {target} {original} 10000")["ok"]
        assert command("confirm")["ok"]
