# Shared native UI provider

The goal is to make whole non-GNUstep applications look and behave native in
NEXTSPACE, including GTK, Qt/KDE and browser applications. Scrollbars are the
starting integration, not the acceptance criterion. Controls, detached menus,
editing, focus, shortcuts and dialogs must use the shared native UI library.
See the [application-wide scope and coverage](../../docs/Native-Control-Integration.md).

Browser toolbars, address bars and built-in tabs remain unchanged in the current
integration. Future requested changes to those components belong in optional
browser-specific patches above the shared bridge. Those patches must consume
the same native provider used by webpage controls and subsequent GTK/Qt/KDE
adapters, so changes to native controls stay in one UI library.

The optional [session host](Host/README.md) now starts through the user launcher
and supervisor when installed. It reuses the shared bridge and this provider,
with no copied control implementation. Its staged session checks and remaining
deployment gaps are recorded in the
[recovery qualification](../../Applications/Session/native-ui-recovery-qualification.json).
The supervisor retains original browser connections and owner capabilities
across host loss; adapters reconstruct native objects from live application
models without copying controls or replaying actions.

The pinned Firefox viewport binding now consumes the same native text geometry
and scrolling API as Chromium. Its engine frame uses native clip/document
measurements, and its real scroll setter retains DOM events while native
`NSScrollView` supplies pixels and arrow tracking. This adds no UI-library,
provider, loader or protocol implementation. See the scoped
[Firefox viewport qualification](../../Experiments/FirefoxNativeUI/viewport-qualification.json).
Its optional wheel binding also reuses the existing native responder operation,
including pages without wheel listeners. Page cancellation and Firefox's APZ
acknowledgement remain in the adapter; AppKit supplies scrolling behavior. See
the [Firefox wheel qualification](../../Experiments/FirefoxNativeUI/wheel-qualification.json).

The bridge and the underlying UI implementation are separate libraries:

- `libnextspace-native-ui.so.1` loads a provider and forwards the C API. It has no
  GNUstep, GTK or Qt dependency and implements no controls.
- `libnextspace-native-ui-gnustep.so.1` binds that API to the installed GNUstep
  controls. It creates ordinary `NSTextField`, `NSSecureTextField`, `NSButton`, `NSSlider`, `NSProgressIndicator` and
  `NSScroller` objects and calls their drawing and input methods. The shared
  view host supplies offscreen backing and event dispatch, with no control
  drawing, geometry or tracking algorithms.
- Optional radio groups use one actual `NSMatrix` with retained `NSButtonCell`
  objects. Stable IDs, selected/key identities and action counts are separate
  application data. Native methods own sizing, drawing and input. The optional
  group methods start at byte 480; optional cell sizing and backing-density
  access extend ABI 1 to 520 bytes without changing existing offsets. Older
  providers retain their supported capabilities. See the original
  [provider qualification](radio-group-qualification.json) and subsequent
  [transport qualification](radio-transport-qualification.json).
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

The shared [radio transport](Bridge/Radios.inc) carries models, exact selected/key
IDs, action snapshots and native member geometry. Member images crop the actual
matrix backing using its native cell rectangles. Application field dimensions
go through native `NSMatrix setCellSize:`; adapters do not recreate grid layout.
Native preferred metrics remain available separately. Invalid models or oversized
native geometry preserve the prior model, selection and key context. The helper
warms controls at `nxs_control_backing_scale()` rather than assuming a 1x display;
the getter returns zero with providers predating that optional API. The shared
[group binding cache](Bridge/RadioBinding.inc) retains only application models,
native state and host epochs. Both pinned browser adapters now use that cache
and the same member paint/pointer serializer. Chromium supplies original weak
DOM node IDs; Gecko retains original engine nodes and assigns opaque binding IDs.
Each engine supplies its original group membership, focus and trusted activation.
See the partial [Chromium](../../Experiments/ChromiumScrollers/radio-group-qualification.json)
and [Gecko](../../Experiments/FirefoxNativeUI/radio-group-qualification.json)
qualifications. Complete pointer/label behavior, layout topology, browser scaling
and group recovery through the session supervisor remain unfinished.

The optional wheel extension appends one function to ABI 1 (416 to 424 bytes
on ARM64). Query `nxs_control_wheel_capabilities()` before calling
`nxs_control_wheel()`. Its size-tagged 40-byte event carries top-left control
coordinates, physical modifiers and unaccelerated surface distances, positive
right/down. The GNUstep provider accepts multiline and flat-list controls, performs
native hit testing independently of keyboard focus, applies the native mouse
multiplier and dispatches to the actual responder. `NSScrollView` supplies
scrolling policy and clamping. Busy, invalid and unsupported input returns zero;
older providers advertise no wheel capability. Keyboard capabilities and prior
by-value viewport/geometry APIs are unchanged. Independent native-reference,
transport, browser and compatibility checks are recorded in
[wheel-qualification.json](wheel-qualification.json).

The API supports native push buttons, checkboxes, radio buttons, sliders,
progress indicators, popup buttons/menus, single-line text/password fields,
multiline text areas, flat lists and the existing scrollbar contract. Normal/disabled state,
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
another native input dispatch, is rejected. Browser text/IME integration, default-button
command models, application menu integration, offscreen keyboard activation animation and
application focus traversal still need their broader integration contracts.
The pinned Chromium experiment now applies next/previous requests through its
real focus controller; other application integrations remain open.

The optional input, event, range, popup, text and descriptor-source functions extend ABI version 1. The loader validates
the original `NXS_NATIVE_UI_CORE_SIZE` prefix and checks the advertised structure
size before reading optional fields. Older providers keep their original
controls and report no input capabilities. An older loader/client can also use
the new provider unchanged. This preserves the separation while the API grows.

