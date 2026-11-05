#!/usr/bin/env python3
"""Check native frame styles against real AppKit geometry and title pixels."""
import argparse
import json
import os
from pathlib import Path
import re
import select
import socket
import subprocess
import tempfile
import uuid

from PIL import Image
from integration import read_json_lines, until


def run(compositor, gui_probe, application_probe, registry_probe, artifacts, styles):
    artifacts.mkdir(parents=True)
    captures = artifacts / "frames"
    captures.mkdir()
    rows, references = [], {}
    rect = lambda value: tuple(map(float, re.findall(r"-?\d+(?:\.\d+)?", value)))
    with tempfile.TemporaryDirectory(prefix="nextspace-native-styles-") as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS="headless",
                   WLR_HEADLESS_OUTPUTS="2", WLR_RENDERER="pixman",
                   NEXTSPACE_COMPOSITOR_CAPTURE_DIR=str(captures.resolve()))
        for name in ("DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET"):
            env.pop(name, None)
        control, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        control.settimeout(5)
        with (artifacts / "compositor.log").open("w") as log:
            server = subprocess.Popen([compositor, "-c", str(child.fileno())], pass_fds=[child.fileno()],
                env=env, stdout=subprocess.PIPE, stderr=log, text=True)
        child.close()
        foreign = None

        def command(value):
            control.sendall(value.encode())
            return json.loads(control.recv(65536))

        try:
            assert select.select([server.stdout], [], [], 10)[0]
            line = server.stdout.readline().strip()
            assert line.startswith("WAYLAND_DISPLAY="), line
            env["WAYLAND_DISPLAY"] = line.split("=", 1)[1]
            target = command("outputs")[0]["name"]
            assert command(f"output-position {target} -1600 -200")["ok"]
            with (artifacts / "foreign.log").open("w") as log:
                foreign = subprocess.Popen([registry_probe, "--window", "StyleReferenceForeign"],
                    env=env, stdout=log, stderr=log)
            foreign_id = until(lambda: next((w["id"] for w in command("windows")
                if w["title"] == "StyleReferenceForeign"), None), "foreign focus reference")
            for decorated in (False, True):
                for style in styles:
                    directory = artifacts / f"{'server' if decorated else 'client'}-{style}"
                    directory.mkdir()
                    client_env = dict(env, NEXTSPACE_SESSION_ID="test-" + str(uuid.uuid4()),
                                      NEXTSPACE_WAYLAND_CAPTURE_DIR=str(directory.resolve()))
                    path = directory / "probe.log"
                    with path.open("w") as log, (directory / "probe.stderr").open("w") as errors:
                        client = subprocess.Popen([gui_probe, "-GSBackend", "libgnustep-wayland", "-GSTheme", "NextSpace",
                            "-GSWaylandServerDecorations", "YES" if decorated else "NO",
                            "-WindowStyleMask", str(style)], env=client_env, stdout=log, stderr=errors)

                    def window():
                        assert client.poll() is None, f"Style probe exited: {client.returncode}"
                        return next((w for w in command("windows") if w["pid"] == client.pid and
                            w["client_id"] > 1 and w["style"] == style and w["title"] == "WaylandProbe"), None)

                    def query(action=None):
                        args = [application_probe, "--application-action" if action else "--application-state", "WaylandProbe"]
                        if action: args.append(action)
                        args += ["--window-number", str(window()["client_id"])]
                        result = subprocess.run(args, env=client_env, capture_output=True, text=True, timeout=10)
                        assert result.returncode == 0, (args, result.stdout, result.stderr)
                        return json.loads(result.stdout)

                    try:
                        w = until(window, "AppKit style window")
                        q = query()
                        assert q["style_mask"] == style
                        f, c = rect(q["frame"]), rect(q["content_rect"])
                        insets = tuple(round(v) for v in (c[0] - f[0], f[1] + f[3] - c[1] - c[3],
                            f[0] + f[2] - c[0] - c[2], c[1] - f[1]))
                        framed = decorated and any(insets)
                        until(lambda: window()["server_decorated"] == framed, "style decoration negotiation")
                        for density in (120, 150, 180, 210, 240):
                            assert command(f"test-scale {target} {density} 10000")["ok"]
                            assert command("confirm")["ok"]
                            heads = command("outputs")
                            h = next(h for h in heads if h["name"] == target)
                            other = next(h for h in heads if h["name"] != target)
                            assert command(f"move {w['id']} {h['x'] + 20} {h['y'] + 20}")["ok"]
                            assert command(f"move {foreign_id} {other['x'] + 20} {other['y'] + 20}")["ok"]
                            until(lambda: window()["preferred_scale"] == density and
                                window()["buffer_width"] == (801 * density + 60) // 120, "style backing density")
                            query("activate")
                            assert command(f"focus {foreign_id}")["ok"]
                            q = query("deactivate")
                            assert not q["active"]
                            # Normalize the independent AppKit reference even for
                            # non-keyable styles whose initial input state is key.
                            q = query("normal-title")
                            assert rect(q["frame"])[2:] == (801, 601), q
                            current = window()
                            assert (current["frame_width"], current["frame_height"]) == (801, 601), current
                            expected = (801 - insets[0] - insets[2], 601 - insets[1] - insets[3]) if framed else (801, 601)
                            assert (current["surface_width"], current["surface_height"]) == expected, current
                            assert current["server_decorated"] == framed
                            edge = lambda value: (value * density + 60) // 120
                            title_extrema = None
                            if insets[1] >= 20:
                                source = captures / f"frame-{w['id']}-{density}.png" if framed else (
                                    directory / f"window-{current['client_id']}-{density}.png")
                                def pixels():
                                    try:
                                        with Image.open(source) as image:
                                            title = image.convert("RGB").crop((0, 0, edge(801), edge(insets[1])))
                                    except OSError: return None
                                    body = title.crop((edge(40), edge(5), edge(65), edge(18))).getextrema()
                                    if body != ((170, 170),) * 3: return None
                                    text = title.crop((edge(230), edge(4), edge(570), edge(19))).getextrema()
                                    expected_text = references[style, density]["text"] if decorated else (
                                        ((0, 170),) * 3 if style & 1 else ((170, 170),) * 3)
                                    return (title, text) if text == expected_text else None
                                title, title_extrema = until(pixels, f"AppKit style {style} title visibility at {density}/120")
                                title.save(directory / f"title-{density}.png")
                            if decorated:
                                assert insets == tuple(references[style, density]["insets"])
                            else:
                                references[style, density] = dict(insets=insets, text=title_extrema)
                            count = len(read_json_lines(path, '{"event":'))
                            assert command(f"pointer {current['x'] + 100} {current['y'] + 601 - 100}")["ok"]
                            assert command("button 272")["ok"]
                            until(lambda: any(e["event"] == "click" and (e["x"], e["y"]) == (100, 100)
                                for e in read_json_lines(path, '{"event":')[count:]), "style content input alignment")
                            rows.append(dict(decorated=decorated, style=style, density=density, insets=insets,
                                text=title_extrema, appkit=q, window=current))
                            (artifacts / "partial-results.json").write_text(json.dumps(rows, indent=2) + "\n")
                        maps = sorted({line.split()[-1] for line in Path(f"/proc/{client.pid}/maps").read_text().splitlines()
                            if any(name in line for name in ("libgnustep-base.so.", "libgnustep-gui.so.", "libgnustep-wayland-"))})
                        (directory / "runtime.json").write_text(json.dumps(maps, indent=2) + "\n")
                    except BaseException:
                        (directory / "failure.json").write_text(json.dumps(dict(windows=command("windows"),
                            appkit=query(), events=read_json_lines(path, '{"event":')[-10:]), indent=2) + "\n")
                        raise
                    finally:
                        if client.poll() is None: client.terminate()
                        client.wait(timeout=5)
        finally:
            if foreign and foreign.poll() is None: foreign.terminate(); foreign.wait(timeout=5)
            if server.poll() is None: server.terminate()
            server.wait(timeout=5)
            control.close(); server.stdout.close()
    (artifacts / "results.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(f"Native AppKit frame styles, title visibility, geometry and input: {len(rows)} snapshots PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compositor", required=True)
    parser.add_argument("--gui-probe", required=True)
    parser.add_argument("--application-probe", required=True)
    parser.add_argument("--registry-probe", required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--styles", type=int, nargs="+", default=list(range(16)))
    run(**vars(parser.parse_args()))
