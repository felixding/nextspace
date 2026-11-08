# Chromium native scrollbar experiment

Current scope (2026-11-07): keep the browser's own tabs, address bar and toolbar.
Native browser-UI replacement is skipped. The shared default scope policy
ignores the earlier frontend/tab opt-in flags; related qualification below is
historical evidence. Continue webpage controls, then shared detached-menu and
native-shortcut integration, followed by GTK and Qt/KDE apps. Future toolbar or
other browser-UI changes belong to optional app-specific patches above the
shared bridge/provider layer.


This opt-in prototype replaces web-content scrollbars in **one unchanged Debian
ARM64 Chromium build** with the existing NEXTSPACE `NSScroller` bridge. Only the
small preload library is compiled for the browser binding. Chromium and AppKit
are not rebuilt or overwritten. The native wheel qualification also builds a
private Wayland input backend with corrected axis normalization. Closing the isolated browser removes the memory patches.
It is not enabled by the installed NEXTSPACE session.

The active browser's real application-menu model is also re-projected after a
native-host epoch change. The existing invalidation work loop schedules this on
Chromium's own UI task queue before another key is required; commands are never
replayed. `Tests/Wayland/native_ui_desktop_chromium.py` checks app switching,
same-process host recovery, native New Tab once before/after recovery and complete
menu pixels captured from the full Workspace desktop. Browser tabs, address bar
and toolbar remain original; remaining controls and shortcuts still need work.

`NEXTSPACE_CHROMIUM_RADIO_GROUPS=1`, together with the existing forms/input flags
and a current shared provider, binds radio groups to actual native matrices.
Original Blink group traversal and DOM node IDs supply membership and identity;
original focus and trusted activation retain page events and cancellation. A
shared model/state cache and serializer live in `Libraries/NativeUI/Bridge` for
reuse by other engines and toolkits. NativeUI supplies all cell sizing, geometry,
pixels, navigation and tracking. Each live group owns one matrix; individual
members do not create a second set of native radio buttons.

This opt-in binding currently models groups as one native column. Complete
pointer/label behavior, CSS visibility and layout variants, scaling, host
replacement, derivatives and installed deployment remain open. See the
[group qualification](radio-group-qualification.json) for measured coverage.

## Native multiline viewport experiment

For the exact browser pin below, `NEXTSPACE_CHROMIUM_MULTILINE_VIEWPORT=1`
adds native textarea viewport integration to the existing
`NEXTSPACE_CHROMIUM_FORMS=1`, `NEXTSPACE_CHROMIUM_INPUT=1`,
`NEXTSPACE_CHROMIUM_TEXT=1` and `NEXTSPACE_CHROMIUM_MULTILINE=1` bindings.
It requires a provider advertising `NXS_TEXT_VIEWPORT` and `NXS_TEXT_GEOMETRY`.
This is opt-in and is not installed as the desktop default.

The real `NSScrollView`/`NSTextView` supplies clip/document dimensions, clamped
scroll points, wrapping, pixels and arrow tracking. The adapter feeds those
measurements into Blink's existing scroll area and padding-box geometry, keeping
its DOM rounding/zoom conversion and scroll-event lifecycle. Blink's separate
scrollbars and corner resize grip are disabled for owned native textareas;
CSS/script can still resize their enclosing boxes. No grip or scroller is copied
into the adapter. Paint ownership distinguishes border-box rendering from
Blink's second scrolling-background pass, and scrolling invalidates the complete
native snapshot rather than relying on translation of hidden browser text.

Verified on the unchanged pinned ARM64 binary at 100% scale: 34 viewport checks
before/after host replacement, including 12 complete image comparisons, native
client/scroll geometry, trusted scroll events, script resizing, native wrapping,
autohiding, and native arrow click/repeat/release. Both browser families retain
their 18 real-seat multiline editing checks. See
[multiline-viewport-qualification.json](../../Libraries/NativeUI/multiline-viewport-qualification.json).
Pointer autoscroll, selection dragging, nowrap and
horizontal modes, accessibility and CSS zoom/HiDPI remain unfinished.
The pinned Firefox now also has a qualified native viewport binding. Other Chromium builds and derivatives remain
unsupported until their own audited adapters are available.

## Native textarea wheel experiment

`NEXTSPACE_CHROMIUM_WHEEL=1` additionally requires the native viewport binding,
the provider's optional wheel capability and the exact instruction guards in
`pinned-wheel.h`. Blink's existing event-handler registry marks the native
widget's wheel region, including pages without JavaScript wheel listeners.
Original targeting, trusted DOM dispatch and cancellation run first. An
uncancelled event reaches the real GNUstep responder's `scrollWheel:` method;
its native offset returns through Blink's existing scroll setter. There is no
second engine default and no copied line/page/modifier/clamping implementation.

On UI-host replacement, the adapter restores the retained engine viewport into
the recreated native object once per host generation. It does not replay wheel
actions. A failed viewport read cannot overwrite the live engine model with a
cached value from the previous host.

The Wayland backend now groups axes per pointer frame, handles discrete and
high-resolution value120 wheel steps, and translates positive-down Wayland Y
to native NSEvent Y. An independent ordinary GNUstep window and the browser
receive identical real-seat full/fractional steps. See the
[wheel qualification](../../Libraries/NativeUI/wheel-qualification.json) for
native pixels, cancellation, DOM mutation/lifetime and host recovery evidence.
These checks cover wrapped textareas on the pinned software/headless build at
100% scale. Root-document wheel behavior, touch momentum, horizontal/nowrap
modes and other browser builds remain open. The pinned Firefox also has a
[native wheel binding](../FirefoxNativeUI/wheel-qualification.json).

## Native textarea caret viewport

Native key handling now returns the `NSTextView` viewport through Blink's real
scroll setter after canonical model synchronization. Layout/paint callbacks
inside the native pre-edit decision retain the busy editor's geometry/image;
they do not rebind it. The shared provider finishes native caret reveal after a
changed external edit model, using the existing native method. The bridge adds
no caret, wrap, selection-layout or scroll algorithm and needs no new API.

Pointer conversion also keeps engine coordinate spaces consistent: the original
`ConvertFromRootFrame` supplies a point in the same frame space as the element
client quads. Adding document scroll there would displace native input on a
scrolled page. Exact call guards are in `pinned-coordinates.h`; the viewport
regression compares a scrolled-page native click, pixels and trusted events with
the same ordinary native reference.

See the shared [caret qualification](../../Libraries/NativeUI/caret-qualification.json)
for actual-seat long-document navigation, forward/backward selection, wrapping,
insertion/cancellation, complete native images, rapid input and host replacement.
Pointer autoscroll, ancestor-page reveal, richer edits/async clipboard commands,
selection-direction metadata, IME/accessibility and other scales/builds remain
unfinished.

The helper calls the unchanged `Libraries/ForeignScrollers` C interface for
geometry, drawing and synchronous native mouse tracking. Its bitmap is transported
to Chromium's paint canvas; no native artwork or tracking algorithm is copied.
Outside the native textarea experiment, Blink retains document layout and scroll ranges, with vertical bars placed
on the left without changing text direction. Native actions are applied through
Chromium's absolute scroll-offset setter on the owning renderer thread.

The preload patches guarded ARM64 instructions and internal vtables before the
renderer sandbox starts. A preconnected socket survives the zygote boundary;
AppKit stays in the separate helper. Chromium's compositor scrollbar press
handler returns its own unhandled result so the press reaches Blink and
`NSScroller` without starting a second compositor scrollbar animation. Wheel and
content handlers outside the optional native textarea binding are not replaced. Native tracking stops when Blink disconnects
a scrollbar, including reload during a held arrow.

## Exact supported binary

- Debian package: `chromium 156.0.8078.79-1~deb13u1`, ARM64.
- Executable SHA-256:
  `7bcc9f719bc77d34358194026b4f148a468e97e4ddc45366e6ce02c119fb9bd1`.
- GNU build ID: `eeeef03b83096958e9eb6385a4a92aa8d2aa404e`.
- Upstream commit: `a21ce95c24ce3964416f09ae1862f53f319eb4d0`.
- Matching Debian debug package SHA-256:
  `85055cc575d3828caf72ca2f45efc28c206ea6f3e00597fb7d88b65b7476ca28`.