This is an initial implementation of the shared host, not full browser support.
Browser text editing, broader engine/frontend focus and keyboard routing, IME, accessibility,
general application menus, lists/trees, tabs,
and engine/frontend adapters for the new control types remain to implement.
The provider ABI is under development until that broader contract is qualified.

## Native multiline editor

`NXS_TEXTAREA` creates an ordinary `NSTextView` inside an ordinary `NSScrollView`.
GNUstep supplies wrapping, selection, line navigation, insertion, undo, scrollbar
placement and tracking. The provider forwards its existing text model, pre-edit
and command contracts to that editor. It adds no text layout, key-binding or
scrollbar implementation. Composite drawing uses native recursive backing;
focus goes to the document view and native hit testing selects its subviews.

`NXS_TEXT_MULTILINE` is advertised through an optional append-only provider
capability query. `NXS_TEXT_VIEWPORT` additionally exposes the native document
and visible rectangle through `nxs_control_text_viewport()`. The scroll operation
uses `NSClipView`'s existing constraint and scroll methods. These are native
geometry and scrolling interfaces for adapters, without copied layout rules.
The ABI remains version 1; an older provider rejects the new kind and reports
neither capability. Existing single-line/password clients keep their prefix.

`NXS_TEXT_GEOMETRY` adds the native clip frame, client size before scrollers,
and minimum/maximum scroll points through `nxs_control_text_geometry()`.
The provider reads `NSScrollView` metrics and `NSClipView` constraints. Callers
initialize the output struct's `size`; unavailable/older providers return zero.
This appends one optional function pointer (408 to 416 bytes on ARM64), leaving
the existing by-value viewport struct and operations 32/33 unchanged. Transport
operation 34 returns the size-tagged geometry only to the owning connection.

External text editors veto the local native edit to avoid inserting twice, then
echo their canonical text and selection. For a focused textarea, the provider
finishes the native caret reveal when that next model actually changes. It calls
the existing `NSTextView` `scrollRangeToVisible:` method; there is no caret or
line-layout calculation in the bridge. An unchanged veto clears the pending
reveal, and subsequent unrelated programmatic updates keep their old behavior.
The API and ABI do not change.

Both browser adapters retain the busy native editor during reentrant engine
layout/paint callbacks, then echo its resulting viewport through their existing
engine scroll setters after key handling. Rebinding during the callback would
discard the very native editor whose edit is awaiting an engine decision.
See the [caret qualification](caret-qualification.json) for native key sequences,
complete images, cancellation, rapid input and host replacement checks.

Full short, scrolling and wrapped images match independent direct GNUstep
references. Tests cover actual scrollbar clicking, double/triple-click selection,
native line navigation, newline/Tab insertion, UTF-16 selection, pre-edit veto,
read-only/disabled state and reentrant transport. The unchanged pinned Chromium
and Firefox builds also have experimental multiline drawing and engine editing
bindings, including real-seat keyboard checks across host replacement.
The pinned Chromium adapter additionally connects native geometry and offsets to
Blink's real scroll area. Twelve complete browser textarea images match provider
output across scroll positions, resizing, wrapping and host replacement. Native
arrow tracking and DOM scroll events also pass. This remains a separate opt-in
experiment. Both pinned adapters now bind textarea viewports and wheel input to
the shared native scroll view. Long vertical/wrapped caret navigation and typed
insertion now also use its viewport; root scrolling, pointer autoscroll, richer
edit/async-command cases, wrap modes, IME
and broader frontend coverage remain unfinished. See the
[multiline qualification](multiline-qualification.json) and
[viewport qualification](multiline-viewport-qualification.json).

## Native application menu foundation

`nxs_native_ui_menu_capabilities()` advertises the optional `NXSMenu` API.
`nxs_menu_items()` copies application-supplied titles, opaque command IDs,
parent indices, separators, state and native key-equivalent metadata into real
`NSMenu`/`NSMenuItem` objects. The provider supplies application validation and
execution callbacks. GNUstep retains drawing, sizing, submenu attachment, hit
testing, highlighting, key matching and tracking. There is no standard-command
or shortcut table in the bridge. Menu key modifiers name native Command,
Control, Alternate and Shift roles; the existing shared event conversion reads
the user's GNUstep physical-key preferences.

`nxs_menu_show()` installs and displays a detached native main menu, or hides
and uninstalls it. An unrelated existing main menu is preserved. The key API
works while hidden, and focused native controls consult the application menu
before their editor menu. `nxs_menu_state()` reads actual native window/item
geometry. Its index is a flattened model index, with -1 selecting the root.
Submenus use the backend's ordinary popup surfaces. The menu's pump keeps the
embedding application responsive during native tracking without taking events
from the menu's loop. Model changes, hiding, destruction and competing control
input are rejected while tracking. A native menu restoring its logical key
window cannot map a private editor backing window.

The original menu extension grows the API from 304 to 352 bytes on ARM64 while
retaining ABI 1, input 3, pointer 1, text 7 and command 1. Older providers report
no menu support; older loaders and clients retain their existing controls. The
[qualification](menu-qualification.json) records fourteen physical-window and
complete-image checks against direct AppKit menus, the native-control/transport
suite, thirty unchanged legacy images, and fresh Chromium/Firefox command
regressions. `Tests/NativeUI/check-menus.py` drives an isolated compositor and
compares unaltered root/submenu captures with direct native references.

The optional `NXS_MENU_CANCEL` capability appends `nxs_menu_cancel()` at byte 352,
growing the API to 360 bytes. It suppresses commands, closes the menu's native
windows and releases its native tracking loop, including during an application
callback. Destruction still waits for tracking/callbacks to return. Providers
with the earlier 352-byte API retain `NXS_MENU_MODELS` without cancellation.
Application callbacks enter the same pump scope as native tracking, so nested
event dispatch cannot start another native input operation before returning an
outer validation RPC.

