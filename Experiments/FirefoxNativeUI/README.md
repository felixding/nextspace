# Firefox native UI integration

Current scope (2026-11-07): keep the browser's own tabs, address bar and toolbar.
Native browser-UI replacement is skipped. The shared default scope policy
ignores the earlier frontend/tab opt-in flags; related qualification below is
historical evidence. Continue webpage controls, then shared detached-menu and
native-shortcut integration, followed by GTK and Qt/KDE apps. Future toolbar or
other browser-UI changes belong to optional app-specific patches above the
shared bridge/provider layer.


This is the Gecko side of the browser-first
[native application integration](../../docs/Native-Control-Integration.md).
The current browser goal covers webpage controls, detached menus and native
shortcuts, followed by other non-GNUstep apps under the scope above.

With the existing input and popup flags, `NEXTSPACE_FIREFOX_LISTS=1` additionally
binds listboxes/multiple selects to the shared ordinary GNUstep `NSBrowser`.
The existing retained select snapshot supplies labels, identities, visibility
and disabled data. The shared ListBinding caches application/native snapshots;
original Gecko DOM setters and interaction completion preserve trusted events.
Native key/pointer tracking, focus/selection, row pixels and scrollers remain in
the UI library. Text and lists share the existing scroll-container display hook;
no second patch at that address bypasses the text adapter. The post-event boundary forwards outside
release, and original model observers schedule repaint for changed labels/text.

This opt-in is qualified only for the exact build and scale-1 fixtures. Native
option/intrinsic geometry, full wheel/scroll/DOM offsets, richer models,
recovery, IME/accessibility and derivatives remain unfinished. An independent
ordinary window confirms the same existing native cell-state artifact after
outside release; the adapter adds no workaround or copied renderer. See
[list qualification](list-qualification.json). Chromium list bindings are next;
shared components remain available for the later GTK/Qt/KDE adapters.

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

A recreated textarea binding restores the engine's retained scroll point even
when the host epoch is unchanged. The full Workspace desktop fixture's
`--menus --restart-host` sequence checks native menu commands, tab return,
application switching, held-submenu dismissal, host replacement and native
control pixels together. This catches binding-lifetime failures that a host-only
recovery test misses.

Qualification remains limited to this exact ARM64 build and scale 1 horizontal
fixtures. Other scales retain Gecko's rendering until scaled native transport
is connected. The initial binding hosts individual radio buttons; the optional
group binding described below instead uses the shared native matrix.
Indeterminate animation, remaining controls, menus, editing, IME, accessibility,
browser application interfaces and derivatives remain open.
The progress fixture retains its author-styled engine path; broader styled
interactive controls remain unqualified. This is not full native Firefox support
and is not activated outside the private test session.

`NEXTSPACE_FIREFOX_RADIO_GROUPS=1`, with native input enabled and shared radio
wire capability 3, binds each eligible original engine group to one ordinary
`NSMatrix`. Gecko's original `RadioGroupContainer` supplies the ordered members
and selection, preserving disabled/hidden members, form ownership, shadow scopes
and independent unnamed controls. Retained engine nodes have opaque binding IDs;
they are released when the canonical group changes or retires. No Gecko DOM ID
or address-reuse assumption supplies lifetime safety.

The engine-neutral `RadioBinding.inc` cache and member paint/pointer serializer
are shared with Chromium. The provider retains the actual native cells and owns
sizing, drawing, tracking and key interpretation. Original Gecko focus and
trusted click dispatch retain DOM input/change, cancellation and rollback.
Focus callbacks are followed by fresh widget, node-type and group checks before
activation. Modifier events use native `flagsChanged:`. Retiring a member frame
invalidates its peers so retained display items cannot keep an obsolete model.

The shared group fixture passes 40 checks and 15 complete native member images
in each pinned browser. Current Firefox text and popup regressions also pass.
See [radio-group-qualification.json](radio-group-qualification.json) for exact
runs and limits, and [radio-group-source-audit.json](radio-group-source-audit.json)
for original engine interfaces and guarded calls. The broader shared button
fixture exposed an existing automatic inline-flex sizing gap: Firefox reported
87.4333 CSS pixels where the native preferred width was 86. That historical
checkpoint retains the identical prior-adapter failure. The subsequent
[button sizing qualification](button-sizing-qualification.json) addresses it.