Offsets and instruction guards were derived from that executable, its matching
Debian debug symbols and exact upstream sources. Runtime use needs neither the
debug package nor GDB/Frida. An update needs a newly audited pin; changing only
the accepted build ID or hash is insufficient. The launcher rejects other
executables. The preload leaves unsupported builds or missing-helper startup
unchanged, with a diagnostic in its log.

## Build and run

Requires Linux ARM64, Python 3.11+, Clang, an existing NEXTSPACE Wayland session,
and the existing `libnextspace-native-scroller.so.1` built by
[ForeignScrollers](../../Libraries/ForeignScrollers/README.md). Run from the
repository root, substituting paths to the matching executable and native bridge:

```sh
python3 Experiments/ChromiumScrollers/build.py --output /tmp/libnextspace-chromium-hook.so
python3 Experiments/ChromiumScrollers/run.py \
  --chromium /path/to/chromium \
  --native-library /path/to/libnextspace-native-scroller.so.1 \
  --hook /tmp/libnextspace-chromium-hook.so \
  --log-directory /tmp/nextspace-chromium-logs \
  -- file:///absolute/path/to/Experiments/ChromiumScrollers/test-page.html
```

The launcher creates a private temporary profile and socket, starts the helper,
and cleans up both processes. It retains the sandbox. It selects non-overlay
scrollbars and software rendering, matching the tested configuration. It does
not disable smooth or threaded content scrolling. `--backend NAME` optionally
selects an existing GNUstep backend for the helper alone; it does not change
user preferences. The test guest had an old user backend alias, so qualification
used a temporary alias to its installed native106 backend.

## Qualification and limits

Verified 2026-11-05 on Debian 13 ARM64, installed NEXTSPACE native106, headless
Wayland/Pixman, 100% scale and a 868×571 content viewport. The renderer retained
`Seccomp: 2`. The test used the previously built native bridge with SHA-256
`5a11964eeb514900fdd7d706b370f419543f4ebc9896bf68c9d8e560584f6042`.

Checks passed for exact native pixels at positions 0 and 700; a single arrow
step; native held-arrow repeat and release; thumb dragging outside the bar;
nested and horizontal controls; retained LTR text direction; reload during
tracking; launcher startup/cleanup; unsupported-build rejection; and
missing-helper startup. The final build's 18×553 scrollbar crop at position 0
again matched every RGB pixel of the native bridge output. See
[qualification.json](qualification.json) for the measured results.

This establishes feasibility, not general Chromium support. Physical GPU and
HiDPI operation, custom CSS scrollbars, accessibility, touch, keyboard parity,
large documents, multiple simultaneous browser instances, helper failure during
use, and performance remain unqualified. Pixel transport emits many paint
rectangles and synchronous IPC can stall rendering. A tab/helper crash or timeout
still needs stronger recovery. Default metrics currently cover the tested native
control size. This experiment changes neither browser chrome menus nor shortcut
bindings, and does not cover other Chromium versions or architectures.

Local raw evidence is under `.build/foreign-scrollbars/chromium-prototype/`:
`qualified-input-checks.json`, `qualified-native.jsonl`, `qualified-hook.log`,
`qualified-zero.png`, native references, earlier comparison screenshots and
source inputs. The stock executable and the existing native bridge passed their
hash checks afterward. Downloaded packages were extracted in a private test
folder; the guest package inventory was unchanged.

## Expanded requirement and disabled-control checks

The [full native-control integration scope](../../docs/Native-Control-Integration.md)
now records the requirement for browser UI, forms, menus, editing and shortcuts
across browser families. The partial standard-form experiment below is the next
implementation step; browser UI, menus and editing remain open.

The earlier `qualified-zero.png` screenshot contains Chromium artwork in the
nested disabled horizontal bar. Its original fallback trigger was not
conclusively reproduced; this artifact must not be described as fully native.
Fresh startup and eight new enabled/disabled comparisons match native pixels.
The request guard now accepts content smaller than the viewport, which the
existing `NSScroller` already supports, rather than invoking Chromium's fallback.

`native-reference.py` renders reference images from the unchanged native bridge
(requires Pillow and the existing GNUstep backend). `check-disabled.py` uses an
explicit agent-browser session attached to the isolated test fixture, checks
both nested scrollbars across fitting, overflowing, empty and restored content,
and compares every pixel with those references. Run the reference generator in
the native test session and the browser checker where agent-browser is available:

```sh
python3 Experiments/ChromiumScrollers/native-reference.py \
  --library /path/to/libnextspace-native-scroller.so.1 --output /tmp/native-references
python3 Experiments/ChromiumScrollers/check-disabled.py \
  --session YOUR_TEST_SESSION --cdp YOUR_TEST_PORT \
  --references /tmp/native-references --output /tmp/disabled-control-results
```

Raw results and screenshots are in
`.build/foreign-scrollbars/chromium-prototype/disabled-matrix/`. All eight native
pixel comparisons passed at 100% scale. This does not qualify other controls,
other browser builds or the cause of every earlier fallback.

The existing scrollbar ABI now forwards to the separate
[native UI provider](../../Libraries/NativeUI/README.md). The Chromium hook asks
that provider for scrollbar thickness at startup; it no longer supplies a fixed
native width. Changing only the UI library's `GSScrollerDefaultWidth` setting
from 18 to 22 changed Chromium's layout and passed eight native pixel checks
plus an arrow-action check without rebuilding Chromium or the bridge. This
qualifies that metric handoff, not all controls or arbitrary theme changes.

## Standard buttons, checkboxes and radio buttons

Set `NEXTSPACE_CHROMIUM_FORMS=1` when launching the same pinned experiment to
enable the initial standard-form bindings, and open `test-forms.html`. This flag
is separate because these bindings do not yet cover the full control contract.
They require the new NativeUI provider behind the legacy scrollbar ABI. The
existing scrollbar-only library still works without generic controls.

`forms.inc` connects Blink's element state, paint lifecycle, geometry and trusted
mouse events to the provider. The helper calls `nxs_control_*`; it does not draw
or implement controls. Native AppKit supplies button text, glyphs, preferred
sizes, pressed state and mouse tracking. Blink's own text children are suppressed
for the native push button, so its label is drawn once by the native library.
The native action gates the existing DOM activation pipeline; page event handlers,
checkbox preactivation/rollback and radio-group model updates stay in Chromium.
Removal cancels native tracking and discards callbacks from the destroyed object.

The common transport now sends larger images using sealed, read-only mapped file
descriptors. The tested 640×64 native button exercises this path inside the
sandboxed renderer. The experiment compiles only its small preload library;
Chromium and the UI library remain unchanged.

On the same ARM64/native106 setup at 100% scale, `check-forms.py` passed 33 checks:
11 complete control images, 3 pressed images and 19 behavior/event assertions.
Direct NativeUI references match every RGB pixel. `check-form-trace.py` separately
verified 19 native press/release pairs, 16 native actions and 3 cancelled gestures
(pointer capture, removal and reload). Eight existing scrollbar pixel checks
also pass with the shared transport. See `forms-qualification.json` for evidence
hashes and the exact limitations.

`native-control-reference.py` renders reference images directly through the
public library ABI, independently of Chromium and its IPC helper. Its `--controls`
JSON describes each fixture control with `id`, `kind`, `width`, `height`, `title`,
`enabled` and `state`; the browser checker also uses its measured integer `x` and
`y`. The reference tool accepts the helper's `-GSBackend` option. Run browser
checks with an explicitly owned agent-browser session and a fresh fixture, and
validate the helper log from that run with `check-form-trace.py`.

That qualification covers the fixture's standard mouse path. The optional
focus/keyboard integration below extends it. Label activation, accessibility,
touch, arbitrary fonts/automatic button sizing,
rich button content, author-styled controls, CSS zoom/transforms, cross-process
frames and HiDPI remain open. Titles containing NUL or exceeding 64 KiB currently
fall back. Browser chrome and Chrome, Vivaldi, Firefox and derivatives have no
qualified form bindings. Closing the private browser removes the memory patches;
the installed NEXTSPACE session is unchanged.

The helper now advertises optional provider input capabilities and accepts
first-responder focus and key events over the generic-control transport.
`check-control-input.py` verifies these round trips for buttons, checkboxes,
radios and sliders; native AppKit interprets the keys.
The existing 33 mouse/pixel checks, native-action trace and eight scrollbar
pixel checks still pass with the extended provider. Provider-level input and
ABI compatibility evidence is in `Libraries/NativeUI/input-qualification.json`.