The optional `NXS_MENU_LIFECYCLE` capability appends two functions, growing the
ARM64 API to 376 bytes without changing ABI 1 or earlier offsets.
`nxs_menu_lifecycle()` registers balanced open/close callbacks while the menu is
hidden. `nxs_menu_branch_items()` replaces an invisible branch's children,
including from its own WILL_OPEN callback before native sizing. Other mutations
remain forbidden while tracking. Non-separator items, including submenu parents,
need unique nonzero opaque IDs; flattened indices can change after replacement.
The provider adds lifecycle calls around inherited `NSMenuView` attachment and
`NSMenu` display/close methods. GNUstep continues to implement the controls.
`Tests/NativeUI/check-menu-lifecycle.py` compares lifecycle-enabled root/submenu
pixels with the original eager native menus, then exercises lazy/nested
preparation, rejection, cancellation and compatibility with the 360-byte provider.

Full model updates preserve the GNUstep root menu, its native window and its
main-menu association. Items are staged and validated before replacing the root's
children through ordinary NSMenu APIs; existing child menus close first. This
avoids losing an arriving pointer press while recreating the root surface.
The physical menu check verifies that the compositor window ID stays unchanged.

The shared browser helper now transports menu models and owner callbacks. It
advertises menu transport in bootstrap part 5.height only when cancellation is
available. Operations 24–30 register callbacks, replace model data, show/hide,
send a key, read native state, destroy and cancel. Models carry application data;
no menu drawing, geometry or shortcut implementation crosses this boundary.
The existing authenticated owner subscription supplies descriptor wakeups and
process lifetime. Peer loss, expired callbacks and owner exit cancel native
tracking and defer object destruction until the native stack unwinds.

`native_callbacks_dispatch()` drains callbacks on their registering UI thread
when its owner loop wakes without an outstanding RPC. Before running an idle
menu callback, the transport acknowledges its pending request sequence, or zero
when idle. The helper defers that request's reply while nested RPCs run. A
one-way resume also handles endpoint replacement inside a callback. Already
queued RPC replies take priority over later callbacks. A worker holding the
request mutex cannot prevent the UI thread from acknowledging its callback.
These are transport rules; application command semantics remain in its model.

The [transport qualification](menu-transport-qualification.json) records eighteen
physical menu/reference checks and eighteen real-helper transport/lifetime
checks, including controlled pending-reply and worker-lock races. Reopening a
submenu also exposed a Wayland retained-image attachment bug. The shared
backend marks that image for attachment after the recreated surface's first
configure; direct AppKit and provider submenus both remap in the private build.

Browser menu-model extraction and binding this idle dispatcher into each
browser's owner loop remain required. Complete browser menus, browser Undo/Redo
routing, broader live model/torn-off behavior, IME, accessibility, scaling and
other toolkit bindings remain required.

## Native text editor foundation

`NXS_TEXTFIELD` and `NXS_PASSWORD` create the installed `NSTextField` and
`NSSecureTextField` with their actual native field editors. Query
`nxs_control_text_capabilities()` first. `nxs_control_text_sync()` supplies a
NUL-terminated UTF-8 application value, editability and selection in native
NSString/UTF-16 units. `NXS_TEXT_NO_SELECTION` leaves selection to the editor.
An unchanged value does not reset editing. Synchronization emits no user edits
and is rejected during native dispatch, preventing a model update from aborting
the editing operation currently on the stack.

`nxs_control_text_get()` returns the required UTF-8 buffer size including NUL,
and optionally reads the actual selected/marked ranges and editor state. A small
buffer is left empty rather than receiving a partial UTF-8 string. The caller
owns the copied value, including password values needed by its application
model; transport diagnostics omit all text payloads. `NXS_TEXT_CHANGED` comes
from the native editor's change notification. Native Return invokes the existing
`NXS_ACTIVATE` callback; native Tab/backtab requests the application's focus order.

The provider uses the existing native editor menu for Cut, Copy and Paste.
`NSMenu performKeyEquivalent:` owns shortcut matching and validation, and
AppKit resolves its nil-target actions through the logical native key window.
No shortcut table or editing/clipboard implementation is copied. The actual
native caret timer invalidates its existing backing; the host exports that
invalidation and reads the native pixels. Text field backing stays unmapped.
Current text snapshots require the backing scale itself; other requested scales
return an empty bitmap rather than resampling text.

The private ARM64 tests verify plain/password selection, deletion, Unicode,
Control+A/E, Alt+C/V and Alt+X, password copy protection, native Return,
read-only/disabled state, caret pixel changes and deferred destruction. Thirty-nine
helper transport checks include four complete images compared with direct
native-provider references. The existing Chromium input fixture passes 62
checks and Firefox range fixture passes 57 checks with the new provider.
Old clients/loaders and a provider without the optional text extension also
pass compatibility checks; all 30 legacy scrollbar images are unchanged.
See [text qualification](text-qualification.json) and
[source audit](text-source-audit.json).

The optional `NXS_TEXT_COMMAND` capability adds `nxs_control_text_command()`.
It reads the actual selector already interpreted by the native editor/menu,
including commands such as `copy:` that produce no text mutation. The embedding
application can then invoke its own semantic action. The provider adds a selector
getter; it adds no editor or shortcut implementation. IPC operation 21 exposes
the same borrowed selector as a copied UTF-8 payload.

This extension preserves ABI version 1 and all existing offsets. The ARM64 API
size grows from 280 to 288 bytes. Old providers return no command capability,
and old loaders/text clients continue to work with the new provider. Forty-two
text transport checks, the pre-edit/reentrant suite and thirty unchanged legacy
scrollbar images pass. See [command qualification](text-command-qualification.json).
Command reporting does not supply external menu availability: a native editor
whose local history is empty disables Undo even when an embedding application
has its own history. Native undo/redo routing still needs that integration.