This opt-in group path currently models one native column at browser scale 1.
Complete disabled/outside-release/label behavior, other layout topologies,
browser scaling and group recovery through the session supervisor remain open.
Browser toolbar, address bar and tabs retain the current browser components.
Future requested UI changes belong in optional application patches over this
shared layer. Neither browser nor AppKit was rebuilt.

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
multiline viewport/layout integration, rich text, accessibility and broader styling remain open. Address
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
readonly and Unicode models, including drags outside the field. Dragging
selected text as data, context menus, touch and long-field
horizontal scrolling remain open. This extension changes the adapter/helper;
the qualified native provider and AppKit binaries are reused unchanged.
The [pointer qualification](text-pointer-qualification.json) records 151 browser
checks, including 50 native pointer ranges and 46 complete native images.

The subsequent optional click-count extension forwards the actual
`WidgetMouseEvent.mClickCount` into the shared native mouse event. Its offset
is checked against the pinned source and guarded compiled copy instructions.
`run-fixture.py --text --click-counts` adds native word/line click and drag
references, verifies the helper received each real click count, and retains the
existing DOM/transaction, renderer-crash and helper-loss checks. This extension
rebuilds the small provider/loader and adapter; Firefox and AppKit stay unchanged.
See [click-count evidence](../../Libraries/NativeUI/click-count-qualification.json).

`NEXTSPACE_FIREFOX_FRONTEND=1`, together with the input/text flags, adds an
optional parent-process text binding. Firefox's address field is an ordinary
HTML text input with `appearance:none`, a transparent background and fractional
bounds. The adapter retains its application model, listeners and commands. It
uses Gecko's existing display item to carry the complete native field bitmap;
the display-item boundary avoids the frontend's separate GTK painting path.
No browser CSS or control implementation is copied. Gecko's real process-role
function is evaluated at use time because child initialization can follow
libxul loading. Web fields retain their existing eligibility rules.

`run-frontend-fixture.py` creates a private compositor, profile, pasteboard and
native helper. It requires the pinned Firefox, native library, adapter, backend
and capture probe paths; `--library-path` accepts the extracted runtime library
directories. The default run invokes `check-frontend.py` and cleans up; `--hold`
keeps its owned control socket open for `check-frontend-lifecycle.py`. Only the
test profile receives `--remote-allow-system-access` for Marionette chrome
inspection. The surrounding red stripes/robot are Firefox's packaged automation
indicator, not an adapter-generated control or rendering fallback.

The retained address-field run passes 59 assertions, including 13 complete
native bitmap comparisons, nine editing commands, 16 pointer ranges and their
actual native tracking records, trusted insertion and beforeinput cancellation.
Seven lifecycle checks cover closing a window while held, retaining the first
window's model, editing after explicitly focusing its address field and typing
after held helper loss. Automatic keyboard focus restoration is not established.
The shared backing tests preserve old clients/loaders and legacy images.
Undo availability, resize-image parity, IME,
accessibility, scaling and the remaining browser controls/menus/dialogs still
require work. See [frontend qualification](frontend-qualification.json).

Native Copy, Cut and Paste now call Gecko's existing text-control command
callback. The callback finds the element's registered controller, checks its
availability and executes it. This preserves the URL bar's custom copy/cut
controller, including complete-URL formatting, and the webpage editor's trusted
clipboard events, cancellation, validation and undo transactions. NativeUI's
existing menu and editor choose the selector; the adapter contains no shortcut
table, URL formatter or clipboard implementation. The initial binding rebuilt
only the adapter.

Modifier keys use Gecko's existing key-name classifier and NativeUI's existing
modifier event. AppKit receives `flagsChanged`, rather than an empty text
insertion that could delete the current selection. Gecko retains its modifier
default actions, including standalone Alt menu activation.

`check-text-commands.py` runs against an owned `--hold` frontend fixture. It
requires that fixture's port and browser PID, its directory, the native
pasteboard probe, native TextEdit, backend name and an output directory. Its 77
checks cover physical modifier transitions, real native-application clipboard
roundtrips, the actual URL-bar controller, webpage clipboard events and
cancellation, custom clipboard data, password/read-only fields, maxlength,
engine undo and frame removal during paste. A focused native application must
import the browser's Wayland selection: reading unfocused shared GPBS storage
alone can return stale data. Input checks wait for browser DOM delivery instead
of treating compositor acknowledgment as completed application processing.
See [command evidence](text-command-qualification.json) and the
[source audit](text-command-source-audit.json).

