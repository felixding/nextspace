"""Measure native buffer lifetimes across repeated resizing and scale changes."""

import argparse
import json
from pathlib import Path
import subprocess
import time
from PIL import Image
from gnustep import headless_session, pasteboard_storage, process_runtime
from integration import until, read_json_lines, submitted_image_pixels


def resources(pid):
    proc = Path("/proc") / str(pid)
    maps = (proc / "maps").read_text().splitlines()
    buffers = []
    for row in maps:
        if "/memfd:nextspace-buffer " in row:
            fields = row.split(None, 5)
            lo, hi = fields[0].split("-")
            buffers.append(
                dict(
                    inode=int(fields[4]),
                    bytes=int(hi, 16) - int(lo, 16),
                    path=fields[5],
                )
            )
    status = dict(
        line.split(":", 1)
        for line in (proc / "status").read_text().splitlines()
        if ":" in line
    )
    return dict(
        pid=pid,
        fd_count=len(list((proc / "fd").iterdir())),
        shm_mappings=len(buffers),
        shm_bytes=sum(b["bytes"] for b in buffers),
        rss_kib=int(status["VmRSS"].split()[0]),
        buffers=buffers,
    )


def run(compositor, probe, pasteboard_server, pasteboard_probe, artifacts, batches=25):
    if batches < 6:
        raise ValueError(
            "Five warmup batches and at least one measured batch are required"
        )
    root = artifacts
    root.mkdir(parents=True)
    samples = []
    frames = []
    pending_paints = []
    with (
        headless_session(compositor, root / "native") as (env, command),
        pasteboard_storage(pasteboard_server, pasteboard_probe, env, root),
    ):
        server_pid = json.loads((root / "native/compositor-runtime.json").read_text())[
            "pid"
        ]
        server_before = resources(server_pid)
        with (
            (root / "probe.log").open("w") as log,
            (root / "probe.stderr").open("w") as err,
        ):
            client = subprocess.Popen(
                [
                    str(probe),
                    "-GSBackend",
                    "libgnustep-wayland",
                    "-GSTheme",
                    "NextSpace",
                ],
                env=env,
                stdout=log,
                stderr=err,
            )

        def window():
            assert client.poll() is None, (root / "probe.stderr").read_text()[-3000:]
            return next(
                (
                    w
                    for w in command("windows")
                    if w["pid"] == client.pid
                    and w["title"] == "WaylandProbe"
                    and w["visible"]
                    and not (w["style"] & 64)
                ),
                None,
            )

        def transition(output, density, width, height):
            old = window()
            if (old["width"], old["height"], old["preferred_scale"]) == (
                width,
                height,
                density,
            ):
                width, height = (997, 699) if width == 801 else (801, 601)
            capture = (
                root / "native/captures" / f"window-{old['client_id']}-{density}.png"
            )
            stamp = capture.stat().st_mtime_ns if capture.exists() else 0
            began = time.monotonic()
            assert command(f"test-scale {output['name']} {density} 10000")["ok"]
            assert command("confirm")["ok"]
            current = next(o for o in command("outputs") if o["name"] == output["name"])
            assert command(f"resize {old['id']} {width} {height}")["ok"]
            assert command(f"move {old['id']} {current['x'] + 10} {current['y'] + 10}")[
                "ok"
            ]
            expected = ((width * density + 60) // 120, (height * density + 60) // 120)

            pending_recorded = False

            def ready():
                nonlocal pending_recorded
                w = window()
                if (
                    w["preferred_scale"] != density
                    or (w["width"], w["height"]) != (width, height)
                    or (w["buffer_width"], w["buffer_height"]) != expected
                ):
                    return None
                try:
                    if capture.stat().st_mtime_ns <= stamp:
                        return None
                    with Image.open(capture) as image:
                        if image.size != expected:
                            return None
                        image.load()
                    submitted_image_pixels(
                        image.convert("RGB"), pattern, (width, height), density
                    )
                    return w
                except AssertionError as error:
                    # Geometry can arrive before AppKit finishes its repaint.
                    # Retain evidence while waiting for complete submitted pixels.
                    if not pending_recorded:
                        pending_paints.append(
                            dict(
                                frame=len(frames),
                                density=density,
                                logical=[width, height],
                                seconds=time.monotonic() - began,
                                reason=str(error),
                            )
                        )
                        if len(pending_paints) <= 3:
                            image.save(
                                root / f"pending-paint-{len(pending_paints)}.png"
                            )
                        pending_recorded = True
                    return None
                except OSError:
                    return None

            actual = until(ready, "complete native resized/scaled pixels")
            elapsed = time.monotonic() - began
            frames.append(
                dict(
                    window_id=actual["id"],
                    client_id=actual["client_id"],
                    style=actual["style"],
                    density=density,
                    logical=[width, height],
                    backing=list(expected),
                    seconds=elapsed,
                )
            )
            return actual

        try:
            initial = until(window, "native resource-stress window")
            pattern = until(
                lambda: next(
                    (
                        e
                        for e in read_json_lines(root / "probe.log", "{")
                        if e.get("event") == "pixel-pattern"
                    ),
                    None,
                ),
                "submitted pattern metadata",
            )
            outputs = command("outputs")
            target = outputs[0]
            origin = outputs[1]
            for batch in range(batches):
                for index, density in enumerate((120, 150, 180, 210, 240)):
                    transition(
                        target,
                        density,
                        801 + ((batch + index) % 2) * 196,
                        601 + ((batch + index) % 2) * 98,
                    )
                transition(origin, 120, 801, 601)
                sample = dict(
                    batch=batch,
                    client=resources(client.pid),
                    compositor=resources(server_pid),
                )
                samples.append(sample)
                (root / "samples.json").write_text(json.dumps(samples, indent=2) + "\n")
                print(
                    "batch",
                    batch,
                    "client",
                    sample["client"]["shm_mappings"],
                    sample["client"]["shm_bytes"],
                    sample["client"]["rss_kib"],
                    "server",
                    sample["compositor"]["shm_mappings"],
                    flush=True,
                )
            warm = samples[4]
            last = samples[-1]
            max_bytes = 4 * (997 * 2) * (699 * 2)
            growth = {}
            for actor in ("client", "compositor"):
                first = warm[actor]
                tail = [r[actor] for r in samples[5:]]
                assert max(r["fd_count"] for r in tail) <= first["fd_count"] + 2, (
                    actor,
                    "unbounded file descriptors",
                    samples,
                )
                assert (
                    max(r["shm_mappings"] for r in tail) <= first["shm_mappings"] + 3
                ), (actor, "unbounded shared buffer mappings", samples)
                assert (
                    max(r["shm_bytes"] for r in tail)
                    <= first["shm_bytes"] + 3 * max_bytes
                ), (actor, "unbounded shared buffer bytes", samples)
                assert (
                    last[actor]["rss_kib"] <= first["rss_kib"] + 6 * max_bytes / 1024
                ), (actor, "RSS growth exceeds six largest buffers", samples)
                growth[actor] = {
                    key: last[actor][key] - first[key]
                    for key in ("fd_count", "shm_mappings", "shm_bytes", "rss_kib")
                }
            actors = dict(
                client=process_runtime(client.pid),
                compositor=process_runtime(server_pid),
            )
            assert command(f"close {initial['id']}")["ok"]
            client.wait(timeout=10)
            assert client.returncode == 0
            until(
                lambda: not any(w["pid"] == client.pid for w in command("windows")),
                "all client surfaces reaped",
            )
            after = until(
                lambda: (
                    r
                    if (r := resources(server_pid))["shm_mappings"]
                    <= server_before["shm_mappings"]
                    else None
                ),
                "all client shared mappings released by compositor",
            )
            result = dict(
                passed=True,
                resize_scale_move_frames=len(frames),
                batches=len(samples),
                warmup_batches=5,
                densities=[100, 125, 150, 175, 200],
                growth_after_warmup=growth,
                frames=frames,
                samples=samples,
                pending_paints=pending_paints,
                actors=actors,
                server_before=server_before,
                server_after_client_exit=after,
                normal_close_exit_code=client.returncode,
                headless_pixman=True,
                physical_gpu_qualified=False,
                performance_release_qualified=False,
                full_plan_complete=False,
            )
            (root / "result.json").write_text(json.dumps(result, indent=2) + "\n")
            print(
                "Native buffer resize/scale stress: bounded resources and full shared-buffer release PASS",
                flush=True,
            )
            return result
        except BaseException:
            (root / "failure.json").write_text(
                json.dumps(
                    dict(windows=command("windows"), samples=samples, frames=frames),
                    indent=2,
                )
                + "\n"
            )
            raise
        finally:
            if client.poll() is None:
                client.terminate()
                client.wait(timeout=5)


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
    parser.add_argument("--batches", type=int, default=25)
    args = parser.parse_args()
    run(
        args.compositor,
        args.probe,
        args.pasteboard_server,
        args.pasteboard_probe,
        args.artifacts,
        args.batches,
    )