The optional [pinned Firefox adapter](../../Experiments/FirefoxNativeUI/text-qualification.json)
now connects plain/password webpage fields. The optional
[Chromium binding](../../Experiments/ChromiumScrollers/text-qualification.json)
also connects their complete drawing and native keys to real Blink transactions.
Web-editor clipboard/IME and broader frontend command integration remain open. Engine edits must
retain beforeinput cancellation, trusted events, validation, selection, undo,
composition and application command behavior. Multiline/rich text, IME, undo
menu routing, other scales, drag/drop and accessibility
still require integration and qualification. Browser adapters must consume the
shared editor rather than reproducing its behavior.

The pinned Firefox binding also uses the existing native tracking API for
single-click, Shift-click and selection-drag behavior. Pointer hit testing,
selection ranges and selected pixels come from the actual native editor.
The optional click-count extension below adds word/line selection. Selected-text
data dragging, context menus and long-field scrolling remain unqualified; this
is not complete text-pointer integration.

### Native click metadata

`nxs_control_pointer_capabilities()` advertises `NXS_POINTER_CLICK_COUNT`
separately from focus/keyboard capabilities. `nxs_control_track_clicks()` passes
the embedding application's positive click count into the existing `NSEvent`.
The actual GNUstep field editor implements word/line selection and dragging;
the bridge contains no click aggregator, word boundaries or selection rules.
Move/release use the existing API and retain that gesture's click count.

The optional function appends to ABI version 1: the ARM64 table grows from 288
to 296 bytes, preserving every existing offset. Older providers advertise zero
pointer capabilities; a count of one delegates to their original tracking
entry point, while larger counts are rejected. Existing clients and loaders
continue to work with the new provider. Focus/keyboard capabilities remain 3.
The shared helper advertises pointer capabilities in bootstrap part 5.x and
accepts operation 22 using the existing request layout, with the count in
`state`. Busy/disabled controls and invalid counts are rejected.

The pinned Chromium address field, Blink plain/password fields and Gecko
plain/password fields consume this extension. Other builds, frontends and
controls still require qualification. See [click-count evidence](click-count-qualification.json).

Fractional text bounds require an integral native backing, while preserving the
actual view's logical bounds. Before recursive text display, the host clears
the covered backing through AppKit; otherwise repeated native draws accumulate
alpha at the fractional edge. The actual native bitmap readback supplies pixel
dimensions, including half-unit rounding. No border or editor is drawn by the
host. `native-backing-probe` checks 30 identical redraws across six plain/secure,
integer/fractional cases. The previous provider reproduces the edge drift.

The optional pinned Firefox frontend binding also consumes these same editors.
Its address-field qualification covers complete native images, native keys,
pointer selection and real engine edit events. Clipboard/application commands,
automatic focus restoration, resize-image parity and broader browser UI remain
open. See [frontend evidence](../../Experiments/FirefoxNativeUI/frontend-qualification.json).

### Native proposals before an edit

The optional `NXS_TEXT_FILTER` capability adds `nxs_control_text_filter()`.
Its callback receives the actual native editor's replacement range, current
selection, UTF-8 replacement and interpreted command selector. A zero return
vetoes the operation before native text mutation and undo registration. Direct
insertion has no command selector. Native Emacs commands and the existing
Cut/Paste menu supply their own selectors and ranges; the bridge supplies no
key table or deletion algorithm. The provider forwards other editor delegate
methods and notifications to the original `NSTextField` delegate.

An owner may read native state during validation. Replacing the model, changing
the filter or destroying the active editor is rejected/deferred. Focused model
updates rebind the delegate after native editor replacement, and removing the
filter restores the native delegate. Refocus retains GNUstep's own select-all
policy; owners can explicitly synchronize a different application selection.

Browser transport operations 19/20 register/unregister a separate connected
Unix SEQPACKET endpoint for an existing kernel-owned process subscription.
The native editor waits for its owner's decision while AppKit and other
requests remain serviceable. The shared C transport releases its request mutex
during validation and reacquires it before sending the decision, allowing
nested queries and another process's request without consuming the pending
outer reply. The proposal has separate storage from borrowed reply buffers.

Disconnected or expired validators veto edits. Expiry currently uses the
existing two-second RPC budget and requires explicit removal/re-registration
to resume validated editing. Late decisions after frame destruction are
consumed outside the native callback so they cannot continuously wake the
native run loop. Keyboard-dispatch ownership is distinguished from an active
mouse gesture when cancelling a deferred destruction.

The native tests cover vetoed/accepted insertion and deletion, Cut cancellation,
Paste proposals, Unicode, plain/secure fields and delegate restoration. The initial C
transport fixture verified six proposals, twelve nested reads, six rejected
nested model replacements, another process's request during validation,
disconnect, expiry, destruction during validation and idle behavior afterward.
The older text client/loader still runs with this provider. That filter
checkpoint occupied 280 bytes on ARM64. See
[filter qualification](text-filter-qualification.json).

This callback supplies the boundary used by the pinned Firefox text adapter.
The engine must preserve its actual insert,
delete, paste, validation, undo and composition transactions, handle script
mutation/reentrancy and reconcile its canonical result with the native editor.
Long-running browser scripts and modal editing flows remain unqualified. The
[pinned Firefox text audit](../../Experiments/FirefoxNativeUI/text-source-audit.json)
records the guarded boundaries and explains why its autocomplete-style value
setter cannot substitute for normal user editing.

### Application command ownership