The optional shared application-command filter also fixes Paste when the
helper has no pasteboard string. Firefox answers native menu validation through
the element's actual controller collection, then invokes its existing command
callback. A native menu action is not executed again in the helper. The shared
host API is now 304 bytes on ARM64; Firefox and AppKit remain unchanged.
`check-text-commands.py --command-filter` adds six checks for empty helper
storage, real browser paste and actual validation/execution callbacks in both
address and webpage fields, bringing that run to 83 assertions. See the
[shared qualification](../../Libraries/NativeUI/command-filter-qualification.json).
Native undo shortcuts still require the application Edit menu; the control's
default menu alone does not supply them.

The existing Firefox D-Bus menubar exporter now has an experimental path to the
shared GNUstep menu provider. `run-frontend-fixture.py --export-menus` enables it
only in the isolated profile and starts a private test bus/name holder. Pass
`--compositor` with the app-menu-protocol build and add the extracted libdbusmenu
runtime directories with `--library-path`. Menu model extraction uses the
existing exporter. One optional pinned callback binding, enabled by
`NEXTSPACE_FIREFOX_MENU_LIFECYCLE=1`, completes its internal menubar lifecycle
through Gecko's own trusted-event dispatcher. The public export fixture enables
this option. It preserves the original popup handlers and keeps the hidden
internal toolbar inactive while GNUstep menus are used, without direct DOM
attribute changes or a copied toolbar implementation.

See [the generic bridge](../DBusMenus/README.md) and the
[lifecycle qualification](menu-lifecycle-qualification.json) for native
Undo/Redo/bookmark and owner-loss evidence. Add `--shared-menus` to the export
fixture to bind that same model in the existing native field/control helper.
GNUstep then supplies application menu key matching and field editing in one
responder host. Physical Undo/Redo and Emacs navigation are qualified in both
webpage and address fields; the 83-check clipboard run also passes through the
real exported application menu. `check-shortcuts.py` and
`check-shared-host.py` live in `Experiments/DBusMenus`. The inherited registration
descriptor is separate from renderer input connections. The additional
`--menu-shell-probe PATH` fixture option uses Workspace's actual shell/menu
connections to follow focus and advertised address changes automatically.
Two-window/native-application transitions are qualified separately. The shared
fixture also enables `NEXTSPACE_FIREFOX_MENU_KEYS=1` with a provider supporting
native key queries. Its pinned global-command binding fixes the earlier
page-body Alt+T failure through Gecko's real lookup/remote-reply/execution phases.
Native matching stays in GNUstep and web keydown cancellation remains effective.
The small adapter must be built with Clang: its existing naked AArch64 wrappers
are incompatible with GCC's ignored-attribute fallback. Treat warnings as errors.
See [global-key qualification](../DBusMenus/global-key-qualification.json).
Session host startup/packaging, registrar
recovery, remaining controls and derivative qualification remain incomplete.
See [Workspace qualification](../DBusMenus/workspace-qualification.json) and the
preceding [shared-host qualification](../DBusMenus/shared-host-qualification.json).

## Experimental multiline fields

`NEXTSPACE_FIREFOX_MULTILINE=1`, alongside the existing input/text flags,
enables text areas when the provider advertises native multiline support.
The same `nsTextControlFrame` display path draws the shared `NSTextView` and
`NSScrollView`. The exact-build adapter uses textarea-specific value, editor,
post-event and controller methods. Its `TextControlState` is at offset 304;
the single-line input's state is at 352. Selection reads use the real common
`TextControlState::GetSelectionRange`, avoiding the textarea's nontrivial
`Nullable<uint32_t>` return ABI. Selection writes reuse the existing common
method. All new calls are guarded after libxul is loaded and its build ID is
verified.

The native newline selector calls `TextEditor::InsertLineBreakAsAction`; native
Tab uses the real text insertion action. The existing controller callback owns
Copy/Cut/Paste, with textarea-specific controller lookup for validation. The
engine retains trusted events, pre-edit cancellation, undo and its data model.
Neither Firefox nor AppKit is rebuilt, and no native text-control code is copied.

The [multiline qualification](../../Libraries/NativeUI/multiline-qualification.json)
records 18 real-seat checks before/after shared-host replacement. The fixture
selects the actual browser pane before content focus; `document.hasFocus()`
alone did not establish that real keys had left the address editor. Independent
cases also dismiss Firefox's original auto-hidden menu bar when Alt release
activates it, following the existing clipboard fixture. That original menu
interaction remains an integration gap. Broader wrap
modes, rich text, IME and derivative coverage are still unfinished;
multiline support remains opt-in.

