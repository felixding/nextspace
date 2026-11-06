# Shared native UI provider

The goal is to make whole non-GNUstep applications look and behave native in
NEXTSPACE, including GTK, Qt/KDE and browser applications. Scrollbars are the
starting integration, not the acceptance criterion. Controls, detached menus,
editing, focus, shortcuts and dialogs must use the shared native UI library.
See the [application-wide scope and coverage](../../docs/Native-Control-Integration.md).

The optional [session host](Host/README.md) now starts through the user launcher
and supervisor when installed. It reuses the shared bridge and this provider,
with no copied control implementation. Its staged session checks and remaining
deployment gaps are recorded in the
[recovery qualification](../../Applications/Session/native-ui-recovery-qualification.json).
The supervisor retains original browser connections and owner capabilities
across host loss; adapters reconstruct native objects from live application
models without copying controls or replaying actions.

The bridge and the underlying UI implementation are separate libraries:

- `libnextspace-native-ui.so.1` loads a provider and forwards the C API. It has no
  GNUstep, GTK or Qt dependency and implements no controls.
- `libnextspace-native-ui-gnustep.so.1` binds that API to the installed GNUstep
  controls. It creates ordinary `NSTextField`, `NSSecureTextField`, `NSButton`, `NSSlider`, `NSProgressIndicator` and
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
progress indicators, popup buttons/menus, single-line text/password fields,
multiline text areas and the existing scrollbar contract. Normal/disabled state,
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

Full short, scrolling and wrapped images match independent direct GNUstep
references. Tests cover actual scrollbar clicking, double/triple-click selection,
native line navigation, newline/Tab insertion, UTF-16 selection, pre-edit veto,
read-only/disabled state and reentrant transport. The unchanged pinned Chromium
and Firefox builds also have experimental multiline drawing and engine editing
bindings, including real-seat keyboard checks across host replacement.
Browser DOM scroll/layout synchronization, wrap modes, IME and broader frontend
coverage remain unfinished. See the [multiline qualification](multiline-qualification.json).

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
