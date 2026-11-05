# Firefox native UI integration

This is the Gecko side of the browser-first
[native application integration](../../docs/Native-Control-Integration.md).
The goal includes complete browser interfaces and other non-GNUstep apps.

The first optional binding renders determinate HTML progress indicators through
actual GNUstep `NSProgressIndicator` objects in the existing NativeUI provider.
Gecko supplies its validated `HTMLProgressElement::Position()` and device-pixel
rectangle. Its existing display-item fallback supplies the DrawTarget. The
adapter transports the native pixels through that API and releases each native
object after the snapshot. It has no progress artwork, geometry or animation
implementation. Browser model changes and read-only clicks retain their engine
paths. The underlying UI library and provider were unchanged.

Chromium and Firefox now share the C transport, wire declarations and audited
ARM64 detour machinery in [`Libraries/NativeUI/Bridge`](../../Libraries/NativeUI/Bridge).
Firefox uses the existing helper and NativeUI provider rather than another
control service implementation. Engine model and frontend bindings remain
separate from the underlying UI library.

Only the unchanged Debian ARM64 Firefox ESR binary in
[`binary-pin.json`](binary-pin.json) is accepted. The launcher checks executable
and libxul hashes; the adapter checks the ELF build ID, instruction bytes and
vtable entries before modifying process memory. [`source-audit.json`](source-audit.json)
records the matching sources, debug archive and interfaces. Firefox and AppKit
are never recompiled. No package was installed, and the package inventory is
unchanged. GTK3 runtime libraries were extracted into the private test root.

The current qualification is deliberately limited: determinate progress at
100% scale, using the ordinary horizontal test fixture. Other scales retain
Gecko's rendering until scaled native transport is connected. Indeterminate
animation, RTL/vertical progress, other controls, menus, editing, IME,
accessibility, browser application interfaces and derivatives remain open.
Author-styled controls retain their engine path. This is not full native
Firefox support and is not activated outside the private test session.

## Reproduce the private fixture

Build only the optional adapter on Linux ARM64:

```sh
python3 Experiments/FirefoxNativeUI/build.py --output /var/tmp/firefox-native-hook.so
```

Use an existing working GNUstep Wayland backend and the shared native provider.
For the recorded private guest, the command was:

```sh
python3 Experiments/FirefoxNativeUI/run-fixture.py \
  --firefox /var/tmp/nextspace-firefox-prototype/root/usr/lib/firefox-esr/firefox-esr \
  --native-library /var/tmp/nextspace-native-ui/bridge-build/libnextspace-native-scroller.so.1 \
  --hook /var/tmp/nextspace-firefox-prototype/native-hook.so \
  --backend nextspace-native-ui-test \
  --library-path /var/tmp/nextspace-firefox-prototype/root/usr/lib/aarch64-linux-gnu \
  --library-path /var/tmp/nextspace-chromium-prototype/root/usr/lib/aarch64-linux-gnu \
  --output /var/tmp/nextspace-firefox-prototype/final
```

The runner owns a private compositor, temporary Firefox profile, native helper
and Marionette port. It generates independent reference images through the
public native C API, runs 21 browser checks, verifies renderer sandbox status
and checks balanced native object lifetime. It also kills its helper and checks
that the existing browser model and ordinary button action remain usable.
It stops its processes and removes the temporary profile in `finally`.
`marionette.py` implements only the standard sequential protocol for this owned
fixture; agent-browser currently supports Chromium/CDP, so it cannot drive this
Firefox test.

The recorded run passed all 21 checks and released all 45 native objects.
The unchanged provider/loader hashes, native pixel comparisons, sandbox state,
helper-loss result and 261 passing Chromium regressions after the shared-code
extraction are recorded in [`progress-qualification.json`](progress-qualification.json).
Raw screenshots, native traces and results are under
`.build/firefox-native-ui/qualified-final/` and
`.build/firefox-native-ui/chromium-regressions/`.