## Native multiline viewport

`NEXTSPACE_FIREFOX_MULTILINE_VIEWPORT=1` additionally requires the multiline
binding, provider viewport/geometry capabilities and the exact guards in
`pinned-viewport.h`. It uses the existing shared NativeUI geometry and scrolling
API; neither that API nor its GNUstep provider needs another implementation.

The adapter binds actual `ScrollContainerFrame` scroll-port, document and range
boundaries to the real `NSScrollView` measurements. Native offsets pass through
Gecko's existing scroll setter and update path, retaining trusted DOM scroll
events. Painting reads native geometry and snapshots; offset transfer occurs
during reflow and input. The whole native border-box image includes its own
left scrollbar and tracking. No control, layout, bounds-clamping or repeat
algorithm is copied into the adapter.

Gecko's hidden editor can otherwise reveal its differently laid-out caret after
a value/selection update, replacing the requested native offset. Only the
Selection belonging to an owned native textarea suppresses that second scroll;
the original queued-event lifetime and cleanup remain intact. The actual
`NSTextView` owns native selection scrolling. The following caret binding covers
long vertical/wrapped navigation and typed insertion; scrolling ancestor pages
still need dedicated qualification.

Host replacement restores the retained engine scroll model into the recreated
native object once per host generation. The adapter retains semantic nodes and
revalidates the live widget after engine scrolling. Frame removal, reinsertion,
unsupported zoom and restoration are covered by the viewport fixture. Unsupported
scales retain the engine viewport; this is not native HiDPI support.

See [viewport qualification](viewport-qualification.json) for complete native
images, geometry, resize/wrapping/autohiding, native arrow click/repeat/release,
trusted events and host recovery. These checks use the unchanged pinned ARM64
build, software/headless Wayland and 100% scale. Root
document scrolling, horizontal/nowrap text, IME/accessibility, other browser
interfaces and derivative builds remain open. This is opt-in and is not the
installed desktop default.

## Native textarea wheel input

`NEXTSPACE_FIREFOX_WHEEL=1` additionally requires a native multiline or list viewport,
the provider's existing wheel capability and the exact guards in `pinned-wheel.h`.
The adapter forwards uncancelled input through the existing bridge operation to
the ordinary GNUstep `NSScrollView` responder. AppKit owns line/page movement,
modifier behavior, bounds and the native image. No control implementation or
NativeUI API is added, and neither Firefox nor AppKit is rebuilt.

Gecko's existing APZ-aware hit-test flag makes its compositor wait for the native
widget even on pages without wheel listeners. The real post-DOM default boundary
preserves page cancellation, then acknowledges native consumption through the
engine's default-handler cancellation. Content still sees its original
`defaultPrevented` result. The original `APZWheelActionFor` keeps Firefox's
zoom/history preferences; the adapter has no replacement action table. Native
offsets return through the existing Gecko scroll setter and event lifecycle.
Retained display lists can survive a focus change. The adapter tracks the focus
represented by its cached image and refreshes native focus/pixels when needed,
so a blurred field does not retain a native caret. This refresh transfers no
engine scroll offset and implements no caret drawing.

The [wheel qualification](wheel-qualification.json) records real-seat full and
fractional steps against an ordinary GNUstep window, complete native images,
trusted wheel/scroll events, read-only/disabled controls, cancellation, element
mutation/removal/reinsertion and host replacement. Firefox suppresses DOM scroll
events on disabled textareas; an independent engine-rendered disabled textarea
establishes that policy. The bridge preserves it.

This remains opt-in for the exact pinned ARM64 build at 100% scale. Root-document
wheel input, touch momentum, horizontal/nowrap text,
IME/accessibility, browser frontend controls and derivative builds remain open.

## Native textarea caret viewport

With the existing native multiline viewport enabled, post-key handling now
forwards the real native scroll position through Gecko's existing setter.
During a pre-edit callback, engine reflow keeps the live native object and its
cached geometry instead of treating a busy model reply as a failed binding.
After the browser commits the canonical model, the shared provider completes the
ordinary `NSTextView` caret reveal. No caret geometry, line navigation, wrapping
or scroll policy is copied into this adapter, and no API extension is needed.

The shared [caret qualification](../../Libraries/NativeUI/caret-qualification.json)
covers actual-seat vertical navigation, forward/backward selection, wrapped
text, offscreen insertion, cancelled insertion, complete native images and host
replacement on the pinned 100% scale build. Pointer autoscroll, ancestor-page
reveal, richer edits/async clipboard commands, selection-direction metadata,
IME/accessibility and other scales/builds still need qualification.