## Optional native focus and keyboard binding

Set both `NEXTSPACE_CHROMIUM_FORMS=1` and `NEXTSPACE_CHROMIUM_INPUT=1` to connect
the same pinned browser's standard buttons, checkboxes and radio buttons to the
provider's optional input API. It requires both advertised input capabilities;
an older provider retains the prior mouse-only path. Neither flag is enabled
in the installed NEXTSPACE session.

`forms-input.inc` translates the browser's focus state, logical key data and
control model into the public NativeUI contract. AppKit's real responder
interprets the keys and draws focus. A native action calls Chromium's existing
trusted activation pipeline after page keyboard listeners have had the chance
to cancel the event. Chromium owns its real form submission, checkbox rollback
and radio-group data model. The provider's next/previous requests call the
browser's real focus controller; the bridge carries no copied tab order or key
bindings. Blink's second widget keyboard handler and focus outline are suppressed
for the native control. Removed objects have distinct native identities, so
reinserting a DOM object cannot revive its cancelled gesture.

`check-form-input.py` passed 62 assertions on the same ARM64/native106 setup:
normal, focused and pressed native pixels; native focus without an additional
browser outline; trusted keyboard actions and model changes; focus traversal;
event cancellation and rollback; untrusted keys; removal/reinsertion; real HTML
form submission; and creation/focus/activation of new controls. The independent
`check-form-input-trace.py` witnesses twelve native keyboard actions and three
native mouse actions, plus next/previous native focus requests. The existing
33 mouse checks also pass with native focus enabled; supply
`check-forms.py --pressed-references` with focused native references for that
configuration. `native-control-reference.py --focus` generates them directly
through the public library ABI. See [input-qualification.json](input-qualification.json).

This remains partial integration of one exact binary. Offscreen native keyboard
activation animation, native radio-group keyboard context, default buttons and
key equivalents, IME, accessibility and the other controls/frontends are still
open. AppKit and Chromium were not rebuilt. Changing appearance or widget key
behavior belongs in the UI library; this bridge remains a consumer of it.

The current native button binding also consumes `NSButton` preferred sizes for
ordinary, input, flex and grid buttons. Buttons and selects share one guarded
Blink layout adapter and its original border/padding accessors. The existing
intrinsic override preserves original containment values and outer CSS size
constraints. Complete native models supply metrics after paint; the existing
renderer work loop schedules normal intrinsic invalidation outside paint.
Original DOM child/attribute/value notifications refresh retained backgrounds
for changed rendered titles, including nested and hidden descendants.

Every painted interactive form control now registers the existing native input
lifetime before native pixels are committed, including button-only documents.
On an observed host epoch change, all painted native controls re-enter the
existing paint path. Actual desktop checks verify all 13 retained button models
are recreated in the replacement host, alongside native sizes, complete pixels,
trusted submit/reset actions and cancelled keys before and after replacement.
`check-button-sizing.py --fixture OUTPUT --text-regression` checks the same
button cases plus native text pixels, Emacs navigation and edit cancellation;
the existing select cases cover the shared layout path. See the
[button sizing qualification](button-sizing-qualification.json).
Rich button content, broader CSS/scaling, animation/default-button behavior,
accessibility, derivatives and installed deployment remain unfinished.

## Determinate progress indicators

Set `NEXTSPACE_CHROMIUM_FORMS=1 NEXTSPACE_CHROMIUM_PROGRESS=1` for the additional
determinate progress binding, and open `test-progress.html`. It works with or
without `NEXTSPACE_CHROMIUM_INPUT=1`. The guarded hook accepts actual
`HTMLProgressElement` objects and reads their existing `position()` method.
Chromium owns HTML value/max validation; the shared NativeUI provider's existing
`NSProgressIndicator` draws the full control. There is no copied progress widget
or browser-specific artwork. These display-only objects do not enter the button
mouse/focus pipeline, so a normal trusted DOM click still reaches the page.

`check-progress.py` passes 20 assertions, including 16 whole native image
comparisons. They cover initial values and HTML defaults/clamping, value/max
updates, resize, reinsertion, replacement and reload. References come directly
from `native-control-reference.py`, whose fixture records can now specify
`minimum`, `maximum`, `value` and `indeterminate`. The independent native trace
verifies 18 real progress objects, 22 model updates, 10 destructions and eight
current-document objects, with no native button/key action requests. Existing
62 input and 33 mouse checks also passed while developing this binding.

An early initial frame showed Chromium artwork in the first bar; changing its
value corrected it. Later fresh starts and reloads passed, but the original
fallback remains unexplained. The first-frame checker does not reload or mutate
controls before checking them, and bitmap/canvas diagnostics remain in the hook.
Without the additional animation flag below, indeterminate animation retains
Chromium's implementation.
See [progress-qualification.json](progress-qualification.json) for the exact
evidence and remaining limits. Chromium, the provider and the UI library were
not rebuilt for this binding; only the preload library was compiled.

## Native progress animation

Add `NEXTSPACE_CHROMIUM_ANIMATION=1` to the forms/progress flags and open
`test-animation.html`. This also requires the provider's optional native-event
capability. Keyboard routing can be enabled or disabled independently. The
installed NEXTSPACE session does not enable these experiment flags.

The provider calls the real `NSProgressIndicator` animation methods and services
its native run-loop timers. The helper uses the returned deadline to wake and
observes the native repaint flag. Operation 9 reports a per-process invalidation
generation and next native delay. A renderer transport watcher uses the existing
thread controller wakeup, then the owning renderer thread marks affected controls
dirty and calls its actual frame scheduling API. The watcher stops when the last
animated object is detached or becomes determinate. Neither helper nor browser
bridge chooses animation frames, artwork, a widget interval or an easing rule.

`check-animation.py` passes 59 assertions: 48 complete frame images match direct
native-provider references, both animated controls move, determinate/stopped
controls stay stable, and restart, reinsertion, removal of every animated control,
creation and reload preserve native output. Native traces verify real view
invalidations and destruction with no button/key actions. Provider and helper
probes independently cover native deadlines, idle wakeup, process isolation and
stop/restart/destruction. The existing 62 keyboard/focus, 33 mouse, 20 progress
and eight scrollbar checks pass with the new event service enabled.

This is still one exact software-rendered ARM64 binary at 100% scale. The earlier
initial-frame fallback remains unresolved. Keyboard activation animation, rich
controls, other frontend/engine bindings, helper failure recovery and broader
display/accessibility/performance qualification remain open. The engine may
still request redundant progress repaints; its old progress pixels are not used
by the native binding. See
[`Libraries/NativeUI/animation-qualification.json`](../../Libraries/NativeUI/animation-qualification.json)
for exact sources and evidence. Only integration libraries were rebuilt; the
installed AppKit library and Chromium executable were unchanged.

## Optional native sliders

Add `NEXTSPACE_CHROMIUM_SLIDERS=1` alongside the forms/input flags and open
`test-sliders.html` in the same pinned binary. This requires the provider's
optional event and range-step capabilities. It connects standard HTML range
controls to actual `NSSlider` instances, including horizontal/vertical output,
native focus, keyboard input and continuous mouse tracking.

`forms-sliders.inc` reads the engine's own range model and invokes its existing
decimal setter, validation, serialization and trusted input/change dispatch.
The helper transports native values; it defines no slider tracking, knob
geometry, artwork or key bindings. Small discrete domains configure the native
slider's existing tick-mark properties through the independent provider API.
Dense domains use native continuous input followed by engine data validation.
Native actions wake the renderer through the existing event handoff, so a held
pointer can update the DOM before release. Page cancellation, removal and
reinserted-control identities are respected.

The initial fixture passes 50 assertions, including nine complete normal/focused
images and sixteen key results compared with independent native-provider
references, live drag updates, outside-control clamping, one change event on
release, cancellation, disabled controls, untrusted keys and callback removal.
Only the provider/integration libraries were rebuilt. The underlying AppKit and
Chromium executable were unchanged. See
[`slider-qualification.json`](slider-qualification.json) for exact evidence.

