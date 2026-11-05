# Shared native UI provider

The goal is to make whole non-GNUstep applications look and behave native in
NEXTSPACE, including GTK, Qt/KDE and browser applications. Scrollbars are the
starting integration, not the acceptance criterion. Controls, detached menus,
editing, focus, shortcuts and dialogs must use the shared native UI library.
See the [application-wide scope and coverage](../../docs/Native-Control-Integration.md).

The bridge and the underlying UI implementation are separate libraries:

- `libnextspace-native-ui.so.1` loads a provider and forwards the C API. It has no
  GNUstep, GTK or Qt dependency and implements no controls.
- `libnextspace-native-ui-gnustep.so.1` binds that API to the installed GNUstep
  controls. It creates ordinary `NSButton`, `NSSlider`, `NSProgressIndicator` and
  `NSScroller` objects and calls their drawing and input methods. The shared
  view host supplies offscreen backing and event dispatch, with no control
  drawing, geometry or tracking algorithms.
- `libnextspace-native-scroller.so.1` preserves the existing scrollbar ABI as a
  C forwarding shim, so its GTK/Qt consumers keep their existing interface.

Appearance and interaction live in the underlying AppKit library and theme.
Changing them there affects all controls using this provider. Consumers do not
carry copies of the controls or artwork. Replacing the underlying UI framework
requires a provider implementing the same C ABI, selected before the first call
with `NEXTSPACE_NATIVE_UI_PROVIDER=/path/to/provider.so`. The provider is loaded
once per process and remains loaded for the lifetime of its native objects.
The C loader rejects an absent, incompatible or incomplete provider. Its error
is available through `nxs_native_ui_error()`; it does not emulate a control.

The API supports native push buttons, checkboxes, radio buttons, sliders,
progress indicators, popup buttons/menus and the existing scrollbar contract. Normal/disabled state,
model updates, native preferred metrics, bitmap output and synchronous mouse
tracking are exposed. The application owns its data model; the native control
owns its actual input loop. The event pump services application/transport events
while that loop runs. Call these APIs on the owning UI thread. Bitmap pixels
are borrowed until that control is drawn, receives input, or is destroyed.
Action-state data is borrowed for the callback. Config/title data is read during synchronization
and retained by the native library as needed. Coordinates are logical units from
the top-left of the returned bitmap; the provider handles its UI library's native
coordinate system. `control_destroy` returns zero during active native
tracking; forward release, allow tracking to return, then destroy the control.

The optional input extension exposes first-responder focus and keyboard events
for the button, checkbox, radio and slider controls. Query
`nxs_control_input_capabilities()` before using it. `nxs_control_focus` asks the
native window/control to accept or resign focus; `nxs_control_focused` reads that
native state. The provider draws its own focus ring. It does not replace one
with bridge artwork.

`nxs_control_key` translates the public logical key/UTF-8 data into a native
event and calls the actual responder with `NSApp.currentEvent` set. The native
control defines activation, slider movement and key bindings. Unhandled events
return `NXS_INPUT_UNHANDLED`. The native window's next/previous focus requests
return `NXS_INPUT_NEXT` or `NXS_INPUT_PREVIOUS`; the application supplies its
focus order and applies that request to its own model. No native key-binding or
slider-step algorithm is copied into this API. Physical modifier translation
uses the same UI-library preferences as mouse tracking.
Unhandled input goes back to application command routing, while the native
provider continues to own the widget's keyboard behavior.

Keyboard dispatch also owns the native control's stack while its action callback
runs. `tracking` reports this busy state, and destruction returns zero until
dispatch returns. Keyboard input to an unfocused/disabled control, or during
another native input dispatch, is rejected. Text and IME editing, default-button
command models, key equivalents, offscreen keyboard activation animation and
application focus traversal still need their broader integration contracts.
The pinned Chromium experiment now applies next/previous requests through its
real focus controller; other application integrations remain open.

The optional input, event, range, popup and descriptor-source functions extend ABI version 1. The loader validates
the original `NXS_NATIVE_UI_CORE_SIZE` prefix and checks the advertised structure
size before reading optional fields. Older providers keep their original
controls and report no input capabilities. An older loader/client can also use
the new provider unchanged. This preserves the separation while the API grows.