## Actual desktop rendering

The first complete Workspace screenshots exposed a gap in the earlier image
checks: Marionette's content screenshots showed native fields, while the actual
desktop showed empty text fields and several original Firefox controls. The
active `nsITheme` can be GTK for web content as well as the browser frontend.
Intercepting only `Theme::CreateWebRenderCommandsForWidget` did not reach that
on-screen path. The adapter now selects Gecko's existing paint fallback at the
shared `nsDisplayThemedBackground` boundary, before virtual theme dispatch.
Owned webpage text fields also use the existing native display-item painter.
These bindings apply even when frontend integration is disabled. No native
control, UI renderer, browser or AppKit implementation was copied or rebuilt.

[`native_ui_desktop.py`](../../Tests/Wayland/native_ui_desktop.py) runs an actual
Workspace desktop with the session supervisor, NativeUI host and pinned Firefox.
It receives the compositor's authorized screencopy role and compares full RGB
control rectangles with independent direct GNUstep references. It never requests
a browser screenshot. Arguments select the existing supervisor, compositor,
Workspace, capture probe, provider, adapter, browser and backend bundle; run
`python3 Tests/Wayland/native_ui_desktop.py --help` for the complete interface.
The runner isolates defaults, browser profile, session bus, control sockets and
Marionette port; `--no-frontend` additionally verifies ordinary web controls
without the address-field binding. The
[desktop qualification](desktop-qualification.json) records both runs and the
old adapter's expected failure. The [source audit](desktop-source-audit.json)
records the exact compiled boundaries. Full browser chrome, rich button content,
select bindings, root-document scrolling, broader CSS, other scales/builds and
derivatives remain unfinished.

## HTML buttons

With the existing `NEXTSPACE_FIREFOX_BUTTONS=1` option, ordinary HTML buttons
now use the same actual `NSButton` as input buttons. Gecko's rendered-text
accessor supplies labels, including nested textual content, hidden descendants,
Unicode and whitespace processing. Native button cells supply drawing and
preferred dimensions. The existing input adapter supplies native tracking,
keyboard interpretation and focus traversal; Gecko retains trusted click,
submit/reset and cancellation behavior. Text display items remain in Gecko's
display list for descendant hit testing, while the native button owns title
painting. No HTML text renderer or widget key policy is copied.

Rendered text is incomplete during reflow. The adapter retains the completed
native model until Gecko's original `DidReflow` finishes, then obtains fresh
native metrics and uses Gecko's existing reflow request when they change.
Fractional first-layout frames retain their measurement binding until native
automatic sizing settles. A committed title change requests Gecko's paint-only
invalidation for the existing background item. Reconstructing display items from
fallback preparation can discard a newly queued WebRender image in the same
transaction and abort the browser. Omitting invalidation leaves stale title
pixels when dimensions stay unchanged; paint-only invalidation handles both.

The desktop runner accepts `--document Experiments/FirefoxNativeUI/test-html-buttons.html`
and `--restart-host` for the expanded fixture. It compares complete native
images on the actual desktop, checks descendant targets, real form actions,
keyboard/click cancellation, disabled controls, author-style fallback and
restoration, label/model changes, resizing, editing, reload and host replacement.
See [qualification](html-button-qualification.json) and
[source audit](html-button-source-audit.json). This qualifies text-label buttons
on the pinned horizontal scale-1 build. Image/SVG/pseudo/shadow content,
default-button policy, accessibility and broader layout/scale/build coverage
remain open.

Automatic inline-flex and inline-grid buttons now feed the same native preferred
metrics into each original Gecko intrinsic-size override. The shared metric
helper uses original engine border/padding offsets; Gecko retains CSS sizing and
constraints. Ordinary non-button flex/grid frames call their original methods.
No native component or layout algorithm is copied.

The expanded shared button/text suite passes 108 checks and 48 complete native
images in Firefox, and 107/48 in the unchanged Chromium adapter. It includes
title growth/Unicode/empty labels, min/max-content, CSS minimum/maximum/fixed
sizes, display-type changes, original form actions and unchanged-size title
updates. Reversing digit titles preserves native preferred size and fixed CSS
bounds while the complete native pixels change. See the
[qualification](button-sizing-qualification.json) and
[source audit](button-sizing-source-audit.json) for exact runs, prior failures
and the retained-image trace. Run `check-button-sizing.py --fixture PATH --port PORT
--text-regression` against an owned native fixture to repeat these shared checks.

