"""Minimal real-app trials on the complete NEXTSPACE runtime."""
import shlex
import subprocess
import json
import sys
from pathlib import Path


def run(command, env, artifacts, programs, until):
    from PIL import Image
    from gnustep import capture_frame, capture_process_failure, process_runtime
    results = []
    identities = {}
    initial_outputs = command("outputs")
    target = max(initial_outputs, key=lambda output: output["x"])["name"]

    def key(code, pressed):
        assert command(f"key {code} {int(pressed)}")["ok"]

    def type_text(text):
        codes = dict(zip("qwertyuiopasdfghjklzxcvbnm", [*range(16, 26), *range(30, 39), *range(44, 51)]))
        codes["\n"] = 28
        for character in text:
            key(codes[character], True)
            key(codes[character], False)

    def shortcut(code):
        key(56, True)  # NEXTSPACE's default Command key is Alt.
        key(code, True); key(code, False)
        key(56, False)

    clipboard = {}

    def copied_text():
        result = subprocess.run([programs["pasteboard"], "--export-text"], env=env, capture_output=True)
        clipboard["export"] = dict(returncode=result.returncode, bytes=len(result.stdout),
            prefix=result.stdout[:120].decode("utf-8", errors="replace"),
            suffix=result.stdout[-120:].decode("utf-8", errors="replace"),
            stderr=result.stderr.decode("utf-8", errors="replace"))
        assert result.returncode in (0, 1), result.stderr
        return result.stdout.decode("utf-8") if result.returncode == 0 else None

    def copy_selection():
        def cleared():
            result = subprocess.run([programs["pasteboard"], "--clear"], env=env)
            clipboard["clear"] = dict(returncode=result.returncode)
            if result.returncode == 75: return False  # EX_TEMPFAIL: another owner won.
            result.check_returncode()
            return True
        until(cleared, "pasteboard sentinel ownership")
        shortcut(46)

    for name in ("Terminal", "TextEdit", "Review", "TimeMon"):
        executable = programs.get(name.lower())
        if not executable:
            continue
        clipboard.clear()
        directory = artifacts / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "failure.json").unlink(missing_ok=True)
        app_env = dict(env, NEXTSPACE_GS_BACKEND="wayland", NEXTSPACE_WAYLAND_CAPTURE_DIR=str(directory.resolve()))
        args = [executable, "-GSTheme", "NextSpace",
                "-GSFirstCommandKey", "Alt_L", "-GSSecondCommandKey", "Alt_R"]
        if name == "Terminal":
            ready, typed = directory / "ready", directory / "typed"
            ready.unlink(missing_ok=True); typed.unlink(missing_ok=True)
            shell = directory / "shell.sh"
            acknowledge_output = shlex.join([sys.executable,
                str(Path(__file__).with_name('terminal_output.py').resolve()),
                '--ack', str((directory / 'output-ack.json').resolve())])
            shell.write_text("#!/bin/sh\ni=0\nwhile [ $i -lt 400 ]; do\n"
                "  printf '%04d native retained text\\n' \"$i\"\n  i=$((i + 1))\ndone\n"
                f"touch {shlex.quote(str(ready.resolve()))}\n"
                "while IFS= read -r line; do\n"
                f"  {acknowledge_output} || exit 1\n"
                f"  printf '%s\\n' \"$line\" >> {shlex.quote(str(typed.resolve()))}\n"
                "done\n")
            shell.chmod(0o700)
            args += ["-Shell", str(shell.resolve()), "-AlternateAsMeta", "NO",
                     "-ScrollBackEnabled", "YES", "-ScrollBackLines", "1000"]
        elif name == "TextEdit":
            document = directory / "document.txt"
            document.write_text("Original text\n")
            args += ["-GSFilePath", str(document.resolve())]
        elif name == "Review":
            document = directory / "quadrants.png"
            image = Image.new("RGB", (512, 384))
            for color, box in zip(((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)),
                ((0, 0, 256, 192), (256, 0, 512, 192), (0, 192, 256, 384), (256, 192, 512, 384))):
                image.paste(color, box)
            image.save(document)
            args += ["-GSFilePath", str(document.resolve())]
        elif name == "TimeMon":
            args += ["-UpdatePeriod", "0.1", "-LagFactor", "1", "-LayerFactor", "4"]
        previous = {window["id"] for window in command("windows")}
        with (directory / "stdout.log").open("w") as log, (directory / "stderr.log").open("w") as errors:
            process = subprocess.Popen(args, env=app_env, stdout=log, stderr=errors,
                                       cwd=directory.resolve())
        try:
            def window():
                assert process.poll() is None, f"{name} exited: {process.returncode}"
                return next((w for w in command("windows") if w["id"] not in previous and
                             ((w["width"], w["height"]) == (64, 64) if name == "TimeMon" else
                              w["width"] >= 400 and w["height"] >= 250)), None)

            def capture(scale, w):
                # Equal-sized offscreen windows and previous runs can coexist.
                # Match the compositor's authenticated client-local window tag.
                assert w["client_id"] > 0, w
                path = directory / f"window-{w['client_id']}-{scale}.png"
                frame = capture_frame(path,(w["buffer_width"],w["buffer_height"]),'RGB')
                return frame['image'] if frame else None

            w = until(window, f"native {name} window", timeout=20)
            (directory / "runtime.json").write_text(json.dumps(process_runtime(process.pid), indent=2) + "\n")
            wid = w["id"]
            assert w["app_id"] and w["app_id"] != "org.nextspace.GNUstep", w
            assert w["pid"] == process.pid, w
            identities[name] = w["app_id"]
            initial_size = w["width"], w["height"]
            if name == "TimeMon":
                # Workspace positions application icons in its IconYard.
                target = next(o["name"] for o in command("outputs") if
                    o["x"] <= w["x"] + w["width"] / 2 < o["x"] + o["width"] and
                    o["y"] <= w["y"] + w["height"] / 2 < o["y"] + o["height"])

            def focus():
                w = window()
                assert command(f"focus {w['id']}")["ok"]
                assert command(f"pointer {w['x'] + 150} {w['y'] + 150}")["ok"]
                assert command("button 272")["ok"]

            if name != "TimeMon":
                focus()
            if name == "Terminal":
                until(ready.exists, "PTY output ready")
                type_text("wayland\n")
                until(lambda: typed.exists() and "wayland" in typed.read_text(), "native Terminal input reaches PTY")
                # Copy is asynchronous; keep its sentinel until publication instead
                # of clearing valid data and resending menu actions on every poll.
                shortcut(30); copy_selection()
                def terminal_text():
                    text = copied_text()
                    return text if text and "0399 native retained text" in text else None
                baseline = until(terminal_text, "Terminal scrollback copied")
                (directory / "scrollback.txt").write_text(baseline)
                assert "0000 native retained text" in baseline
            elif name == "TextEdit":
                shortcut(30)
                type_text("wayland\n")
                shortcut(31)  # Save the existing plain-text document.
                until(lambda: document.read_text(encoding="utf-8-sig") == "wayland\n", "TextEdit edit and save")

            for scale in (120, 150, 180, 210, 240):
                assert command(f"test-scale {target} {scale} 10000")["ok"]
                assert command("confirm")["ok"]
                output = next(o for o in command("outputs") if o["name"] == target)
                w = until(window, f"{name} window before movement")
                wid = w["id"]
                # A standalone app icon can cross an output boundary when a
                # scale change shrinks that output. Keep it on the tested
                # output; Workspace's normal IconYard placement stays intact.
                on_output = (output['x'] <= w['x'] + w['width'] / 2 < output['x'] + output['width'] and
                             output['y'] <= w['y'] + w['height'] / 2 < output['y'] + output['height'])
                if name != "TimeMon" or not on_output:
                    assert command(f"move {wid} {output['x'] + 10} 10")["ok"]

                def rendered():
                    w = window()
                    if not w:
                        return None
                    width, height = initial_size
                    return w if (w["width"], w["height"], w["buffer_width"], w["buffer_height"]) == (
                        width, height, (width * scale + 60) // 120, (height * scale + 60) // 120) else None

                w = until(rendered, f"{name} density {scale}/120")
                assert not w["legacy"]
                assert w["app_id"] == identities[name]
                def window_image():
                    # Theme image caches must survive output scale changes.
                    # Sample inside the close-button bezel, excluding its border.
                    rgb = capture(scale, w)
                    if rgb is None:
                        return False
                    if name == "TimeMon":
                        # The custom vector graph must reach the submitted icon
                        # buffer, including its blue CPU rings and white idle area.
                        pixels = list(rgb.getdata())
                        return rgb if any(b > r + 30 and b > g + 10 for r, g, b in pixels) and (
                            (255, 255, 255) in pixels) else False
                    bounds = tuple(value * scale // 120 for value in
                        (initial_size[0] - 16, 6, initial_size[0] - 7, 16))
                    if not any(max(pixel[:3]) < 40 for pixel in rgb.crop(bounds).getdata()):
                        return False
                    if name == "TextEdit":
                        # The edited seven-letter line must replace the longer
                        # original line in the pixels, as well as in the file.
                        line = rgb.crop(tuple(value * scale // 120 for value in (4, 24, 150, 48)))
                        ink = line.convert("L").point(lambda value: 255 if value < 80 else 0).getbbox()
                        return ink and ink[2] <= 75 * scale // 120
                    if name == "Review":
                        return [rgb.getpixel((rgb.width * x // 4, rgb.height * y // 4))
                            for y in (1, 3) for x in (1, 3)] == [
                                (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
                    return True
                rendered_capture = until(window_image, f"{name} rendered content survives scaling")
                if name == "Terminal":
                    # Backing regeneration must retain the entire logical scrollback.
                    assert command(f"focus {wid}")["ok"]
                    copy_selection()
                    until(lambda: copied_text() == baseline, "Terminal scrollback survives scale change")
                    # Font metrics determine the actual window height. Limit
                    # retained-text comparisons to content, clear of its frame.
                    logical_bounds = (30, 30, min(400, w['width'] - 30),
                        min(350, w['height'] - w.get('frame_bottom', 0) - 2))
                    bounds = tuple(value * scale // 120 for value in logical_bounds)
                    def visible_text():
                        image = capture(scale, w)
                        return image.crop(bounds).tobytes() if image else None

                    before = until(visible_text, "Terminal tail rendered")
                    crop_size = (bounds[2] - bounds[0], bounds[3] - bounds[1])
                    Image.frombytes('RGB', crop_size, before).save(directory / f'tail-{scale}-before.png')
                    before_frame = until(lambda: capture(scale, w), "Terminal complete frame before scrolling")
                    before_frame.save(directory / f'frame-{scale}-before.png')
                    assert command(f"pointer {w['x'] + 100} {w['y'] + 100}")["ok"]
                    assert command("scroll 1000")["ok"]
                    scrolled = until(lambda: (text if (text := visible_text()) not in (None, before) else None),
                                     "Terminal scrolls into retained history")
                    Image.frombytes('RGB', crop_size, scrolled).save(directory / f'tail-{scale}-scrolled.png')
                    assert command("scroll -1000")["ok"]
                    try:
                        until(lambda: visible_text() == before, "Terminal redraws the same tail after scrolling")
                        until(lambda: (frame := capture(scale, w)) is not None and
                            frame.tobytes() == before_frame.tobytes(),
                            "Terminal frame and scroller repaint identically after scrolling")
                    finally:
                        returned = capture(scale, w)
                        if returned:
                            returned.crop(bounds).save(directory / f'tail-{scale}-returned.png')
                            returned.save(directory / f'frame-{scale}-returned.png')
                elif name == "TextEdit":
                    assert document.read_text(encoding="utf-8-sig") == "wayland\n"
                elif name == "TimeMon":
                    before = rendered_capture.tobytes()
                    # Create a small, bounded change in real CPU load. The test
                    # observes graph pixels rather than a timer or file timestamp.
                    load = subprocess.Popen(["yes"], stdout=subprocess.DEVNULL)
                    try:
                        until(lambda: (image := capture(scale, w)) is not None and image.tobytes() != before,
                              "TimeMon graph updates at the current density")
                    finally:
                        load.terminate(); load.wait(timeout=5)
                results.append(dict(application=name, scale=scale, window=w))
            if name == "Review" and programs.get("review_probe"):
                from review import run as review_workflow, run_scroll as review_scroll, run_formats as review_formats, run_saves as review_saves
                results.extend(review_workflow(command, app_env, directory / "multipage", process.pid, programs["review_probe"]))
                results.extend(review_scroll(command, app_env, directory / "scrolling", process.pid, programs["review_probe"]))
                results.extend(review_formats(command, app_env, directory / "formats", process.pid,
                    programs["review_probe"], directory / "scrolling/scroll-pattern.png"))
                results.extend(review_saves(command, app_env, directory / "saving", process.pid, programs["review_probe"]))
        except BaseException:
            try:
                capture_process_failure(process, directory, 'failure-application')
                (directory / "failure.json").write_text(json.dumps(dict(windows=command("windows"),
                    exit_code=process.poll(), clipboard=clipboard), indent=2) + "\n")
            except Exception as diagnostic_error:
                (directory / 'failure-diagnostic.txt').write_text(repr(diagnostic_error) + '\n')
            raise
        finally:
            if process.poll() is None:
                process.terminate(); process.wait(timeout=5)
        assert command(f"test-scale {target} 180 10000")["ok"]
        assert command("confirm")["ok"]
    assert len(set(identities.values())) == len(identities), identities
    for output in initial_outputs:
        assert command(f"test-scale {output['name']} {output['scale']} 10000")["ok"]
        assert command("confirm")["ok"]
    return results