`nxs_control_command_filter` optionally lets an application validate and execute
selectors chosen by the actual native menu or responder. The callback receives
`NXS_COMMAND_VALIDATE` or `NXS_COMMAND_EXECUTE`: return -1 to retain the original
native behavior, zero for an owned disabled/rejected command, or one to enable
or execute it. Unknown actions keep their original native target and validator.
The native menu still owns items, key equivalents, matching and dispatch. No
application shortcut table, clipboard implementation or control is duplicated.

This matters when an offscreen editor cannot import the focused application's
Wayland clipboard. Native Paste validation would otherwise consult empty helper
storage and reject valid application data. The host routes native menu target
validation through a forwarding object, and the native editor's command delegate
through the same callback. The application executes its own existing command
and the host suppresses a second native action. Changes/destruction during the
callback follow the existing deferred-dispatch rules.

The append-only ARM64 API grows from 296 to 304 bytes while retaining ABI 1 and
the previous input, pointer and text capability values. Command support has a
separate `nxs_control_command_capabilities` query. New loaders reject the optional
filter for older providers; unchanged earlier clients/loaders remain usable.
The direct native probe and shared transport probe cover application validation,
native fallback, secure Copy restrictions, nested queries, mutation rejection,
peer loss, expiry, frame destruction and idle behavior afterward. This supplies
no new menu items or undo shortcuts. A mixed-reply probe verifies that an older
command decision cannot cancel a newer edit; the isolated earlier helper fails
the same probe. See
[command-filter qualification](command-filter-qualification.json).

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

An application may have a selected value that is absent from its visible menu.
Query `nxs_control_popup_title_capabilities()` and use
`nxs_control_popup_title(control, title)` for its independent display title.
The provider calls ordinary `NSPopUpButtonCell` `setUsesItemFromMenu:NO` and
`setTitle:`. It adds no fake menu item and changes neither selection nor menu
labels. `NULL` restores the native selected-item title; `""` is a real empty
override. Model replacement preserves this mode until the application restores
it. Invalid UTF-8, an open menu and native tracking reject mutation atomically.
Programmatic title updates emit no user action.

This optional method appends to ABI 1 after the existing 472-byte prefix,
making the table 480 bytes on ARM64. Its separate capability query preserves
the existing `NXS_POPUP_ITEMS` value for older clients. A new loader safely
reports title support unavailable from an older provider. The previous loader
and popup client remain usable with the expanded provider.

At the actual screen density, popups use the same native backing/readback path
as text controls. This preserves native image positioning at 200 percent; the
older inverted offscreen canvas displaced the popup arrow by one device pixel.
The existing arbitrary-density image path remains available for legacy callers
requesting a different scale. This does not qualify browser zoom or every
fractional-scale mode. No image, control or menu drawing algorithm is added.

`Tests/NativeUI/check-tabs.py --popup-title` reuses the ordinary-desktop capture
harness for popup titles at 100 and 200 percent. It compares complete control
images and native preferred sizes, exercises selection/cancellation and tests
older provider/client/loader compatibility. `Tests/NativeUI/run.py --transport`
also checks title changes and ownership through the shared IPC helper.
The [component qualification](popup-title-qualification.json) records 210 check
rows, 24 complete native images and all 35 existing suite sections. The
[source audit](popup-title-source-audit.json) records the shared implementation
and unchanged runtime dependencies. Browser hidden-option binding remained open
at that checkpoint.

The subsequent [browser model qualification](browser-popup-model-qualification.json)
binds that existing title method and the shared row transport in both engines.
It covers groups, hidden selections, disabled data, separators and original
index mapping through actual native input. It adds no provider or UI-library
implementation. Native intrinsic sizing and complete browser coverage remain open.

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
the table at that checkpoint 256 bytes. Query `nxs_control_popup_open_capabilities()` first.
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

## Native menu key queries

The optional `NXS_MENU_KEY_QUERY` bit advertises `nxs_menu_key_query`. It uses
GNUstep's existing `NSMenu` matching and validation while suppressing the
menu-view actuation/highlighting step. Normal execution uses `nxs_menu_key`
unchanged; disabled matching commands still consume their keys as native menus
do. This permits an embedding to ask whether a native command exists before
waiting for web content to cancel it, without copying key policy or controls.
The append-only API is 384 bytes on ARM64, ABI 1, with menu capability mask 15.
The new loader safely reports query unsupported for the preceding 376-byte
provider. See the [global-key qualification](../../Experiments/DBusMenus/global-key-qualification.json)
for provider, native pixel, transport and pinned Firefox command-boundary checks.

## Menu-only application activation

The shared Wayland backend uses application protocol v9 to forward AppKit's
existing explicit main-menu activation when an app has no key/main document.
Ordinary mapping and pointer clicks do not initially activate the menu, and
an ordinary document remains the preferred focus target. NativeUI sets
`GSSuppressMenuActivation` before creating its host application, so menus that
represent a browser do not take the browser's keyboard focus. There are no
application-name rules or copies of native menu/key behavior in this path.

The [activation qualification](menu-activation-qualification.json) records 136
passing protocol, actual desktop and direct-native checks: native icon activation
and Quit without a document, proxy title/submenu input, browser focus and host
replacement. It also retains 153 whole-control desktop comparisons and four
complete native-menu comparisons. Browser/AppKit binaries and the public
NativeUI ABI remain unchanged. Custom Workspace placeholder icons, cross-desktop
menu-only activation and the wider application/control matrix remain unqualified.

## Shared browser window frames

The browser launchers' optional `--native-frame` setting uses the browsers'
existing system-decoration paths through [`Bridge/browser_frames.py`](Bridge/browser_frames.py).
Chromium requests xdg server decoration; the recorded Firefox GTK3 runtime uses
the older KDE decoration protocol. The compositor resolves both through its
existing shared frame, rendering and input implementation. NativeUI controls,
browser hooks and browser binaries are unchanged.