Shared Workspace menu selection and menu-only activation are now qualified
separately using actual desktop focus, visibility and native input. See
[desktop menus](../../Libraries/NativeUI/desktop-menu-qualification.json) and
[menu activation](../../Libraries/NativeUI/menu-activation-qualification.json).
These shared rules use window ownership and focus without application-name cases.

The optional `--native-frame` flag in both Firefox fixture launchers selects
Firefox's existing system-decoration settings through the shared
[`browser_frames.py`](../../Libraries/NativeUI/Bridge/browser_frames.py) helper.
The compositor's GTK3 legacy-decoration compatibility path supplies the existing
desktop frame, including title drag, Escape rollback, shade/unshade, resize,
fullscreen, minimize and close. This adds no browser hook or copied drawing.
Tabs, toolbars and other remaining browser controls are still separate work.

`run-frontend-fixture.py --native-tabs` enables the experimental browser tab
container binding. `NEXTSPACE_FIREFOX_TABS=1` also enables it when frontend/text
integration is already configured. The unchanged pinned Gecko build supplies
its real ordered XUL tab elements, displayed labels and selected state. The
shared [`Bridge/Tabs.inc`](../../Libraries/NativeUI/Bridge/Tabs.inc) sends that
application data to the same ordinary GNUstep `NSTabView` used by Chromium.
Gecko's existing background display item carries the native image; the old
child painting is replaced. There is no CSS theme or second tab renderer.

AppKit supplies pointer behavior and item rectangles. Committed native selection
calls Gecko's original `nsXULElement::ClickWithInputSource`, which dispatches the
real trusted XUL activation through Firefox's browser handlers. Cancelled
physical input preserves selection. Native IDs retain their DOM nodes until
model retirement, and the binding identity survives original dispatch without
using a stale frame pointer. Existing browser commands retain close, next-tab
and reorder behavior. The original GLib UI queue invalidates the full native
owner after model changes, including later titles in a loading document.

The actual Workspace desktop fixture accepts `--native-tabs`. Its
[tab qualification](tab-qualification.json) records full native-image comparisons
and real-seat input alongside the existing controls, detached menus and host
recovery. The native-tab run passes 113 checks, with sixteen whole native tab
images and all 153 existing control images. The final adapter with tabs disabled
also passes 82 checks and 153 complete control images. The shared NativeUI
provider and AppKit remain unchanged.
This is an opt-in pinned scale-1 tab-container prototype. Native tab icons,
loading indicators, alerts, new-tab and per-tab close buttons, context menus,
dragging/touch, overflow/groups, complete pane/toolbar layout, accessibility, broader scaling,
derivatives and installed deployment remain unfinished.


`NEXTSPACE_FIREFOX_POPUPS=1` enables an in-progress webpage single-select
binding when native input is configured. It sends Gecko's option data to the
existing kind-6 `NSPopUpButton`/`NSMenu` provider. Gecko's original selection
method dispatches application events; its original WebIDL setter and
`AutoJSContext` manage `:open`. Native drawing, menu layout, tracking and key
interpretation remain in the shared GNUstep implementation. The browser,
AppKit, provider and public NativeUI ABI remain unchanged.

This binding is not qualified for deployment. The historical initial fixture passed
17 checks, including five whole native control images, trusted selection,
Escape, cancellation, stale identities, reentrant removal and blur. An optional `NEXTSPACE_GTK3_GEOMETRY_LIBRARY` points to the shared GTK3 geometry
bridge. The pinned adapter supplies its compositor origin to Gecko's existing
bounds calculation and original parent/content dimension notifications. Initial,
moved, fullscreen and restored menu anchors now pass, including real native
press-drag-release selection and the subsequent complete native control image.
The current model includes ordered group headings, disabled options, native
separators, attribute/computed visibility and hidden-selected labels. It uses
the shared `Bridge/Popups.inc` serializer and the provider's existing independent
popup-title method. Actual option indices and retained DOM identities guard
commits when hidden options change the mapping. An empty visible model keeps
the engine/native menu closed. All drawing, tracking and key handling stay
native. Broader lifecycle, moving owners while open, zoom,
listboxes, IME and accessibility remain unfinished.

The current implementation order is webpage controls, detached menus, then
native shortcuts. Each must reuse the existing GNUstep/AppKit component and
behavior through the bridge. Toolbar work is skipped at the user's request.


