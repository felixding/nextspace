#!/usr/bin/env python3
"""Cycle an actual NSProgressIndicator through all six frames at each density."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from PIL import Image
from gnustep import headless_session, pasteboard_storage, process_runtime
from integration import until, read_json_lines
from image_usage import summarize
from progress_artwork import SIZES, PHASES


def frame_pixels(image, window, density, metadata):
    factor = density / 120
    left = window["frame_left"] + metadata["x"] + 4
    top = (
        window["frame_top"]
        + metadata["content_height"]
        - metadata["y"]
        - metadata["height"]
        + 4
    )
    width, height = metadata["width"] - 8, metadata["height"] - 8
    # Original native 100% captures pin this fixture's flipped tile origin.
    # Test interior points clear of the diagonal sampling fringe at every scale.
    phase = PHASES[metadata["frame"] - 1] + 1
    checks = 0
    for y in range(int(top * factor) + 2, int((top + height) * factor) - 2, 3):
        for x in range(int(left * factor) + 2, int((left + width) * factor) - 2, 5):
            position = (
                (x + 0.5) / factor - left - ((y + 0.5) / factor - top) + phase
            ) % 12
            if min(position, abs(position - 6), 12 - position) < 1.25:
                continue
            expected = 0 if position < 6 else 153
            actual = image.getpixel((x, y))
            assert (
                actual[3] == 255 and max(abs(c - expected) for c in actual[:3]) <= 1
            ), (
                "Stale or incorrect progress frame",
                metadata["frame"],
                density,
                x,
                y,
                actual,
                expected,
            )
            checks += 1
    assert checks >= 86
    crop = image.crop(
        (
            int(left * factor),
            int(top * factor),
            int(left * factor) + int(width * factor),
            int(top * factor) + int(height * factor),
        )
    )
    return crop, checks


def spinner_pixels(image, window, density, metadata):
    from artwork_reference import artwork_original

    original, _ = artwork_original(
        "progress-spinners", "common_ProgressSpinning_" + str(metadata["frame"])
    )
    # NSProgressIndicator is flipped; the pinned original native run verifies
    # this NSImage drawing orientation before the resource overlay is applied.
    original = original.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    factor = density / 120
    left = window["frame_left"] + metadata["x"]
    top = (
        window["frame_top"]
        + metadata["content_height"]
        - metadata["y"]
        - metadata["height"]
    )
    checks = 0
    for y in range(2, 30):
        for x in range(2, 30):
            color = original.getpixel((x, y))
            if color[3] != 255 or not all(
                original.getpixel((x + dx, y + dy)) == color
                for dx in (-2, -1, 0, 1, 2)
                for dy in (-2, -1, 0, 1, 2)
            ):
                continue
            actual = image.getpixel(
                (int((left + x + 0.5) * factor), int((top + y + 0.5) * factor))
            )
            assert max(abs(a - b) for a, b in zip(color, actual)) <= 1, (
                "Stale or incorrect spinner frame",
                metadata["frame"],
                density,
                x,
                y,
                color,
                actual,
            )
            checks += 1
    assert checks >= 334
    return image.crop(
        (
            int(left * factor),
            int(top * factor),
            int(left * factor) + int(metadata["width"] * factor),
            int(top * factor) + int(metadata["height"] * factor),
        )
    ), checks


def run(
    compositor,
    probe,
    pasteboard_server,
    pasteboard_probe,
    artifacts,
    usage_observer=None,
    *,
    spinner=False,
):
    if spinner:
        from spinner_artwork import SIZES as sizes
    else:
        sizes = SIZES
    frame_count, unique_phases = (8, 8) if spinner else (6, 3)
    check_pixels = spinner_pixels if spinner else frame_pixels
    artifacts.mkdir(parents=True)
    traces = artifacts / "traces"
    traces.mkdir()
    extra = (
        dict(LD_PRELOAD=str(usage_observer), NEXTSPACE_IMAGE_USAGE_DIR=str(traces))
        if usage_observer
        else {}
    )
    cases = []
    with headless_session(compositor, artifacts / "session", extra_env=extra) as (
        env,
        command,
    ):
        with pasteboard_storage(pasteboard_server, pasteboard_probe, env, artifacts):
            with (
                (artifacts / "probe.log").open("w") as out,
                (artifacts / "probe.stderr").open("w") as err,
            ):
                process = subprocess.Popen(
                    [
                        str(probe),
                        "-GSBackend",
                        "libgnustep-wayland",
                        "-GSTheme",
                        "NextSpace",
                        "-ArtworkProgress",
                        "YES",
                        "-ArtworkSpinner",
                        "YES" if spinner else "NO",
                    ],
                    env=env,
                    stdout=out,
                    stderr=err,
                )

            def events():
                return [
                    r
                    for r in read_json_lines(artifacts / "probe.log", "{")
                    if r.get("event") == "progress"
                ]

            def window():
                assert process.poll() is None, (artifacts / "probe.stderr").read_text()[
                    -2500:
                ]
                return next(
                    (
                        w
                        for w in command("windows")
                        if w["pid"] == process.pid
                        and w["title"] == "ProgressArtwork"
                        and w["visible"]
                    ),
                    None,
                )

            try:
                until(window, "real progress window")
                until(lambda: events(), "initial progress draw")
                output = command("outputs")[0]
                for density in (120, 150, 180, 210, 240):
                    assert command(f"test-scale {output['name']} {density} 15000")["ok"]
                    assert command("confirm")["ok"]
                    current = window()
                    assert command(
                        f"move {current['id']} {output['x'] + 20} {output['y'] + 20}"
                    )["ok"]
                    until(
                        lambda: (
                            window()["preferred_scale"] == density
                            and events()[-1]["scale"] == density / 120
                        ),
                        "real progress at requested density",
                    )
                    crops = {}
                    for _ in range(frame_count):
                        sequence = events()[-1]["sequence"] + 1
                        current = window()
                        picture = (
                            artifacts
                            / "session/captures"
                            / f"window-{current['client_id']}-{density}.png"
                        )
                        before = picture.stat().st_mtime_ns if picture.exists() else 0
                        # Ordinary public button action calls NSProgressIndicator.animate:.
                        x = current["x"] + current["frame_left"] + 128
                        y = current["y"] + current["frame_top"] + 112 - 30
                        assert command(f"pointer {x} {y}")["ok"]
                        assert command("button 272 1")["ok"]
                        assert command("button 272 0")["ok"]

                        def painted():
                            meta = next(
                                (
                                    r
                                    for r in reversed(events())
                                    if r["sequence"] == sequence
                                    and r["scale"] == density / 120
                                ),
                                None,
                            )
                            if (
                                not meta
                                or not picture.exists()
                                or picture.stat().st_mtime_ns <= before
                            ):
                                return None
                            current = window()
                            try:
                                with Image.open(picture) as source:
                                    if source.size != (
                                        current["buffer_width"],
                                        current["buffer_height"],
                                    ):
                                        return None
                                    image = source.convert("RGBA")
                                crop, checks = check_pixels(
                                    image, current, density, meta
                                )
                                colors = {p[:3] for p in crop.getdata()}
                                if not spinner and not {
                                    (0, 0, 0),
                                    (153, 153, 153),
                                }.issubset(colors):
                                    return None
                                if not spinner and set(colors) - {
                                    (0, 0, 0),
                                    (153, 153, 153),
                                }:
                                    # Fractional pattern sampling may blend only the two original colors.
                                    if any(
                                        r != g or g != b or r > 153
                                        for r, g, b in colors
                                    ):
                                        return None
                                return current, meta, picture.read_bytes(), crop, checks
                            except AssertionError as error:
                                pending = (
                                    artifacts / f"pending-{sequence}-{density}.json"
                                )
                                if not pending.exists():
                                    pending.write_text(
                                        json.dumps(
                                            dict(reason=str(error), state=meta),
                                            indent=2,
                                        )
                                        + "\n"
                                    )
                                    image.save(pending.with_suffix(".png"))
                                return None
                            except OSError:
                                return None

                        current, meta, pixels, crop, checks = until(
                            painted, "completed real progress animation frame"
                        )
                        frame = meta["frame"]
                        name = f"frame-{frame}-{density}.png"
                        (artifacts / name).write_bytes(pixels)
                        crops[frame] = crop.tobytes()
                        cases.append(
                            dict(
                                density=density,
                                sequence=sequence,
                                frame=frame,
                                known_pixel_checks=checks,
                                state=meta,
                                window=current,
                                capture=name,
                                sha256=hashlib.sha256(pixels).hexdigest(),
                                interior_sha256=hashlib.sha256(
                                    crop.tobytes()
                                ).hexdigest(),
                            )
                        )
                    assert set(crops) == set(range(1, frame_count + 1))
                    assert spinner or all(
                        crops[i] == crops[i + 3] for i in range(1, 4)
                    ), "Repeated original animation phases differ"
                    assert len(set(crops.values())) == unique_phases, (
                        "Original three stripe phases did not animate"
                    )
                (artifacts / "application-runtime.json").write_text(
                    json.dumps(process_runtime(process.pid), indent=2) + "\n"
                )
                assert command(f"close {window()['id']}")["ok"]
                assert process.wait(timeout=10) == 0
            except BaseException:
                (artifacts / "failure.json").write_text(
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
    usage = None
    if usage_observer:
        usage = summarize(traces)
        (artifacts / "image-usage.json").write_text(json.dumps(usage, indent=2) + "\n")
        assert not usage["errors"]
        resources = {
            Path(name).stem: item
            for name, item in usage["resources"].items()
            if Path(name).stem in sizes
        }
        assert set(resources) == set(sizes), resources.keys()
        for item in resources.values():
            assert not item["potential_undersampled_draws"], item
            assert {draw["window_scale"] for draw in item["draws"]} == {
                1,
                1.25,
                1.5,
                1.75,
                2,
            }, item
    result = dict(
        passed=True,
        native_captures=len(cases),
        button_actions=frame_count * 5,
        known_pixel_checks=sum(c["known_pixel_checks"] for c in cases),
        real_progress_animation_frames=frame_count,
        unique_original_phases=unique_phases,
        spinner=spinner,
        repeated_phases_identical=None if spinner else True,
        normal_close=True,
        observed_resources=frame_count if usage else 0,
        cases=cases,
        full_plan_complete=False,
    )
    (artifacts / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        f"Real progress indicator: {frame_count * 5} frame actions and captures PASS.",
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
        "usage-observer",
    ):
        parser.add_argument("--" + name, type=Path, required=name != "usage-observer")
    parser.add_argument("--spinner", action="store_true")
    args = parser.parse_args()
    run(
        args.compositor,
        args.probe,
        args.pasteboard_server,
        args.pasteboard_probe,
        args.artifacts,
        args.usage_observer,
        spinner=args.spinner,
    )