The [frame qualification](browser-frame-qualification.json) records 162 passing
browser/protocol checks, including drag, Escape rollback, shade/unshade, resize,
fullscreen, minimize and close. All 153 Firefox whole-control desktop comparisons
and Chromium menu recovery comparisons pass. Independent legacy-protocol titles
equal the existing xdg titles; the existing five-density frame regression also
passes. Browser mixed-DPI, tabs/toolbars, remaining controls, derivatives and
installed-profile/deployment integration remain unfinished.

## Shared native tabs

`NXS_TABVIEW` owns an ordinary GNUstep `NSTabView` and `NSTabViewItem` objects.
The optional `NXS_TAB_ITEMS` capability adds model replacement, state and native
item rectangles. Application models supply unique nonzero 64-bit identities,
UTF8 titles/tooltips and selection. Programmatic updates emit no user action;
native pointer selection emits `NXS_VALUE_CHANGED` with the selected index.
Native items survive reorder/title changes. Empty models use selected ID zero.
The tabs extension retains ABI version 1 and first extended its table to 448 bytes on ARM64.
Earlier providers safely report no tabs capability.

AppKit supplies `minimumSize`, `contentRect`, cached `_tabRect`, drawing and
selection. Item rectangles describe the latest native draw, in logical units
with a top-left origin. GNUstep's tab view does not itself accept first responder;
the bridge preserves that behavior. It clears the outgoing native key-view link
before removing a selected item, avoiding a stale pane during empty/restore.

The shared host transports models and 64-bit selected IDs without control code.
Models/configuration are rejected while input is pending or tracking. Responses
use the existing bitmap/memfd channel, including requested 1x/2x density. A thin
draw scope supplies the temporary cache window's actual embedding density;
AppKit retains all image representation and cache policy.

The [tab qualification](tab-qualification.json) records 89 direct/compatibility
checks, 66 transport checks and twenty complete ordinary-desktop/native image
comparisons. Both existing browser desktop suites and all 35 NativeUI regression
sections pass with the updated library. That receipt qualifies the foundation.
The later [Chromium tab-container binding](../../Experiments/ChromiumScrollers/tab-qualification.json)
and [Firefox tab-container binding](../../Experiments/FirefoxNativeUI/tab-qualification.json)
use the same control and shared client serializer. Complete browser tabs/toolbars
and the remaining application-wide requirements are unfinished.

Browser embedding also exposed an empty-pane invalidation that the foundation
had not checked. Native tab items create ordinary `NSView` panes, whose
`drawRect:` is guaranteed empty. The host acknowledges those no-op pane displays
after drawing the parent; control subclasses keep their own dirty flags. The
updated probe requires native drawing to consume invalidation and retains all
ten full 1x/2x ordinary-desktop comparisons. AppKit rendering remains unchanged.


## Shared native toolbar foundation

`NXS_TOOLBAR` embeds the ordinary `NSToolbar` representation and its original
`NSToolbarItem` buttons, spaces, separators and overflow menu. Application models
supply opaque nonzero `uint64` IDs, labels, tooltips, native image names and
availability. AppKit owns layout, preferred height, clipping, validation, hit
testing, highlighting and tracking. Native target/action reports the current
ordered index through `NXS_ACTIVATE`; `toolbar_state.command` retains the exact
64-bit identity. Model updates emit no action and reject invalid data atomically.
Native action items retain their identity across reorder/title changes.

Three optional methods append to ABI 1, making the table 472 bytes on ARM64.
Earlier providers report no toolbar capability. Earlier 448-byte tab clients and
loaders remain usable with the expanded provider. Native visible-item and open
menu rectangles use control-relative logical coordinates with a top-left origin.
The host supplies pointer events to the ordinary and transient menu windows;
AppKit's existing menu implementation owns placement and selection.

Compound controls use AppKit's recursive display into their actual backing.
The Cairo backend's optional `GSReadRectAtBackingScale:` reuses its existing
readback implementation to return device pixels at the surface's density.
The original `GSReadRect:` contract stays unchanged. The provider transports
those pixels; it contains no toolbar renderer or duplicated child drawing code.
Native window invalidation tracks visible work without consuming clipped native
children's dirty flags. The shared Wayland backend acknowledges stored positions
for windows without a compositor role; their menus then agree with the actual
compositor surface position. No application identity participates in this policy.

`Tests/NativeUI/check-toolbars.py` compares four complete ordinary toolbar images
at both 100% and 200%, alongside native actions, cancellation, disabled state,
standard item types, exact IDs and empty/restore lifecycle checks. The
[toolbar qualification](toolbar-qualification.json) records the measured scope.
Toolbar IPC and browser toolbar bindings remain unfinished. This foundation does
not make either complete browser interface native; GTK/Qt/KDE integration and the
remaining browser/derivative/deployment requirements remain open.


The optional [GTK3 geometry bridge](Bridge/Gtk3Geometry.h) transports authoritative
Wayland surface origins for toolkit adapters. It uses the compositor's read-only
version-10 surface observer on the actual GDK connection and the existing GLib
idle queue. GDK owns window/display lifetime. Popup and non-Wayland windows keep
their original path; an unavailable compositor reports unavailable rather than
inventing coordinates. This component draws no controls and changes no focus,
window metadata or toolkit layout.

Build it independently with `cmake -S Libraries/NativeUI/Bridge -B BUILD` and
`cmake --build BUILD`, or enable `NXS_BUILD_GTK3_GEOMETRY` in the NativeUI build.
It links Wayland/GLib only, and resolves the public GTK3/GDK functions at use
time. It requires neither a provider nor an AppKit/browser rebuild. The existing
NativeUI public control ABI remains unchanged. See
[geometry qualification](gtk3-geometry-qualification.json) for the tested scope.


