# Firefox native UI integration

This is the Gecko side of the browser-first
[native application integration](../../docs/Native-Control-Integration.md).
The goal includes complete browser interfaces and other non-GNUstep apps.

The optional progress binding renders determinate HTML progress indicators through
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

The first interactive binding adds actual native checkbox and radio controls.
The provider supplies distinct preferred sizes, drawing, first-responder focus,
mouse tracking and key interpretation. Gecko retains its real click dispatch,
trusted input/change events, cancellation, radio-group data model and document
focus order. Native activation gates the engine action; no tracking or widget
key rules are copied. Controls can bind before the first paint. Focus handlers
may replace frames, so the bridge retains the semantic node across original
dispatch and then obtains its live frame.

Frame destruction, page freezing and inactive tabs release the native bindings.
Restored cached pages rebind to new native objects without disabling the
back/forward cache. The existing helper's descriptor registration and kernel
process watch also release controls when their renderer crashes, even while a
parent process retains the shared request socket. The helper now logs generic
control destruction as well as progress/popup destruction.

Qualification remains limited to this exact ARM64 build and scale 1 horizontal
fixtures. Other scales retain Gecko's rendering until scaled native transport
is connected. Native radio-group arrow navigation is still open: the provider
currently hosts individual radio buttons rather than a native group container.
The tested radio-group data changes use real engine mouse/Space activation.
Indeterminate animation, remaining controls, menus, editing, IME, accessibility,
browser application interfaces and derivatives remain open.
The progress fixture retains its author-styled engine path; broader styled
interactive controls remain unqualified. This is not full native Firefox support
and is not activated outside the private test session.

The optional range binding (`NEXTSPACE_FIREFOX_SLIDERS=1` with
`NEXTSPACE_FIREFOX_INPUT=1`) uses the same provider's actual `NSSlider`. Gecko's
real minimum, maximum, value and step accessors supply application data. Native
mouse tracking and logical-key interpretation supply values; Gecko's real
setter retains serialization, validation and trusted input/change events.
The adapter keeps the original range drag lifecycle for capture, focus
bookkeeping, blur and cancellation. It replaces that lifecycle's point-to-value
result with the native slider result, rather than copying track/knob geometry.
Keyboard actions use the same actual engine setter. Effective appearance and
author-style eligibility use the engine's own methods.

Run `--sliders` for independent whole native images and key results, including
horizontal/vertical, disabled, discrete, continuous and locked models. The
fixture passes 57 checks, including 16 full native-image comparisons. It checks
continuous input before pointer release, trusted change on
commit, cancellation, frame replacement, removal and style changes during
tracking, cache/tab restoration, renderer death and helper loss. Native keyboard
expectations come from the provider; its normal ArrowRight step differs from
Gecko's old widget step. The adapter defines no replacement key bindings.

Only fixed integer sizes at scale 1 are qualified for the tested range models.
Automatic range sizing, noncanonical aspect ratios, transformed/scaled output,
nonzero step bases and broader discrete-step/end-point combinations remain
open. Datalist tick labels, touch/wheel input, accessibility and full browser
interfaces also remain open. Unsupported style/orientation changes release
native ownership and retain the whole engine fallback. No UI library, provider,
loader or Firefox rebuild is needed. See
[`range-source-audit.json`](range-source-audit.json) and
[`range-qualification.json`](range-qualification.json) for the precise evidence.
The 54 input-button, 40 checkbox/radio and 21 progress checks also pass with
slider hooks enabled. Installed packages and native loader/provider hashes
remain unchanged.

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
Add `--controls` to that command and use the newly built hook to run the optional
checkbox/radio fixture; it enables `NEXTSPACE_FIREFOX_INPUT=1` for that owned
Firefox only. The control run adds 40 checks, 15 independent native image
comparisons, actual back/forward-cache and tab restoration, renderer-crash
cleanup and mouse/key behavior after helper loss. It rejects an occupied test
port and verifies each Marionette session belongs to the owned Firefox PID.
Sessions are explicitly deleted before another client attaches.
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


The interactive binding's matching source/ABI audit is recorded in
[`input-source-audit.json`](input-source-audit.json); its runtime evidence and
remaining gaps are in [`input-qualification.json`](input-qualification.json).
The final control run created 107 native objects: 101 had explicit destruction
records (including six released after renderer death), and the remaining six
were reclaimed with the intentionally killed helper process. The native loader,
provider and installed package inventory remained unchanged.