This is an initial implementation of the shared host, not full browser support.
Text editing, broader engine/frontend focus and keyboard routing, IME, accessibility,
general application menus, lists/trees, tabs,
and engine/frontend adapters for the new control types remain to implement.
The provider ABI is under development until that broader contract is qualified.

## Build and checks

Build the provider alone using the installed NEXTSPACE SDK:

```sh
cmake -S Libraries/NativeUI -B /tmp/native-ui -DCMAKE_OBJC_COMPILER=clang
cmake --build /tmp/native-ui -j2
```

Build the provider plus the existing C scrollbar bridge without GTK/Qt build
dependencies:

```sh
cmake -S Libraries/ForeignScrollers -B /tmp/native-ui-bridge \
  -DCMAKE_OBJC_COMPILER=clang -DNEXTSPACE_BUILD_TOOLKIT_ADAPTERS=OFF
cmake --build /tmp/native-ui-bridge -j2
python3 Tests/NativeUI/run.py --build /tmp/native-ui-bridge \
  --output /tmp/native-ui-results
```

The probe invokes real native mouse tracking and checks actions, checked states,
slider changes, disabled and cancelled gestures, rejected invalid updates and
safe deferred destruction. It also checks that private backing windows never
map, that the C loader has no UI toolkit dependency, that provider internals are
not exported, and that selecting a relay provider preserves the same native
behavior in the unchanged test client. An incompatible provider ABI is rejected.

The input probe additionally checks native Space actions, slider arrow/Home/End
actions, focus transfer, actual focus-ring image changes, next/previous focus
requests, disabled/unfocused input and safe destruction during keyboard
callbacks. `--previous-provider`, `--previous-client` and `--previous-loader`
can verify both directions of the optional-extension compatibility contract using
saved pre-extension binaries. These checks passed on the same private ARM64
setup, including 30 unchanged scrollbar comparisons. The helper transport also
passes native focus/key round trips for all four types. The existing Chromium
mouse fixture still passes 33 checks and its native action trace; eight scrollbar
pixel checks pass. See `input-qualification.json` and `.build/native-ui/input-*`.
The later optional Chromium focus/keyboard binding passes 62 browser assertions
and independent native-action traces using this unchanged provider. Its narrower
browser qualification and remaining gaps are recorded separately in
[`Experiments/ChromiumScrollers/input-qualification.json`](../../Experiments/ChromiumScrollers/input-qualification.json).
The provider's existing determinate `NSProgressIndicator` is also connected to
that pinned browser's HTML progress model. This required no provider or UI-library
change; its pixels and resize/model behavior pass 20 browser checks. That partial
binding, its unresolved early initial-frame fallback and the remaining native
animation work are recorded in
[`progress-qualification.json`](../../Experiments/ChromiumScrollers/progress-qualification.json).

`--baseline DIRECTORY` adds byte-for-byte comparisons against the prior
`libnextspace-native-scroller.so.1`, using the same executable and both scrollbar
orientations, three range states, and 100%, 125%, 150%, 175%, and 200% scale.
`--backend NAME` optionally selects an existing GNUstep backend for the test
processes alone.

The first local run on Debian 13 ARM64/native106 passed the five control probes,
legacy native tracking, provider isolation/selection and all 30 scrollbar pixel
comparisons. Evidence is in `.build/native-ui/`. The unchanged pinned Chromium binary also passed eight native bitmap checks at
its usual width and eight more after changing only GNUstep's own
`GSScrollerDefaultWidth` setting from 18 to 22. Its layout reported width 22 and
its native arrow still moved by 40, with no browser or bridge rebuild between
the two UI settings. The Chromium shim now queries the provider's width instead
of supplying a fixed width. Staged-library controls and tracking checks passed.
Full GTK/Qt package regression and the broader browser/control qualification
remain required before activation outside the private test environment.

