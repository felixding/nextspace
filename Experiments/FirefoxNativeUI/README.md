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

A recreated textarea binding restores the engine's retained scroll point even
when the host epoch is unchanged. The full Workspace desktop fixture's
`--menus --restart-host` sequence checks native menu commands, tab return,
application switching, held-submenu dismissal, host replacement and native
control pixels together. This catches binding-lifetime failures that a host-only
recovery test misses.

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

`NEXTSPACE_FIREFOX_WHEEL=1` additionally requires the native multiline viewport,
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
automatic sizing settles. A committed title change invalidates the separate
background display item once, so retained display lists do not leave an old
native title on screen.

The desktop runner accepts `--document Experiments/FirefoxNativeUI/test-html-buttons.html`
and `--restart-host` for the expanded fixture. It compares complete native
images on the actual desktop, checks descendant targets, real form actions,
keyboard/click cancellation, disabled controls, author-style fallback and
restoration, label/model changes, resizing, editing, reload and host replacement.
See [qualification](html-button-qualification.json) and
[source audit](html-button-source-audit.json). This qualifies text-label buttons
on the pinned horizontal scale-1 build. Image/SVG/pseudo/shadow content,
automatic flex/grid sizing, default-button policy, accessibility and broader
layout/scale/build coverage remain open.

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
