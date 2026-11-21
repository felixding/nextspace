# Toshy keyboard shortcuts in NEXTSPACE

Implement a shared shortcut experience for GTK, KDE and browsers. Ordinary
commands should feel native by default. Use GNUstep's configured Command
modifier, which defaults to Alt (Option on a Mac keyboard), for Copy, Paste,
Find, New Tab (`Alt+T`), Close (`Alt+W`) and Reopen Closed Tab
(`Alt+Shift+T`) where the app supports them. Preserve the app's normal close
behavior, including confirmations and last-tab handling.

## Reuse upstream

- Package a pinned [upstream Toshy release](https://github.com/RedBearAK/Toshy/releases)
  with its bundled `xwaykeyz` revision. Record the source revision and checksum
  in the existing [Debian packaging workflow](../Packaging/Debian/README.md).
  Refresh the pin and checksum together, rebuild, and rerun the same shortcut
  tests. Keep the upstream sources intact and contribute reusable fixes upstream.
- Keep NEXTSPACE-specific settings in Toshy's supported
  [configuration sections](https://github.com/RedBearAK/Toshy/wiki/Toshifying-a-New-Linux-Application),
  with the local settings stored separately from the upstream source. Prove that
  refreshing the upstream config preserves the local settings. Toshy's rules are
  executable Python tied to `xwaykeyz`. Reuse the runtime and rules together.

## Integrate with the native bridge

- Give Toshy the active Wayland application's identity through a supported
  [window context provider](https://github.com/RedBearAK/xwaykeyz#how-it-works).
  The [compositor](../Applications/Compositor/src/main.c) already knows the
  focused surface and its application ID. Check whether the upstream wlroots
  provider fits or needs a small upstream extension. Derive context from the
  real keyboard focus, including modal windows and focus loss.
- Give each shortcut one owner. The existing GNUstep bridge owns native menu
  key equivalents and text editing. Toshy supplies compatibility mappings for
  the app and shortcuts assigned to it. Since `xwaykeyz` remaps keyboard events
  before delivery to the compositor, verify that the supported configuration
  can pass through the keys the bridge owns before enabling it by default.
  Keep the native path available if the mapper exits or loses its focus context.
- Where the bridge owns a shortcut, bind it to the app's existing action and
  show the effective binding in its detached menu. Use stable action IDs where
  available. Allow explicit app overrides in either direction. Preserve
  focused editors, IME input, browser page cancellation and terminal input.

Start in the [GTK and Qt adapters](../Libraries/ForeignScrollers/README.md), the
[shared menu transport](../Libraries/NativeUI/Bridge/Menu.inc), and the
[browser keyboard paths](Browser-Platform-Integration.md). The local toolkit
preview qualified detached menus in Konsole, Kate, Mousepad and Thunar.
The desktop shortcut gate covers Konsole's terminal and Find field and
the editors in Kate and Mousepad.

## Session settings

The GTK and Qt adapters derive Command aliases from each action's registered
primary Control shortcut. The aliases preserve the key and Shift and leave
the original shortcut available. Use Toshy for chords that differ from the
app's registered shortcut.
Command and Alternate Swap in Keyboard Preferences updates the active Wayland
keymap. Both the app shortcuts and Toshy's Command rules follow it immediately.
In focused text editors, GNUstep's Control+A and Control+E move the cursor to
the beginning and end of the line. Command+A selects all text.
If you edit GNUstep's modifier defaults directly, restart GTK and Qt apps to
refresh their shortcut bindings. Qt actions may set `nextspaceOriginalShortcut`
to keep their own binding. Launch an app with `NEXTSPACE_SHORTCUTS=original`
to use its original shortcut handling or `NEXTSPACE_SHORTCUTS=native` to
select the bridge.

The optional Debian mapper runs as the authenticated session user with
`NEXTSPACE_TOSHY=on` and the normal evdev and uinput access for that user.
It uses Toshy's wlroots D-Bus provider through a private compositor
connection. The active application ID clears when keyboard focus is lost.
Without local rules the mapper leaves the native app chords alone.

The graphical review launcher selects upstream Toshy's terminal profile for
Konsole. It uses the profile's same-key modifier aliases so Konsole's registered
actions handle the result. The launcher makes the VM keyboard and uinput
available inside the preview's mount namespace. The original device nodes keep
their existing ownership and permissions throughout the session.

Add app-specific rules to
`${XDG_CONFIG_HOME:-$HOME/.config}/nextspace/toshy/shortcuts.py`.
Use `NEXTSPACE_SHORTCUTS=original` if Toshy is taking over shortcuts the
native bridge would also handle. `Command` in a source chord follows the
current modifier. Specify `Command` in the target as well to use the same
physical modifier. Other modifiers use xwaykeyz syntax.

```python
compatibility_keymap("org.kde.konsole", {"Command-t": "Shift-Command-t"})
```

Use the actual Wayland app ID. Relaunch the session after editing rules.
The config is regenerated from the pinned upstream template on startup.
Local rules are loaded from their existing file.

## Acceptance

- In Konsole, a tabbed GTK app, Firefox and Chromium, test New Tab, Close and
  Reopen where offered, plus Find, Copy and Paste. Verify the same action by
  keyboard and menu, exactly one action per press, and correct ownership as
  focus moves among windows, editors, dialogs, and browser pages.
- In Konsole, verify Copy with and without a selection, paste, and plain
  `Ctrl+C` interrupt. Copy with no selection must send neither an interrupt nor
  stray input to the shell. [Toshy's Konsole workaround](https://github.com/RedBearAK/Toshy/blob/main/default-toshy-config/toshy_config.py#L4911-L4955)
  documents why this matters. Verify an app override and a non-default GNUstep
  Command key. Verify that a page which cancels a shortcut keeps its existing
  browser behavior.
- Personally test the packaged preview in the local VM through the ordinary
  graphical launcher before handoff. Follow [AGENTS.md](../AGENTS.md) and the
  [preview workflow](MacBook-Preview.md). Preserve the browser regression gate,
  update the existing archive and SHA-256 sidecar after qualification, and keep
  the user command `bash ~/Downloads/Review.command`.
