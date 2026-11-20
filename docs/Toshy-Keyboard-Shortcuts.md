# Toshy keyboard shortcuts in NEXTSPACE

Implement a shared shortcut experience for GTK, KDE and browsers. Ordinary
commands should feel native by default. Use the physical Command key configured
in GNUstep for Copy, Paste, Find, New Tab (`Command+T`), Close (`Command+W`) and
Reopen Closed Tab (`Command+Shift+T`) where the app supports them. Preserve the
app's normal close behavior, including confirmations and last-tab handling.

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
preview qualified detached menus in Konsole, Kate, Mousepad and Thunar. The
Konsole editing check covered its Find field. Terminal-pane shortcuts and
Toshy coexistence still need qualification.

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