A later repeat run timed out after a legacy probe wrote its bitmap. The next
complete run passed; the timeout's cause remains unconfirmed. The later slider
verification below distinguishes waiting for captured output from waiting for
the probe to exit and retains backtrace capture on exit timeouts.

## Native events and animation

The optional event extension exposes `nxs_native_ui_event_capabilities()`,
`nxs_native_ui_dispatch_events(maximum_wait)` and
`nxs_control_needs_display(control)`. Service events on the owning UI thread;
zero wait is nonblocking. The returned delay comes from the native run loop's
next deadline, with `-1` for no deadline. It is not a bridge animation period.
The repaint flag is the native view's own state and clears when the provider
draws the control. Older providers advertise no event capabilities; older
loaders/clients retain their original methods unchanged.

Indeterminate progress configuration now calls the actual
`NSProgressIndicator.startAnimation:`/`stopAnimation:` methods. Its existing
timer, frame selection, artwork and timing remain in AppKit. Destroying an
animated control stops that timer before releasing its last view reference.
The shared host services the native run-loop mode, including the tracking mode
while a native tracking loop owns input. No widget interval or animation counter
was added to the provider or consumers.

The native probe observes changing images and repaint flags, stable determinate
mode, restart and safe active-timer destruction, with no mapped backing window.
Thirty old scrollbar images and both directions of client/provider compatibility
still pass. The Chromium helper services these deadlines, exposes per-process
invalidation generations and passes idle animation, process-isolation and
lifecycle checks. The optional pinned browser binding passes 59 animation
assertions, including 48 complete images against native references. Its renderer
thread applies native invalidations through the engine's existing scheduling
API. See [`animation-qualification.json`](animation-qualification.json).

This covers progress animation in the qualified setup. Offscreen native keyboard
activation animation, other widgets' animation/invalidation contracts and the
broader engine/frontend matrix remain open.

## Native slider data

The optional `nxs_control_range_capabilities()` / `nxs_control_set_step()`
extension adds the application's data quantum without replacing native input
rules. Zero means continuous. The provider configures `NSSlider`'s existing tick
marks and tick-only values for domains with 2–64 discrete values; denser domains
retain its continuous presentation. AppKit still draws the ticks/knob and
interprets every mouse/key event. The application validates and serializes the
returned number using its own data model. There is no second snapping, drawing
or keyboard implementation in the bridge.

The extension is appended after the event methods (ABI 1, 200 bytes on ARM64).
Older providers advertise no range capability. The direct range probe checks
coarse native keys, dense continuous input, range changes and invalid arguments;
the old provider/client compatibility checks and 30 scrollbar comparisons pass.
`--previous-range-provider` verifies a saved provider predating this extension.
The pinned Chromium slider binding and its narrower qualification are recorded
in [`slider-qualification.json`](../../Experiments/ChromiumScrollers/slider-qualification.json).

Three earlier verification attempts timed out while collecting probe output.
One diagnostic found the target already terminated; that evidence does not
establish a live control deadlock. The harness now waits for the probe's actual
exit independently of inherited output descriptors, and captures a backtrace
on an actual exit timeout. The subsequent complete run passed. The original
timeouts' exact cause remains unconfirmed.

## Native popup menus and event sources

`NXS_POPUP` hosts an actual `NSPopUpButton` and `NSMenu`. Query
`nxs_control_popup_capabilities()` before supplying ordered UTF-8 item labels,
enabled/separator flags and a selected array index with
`nxs_control_popup_items()`. Duplicate labels retain distinct indices. The
provider constructs ordinary menu items and uses the popup's public `setMenu:`
and selection methods. Native menu ownership supplies selection and action
dispatch. The callback reports `NXS_VALUE_CHANGED` with the native selected
index. No private popup selectors or widget implementations are copied.

`nxs_control_popup_state()` and `nxs_control_popup_item_rect()` read native
visibility, highlight and geometry in control bitmap coordinates; rectangles
can extend outside the control. The optional origin request sets the hidden
host's native layout position relative to the main screen. Placement remains
subject to the backend and compositor. Owned menu windows read the embedding
pointer stream during synthetic tracking, while retaining their actual native
layout, hit testing, rendering and tracking. The menu windows are real native
windows; control backing windows remain hidden.

