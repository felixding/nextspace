#!/usr/bin/env python3
"""Exercise the production output transaction on the private shell connection."""
import argparse
import copy
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import tempfile
from integration import until
from shell import Shell


class WorkspaceOutputs(Shell):
    """Drive the actual Objective-C client with the same transaction scenarios."""
    def send(self, command):
        words = command.split()
        if words[0] == "configure": self.proposal = dict(revision=int(words[1]), layout=[])
        elif words[0] == "head":
            self.proposal["layout"].append(dict(zip(("id", "enabled", "primary", "width", "height",
                "refresh", "scale", "transform", "x", "y"), map(int, words[1:]))))
        elif words[0] == "input": super().send(json.dumps(dict(action="input-state")))
        elif words[0] == "background":
            request = dict(action="background")
            if len(words) == 4: request["color"] = dict(zip(("Red", "Green", "Blue"), (int(v) / 1000 for v in words[1:])))
            super().send(json.dumps(request))
        elif words[0] in ("pointer", "keyboard"):
            if words[0] == "pointer": settings = dict(speed=float(words[1]), profile=int(words[2]))
            else:
                settings = dict(zip(("model", "layout", "variant", "options"),
                    (value if value != "_" else "" for value in words[1:5])))
                settings.update(dict(zip(("delay", "rate", "numlock"), map(int, words[5:]))))
            super().send(json.dumps(dict(action=words[0], settings=settings)))
        elif words[0] in ("test", "apply", "confirm", "cancel"):
            request = dict(self.proposal, action=words[0])
            if words[0] == "apply": request["timeout"] = int(words[1])
            super().send(json.dumps(request))
        else: super().send(command)


