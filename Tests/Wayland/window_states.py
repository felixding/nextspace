#!/usr/bin/env python3
"""Drive standard maximize/fullscreen requests through GTK on Wayland."""
import argparse
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import tempfile
from contextlib import contextmanager
from integration import read_json_lines, until
from shell import Shell


def run(compositor, client, artifacts, registry_probe=None, shell_probe=None):
    artifacts.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="nextspace-window-states-") as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS="headless",
                   WLR_HEADLESS_OUTPUTS="2", WLR_RENDERER="pixman", GSK_RENDERER="cairo",
                   GTK_A11Y="none", GDK_BACKEND='wayland')
        for name in ("DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET"):
            env.pop(name, None)
        control, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        broker, broker_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        control.settimeout(5)
        shell = None
        with (artifacts / "compositor.log").open("w") as log:
            server = subprocess.Popen([compositor, "-d", "-c", str(child.fileno()),
                "-S", str(broker_child.fileno())],
                pass_fds=[child.fileno(), broker_child.fileno()], env=env, stdout=subprocess.PIPE, stderr=log, text=True)
        child.close(); broker_child.close()
        records = []

        def command(value):
            control.sendall(value.encode())
            return json.loads(control.recv(65536))

        def output(name):
            return next(o for o in command("outputs") if o["name"] == name)

        def bounds(name, maximized=False):
            h = output(name)
            return dict(h, **{k: h["work_" + k] for k in ("x", "y", "width", "height")}) if maximized else h

        def reserve(name, enabled):
            if not shell: return
            h = next(h for h in shell.outputs.values() if h["name"] == name)
            shell.send(f"insets {h['id']} 0 0 {67 if enabled else 0} {64 if enabled else 0}")
            until(lambda: output(name)["work_width"] == output(name)["width"] - (67 if enabled else 0),
                  "shell reservation applied")

        def scale(name, value):
            assert command(f"test-scale {name} {value} 10000")["ok"]
            assert command("confirm")["ok"]

        @contextmanager
        def application(name, *arguments):
            path = artifacts / (name + ".log")
            with path.open("w") as log, (artifacts / (name + ".stderr")).open("w") as errors:
                process = subprocess.Popen([client, *arguments], env=env, stdout=log, stderr=errors)
            try:
                def window():
                    assert process.poll() is None, f"GTK exited: {process.returncode}"
                    return next((w for w in command("windows") if w["title"] == "GtkProbe"), None)

                def events():
                    return read_json_lines(path, "{")

                w = until(window, "GTK window")
                assert not w["legacy"], w
                yield window, events
            except BaseException:
                (artifacts / (name + "-failure.json")).write_text(json.dumps(dict(
                    windows=command("windows"), records=records), indent=2) + "\n")
                raise
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
                until(lambda: not any(w["title"] == "GtkProbe" for w in command("windows")), "GTK window cleanup")

        try:
            assert select.select([server.stdout], [], [], 10)[0]
            line = server.stdout.readline().strip()
            assert line.startswith("WAYLAND_DISPLAY="), line
            env["WAYLAND_DISPLAY"] = line.split("=", 1)[1]
            if shell_probe:
                shell = Shell(shell_probe, broker, env, artifacts, 0, version=14)
                shell.wait(lambda: shell.output_batches, "shell output inventory")
                for h in list(shell.outputs.values()): reserve(h["name"], True)
            if registry_probe:
                subprocess.run([registry_probe, "--no-focus"], env=env, check=True, timeout=15)
            left, right = sorted(command("outputs"), key=lambda o: o["x"])
            target = right["name"]
            scale(target, 150)
            assert command(f"output-position {target} -1280 -200")["ok"]

            with application("transitions", "--window-drag") as (window, events):
                wid = window()["id"]
                normal = dict(x=-1240, y=-160, width=801, height=601)
                assert command(f"move {wid} {normal['x']} {normal['y']}")["ok"]
                until(lambda: all(window()[k] == v for k, v in normal.items()), "initial floating frame")


                def key(code):
                    assert command(f"focus {wid}")["ok"]
                    assert command(f"key {code} 1")["ok"]
                    assert command(f"key {code} 0")["ok"]

                def state(maximized, fullscreen, name=None):
                    def matches():
                        w = window()
                        if not w or (w["maximized"], w["fullscreen"]) != (maximized, fullscreen):
                            return None
                        frame = bounds(name, maximized and not fullscreen) if name else normal
                        if any(w[k] != frame[k] for k in ("x", "y", "width", "height")):
                            return None
                        if name:
                            density = frame['scale']
                            if (w["buffer_width"], w["buffer_height"]) != tuple(
                                    (frame[k] * density + 60) // 120 for k in ("width", "height")):
                                return None
                        return w
                    w = until(matches, f"state max={maximized} full={fullscreen} output={name}")
                    until(lambda: any(e["event"] == "window-state" and
                        (e["maximized"], e["fullscreen"]) == (maximized, fullscreen) for e in events()),
                        "GTK acknowledges window state")
                    records.append(w)
                    return w

                key(50)  # m: maximize through GTK's ordinary protocol path.
                state(True, False, target)
                for density in (120, 150, 180, 210, 240):
                    scale(target, density)
                    state(True, False, target)
                if shell:
                    reserve(target, False); state(True, False, target)
                    reserve(target, True); state(True, False, target)
                key(33)  # f: fullscreen preserves the prior maximization.
                state(True, True, target)
                key(32)  # d: a real transient dialog must stay visible above fullscreen.
                dialog = until(lambda: next((w for w in command("windows") if w["title"] == "GtkStateDialog"
                    and w["focused"] and w["width"] == 321), None), "fullscreen transient dialog")
                assert command(f"move {dialog['id']} {window()['x'] + 100} {window()['y'] + 100}")["ok"]
                until(lambda: command(f"hit {window()['x'] + 150} {window()['y'] + 150}")["id"] == dialog["id"],
                      "transient dialog above its fullscreen parent")
                assert command("key 1 1")["ok"]
                assert command("key 1 0")["ok"]
                until(lambda: not any(w["title"] == "GtkStateDialog" for w in command("windows")), "dialog close")
                until(lambda: window()["focused"], "fullscreen parent focus restored")
                for density in (120, 150, 180, 210, 240, 150):
                    scale(target, density)
                    state(True, True, target)
                for code in (2, 3):
                    before = len(events())
                    key(code)
                    chosen = until(lambda: next((e["name"] for e in events()[before:]
                        if e["event"] == "fullscreen-output"), None), "requested fullscreen output")
                    state(True, True, chosen)
                key(19)  # r: return to maximization on its original output.
                state(True, False, target)
                key(22)  # u: restore the exact original logical frame.
                state(False, False)
                key(33)
                state(False, True, target)
                key(50)
                state(True, True, target)
                key(22)
                state(False, True, target)
                key(19)
                state(False, False)
                # Repeated requests must not replace the saved normal frame.
                for code in (50, 50, 22, 50): key(code)
                state(True, False, target)
                key(22)
                state(False, False)
                # Exercise real GDK move requests. Maximized windows retain
                # their size while moving.
                def frame(w):
                    return {k: w[k] for k in ("x", "y", "width", "height")}

                def drag(mode, density, cancel=False, configure=True):
                    scale(target, density)
                    if shell and configure:
                        shell.send(f"maximized-drag {mode}")
                        shell.snapshot()  # Barrier on the authorized connection.
                    key(50)
                    before = state(True, False, target)
                    start_x, start_y = before["x"] + before["width"] * 3 // 4, before["y"] + 12
                    assert command(f"pointer {start_x} {start_y}")["ok"]
                    count = len(events())
                    assert command("button 272 1")["ok"]
                    until(lambda: any(e["event"] == "window-move-requested" for e in events()[count:]),
                          "GTK move request")
                    if mode != 3:
                        until(lambda: command("move-state") == dict(id=wid, mode=1), "authorized interactive move")
                    assert command(f"pointer {start_x + 41} {start_y + 29}")["ok"]
                    if mode == 3:
                        assert command("move-state") == dict(id=0, mode=0)
                        expected = frame(before)
                    elif mode == 1:
                        expected = dict(normal, x=int(start_x - (start_x - before["x"]) /
                            before["width"] * normal["width"]) + 41, y=before["y"] + 29)
                    else:
                        expected = dict(frame(before), x=before["x"] + 41, y=before["y"] + 29)
                    try:
                        until(lambda: frame(window()) == expected and window()["maximized"] == (mode in (0, 3)),
                              "configured maximized drag behavior")
                    except BaseException:
                        (artifacts / "drag-failure.json").write_text(json.dumps(dict(mode=mode, density=density,
                            before=before, expected=expected, current=window(), move_state=command("move-state"),
                            pointer_focus=command("pointer-focus"), outputs=command("outputs"),
                            recent_events=events()[-12:]), indent=2) + "\n")
                        raise
                    if cancel:
                        key(1)  # Escape restores the complete pre-drag state.
                        until(lambda: frame(window()) == frame(before) and window()["maximized"],
                              "cancelled maximized drag restores state and geometry")
                    assert command("button 272 0")["ok"]
                    assert command("move-state") == dict(id=0, mode=0)
                    if mode == 0 and density == 150 and not cancel:
                        for changed_density in (180, 150):
                            scale(target, changed_density)
                            changed = bounds(target, True)
                            expected.update(width=changed["width"], height=changed["height"])
                            until(lambda: frame(window()) == expected and window()["maximized"],
                                  "moved maximized window retains displacement through density changes")
                    records.append(dict(drag_mode=mode, density=density, cancelled=cancel, window=window()))
                    if mode in (0, 3) or cancel:
                        key(22)
                        state(False, False)
                    else:
                        # Restore the independent test's original floating frame.
                        assert command(f"resize {wid} {normal['width']} {normal['height']}")["ok"]
                        assert command(f"move {wid} {normal['x']} {normal['y']}")["ok"]
                        until(lambda: frame(window()) == normal, "next drag starts at original frame")

                for mode in (0, 1, 2, 3) if shell else (0,):
                    for density in (120, 150, 180, 210, 240):
                        drag(mode, density)
                    drag(mode, 150, cancel=True)
                if shell:
                    shell.stop()
                    shell = Shell(shell_probe, broker, env, artifacts, 1, version=14)
                    shell.wait(lambda: shell.output_batches, "replacement shell inventory")
                    shell.send("maximized-drag 99")
                    shell.snapshot()
                    drag(3, 150, configure=False)  # NoMove survives replacement and invalid input.
                    shell.send("maximized-drag 0")
                    shell.snapshot()
                for density in (120, 150, 180, 210, 240):
                    for mode, request_key, request in ((0, 22, "unmaximize"), (0, 33, "fullscreen"),
                            (1, 33, "fullscreen"), (2, 33, "fullscreen"), (3, 33, "fullscreen")):
                        if mode and not shell: continue
                        scale(target, density)
                        if shell:
                            shell.send(f"maximized-drag {mode}"); shell.snapshot()
                        key(50)
                        before = state(True, False, target)
                        x, y = before["x"] + before["width"] * 3 // 4, before["y"] + 12
                        count = len(events())
                        assert command(f"pointer {x} {y}")["ok"]
                        assert command("button 272 1")["ok"]
                        try:
                            until(lambda: any(e["event"] == "window-move-requested" for e in events()[count:]),
                                  "GTK move before client state request")
                            expected_move = dict(id=0, mode=0) if mode == 3 else dict(id=wid, mode=1)
                            until(lambda: command("move-state") == expected_move, "GTK interactive move is established")
                            assert command(f"pointer {x + 41} {y + 29}")["ok"]
                            if mode in (1, 2):
                                until(lambda: not window()["maximized"], "drag mode leaves maximization")
                            key(request_key)
                            requested = state(request == "fullscreen", request == "fullscreen",
                                              target if request == "fullscreen" else None)
                            assert command("move-state") == dict(id=0, mode=0), "Client request retained an active move"
                        except BaseException:
                            (artifacts / "state-request-failure.json").write_text(json.dumps(dict(
                                density=density, drag_mode=mode, request=request, before=before,
                                current=window(), move_state=command("move-state"),
                                pointer_focus=command("pointer-focus"), hit=command(f"hit {x} {y}"),
                                outputs=command("outputs"), recent_events=events()[-15:]), indent=2) + "\n")
                            raise
                        finally:
                            assert command("button 272 0")["ok"]
                        if request == "fullscreen":
                            key(19)  # r: leave fullscreen through GTK.
                            state(True, False, target)
                            key(22)
                        restored = state(False, False)
                        records.append(dict(during_move_request=request, density=density, drag_mode=mode,
                            before=before, requested=requested, restored=restored))
                if shell:
                    shell.send("maximized-drag 0"); shell.snapshot()
                scale(target, 150)
                key(33)
                state(False, True, target)
                full = frame(window())
                x, y = full["x"] + 100, full["y"] + 12
                count = len(events())
                assert command(f"pointer {x} {y}")["ok"]
                assert command("button 272 1")["ok"]
                until(lambda: any(e["event"] == "window-move-requested" for e in events()[count:]),
                      "fullscreen move request")
                assert command(f"pointer {x+41} {y+29}")["ok"]
                assert command("button 272 0")["ok"]
                assert command("move-state") == dict(id=0, mode=0)
                assert frame(window()) == full and window()["fullscreen"]
                assert command(f"resize-output {target} 1800 1400")["ok"]
                state(False, True, target)
                assert command(f"remove-output {target}")["ok"]
                state(False, True, left["name"])
                key(19)
                normal.update(x=left["x"], y=left["y"])
                state(False, False)

            # Requests before the first map must receive a useful initial size.
            for name, flag in (("maximized", "--maximize"), ("fullscreen", "--fullscreen")):
                with application(name, flag) as (window, events):
                    frame = bounds(left["name"], name == "maximized")
                    until(lambda: window()[name] and all(window()[k] == frame[k]
                        for k in ("x", "y", "width", "height")), "initial " + name)
                    records.append(window())
            if registry_probe:
                with (artifacts / "small-fullscreen.log").open("w") as log:
                    small = subprocess.Popen([registry_probe, "--small-fullscreen", "SmallFullscreen"],
                        env=env, stdout=log, stderr=log)
                try:
                    def centered():
                        assert small.poll() is None
                        w = next((w for w in command("windows") if w["title"] == "SmallFullscreen"), None)
                        frame = output(left["name"])
                        return w if w and w["fullscreen"] and (w["x"], w["y"], w["width"], w["height"]) == (
                            frame["x"] + (frame["width"] - 64) // 2,
                            frame["y"] + (frame["height"] - 64) // 2, 64, 64) else None
                    for density in (120, 150, 180, 210, 240):
                        scale(left["name"], density)
                        w = until(centered, "small fullscreen centered in logical output bounds")
                        expected = dict(samples=[0xff000000] * 4, center=0xff808080)
                        until(lambda: command(f"output-samples {left['name']}") == expected,
                              "presented black borders and translucent content over black")
                        records.append(dict(window=w, density=density, pixels=expected))
                    with (artifacts / "foreign-window.log").open("w") as log:
                        foreign = subprocess.Popen([registry_probe, "--window", "ForeignWindow"], env=env, stdout=log, stderr=log)
                    try:
                        other = until(lambda: next((w for w in command("windows") if w["title"] == "ForeignWindow"
                            and w["focused"]), None), "another application takes focus")
                        frame = output(left["name"])
                        x, y = frame["x"] + 100, frame["y"] + 100
                        assert command(f"move {other['id']} {x} {y}")["ok"]
                        until(lambda: command(f"hit {x+20} {y+20}")["id"] == other["id"],
                              "focused foreign window remains usable above inactive fullscreen")
                        assert command(f"focus {w['id']}")["ok"]
                        until(lambda: command(f"hit {x+20} {y+20}")["id"] != other["id"],
                              "reactivated fullscreen covers unrelated windows")
                    finally:
                        if foreign.poll() is None: foreign.terminate(); foreign.wait(timeout=5)
                finally:
                    if small.poll() is None: small.terminate(); small.wait(timeout=5)
                until(lambda: command(f"output-samples {left['name']}").get("center") != 0xff808080,
                      "fullscreen fill removed with its window")
            (artifacts / "results.json").write_text(json.dumps(records, indent=2) + "\n")
            print("Wayland maximize/fullscreen, density, output selection, restoration and hotplug: PASS")
        except BaseException:
            if server.poll() is None:
                (artifacts / "failure.json").write_text(json.dumps(dict(windows=command("windows"),
                    outputs=command("outputs")), indent=2) + "\n")
            raise
        finally:
            if shell: shell.stop()
            broker.close()
            control.close()
            if server.poll() is None:
                server.terminate()
                server.wait(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compositor", required=True)
    parser.add_argument("--client", required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--registry-probe")
    parser.add_argument("--shell-probe")
    run(**vars(parser.parse_args()))