Model replacement and destruction are rejected while native input owns the
object. Destruction after dispatch closes an open menu. Invalid model data is
rejected before replacing the model. The optional descriptor-source API
registers caller-owned readable descriptors with the native run loop. It wakes
event dispatch without reading or closing the descriptors; remove sources on
their UI thread before closing the descriptors. The host services native window
and input events while idle and leaves active native tracking in charge of its
queue. The helper can wait on native window events and IPC without a widget
polling interval.

The popup and descriptor fields extend ABI 1 from 200 to 248 bytes on ARM64.
Explicit `nxs_control_popup_open(control, open)` appends another method, making
the current table 256 bytes. Query `nxs_control_popup_open_capabilities()` first.
The provider uses `NSPopUpButtonCell`'s public attach/dismiss methods, so an
application's show/hide request does not assume a keyboard binding. Unfocused
opening, repeated open/close, disabled/empty rejection and native closure pass
direct checks and helper round trips. Older providers advertise no unavailable
capabilities; old loaders/clients work unchanged. `--previous-popup-provider`
checks a pre-popup provider; `--previous-popup-open-provider` checks the 248-byte
popup provider without explicit visibility methods.
`Tests/NativeUI/run.py --transport` runs the existing mouse, focus, keyboard and
animation transport checks plus 20 popup checks. They cover complete
normal/focused images against direct native references, native menu mapping
without further RPCs, keys and mouse selection, disabled items/controls,
duplicate labels, cancellation, isolation, invalid models and destruction.
The helper used zero CPU time during the test's 200 ms idle-menu sample;
broader performance remains unqualified.

The view host now defers backend creation for its private backing window. This
keeps NSWindow's geometry synchronous while it remains unmapped, fixing the
stale origin that placed native menus at the compositor's origin. Synchronizing
an unchanged selection also leaves live native highlight/selection intact, and
model replacement restores the configured enabled state through native methods.
These checks and the 30 legacy scrollbar image comparisons pass.

An optional pinned Chromium adapter now binds classic HTML selects to this
contract. Its 29 fixture checks and 232 existing browser checks pass. Default
disabled CSS opacity, live model changes, browser window parenting/coordinates
across movement, outputs/scales and frontend menus remain unfinished; this is
partial browser coverage. One provider run timed out loading a progress image
in AppKit's resource lookup; the saved backtrace establishes that location, not
the underlying cause. A later complete compatibility/transport run passed.
See the original [`popup-qualification.json`](popup-qualification.json) and the
new [select qualification](../../Experiments/ChromiumScrollers/popup-qualification.json).

The browser helper now prepares its actual native controls before publishing
the service socket, so initial AppKit image/font loading happens before paint
RPCs. Its optional invalidation transport wakes renderer-owned descriptors
instead of polling; this uses the existing native view/action state and source
API without changing the public NativeUI ABI or control implementations.
Active subscriber lifetime is tracked using kernel credentials and pidfds.
The separate [notification qualification](../../Experiments/ChromiumScrollers/notification-qualification.json)
records native-window delivery, resource preparation and cleanup checks.


The first optional Firefox/Gecko binding now reuses this unchanged provider for
determinate HTML progress. Chromium and Firefox share the internal transport
and ARM64 hook support in [`Bridge`](Bridge); neither adapter implements a
native control. See the [Firefox experiment](../../Experiments/FirefoxNativeUI)
for its exact binary pin, 21 passing checks, remaining controls/frontend work
and the 261 Chromium regressions after extraction. Generic-control scaled
transport and broader Firefox integration remain open.


The optional Gecko checkbox/radio binding now also uses the existing `NSButton`
provider for preferred metrics, focus, tracking and key interpretation. Forty
browser checks and fifteen independent native images cover that partial input
binding, with actual engine actions and frame/page/process lifetime cleanup.
This adds no UI-library or provider implementation; the underlying native
binaries retain their earlier hashes. See the
[Gecko input qualification](../../Experiments/FirefoxNativeUI/input-qualification.json)
for the remaining radio-group, scale and full-browser integration work.