The single-select checks are reproducible with
`check-popups.py --fixture OUTPUT --geometry --models --sizing` against a held owned fixture
launched with `NEXTSPACE_FIREFOX_POPUPS=1`. The checker uses whole desktop
captures, independent provider images, original DOM events, native item
rectangles and compositor geometry. It also rejects native browser field/tab
bindings. `Tests/Wayland/popup_models.py` and `native_popup_fixture.py` supply
the same model cases, native references, real seat input and geometry checks
for both browser engines. Browser-owned UI stays preserved.

At scale 1, the pinned Firefox adapter now feeds the existing native cell's
preferred size into Gecko's intrinsic inline and automatic block sizing.
Gecko retains explicit CSS dimensions, min/max and box sizing; its separate
dropmarker allocation is suppressed while the complete native control supplies
the arrow. Gecko's existing select mutation observer schedules ordinary
intrinsic-size invalidation after light-tree changes. No text measurement,
widget geometry, additional DOM observer or polling loop is implemented here.
The shared `Tests/Wayland/popup_sizing.py` checks independent native sizes and
complete pixels for empty/disabled/Unicode/grouped controls, CSS constraints,
changed text/labels, visibility, insertion and removal without application actions.

Native-host replacement also replays an unchanged retained popup model and
resets its action counter for the new host. The optional desktop
`--restart-host --popup-recovery` check retains a hidden selected option and
grouped/disabled menu model, then verifies the first replacement-host action
commits the original DOM index once. Wider select lifecycle, scaling, derivatives
and installed deployment remain open. See the
[sizing and recovery qualification](popup-sizing-qualification.json).


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


### Native list viewport and point targets

The optional list binding now consumes the same shared scroll geometry and
item-hit queries as Chromium. Lists and text areas share the existing guarded
scroll-container reflow, scroll setter and wheel boundaries. Actual native clip,
document and row measurements supply DOM geometry; original Gecko SetRect and
scroll/reveal methods retain engine bookkeeping and trusted events. There is no
second row layout or scrolling implementation in the adapter.

Shared operation 50 pairs the original native row rectangle with its existing
list state payload in one dispatch. Bootstrap part 2.y advertises this optional
metadata; NativeUI remains API 1/584. Older rectangle-only consumers ignore the
payload, and providers missing required geometry/hit capabilities retain Gecko's
original list implementation.

The original GetFramesForArea traversal runs first. Its existing list-root entry
anchors the shared native item query. Original TransformPoint converts layout
or visual viewport coordinates into the native owner; original nsTArray
InsertSlotsAt inserts the live option frame before that root. Original traversal
ordering preserves overlays. Semantic nodes are retained and frame/control
identity is rechecked after native RPC. No hit, selection, allocation or pointer
event algorithm is duplicated.

See [viewport/point qualification](list-scroll-qualification.json) and
[source audit](list-scroll-source-audit.json). This covers the measured pinned
scale-1 point and scroll contracts. Rich models/styles, broader layout APIs,
rectangle/list-based contracts, held scrollers, host/failure recovery, scaling,
IME/accessibility, metadata performance and derivative builds/deployment remain
open. Browser toolbar, address bar and tabs retain their existing components;
future changes belong in optional app-specific patches above the shared layer.


### Native list wheel lifetimes

The shared list scroll fixture now removes a native list from a trusted wheel
callback, checks its released native lifetime, reinserts it and compares the next
physical wheel with an independent actual GNUstep list. It observes the native
offset over 350ms and compares the complete control after reinsertion. The same
module runs in Chromium and preserves the exact native script-reveal target.
The pinned Firefox adapter needs no change for these cases; see the paired
[reveal/lifecycle qualification](../ChromiumScrollers/list-reveal-qualification.json).


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

Keyboard interruption ends native tracking before native key dispatch and
cancels the pending pointer action. A real held-button Ctrl+A witness verifies
GNUstep caret-beginning behavior instead of browser select-all. The corresponding
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

`NEXTSPACE_FIREFOX_COLORS=1` enables the exact guarded native sRGB color path.
Ordinary NSColorWell pixels replace the page swatch. The original Firefox
parent-process picker borrows that same well through shared color ownership,
using the original IPC actor ID. It creates no parent duplicate. Original
parsing, picker permission checks, canonical serialization, trusted input/change
and callback ownership remain in Firefox. No browser rebuild or toolbar/tab
replacement is involved.

