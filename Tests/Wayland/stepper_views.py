#!/usr/bin/env python3
"""Exercise real stepper values and verify normal/held faces at every density."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from PIL import Image
from gnustep import headless_session, pasteboard_storage, process_runtime
from integration import until, read_json_lines
from image_usage import summarize
from stepper_artwork import SIZES


def run(
    compositor,
    probe,
    pasteboard_server,
    pasteboard_probe,
    artifacts,
    usage_observer=None,
):
    root = artifacts
    root.mkdir(parents=True)
    traces = root / "traces"
    traces.mkdir()
    cases = []
    extra_env = (
        dict(LD_PRELOAD=str(usage_observer), NEXTSPACE_IMAGE_USAGE_DIR=str(traces))
        if usage_observer
        else {}
    )
    with headless_session(compositor, root / "session", extra_env=extra_env) as (
        env,
        command,
    ):
        with pasteboard_storage(pasteboard_server, pasteboard_probe, env, root):
            with (
                (root / "probe.log").open("w") as out,
                (root / "probe.stderr").open("w") as err,
            ):
                process = subprocess.Popen(
                    [
                        str(probe),
                        "-GSBackend",
                        "libgnustep-wayland",
                        "-GSTheme",
                        "NextSpace",
                        "-ArtworkSteppers",
                        "YES",
                    ],
                    env=env,
                    stdout=out,
                    stderr=err,
                )

            def events():
                return [
                    r
                    for r in read_json_lines(root / "probe.log", "{")
                    if r.get("event") == "stepper"
                ]

            def window():
                assert process.poll() is None, (root / "probe.stderr").read_text()[
                    -2500:
                ]
                return next(
                    (
                        w
                        for w in command("windows")
                        if w["pid"] == process.pid
                        and w["title"] == "StepperArtwork"
                        and w["visible"]
                    ),
                    None,
                )

            def capture(label, density, after=0):
                def image():
                    current = window()
                    p = (
                        root
                        / "session/captures"
                        / f"window-{current['client_id']}-{density}.png"
                    )
                    try:
                        if p.stat().st_mtime_ns <= after:
                            return None
                        with Image.open(p) as im:
                            if im.size != (
                                current["buffer_width"],
                                current["buffer_height"],
                            ):
                                return None
                            current = window()
                            meta = events()[-1]
                            for b in meta["buttons"]:
                                expected = (
                                    255
                                    if label == ("up-held" if b["up"] else "down-held")
                                    else 170
                                )
                                x = int(
                                    (current["frame_left"] + b["x"] + 3.5)
                                    * density
                                    / 120
                                )
                                y = int(
                                    (
                                        current["frame_top"]
                                        + meta["content_height"]
                                        - b["y"]
                                        - b["height"] / 2
                                    )
                                    * density
                                    / 120
                                )
                                if (
                                    im.convert("RGB").getpixel((x, y))
                                    != (expected,) * 3
                                ):
                                    return None
                            im.load()
                        return p, p.read_bytes()
                    except OSError:
                        return None

                p, pixels = until(image, "complete real stepper " + label)
                name = f"{label}-{density}.png"
                (root / name).write_bytes(pixels)
                cases.append(
                    dict(
                        state=label,
                        density=density,
                        window=window(),
                        capture=name,
                        sha256=hashlib.sha256(pixels).hexdigest(),
                        value=events()[-1]["value"],
                    )
                )
                return p

            try:
                meta = until(
                    lambda: events()[-1] if events() else None,
                    "actual stepper metadata",
                )
                assert meta["value"] == 50
                until(window, "actual NSStepper")
                target = command("outputs")[0]
                assert command(f"resize-output {target['name']} 1600 1000")["ok"]
                target = next(
                    o for o in command("outputs") if o["name"] == target["name"]
                )
                for density in (120, 150, 180, 210, 240):
                    assert command(f"test-scale {target['name']} {density} 15000")["ok"]
                    assert command("confirm")["ok"]
                    w = window()
                    assert command(
                        f"move {w['id']} {target['x'] + 20} {target['y'] + 20}"
                    )["ok"]
                    until(
                        lambda: window()["preferred_scale"] == density,
                        "stepper density",
                    )
                    capture("normal", density)
                    for up in (True, False):
                        meta = events()[-1]
                        button = next(b for b in meta["buttons"] if bool(b["up"]) == up)
                        w = window()
                        x = w["x"] + w["frame_left"] + button["x"] + button["width"] / 2
                        y = (
                            w["y"]
                            + w["frame_top"]
                            + meta["content_height"]
                            - button["y"]
                            - button["height"] / 2
                        )
                        assert command(f"focus {w['id']}")["ok"]
                        assert command(f"pointer {round(x)} {round(y)}")["ok"]
                        p = (
                            root
                            / "session/captures"
                            / f"window-{w['client_id']}-{density}.png"
                        )
                        old = p.stat().st_mtime_ns
                        before = len(events())
                        assert command("button 272 1")["ok"]
                        image = (
                            "common_Stepper"
                            + ("Up" if up else "Down")
                            + "Highlighted.tiff"
                        )
                        if usage_observer:
                            until(
                                lambda: any(
                                    r.get("name") == image[:-5]
                                    and r.get("window_scale") == density / 120
                                    for path in traces.glob("*.jsonl")
                                    for r in read_json_lines(path, "{")
                                ),
                                "actual highlighted stepper draw",
                            )
                        capture("up-held" if up else "down-held", density, old)
                        assert command("button 272 0")["ok"]
                        expected = 51 if up else 50
                        until(
                            lambda: (
                                len(events()) > before
                                and events()[-1]["value"] == expected
                            ),
                            "ordinary stepper increments and decrements",
                        )
                (root / "application-runtime.json").write_text(
                    json.dumps(process_runtime(process.pid), indent=2) + "\n"
                )
                assert command(f"close {window()['id']}")["ok"]
                assert process.wait(timeout=10) == 0
            except BaseException:
                (root / "failure.json").write_text(
                    json.dumps(
                        dict(cases=cases, windows=command("windows"), events=events()),
                        indent=2,
                    )
                    + "\n"
                )
                raise
            finally:
                command("button 272 0")
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)

    remaining = None
    if usage_observer:
        usage = summarize(traces)
        (root / "image-usage.json").write_text(json.dumps(usage, indent=2) + "\n")
        assert not usage["errors"], usage["errors"]
        steppers = {
            Path(path).stem: item
            for path, item in usage["resources"].items()
            if Path(path).stem.startswith("common_Stepper")
        }
        assert set(steppers) == set(SIZES), sorted(steppers)
        for name, item in steppers.items():
            assert {draw["window_scale"] for draw in item["draws"]} == {
                1,
                1.25,
                1.5,
                1.75,
                2,
            }, name
        remaining = sorted(
            name
            for name, item in steppers.items()
            if item["potential_undersampled_draws"]
        )
        assert not remaining, remaining
    result = dict(
        passed=True,
        native_captures=len(cases),
        ordinary_pointer_actions=10,
        normal_close=True,
        normal_and_held_face_pixels_verified=True,
        usage_observed=usage_observer is not None,
        stepper_undersampling_candidates=remaining,
        full_plan_complete=False,
        cases=cases,
    )
    (root / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        "Real NSStepper: ten increment/decrement actions and fifteen verified native states PASS",
        flush=True,
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "compositor",
        "probe",
        "pasteboard-server",
        "pasteboard-probe",
        "artifacts",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--usage-observer", type=Path)
    args = parser.parse_args()
    run(
        args.compositor,
        args.probe,
        args.pasteboard_server,
        args.pasteboard_probe,
        args.artifacts,
        args.usage_observer,
    )