def run(compositor, shell_probe, registry_probe, artifacts, workspace_shell_probe=None, mode=0, gui_probe=None, readonly_probe=None, input_settings=False, state_client=None):
    artifacts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nextspace-outputs-") as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS="headless",
                   WLR_HEADLESS_OUTPUTS="2", WLR_RENDERER="pixman", NEXTSPACE_SESSION_ID="test-" + Path(runtime).name)
        for key in ("DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET"): env.pop(key, None)
        control, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        broker, broker_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        control.settimeout(5)
        shells, clients, checks = [], [], []
        state_clients = {}
        work_area_records = []
        zoom_records = []
        with (artifacts / "compositor.log").open("w") as log:
            server = subprocess.Popen([compositor, "-c", str(child.fileno()), "-S", str(broker_child.fileno())],
                pass_fds=[child.fileno(), broker_child.fileno()], env=env, stdout=subprocess.PIPE,
                stderr=log, text=True)
        child.close(); broker_child.close()

        def command(value):
            control.sendall(value.encode()); return json.loads(control.recv(65536))

        def connect():
            shell = (WorkspaceOutputs(workspace_shell_probe, broker, env, artifacts, len(shells),
                version=7, workspace_mode=mode) if workspace_shell_probe else
                Shell(shell_probe, broker, env, artifacts, len(shells), version=13 if state_client else 9 if input_settings else 7))
            shells.append(shell)
            shell.wait(lambda: shell.output_batches, "complete output inventory")
            return shell

        def snapshot():
            before = shell.output_batches
            shell.send("outputs")
            shell.wait(lambda: shell.output_batches > before, "fresh output snapshot")
            heads = copy.deepcopy(shell.outputs)
            check_states(heads)
            return heads

        def check_states(heads):
            for title, (process, flag) in state_clients.items():
                def window():
                    assert process.poll() is None, f"{title} exited: {process.returncode}"
                    return next((w for w in command("windows") if w["title"] == title and w[flag]), None)
                w = until(window, title + " mapped")
                # A fully occluded client can defer drawing. Bring each state
                # into view before checking its submitted backing pixels.
                assert command(f"focus {w['id']}")["ok"]
                def matches():
                    w = window()
                    if not w: return False
                    matching = [h for h in heads.values() if h["enabled"] and
                        tuple(w[k] for k in ("x", "y", "width", "height")) ==
                        tuple(h[k] for k in (("work_x", "work_y", "work_width", "work_height") if flag == "maximized"
                            else ("x", "y", "logical_width", "logical_height")))]
                    return any((w["buffer_width"], w["buffer_height"]) == tuple(
                        (w[k] * h["scale"] + 60) // 120 for k in ("width", "height")) for h in matching)
                until(matches, title + " geometry and backing density follow the complete output layout")
            if state_clients and gui_probe:
                probe = subprocess.run([gui_probe, "-WorkAreaProbe", "YES", "-GSBackend", "libgnustep-wayland",
                    "-NSUseRunningCopy", "NO"], env=env, capture_output=True, text=True, check=True, timeout=15)
                areas = json.loads(probe.stdout)
                enabled = [h for h in heads.values() if h["enabled"]]
                bottom = max([0] + [h["y"] + h["logical_height"] for h in enabled])
                expected = [dict(frame=[h["x"], bottom - h["y"] - h["logical_height"], h["logical_width"], h["logical_height"]],
                    work=[h["work_x"], bottom - h["work_y"] - h["work_height"], h["work_width"], h["work_height"]])
                    for h in enabled]
                assert sorted(areas, key=lambda a: a["frame"]) == sorted(expected, key=lambda a: a["frame"]), (areas, expected)
                work_area_records.append(areas)

        def configure(heads, revision=None):
            shell.send(f"configure {shell.output_revision if revision is None else revision}")
            for h in heads:
                shell.send("head " + " ".join(str(h[k]) for k in (
                    "id", "enabled", "primary", "width", "height", "refresh", "scale", "transform", "x", "y")))

        def result(request, status):
            before = len(shell.configuration_results)
            shell.send(request)
            shell.wait(lambda: len(shell.configuration_results) > before, request + " result")
            actual = shell.configuration_results[-1]
            assert actual["status"] == status, actual
            return actual

        def state(heads):
            return {h["id"]: {k: h[k] for k in ("id", "enabled", "primary", "width", "height", "refresh",
                    "scale", "transform", "x", "y")} for h in heads.values()}

        def native_window():
            return next((w for w in command("windows") if w["title"] == "WaylandProbe" and w["accepts_focus"]), None)

        def native_zoom(heads):
            before = native_window()
            assert command(f"focus {before['id']}")["ok"]
            def key():
                assert command("key 88 1")["ok"]  # F12 invokes the real NSWindow zoom API.
                assert command("key 88 0")["ok"]
            if not zoom_records:
                def events():
                    return [json.loads(line) for line in (artifacts / "native.log").read_text().splitlines()
                        if line.startswith('{"event":')]
                assert command("key 87 1")["ok"]; assert command("key 87 0")["ok"]
                until(lambda: any(e["event"] == "zoom-veto" and e["denied"] for e in events()), "AppKit delegate veto enabled")
                key()
                event = until(lambda: next((e for e in events() if e["event"] == "zoom-request"), None), "vetoed zoom completed")
                assert not event["zoomed"] and not native_window()["maximized"], event
                assert command("key 87 1")["ok"]; assert command("key 87 0")["ok"]
                until(lambda: any(e["event"] == "zoom-veto" and not e["denied"] for e in events()), "AppKit delegate veto released")
            key()
            def maximized():
                w = native_window()
                return w if w and w["maximized"] and any(h["enabled"] and
                    tuple(w[k] for k in ("x", "y", "width", "height")) ==
                    tuple(h[k] for k in ("work_x", "work_y", "work_width", "work_height")) and
                    tuple(w["buffer_" + k] for k in ("width", "height")) == tuple(
                        (w[k] * h["scale"] + 60) // 120 for k in ("width", "height")) for h in heads.values()) else None
            enlarged = until(maximized, "AppKit zoom uses native compositor maximization and work-area backing pixels")
            key()
            until(lambda: not native_window()["maximized"] and all(native_window()[k] == before[k]
                for k in ("x", "y", "width", "height")), "AppKit unzoom restores its original floating frame")
            zoom_records.append(dict(before=before, maximized=enlarged, restored=native_window()))

        def restored(expected):
            until(lambda: state(snapshot()) == state(expected), "previous complete layout restored")

        try:
            assert select.select([server.stdout], [], [], 10)[0], "No compositor socket"
            env["WAYLAND_DISPLAY"] = server.stdout.readline().strip().split("=", 1)[1]
            if readonly_probe:
                readonly = subprocess.run([readonly_probe, "--readonly", "-GSBackend", "libgnustep-wayland",
                    "-NSUseRunningCopy", "NO"], env=env, capture_output=True, text=True, timeout=15)
                (artifacts / "readonly-model.log").write_text(readonly.stdout + readonly.stderr)
                assert readonly.returncode == 0, readonly.stdout + readonly.stderr
                checks.append("public SystemKit bootstrap without Workspace, X11 or a settings capability")
            shell = connect()
            initial = snapshot()
            assert len(initial) == 2 and sum(h["primary"] for h in initial.values()) == 1
            assert all(h["modes"] for h in initial.values())
            # The ordinary native connection has no output-setting capability.
            subprocess.run([registry_probe], env=env, check=True, capture_output=True, timeout=10)
            checks.append("private output authority and complete inventory")
            if gui_probe:
                with (artifacts / "native.log").open("w") as log:
                    clients.append(subprocess.Popen([gui_probe, "-GSBackend", "libgnustep-wayland",
                        "-GSTheme", "NextSpace", "-NSUseRunningCopy", "NO",
                        *( ["-ZoomProbe", "YES"] if state_client else [])], env=env, stdout=log, stderr=log))
                until(lambda: native_window(), "native application remains alive during output transactions")
            if input_settings:
                from input_settings import run as run_inputs
                checks.append(run_inputs(shell, command, native_window if gui_probe else None,
                                         artifacts / "native.log" if gui_probe else None))
                def background(request):
                    before = len(shell.events)
                    shell.send(request)
                    return shell.wait(lambda: next((event for event in shell.events[before:] if event["event"] == "background"), None),
                                      "desktop background reply")
                original_background = background("background")
                for rgb in ((0, 0, 0), (1000, 1000, 1000), (500, 250, 750)):
                    color = background("background " + " ".join(map(str, rgb)))
                    actual = command("background-state")
                    for key, value in zip(("Red", "Green", "Blue"), rgb):
                        assert abs(color[key] - value / 1000) <= 1 / 256
                        assert abs(actual[key] - color[key]) <= 1 / 256
                previous = command("background-state")
                background("background -500 0 0")
                assert command("background-state") == previous
                background("background " + " ".join(str(round(original_background[key] * 1000)) for key in ("Red", "Green", "Blue")))
                checks.append("validated desktop color reaches the compositor scene")
            if state_client:
                first = next(iter(initial.values()))
                shell.send(f"insets {first['id']} 0 0 4096 4096")
                def usable_fallback():
                    heads = snapshot()
                    h = heads[first["id"]]
                    return (h.get("work_x"), h.get("work_y"), h.get("work_width"), h.get("work_height")) == (
                        h["x"], h["y"], h["logical_width"], h["logical_height"])
                until(usable_fallback, "oversized reservations preserve a usable output")
                for h in initial.values(): shell.send(f"insets {h['id']} 7 11 67 64")
                def reserved():
                    heads = snapshot()
                    return heads if all((h.get("work_x"), h.get("work_y"), h.get("work_width"), h.get("work_height")) == (
                        h["x"] + 7, h["y"] + 11, h["logical_width"] - 74, h["logical_height"] - 75)
                        for h in heads.values()) else None
                initial = until(reserved, "complete work-area reservations")
                revision = shell.output_revision
                for h in initial.values():
                    assert (h["work_x"], h["work_y"], h["work_width"], h["work_height"]) == (
                        h["x"] + 7, h["y"] + 11, h["logical_width"] - 74, h["logical_height"] - 75)
                    for values in ("-1 0 0 0", "0 0 4097 0"):
                        shell.send(f"insets {h['id']} {values}")
                assert snapshot() == initial and shell.output_revision == revision
                checks.append("logical work areas, invalid inset rejection and unchanged output revision")
                state_env = dict(env, GDK_BACKEND="wayland", GSK_RENDERER="cairo", GTK_A11Y="none")
                for flag, argument in (("maximized", "--maximize"), ("fullscreen", "--fullscreen")):
                    title = "Output-" + flag
                    with (artifacts / (title + ".log")).open("w") as log:
                        process = subprocess.Popen([state_client, argument, "--title", title],
                            env=state_env, stdout=log, stderr=log)
                    clients.append(process)
                    state_clients[title] = process, flag
                check_states(initial)
            heads = sorted(copy.deepcopy(list(initial.values())), key=lambda h: h["x"])
            for turn in range(8):
                scales = ((120, 240), (150, 180), (180, 240), (210, 150), (240, 120))[turn % 5]
                snapshot()
                proposal = copy.deepcopy(heads)
                for i, h in enumerate(proposal):
                    h.update(scale=scales[i], transform=turn if i else 7 - turn, primary=i == 1,
                             x=-1600 if not i else -300, y=-200)
                    h["primary"] = int(h["primary"])
                configure(proposal)
                result("test", 0)
                restored(initial)  # Test performs no commit or placement.
                result("apply 15000", 1)
                applied = snapshot()
                assert state(applied) == state({h["id"]: h for h in proposal})
                if input_settings:
                    desktop = command("background-state")
                    left = min(h["x"] for h in applied.values()); top = min(h["y"] for h in applied.values())
                    right = max(h["x"] + h["logical_width"] for h in applied.values())
                    bottom = max(h["y"] + h["logical_height"] for h in applied.values())
                    assert tuple(desktop[k] for k in ("x", "y", "width", "height")) == (left, top, right - left, bottom - top)
                for h in applied.values():
                    w, ht = h["width"], h["height"]
                    if h["transform"] % 2: w, ht = ht, w
                    assert (h["logical_width"], h["logical_height"]) == (
                        int(w * 120 / h["scale"]), int(ht * 120 / h["scale"]))
                if gui_probe:
                    target = next(h for h in applied.values() if h["primary"])
                    window = native_window()
                    assert command(f"move {window['id']} {target['x'] + 10} {target['y'] + 10}")["ok"]
                    def native_density():
                        w = native_window()
                        scale = target["scale"]
                        return w and (w["width"], w["height"]) == (801, 601) and (
                            w["buffer_width"], w["buffer_height"]) == (
                            (801 * scale + 60) // 120, (601 * scale + 60) // 120)
                    until(native_density, "native redraw after a complete rotated output transaction")
                    if state_client: native_zoom(applied)
                    window = native_window()
                    assert command(f"focus {window['id']}")["ok"]
                    assert command(f"pointer {window['x'] + 200} {window['y'] + 300}")["ok"]
                    assert command("button 272")["ok"]
                result("cancel", 3)
                restored(initial)
            checks.append("all five scales, mixed density, rotation, primary and negative origins")

            # A committed modeset and disabled head can still be reverted.
            proposal = copy.deepcopy(heads)
            proposal[0].update(width=1921, height=1081, refresh=75000, scale=150)
            proposal[1].update(enabled=0, primary=0)
            configure(proposal); result("apply 1000", 1)
            shell.wait(lambda: shell.configuration_results[-1]["status"] == 3, "server timeout rollback")
            restored(initial)
            checks.append("mode, disable, re-enable and compositor deadline")

            # Reject incomplete, duplicate, dark, invalid and stale layouts.
            bad_layouts = [heads[:1], [heads[0], heads[0]],
                [dict(h, enabled=0, primary=0) for h in heads],
                [dict(h, primary=1) for h in heads],
                [dict(h, scale=0) for h in heads], [dict(h, transform=8) for h in heads],
                [dict(h, x=65537) for h in heads], [dict(h, id=4294967295) for h in heads]]
            for bad in bad_layouts:
                snapshot(); configure(bad); result("apply 15000", 4); restored(initial)
            snapshot(); configure(heads, revision=shell.output_revision - 1)
            result("test", 4); restored(initial)
            checks.append("incomplete, duplicate, dark, invalid and stale proposals rejected")

            for partial in (1, 2):
                assert command(f"fail-output-commit {partial}")["ok"]
                configure(proposal); result("apply 15000", 4); restored(initial)
            checks.append("injected partial backend commits restore the complete previous layout")
            configure(proposal); result("apply 15000", 1)
            shell.send("destroy-config"); restored(initial)
            checks.append("configuration destruction rolls back")
            configure(proposal); result("apply 15000", 1)
            shell.process.kill(); shell.process.wait(timeout=5)
            shell = connect(); restored(initial)
            checks.append("shell crash rolls back while compositor survives")

            # Confirm keeps the complete layout after the settings object dies.
            proposal = copy.deepcopy(heads)
            proposal[0].update(scale=180, x=-800, y=-400)
            configure(proposal); result("apply 15000", 1); result("confirm", 2)
            shell.send("destroy-config")
            confirmed = snapshot()
            assert state(confirmed) == state({h["id"]: h for h in proposal})
            shell.process.kill(); shell.process.wait(timeout=5)
            shell = connect(); assert state(snapshot()) == state(confirmed)
            checks.append("confirmed layout survives object and shell replacement")

            # Hotplug aborts an unconfirmed change and restores surviving heads.
            configure(heads); result("apply 15000", 1)
            removed = heads[1]
            assert command(f"remove-output {removed['name']}")["ok"]
            shell.wait(lambda: shell.configuration_results[-1]["status"] == 3, "hotplug abort")
            remaining = snapshot()
            assert len(remaining) == 1
            assert next(iter(remaining.values()))["scale"] == 180
            assert next(iter(remaining.values()))["enabled"]
            assert command("add-output")["ok"]
            shell.wait(lambda: len(shell.outputs) == 2, "hotplug inventory")
            assert removed["id"] not in shell.outputs, "IDs must never alias an earlier head"
            checks.append("hotplug rollback and non-reused head IDs")
            # The previous single enabled head disappears during a new test.
            # Rollback must enable a surviving head, even if it used to be off.
            both = list(snapshot().values())
            single = [dict(h, enabled=int(i == 1), primary=int(i == 1)) for i, h in enumerate(both)]
            configure(single); result("apply 15000", 1); result("confirm", 2); snapshot()
            configure([dict(h, enabled=1, primary=int(i == 0)) for i, h in enumerate(both)])
            result("apply 15000", 1)
            assert command(f"remove-output {both[1]['name']}")["ok"]
            shell.wait(lambda: shell.configuration_results[-1]["status"] == 3, "usable fallback after hotplug")
            survivor = next(iter(snapshot().values()))
            assert survivor["enabled"] and survivor["primary"]
            checks.append("hotplug preserves a usable head when the previous primary disappears")
            assert command("add-output")["ok"]
            shell.wait(lambda: len(shell.outputs) == 2, "ordinary hotplug without a settings preview")
            added = next(h for h in snapshot().values() if h["id"] != survivor["id"])
            if gui_probe:
                w = native_window()
                assert command(f"move {w['id']} {added['x'] + 10} {added['y'] + 10}")["ok"]
                until(lambda: native_window()["x"] == added["x"] + 10, "native window on the added head")
            assert command(f"remove-output {added['name']}")["ok"]
            if gui_probe:
                until(lambda: native_window()["x"] != added["x"] + 10,
                      "native window recovered after ordinary output removal")
            checks.append("ordinary hotplug recovers windows without a pending transaction")
            snapshot()
            if state_clients:
                checks.append("maximized and fullscreen native windows retain output bounds and density through rotation, rollback and hotplug")
            if gui_probe:
                entries = [json.loads(line) for line in (artifacts / "native.log").read_text().splitlines()
                           if line.startswith('{"event":')]
                clicks = [e for e in entries if e["event"] == "click"]
                assert len(clicks) == 8 and all((e["x"], e["y"]) == (200, 301) for e in clicks), clicks
                assert clients[0].poll() is None and native_window()
                checks.append("native logical size, backing density, input and client survival during rotation/rollback/hotplug")
                if zoom_records: checks.append("AppKit zoom/maximize and exact unzoom restoration through rotated mixed-density layouts")
            (artifacts / "results.json").write_text(json.dumps(dict(initial=initial, confirmed=confirmed,
                checks=checks, work_areas=work_area_records, native_zoom=zoom_records), indent=2) + "\n")
            print("Output inventory, complete transactions, rotation, confirmation and failure rollback: PASS")
        except BaseException:
            if server.poll() is None:
                (artifacts / "failure.json").write_text(json.dumps(dict(windows=command("windows"),
                    outputs=command("outputs"), checks=checks), indent=2) + "\n")
            raise
        finally:
            for owner in shells: owner.stop()
            for client in clients:
                if client.poll() is None: client.terminate(); client.wait(timeout=5)
            if server.poll() is None: server.terminate(); server.wait(timeout=5)
            assert server.returncode == 0, f"Compositor exited with {server.returncode}"
            server.stdout.close(); control.close(); broker.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("compositor", "shell-probe", "registry-probe"): parser.add_argument("--" + name, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--workspace-shell-probe")
    parser.add_argument("--gui-probe")
    parser.add_argument("--readonly-probe")
    parser.add_argument("--input-settings", action="store_true")
    parser.add_argument("--state-client")
    parser.add_argument("--mode", type=int, default=0, choices=range(4))
    args = parser.parse_args()
    run(args.compositor, args.shell_probe, args.registry_probe, args.artifacts, args.workspace_shell_probe, args.mode, args.gui_probe, args.readonly_probe, args.input_settings, args.state_client)