The optional input-button binding (`NEXTSPACE_FIREFOX_BUTTONS=1`, together with
`NEXTSPACE_FIREFOX_INPUT=1`) connects `<input type=button|submit|reset>` to the
same existing `NSButton` provider. Gecko's actual `GetLabel` supplies the title,
including localized defaults. The native control draws the complete bezel and
title. Display-list interception suppresses only that input frame's anonymous
label after a complete native snapshot is available. A failed preparation
restores the whole engine control; changing to unsupported styling or fractional
dimensions releases native ownership. The bridge contains no button artwork,
title layout or tracking/key rules. Native actions retain Gecko's real trusted
click, submission, reset and cancellation paths.

Use `--buttons` instead of `--controls` to reproduce this fixture. It passes 54
checks, including 33 complete native-image comparisons, dynamic Unicode titles,
resizing, held-pointer cancellation, form semantics, style/size fallback,
focus-handler replacement, actual cached-page and tab restoration. The runner
also verifies renderer-crash cleanup and mouse/key actions after helper loss.
It records renderer sandbox status while processes are live, since navigation
can retire a renderer before the final census. All 40 checkbox/radio and 21
progress checks pass with the button hooks enabled.

Native preferred/intrinsic sizing now uses the actual button cell's measured
size through the existing C API. Gecko retains its shrink-to-fit, box sizing and
constraint pipeline; the bridge supplies native metrics at its existing
intrinsic/auto-size boundaries. Tests cover automatic sizes for normal,
disabled, localized default, Unicode and empty titles, title changes, native
font metrics, basic flex/grid, min/max-content and explicit min/max constraints.
The reference generator independently asks the native provider for its preferred
size; its 34 previous fixed-size images remain byte-for-byte identical.

Measurement can precede first reflow. A measurement-only binding does not own
input until a complete native image is prepared at the live frame size. The
mouse/key entry path also prepares this image before a first paint. The initial
sizing run exposed and corrected that handoff in the held-pointer test.

This qualification uses horizontal scale 1 in the pinned ARM64 binary.
Default-button policy, rich-content HTML `<button>`, scaled/vertical output,
broader CSS/layout combinations and browser application interfaces
remain open. The actual UI library, loader and provider are unchanged. See
[`button-source-audit.json`](button-source-audit.json) and
[`button-qualification.json`](button-qualification.json) for the exact boundaries
and evidence. This is another partial engine binding, not native browser-wide
support.


The optional plain/password text binding (`NEXTSPACE_FIREFOX_TEXT=1` with
`NEXTSPACE_FIREFOX_INPUT=1`) uses actual `NSTextField`/`NSSecureTextField` field
editors. Those editors render the complete contents, selection, caret and bezel,
and interpret logical keys. A complete prepared snapshot replaces the engine's
anonymous editor display. Native pre-edit ranges/selectors call Gecko's actual
insertion/deletion transactions, preserving trusted `beforeinput`/`input`,
cancellation, maximum length, script mutation and engine undo. The native
proposal is vetoed after the engine action, then its canonical result is echoed
back; the bridge contains no editing algorithm or copied key-binding table.

Use `--text` for the owned fixture. Its independent native references include
complete normal/selected images and actual native key/Return results. Checks
cover Emacs navigation/deletion, password/readonly/disabled fields, UTF-16
selection, programmatic values, resize, form Return, Tab, engine undo, cancelled
keydown/beforeinput, reentrant value changes/frame removal, cache restoration,
caret invalidation, renderer death and helper-loss recovery. A one-line provider
fix avoids reapplying unchanged `setEditable`, which restarted the native caret;
AppKit still supplies the timer and rendering. The existing eventfd subscription
wakes the engine UI loop through GLib. No browser or underlying AppKit rebuild
is required. See [text source audit](text-source-audit.json) and
[text qualification](text-qualification.json).

This is an opt-in fixed integer-size, scale-1 binding for one exact binary.
Clipboard command/web-event integration, native
undo-menu routing, IME/composition, other text types, intrinsic sizing,
multiline/rich text, accessibility and broader styling remain open. Address
bars and other browser application interfaces remain separate work. A native
field editor does not automatically provide all application behaviors.

Single clicks, Shift-click extension and forward/reverse selection drags now
use the same native editor's actual mouse tracking. Gecko keeps DOM events,
focus handlers, pointer capture and click dispatch; its frame selection geometry
is suppressed only after a native field is prepared. Native selection changes
return through the existing descriptor wakeup. A read-only snapshot query
refreshes pixels during tracking without rebinding the busy editor. Model,
style, size or focus changes cancel tracking before canonical rebinding.
Independent native pointer ranges and selected images cover plain/password,
readonly and Unicode models, including drags outside the field. Double/triple
click counts, dragging selected text as data, context menus, touch and long-field
horizontal scrolling remain open. This extension changes the adapter/helper;
the qualified native provider and AppKit binaries are reused unchanged.
The [pointer qualification](text-pointer-qualification.json) records 151 browser
checks, including 50 native pointer ranges and 46 complete native images.
