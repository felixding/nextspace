#!/usr/bin/env python3
"""Verify native pattern colors, density, transforms, phase and actual clip shapes."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from PIL import Image
from gnustep import headless_session, pasteboard_storage, process_runtime
from integration import until, read_json_lines

DENSITIES = (120, 150, 180, 210, 240)


def sample(image, window, density, height, x, y):
    return image.getpixel(
        (
            int((window["frame_left"] + x) * density / 120),
            int((window["frame_top"] + height - y) * density / 120),
        )
    )


def difference(a, b):
    return max(abs(x - y) for x, y in zip(a, b))


def formats(image, window, density, metadata):
    pixels = [sample(image, window, density, 216, 56.5, y) for y in range(16, 185, 24)]
    solid = (255, 0, 0, 255) if density == 120 else (0, 0, 255, 255)
    alpha = (227, 167, 147, 255) if density == 120 else (147, 207, 237, 255)
    expected = [
        solid,
        alpha,
        None,
        (0, 255, 0, 255),
        (170, 170, 170, 255),
        (64, 192, 32, 255),
        solid,
        (0, 255, 0, 255),
    ]
    for index, (actual, color) in enumerate(zip(pixels, expected)):
        if color is not None:
            assert difference(actual, color) <= 1, (
                "pattern color or format",
                index,
                density,
                actual,
                color,
            )
    outside = sample(image, window, density, 216, 9.5, 153.5)
    assert outside == (255, 255, 255, 255), ("ellipse filled its bounding box", outside)
    stripe_y = int((window["frame_top"] + 216 - 64) * density / 120)
    stripe_x = int((window["frame_left"] + 8) * density / 120)
    stripe = [image.getpixel((stripe_x + i, stripe_y)) for i in range(24)]
    if density == 240:
        assert all(c[:3] in ((0, 0, 0), (255, 255, 255)) for c in stripe), stripe
        assert all(a != b for a, b in zip(stripe, stripe[1:])), stripe
    return dict(
        submitted_samples=pixels,
        expected_solid_samples=expected,
        ellipse_outside=outside,
        stripe_row=stripe,
    )


def transforms(image, window, density, metadata):
    assert {case["profile"] for case in metadata["cases"]} == set(range(9)), metadata
    details = []
    for case in metadata["cases"]:
        profile = case["profile"]
        ox, oy = 8, 24 + 80 * profile
        for pair in case["pairs"]:
            assert abs(pair["reference_x"] - pair["x"] - 160) < 0.0001
            assert abs(pair["reference_y"] - pair["y"]) < 0.0001
            x, y = pair["x"] - ox, pair["y"] - oy
            if profile == 2:
                x, y = x / 1.5, y / 1.25
            elif profile == 3:
                x, y = y + 26, 46 - x
            elif profile == 4:
                y = 20 - y
            for dx, dy, color in (
                (0, 0, (0, 0, 255, 255)),
                (4, 0, (255, 255, 0, 255)),
                (0, 3, (255, 0, 0, 255)),
                (4, 3, (0, 255, 0, 255)),
            ):
                if not (1 <= x + dx < 71 and 1 <= y + dy < 19):
                    continue
                if profile == 2:
                    tx, ty = dx * 1.5, dy * 1.25
                elif profile == 3:
                    tx, ty = -dy, dx
                elif profile == 4:
                    tx, ty = dx, -dy
                else:
                    tx, ty = dx, dy
                expected = (
                    (255, 255, 255, 255)
                    if profile == 8
                    or (profile == 6 and 20 <= x + dx < 52 and 4 <= y + dy < 16)
                    else color
                )
                actual = sample(
                    image,
                    window,
                    density,
                    metadata["content_height"],
                    pair["x"] + tx,
                    pair["y"] + ty,
                )
                reference = sample(
                    image,
                    window,
                    density,
                    metadata["content_height"],
                    pair["reference_x"] + tx,
                    pair["reference_y"] + ty,
                )
                assert difference(reference, expected) <= 1, (
                    "ordinary tiled image",
                    profile,
                    density,
                    x + dx,
                    y + dy,
                    reference,
                    expected,
                )
                maximum = difference(actual, reference)
                assert maximum <= 1, (
                    "pattern differs from tiled image",
                    profile,
                    density,
                    x + dx,
                    y + dy,
                    actual,
                    reference,
                )
                details.append(
                    dict(
                        profile=profile,
                        logical=[x + dx, y + dy],
                        pattern=[pair["x"] + tx, pair["y"] + ty],
                        reference_point=[
                            pair["reference_x"] + tx,
                            pair["reference_y"] + ty,
                        ],
                        expected=expected,
                        actual=actual,
                        reference=reference,
                        maximum_channel_difference=maximum,
                    )
                )
    assert len(details) == 864, len(details)
    return dict(comparisons=details)


def run(compositor, probe, pasteboard_server, pasteboard_probe, artifacts):
    artifacts.mkdir(parents=True)
    reports = []
    for profile, check, event in (
        ("formats", formats, "pattern"),
        ("transforms", transforms, "pattern-transform"),
    ):
        root = artifacts / profile
        root.mkdir()
        records = []
        pending = []
        with headless_session(compositor, root / "session") as (env, command):
            with pasteboard_storage(pasteboard_server, pasteboard_probe, env, root):
                with (
                    (root / "probe.log").open("w") as out,
                    (root / "probe.stderr").open("w") as err,
                ):
                    client = subprocess.Popen(
                        [
                            str(probe),
                            "-GSBackend",
                            "libgnustep-wayland",
                            "-GSTheme",
                            "NextSpace",
                            "-ArtworkPatterns",
                            "YES",
                            "-ArtworkPatternTransforms",
                            "YES" if profile == "transforms" else "NO",
                        ],
                        env=env,
                        stdout=out,
                        stderr=err,
                    )

                def events():
                    return [
                        row
                        for row in read_json_lines(root / "probe.log", "{")
                        if row.get("event") == event
                    ]

                def window():
                    assert client.poll() is None, (root / "probe.stderr").read_text()[
                        -3000:
                    ]
                    return next(
                        (
                            w
                            for w in command("windows")
                            if w["pid"] == client.pid
                            and w["title"] == "PatternArtwork"
                            and w["visible"]
                        ),
                        None,
                    )

                try:
                    until(window, "native " + profile + " pattern window")
                    until(lambda: events(), "complete pattern draw metadata")
                    target = command("outputs")[0]
                    assert command(f"resize-output {target['name']} 1600 1800")["ok"]
                    target = next(
                        o for o in command("outputs") if o["name"] == target["name"]
                    )
                    for density in DENSITIES:
                        assert command(f"test-scale {target['name']} {density} 15000")[
                            "ok"
                        ]
                        assert command("confirm")["ok"]
                        w = window()
                        assert command(
                            f"move {w['id']} {target['x'] + 20} {target['y'] + 20}"
                        )["ok"]
                        metadata = until(
                            lambda: next(
                                (
                                    r
                                    for r in reversed(events())
                                    if r["scale"] == density / 120
                                ),
                                None,
                            ),
                            "pattern metadata at tested density",
                        )
                        recorded = False

                        def ready():
                            nonlocal recorded
                            current = window()
                            if current["preferred_scale"] != density:
                                return None
                            picture = (
                                root
                                / "session/captures"
                                / f"window-{current['client_id']}-{density}.png"
                            )
                            try:
                                with Image.open(picture) as source:
                                    if source.size != (
                                        current["buffer_width"],
                                        current["buffer_height"],
                                    ):
                                        return None
                                    image = source.convert("RGBA")
                                result = check(image, current, density, metadata)
                                return current, picture.read_bytes(), result
                            except AssertionError as error:
                                if not recorded:
                                    pending.append(
                                        dict(density=density, reason=str(error))
                                    )
                                    image.save(root / f"pending-{density}.png")
                                    recorded = True
                                return None
                            except OSError:
                                return None

                        current, pixels, result = until(
                            ready,
                            "complete and correct native "
                            + profile
                            + " pattern pixels",
                        )
                        name = f"{profile}-{density}.png"
                        (root / name).write_bytes(pixels)
                        records.append(
                            dict(
                                density=density,
                                window=current,
                                metadata=metadata,
                                capture=name,
                                sha256=hashlib.sha256(pixels).hexdigest(),
                                **result,
                            )
                        )
                    (root / "application-runtime.json").write_text(
                        json.dumps(process_runtime(client.pid), indent=2) + "\n"
                    )
                    assert command(f"close {window()['id']}")["ok"]
                    assert client.wait(timeout=10) == 0
                except BaseException:
                    (root / "failure.json").write_text(
                        json.dumps(
                            dict(
                                cases=records,
                                pending=pending,
                                windows=command("windows"),
                                events=events(),
                            ),
                            indent=2,
                        )
                        + "\n"
                    )
                    raise
                finally:
                    if client.poll() is None:
                        client.terminate()
                        client.wait(timeout=5)
        report = dict(
            passed=True,
            profile=profile,
            normal_close=True,
            cases=records,
            pending_paints=pending,
            physical_gpu_qualified=False,
            full_plan_complete=False,
        )
        (root / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        reports.append(report)
    result = dict(
        passed=True,
        native_captures=sum(len(p["cases"]) for p in reports),
        transform_pixel_comparisons=sum(
            len(c["comparisons"])
            for p in reports
            if p["profile"] == "transforms"
            for c in p["cases"]
        ),
        formats=[
            "RGBA",
            "unassociated alpha",
            "RGB",
            "grayscale",
            "planar RGB",
            "vector",
        ],
        logical_phase_before_and_after_color=True,
        graphics_state_phase_restored=True,
        scale_rotation_reflection=True,
        curved_fills=True,
        even_odd_and_empty_clips=True,
        normal_close=True,
        physical_gpu_qualified=False,
        full_plan_complete=False,
    )
    (artifacts / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        "Native patterns: formats, density, phase, transforms and clipped images PASS",
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
    args = parser.parse_args()
    run(
        args.compositor,
        args.probe,
        args.pasteboard_server,
        args.pasteboard_probe,
        args.artifacts,
    )
