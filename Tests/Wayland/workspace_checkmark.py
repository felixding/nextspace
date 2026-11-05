"""Capture the actual Workspace Dock autostart image cell at all five scales."""

import hashlib
import json
from PIL import Image
from integration import until


def cell_pixels(image, window, density, metadata):
    x, y, width, height = metadata["cell"]
    factor = density / 120
    left = int((window["frame_left"] + x) * factor)
    top = int((window["frame_top"] + metadata["content_height"] - y - height) * factor)
    return image.crop(
        (left, top, left + round(width * factor), top + round(height * factor))
    )


def run(command, query, artifacts):
    artifacts.mkdir(parents=True)
    cases = []
    output = command("outputs")[0]
    assert command(f"resize-output {output['name']} 1600 1800")["ok"]
    for density in (120, 150, 180, 210, 240):
        assert command(f"test-scale {output['name']} {density} 15000")["ok"]
        assert command("confirm")["ok"]
        metadata = query("--dock-checkmark")
        assert metadata["name"] == "CheckMark" and metadata["logical_size"] == [10, 10]

        def current():
            return next(
                (
                    w
                    for w in command("windows")
                    if w["client_id"] == metadata["window"]
                    and w["visible"]
                    and not w["legacy"]
                ),
                None,
            )

        window = until(current, "the actual Dock preferences window")
        assert command(f"move {window['id']} {output['x'] + 20} {output['y'] + 20}")[
            "ok"
        ]
        metadata = until(
            lambda: (
                m
                if (m := query("--dock-checkmark"))["scale"] == density / 120
                else None
            ),
            "Dock autostart cell at the requested density",
        )

        def ready():
            window = current()
            if not window or window["preferred_scale"] != density:
                return None
            # Workspace's standard fixture captures into the parent directory.
            picture = artifacts.parent / f"window-{window['client_id']}-{density}.png"
            try:
                with Image.open(picture) as source:
                    if source.size != (window["buffer_width"], window["buffer_height"]):
                        return None
                    image = source.convert("RGBA")
                cell = cell_pixels(image, window, density, metadata)
                assert cell.width > 5 and cell.height > 5
                assert (
                    len(
                        set(
                            cell.crop((2, 2, cell.width - 2, cell.height - 2)).getdata()
                        )
                    )
                    >= 3
                )
                return window, picture.read_bytes(), cell
            except (OSError, AssertionError):
                return None

        window, pixels, cell = until(
            ready, "completed actual Dock autostart cell pixels"
        )
        name = f"checkmark-{density}.png"
        (artifacts / name).write_bytes(pixels)
        cell.save(artifacts / f"cell-{density}.png")
        cases.append(
            dict(
                density=density,
                window=window,
                metadata=metadata,
                capture=name,
                sha256=hashlib.sha256(pixels).hexdigest(),
                cell_rgba_sha256=hashlib.sha256(cell.tobytes()).hexdigest(),
            )
        )
    result = dict(
        passed=True,
        native_captures=5,
        actual_dock_autostart_cell=True,
        original_logical_image_size=[10, 10],
        cases=cases,
        full_plan_complete=False,
    )
    (artifacts / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Actual Dock CheckMark: five native cell captures PASS", flush=True)
    return result
