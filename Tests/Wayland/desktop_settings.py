"""Drive the existing Desktops preference view and its real keyboard shortcuts."""
import json
from pathlib import Path
from integration import until


def run(command, query, artifacts, restart=None):
    legacy = [Path.home() / "Library/Preferences/.NextSpace" / name for name in ("WM.plist", "WMState.plist")]
    preceding = {path: path.read_bytes() if path.exists() else None for path in legacy}
    initial = query("--desktop-preferences")
    renamed = query("--desktop-preferences", "name", "Native Desktop")
    assert renamed["names"][initial["current"]] == "Native Desktop"
    count = query("--desktop-preferences", "desktopsNumber", "3")
    assert len(count["names"]) == 3
    changed = query("--desktop-preferences", "switchKey", "0")
    assert changed["shortcuts"]["NextWorkspaceKey"] == "Super+Control+Right"
    changed = query("--desktop-preferences", "directSwitchKey", "2")
    assert changed["shortcuts"]["Desktop1Key"] == "Alt+Control+1"
    if restart:
        restart()
        reloaded = query("--desktop-preferences")
        assert reloaded["names"] == changed["names"] and reloaded["shortcuts"] == changed["shortcuts"]

    def state():
        request = artifacts / "desktop-settings-request.json"
        request.write_text(json.dumps(dict(action="desktop-settings")))
        return query("--display-request", str(request))

    def key(code, modifiers, expected):
        for modifier in modifiers:
            assert command(f"key {modifier} 1")["ok"]
        assert command(f"key {code} 1")["ok"] and command(f"key {code} 0")["ok"]
        for modifier in reversed(modifiers):
            assert command(f"key {modifier} 0")["ok"]

        actual = command("desktops")
        assert actual["current"] == expected, (code, modifiers, actual)
        until(lambda: state()["current"] == expected, "Workspace receives the compositor desktop notification")

    key(2, (29, 56), 0)
    key(106, (29,), 0)  # The previous desktop shortcut must be unbound.
    key(106, (29, 125), 1)
    key(4, (29, 56), 2)
    key(2, (29,), 2)  # The previous direct shortcut must be unbound.
    key(2, (29, 56), 0)

    # Restore the complete pre-test preference value through the same service.
    request = artifacts / "desktop-settings-request.json"
    request.write_text(json.dumps(dict(action="desktop-settings", names=initial["names"], shortcuts=initial["shortcuts"])))
    restored = query("--display-request", str(request))
    assert restored["names"] == initial["names"] and restored["shortcuts"] == initial["shortcuts"]
    assert all((path.read_bytes() if path.exists() else None) == content for path, content in preceding.items()), \
        "Native desktop preferences changed the X11 preference files"
    (artifacts / "desktop-preferences.json").write_text(json.dumps(dict(initial=initial,
        changed=changed, restored=restored), indent=2) + "\n")