The shared suite runs with `check-button-sizing.py --fixture <owned-fixture>
--port <port> --colors-only`. The measured cohort passes 18 checks and six
complete native images, including source model updates and picker closure on
field retirement. See [shared qualification](../../Libraries/NativeUI/color-owner-qualification.json)
and [source audit](color-source-audit.json). Native HTML-picker/alpha/wide-gamut
modes, pointer/drag feedback, native palette behavior, recovery, broader
styles/scales/accessibility, derivatives and deployment remain open.

`NEXTSPACE_FIREFOX_NUMBERS=1` opts the guarded Firefox build into the shared
native number binding. It composes the existing NSTextField and NSStepper,
using Gecko's original anonymous button frame for component geometry.
TextControlState supplies the displayed value and selection; original Gecko
stepping and commit methods preserve decimal/range policy, validation, trusted
events and focus. Native command selectors connect Up/Down to that model.
The same shared action receipts and stepper binding serve Chromium and Firefox;
the GNUstep provider and browser binaries are unchanged.

Run `Tests/Wayland/check-native-number-fields.py --engine firefox
--baseline <original-fixture> --native <native-fixture> --native-pixels
--output <results.json>` with owned fixtures on the specified Marionette ports.
The focused number cohort passes 21 behavior checks and six complete component
image comparisons. An ordinary URL/telephone regression adds 43 checks and 17
native image comparisons. See [qualification](number-qualification.json) and
[source audit](number-source-audit.json) for exact binaries, scope and evidence.
The fixed fixture compares source/native pointer actions through unchanged
anonymous-frame geometry. Broad styles/scales/RTL/IME/accessibility, intrinsic
native height, host/receipt-loss recovery, derivatives and deployment remain
unqualified. Remaining temporal controls, detached
menus/shortcuts and subsequent GTK/Qt/KDE integration are still required.

`NEXTSPACE_FIREFOX_DATES=1` enables `<input type=date>` through the same shared
NSDatePicker, nullable model and ordered action binding as Chromium. The
adapter replaces the original UA widget attachment so hidden JavaScript
segments cannot consume edits or focus behind the native picker. Original
Gecko serialization, SetUserInput, validation, trusted events and focus order
remain in use. Browser chrome stays original.

Run `python3 Tests/Wayland/native_date_fields.py <owned-fixture> <Marionette-port>`.
The focused cohort passes 37 checks, including explicit original native action
witnesses and four complete independent native images. See
[date qualification](date-qualification.json) and [source audit](date-source-audit.json).
With the shared TIME_OF_DAY capability, the same flag enables `time` and
`datetime-local` using that original picker. The original Gecko serializer
retains millisecond values. Temporal type changes keep the replaced UA editor
retired through its separate setup/change notification boundary. Shared date
receipts are rebased when page script replaces a model during native repeat.

Run `python3 Tests/Wayland/native_temporal_fields.py <owned-fixture> <Marionette-port>`.
The current temporal cohort passes 41 checks/four complete independent native
images; date and number regressions pass 37 and 27 checks. See the shared
[temporal qualification](../../Libraries/NativeUI/temporal-qualification.json).
Month/week consumers, native calendar showPicker presentation, broad geometry/
style/accessibility qualification, recovery and deployment remain unfinished.


The shared proleptic-calendar capability now applies to the existing date/time
consumers, using staged Foundation04 and the unchanged original GUI02 picker.
Seven additional early-era checks include actual native callbacks and two full
native images; temporal/date/number regressions remain 41/37/27 passing checks.

Pinned Firefox defaults resolve month/week to text. The existing shared native
NSTextField preserves that behavior and passes 16 checks/four full images,
including native Emacs commands, trusted edits and readonly/disabled models.
Run `python3 Tests/Wayland/native_temporal_fallback_fields.py <owned-fixture> <port>`
and `python3 Tests/Wayland/native_calendar_eras.py <owned-fixture> <port>`.
This does not qualify preference-enabled month/week pickers. See the shared
[month qualification](../../Libraries/NativeUI/month-qualification.json).


The staged week-capable GUI04/Base05 provider also passes the existing Firefox
128-check cohort with 20 full native images: temporal text fallbacks, date/time,
early eras and number controls. Firefox's adapter is reused unchanged for this
native-library update. Preference-enabled month/week pickers and native calendar
presentation remain unfinished. See the shared
[week qualification](../../Libraries/NativeUI/week-qualification.json).