This is partial HTML slider support for one pinned build at 100% scale.
Constant-value domains are excluded because the installed `NSSliderCell`'s knob
geometry divides by the range width; that needs a fix in the UI library itself.
Automatic metrics/layout, arbitrary step bases and dense-step rounding, dynamic
style/model combinations, touch, accessibility, HiDPI and other browser/frontends
remain unqualified. Existing early progress/scrollbar fallback observations
remain unresolved. This does not complete the all-controls requirement.

The shared provider now hosts actual native popup buttons and menu windows.
The generic helper accepts their ordered models, native input, geometry queries
and origin requests through optional operations 11–13, with item payloads up to
64 KiB. Native descriptor readiness services IPC and native window events while
idle. Eighteen independent transport checks pass; see the
[provider menu contract](../../Libraries/NativeUI/README.md). These methods are
now wired experimentally to classic HTML selects as described below. Browser
frontend menus and the Firefox adapter remain implementation work.

## Native HTML selects

`NEXTSPACE_CHROMIUM_POPUPS=1`, together with the existing forms/input flags,
binds the pinned binary's classic single-selection controls to actual
`NSPopUpButton`/`NSMenu` objects. The engine supplies ordered option/group data,
labels, disabled state, selection identities and screen-coordinate conversion.
NativeUI supplies drawing, menu geometry, highlight movement, key handling and
tracking. Native actions call Chromium's real popup-selection method and emit
trusted application input/change events. The engine's own popup lifecycle
retains `:open`, mutation observers and its accessibility notifications.
Application `showPicker()`/hide requests use optional native operation 14;
they do not synthesize a particular opening key.

The current option model also omits display-hidden groups and descendants,
preserves a hidden selected label through the shared native popup-title method,
and validates original list indices as well as visible identities before a
commit. Inserting a hidden option can change those indices without changing
any visible row. Both engines now share `Bridge/Popups.inc` for row/title
transport and `Tests/Wayland/popup_models.py` for the same actual-seat model
cases. `check-popup-models.py --fixture OUTPUT --sizing` uses the owned CDP-pipe fixture
and whole desktop captures; it keeps the browser's own tabs/address bar/toolbar.

At zoom 1 in horizontal writing, the pinned adapter now returns the native
popup cell's preferred size at Blink's existing menu-list intrinsic boundaries.
Original border/padding accessors convert the full native size to content size;
Blink retains explicit CSS sizes, min/max and box sizing. Existing option/group
notifications call the original menu-list intrinsic invalidation method, so
unselected text, labels, visibility, insertion and removal update layout without
a second observer, timer or text-measurement implementation.

The native cell also owns disabled drawing. A small adapter correction at the
original UA stylesheet parser removes the browser's additional fade for ordinary
single selects, including feature-dependent UA rules. Author/user opacity and
unsupported listbox/multiple-select defaults retain their cascade behavior.
The shared desktop recovery case replays an unchanged hidden selected label and
grouped/disabled model after host replacement, then commits the first native
action to the original option index once. See the
[sizing and recovery qualification](popup-sizing-qualification.json).

`check-popups.py` passes 29 checks, including seven full control images,
keyboard/mouse selection, cancellation, focus navigation, application opening
and blur, duplicate labels, disabled items, stale option identities and
removal/reinsertion during callbacks. References come directly from NativeUI;
the mouse test waits for the native highlight and uses native item rectangles.
That earlier disabled image comparison explicitly set CSS opacity to 1; the
current sizing checks above compare the ordinary disabled control without an
author workaround and independently check author opacity and listbox defaults.
All 232 existing browser checks and the shared provider's compatibility,
transport and 30 unchanged scrollbar image comparisons also pass.

Complete popup lifecycle, scaling, vertical writing, appearance overrides,
listboxes, IME, accessibility, derivatives and installed deployment remain open.

This remains partial support for one exact binary at 100% scale, with no browser
or underlying UI-library rebuild. Live model replacement while open currently
rejects stale actions rather than updating the displayed menu. Default disabled
opacity, automatic metrics/layout, styled selects/listboxes, physical auxiliary
window input across focus changes, browser window parenting and compositor-global anchor
agreement after moving/resizing, multiple outputs/scales, touch and full
accessibility remain unfinished. No browser frontend or derivative
coverage follows from this fixture. See [`popup-qualification.json`](popup-qualification.json).

## Native invalidation notifications

The helper now signals a renderer-owned eventfd when the native UI invalidates
a view, changes a popup's visibility or sends an action. The renderer waits for
descriptor readiness and schedules its existing UI thread; idle watchers no
longer poll a native deadline to discover those changes. This is transport for
all bound controls, with no widget timer, drawing or key rules in the bridge.
The optional operations 15/16 leave existing request structures and the public
NativeUI ABI unchanged. An older helper retains the prior deadline handoff.

Registration covers changes since the renderer's last generation snapshot.
Notifications coalesce and remain isolated by process. The helper validates
nonblocking eventfds, keeps its own reference, and closes it on replacement,
unregister or disconnect. Kernel sender credentials and pidfd readiness track
active subscribers even when sandboxed renderers report PID 1 or share a
request connection. A killed subscriber's native form controls are destroyed.
This does not yet provide process-lifetime cleanup for all idle/native-scrollbar
objects when no notification subscription exists.

The helper also completes initial draws through the actual native controls and
scrollbar API before binding its service socket. This moves AppKit's first
font/image initialization out of bounded application paint RPCs. A reproduced
progress-resource lookup timeout and first-frame fallback led to this change;
earlier fallback reports with unconfirmed triggers remain separate open issues.
No underlying UI library or browser was rebuilt for this work.

The transport suite includes isolation, registration races, saturated counters,
descriptor cleanup and abrupt owner death with a shared connection still open.
Real native menu-window clicks have separate helper/renderer timestamp traces.
See [`notification-qualification.json`](notification-qualification.json) for
the measured results and remaining scope.

## Native plain/password text fields

`NEXTSPACE_CHROMIUM_TEXT=1` with the existing forms/input flags binds themed
plain/password webpage fields to the shared actual `NSTextField` and
`NSSecureTextField` field editors. Native controls supply the complete bitmap,
selection, caret and interpreted key commands. The adapter suppresses the
engine's anonymous editor drawing and caret only after a native field is
prepared. No text editor, key-binding table, glyph layout or caret timer is
copied into the bridge. The existing NativeUI provider/loader/shim and AppKit
binaries are reused unchanged.

Single-click and Shift-click positioning, selection dragging and outside-field
extension now use those actual native editors' `mouseDown` tracking. Blink
retains cancellable DOM events, focus and mouse-release bookkeeping. While the
native editor owns the gesture, the adapter bypasses competing Blink selection,
text-data dragging and selection autoscroll. The existing notification channel
echoes actual native UTF-16 selections on the renderer thread. Reading a busy
editor's bitmap does not rebind its model. Script changes to value/selection,
editability, focus or size end tracking before applying the canonical model.

Native proposals enter Blink's actual insertion and menu/key command paths.
They retain `beforeinput` cancellation, trusted `input`/`change`, maxlength,
readonly/disabled state and engine undo. Native proposed deletion ranges are
applied after `beforeinput` only while the canonical value and original
selection remain unchanged. The native edit is vetoed after the engine action,
then its canonical model is echoed back. Logical modified keys use DOM key
identity instead of Chromium's control-character text payload. Programmatic
value and selection updates invalidate the complete native snapshot at the
actual engine model boundaries. Native caret invalidations reuse the existing
process-owned eventfd/work-loop integration.

The [source/ABI audit](text-source-audit.json) and
[text qualification](text-qualification.json) record the exact boundaries and
runtime evidence. `check-text.py` drives the owned fixture through agent-browser
and compares complete fields with independent direct-provider references.
The [pointer qualification](text-pointer-qualification.json) records fifty
independent native pointer cases and the lifecycle/regression checks.
`check-text-pointer.py` keeps the same owned browser session for inspection and
screenshots. For fractional pointer coordinates and held Shift, which the
installed CLI cannot express, it sends input through that owned page's CDP
endpoint using Node's built-in WebSocket.

This is one exact opt-in ARM64 build at scale 1 with fixed field dimensions.
Multiple-click metadata, selected-text data dragging, context menus, touch and
long-field horizontal/autoscroll behavior remain open.
Clipboard/cut/paste web-event integration, native undo-menu routing,
typing undo grouping, selection-event/direction details, IME/composition,
accessibility, other text types, native intrinsic sizing, broader styling and
scaled/transformed output remain open. Address bars, browser frontends,
derivatives and other binaries still require integration. The native control
does not automatically provide all browser/application behavior.