The optional semantic activation extension appends control_perform_click at
byte 520 (ABI version 1, size 528). Existing native buttons accept item ID zero;
NSMatrix accepts an existing enabled member ID. The provider delegates to original
NSButton performClick: or original NSMatrix selectCell:/performClick:. Original
native state/key-cell/action methods supply the result. The shared host guards
the native call stack against destruction/reentry, and the operation does not
move input focus or manufacture mouse/keyboard events. Earlier providers return
unsupported through the size-checked loader. IPC operation 47 enforces the
creating connection, current idle state and exact request shape. It carries the
existing typed matrix state and preserves the existing sequence field. Browser
label association/default-action rules stay in each original engine; GTK/Qt/KDE
can reuse this operation for their own semantic activation boundaries.


### Native flat lists

The optional `NXS_LISTBOX` provider binds an ordinary one-column `NSBrowser`.
Its original `NSBrowserCell`, matrix and scroll views own native drawing,
selection, keyboard interpretation and scrolling. `GNUstep/List.inc` is only
a data source and action binding. The bridge and future application adapters
supply ordered IDs, titles, enabled flags and selected data. They do not
implement a list control.

The ABI 1 extension appends five methods after the unchanged 528-byte prefix
(new size 568): model replacement, typed native state, complete selected IDs,
native row geometry and native scroll positioning. IDs retain all 64 bits.
Invalid models are rejected before mutation; unchanged models retain native
cell/key context. Model replacement emits no action, and tracking/callbacks
reject model mutation and destruction. The original native scrollbar remains
interactive when rows are disabled. Pointer preparation uses the actual native
backing density. Older providers return unsupported through the size-checked
loader, and existing clients keep their original ABI.

Independent ordinary controls receive real Wayland seat pointer/key input;
full images use a fresh ordinary native list populated from that reference's
resulting state. This avoids using accumulated transparent-cell damage as the
image oracle. See [qualification](list-qualification.json).

This is shared provider infrastructure. Browser listbox/multiple-select model/
DOM transactions, intrinsic layout, broader lifecycle, accessibility
and deployment remain work. At this provider checkpoint, browser adapters,
toolbar, address bar and tabs were unchanged. Later GTK/Qt/KDE adapters will
consume the same API.

The shared list wire uses kind 13 and operations 48–51 for models, complete
native snapshots, row rectangles and scroll position. Existing operation 35
routes wheel input; existing owned configure, draw, pointer, focus/key and
retirement paths serve lists as well. Bootstrap part 3.x advertises this wire
capability without changing old fields. Replies expose actual native backing
density, and models must use that density within the existing bitmap budget.

Snapshots preserve native primary/key/action IDs and every selected 64-bit ID,
with native viewport/document geometry. The C serializer lives in
`Bridge/Lists.inc`; radio and list callers share `Bridge/Inputs.inc` for focus
and key metadata. The host supplies no selection or scrolling algorithm.
Creating-connection checks, strict UTF8/model validation and native tracking
mutation guards apply before mutation. See [wire qualification](list-wire-qualification.json).
Pinned Gecko and Chromium model/DOM bindings consume this shared transport.
Complete browser list layout/scroll integration remains unfinished.


`Bridge/ListBinding.inc` now shares list model, snapshot, bitmap and host-epoch
lifetime across consumers. It stores application data and the original native
results; it adds no selection, navigation, layout, scrolling or drawing policy.
The first opt-in Gecko consumer reuses the existing retained select snapshot,
feeds native selected IDs into original DOM setters and sends original trusted
interaction completion. Exact ordinary native key and real-seat gesture
references cover the measured scope; see [Firefox list qualification](../../Experiments/FirefoxNativeUI/list-qualification.json).
Native row/intrinsic layout, full wheel/scroll/DOM geometry, host recovery,
scaling remain work. The pinned Chromium consumer now reuses the same binding
and shared fixture; see [Chromium list qualification](../../Experiments/ChromiumScrollers/list-qualification.json). Toolbar/address bar/tabs
remain the browsers' own components.


The optional shared scroll geometry method appends one pointer after the
568-byte provider prefix (ABI 1/576). `NXSScrollGeometry` preserves the existing
text geometry layout. Both list and text callers use one native helper to
measure the real clip frame in control coordinates, client size before
scrollers and limits returned by `NSClipView`. No scrollbar dimensions or
clamping policy are reproduced in a consumer. The original text API remains
available.

`nxs_control_scroll_capabilities` reports support through the size-checked
loader. Bootstrap part 3.y carries this capability independently of list
capabilities in 3.x; owned operation 52 returns the measurements for a list or
text area. Actual older 568-byte providers retain list rendering and reject
this optional query without changing the caller buffer. Shared ListBinding
stores geometry per host epoch and provides the same scroll/wheel plus native
snapshot/image refresh for both browser engines and future toolkit adapters.
See [scroll geometry qualification](scroll-geometry-qualification.json).

These measurements prepare browser option/layout and DOM scroll binding.
They do not by themselves complete native browser scrolling, intrinsic sizing,
wheel/default routing or host recovery. Toolbar/address bar/tabs stay original.


The optional native item query appends `control_item_at_point` after the
unchanged 576-byte prefix (ABI 1/584). The size-checked loader exposes
`nxs_control_item_hit_capabilities`; an older provider leaves the query output
unchanged. For lists, the provider uses the ordinary native view hit test,
coordinate conversion and `NSMatrix` cell lookup to return the existing 64-bit
model ID. Zero denotes a non-item area, including native scrollbars and clipped
rows. Queries do not alter selection, focus or actions. No row geometry or hit
algorithm is reproduced in an adapter.

