"""Shared input scenarios for independent and Workspace shell clients."""
import json
import time
from integration import until


def run(shell, command, native_window=None, native_log=None):
    def snapshot():
        before = shell.input_batches
        shell.send("input")
        shell.wait(lambda: shell.input_batches > before, "input settings snapshot")
        return {k: v for k, v in shell.input_settings.items() if k != "event"}

    def apply(request, success=True):
        before = len(shell.input_results)
        shell.send(request)
        shell.wait(lambda: len(shell.input_results) > before, "input settings result")
        assert bool(shell.input_results[-1]["success"]) == success, shell.input_results[-1]

    def keyboard(state):
        return "keyboard " + " ".join(str(state[key]) or "_" for key in (
            "model", "layout", "variant", "options", "delay", "rate", "numlock"))

    initial = snapshot()
    assert initial["accelerated_devices"] == 0, "Headless proof must not claim physical libinput coverage"
    for speed in (-1, -0.5, 0, 0.5, 1):
        for profile in (0, 1):
            apply(f"pointer {speed} {profile}")
            actual = snapshot()
            assert (actual["speed"], actual["profile"]) == (speed, profile), actual
    before = snapshot()
    for invalid in ("pointer 2 0", "pointer 0 2"):
        apply(invalid, False); assert snapshot() == before

    for layout in ("us", "de", "us,jp"):
        state = dict(initial, layout=layout, delay=150, rate=30, numlock=1,
                     options="grp:alt_shift_toggle" if "," in layout else "")
        apply(keyboard(state))
        actual = snapshot()
        assert all(actual[k] == state[k] for k in ("layout", "delay", "rate", "numlock", "options")), actual
    before = snapshot()
    for invalid in (dict(before, layout="nextspace_invalid_layout"), dict(before, delay=10001),
                    dict(before, rate=1001), dict(before, numlock=2)):
        apply(keyboard(invalid), False); assert snapshot() == before

    if native_window:
        def keys():
            return [entry for line in native_log.read_text().splitlines() if line.startswith('{"event":')
                    and (entry := json.loads(line))["event"] == "key"]
        def release(key):
            def handled():
                return sum(1 for line in native_log.read_text().splitlines() if line.startswith('{"event":')
                    and (event := json.loads(line))["event"] == "key-up-handled" and event["keycode"] == key + 8)
            before = handled()
            assert command(f"key {key} 0")["ok"]
            until(lambda: handled() > before, "native release drains preceding repeat events")
        for layout, character in (("de", ord("z")), ("us", ord("y"))):
            apply(keyboard(dict(initial, layout=layout, variant="", options="", delay=100, rate=40, numlock=0)))
            assert command(f"focus {native_window()['id']}")["ok"]
            before = len(keys())
            assert command("key 21 1")["ok"] and command("key 21 0")["ok"]
            until(lambda: len(keys()) > before, "native key after live keymap change")
            assert keys()[-1]["character"] == character, keys()[-1]
        for option, modifier, flags in (("caps:ctrl_modifier", 58, 1 << 18),
                                        ("altwin:swap_lalt_lwin", 56, 1 << 19),
                                        ("altwin:swap_lalt_lwin", 125, 1 << 20)):
            apply(keyboard(dict(initial, layout="us", variant="", options=option, delay=100, rate=40, numlock=0)))
            before = len(keys())
            for code, pressed in ((modifier, 1), (45, 1), (45, 0), (modifier, 0)):
                assert command(f"key {code} {pressed}")["ok"]
            until(lambda: len(keys()) > before, "native key after modifier remapping")
            assert keys()[-1]["modifiers"] & ((1 << 18) | (1 << 19) | (1 << 20)) == flags, keys()[-1]
        apply(keyboard(dict(initial, layout="us", variant="", options="compose:menu", delay=100, rate=40, numlock=0)))
        before = len(keys())
        for code in (127, 40):
            assert command(f"key {code} 1")["ok"] and command(f"key {code} 0")["ok"]
        assert command("key 18 1")["ok"]
        until(lambda: len(keys()) >= before + 3, "composed Unicode text and repeat")
        release(18)
        assert all(event["character"] == ord("é") for event in keys()[before:]), keys()[before:]
        before = len(keys())
        for code in (127, 40, 1, 30):
            assert command(f"key {code} 1")["ok"] and command(f"key {code} 0")["ok"]
        until(lambda: len(keys()) > before, "Escape cancels a compose sequence")
        assert [event["character"] for event in keys()[before:]] == [ord("a")]
        before = len(keys())
        for code, pressed in ((127, 1), (127, 0), (40, 1), (40, 0), (29, 1),
                              (45, 1), (45, 0), (29, 0), (18, 1), (18, 0)):
            assert command(f"key {code} {pressed}")["ok"]
        until(lambda: len(keys()) >= before + 2, "Control shortcut cancels compose without consuming the shortcut")
        assert [event["character"] for event in keys()[before:]] == [24, ord("e")]
        apply(keyboard(dict(initial, layout="us", variant="", options="", delay=100, rate=40, numlock=0)))
        before = len(keys())
        assert command("key 30 1")["ok"]
        until(lambda: len(keys()) >= before + 3, "native repeat uses compositor settings")
        release(30)
        assert any(entry["repeat"] for entry in keys()[before:])
        apply(keyboard(dict(initial, delay=100, rate=0, numlock=0)))
        before = len(keys())
        assert command("key 30 1")["ok"]
        time.sleep(0.3)
        release(30)
        until(lambda: len(keys()) > before, "native key with repeat disabled")
        assert len(keys()) == before + 1, keys()[before:]

    if shell.workspace:
        defaults = ["Command+Up", "Command+Down", "Command+Tab", "Command+Shift+Tab",
                    "Command+grave", "Command+Shift+grave", "Control+Right", "Control+Left"]
        defaults += ["Control+" + str(i) for i in (*range(1, 10), 0)]
        bindings = list(defaults)
        bindings[6:9] = ["Super+Control+Right", "Super+Control+Left", "Shift+F1"]

        def desktop():
            before = len(shell.events)
            shell.send("desktop-count 4")
            return shell.wait(lambda: next((e["current"] + 1 for e in shell.events[before:]
                if e["event"] == "desktop-result"), None), "desktop state after shortcut") - 1

        def stroke(key, modifiers):
            for code in modifiers: assert command(f"key {code} 1")["ok"]
            assert command(f"key {key} 1")["ok"] and command(f"key {key} 0")["ok"]
            for code in reversed(modifiers): assert command(f"key {code} 0")["ok"]

        apply(keyboard(dict(initial, layout="us", variant="", options="", numlock=0)))
        apply(json.dumps(dict(action="shortcuts", bindings=bindings)))
        assert desktop() == 0
        stroke(106, (29,))
        assert desktop() == 0
        stroke(106, (29, 125))
        assert desktop() == 1
        stroke(59, (42,))
        assert desktop() == 0
        for invalid in (bindings[:9], [*bindings[:9], "Shift+F1", *bindings[10:]],
                        ["Hyper+Up", *bindings[1:]]):
            apply(json.dumps(dict(action="shortcuts", bindings=invalid)), False)
            stroke(106, (29, 125))
            assert desktop() == 1
            stroke(59, (42,))
            assert desktop() == 0, "Rejected bindings changed the preceding shortcut table"
        apply(json.dumps(dict(action="shortcuts", bindings=defaults)))
        stroke(106, (29,))
        assert desktop() == 1
        stroke(2, (29,))
        assert desktop() == 0

    apply(keyboard(initial))
    apply(f"pointer {initial['speed']} {initial['profile']}")
    assert snapshot() == initial
    return "input validation, live keymap/repeat/numlock, modifier remapping, compose and saved pointer intent"
