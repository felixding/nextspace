#!/usr/bin/env python3
"""Exercise TextEdit's real font panel and all four rich-text ruler markers."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from PIL import Image
from gnustep import headless_session, pasteboard_storage, process_runtime
from integration import until
from image_usage import summarize
from ruler_artwork import SIZES


def run(
    compositor,
    textedit,
    probe,
    artifacts,
    pasteboard_server,
    pasteboard_probe,
    usage_observer=None,
):
    root = artifacts
    root.mkdir(parents=True)
    traces = root / "traces"
    traces.mkdir()
    document = root / "document.txt"
    text = "NEXTSPACE rich text and font panel\nLeft\tCenter\tRight\t12.34\n"
    document.write_text(text)
    cases = []
    helper = probe
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
            with (root / "textedit.log").open("w") as log:
                process = subprocess.Popen(
                    [
                        str(textedit),
                        "-GSBackend",
                        "libgnustep-wayland",
                        "-GSTheme",
                        "NextSpace",
                        "-GSFilePath",
                        str(document),
                        "-NSUseRunningCopy",
                        "NO",
                    ],
                    env=env,
                    stdout=log,
                    stderr=log,
                )

            def windows():
                assert process.poll() is None, (root / "textedit.log").read_text()[
                    -3500:
                ]
                return [
                    w
                    for w in command("windows")
                    if w["pid"] == process.pid and w["visible"]
                ]

            try:
                main = until(
                    lambda: next(
                        (w for w in windows() if "document.txt" in w["title"]), None
                    ),
                    "actual TextEdit document",
                )
                target = command("outputs")[0]
                assert command(f"resize-output {target['name']} 1600 1800")["ok"]
                target = next(
                    o for o in command("outputs") if o["name"] == target["name"]
                )
                for action in ("font", "ruler"):
                    result = subprocess.run(
                        [str(helper), "--textedit-panel", action],
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=20,
                    )
                    (root / (action + "-action.log")).write_text(
                        result.stdout + result.stderr
                    )
                    assert result.returncode == 0, (result.stdout, result.stderr)
                    metadata = json.loads(result.stdout)
                    if action == "ruler":
                        assert {
                            (m["type"], m["location"])
                            for m in metadata["ruler_markers"]
                        } == {(i, 60 + 60 * i) for i in range(4)}, metadata
                        assert {m["image"] for m in metadata["ruler_markers"]} == set(
                            SIZES
                        ), metadata
                    if action == "font":
                        panel = until(
                            lambda: next(
                                (
                                    w
                                    for w in windows()
                                    if w["id"] != main["id"] and w["width"] > 200
                                ),
                                None,
                            ),
                            "actual font panel",
                        )
                    else:
                        panel = next(w for w in windows() if w["id"] == main["id"])
                    for density in (120, 150, 180, 210, 240):
                        assert command(f"test-scale {target['name']} {density} 15000")[
                            "ok"
                        ]
                        assert command("confirm")["ok"]
                        assert command(
                            f"move {panel['id']} {target['x'] + 20} {target['y'] + 20}"
                        )["ok"]

                        def rendered():
                            current = next(
                                (
                                    w
                                    for w in windows()
                                    if w["id"] == panel["id"]
                                    and w["preferred_scale"] == density
                                ),
                                None,
                            )
                            if not current:
                                return None
                            p = (
                                root
                                / "session/captures"
                                / f"window-{current['client_id']}-{density}.png"
                            )
                            try:
                                with Image.open(p) as im:
                                    if im.size != (
                                        current["buffer_width"],
                                        current["buffer_height"],
                                    ):
                                        return None
                                    im.load()
                                return current, p.read_bytes()
                            except OSError:
                                return None

                        current, pixels = until(
                            rendered, "native TextEdit " + action + " panel capture"
                        )
                        name = f"{action}-{density}.png"
                        (root / name).write_bytes(pixels)
                        cases.append(
                            dict(
                                action=action,
                                density=density,
                                window=current,
                                capture=name,
                                sha256=hashlib.sha256(pixels).hexdigest(),
                            )
                        )
                    if action == "font":
                        assert command(f"close {panel['id']}")["ok"]
                        until(
                            lambda: not any(w["id"] == panel["id"] for w in windows()),
                            "font panel closes normally",
                        )
                        assert command(f"focus {main['id']}")["ok"]
                (root / "application-runtime.json").write_text(
                    json.dumps(process_runtime(process.pid), indent=2) + "\n"
                )
                assert document.read_text() == text
            except BaseException:
                (root / "failure.json").write_text(
                    json.dumps(dict(cases=cases, windows=command("windows")), indent=2)
                    + "\n"
                )
                raise
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)

    remaining = None
    if usage_observer:
        usage = summarize(traces)
        (root / "image-usage.json").write_text(json.dumps(usage, indent=2) + "\n")
        assert not usage["errors"], usage["errors"]
        markers = {
            Path(path).stem: item
            for path, item in usage["resources"].items()
            if Path(path).stem in SIZES
        }
        assert set(markers) == set(SIZES), sorted(markers)
        for name, item in markers.items():
            assert {draw["window_scale"] for draw in item["draws"]} == {
                1,
                1.25,
                1.5,
                1.75,
                2,
            }, name
        remaining = sorted(
            path
            for path, item in usage["resources"].items()
            if item["potential_undersampled_draws"]
        )
        assert not remaining, remaining
    result = dict(
        passed=True,
        native_captures=len(cases),
        ordinary_font_panel_close=True,
        source_file_unchanged=True,
        four_real_ruler_marker_types_verified=True,
        usage_observed=usage_observer is not None,
        remaining_resolution_candidates=remaining,
        artwork_fidelity_approval=False,
        full_plan_complete=False,
        cases=cases,
    )
    (root / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        "TextEdit font and ruler: ten native captures, all four real marker types and normal panel close PASS",
        flush=True,
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "compositor",
        "textedit",
        "probe",
        "artifacts",
        "pasteboard-server",
        "pasteboard-probe",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--usage-observer", type=Path)
    args = parser.parse_args()
    run(
        args.compositor,
        args.textedit,
        args.probe,
        args.artifacts,
        args.pasteboard_server,
        args.pasteboard_probe,
        args.usage_observer,
    )