Owned operation 53 transports this result through shared `Bridge/ItemHits.inc`;
bootstrap part 2.x advertises it independently of existing capabilities.
Independent ordinary native windows and the C-only transport client compare
hits across a grid at 1x/2x, including scrolling, disabled cells and clip edges.
See [item hit qualification](item-hit-qualification.json). The pinned Chromium
adapter now consumes this query through its original point-hit result path;
see [browser qualification](../../Experiments/ChromiumScrollers/list-hit-qualification.json).
The pinned Firefox consumer also uses this shared query through original
Gecko frame traversal and coordinate conversion; see its
[qualification](../../Experiments/FirefoxNativeUI/list-scroll-qualification.json).
Broader rectangle/list-based browser hit contracts remain separate work.
Existing browser toolbar/address bar/tabs stay original.


List operation 50 now additionally returns the existing list state/selection
payload from the same native dispatch as its row rectangle. Bootstrap part 2.y
advertises NXS_LIST_ITEM_GEOMETRY. Shared Lists.inc parses that paired metadata
so consumers can bind document rows without racing the native tracking offset.
The original part-6 rectangle remains compatible with existing clients. This
extends transport metadata, with no provider/loader ABI or UI implementation
change. The ordinary-window and C transport probes compare actual native row
rectangles and state, including an unchanged previously compiled client; see
[paired metadata qualification](list-item-geometry-qualification.json).


### Search fields

NXS_SEARCHFIELD creates the original GNUstep NSSearchField with its original
NSSearchFieldCell. It shares the existing text model, field editor, filter,
clipboard and focus bindings. NXS_TEXT_SEARCH advertises support. The optional
nxs_control_search_part query returns native search-button, cancel-button and
text rectangles; API 1's existing 584-byte prefix is unchanged, with the new
function pointer appended at byte 584 (total 592 bytes). Older providers return
no search capability and an empty part rectangle through the current loader.

The cancel observer forwards the original button target/action, snapshots its
native pre-action string/selection and offers the actual clear result to the
existing edit filter. Ordinary text-change actions do not enter that scope. An
embedding can veto the local result, run its original validation/events/undo and
echo its canonical model through the same text sync API.

NXS_TEXT_SEARCH_ACTION advertises native search-button commands. Its observer
forwards the original button target/action, then reports performClick: through
the existing application-command filter. Ordinary text changes and keyboard
Return do not enter that observer. API 1 remains 592 bytes; an older search
provider keeps editing/clear support without advertising the new action. The
shared bridge activation receipt carries only native identity, action item,
command serial and host epoch. Applications consume it after their cancellable click dispatch
and retain their original form, validation and event behavior. Recents remain
application-binding work. No widget drawing, layout, clearing or key algorithm
is reimplemented in this provider.


NXS_TEXT_SEARCH_CLEAR_COMMAND offers the original clearSearch: action through
the command filter before it runs. Returning -1 keeps the immediate original
native action; zero suppresses it; a client accepting it can commit later with
nxs_control_perform_click(control, NXS_SEARCH_CANCEL). This uses the existing
semantic activation API and keeps API 1/592 unchanged. The provider calls the
original cancel NSButtonCell performClickWithFrame:inView: using its own
cancel-button rectangle under a scoped recursion guard. The original cancel observer/edit gate still
handles the actual native result.

The browser bindings carry the item identifier in their shared activation
receipt and commit after original click dispatch. They revalidate the owner,
refresh its canonical text model, then enter the existing engine edit
transaction. Disabled, retired or focus-diverted owners do not affect a peer
field. A real key ending pointer tracking cancels that control's pending
button action. Older providers without the capability retain their fallback.
See [clear-default qualification](../Experiments/ChromiumScrollers/clear-default-qualification.json).


Search notification dispatch belongs to application bindings. The paired
browser bindings reuse the original engine dispatch/scheduling methods and
retain native edit provenance across nested script actions. No search timer,
DOM event implementation or native widget is added to this library; its API
and provider binaries are unchanged by that checkpoint. See
[search notification qualification](../Experiments/ChromiumScrollers/search-notify-qualification.json).


Plain, secure and search placeholders now use the original native cell's
`setPlaceholderString:` method. The optional ABI 1/600 method preserves the
592-byte prefix and existing text model. `NXS_TEXT_PLACEHOLDER` advertises it;
older providers reject the optional call. Shared owned operation 54 carries
UTF8 data or removal through `Bridge/TextPlaceholder.inc`, without a second
placeholder renderer, geometry rule or visibility policy. Multiline fields
remain outside this extension. Browser adapters supply their original engine
placeholder data and newline normalization.

See [placeholder qualification](placeholder-qualification.json) for ordinary
native desktop comparisons, transport ownership, compatibility and paired
browser evidence. Subsequent GTK/Qt adapters consume this same API.

The combined Chromium text/search/placeholder run retains an unresolved
disabled-field repaint mismatch after 299 passing checks. Its focused
placeholder run passes, and Firefox passes the combined run. The shared
provider/transport qualify their measured contracts; complete Chromium
placeholder integration is not claimed until that failure is resolved.


The shared provider now also hosts the original `NSStepper`, `NSColorWell`
and `NSDatePicker`. Optional ABI 1/640 preserves the 600-byte prefix and
adds capability discovery plus typed color/date models. Steppers reuse
configuration, state and increment operations. Owned operations 55–58 carry
color/date data; all three controls share the existing image/input/lifetime
transport. Color wells also use the existing semantic activation operation.

These controls render through the existing native backing store. A generic
opt-in event forwarding mode retains views whose native `mouseDown` returns
before `mouseUp`, preserving the original color well's event sequence and
color panel. Native callbacks reject reentrant mutation and destruction;
readback remains available. No stepping, date parsing/calendar arithmetic,
color-panel UI, gesture threshold or drawing code is copied.

See [specialized component qualification](specialized-qualification.json).
Browser-specific specialized-control bindings, numeric editor composition,
nullable date models, file panels and the broader app scope remain unfinished.
The prior Chromium combined-run repaint gap remains open.
