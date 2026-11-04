#!/usr/bin/env python3
"""Select every top and bottom NSTabView state through the real pointer path."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from PIL import Image
from gnustep import headless_session, pasteboard_storage, process_runtime
from integration import until, read_json_lines
from image_usage import summarize
from tab_artwork import SIZES


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
    cases = []
    traces = root / "traces"
    traces.mkdir()
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
                (root / "probe.log").open("w") as log,
                (root / "probe.stderr").open("w") as err,
            ):
                process = subprocess.Popen(
                    [
                        str(probe),
                        "-GSBackend",
                        "libgnustep-wayland",
                        "-GSTheme",
                        "NextSpace",
                        "-ArtworkTabs",
                        "YES",
                    ],
                    env=env,
                    stdout=log,
                    stderr=err,
                )

            def reports():
                return [
                    e
                    for e in read_json_lines(root / "probe.log", "{")
                    if e.get("event") == "tabs"
                ]

            def window():
                assert process.poll() is None, (root / "probe.stderr").read_text()[
                    -3000:
                ]
                return next(
                    (
                        w
                        for w in command("windows")
                        if w["pid"] == process.pid
                        and w["title"] == "TabArtwork"
                        and w["visible"]
                    ),
                    None,
                )

            try:
                meta = until(
                    lambda: (
                        reports()[-1]
                        if reports()
                        and len(reports()[-1]["views"]) == 2
                        and all(len(v["headers"]) == 3 for v in reports()[-1]["views"])
                        else None
                    ),
                    "real top and bottom tab header geometry",
                )
                until(window, "real NSTabView window")
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
                        "tab density change",
                    )
                    for orientation in ("top", "bottom"):
                        for selected in (1, 2, 0):
                            before = len(reports())
                            meta = reports()[-1]
                            view = next(
                                v
                                for v in meta["views"]
                                if v["orientation"] == orientation
                            )
                            header = next(
                                h for h in view["headers"] if h["index"] == selected
                            )
                            w = window()
                            picture = (
                                root
                                / "session/captures"
                                / f"window-{w['client_id']}-{density}.png"
                            )
                            old = picture.stat().st_mtime_ns if picture.exists() else 0
                            x = (
                                w["x"]
                                + w["frame_left"]
                                + header["x"]
                                + header["width"] / 2
                            )
                            y = (
                                w["y"]
                                + w["frame_top"]
                                + meta["content_height"]
                                - header["y"]
                                - header["height"] / 2
                            )
                            assert command(f"focus {w['id']}")["ok"]
                            assert command(f"pointer {round(x)} {round(y)}")["ok"]
                            assert command("button 272")["ok"]

                            def selected_state():
                                r = reports()
                                return (
                                    r[-1]
                                    if len(r) > before
                                    and next(
                                        v
                                        for v in r[-1]["views"]
                                        if v["orientation"] == orientation
                                    )["selected"]
                                    == selected
                                    else None
                                )

                            state = until(
                                selected_state,
                                "actual pointer selects "
                                + orientation
                                + " tab "
                                + str(selected),
                            )

                            def rendered():
                                try:
                                    if picture.stat().st_mtime_ns <= old:
                                        return None
                                    with Image.open(picture) as im:
                                        if im.size != (
                                            window()["buffer_width"],
                                            window()["buffer_height"],
                                        ):
                                            return None
                                        im.verify()
                                    return picture.read_bytes()
                                except OSError:
                                    return None

                            pixels = until(
                                rendered, "completed selected-tab native buffer"
                            )
                            filename = f"{orientation}-{selected}-{density}.png"
                            (root / filename).write_bytes(pixels)
                            cases.append(
                                dict(
                                    orientation=orientation,
                                    index=selected,
                                    density=density,
                                    pointer=[x, y],
                                    state=state,
                                    window=window(),
                                    capture=filename,
                                    sha256=hashlib.sha256(pixels).hexdigest(),
                                )
                            )
                (root / "application-runtime.json").write_text(
                    json.dumps(process_runtime(process.pid), indent=2) + "\n"
                )
                assert command(f"close {window()['id']}")["ok"]
                assert process.wait(timeout=10) == 0
            except BaseException:
                (root / "failure.json").write_text(
                    json.dumps(
                        dict(
                            cases=cases, windows=command("windows"), reports=reports()
                        ),
                        indent=2,
                    )
                    + "\n"
                )
                raise
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)

    usage = None
    if usage_observer:
        usage = summarize(traces)
        (root / "image-usage.json").write_text(json.dumps(usage, indent=2) + "\n")
        assert not usage["errors"], usage["errors"]
        tabs = {
            Path(name).stem: item
            for name, item in usage["resources"].items()
            if Path(name).stem.startswith("common_Tab")
        }
        assert set(tabs) == set(SIZES), sorted(tabs)
        for name, item in tabs.items():
            assert {draw["window_scale"] for draw in item["draws"]} == {
                1,
                1.25,
                1.5,
                1.75,
                2,
            }, name
            assert not item["potential_undersampled_draws"], name
    result = dict(
        passed=True,
        pointer_selections=len(cases),
        native_captures=len(cases),
        normal_close=True,
        usage_observed=usage is not None,
        source_original_fidelity_approval=False,
        headless_only=True,
        full_plan_complete=False,
        cases=cases,
    )
    (root / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        "Real top and bottom tabs: thirty pointer selections at five densities PASS",
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