## Partial native address field

The same pinned binary now has an optional Omnibox/Views adapter. Launch with
`run.py --native-views` and a NativeUI provider advertising `NXS_TEXT_COMMAND`.
This enables the required form/input/text bindings as well. Only the small
adapter and shared provider extension are built; Chromium and installed AppKit
remain unchanged. Unsupported browser builds still fail the executable guard.

`views-text.inc` binds the real Omnibox model to the existing `NSTextField`.
The native library draws the complete field and interprets editing keys. Real
Views insertion/deletion methods retain application callbacks and history;
the native pre-edit veto prevents a duplicate edit. Native-interpreted clipboard
selectors invoke the actual Omnibox commands, including its asynchronous paste
and existing sanitization. A focused native editor receives modified editing
commands before browser accelerators, without a copied shortcut table.
The source audit also accounts for the inlined Omnibox painter and separate
engine caret view. Actual native invalidations reuse the eventfd/work-loop host.

The [Views audit](views-source-audit.json) records the source receipts, compiled
layouts and 28 instruction guards, including the four pointer boundaries. [Qualification](views-qualification.json)
records 43 address-field checks, including nine independent native editing-key
cases, Alt+C/V/X, real focused TextEdit copy into the browser, and complete native
images at two widths. All 335 webpage pointer/text/input/slider/progress/animation
checks pass with the new provider/helper. Closing a second browser window
explicitly releases its native field. Losing the owned helper restores engine
painting and typing. Older providers/loaders/text clients and thirty unchanged
legacy scrollbar images pass the shared provider checks.

`check-views.py` runs inside the private headless fixture, using its owned
compositor control socket and trusted screencopy client. It requires `--fixture`,
`--references`, `--pasteboard-probe`, `--native-text-app` and `--backend` paths.
The retained fixture harness, inputs, images and logs are under
`.build/native-ui/chromium-views-qualified/` and `chromium-views-source/`.
`NEXTSPACE_CHROMIUM_VIEWS_TRACE=1` records actual model values for synthetic tests
and is off by default; keep it off for normal browsing.

Native address-bar multiple-click metadata, undo/redo availability, clipboard availability
across different native/platform states, IME, accessibility and scaling remain
open. The surrounding address-bar layout, buttons, suggestion popup, tabs, menus
and dialogs still need native integration. This qualifies one partial Chromium
frontend binding; Chrome, Vivaldi, Firefox frontends and other toolkits remain
required by the full scope.

The [pointer qualification](views-pointer-qualification.json) now adds native
single primary-click/Shift-click and selection dragging to the address field.
`views-pointer.inc` binds the real SelectionController boundary to the existing
native editor. Its original handled-press path retains application click-count
and drag-threshold bookkeeping while skipping engine selection geometry.
Application selection callbacks, release/capture handling and primary clipboard
publication remain in Views/Omnibox. No hit testing, tracking loop or control is
copied. Held drawing reads the actual busy editor; model, focus, enabled or size
changes end that native gesture without overwriting application state.

`check-views-pointer.py --fixture PATH --library PATH --backend NAME` compares
ten cases with independent direct-provider ranges and verifies every gesture
entered native tracking. Fifty assertions pass, including typing from the native
range and resizing during a held gesture. Six released images compare the
complete field. Two outside-field held images also compare the complete field;
four other held comparisons exclude only the measured cursor overlay, retaining
unaltered captures and requiring complete comparisons after release. The previous
43 address-field and 335 webpage checks pass with the new adapter. Closing a
window and losing the helper during held selection also pass recovery checks.
The provider, loader, shim, AppKit and Chromium binaries remain unchanged.

Right/middle buttons, selected-text data dragging, touch,
long-field autoscroll, broader initial-focus/unelision behavior, selection
direction, IME and scaling remain unqualified. Those paths and the remaining
browser frontend still require integration.

The optional shared pointer capability now forwards real Views click-count
flags and Blink's existing `WebMouseEvent.click_count` to the native editor.
`check-views-pointer.py --click-counts` compares real double/triple clicks and
word/line drags with independent GNUstep ranges and pixels. Webpage pointer
checks also consume references generated with `native-control-reference.py
--pointers --click-counts`. No browser or AppKit rebuild is needed; only the
small shared provider/loader extension and adapters change. Runtime and ABI
evidence is in [click-count qualification](../../Libraries/NativeUI/click-count-qualification.json).

## Application clipboard commands

The opt-in startup menu binding below changes clipboard shortcut provenance:
GNUstep's application menu can handle the key before the field's own menu.
Use `check-text-commands.py --application-menus` for that fixture. It requires
native validation and exactly one real Chromium model execution for Paste,
then runs the same trusted event, cancellation and editing checks. The
ordinary field-only callback assertions remain available without this flag.

The Chromium address and webpage text bindings now opt into the existing shared
application-command filter. GNUstep's real menu and editor still choose and
validate keyboard actions. The bridge asks the actual Omnibox or Blink command
controller whether Copy, Cut or Paste is available, then executes that existing
application command once. No control, shortcut table, clipboard implementation
or menu implementation is copied. Only the small Chromium adapter is rebuilt;
Chromium, AppKit and the shared provider/loader/shim remain unchanged.

This fixes native Paste when Chromium owns valid platform clipboard text but the
offscreen native helper has no pasteboard types. `check-text-commands.py` proves
that precondition with an original browser textarea before testing the native
address and webpage fields. Its `--negative` mode requires both Paste cases to
fail with the earlier adapter. Positive checks also cover trusted clipboard
events, cancellation, Unicode, custom clipboard data, password/read-only fields,
maxlength, existing engine undo and removal during paste. The real Omnibox paste
path retains asynchronous policy checks and URL sanitization.

The [source audit](text-command-source-audit.json) records the four additional
compiled guards and exact upstream receipts. The
[qualification](text-command-qualification.json) records 44 command assertions,
43 address-field assertions, 335 webpage regressions and four recovery
assertions. Complete native field images and native TextEdit clipboard exchange
are included. All 26 recorded owner processes exited, and the private sockets,
backend alias and owned automation connection were closed.

This remains a partial binding for one exact Chromium build. Complete application
menu coverage and Undo/Redo availability, clipboard owner/focus lifetimes, other clipboard
formats, IME, accessibility, scaling, remaining browser controls and dialogs,
derivative builds and GTK/Qt/KDE applications still require integration. The
shared command boundary also serves the separately qualified Firefox binding.

## Application menu models

`run.py --native-menus` opts the pinned legacy Chromium application menu into
real GNUstep `NSMenu`/`NSMenuItem` objects and enables the required native Views
bindings. Activating the existing toolbar menu button projects Chromium's actual
model. The browser still owns localized labels, live command availability and
command execution. Icon-button labels use its existing accessibility helper;
mnemonic removal uses its existing text utility. GNUstep owns menu sizing,
tracking, submenu placement and native key-equivalent matching. The bridge and
UI provider remain separate. Chromium and AppKit are not rebuilt.

Native execution queues the actual model activation through Chromium's real UI
task runner. A synchronous native paint RPC can dispatch a callback on the UI
thread while Chromium is midway through a frame, so executing a browser mutation
inline is unsafe. The shared transport also services owner callbacks before
blocking on a worker-held RPC mutex; otherwise an idle menu acknowledgment can
form a wait cycle. The retained earlier transport fails that new regression.

`check-app-menus.py` runs after `check-text-commands.py` on the owned English
`test-text.html` fixture, with `NEXTSPACE_CHROMIUM_MENUS_TRACE=1` enabled for model
assertions. It verifies actual tabs, page zoom, trusted clipboard events, engine
undo, a native Command key from a text field, and menu replacement. Its observed
fixture coordinates never enter production code. Model tracing is opt-in because
application labels can contain user data. Exact source receipts, ABI guards and
runtime results are in [the source audit](app-menu-source-audit.json) and
[qualification](app-menu-qualification.json).

This is partial integration for one exact build. Automatic startup and active-app
menu association, the full original menu lifecycle, lazy bookmark/tab-group
models, dynamic structure and checkmarks, icons/torn-off menus, actionable
submenus, additional key encodings and global shortcut dispatch remain required.
The alternate `ActionAppMenu` path, Firefox menus, derivative browsers and
GTK/Qt/KDE bindings are not implemented by this change.

