# Chromium native scrollbar experiment

This opt-in prototype replaces web-content scrollbars in **one unchanged Debian
ARM64 Chromium build** with the existing NEXTSPACE `NSScroller` bridge. Only the
small preload library is compiled. Chromium, GNUstep and `NSScroller` are not
rebuilt or overwritten. Closing the isolated browser removes the memory patches.
It is not enabled by the installed NEXTSPACE session.

The helper calls the unchanged `Libraries/ForeignScrollers` C interface for
geometry, drawing and synchronous native mouse tracking. Its bitmap is transported
to Chromium's paint canvas; no native artwork or tracking algorithm is copied.
Blink retains the document layout and scroll ranges, with vertical bars placed
on the left without changing text direction. Native actions are applied through
Chromium's absolute scroll-offset setter on the owning renderer thread.

The preload patches guarded ARM64 instructions and internal vtables before the
renderer sandbox starts. A preconnected socket survives the zygote boundary;
AppKit stays in the separate helper. Chromium's compositor scrollbar press
handler returns its own unhandled result so the press reaches Blink and
`NSScroller` without starting a second compositor scrollbar animation. Wheel and
content handlers are not replaced. Native tracking stops when Blink disconnects
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
