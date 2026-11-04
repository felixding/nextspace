"""Drive the real Preferences display controls and confirmation panel."""
import json
import subprocess
import re
import time
import shutil
import hashlib
from pathlib import Path
from PIL import Image
from integration import until


def run(executable, probe, env, command, query, processes, artifacts):
    log_path = artifacts / "preferences.log"
    captures = artifacts / "preferences-captures"; captures.mkdir(exist_ok=True)
    app_env = dict(env, NEXTSPACE_WAYLAND_CAPTURE_DIR=str(captures.resolve()))
    with log_path.open("w") as log:
        process = subprocess.Popen([executable, "-GSBackend", "libgnustep-wayland", "-GSTheme", "NextSpace",
            "-NSUseRunningCopy", "NO"], env=app_env, stdout=log, stderr=log)
    processes.append(process)

    def window(title):
        assert process.poll() is None, log_path.read_text()[-8000:]
        return next((w for w in command("windows") if w["pid"] == process.pid and w["title"] == title and w["visible"]), None)

    until(lambda: window("Localization Preferences"), "native Preferences starts")
    font = query("--preferences-metadata", "Font")["controls"]
    def module_runtime(name):
        mappings = Path(f"/proc/{process.pid}/maps").read_text().splitlines()
        modules = sorted({line.split()[-1] for line in mappings if f"/{name}.preferences/" in line})
        assert len(modules) == 1, (name, modules)
        module = Path(modules[0])
        executable = Path(f"/proc/{process.pid}/exe").resolve()
        candidate = executable.parent / 'Resources' / (name + '.preferences') / name
        checksum = hashlib.sha256(module.read_bytes()).hexdigest()
        assert candidate.is_file() and checksum == hashlib.sha256(candidate.read_bytes()).hexdigest(), (
            f"Preferences loaded a different {name} module than its requested application", str(module), str(candidate))
        (artifacts / f"preferences-{name.lower()}-runtime.json").write_text(json.dumps(dict(module=str(module),
            sha256=checksum, candidate=str(candidate), executable=str(executable), libraries=sorted({line.split()[-1]
                for line in mappings if any(token in line for token in ("libgnustep-base.so.", "libgnustep-gui.so.",
                    "libgnustep-wayland-", "SystemKit.framework", "DesktopKit.framework"))})), indent=2) + "\n")
    module_runtime('Font')
    original_font_aa = font["antialiased"]
    font_path = Path(font["wm_defaults_path"])
    assert font_path.is_relative_to(Path(env["XDG_RUNTIME_DIR"])), "Font test requires isolated defaults"
    original_font_file = font_path.read_bytes() if font_path.exists() else None
    original_frame_font = command("decoration-settings")["title_appearance"]
    font_results = []
    try:
        for enabled in (1, 0, original_font_aa):
            query("--preferences-action", "Font", "enableAntiAliasingButton", str(enabled))
            saved = query("--preferences-metadata", "Font")["controls"]["wm_preferences"]
            assert font_path.is_file() and f"antialias={'true' if enabled else 'false'}" in saved["WindowTitleFont"], saved
            until(lambda: command("decoration-settings")["title_appearance"]["antialiased"] == bool(enabled),
                  "real Font-panel notification repaints compositor titles")
            frame = command("decoration-settings")["title_appearance"]
            font_results.append(dict(enabled=enabled, saved=saved, frame=frame, original=original_frame_font))
            (artifacts / "preferences-font.json").write_text(json.dumps(font_results, indent=2) + "\n")
            if original_font_file is None:
                assert frame["font"] == original_frame_font["font"], \
                    "Antialias toggle changed the default title face or size"
    finally:
        query("--preferences-action", "Font", "enableAntiAliasingButton", str(original_font_aa))
        if original_font_file is None: font_path.unlink(missing_ok=True)
        else: font_path.write_bytes(original_font_file)
        query("--post-appearance")
        until(lambda: all(command("decoration-settings")["title_appearance"][key] == original_frame_font[key]
                          for key in ("font", "antialiased", "justification")), "restore original title preferences")
    (artifacts / "preferences-font.json").write_text(json.dumps(font_results, indent=2) + "\n")
    def input_request(action, **values):
        request = artifacts / "preferences-input-request.json"
        request.write_text(json.dumps(dict(action=action, **values)))
        return query("--display-request", str(request))

    mouse = query("--preferences-metadata", "Mouse")["controls"]
    original_interval = mouse["double_click_time"]
    intervals = mouse["double_click_choices"]
    mouse_results = []
    try:
        for interval in dict.fromkeys((intervals[0], intervals[len(intervals) // 2], intervals[-1])):
            query("--preferences-action", "Mouse", "doubleClickMtrx", str(interval))
            until(lambda: command("decoration-settings")["double_click_time"] == interval,
                  "Mouse Preferences timing reaches compositor-owned frames")
            assert query("--preferences-metadata", "Mouse")["controls"]["double_click_time"] == interval
            mouse_results.append(dict(interval=interval, frame_settings=command("decoration-settings")))
    finally:
        query("--preferences-action", "Mouse", "doubleClickTime", str(original_interval))
        until(lambda: command("decoration-settings")["double_click_time"] == original_interval,
              "original mouse timing restored")
    (artifacts / "mouse-timing.json").write_text(json.dumps(mouse_results, indent=2) + "\n")

    initial_input = input_request("input-state")
    initial_modifiers = query("--preferences-action", "Keyboard", "sectionsBtn", "5")["controls"]
    for control, value, option in (("swapCAMtrx", "1", "altwin:swap_lalt_lwin"),
                                    ("capsLockBtn", "Control", "caps:ctrl_modifier"),
                                    ("composeKeyBtn", "Menu", "compose:menu")):
        query("--preferences-action", "Keyboard", control, value)
        assert option in input_request("input-state")["options"].split(",")
        # Reopening must look up the saved selection in a live configuration
        # dictionary, including when compose and Caps Lock options already exist.
        query("--preferences-action", "Keyboard", "sectionsBtn", "5")
    modifier_settings = input_request("input-state")
    # Restore the controls too: their saved defaults are reapplied when the
    # session restores settings, independently of the current compositor state.
    for control, value in (("swapCAMtrx", initial_modifiers["swap"]),
                           ("capsLockBtn", initial_modifiers["capsLockBtn"]),
                           ("composeKeyBtn", initial_modifiers["composeKeyBtn"])):
        query("--preferences-action", "Keyboard", control, str(value))
    assert input_request("keyboard", settings=initial_input)["success"]
    initial = query("--display-state")
    metadata = query("--preferences-metadata", "Display")
    module_runtime('Display')
    assert "scaleBtn" in metadata["controls"] and "effectiveSize" in metadata["controls"]
    until(lambda: (w := window("Display Preferences")) and w["height"] == 396, "display controls retain logical layout")
    measurements = []

    def choose(control, tag, keep, module="Display"):
        before = query("--display-state")
        before_ids = {w["id"] for w in command("windows") if w["pid"] == process.pid and w["visible"]}
        errors = (artifacts / f"preferences-{control}-{tag}.stderr").open("w")
        action = subprocess.Popen([probe, "--preferences-action", module, control, str(tag),
            "-GSWorkspaceApplication", "Workspace"], env=env, stdout=subprocess.PIPE, stderr=errors, text=True)
        try:
            dialog = until(lambda: next((w for w in command("windows") if w["pid"] == process.pid and
                w["id"] not in before_ids and w["visible"] and not w["title"] and w["width"] > 100), None),
                "compositor-managed display confirmation")
            if keep:
                # NXTAlert places keyboard focus on its alternate button.
                # Exercise that real modal focus path without a synchronous
                # distributed-object request into an active modal callback.
                assert command(f"focus {dialog['id']}")["ok"]
                assert command("key 57 1")["ok"] and command("key 57 0")["ok"]
            stdout, _ = action.communicate(timeout=12)
            assert action.returncode == 0, (stdout, (artifacts / f"preferences-{control}-{tag}.stderr").read_text())
            after = query("--display-state")
            assert not after["pending"]
            if not keep:
                assert after["heads"] == before["heads"], "Timeout changed the previous layout"
            measurements.append(dict(module=module, control=control, tag=tag, kept=keep, heads=after["heads"]))
            until(lambda: not any(w["id"] == dialog["id"] and w["visible"] for w in command("windows")), "confirmation panel closes")
        finally:
            errors.close()
            if action.poll() is None: action.kill(); action.wait(timeout=5)
            if action.stdout: action.stdout.close()

    choose("scaleBtn", 180, True)
    assert any(h["scale"] == 180 for h in query("--display-state")["heads"])
    choose("scaleBtn", 240, False)
    choose("rotationBtn", 1, True)
    assert any(h["transform"] == 1 for h in query("--display-state")["heads"])
    choose("reflectionBtn", 4, True)
    assert any(h["transform"] == 5 for h in query("--display-state")["heads"])
    choose("reflectionBtn", 0, True)
    choose("rotationBtn", 0, True)
    choose("scaleBtn", 120, True)
    restored = query("--display-state")
    assert restored["heads"] == initial["heads"]
    screen = query("--preferences-metadata", "Screen")
    assert len(screen["controls"]["displays"]) == 2
    names = [d["name"] for d in screen["controls"]["displays"]]
    primary = next(i for i, name in enumerate(names) if next(h for h in initial["heads"] if h["name"] == name)["primary"])
    secondary = 1 - primary

    def select(index):
        return query("--preferences-action", "Screen", "select", str(index))

    select(secondary)
    choose("setMainBtn", 0, True, "Screen")
    assert next(h for h in query("--display-state")["heads"] if h["name"] == names[secondary])["primary"]
    select(secondary)
    choose("setStateBtn", 0, False, "Screen")
    select(secondary)
    choose("setStateBtn", 0, True, "Screen")
    assert not next(h for h in query("--display-state")["heads"] if h["name"] == names[secondary])["enabled"]
    assert not select(primary)["controls"]["setStateBtn"]["enabled"], "UI may disable the last usable output"
    select(secondary)
    choose("setStateBtn", 0, True, "Screen")
    if select(primary)["controls"]["setMainBtn"]["enabled"]:
        choose("setMainBtn", 0, True, "Screen")

    # Drag the second monitor in the real flipped arrangement canvas. Revert
    # first leaves hardware untouched; applying it uses the same confirmation.
    def drag_monitor():
        screen = query("--preferences-metadata", "Screen")
        box = screen["controls"]["displays"][secondary]
        x, y, width, height = map(float, re.findall(r"-?\d+(?:\.\d+)?", box["base"]))
        panel = window("Screen Preferences")
        x, y = round(panel["x"] + x + width / 2), round(panel["y"] + panel["height"] - y - height / 2)
        assert command(f"focus {panel['id']}")["ok"]
        assert command(f"pointer {x} {y}")["ok"]
        assert command("button 272 1")["ok"]
        time.sleep(.06)
        assert command(f"pointer {x} {y - 30}")["ok"]
        time.sleep(.10)
        assert command("button 272 0")["ok"]
        until(lambda: query("--preferences-metadata", "Screen")["controls"]["applyBtn"]["enabled"],
              "monitor arrangement drag")

    before_arrangement = query("--display-state")["heads"]
    drag_monitor()
    assert query("--display-state")["heads"] == before_arrangement
    query("--preferences-action", "Screen", "revertBtn", "0")
    assert query("--display-state")["heads"] == before_arrangement
    drag_monitor()
    choose("applyBtn", 0, True, "Screen")
    arranged = query("--display-state")["heads"]
    old = next(h for h in before_arrangement if h["name"] == names[secondary])
    moved = next(h for h in arranged if h["name"] == names[secondary])
    assert moved["y"] < old["y"], "Dragging upward must lower the logical top-left output Y"
    for head in arranged:
        if head["name"] != names[secondary]:
            assert head == next(h for h in before_arrangement if h["name"] == head["name"]), "Dragging moved another output"
    # Restore through the existing settings service so subsequent shell tests
    # begin with their original desktop extent.
    request = artifacts / "preferences-restore.json"
    state = query("--display-state")
    request.write_text(json.dumps(dict(action="apply", layout=initial["heads"], revision=state["revision"], timeout=5000)))
    transaction = query("--display-request", str(request))
    assert transaction["status"] == 1
    request.write_text(json.dumps(dict(action="confirm", token=transaction["token"])))
    assert query("--display-request", str(request))["status"] == 2
    # Switching modules restores the original panel extent and returns to the
    # added scale row without growing the window on each visit.
    query("--preferences-metadata", "Mouse")
    until(lambda: (w := window("Mouse Preferences")) and w["height"] == 342, "standard Preferences extent")
    query("--preferences-metadata", "Display")
    until(lambda: (w := window("Display Preferences")) and w["height"] == 396, "stable extended Preferences extent")
    densities = []
    for scale in (120, 150, 180, 210, 240):
        for output in command("outputs"):
            assert command(f"test-scale {output['name']} {scale} 10000")["ok"]
            assert command("confirm")["ok"]
        for module in ("Screen", "Display", "Keyboard", "Mouse"):
            for capture in captures.glob(f"window-*-{scale}.png"): capture.unlink()
            query("--preferences-metadata", module)
            def rendered():
                panel = window(module + " Preferences")
                if not panel: return None
                expected = tuple((panel[key] * scale + 60) // 120 for key in ("width", "height"))
                capture = captures / f"window-{panel['client_id']}-{scale}.png"
                if (panel["buffer_width"], panel["buffer_height"]) != expected or not capture.exists(): return None
                with Image.open(capture) as pixels:
                    if pixels.size != expected or pixels.convert("RGB").getextrema() == ((0, 0),) * 3: return None
                return panel, capture
            panel, capture = until(rendered, f"{module} Preferences submitted pixels at {scale}/120")
            shutil.copyfile(capture, artifacts / f"preferences-{module.lower()}-{scale}.png")
            densities.append(dict(module=module, scale=scale, width=panel["width"], height=panel["height"]))
    for output in command("outputs"):
        assert command(f"test-scale {output['name']} 120 10000")["ok"]
        assert command("confirm")["ok"]
    active = query("--application-state", "Preferences")
    assert active["active"]
    workspace_window = next(w for w in command("windows") if w["app_id"] == "org.nextspace.Workspace" and w["accepts_focus"])
    assert command(f"focus {workspace_window['id']}")["ok"]
    inactive = until(lambda: (state if not (state := query("--application-state", "Preferences"))["active"] else None),
                     "Preferences resigns application activation")
    assert not inactive["menu_visible"], "Inactive application menu remains visible"
    query("--preferences-metadata", "Display")
    reactivated = until(lambda: (state if (state := query("--application-state", "Preferences"))["active"] else None),
                       "Preferences regains application activation")
    (artifacts / "preferences-results.json").write_text(json.dumps(dict(initial=initial, measurements=measurements,
        metadata=metadata, restored=restored, densities=densities,
        application_activation=dict(active=active, inactive=inactive, reactivated=reactivated),
        modifier_settings=modifier_settings), indent=2) + "\n")
    process.terminate(); process.wait(timeout=5)
    until(lambda: not any(w["pid"] == process.pid for w in command("windows")), "Preferences surfaces close")
    processes.remove(process)
