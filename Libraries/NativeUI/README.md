# Shared native UI provider

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

The initial API supports native push buttons, checkboxes, radio buttons, sliders,
determinate progress indicators and the existing scrollbar contract. Normal/disabled state,
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

The input function pointers are appended to ABI version 1. The loader validates
the original `NXS_NATIVE_UI_CORE_SIZE` prefix and checks the advertised structure
size before reading optional fields. Older providers keep their original
controls and report no input capabilities. An older loader/client can also use
the new provider unchanged. This preserves the separation while the API grows.

This is an initial implementation of the shared host, not full browser support.
Text editing, broader engine/frontend focus and keyboard routing, IME, accessibility,
menus, lists/trees, tabs, popup controls,
progress animation
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

A later repeat run timed out during one legacy probe's shutdown after writing
its bitmap. The next complete run passed; the original timeout remains an open
lifecycle issue. The verifier now captures a live backtrace if it recurs rather
than treating that run as passed.
