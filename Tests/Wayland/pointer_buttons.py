"""Check public AppKit mouse events through real Wayland pointer delivery."""


def check(command, events, until, window_id, output_name, dimensions):
    # Linux button code, AppKit button number, down/drag/up event types.
    buttons = (
        ("left", 272, 0, (1, 6, 2)),
        ("right", 273, 1, (3, 7, 4)),
        ("middle", 274, 2, (25, 27, 26)),
        ("side", 275, 3, (25, 27, 26)),
        ("extra", 276, 4, (25, 27, 26)),
        ("forward", 277, 5, (25, 27, 26)),
        ("back", 278, 6, (25, 27, 26)),
        ("task", 279, 7, (25, 27, 26)),
    )

    def pointer_events():
        return [event for event in events() if event["event"] == "pointer-event"]

    cases = []
    for scale in (120, 150, 180, 210, 240):
        assert command(f"test-scale {output_name} {scale} 10000")["ok"]
        assert command("confirm")["ok"]
        output = next(o for o in command("outputs") if o["name"] == output_name)
        assert command(f"move {window_id} {output['x'] + 10} {output['y'] + 10}")["ok"]
        until(lambda: dimensions(scale), "pointer button density")
        for name, code, number, types in buttons:
            # A changed position produces a fresh motion even after a repeated click.
            assert command(f"pointer {output['x'] + 211} {output['y'] + 311}")["ok"]
            assert command(f"pointer {output['x'] + 210} {output['y'] + 310}")["ok"]
            until(lambda: any(e["type"] == 5 and e["x"] == 200 and e["y"] == 301
                for e in pointer_events()[-3:]), "pointer button start")
            start = len(pointer_events())
            assert command(f"button {code} 1")["ok"]
            down = until(lambda: next((e for e in pointer_events()[start:]
                if e["type"] in (1, 3, 25)), None), "pointer button press")
            start = len(pointer_events())
            assert command(f"pointer {output['x'] + 220} {output['y'] + 320}")["ok"]
            motion = until(lambda: next((e for e in pointer_events()[start:]
                if e["x"] == 210 and e["y"] == 291), None), "pointer button drag")
            start = len(pointer_events())
            assert command(f"button {code} 0")["ok"]
            up = until(lambda: next((e for e in pointer_events()[start:]
                if e["type"] in (2, 4, 26)), None), "pointer button release")
            case = dict(scale=scale, name=name, linux_button=code, down=down, motion=motion, up=up)
            assert tuple(e["type"] for e in (down, motion, up)) == types, case
            assert all(e["button"] == number and e["scale"] == scale / 120
                       for e in (down, motion, up)), case
            assert (down["x"], down["y"]) == (200, 301), case
            assert (up["x"], up["y"]) == (210, 291), case
            cases.append(case)
    assert command(f"test-scale {output_name} 180 10000")["ok"]
    assert command("confirm")["ok"]
    until(lambda: dimensions(180), "restore density after pointer buttons")
    return dict(passed=True, cases=cases, public_pointer_events=len(cases) * 3)
