#!/usr/bin/env python3
"""Negotiate real server frames and exercise geometry, pixels and pointer input."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import tempfile
from PIL import Image
from integration import read_json_lines, until
from shell import Shell
from titlebar import run as run_titlebar
from state_requests import run as run_state_requests


def frame_pixels_ready(image, scale):
    # A valid monochrome NeXT frame has only four colors. Check its actual
    # title/control ink and bevels instead of requiring antialiasing shades.
    image = image.convert("RGB")
    def edge(value):
        return (value * scale + 60) // 120
    for box in ((4, 4, 18, 18), (23, 2, 300, 20), (304, 4, 318, 18)):
        if image.crop(tuple(edge(value) for value in box)).getextrema() != ((0, 255),) * 3:
            return False
    return (image.getpixel((edge(40), edge(1))) == (170, 170, 170) and
            image.getpixel((edge(40), edge(20))) == (85, 85, 85))


def run(compositor, probe, shell_probe, artifacts):
    artifacts.mkdir(parents=True)
    captures = artifacts / "captures"
    captures.mkdir()
    records = []
    metric_records = []
    title_hint_records = []
    with tempfile.TemporaryDirectory(prefix="nextspace-decorations-") as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS="headless",
                   WLR_HEADLESS_OUTPUTS="2", WLR_RENDERER="pixman",
                   NEXTSPACE_COMPOSITOR_CAPTURE_DIR=str(captures.resolve()))
        for name in ("DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET"):
            env.pop(name, None)
        control, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        broker, broker_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        control.settimeout(5)
        with (artifacts / "compositor.log").open("w") as log:
            server = subprocess.Popen([compositor, "-c", str(child.fileno()), "-S", str(broker_child.fileno())],
                pass_fds=[child.fileno(), broker_child.fileno()], env=env,
                stdout=subprocess.PIPE, stderr=log, text=True)
        child.close(); broker_child.close()
        shell = None

        def command(text):
            control.sendall(text.encode())
            return json.loads(control.recv(65536))

        @contextmanager
        def application(label, *arguments):
            path = artifacts / (label + ".jsonl")
            with path.open("w") as log, (artifacts / (label + ".stderr")).open("w") as errors:
                client = subprocess.Popen([probe, *arguments], env=env, stdin=subprocess.PIPE,
                                          stdout=log, stderr=errors, text=True)
            def send(text):
                client.stdin.write(text + "\n"); client.stdin.flush()
            def events():
                return read_json_lines(path)
            try:
                yield client, send, events
            except BaseException:
                if server.poll() is None:
                    (artifacts / (label + "-failure.json")).write_text(json.dumps(command("windows"), indent=2) + "\n")
                raise
            finally:
                if client.poll() is None:
                    client.terminate()
                client.wait(timeout=5)
                client.stdin.close()

        try:
            assert select.select([server.stdout], [], [], 10)[0], "No compositor socket"
            line = server.stdout.readline().strip()
            assert line.startswith("WAYLAND_DISPLAY="), (line, server.poll())
            env["WAYLAND_DISPLAY"] = line.split("=", 1)[1]
            shell = Shell(shell_probe, broker, env, artifacts, 0, version=15)
            outputs = command("outputs")
            target = outputs[0]["name"]
            def output():
                return next(o for o in command("outputs") if o["name"] == target)

            with application("server") as (client, send, events):
                def window():
                    assert client.poll() is None, f"Decoration client exited: {client.returncode}"
                    return next((w for w in command("windows") if w["pid"] == client.pid), None)
                def synchronized():
                    count = len(events())
                    send("sync")
                    until(lambda: any(e["event"] == "sync" for e in events()[count:]), "client input barrier")
                w = until(lambda: window() if window() and window()["server_decorated"] else None,
                          "default server-decoration negotiation")
                wid = w["id"]
                assert (w["surface_width"], w["surface_height"], w["frame_width"], w["frame_height"]) == (321, 241, 323, 272), w
                for scale in (120, 150, 180, 210, 240):
                    assert command(f"test-scale {target} {scale} 10000")["ok"]
                    assert command("confirm")["ok"]
                    h = output()
                    assert command(f"move {wid} {h['x'] + 10} {h['y'] + 10}")["ok"]
                    w = until(lambda: window() if window().get("decoration_scale") == scale else None,
                              "server frame backing density")
                    expected = ((323 * scale + 60) // 120, (22 * scale + 60) // 120)
                    assert (w["decoration_buffer_width"], w["decoration_buffer_height"]) == expected, w
                    image_path = captures / f"frame-{wid}-{scale}.png"
                    def captured():
                        try:
                            with Image.open(image_path) as image:
                                return image.size == expected and frame_pixels_ready(image, scale)
                        except OSError:
                            return False
                    until(captured, "rendered title, bevels and buttons at backing density")
                    # Client coordinates exclude the compositor's frame.
                    count = len(events())
                    command(f"pointer {w['x'] + 21} {w['y'] + 52}")
                    command("button 272")
                    until(lambda: any(e["event"] in ("motion", "enter") and (e["x"], e["y"]) == (20, 30)
                                      for e in events()[count:]), "content pointer coordinates")
                    until(lambda: len([e for e in events()[count:] if e["event"] == "button"]) == 2,
                          "content press and release")
                    buttons = len([e for e in events() if e["event"] == "button"])
                    command(f"pointer {w['x'] + 100} {w['y'] + 10}")
                    command("button 272 1")
                    assert command("move-state") == dict(id=wid, mode=1)
                    command(f"pointer {w['x'] + 140} {w['y'] + 35}")
                    command("button 272 0")
                    moved = window()
                    assert (moved["x"], moved["y"]) == (w["x"] + 40, w["y"] + 25), moved
                    assert command("move-state") == dict(id=0, mode=0)
                    synchronized()
                    assert len([e for e in events() if e["event"] == "button"]) == buttons, events()
                    # Resize through the actual bottom-right grab area.
                    x, y = moved["x"] + 313, moved["y"] + 268
                    command(f"pointer {x} {y}"); command("button 272 1")
                    assert command("move-state") == dict(id=wid, mode=2)
                    command(f"pointer {x + 17} {y + 19}"); command("button 272 0")
                    resized = until(lambda: window() if (window()["frame_width"], window()["frame_height"]) == (340, 291) else None,
                                    "server-frame resize configures client content")
                    assert (resized["surface_width"], resized["surface_height"]) == (338, 260), resized
                    command(f"resize {wid} 323 272")
                    until(lambda: window()["frame_width"] == 323 and window()["frame_height"] == 272,
                          "restore fixture size")
                    records.append(dict(scale=scale, window=w, capture=image_path.name, drag=moved, resize=resized))
                # A content press keeps its implicit client grab when the
                # pointer crosses into a compositor-owned title before release.
                w = window(); synchronized()
                before = len([e for e in events() if e["event"] == "button"])
                command(f"pointer {w['x'] + 51} {w['y'] + 72}"); command("button 272 1")
                command(f"pointer {w['x'] + 100} {w['y'] + 10}"); command("button 272 0")
                synchronized()
                assert [e["state"] for e in events() if e["event"] == "button"][before:] == [1, 0], events()
                assert command("move-state") == dict(id=0, mode=0)
                # The title follows the content's preferred output, including
                # a move between densities and a negative-origin layout.
                other = outputs[1]["name"]
                assert command(f"output-position {other} -1280 -80")["ok"]
                second = next(o for o in command("outputs") if o["name"] == other)
                command(f"move {wid} {second['x'] + 40} {second['y'] + 40}")
                mixed = until(lambda: window() if window().get("decoration_scale") == 120 else None,
                              "server frame rerenders after mixed-density movement")
                command(f"pointer {mixed['x'] + 101} {mixed['y'] + 92}")
                assert command("hit %d %d" % (mixed["x"] + 100, mixed["y"] + 10))["id"] == wid
                before = len([e for e in events() if e["event"] == "button"])
                command(f"pointer {mixed['x'] + 100} {mixed['y'] + 10}"); command("button 272 1")
                command(f"pointer {mixed['x'] + 125} {mixed['y'] + 25}")
                command("key 1 1"); command("key 1 0"); command("button 272 0")
                assert (window()["x"], window()["y"]) == (mixed["x"], mixed["y"]), window()
                synchronized()
                assert len([e for e in events() if e["event"] == "button"]) == before
                shell.stop()
                shell = Shell(shell_probe, broker, env, artifacts, 1, version=15)
                shell.wait(lambda: wid in shell.windows and shell.windows[wid].get("title_height") == 22,
                           "replacement shell recovers decorated window state")
                h = output()
                command(f"move {wid} {h['x'] + 50} {h['y'] + 35}")
                until(lambda: window().get("decoration_scale") == 240, "return to dense output")
                send("title")
                until(lambda: window()["title"] == "Unicode title: Ω", "title metadata update")
                w = window()
                shell.send(f"shade {wid} 1")
                until(lambda: window()["shaded"], "server-frame shade")
                assert command(f"hit {w['x'] + 50} {w['y'] + 30}")["id"] != wid
                assert command(f"hit {w['x'] + 50} {w['y'] + 10}")["id"] == wid
                shell.send(f"shade {wid} 0")
                until(lambda: not window()["shaded"], "server-frame unshade")
                command(f"pointer {w['x'] + 10} {w['y'] + 10}"); command("button 272")
                until(lambda: window()["minimized"], "server minimize button")
                shell.send(f"minimize {wid} 0")
                until(lambda: not window()["minimized"], "shell restores server-framed window")
                command(f"focus {wid}")
                synchronized()
                title_path = captures / f"frame-{wid}-240.png"
                def title_gray(active):
                    with Image.open(title_path) as image:
                        r, g, b, a = image.convert("RGBA").getpixel((50, 20))
                        return a == 255 and r == g == b and (r == 0 if active else r > 100)
                until(lambda: title_gray(True), "active server title pixels")
                client.send_signal(signal.SIGSTOP)
                try:
                    shell.send(f"minimize {wid} 1")
                    until(lambda: window()["minimized"], "shell minimizes stopped client")
                    shell.send(f"minimize {wid} 0")
                    until(lambda: not window()["minimized"] and not window()["focused"], "restore without focus")
                    until(lambda: title_gray(False), "server title repaints focus without a client commit")
                finally:
                    client.send_signal(signal.SIGCONT)
                synchronized()
                before = len([e for e in events() if e["event"] == "button"])
                command(f"pointer {w['x'] + w['frame_width'] - 10} {w['y'] + 10}")
                command("button 272 1")
                command(f"pointer {w['x'] + 50} {w['y'] + 60}")
                command("button 272 0")
                synchronized()
                assert len([e for e in events() if e["event"] == "button"]) == before
                assert client.poll() is None, "A released close button activated away from its frame"
                send("maximize")
                until(lambda: window()["maximized"] and window()["frame_width"] == output()["work_width"] and
                      window()["frame_height"] == output()["work_height"], "maximized frame fits logical work area")
                send("fullscreen")
                until(lambda: window()["fullscreen"] and not window()["server_decorated"] and
                      window()["width"] == output()["width"] and window()["height"] == output()["height"],
                      "fullscreen omits server decorations")
                send("unfullscreen")
                until(lambda: not window()["fullscreen"] and window()["server_decorated"] and
                      window()["frame_height"] == output()["work_height"], "maximize restored after fullscreen")
                send("restore")
                until(lambda: not window()["maximized"] and window()["frame_width"] == 323 and
                      window()["frame_height"] == 272, "normal frame restored")
                send("mode 1")
                until(lambda: not window()["server_decorated"] and window()["frame_width"] == 321,
                      "client-side negotiation removes frame")
                send("unset")
                until(lambda: window()["server_decorated"], "unset preference restores compositor policy")
                send("destroy")
                until(lambda: not window()["server_decorated"], "decoration destruction applies at commit")
            with application("title-hints", "--metrics") as (client, send, events):
                def window():
                    assert client.poll() is None, f"Title hint client exited: {client.returncode}"
                    return next((w for w in command("windows") if w["pid"] == client.pid), None)
                def sync():
                    count = len(events()); send("sync")
                    until(lambda: any(e["event"] == "sync" for e in events()[count:]), "title hint barrier")
                def snapshot(label, reported, focused):
                    def pixels():
                        w = window()
                        if w["client_title_state"] != reported or w["focused"] != focused: return None
                        try:
                            scale = w["decoration_scale"]
                            with Image.open(captures / f"frame-{w['id']}-{scale}.png") as image:
                                pixel = image.convert("RGB").getpixel(((40 * scale + 60) // 120, (10 * scale + 60) // 120))
                        except (OSError, KeyError): return None
                        return w if pixel == ((0 if focused else 170),) * 3 else None
                    current = until(pixels, label)
                    assert current["title_state"] == (0 if focused else 1)
                    title_hint_records.append(dict(label=label, window=current))
                w = until(lambda: window() if window() and window()["server_decorated"] else None, "owned title hint window")
                command(f"test-scale {target} 150 10000"); command("confirm")
                h = output(); command(f"move {w['id']} {h['x'] + 50} {h['y'] + 50}")
                until(lambda: window().get("decoration_scale") == 150, "fractional title hint fixture")
                for state in (0, 1, 2, 99, 4294967295):
                    send(f"title-state {state}"); sync()
                    snapshot(f"focused ignores presentation hint {state}", min(state, 2), True)
                with application("title-hints-foreign", "--metrics") as (other, other_send, other_events):
                    until(lambda: any(t["pid"] == other.pid and t["focused"] for t in command("windows")), "foreign title hint window focus")
                    for state in (0, 2, 1, 2, 99, 4294967295):
                        send(f"title-state {state}"); sync()
                        snapshot(f"unfocused hint {state} cannot claim focus or main appearance", min(state, 2), False)
                        assert any(t["pid"] == other.pid and t["focused"] for t in command("windows"))
                command(f"focus {w['id']}")
                snapshot("authoritative focus restores key title", 2, True)
                send("forget-window"); sync()
                snapshot("destroying owned hints retains actual focus", 1, True)
            with application("native-metrics", "--metrics") as (client, send, events):
                def window():
                    assert client.poll() is None, f"Metrics client exited: {client.returncode}"
                    return next((w for w in command("windows") if w["pid"] == client.pid), None)
                def sync():
                    count = len(events()); send("sync")
                    until(lambda: any(e["event"] == "sync" for e in events()[count:]), "metrics client barrier")
                def extents():
                    w = window()
                    return tuple(w["frame_" + k] for k in ("left", "top", "right", "bottom"))
                w = until(lambda: window() if window() and window()["server_decorated"] else None,
                          "native logical frame metrics")
                wid = w["id"]
                assert (w["surface_width"], w["surface_height"], w["frame_width"], w["frame_height"]) == (321, 241, 323, 273), w
                h = output()
                command(f"move {wid} {h['x'] + 10} {h['y'] + 10}")
                sync()
                # Edited metadata repaints immediately, without a surface commit.
                def close_center(gray):
                    w = window()
                    scale = w.get("decoration_scale", 120)
                    edge = lambda value: (value * scale + 60) // 120
                    try:
                        with Image.open(captures / f"frame-{wid}-{scale}.png") as image:
                            return image.convert("RGB").getpixel((edge(w["frame_width"] - 13), edge(10))) == (gray,) * 3
                    except OSError:
                        return False
                until(lambda: close_center(0), "clean owned close indicator")
                send("edited 1"); sync()
                until(lambda: window()["document_edited"] and close_center(170), "edited repaint without commit")
                send("edited 0"); sync()
                until(lambda: not window()["document_edited"] and close_center(0), "clean repaint without commit")
                send("pending-metrics 3 30 4 11"); sync()
                assert extents() == (1, 23, 1, 9), window()
                send("pending-metrics 129 0 0 0"); sync()
                assert extents() == (1, 23, 1, 9), window()
                send("commit"); sync()
                until(lambda: extents() == (3, 30, 4, 11), "valid metrics survive a rejected pending request")
                assert (window()["frame_width"], window()["frame_height"]) == (328, 282), window()
                for scale in (120, 150, 180, 210, 240):
                    command(f"test-scale {target} {scale} 10000"); command("confirm")
                    w = until(lambda: window() if window().get("decoration_scale") == scale else None,
                              "native title metric backing density")
                    assert (w["decoration_buffer_width"], w["decoration_buffer_height"]) == (
                        (328 * scale + 60) // 120, (30 * scale + 60) // 120), w
                    command(f"pointer {w['x'] + 24} {w['y'] + 61}")
                    count = len(events())
                    command(f"pointer {w['x'] + 23} {w['y'] + 60}")
                    until(lambda: any(e["event"] in ("motion", "enter") and (e["x"], e["y"]) == (20, 30)
                                      for e in events()[count:]), "content coordinates with custom frame metrics")
                    metric_records.append(w)
                send("style 1"); sync()
                w = window()
                # The old close and minimize locations now belong to the title.
                for x in (w["x"] + 10, w["x"] + w["frame_width"] - 10):
                    command(f"pointer {x} {w['y'] + 15}"); command("button 272")
                    sync()
                    assert client.poll() is None and not window()["minimized"], window()
                command(f"pointer {w['x'] + w['frame_width'] - 5} {w['y'] + w['frame_height'] - 5}")
                command("button 272 1")
                assert command("move-state") == dict(id=0, mode=0), "Fixed native style began a resize"
                command("button 272 0")
                send("style 0"); send("metrics 0 0 0 0"); sync()
                until(lambda: extents() == (0, 0, 0, 0), "borderless native metrics")
                assert (window()["frame_width"], window()["frame_height"]) == (321, 241)
                send("style 15"); send("metrics 1 23 1 9"); sync()
                until(lambda: extents() == (1, 23, 1, 9), "restore native frame metrics")
                send("maximize")
                until(lambda: window()["maximized"] and window()["frame_width"] == output()["work_width"] and
                      window()["frame_height"] == output()["work_height"], "native maximize includes custom frame")
                send("metrics 3 30 4 11"); sync()
                until(lambda: window()["frame_width"] == output()["work_width"] and
                      window()["frame_height"] == output()["work_height"], "metric change retains maximized bounds")
                send("restore")
                until(lambda: not window()["maximized"] and window()["frame_width"] == 328 and
                      window()["frame_height"] == 282, "metric change preserves floating content on unzoom")
                assert (window()["surface_width"], window()["surface_height"]) == (321, 241), window()
                send("fullscreen")
                until(lambda: window()["fullscreen"] and not window()["server_decorated"] and
                      window()["frame_width"] == output()["width"], "native metrics omitted in fullscreen")
                send("metrics 1 23 1 9"); sync()
                send("unfullscreen")
                until(lambda: not window()["fullscreen"] and window()["frame_width"] == 323 and
                      window()["frame_height"] == 273, "fullscreen metric change preserves floating content")
                send("mode 1")
                until(lambda: not window()["server_decorated"] and window()["title_height"] == 23,
                      "client-side fallback retains its title metadata")
                shell.send(f"shade {wid} 1")
                until(lambda: window()["shaded"], "fallback title remains shadeable")
                shell.send(f"shade {wid} 0")
                until(lambda: not window()["shaded"], "fallback unshade")
                send("unset")
                until(lambda: window()["server_decorated"] and window()["frame_height"] == 273,
                      "server frame returns after client-side fallback")
            with application("titlebar", "--metrics") as (client, send, events):
                def window():
                    assert client.poll() is None, f"Title client exited: {client.returncode}"
                    return next((w for w in command("windows") if w["pid"] == client.pid), None)
                def sync():
                    count = len(events()); send("sync")
                    until(lambda: any(e["event"] == "sync" for e in events()[count:]), "title input barrier")
                def replace_shell():
                    nonlocal shell
                    shell.stop()
                    shell = Shell(shell_probe, broker, env, artifacts, 20, version=15)
                    return shell
                until(lambda: window() and window()["server_decorated"], "native title gesture fixture")
                titlebar_records = run_titlebar(command, window, send, events, sync, shell, replace_shell,
                    target, captures, artifacts / "titlebar")
                state_request_records = run_state_requests(command, window, send, events, sync,
                    shell, target, artifacts / "state-requests")
            with application("close", "2") as (client, send, events):
                w = until(lambda: next((w for w in command("windows") if w["pid"] == client.pid and w["server_decorated"]), None),
                          "explicit server-side preference")
                command(f"pointer {w['x'] + w['frame_width'] - 10} {w['y'] + 10}")
                command("button 272")
                assert client.wait(timeout=5) == 0
                assert any(e["event"] == "close" for e in events())
            with application("client-side", "1") as (client, send, events):
                w = until(lambda: next((w for w in command("windows") if w["pid"] == client.pid), None), "client-side preference")
                assert not w["server_decorated"] and w["frame_width"] == w["width"]
                send("mode 99")
                assert client.wait(timeout=5) == 1, "Invalid decoration mode was accepted"
            assert server.poll() is None, "Invalid client killed the compositor"
            (artifacts / "results.json").write_text(json.dumps(dict(densities=records,
                mixed_output=mixed, native_metrics=metric_records, titlebar=titlebar_records,
                state_requests=state_request_records,
                title_hints=title_hint_records,
                checks=["content coordinates", "move", "resize", "Escape rollback",
                "shell replacement", "shade", "minimize", "maximize", "fullscreen", "unzoom",
                "CSD switch", "unset preference", "decoration destruction", "close", "invalid mode",
                "stalled-client focus repaint", "content grab crosses server frame",
                "document-edited repaint without commit"]), indent=2) + "\n")
            print("Server-decoration negotiation, density, input and lifecycle: PASS", flush=True)
        except BaseException:
            if server.poll() is None:
                (artifacts / "failure.json").write_text(json.dumps(command("windows"), indent=2) + "\n")
            raise
        finally:
            if shell: shell.stop()
            if server.poll() is None: server.terminate()
            server.wait(timeout=5)
            control.close(); broker.close(); server.stdout.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("compositor", "probe", "shell-probe"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--artifacts", required=True, type=Path)
    run(**vars(parser.parse_args()))