## Native menu keys from startup

`NEXTSPACE_CHROMIUM_MENU_KEYS=1`, together with the existing native Views and
menu options, makes the pinned Chromium build create its actual application
menu model from a real UI task after window initialization. The detached
GNUstep menu therefore exists before the toolbar button is clicked. Window
activation selects that window's model; teardown retires its identity so a
queued task cannot revive a deleted browser window.

The bridge asks the actual native menu whether a web key matches, then lets
Chromium deliver the key to the renderer. Execution occurs after the renderer
declines it, or through an existing native control's normal menu dispatch.
A page's `preventDefault()` still cancels the action. Native field behavior,
application controllers and GNUstep's menu ordering remain intact. There is
no new shortcut table, widget renderer, menu tracker or browser rebuild.

`check-global-menu-keys.py` covers cold startup, body/button keys, cancellation,
synthetic and unmatched events, foreign connections, two-window focus and
window teardown. The source audit is [here](global-menu-source-audit.json),
and the qualification is [here](global-menu-qualification.json).

## Shared-host recovery and real seat input

The session supervisor now retains the original client and callback endpoints
across native host loss. The pinned browser reconstructs its native fields and
application menu from live engine models. A missing native menu is reprojected
on focus or key handling, and a queued menu action from an older host epoch is
discarded. No browser rebuild or control implementation is involved.

Real Wayland Control-letter events can carry an ASCII control character in
Blink's unmodified-text field, while automation supplies the DOM key. For
Control-only letter events, the adapter uses the existing DOM key as the
native event's unmodified characters. GNUstep interprets the binding; the
adapter adds no key table. Alt/Super and logical key paths retain their data.
The shared host also defers keys received inside native menu validation until
that call returns, with expiry before the adapter's fallback deadline.

The [recovery qualification](../../Applications/Session/native-ui-recovery-qualification.json)
covers real compositor-seat keys for normal/password webpage fields and the
Omnibox before and after host replacement, native application commands and
switching to Firefox and back. These checks apply to the pinned Chromium build;
other Views controls, IME, automatic installation and derivative frontends
remain open.

## Experimental multiline fields

`NEXTSPACE_CHROMIUM_MULTILINE=1`, alongside the existing forms/input/text flags,
enables text areas when the provider advertises native multiline support.
The exact-build adapter uses the real `HTMLTextAreaElement::Value()` getter and
default-event boundary, the shared `TextControlElement` selection methods and
the existing engine edit transactions. The textarea painter tail-calls the
already guarded text-field painter in this binary. Newline and Tab selectors
invoke the engine's `InsertNewline` and `InsertTab` commands; cancellation and
trusted events remain in Blink. No Chromium or AppKit rebuild is involved.

The [multiline qualification](../../Libraries/NativeUI/multiline-qualification.json)
records 18 real-seat checks before/after native host loss: native line navigation,
newline insertion and veto, ordinary insertion, Unicode ranges, key cancellation,
clipboard controllers and read-only values. This is experimental coverage of
the pinned build. Browser DOM scrolling, native viewport/layout synchronization,
wrap modes, complete scrollbar ownership, IME and other frontend controls remain
unfinished; the feature stays opt-in.

This remains an optional adapter for the recorded Linux ARM64 executable.
Chrome, Vivaldi, other Chromium versions, the remaining browser frontend,
full desktop session integration and other toolkits still require work.

`run.py --native-frame` additionally selects Chromium's existing system-frame
preference in its disposable profile through the shared
[`browser_frames.py`](../../Libraries/NativeUI/Bridge/browser_frames.py) helper.
The browser requests the compositor's existing xdg-decoration frame. Its title,
close/minimize controls, move/resize, shade and fullscreen behavior share the
desktop implementation; no browser hook or control drawing is added. The
actual Workspace desktop fixture accepts the same flag. Browser tabs/toolbars,
other builds/derivatives and installed-profile migration remain separate work.

`run.py --native-tabs` enables the experimental tab-container binding and its
required native Views/text bindings. The pinned browser's existing displayed
titles and ordered tab objects become application data for the shared ordinary
GNUstep `NSTabView`. AppKit supplies the complete image and pointer hit testing;
native selection invokes Chromium's original `TabStrip::SelectTab` controller.
Opaque monotonic IDs stay stable across reorder and retire before browser view
allocations can be reused. Browser pointers do not cross the tab transport.
The shared serializer is [`Bridge/Tabs.inc`](../../Libraries/NativeUI/Bridge/Tabs.inc).

The adapter replaces the container's child-painting/targeting paths, classifies
the owned native rectangle as client content and removes five
guarded legacy corner-overlap terms from the existing parent layout. It adds no
native drawing, tab layout, font, artwork or key-binding implementation. Browser
close/reorder/next-tab commands still use the browser's real controller. When
tab input retires Chromium's temporary application-menu model, the existing UI
queue recreates that real model without waiting for another key or focus change.
The original icon-layer lifecycle also keeps replaced loading indicators inside
the container paint boundary, including calls with inlined layer eligibility.

The [tab qualification](tab-qualification.json) records 81 actual Workspace
checks, including twelve complete native tab images, real pointer selection,
close/replacement/reorder, rapid tab clicks that retain client-area semantics, loading and later title changes, idle behavior, menu/model recovery, host replacement,
resize and fullscreen restoration. Shared-provider and both existing browser
regressions also pass. This is a tab-container prototype for the pinned scale-1
build: favicons/alerts, per-tab close buttons, context menus, dragging/touch,
overflow/groups, full pane/toolbar layout, accessibility and browser scaling
remain unfinished. The [Firefox binding](../FirefoxNativeUI/tab-qualification.json)
now reuses the same provider and serializer. Derivatives and installed deployment
also remain unfinished.


### Native radio pointer actions

The opt-in group adapter also routes pointer actions from the existing native
NSMatrix through the browser's original trusted pointer-click dispatcher. Shared
RadioBinding code retains the native action/key-cell snapshot and forwards the
original click count through the existing NativeUI transport. AppKit determines
selection, disabled-member behavior, outside-release behavior and multi-click
tracking. Frame retirement cancels the original tracking operation; the adapter
revalidates original engine membership and binding identity after page callbacks.
No control implementation or browser UI component is added.

See [pointer qualification](../FirefoxNativeUI/radio-pointer-qualification.json)
and its source audit for measured coverage. Label activation, layouts beyond the
current one-column model, browser scales and session-supervisor group recovery
remain open. This is a partial browser integration checkpoint.


### Native radio labels

With the shared semantic-activation capability, the pinned group adapter keeps
the original browser label handler and intercepts only its trusted forwarded
control activation. Original association, interactive descendants, text-selection
drag, focus and DOM cancellation remain engine-owned. The shared provider calls
original NSMatrix selectCell: and performClick:; native action state then passes
through the original engine click constructor and preactivation/rollback.

No key or pointer gesture is fabricated. The same optional NativeUI operation
serves existing NSButton controls for later toolkit/application adapters. See
[qualification](../FirefoxNativeUI/radio-label-qualification.json). The form
activation checkpoint below adds checkbox and button labels. Full accessibility,
topology/scaling and session group recovery remain open. Browser toolbar,
address bar and tabs keep their existing components.


### Native checkbox state and form labels

Trusted pointer, keyboard and label activation now carries the actual native
checkbox result into the original engine preactivation journal. Shared
`Bridge/ControlActions.inc` contains only the result, host epoch and scoped
source binding. The engine retains its original setter, dirty/model flags,
trusted events, click-handler writes and cancellation rollback. In particular,
an initially checked mixed checkbox follows the native button result rather
than an independently computed browser toggle. No checkbox cycling rule is
copied.

Original label association/filtering/focus and forwarded click construction
remain engine-owned. Checkbox and button labels use the existing shared
`performClick` operation, including original submit/reset defaults. Programmatic
activation follows the original model path. NativeUI provider/loader/shim and
the 528-byte API are unchanged for this checkpoint. Only the small adapters
are rebuilt; browser and AppKit binaries stay unchanged. See
[form activation qualification](../FirefoxNativeUI/form-activation-qualification.json)
and [source audit](../FirefoxNativeUI/form-activation-source-audit.json).

