#!/usr/bin/env python3
"""Run the actual Workspace with a private shell and no X display."""
import argparse
import array
import json
import os
import plistlib
import signal
import shutil
from pathlib import Path
import select
import shlex
import socket
import subprocess
import tempfile
import time
import uuid
from integration import until
from gnustep import private_defaults
from PIL import Image


def run(compositor, workspace, probe, artifacts, client=None, gui_probe=None, display_probe=None, preferences=None, openup=None,
        application_directory=None, alert_probe=None, power_probe=None, checkmark_only=False):
    artifacts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nextspace-workspace-") as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS="headless",
                   WLR_HEADLESS_OUTPUTS="2", WLR_RENDERER="pixman",
                   NEXTSPACE_SESSION_ID="test-" + str(uuid.uuid4()),
                   NEXTSPACE_GS_BACKEND="wayland", NEXTSPACE_WAYLAND_CAPTURE_DIR=str(artifacts.resolve()))
        for key in ("DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET", "NEXTSPACE_SHELL_SOCKET"):
            env.pop(key, None)
        # Keep Workspace and its children in a fresh defaults database. The
        # configured framework paths stay intact, including native runtime tests.
        private_defaults(env, runtime, application_directory)
        control, control_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        broker, broker_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        control.settimeout(5)
        with (artifacts / "compositor.log").open("w") as log:
            server = subprocess.Popen([compositor, "-c", str(control_child.fileno()),
                "-S", str(broker_child.fileno())], pass_fds=[control_child.fileno(), broker_child.fileno()],
                env=env, stdout=subprocess.PIPE, stderr=log, text=True)
        control_child.close(); broker_child.close()
        shell = None
        applications = []
        starts = 0
        dock_pids = set()
        display_requests = []
        profile = Path.home() / "Library/Preferences/.NextSpace/WaylandDisplays.plist"
        previous_profile = profile.read_bytes() if profile.exists() else None

        def command(value):
            control.sendall(value.encode())
            return json.loads(control.recv(65536))

        def work_areas(dock=True, yard=True):
            def matches():
                heads = query("--display-state")["heads"]
                return all((h.get("work_x"), h.get("work_y"), h.get("work_width"), h.get("work_height")) == (
                    h["x"], h["y"], h["logical_width"] - (67 if dock and h["primary"] else 0),
                    h["logical_height"] - (64 if yard else 0)) for h in heads if h["enabled"])
            until(matches, "Workspace work areas follow Dock and IconYard visibility")

        def query(*arguments):
            started = time.monotonic()
            try:
                result = subprocess.run([probe, *arguments, "-GSWorkspaceApplication", "Workspace"],
                    env=env, capture_output=True, text=True, timeout=15)
            except subprocess.TimeoutExpired:
                for name, process in (("workspace", shell), ("compositor", server)):
                    if process and process.poll() is None and shutil.which("gdb"):
                        with (artifacts / f"timeout-{name}.log").open("w") as log:
                            subprocess.run(["gdb", "--batch", "-p", str(process.pid), "-ex", "thread apply all bt"],
                                stdout=log, stderr=log, timeout=10)
                raise
            with (artifacts / "workspace-api.jsonl").open("a") as log:
                log.write(json.dumps(dict(arguments=arguments, status=result.returncode,
                                          stdout=result.stdout, stderr=result.stderr,
                                          elapsed_seconds=time.monotonic()-started)) + "\n")
            assert result.returncode == 0, result.stderr
            return json.loads(result.stdout)

        def start_workspace(restore_settings=False):
            nonlocal shell, starts
            endpoint, client_endpoint = socket.socketpair()
            broker.sendmsg([b"C"], [(socket.SOL_SOCKET, socket.SCM_RIGHTS,
                                      array.array("i", [endpoint.fileno()]))])
            endpoint.close()
            log_path = artifacts / ("workspace.log" if starts == 0 else f"workspace-{starts}.log")
            starts += 1
            with log_path.open("w") as log:
                shell = subprocess.Popen([workspace, "-GSTheme", "NextSpace", "-NSUseRunningCopy", "NO",
                    "--nextspace-shell-fd", str(client_endpoint.fileno())] +
                    (["--nextspace-restore-settings"] if restore_settings else []), env=env,
                    pass_fds=[client_endpoint.fileno()], stdout=log, stderr=log)
            client_endpoint.close()

            def ready():
                assert shell.poll() is None, log_path.read_text()[-8000:]
                return "Workspace is ready" in log_path.read_text()
            until(ready, "native Workspace ready", timeout=30)
            libraries = sorted({line.split()[-1] for line in Path(f"/proc/{shell.pid}/maps").read_text().splitlines()
                if any(name in line for name in ("libgnustep-base.so.", "libgnustep-gui.so.", "libgnustep-wayland-",
                                                "SystemKit.framework", "DesktopKit.framework"))})
            (artifacts / f"workspace-{starts - 1}-runtime.json").write_text(json.dumps(dict(
                executable=str(Path(f"/proc/{shell.pid}/exe").resolve()), libraries=libraries), indent=2) + "\n")

        try:
            rejected = subprocess.run([workspace, "-GSBackend", "unsupported"],
                env=dict(env, XDG_SESSION_TYPE="wayland"), capture_output=True, timeout=10)
            assert rejected.returncode == 1 and b"requires the native Wayland backend" in rejected.stderr
            assert select.select([server.stdout], [], [], 10)[0], "No compositor socket"
            line = server.stdout.readline().strip()
            assert line.startswith("WAYLAND_DISPLAY="), line
            env["WAYLAND_DISPLAY"] = line.split("=", 1)[1]
            assert query("--write-desktops", "4")["saved"]
            entries = [dict(Name="Workspace.GNUstep", Command="", Position="0,0", Lock="Yes", AutoLaunch="Yes")]
            if gui_probe:
                entries.extend([dict(Name="WaylandProbe.GNUstep", Command=f"'{gui_probe}' -GSSuppressAppIcon NO",
                                Position="0,1", AutoLaunch="No"),
                           dict(Name="Overflow.Test", Command="/bin/false", Position="0,31", AutoLaunch="No")])
                if client:
                    entries.append(dict(Name="GtkProbe.GNUstep", Command=f"'{client}'", Position="0,2", AutoLaunch="No"))
            dock = Path(runtime) / "dock.plist"
            dock.write_bytes(plistlib.dumps(dict(Applications=entries, Collapsed="No")))
            assert query("--write-dock", str(dock))["saved"]
            start_workspace()
            if checkmark_only:
                from workspace_checkmark import run as checkmark
                checkmark(command, query, artifacts / "checkmark")
                return
            def display_request(action, **values):
                path = Path(runtime) / "display-request.json"
                path.write_text(json.dumps(dict(action=action, **values)))
                result = query("--display-request", str(path))
                display_requests.append(dict(action=action, result=result))
                return result
            display_state = query("--display-state")
            assert display_state["schema"] == 1 and len(display_state["heads"]) == 2
            original = display_state["heads"]
            proposal = [dict(h, scale=180) for h in original]
            tested = display_request("test", layout=proposal, revision=display_state["revision"])
            assert tested["status"] == 0
            applied = display_request("apply", layout=proposal, revision=display_state["revision"], timeout=1000)
            assert applied["status"] == 1 and applied["token"]
            assert display_request("confirm", token="stale-token")["status"] == 4
            assert display_request("apply", layout=proposal, revision=display_state["revision"], timeout=1000)["status"] == 4
            # The requesting process has already exited. The compositor still
            # restores the layout and Workspace reports the matching lease.
            until(lambda: display_request("status", token=applied["token"])["status"] == 3,
                  "display settings timeout after requester exit")
            assert display_request("apply", layout=proposal, revision=display_state["revision"], timeout=1000)["status"] == 4
            assert display_request("status", token=applied["token"])["status"] == 3, \
                "Rejected stale settings must preserve the preceding timeout result"
            state = query("--display-state")
            assert [h["scale"] for h in state["heads"]] == [h["scale"] for h in original]
            applied = display_request("apply", layout=proposal, revision=state["revision"], timeout=15000)
            assert display_request("confirm", token=applied["token"])["status"] == 2
            state = query("--display-state")
            assert all(h["scale"] == 180 for h in state["heads"])
            restored = display_request("apply", layout=original, revision=state["revision"], timeout=15000)
            assert display_request("confirm", token=restored["token"])["status"] == 2
            (artifacts / "display-settings.json").write_text(json.dumps(dict(initial=display_state,
                tested=tested, applied=applied, restored=restored), indent=2) + "\n")
            if alert_probe:
                from alerts import run as run_alerts
                run_alerts(alert_probe, env, command, artifacts / 'alerts')
            if display_probe:
                display_captures = artifacts / "display-model-captures"; display_captures.mkdir(exist_ok=True)
                result = subprocess.run([display_probe, "-GSBackend", "libgnustep-wayland", "-GSTheme", "NextSpace",
                    "-NSUseRunningCopy", "NO"], env=dict(env, NEXTSPACE_WAYLAND_CAPTURE_DIR=str(display_captures.resolve())),
                    capture_output=True, text=True, timeout=60)
                (artifacts / "display-model.log").write_text(result.stdout + result.stderr)
                (artifacts / "display-model-status.json").write_text(json.dumps(dict(
                    executable=display_probe, returncode=result.returncode,
                    stdout=result.stdout, stderr=result.stderr), indent=2) + "\n")
                assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
            if preferences:
                from preferences import run as run_preferences
                run_preferences(preferences, probe, env, command, query, applications, artifacts)
            if openup:
                from openup import run as run_openup
                run_openup(openup, probe, env, command, query, applications, artifacts)
            if display_probe:
                def apply_heads(heads):
                    state = query("--display-state")
                    lease = display_request("apply", layout=heads, revision=state["revision"], timeout=5000)
                    assert lease["status"] == 1
                    assert display_request("confirm", token=lease["token"])["status"] == 2
                saved = [dict(head, scale=150) for head in original]
                live = [dict(head, scale=180) for head in original]
                apply_heads(saved)
                result = subprocess.run([display_probe, "--save-only"], env=env, capture_output=True, timeout=15)
                assert result.returncode == 0, result.stderr
                apply_heads(live)
                shell.kill(); shell.wait(timeout=5); start_workspace(restore_settings=True)
                assert all(h["scale"] == 150 for h in query("--display-state")["heads"]), "startup did not restore the confirmed profile"
                apply_heads(live)
                shell.kill(); shell.wait(timeout=5); start_workspace()
                assert all(h["scale"] == 180 for h in query("--display-state")["heads"]), "shell restart overwrote the live layout"
                apply_heads(original)
            def initial_windows():
                current = command("windows")
                return current if any(w["title"] == "Recycler" for w in current) else None
            windows = until(initial_windows, "initial native shell surfaces mapped")
            assert windows and all(not w["legacy"] and w["pid"] == shell.pid for w in windows)
            assert any(w["title"] == "Recycler" for w in windows)
            assert query("--open", "/tmp")["opened"]
            until(lambda: any(w["width"] > 200 and w["height"] > 100 for w in command("windows")),
                  "native file viewer")
            recycler = until(lambda: next((w for w in command("windows") if w["title"] == "Recycler" and
                                           w["x"] > 1000 and w["y"] > 1000), None), "Recycler position")
            primary_name = next(output["name"] for output in command("outputs")
                                if output["x"] <= recycler["x"] < output["x"] + output["width"])
            assert command(f"pointer {recycler['x'] + 32} {recycler['y'] + 32}")["ok"]
            assert command("button 272")["ok"]
            assert command("button 272")["ok"]
            panel = until(lambda: next((w for w in command("windows") if w["title"] == "Recycler" and
                                        w["width"] > 100), None), "native Recycler panel")
            desktop = display_request("desktop-state")
            assert desktop == dict(current=0, count=4)
            before_desktops = {w["id"]: (w["width"], w["height"]) for w in command("windows")}
            for key, index in ((3, 1), (4, 2), (2, 0)):
                for code, pressed in ((29, 1), (key, 1), (key, 0), (29, 0)):
                    assert command(f"key {code} {pressed}")["ok"]
                until(lambda: display_request("desktop-state")["current"] == index, "Workspace desktop state follows the compositor")
                current = command("windows")
                assert all(w["visible"] for w in current if w["style"] & 64), "Dock and Recycler must remain on every desktop"
                if index: assert all(not w["visible"] for w in current if w["width"] > 200)
                assert all((w["width"], w["height"]) == before_desktops[w["id"]] for w in current)
            viewer = next(w for w in command("windows") if w["title"].endswith("/tmp"))
            from desktop_settings import run as run_desktop_settings
            def restart_desktop_settings():
                shell.kill(); shell.wait(timeout=5); start_workspace()
            run_desktop_settings(command, query, artifacts, restart_desktop_settings)
            assert query("--open", "/tmp")["opened"]
            viewer = until(lambda: next((w for w in command("windows") if w["pid"] == shell.pid and
                w["title"].endswith("/tmp") and w["visible"]), None), "File Viewer after desktop preferences restart")
            assert command(f"focus {viewer['id']}")["ok"]
            assert command(f"pointer {viewer['x'] + 95} {viewer['y'] + 150}")["ok"]
            assert command("button 272")["ok"]
            until(lambda: shell.poll() is None and command("windows"), "native shelf icon selection")
            if gui_probe:
                def pin(name):
                    names = ("GtkProbe", "gtk-probe") if name == "GtkProbe" else (name,)
                    return next((w for w in command("windows") if w["pid"] == shell.pid and
                                 w["title"] in names and w["style"] & 64), None)
                def click_icon(icon):
                    assert command(f"pointer {icon['x'] + 32} {icon['y'] + 32}")["ok"]
                    assert command("button 272")["ok"]
                    assert command("button 272")["ok"]
                launcher = until(lambda: pin("WaylandProbe"), "native pinned launcher")
                assert (launcher["x"], launcher["y"]) == (recycler["x"], 64)
                overflow = until(lambda: pin("Overflow"), "overflow pin remains accessible in IconYard")
                assert overflow["presented"] and overflow["x"] != recycler["x"]
                click_icon(launcher)
                native = until(lambda: next((w for w in command("windows") if w["title"] == "WaylandProbe" and
                                              w["pid"] != shell.pid and w["width"] > 100), None), "Dock launches native application")
                dock_pids.add(native["pid"])
                def adopted_icon():
                    windows = command("windows")
                    icon = next((w for w in windows if w["pid"] == native["pid"] and w["style"] & 64), None)
                    placeholder = pin("WaylandProbe")
                    return icon if icon and placeholder and not placeholder["presented"] and (
                        icon["x"], icon["y"]) == (launcher["x"], launcher["y"]) else None
                until(adopted_icon, "running native app icon replaces its launcher")
                until(lambda: query("--application-state", "WaylandProbe")["active"], "native application activation state")
                assert command(f"focus {viewer['id']}")["ok"]
                until(lambda: not query("--application-state", "WaylandProbe")["active"], "native application resigns activation")
                assert command(f"focus {native['id']}")["ok"]
                until(lambda: query("--application-state", "WaylandProbe")["active"], "native application regains activation")
                from native_window_drag import check as check_native_window_drag
                native = check_native_window_drag(command, query, native, artifacts)
                for hide, shaded in (("application", False), ("others", False), ("application", True), ("others", True)):
                    original_size = native["width"], native["height"]
                    original_id = native["id"]
                    assert command(f"shade {original_id} {int(shaded)}")["ok"]
                    until(lambda: any(w["id"] == original_id and w["shaded"] == shaded for w in command("windows")),
                          "document shade state before hide")
                    if hide == "application": query("--application-action", "WaylandProbe", "hide")
                    else:
                        assert command(f"focus {viewer['id']}")["ok"]
                        assert query("--workspace-hide-others")["requested"]
                    until(lambda: query("--application-state", "WaylandProbe")["hidden"], "native application hides")
                    until(lambda: not any(w["pid"] == native["pid"] and w["width"] > 100 and w["visible"]
                                          for w in command("windows")), "hidden native application removes its documents from the scene")
                    click_icon(until(adopted_icon, "hidden native application retains its Dock icon"))
                    restored = until(lambda: next((w for w in command("windows") if w["pid"] == native["pid"] and
                        w["title"] == "WaylandProbe" and w["width"] > 100 and w["visible"]), None), "Dock icon unhides the existing native process")
                    native = restored
                    assert (native["width"], native["height"]) == original_size
                    assert native["id"] == original_id and native["shaded"] == shaded, "Hide/unhide lost the native window state"
                    until(lambda: not (state := query("--application-state", "WaylandProbe"))["hidden"] and state["active"],
                          "Dock unhide restores application activation")
                assert command(f"shade {native['id']} 0")["ok"]
                assert all(entry["Name"] != "WaylandProbe.GNUstep" for entry in query("--undocked")), \
                    "Pinned apps retain their Dock autostart policy instead of an undocked-session copy"
                from icon_placement import check as check_icon_placement, check_locked, check_mini, check_foreign
                def restart_icons():
                    shell.kill(); shell.wait(timeout=5)
                    start_workspace()
                check_icon_placement(command, query, native["pid"], artifacts, restart_icons)
                native = check_mini(command, query, native["pid"], artifacts)
                assert query("--open", "/tmp")["opened"]
                viewer = until(lambda: next((w for w in command("windows") if w["pid"] == shell.pid and
                    w["title"].endswith("/tmp")), None), "File Viewer restored after icon recovery tests")
                # A placeholder for an app without its own icon activates the same
                # process rather than launching another copy.
                if client:
                    foreign_launcher = until(lambda: pin("GtkProbe"), "GTK pinned launcher")
                    click_icon(foreign_launcher)
                    foreign = until(lambda: next((w for w in command("windows") if w["app_id"] in ("org.nextspace.GtkProbe", "gtk-probe")), None),
                                    "Dock launches GTK application")
                    dock_pids.add(foreign["pid"])
                    assert command(f"focus {native['id']}")["ok"]
                    click_icon(foreign_launcher)
                    until(lambda: any(w["id"] == foreign["id"] and w["focused"] for w in command("windows")),
                          "Dock activates existing GTK application")
                    assert len({w["pid"] for w in command("windows") if w["app_id"] == foreign["app_id"]}) == 1
                    check_foreign(command, query, lambda: pin("GtkProbe"), foreign["pid"], artifacts)
                    assert command(f"close {foreign['id']}")["ok"]
                    until(lambda: not any(w["pid"] == foreign["pid"] for w in command("windows")), "GTK Dock client closes")
                    dock_pids.remove(foreign["pid"])
                preferences = query("--dock-preferences")
                running_arguments = [os.fsdecode(value) for value in
                    Path(f"/proc/{native['pid']}/cmdline").read_bytes().split(b"\0") if value]
                assert preferences["name"] == "WaylandProbe.GNUstep" and \
                    shlex.split(preferences["command"]) == running_arguments, preferences
                assert query("--dock-preferences", "/bin/false")["locked"]
                check_locked(command, adopted_icon)
                assert query("--dock-level", "0")["level"] == 0
                until(lambda: all(w["level"] == 0 for w in command("windows") if w["style"] & 64),
                      "normal Dock level reaches the native running icon")
                assert query("--dock-level", "5")["level"] == 5
                until(lambda: adopted_icon() and adopted_icon()["level"] == 21,
                      "keep-on-top Dock level reaches the native running icon")
                assert command("pointer 500 500")["ok"]
                assert query("--dock-level", "-1000")["automatic_enabled"]
                until(lambda: adopted_icon() and adopted_icon()["level"] == 0, "automatic Dock uses the normal stacking level")
                # Partially cover the running app icon. Hover its exposed half,
                # then inspect the covered half without moving the pointer.
                icon = adopted_icon()
                overlap = (icon["x"] + 16, icon["y"] + 32)
                assert command(f"move {native['id']} {icon['x'] - native['width'] + 32} {icon['y']}")["ok"]
                assert command(f"focus {native['id']}")["ok"]
                until(lambda: command(f"hit {overlap[0]} {overlap[1]}")["id"] == native["id"],
                      "normal Dock begins below the overlapping document")
                assert command(f"pointer {icon['x'] + 48} {icon['y'] + 32}")["ok"]
                until(lambda: command(f"hit {overlap[0]} {overlap[1]}")["id"] == icon["id"],
                      "automatic Dock raises over a document after pointer entry")
                assert command("pointer 500 500")["ok"]
                until(lambda: command(f"hit {overlap[0]} {overlap[1]}")["id"] == native["id"],
                      "automatic Dock lowers after pointer exit")
                assert query("--dock-level", "5")["level"] == 5
                assert query("--dock-action", "collapse")["title"] == "Uncollapse"
                work_areas()
                until(lambda: all(pin(name) and not pin(name)["presented"] for name in
                      (["WaylandProbe", "GtkProbe"] if client else ["WaylandProbe"])),
                      "Dock collapse preserves running applications")
                shell.kill(); shell.wait(timeout=5)
                start_workspace()
                until(lambda: all(pin(name) and not pin(name)["presented"] for name in
                      (["WaylandProbe", "GtkProbe"] if client else ["WaylandProbe"])), "Dock collapse survives Workspace restart")
                preferences = query("--dock-preferences")
                assert preferences["command"] == "/bin/false" and preferences["locked"], preferences
                assert query("--dock-action", "expand")["title"] == "Collapse"
                until(adopted_icon, "Workspace restart adopts a running pinned icon")
                assert query("--dock-action", "hide")["title"] == "Show"
                work_areas(dock=False)
                until(lambda: all(not w["presented"] for w in command("windows") if
                      (w["pid"] == native["pid"] and w["style"] & 64) or
                      (w["pid"] == shell.pid and w["style"] & 64 and w["title"] != "Overflow")),
                      "hidden Dock excludes native app icons without closing them")
                assert pin("Overflow")["presented"]
                assert query("--dock-action", "hide-yard")["title"] == "Show"
                work_areas(dock=False, yard=False)
                until(lambda: not pin("Overflow")["presented"], "IconYard presentation independent of Dock")
                assert query("--dock-action", "show")["title"] == "Hide"
                work_areas(yard=False)
                until(adopted_icon, "Dock presentation restores the running app icon")
                assert not pin("Overflow")["presented"]
                assert query("--dock-action", "show-yard")["title"] == "Hide"
                work_areas()
                until(lambda: pin("Overflow")["presented"], "IconYard presentation restored")
                assert command(f"close {native['id']}")["ok"]
                until(lambda: not any(w["pid"] == native["pid"] for w in command("windows")), "native Dock client closes")
                dock_pids.remove(native["pid"])
                until(lambda: pin("WaylandProbe") and pin("WaylandProbe")["presented"], "launcher returns after application exits")
            if client:
                for index in range(2):
                    with (artifacts / f"client-{index}.log").open("w") as log:
                        application = subprocess.Popen([client], env=dict(env, GDK_BACKEND="wayland"),
                            stdout=log, stderr=log)
                    applications.append(application)
                    until(lambda: any(application.pid in item["pids"] for item in query("--list")),
                          "native foreign application registration")
                grouped = next(item for item in query("--list") if applications[0].pid in item["pids"])
                assert set(grouped["pids"]) == {app.pid for app in applications}
                if gui_probe:
                    group = [w for w in command("windows") if w["pid"] in {app.pid for app in applications}]
                    minimized = group[0]
                    assert command(f"minimize {minimized['id']} 1")["ok"]
                    workspace_window = next(w for w in command("windows") if w["pid"] == shell.pid and w["accepts_focus"])
                    assert command(f"focus {workspace_window['id']}")["ok"]
                    assert query("--workspace-hide-others")["requested"]
                    until(lambda: all(not w["presented"] for w in command("windows") if
                        w["pid"] in {app.pid for app in applications}), "Workspace hides the complete foreign group")
                    click_icon(until(lambda: pin("GtkProbe"), "foreign group Dock launcher"))
                    until(lambda: all(w["presented"] for w in command("windows") if
                        w["pid"] in {app.pid for app in applications}), "Dock restores the complete foreign group")
                    assert next(w for w in command("windows") if w["id"] == minimized["id"])["minimized"], \
                        "Application unhide must preserve independent miniaturization"
                    assert {w["pid"] for w in command("windows") if w["app_id"] == group[0]["app_id"]} == {app.pid for app in applications}
                    assert command(f"minimize {minimized['id']} 0")["ok"]
                retained = {w["id"]: (w["pid"], w["x"], w["y"], w["width"], w["height"])
                            for w in command("windows") if w["pid"] in {a.pid for a in applications}}
                shell.kill(); shell.wait(timeout=5)
                start_workspace()
                assert all(application.poll() is None for application in applications)
                recovered = {w["id"]: (w["pid"], w["x"], w["y"], w["width"], w["height"])
                             for w in command("windows") if w["pid"] in {a.pid for a in applications}}
                assert recovered == retained, "Restarting Workspace must preserve other clients and window geometry"
                until(lambda: any(set(item["pids"]) == {a.pid for a in applications}
                                  for item in query("--list")), "Workspace recovers existing client process groups")
                for index, application in enumerate(applications):
                    window = until(lambda: next((w for w in command("windows") if w["pid"] == application.pid), None),
                                   "native foreign window")
                    assert command(f"focus {window['id']}")["ok"]
                    until(lambda: application.pid in query("--active").get("pids", []), "native active application")
                    assert command(f"close {window['id']}")["ok"]
                    application.wait(timeout=10)
                    assert application.returncode == 0
                    until(lambda: all(application.pid not in item["pids"] for item in query("--list")),
                          "native foreign application removal")
                    if index == 0:
                        assert any(applications[1].pid in item["pids"] for item in query("--list"))
            assert query("--open", "/tmp")["opened"]
            # Resize output density, keeping the same mapped Workspace document,
            # menu and Recycler surfaces with appropriately sized submitted PNGs.
            document = until(lambda: next((w for w in command("windows") if w["title"].endswith("/tmp")), None),
                             "opened document mapped after Workspace restart")
            scales = []
            for scale in (120, 150, 180, 210, 240):
                for output in command("outputs"):
                    assert command(f"test-scale {output['name']} {scale} 10000")["ok"]
                    assert command("confirm")["ok"]
                def density_ready():
                    current = command("windows")
                    for window in current:
                        expected = tuple((window[key] * scale + 60) // 120 for key in ("width", "height"))
                        if (window["buffer_width"], window["buffer_height"]) != expected:
                            return False
                        image = artifacts / f"window-{window['client_id']}-{scale}.png"
                        if not image.exists():
                            return False
                        with Image.open(image) as pixels:
                            if pixels.size != expected or pixels.convert("RGB").getextrema() == ((0, 0),) * 3:
                                return False
                    return current
                current = until(density_ready, "Workspace buffers and submitted artwork at target density")
                retained = next(w for w in current if w["id"] == document["id"])
                assert (retained["width"], retained["height"]) == (document["width"], document["height"])
                scales.append(dict(scale=scale, windows=current))
            def desktop_icons():
                output = next(o for o in command("outputs") if o["name"] == primary_name)
                icons = [w for w in command("windows") if w["pid"] == shell.pid and w["style"] & 64]
                return output, next((w for w in icons if w["client_id"] == 1), None), next(
                    (w for w in icons if w["title"] == "Recycler"), None)
            def placed_icons():
                output, workspace_icon, recycler_icon = desktop_icons()
                if not workspace_icon or not recycler_icon: return None
                return (workspace_icon, recycler_icon) if (
                    (workspace_icon["x"], workspace_icon["y"]) == (output["x"] + output["width"] - 64, output["y"]) and
                    (recycler_icon["x"], recycler_icon["y"]) == (output["x"] + output["width"] - 64,
                                                                         output["y"] + output["height"] - 64)) else None
            # Public wl_output updates and the private output inventory use
            # separate connections. Neither arrival order may leave old Dock
            # geometry behind. Repeated changes exercise both dispatch orders.
            mode_changes = []
            for width, height in [(1800, 1400), (1760, 1360), (1840, 1440)] * 5 + [(1800, 1400)]:
                assert command(f"resize-output {primary_name} {width} {height}")["ok"]
                workspace_icon, recycler_icon = until(placed_icons,
                    "desktop icons follow a resolution change without moving document surfaces")
                mode_changes.append(dict(width=width, height=height,
                    workspace=workspace_icon, recycler=recycler_icon))
            (artifacts / "icon-mode-changes.json").write_text(json.dumps(mode_changes, indent=2) + "\n")
            for output in command("outputs"):
                position = (-1400, -1200) if output["name"] == primary_name else (-400, -1000)
                assert command(f"output-position {output['name']} {position[0]} {position[1]}")["ok"]
            workspace_icon, recycler_icon = until(placed_icons, "desktop icon placement on negative-origin outputs")
            assert command(f"pointer {recycler_icon['x'] + 32} {recycler_icon['y'] + 32}")["ok"]
            assert command("button 272")["ok"]
            assert command("button 272")["ok"]
            until(lambda: any(w["title"] == "Recycler" and w["width"] > 100 and w["focused"]
                              for w in command("windows")), "Recycler input on a negative-origin display")
            if gui_probe:
                from workspace_checkmark import run as checkmark
                checkmark(command, query, artifacts / "checkmark")
            (artifacts / "results.json").write_text(json.dumps(dict(windows=command("windows"),
                recycler_panel=panel, applications=query("--list"),
                scales=scales, native_foreign_instances=len(applications), workspace_starts=starts,
                passed=["native startup without DISPLAY", "private shell capability", "file viewer open",
                        "native Recycler icon double-click", "native shelf icon input",
                        "negative-origin icon placement and input", "revision-checked output settings RPC",
                        "transaction tokens and requester-exit timeout rollback"] + ([
                        "stale display requests preserve the completed rollback result",
                        "native maximized title-bar dragging and exact unzoom at five densities plus Escape",
                        "pinned native and GTK launchers", "running native icon adoption", "Dock collapse persistence",
                        "native Dock preferences edit and reload", "normal and keep-on-top Dock levels", "automatic Dock raise and lower with real overlapping windows",
                        "independent Dock and IconYard visibility and work areas", "Dock icon recovery after Workspace restart",
                        "native application activation, hide and Dock unhide in the same process",
                        "complete foreign group unhide preserves independent minimization",
                        "native icon drag thresholds, Escape, pin/unpin and slot swaps at five densities",
                        "locked Dock pins, persistent free IconYard placement and live-grab shell recovery",
                        "miniwindow drag and double-click restoration at three densities",
                        "foreign IconYard group activation and pinning without a new process"
                    ] if gui_probe else [])), indent=2) + "\n")
            print("Native Workspace startup, file viewer and Recycler: PASS")
            if power_probe:
                from workspace_power import check
                check(power_probe,env,command,lambda:shell,start_workspace,probe,artifacts/'power')
        except BaseException:
            try:
                (artifacts / "failure.json").write_text(json.dumps(dict(
                    outputs=command("outputs"), windows=command("windows"),
                    display_requests=display_requests[-32:],
                    workspace_exit=shell.poll() if shell else None), indent=2) + "\n")
            except (OSError, ValueError):
                pass
            raise
        finally:
            if previous_profile is not None:
                profile.parent.mkdir(parents=True, exist_ok=True); profile.write_bytes(previous_profile)
            else:
                profile.unlink(missing_ok=True)
            for pid in dock_pids:
                try: os.kill(pid, signal.SIGTERM)
                except ProcessLookupError: pass
            def stop(process):
                if process and process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait(timeout=5)
            for application in applications: stop(application)
            # Avoid interactive logout and still clean up after an unresponsive
            # test shell; its timeout must not hide the original failure.
            stop(shell)
            stop(server)
            assert server.returncode == 0, f"Compositor exited with {server.returncode}"
            server.stdout.close(); control.close(); broker.close()
            subprocess.run([probe, "--cleanup-registry"], env=env, capture_output=True, timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--compositor", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--probe", required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--preferences", help="Native Preferences application")
    parser.add_argument("--openup", help="Native OpenUp application")
    parser.add_argument("--application-directory", type=Path, help="Isolated directory containing staged app bundles")
    parser.add_argument("--display-probe", help="Public SystemKit display model fixture")
    parser.add_argument("--alert-probe", help="DesktopKit modal default-action fixture")
    parser.add_argument("--gui-probe", help="Native application for pinned Dock lifecycle tests")
    parser.add_argument("--client", help="Optional GTK comparison application")
    parser.add_argument("--power-probe", help="Owned fake logind fixture; requires an explicitly isolated power-test bus")
    arguments = parser.parse_args()
    run(arguments.compositor, arguments.workspace, arguments.probe, arguments.artifacts, arguments.client, arguments.gui_probe,
        arguments.display_probe, arguments.preferences, arguments.openup, arguments.application_directory, arguments.alert_probe,arguments.power_probe)