Browser toolbar, address bar and tabs retain their existing components. Later
requested UI changes belong in optional app-specific patches above the same
shared native library and bridge, reused by later GTK/Qt/KDE integration.

This checkpoint passes 732 scoped checks and 255 complete native image
comparisons across both engines and the dedicated original input mode. The
latter verifies six-control renderer cleanup, helper-loss fallback and preserved
`Seccomp=2`/`NoNewPrivs=1`. Runtime audit retains 20 unchanged measured production
binaries, the unchanged NativeUI SDK and no live owned candidate mappings.
Broader browser controls, geometry/scales, accessibility, recovery, complete
menus/shortcuts, derivatives/deployment and subsequent GTK/Qt/KDE work remain
unfinished.


### Native listboxes and multiple selects

`NEXTSPACE_CHROMIUM_LISTS=1` enables the pinned Blink list binding with the
existing native popup, text and input flags. It uses the same
`Bridge/ListBinding.inc`, wire transport and ordinary GNUstep `NSBrowser` as
the Firefox binding. There is no second list control or selection algorithm.
Original Blink DOM identities, option labels, visibility and selectedness form
the application model. Native selected IDs are applied through original option
setters and original trusted interaction completion.

Blink routes listboxes directly to CSS at its common theme boundary. The
adapter wraps that boundary once, keeps existing text hooks intact and supplies
the complete native bitmap. Existing engine option notifications and the
original selected-state setter invalidate that native owner after model changes,
including script selection. UA-origin corrections remove the extra disabled
fade and radius clipping; author/user cascade origins remain higher.

The shared real-seat suite compares whole images with ordinary native controls,
including a focused-only document before first paint, single/multiple selection,
script selection, cancelled input, model updates, outside release and frame
retirement. An independent ordinary window replays the outside gesture, since
the underlying matrix can retain visual state beyond its selected set.

This is opt-in integration for the exact pinned build at scale 1. Native
intrinsic/option geometry, full wheel/DOM/default scrolling, richer models,
host recovery, scales/zoom/accessibility, other browser builds and deployment
remain open. See [list qualification](list-qualification.json) and
[source audit](list-source-audit.json). Browser toolbar/address bar/tabs retain
their existing components; future requested changes use optional app patches
over the same shared layer used by later GTK/Qt/KDE adapters.

Final candidate 08 passes 34 list checks/13 whole native images. The same
adapter passes forms 101/28, radios 94/29, popups 66/27 and button/text 107/48.
The unchanged Firefox adapter passes the expanded shared list suite, 34/13.
The scoped total is 436 checks/158 complete images. Runtime audit retains all
20 measured production hashes, unchanged NativeUI SDK/API 1/568 and renderer
sandboxing. A separate source reproduction is byte-identical; all owned
fixtures are stopped. Earlier failing candidates remain separate evidence.


### Native list viewport and scroll binding

The pinned list adapter now consumes shared native clip/document measurements
through the existing text scroll-area boundaries. DOM client/scroll dimensions,
script scrolling and clamping use the real native values. Wheel input follows
original trusted DOM dispatch/cancellation and the native widget handler region;
GNUstep supplies the actual wheel movement. Native positions return through the
original engine setter and trusted scroll lifecycle.

Option client rectangles and selection-reveal bounds use measured native row
rectangles. The original selection task remains intact. Its scroll-origin
conversion uses the native clip origin, avoiding a second movement based on
hidden browser row/border geometry. Resizing and native appearance restoration
retain the original application offset and let the UI library clamp it. A
provider without the required geometry or item-hit API keeps the original engine
list path.

See [viewport qualification](list-scroll-qualification.json) and
[source audit](list-scroll-source-audit.json) for the original geometry work and
its retained failing target diagnostic. The pinned adapter now consumes the
shared native item-hit query at the original `LayoutView` hit-result boundary.
GNUstep supplies the row ID and row rectangle; the original engine setter owns
node references, write barriers and element/pseudo normalization. Native
non-item areas target the control. Original traversal, caches, trusted dispatch,
hover/related targets, cancellation and application overlays remain in use.

[Point-hit qualification](list-hit-qualification.json) covers down/up/click
targets, `elementFromPoint`, repeated cache hits, mouse/pointer hover, related
targets, cancellation, overlays and page scrolling. Native row identity is
revalidated after metadata RPC. Rectangle/list-based hit contracts remain open,
along with broader option/layout APIs, intrinsic sizing, held scrollers,
recovery, models/styles, scales/accessibility, derivatives/deployment and the
Firefox viewport/target port. Browser toolbar/address bar/tabs retain their
components; future UI changes remain app-specific patches over the shared layer.


### Native list refresh failures

A temporary native list-state rejection now remains in the list/engine fallback
path. It cannot enter textarea layout or call HTMLInputElement's text getter on
a select. Text model access validates the actual semantic kind. When native
measurements recover, lists reuse the existing deferred native-control layout
queue also used for button preferred-size changes. The original engine layout
invalidator removes temporary engine scrollbars before the complete native
control resumes. No control or layout algorithm is duplicated.

The test fixture accepts an optional --control-helper for an isolated real-host
fault wrapper. Tests/Wayland/native_ui_fault_helper.py rejects one armed list
state request, while retaining actual GNUstep controls and all other messages.
Run check-lists.py --native-failure --only-list with that fixture to exercise
single/multiple recovery, full native pixels, DOM viewport geometry and original
trusted native navigation. The CDP pipe retains notifications and request
metadata, including target crashes. It does not log evaluated scripts or image
response bodies.

See [failure qualification](list-failure-qualification.json) and
[source audit](list-failure-source-audit.json). This resolves the measured
renderer crash from the Firefox metadata compatibility checkpoint. A later wheel lifecycle fix resolves the separately retained textarea
reinsertion drift; see the native wheel default section below. Broader
recovery/scaling and the full browser integration goal remain open. Toolbar, address bar and tabs retain their existing components.


### Native wheel defaults and retired targets

Native wheel delivery runs inside the original trusted textarea/select default
handler. The adapter stages the original input only during original DOM
dispatch, checks actual WheelEvent class/trust/cancellation, and marks the
original default handled after the real shared NSScrollView accepts it. The
original manager supplies acknowledgement and target lifecycle. Nested
synthetic DOM events cannot trigger another native wheel action.

If a page listener removes or replaces the native target, the existing common
DOM dispatch boundary consumes that retired widget's default without calling
the released control. Otherwise the browser can begin a compositor scroll
which later overwrites the reinserted native viewport. Page listeners and
explicit cancellation retain their original behavior; native handling does
not set the content-visible defaultPrevented flag. No animation, scroll
algorithm or native component is copied.

The wheel regression checks observe the reinserted offset over 350ms and compare
the final complete native control, as well as cancellation, page mutation,
removal/reinsertion, nested synthetic events, fractional/modifier input and
unrelated engine scroll areas. Physical-seat input after reload waits for the
new visible frame. See [qualification](wheel-default-qualification.json) and
[source audit](wheel-default-source-audit.json). This remains a pinned scale-1
Chromium adapter; zoom, other builds/derivatives and broader browser integration
remain open. Browser toolbars, address bars and tabs keep their components.


### Native list model reveal

The existing renderer-thread native invalidation worker now mirrors list
viewports alongside textarea viewports. A real native list can reveal a new
script-selected row while its model is synchronized. Chromium must adopt that
measured native viewport through the existing original scroll setter; otherwise
its later reveal task sees a visible native row while DOM scrollTop stays stale.
The binding refresh and viewport setter are shared with native input. No reveal
or scrolling algorithm is added.

The shared engine test now retains immediate and asynchronous reveal samples,
requiring the exact original native target. It also removes a list during its
trusted wheel callback, verifies native release, reinserts it and compares a
subsequent physical wheel and stable viewport with the original native list.
Both engines run that same module. See
[reveal/lifecycle qualification](list-reveal-qualification.json).


### Native URL and telephone webpage fields

URL and telephone input types use the existing native text-field binding,
including real NSTextField pixels, editing, Emacs navigation and native clipboard
commands. Their engine selection APIs are compatible with the existing adapter;
the original engine still owns validation, sanitization, beforeinput/input and
page cancellation. No text editor, key map, formatter or UI component is added.

The shared text-types fixture compares complete native controls, tests Alt+C/V
from a URL field into a telephone field, and exercises read-only/disabled fields,
script updates, changing between text/URL/telephone and retirement during an edit.
Existing plain/password/Unicode text checks run in the same fixture. Browser
address bars, tabs and toolbars retain their components. Number
and other specialized field types still need integration. See the paired
[text-type qualification](../ChromiumScrollers/text-types-qualification.json).


### Native email webpage fields

Email and multiple-email inputs share the existing native NSTextField binding.
The adapter's original internal selection methods support them while the public
webpage API retains null selection properties and InvalidStateError for
setSelectionRange. Native keyboard selection and clipboard actions use the same
editor and original engine command path as ordinary fields. Validation, multiple
address sanitization, maxlength and trusted events remain engine behavior.

Independent native key sequences supply the email editor image oracle. For
read-only focus, the reference can configure its model before focusing and use
NXS_TEXT_NO_SELECTION so the original responder chooses its initial selection.
The tests preserve that native result rather than assuming a hidden caret range
or a select-all shortcut. Firefox also reuses paint-only owner invalidation from
its original input value-change callback, keeping inactive native field images
synchronized with script updates. Chromium reuses its existing before-paint
control binder for eligible single-line text fields, so immediate input after a
page changes the field type still reaches the native editor. The same guarded
style reader serves list and text eligibility. See the paired
[email qualification](../ChromiumScrollers/email-qualification.json).


### Native search editing and clear actions

Search inputs use the same shared native text binding with the original
GNUstep NSSearchField and NSSearchFieldCell. The native cell supplies the search
button, clear button, text rectangle, sizing and painting. NXS_SEARCHFIELD and
NXS_TEXT_SEARCH extend the existing control/model contract; providers without
the capability retain the original application fallback. NativeUI's optional
search-part query extends API 1 to 592 bytes while preserving its older prefix.

The clear observer forwards the original native button target/action and sends
its actual result through the existing text filter. Browser transactions retain
trusted beforeinput/input, cancellation and callback retirement. Chromium also
skips its hidden shadow widget's competing click default. Native delete: uses
the existing guarded DeleteBackward path so the proposed range is installed
after beforeinput. Firefox revalidates the owner before continuing pointer post
handling after a page callback destroys the frame. No search widget, clear
algorithm, icon, inset or key-binding table is copied.

The native search-button binding is described below. Recents, placeholders,
broader key/IME/accessibility semantics and other builds remain open. Browser address bars, toolbars and tabs
keep their existing components. See the measured
[search editing/clear qualification](../ChromiumScrollers/search-qualification.json).


### Native search-button activation

The shared provider forwards the original NSSearchField search-button action
and emits performClick: through the existing command filter. Capability
NXS_TEXT_SEARCH_ACTION gates this extension without changing API 1/592.
The common bridge retains only an activation receipt with native control ID,
action item, command serial and host epoch. Adapters consume it after the original DOM
click dispatch, where page listeners can cancel, remove or change the field.

Chromium uses its original TextEvent factory and internal EventTarget dispatcher
on the owning input. Its original input default handler retains change, implicit
submission, validation, default submitters and asynchronous search events.
Firefox uses its original FireChangeEventIfNeeded and MaybeSubmitForm methods
with the real pointer event's nsPresContext, after querying Gecko's existing
enabled state. Original keyboard Enter keeps its existing engine path. These
methods are guarded against the pinned binaries; no browser is recompiled.

See [search-action qualification](../ChromiumScrollers/search-action-qualification.json)
and its source audit for measured coverage and limitations. Clear-button click
ordering and cancellation are covered by the checkpoint below. Search
notifications, recents and broader editing/IME/accessibility contracts remain
separate work. Webpage control coverage, other browser builds
and derivatives, complete menus/shortcuts/deployment, then GTK/Qt/KDE remain
open. Later toolbar/tab patches must reuse the same native UI provider.


### Native clear actions after click dispatch

The original native cancel button now offers clearSearch: through the existing
command filter. Capability NXS_TEXT_SEARCH_CLEAR_COMMAND (256) gates this path;
unknown commands keep the previous native behavior. Both adapters use the same
activation receipt and existing click-default boundary as search submission.
They commit the original native cell through control_perform_click with
NXS_SEARCH_CANCEL after page listeners have run, retaining beforeinput/input,
cancellation, model changes and callback retirement in the original engine.
The provider's scoped recursion guard prevents the committed native button from
requesting another deferred action. API 1 stays 592 bytes. No browser private
method or control implementation is added for this change.

Keyboard interruption cancels the pending pointer action. The corresponding
retirement check now requires the actual key's trusted insertText beforeinput,
rather than a delete from the former premature clear. See
[clear-default qualification](../ChromiumScrollers/clear-default-qualification.json)
and its source audit. Search notification coverage is described below. Recents, broader field
contracts and other specialized controls remain open, followed by the remaining
browser/menu/shortcut/deployment and GTK/Qt/KDE work.


### Native clear search notifications and nested edits

Chromium sends native clear notifications through its original
HTMLInputElement::OnSearch. Its original user-edit callback and incremental
attribute getter identify an already scheduled notification, preserving the
engine's timer and event behavior without adding a second event. Attribute
changes from input handlers are observed at the original engine boundary.
Firefox retains its original absence of this search event. The shared native
control implementation and API 1/592 are unchanged.

Native proposal ranges must stay with their own edit. Chromium tracks DOM
dispatch context; Firefox distinguishes its native delete action from nested
script delete actions through the existing guarded editor entry point. Page
scripts keep their original ranges even when they edit during a cancelled
beforeinput. Validation, undo and event creation remain in the original engine.

See [search notification qualification](../ChromiumScrollers/search-notify-qualification.json)
and its source audit for measured coverage and remaining scope. The engine
reference uses appearance:none and a real original select-all witness; native
field images remain compared with independent GNUstep controls. Recents,
broader editing/style/zoom/IME/accessibility contracts, other
specialized controls and complete browser/derivative/menu/shortcut/deployment
work remain open, followed by GTK/Qt/KDE through the shared native library.


With a capable provider, webpage text/password/search/URL/telephone/email
placeholders use the existing native field cells through shared operation 54.
The optional provider method preserves its prior ABI prefix; older providers
retain the earlier binding. Blink's original `StrippedPlaceholder` and Gecko's
original attribute/newline helpers supply canonical text. Native cells own its
font, geometry, visibility and rendering; no component is copied into either
adapter. Browser address bars, toolbars and tabs remain original.

See [paired placeholder qualification](../../Libraries/NativeUI/placeholder-qualification.json).
Multiline placeholders, recents, broader styling/layout/zoom/IME/accessibility,
other specialized controls and complete browser/derivative/menu/shortcut/
deployment requirements remain open, followed by GTK/Qt/KDE integration.

The combined Chromium text/search/placeholder run retains an unresolved
disabled-field repaint mismatch after 299 passing checks. Its focused
placeholder run passes, and Firefox passes the combined run. The shared
provider/transport qualify their measured contracts; complete Chromium
placeholder integration is not claimed until that failure is resolved.


### Native color inputs

`NEXTSPACE_CHROMIUM_COLORS=1` opts the exact guarded Chromium build into the
shared NSColorWell/NSColorPanel binding. Browser toolbars, address bars and tabs
remain original. The adapter calls Blink's existing chooser/parser/model/event
boundaries; the shared bridge owns only typed color data and native picker
lifetime. It adds no widget implementation or browser rebuild.

The focused suite is `check-button-sizing.py --fixture <owned-fixture>
--colors-only`. It passes 16 checks and six complete native images, including
real native wheel selection, trusted input/change, cancelled clicks, disabled
controls, script updates, owner retirement, one shared panel and original
keyboard activation. See [qualification](color-qualification.json) for exact
binaries and limits. Firefox color binding, wide-gamut/alpha coverage, pointer
feedback/dragging, suggestions/eyedropper, native palette ownership behavior,
host recovery, broader scales/styles/accessibility and deployment remain open.


The shared color ownership extension also supports Firefox's process split
without creating another native well. Chromium retains its existing direct
well binding and passes the expanded 17-check/six-image color cohort against
that same bridge. Original browser chrome stays unchanged. Shared action
receipts prevent application model sync from becoming a synthetic user edit.
See [shared ownership qualification](../../Libraries/NativeUI/color-owner-qualification.json).
