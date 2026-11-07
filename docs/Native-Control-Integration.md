# Native controls across foreign applications

User requirement, clarified 2026-11-05: make non-GNUstep applications look and
behave native throughout NEXTSPACE. This includes GTK applications, Qt/KDE
applications and browsers such as Chromium, Chrome, Vivaldi, Firefox and their
derivatives. The scope covers whole applications: controls, layout and placement,
detached menus, text editing, focus, keyboard shortcuts, dialogs and integration
with the desktop's window decorations and commands.

Reuse the actual NEXTSPACE control implementations. Keep toolkit/application
adapters and the shared bridge separate from the underlying UI library, so
appearance and interaction can be changed in that library in one place.
Recompiling each application is excluded. The branch is now
`codex/native-app-integration`; its former `codex/left-scrollbars` name identified
the starting experiment. Acceptance is application-wide native integration
across foreign toolkits and frontends.

Implementation priority, clarified 2026-11-07: first integrate the Chromium-based
and Firefox-based browser families, then continue with the remaining non-GNUstep applications.
Both stages use the same native UI library and keep the no-duplication and
no-application-recompile requirements.

The current browser scope keeps each browser's built-in tabs, address bar and
toolbar. Work proceeds through webpage controls, detached menus and native
shortcuts. Native command routing can operate the existing tabs without
replacing their component. Later requested browser-UI changes belong to optional
app-specific patches above the shared engine/toolkit bridges and UI library.
GTK and Qt/KDE integration will reuse that shared layer, with app-specific
patches only for application-specific issues.

The shared popup row/title transport now binds both pinned engines' ordinary
single-select models, including groups, disabled children, separators and hidden
selected labels. The same real-seat cases reject stale indices after a hidden
insertion and commit the updated original option on the next menu. See the
[model qualification](../Libraries/NativeUI/browser-popup-model-qualification.json).
Both pinned engines now use native popup preferred sizes through their existing
layout and option notifications, including label/option changes and CSS size limits;
see the [Firefox](../Experiments/FirefoxNativeUI/popup-sizing-qualification.json)
and [Chromium](../Experiments/ChromiumScrollers/popup-sizing-qualification.json)
qualifications. Retained grouped/hidden popup models and first native actions also
recover after native-host replacement. Complete popup lifecycle/scaling, derivative
builds and installed deployment remain unfinished. Toolbar changes remain optional
browser-specific patches above this shared integration.

Detached-menu visibility is an application-agnostic desktop policy: present
the active application's menu and hide inactive applications' menus. Workspace
uses the focused window's owner PID and the acknowledged shared menu host;
application names and toolkit identities do not select this behavior. TimeMon
in the earlier failure capture identifies the visible symptom, not the scope
of the fix.

Workspace's version-19 shell connection now selects the active window's menu
address and forwards it through an optional inherited native-host role. The
live two-window Firefox check follows focus to TextEdit and back without copied
controls. The session supervisor now owns the shared host, publishes its endpoint
to children and activation, and relays Workspace's private menu role across host
restarts. Headless staged checks exercise the user launcher and actual Workspace
connection classes; full installed Workspace/PAM deployment remains open.
Pinned Firefox global shortcuts now use native menu matching at Gecko's
real command boundary, including outside text fields and after web cancellation
checks. The earlier page-body Alt+T failure is retained as historical evidence;
Pinned Chromium also binds its startup application menu and global keys to
native matching. Derivative builds remain unqualified. See the
[association qualification](../Experiments/DBusMenus/workspace-qualification.json),
[Chromium global-key qualification](../Experiments/ChromiumScrollers/global-menu-qualification.json)
and [session qualification](../Applications/Session/native-ui-qualification.json).

The shared session host now retains the original browser connections across
host loss, including sandboxed renderer subscriptions. Pinned Chromium and
Firefox checks preserve native text transactions, Emacs navigation, cancellation
and application menu commands after replacement, then switch between the two
menu transports without competing roots. AppKit and browser executables remain
unchanged. See the [recovery qualification](../Applications/Session/native-ui-recovery-qualification.json).
This closes the measured connection-recovery gap, while broader control,
frontend, derivative and installed-desktop requirements remain unfinished.

Actual full Workspace desktop captures exposed a Firefox rendering gap that
content-only browser screenshots had hidden: native text models existed while
the visible fields were blank. The pinned adapter now routes eligible themed
display items into Gecko's existing fallback before GTK theme dispatch. The
new desktop fixture compares compositor screencopy pixels with independently
rendered GNUstep controls, including changes, resizing, editing and reload,
with frontend integration both enabled and disabled. This reuses the same
provider and UI library. See the
[desktop rendering qualification](../Experiments/FirefoxNativeUI/desktop-qualification.json).
Full installed deployment and the remaining application-wide requirements are
still open.

Pinned Firefox HTML text-label buttons now reuse the existing `NSButton`
provider and input adapter. Native cells supply preferred size and full title/
bezel images; Gecko supplies rendered label text, descendant hit testing and
real form activation/cancellation. Actual desktop checks include automatic
block sizing, fixed flex/grid buttons, Unicode/nested labels, model changes,
native editing and host replacement. The bridge preserves its completed model
across reflow and requests paint-only invalidation for changed native title
pixels. Reconstructing display items inside fallback preparation could discard
an image still queued in WebRender; omitting invalidation kept stale titles at
unchanged bounds. The existing engine paint-only mode handles both cases.
See the [HTML button qualification](../Experiments/FirefoxNativeUI/html-button-qualification.json).
The subsequent [Firefox sizing qualification](../Experiments/FirefoxNativeUI/button-sizing-qualification.json)
connects original block/flex/grid intrinsic methods to one native metric helper.
The stronger shared button/text fixture passes 108 checks/48 full native images
in Firefox and 107/48 in unchanged Chromium, including CSS constraints,
display-type changes and unchanged-size title updates.
Pinned Chromium buttons now consume the same native preferred sizes, including
automatic regular, input, flex/grid and CSS-constrained controls. Buttons and
selects share Blink layout primitives; actual native cells supply all metrics.
Painted interactive controls register the shared input lifetime even on
button-only pages. Host-epoch repaint recreates retained controls in the new
native host. See the
[Chromium button qualification](../Experiments/ChromiumScrollers/button-sizing-qualification.json).
Rich button content and the broader browser/application scope remain unfinished.
Radio-group integration needs the actual native group context, rather than
independent radio buttons. An ordinary `NSMatrix` reference now records real-seat
navigation, focus, selection, actions and pointer release at 1x and 2x. The
reference passes its original `NSButtonCell` objects into the matrix and verifies
their identities throughout input. Shift+Arrow demonstrates why key-cell and
selected-cell identities must be transported separately. See the
[native radio reference](../Libraries/NativeUI/radio-reference-qualification.json).
The shared provider now exposes an ordinary native matrix through an optional
API extension. Stable application IDs retain the same radio cells across model
updates; the old matrix clears its native selection and transfers cell ownership
before replacement. Native methods supply preferred size, cell geometry, drawing,
navigation and tracking. The provider qualifies 24 complete native images at
1x/2x, with separate selection/key identities and native action counts; see the
[shared radio-group qualification](../Libraries/NativeUI/radio-group-qualification.json).
The subsequent [shared group transport](../Libraries/NativeUI/radio-transport-qualification.json)
carries models, typed native state, member geometry and native member pixels.
Original native cell sizing accepts application field bounds, and the shared host
uses the actual native backing density during startup. The first opt-in pinned
Chromium group binding now supplies original engine membership/identities and
DOM focus/activation through a common group model cache; native matrices supply
member painting and input. Its
[qualification](../Experiments/ChromiumScrollers/radio-group-qualification.json)
records the partial tested scope. The opt-in pinned Gecko binding now uses the
same cache, member transport and pointer serializer. Its original group container
supplies ordered members and selection; retained engine nodes supply safe opaque
binding identities. Native key actions return through original Gecko focus and
trusted activation, with membership rechecked after callbacks. The shared tests
pass 40 group checks and 15 complete native member images in each browser; see
the [Gecko qualification](../Experiments/FirefoxNativeUI/radio-group-qualification.json).
Complete pointer/label behavior, layout topology, browser scaling, group recovery
and broader application coverage remain unfinished. A broader Firefox button
test also exposed an existing automatic inline-flex sizing gap, reproduced with
the prior adapter and retained in that historical qualification. The subsequent
Firefox sizing checkpoint above addresses it.
An earlier Firefox host-replacement capture showed TimeMon while Firefox was
focused; that run did not qualify menu presentation. The later menu/session
qualifications above cover their measured ownership and recovery cases.

The provider now also supplies an ordinary `NSTextView`/`NSScrollView` multiline
control, including native document/viewport geometry. Opt-in bindings for both
pinned browsers pass real-seat multiline editing, event cancellation and
clipboard checks across host replacement. Complete images match independent
direct GNUstep controls in the provider checks. The pinned Chromium viewport
experiment now uses native clip/document metrics, native bounds and actual
scroll offsets, retaining Blink's trusted scroll events. Twelve complete browser
images match provider output before/after host replacement; native arrow click,
repeat, release and CSS/script resizing pass. Its native scroll view replaces the
browser's scrollbar and overlapping resize grip. The pinned Chromium textarea
now also routes uncancelled wheel input to the native responder, including
pages without wheel listeners. Ordinary GNUstep and browser windows agree on
real-seat full/fractional steps after correcting the Wayland backend's axis
normalization. The adapter restores viewport state after host replacement.
See the [wheel qualification](../Libraries/NativeUI/wheel-qualification.json).
The pinned Firefox viewport now also consumes the shared native clip/document
geometry and scroll API, preserving real engine scroll events, native pixels
and arrow tracking through host replacement. Its hidden editor no longer
overrides native offsets with an independently laid-out caret. See the
[Firefox viewport qualification](../Experiments/FirefoxNativeUI/viewport-qualification.json).
Firefox's optional native wheel binding now routes its real post-DOM default
through the same GNUstep responder. The existing APZ-aware hit-test flag and
engine acknowledgement prevent a second compositor default, including pages
without wheel listeners. Page cancellation and original app wheel preferences
remain intact. See the
[Firefox wheel qualification](../Experiments/FirefoxNativeUI/wheel-qualification.json).
Both pinned adapters now also return the native caret viewport after key handling
and keep a busy editor alive during reentrant engine layout. The shared provider
completes native reveal after a changed canonical edit model, preserving
unchanged cancellation. Long vertical/wrapped navigation, selection and typed
insertion are recorded in the [caret qualification](../Libraries/NativeUI/caret-qualification.json).
Root-document wheel behavior, touch momentum, pointer autoscroll, ancestor-page
reveal, richer edits/async commands, broader wrap modes and Firefox's original
Alt/menu-bar interaction remain open, so complete text-area support is unproven.
See the [multiline qualification](../Libraries/NativeUI/multiline-qualification.json)
and [viewport qualification](../Libraries/NativeUI/multiline-viewport-qualification.json).

## Shared implementation and distinct integration boundaries

Keep one native host in `Libraries/NativeUI` using installed GNUstep/AppKit and
DesktopKit controls. `Libraries/ForeignScrollers` now forwards its legacy ABI to
that provider; toolkit and browser adapters consume the independent public C
interface. Extend the provider as additional control types are implemented. Do not copy native
artwork, geometry, editing rules, tracking loops or menu behavior into adapters.
Native focus, hit testing, pressed/disabled state, keyboard interpretation, IME,
selection, accessibility and lifecycle must be part of the contract, not just
paint requests.

Adapters connect host application semantics to that shared native host. The
required integration surfaces differ:

| Surface | Required integration | Current evidence |
| --- | --- | --- |
| GTK applications | Toolkit controls, layout, editing, menus, commands, dialogs and input adapters | Existing GTK3/GTK4 adapters cover scrollbars only. |
| Qt Widgets and KDE applications | Qt controls and application models, including KDE menus/actions, editing, dialogs and shortcuts | Existing Qt6 Widgets adapter covers scrollbars only; Konsole additionally uses its existing scrollbar-placement setting. |
| Qt Quick/QML and KDE frontends using them | Their control, rendering, layout, command and input boundaries | The Qt Widgets scrollbar adapter does not cover this surface. |
| Chromium web controls | Blink layout, theme, input and renderer transport | One exact ARM64 binary has experimental native scrollbars, partial button/checkbox/radio/slider/select integration, native progress animation and plain/password drawing, editing keys and single/Shift/double/triple-click selection and dragging connected to real Blink transactions. Native clipboard validation/execution now uses the existing Blink commands. IME, sizing/scaling and broader commands remain open. |
| Chrome/Chromium browser UI | Views controls, text editing and menu models | The pinned Chromium Omnibox uses the shared native field for pixels, editing, clipboard and pointer selection. Its real application menu model also binds to native detached menus. Broader command availability, IME and other Views controls remain open; Chrome builds are not qualified. |
| Vivaldi browser UI | Its HTML/CSS/JS frontend plus the underlying Chromium integration | No frontend adapter implemented; Chromium coverage cannot establish Vivaldi coverage. |
| Firefox web controls | Gecko widget/layout/input and process transport | One exact unchanged ARM64 Firefox ESR build has experimental determinate progress, checkbox/radio, input buttons with native intrinsic sizing, native ranges and plain/password fields with single/Shift/double/triple-click selection and dragging through the shared provider. Native clipboard validation/execution now uses the existing Gecko controllers. Selected-text data dragging, IME, other controls, scaled output and broader input remain open. |
| Firefox browser UI | HTML/XUL frontend, command/menu models and Gecko integration | The pinned Firefox address editor uses the shared native field for pixels, editing and pointer selection. Its actual D-Bus menu model supplies native detached menus, lazy bookmark branches and real commands. Sharing the menu and field host now qualifies native Undo/Redo shortcuts, Emacs navigation and clipboard commands in webpage/address fields. Production desktop association, other frontend controls and wider qualification remain open. |
| Other toolkits and application-specific controls | Their actual frontend, rendering and binary interfaces | Must be inspected and tested; a toolkit or engine family name alone does not prove coverage. |

Chromium's own documentation describes its Linux GTK integration as primarily
color extraction, rather than whole GTK widgets. Its browser address bar and
menus use Views. Mozilla's source explicitly routes common form controls to its
non-native theme, and Firefox's frontend documentation describes HTML/CSS/JS and
XUL. Vivaldi documents its separate HTML/CSS/JS UI. These are separate semantic
boundaries, even when they share a renderer.

Sources inspected 2026-11-05:

- [Chromium GTK integration](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/linux/gtk_theme_integration.md)
- [Chromium NativeTheme](https://chromium.googlesource.com/chromium/src/+/HEAD/ui/native_theme/)
- [Chromium Views](https://www.chromium.org/chromium-os/developer-library/guides/views/intro/)
- [Firefox native GTK theme source](https://searchfox.org/firefox-main/source/widget/gtk/nsNativeThemeGTK.cpp)
- [Firefox frontend overview](https://firefox-source-docs.mozilla.org/browser/overview.html)
- [Vivaldi frontend description](https://help.vivaldi.com/desktop/privacy/is-vivaldi-open-source/)

## No-recompile constraint

The existing Chromium experiment patches internal instructions and vtables in
memory. This proves that rebuilding Chromium is unnecessary for that particular
integration. It does not create a stable browser-wide plugin ABI. Build guards
and derivative qualification remain necessary until the browsers expose a
suitable interface. Do not broaden the accepted build IDs without auditing
actual instruction bytes, layouts, method signatures and process boundaries.

An OS compositor receives surfaces and input events; this is not enough to
replace application-internal editing, command or menu models with native ones.
A screenshot or accessibility overlay is not evidence that native input and
application behavior have been preserved. Custom web/canvas controls can also
lack a standard widget contract; the policy for forcibly replacing these is a
separate user decision.

There is currently no implemented universal adapter satisfying the requirement.
The shared provider and helper now expose actual GNUstep single-line text and
password editors, including native Emacs commands, Cut/Copy/Paste menu routing,
selection and caret invalidation. This foundation is qualified separately in
[`Libraries/NativeUI/text-qualification.json`](../Libraries/NativeUI/text-qualification.json).
The pinned Firefox adapter now binds plain/password webpage fields to those
editors; Chromium now also connects plain/password webpage drawing and native
keys to real engine text transactions. Chromium's address field now also binds
complete pixels and native editing keys to its real Views model, with clipboard
selectors routed through the actual Omnibox commands. Its single primary-click,
Shift-click and selection dragging now use the same actual native tracking loop.
Multiple-click selection and Firefox's address field have separate browser
qualification. The shared menu/field responder host now also qualifies native
Firefox Undo/Redo shortcuts. Provider and transport checks alone cannot
establish browser text integration.
The shared editor now also exposes native pre-edit proposals and cancellation
through a reentrant process-owned channel. The pinned Firefox adapter runs its
actual engine edit transaction during that callback, retains `beforeinput`
cancellation, and echoes the canonical result into the native editor. Its
text transaction audit rules out the
autocomplete-style whole-value setter as a general typing adapter because it
temporarily clears read-only and maximum-length constraints.
A shared host avoids duplicating the native components; coverage still requires
toolkit, engine and application-frontend adapters. Verify representative GTK and
Qt/KDE applications as well as browsers. A scrollbar or individual-control test
does not establish whole-application native compatibility.

## Implementation and acceptance sequence

1. Keep the scrollbar prototype optional and add disabled/fitting-content and
   state-transition pixel checks. Record every visible control in the fixture,
   including empty scrollbars and corners; a crop of one bar is insufficient.
2. Extend the shared host with actual native button, checkbox, radio, text,
   popup, slider, progress, list/tree and tab controls. Transport native events
   and model updates without substituting host-side drawing or tracking rules.
3. Bind Chromium-based and Firefox-based browser engines to the shared host,
   including metrics, layout, focus, input and state synchronization. Qualify
   each advertised browser/build, including derivative-specific frontends.
4. Bind browser application interfaces, command models and desktop integration. Native text editing,
   detached menus, command validation, dialogs, window decorations and shortcut
   routing must invoke the application's real actions and preserve its data.
5. Continue with GTK, Qt/KDE and other non-GNUstep applications through toolkit
   and application-frontend adapters to the same host. Cover complete
   applications, including controls outside standard toolkit widgets. Adapters
   translate semantics and events without owning another widget implementation.
6. Qualify every advertised toolkit/application/build and normal/disabled/focused/pressed
   state at the supported scales. Test shipped binaries with their sandboxes
   retained where applicable. Require native pixel references and native
   interaction traces, plus reload/close/crash/resize/IME/accessibility checks.
   Unsupported coverage remains explicit rather than silently falling back to
   a lookalike and claiming completion.

The first implementation of step 2 is in
[`Libraries/NativeUI`](../Libraries/NativeUI/README.md): a C-only loader, an
independent GNUstep UI provider and the existing scrollbar ABI forwarding shim.
The provider hosts actual push buttons, checkboxes, radio buttons, sliders,
progress indicators, popup buttons/menus and scrollbars using one shared view/event host. Native
tracking/model probes and 30 unchanged-scrollbar bitmap comparisons pass on the
private ARM64 test setup. The unchanged Chromium scrollbar path also passes
through this provider; changing the UI library's width setting changes its
layout and passes native pixels/input without a browser or bridge rebuild. Text, application menu integration and the remaining controls are still open.
The first Blink bindings now connect standard push buttons, checkboxes and radio
buttons in the same pinned Chromium experiment. They reuse this provider through
its public C ABI for metrics, pixels and mouse tracking. Fourteen native pixel
comparisons, nineteen browser assertions and independent native-action traces
pass, including cancellation and destruction during tracking. The optional
focus/keyboard integration below adds another part of the contract. Label
activation and broader layout coverage are still incomplete. The new types
are not connected to GTK/Qt or other browser families. Steps 3-5 and the full
application matrix remain open; this experiment is not globally activated.

The shared provider now also exposes native first-responder focus and logical
keyboard events through an optional ABI extension. Native button/checkbox/radio
Space activation, slider keys, focus-ring drawing, focus transfer and navigation
requests pass direct provider checks and helper round trips. The old loader and
client work unchanged with the extended provider, and the new loader accepts the
older provider without advertising unavailable input methods. No key bindings or
focus artwork were copied into the bridge.

The pinned Chromium adapter now consumes that handoff with the separate opt-in
`NEXTSPACE_CHROMIUM_INPUT=1`. Page cancellation runs before native input; native
actions invoke Chromium's trusted DOM activation pipeline, preserving form
submission and checkbox rollback. Native next/previous focus requests call the
engine's actual focus controller. The bridge translates logical keys and state;
it defines no Space/Enter/arrow bindings and draws no focus ring. Distinct native
object identities prevent a detached/reinserted DOM object from inheriting an
old gesture.

The private fixture passes 62 focus/keyboard/pixel assertions. Native traces
independently witness twelve keyboard actions, three mouse actions and both
focus-navigation requests. The existing 33 mouse checks pass with the input
handoff enabled. This establishes only the tested buttons, checkboxes and radio
buttons in the pinned binary. Native activation animation, radio-group keyboard
context, default buttons, command/menu models, IME, accessibility and other
engine/frontend integrations remain open. See
[`input-qualification.json`](../Experiments/ChromiumScrollers/input-qualification.json).

The same provider's existing `NSProgressIndicator` now supplies determinate HTML
progress bars in the pinned experiment with `NEXTSPACE_CHROMIUM_PROGRESS=1`.
Chromium's actual `HTMLProgressElement::position()` supplies its validated
value/max ratio; the bridge adds no parsing, clamping or native artwork. Progress
objects are excluded from button tracking and focus ownership, preserving their
ordinary read-only DOM click behavior. Twenty fixture checks cover whole native
images, model changes, resize, replacement, reinsertion and reload. The provider
and the UI library were unchanged for this binding.

Indeterminate progress additionally uses the real native timer/invalidation
handoff when `NEXTSPACE_CHROMIUM_ANIMATION=1` is enabled. The optional provider
event API services its native run loop and exposes repaint state; the helper
transports per-process invalidations, and the owning renderer thread schedules
the actual engine frame update. No native interval, frame selection or artwork
is copied. Fifty-nine browser checks pass, including 48 complete images against
native references and lifecycle/mode transitions. Older providers and old
loaders/clients retain their supported methods without emulation. See
[`animation-qualification.json`](../Libraries/NativeUI/animation-qualification.json).

One early initial-frame screenshot also showed
browser artwork in the first determinate bar; model invalidation corrected it,
and later fresh runs passed, but its cause remains unresolved. The diagnostics
and initial-frame test preserve that gap. See
[`progress-qualification.json`](../Experiments/ChromiumScrollers/progress-qualification.json).

The shared provider now adds actual `NSPopUpButton`/`NSMenu` objects and native
window event dispatch. Its optional descriptor-source API integrates browser
transport descriptors with the native run loop. Eighteen helper checks verify
native pixels, menu mapping while idle, keys, mouse selection, disabled items,
models and destruction. Existing Chromium checks remain green. This is the
common menu contract; browser application menus, browser parent/placement,
command models and Gecko integration remain unfinished. See
[`popup-qualification.json`](../Libraries/NativeUI/popup-qualification.json).
Firefox binary preparation is recorded separately in
[`Experiments/FirefoxNativeUI`](../Experiments/FirefoxNativeUI/README.md).

The first optional classic HTML select binding now passes 29 browser checks
through that same native provider, including trusted selection events,
keyboard/mouse cancellation, application `showPicker()`, blur and DOM lifecycle
changes. Existing browser regressions still pass 232 checks. The shared host's
deferred private window fixes stale native anchor geometry without copying menu
placement. Default disabled CSS opacity, live menu-model updates, auxiliary
input latency, browser window parenting/global coordinates and broader layout,
accessibility, frontend and build coverage remain open. The disabled native
image test uses explicit CSS opacity 1; default disabled presentation is not
qualified. See the [select qualification](../Experiments/ChromiumScrollers/popup-qualification.json).

Native invalidations now wake sandboxed renderers through an optional descriptor
transport using the same UI library. Active subscriptions follow real sender
lifetimes across PID namespaces and shared connections. Initial native drawing
also finishes before helper readiness, addressing a reproduced cold-resource
RPC timeout. The broader input, appearance and application requirements above
remain open. See the [notification qualification](../Experiments/ChromiumScrollers/notification-qualification.json).


The first Gecko binding now paints determinate HTML progress through the same
unchanged NativeUI provider and actual `NSProgressIndicator` implementation.
Gecko supplies its validated model and existing fallback DrawTarget; the bridge
transports native pixels and releases every native object after the snapshot.
Chromium and Firefox now share transport, protocol and ARM64 hook machinery in
`Libraries/NativeUI/Bridge`, with no copied native control implementation.
The private Firefox fixture passed 21 checks, including full native image
comparisons, model/maximum changes, resize, reinsert, reload and trusted engine
clicks; all 45 native objects were released. Renderer sandbox checks and helper
loss passed. The existing Chromium suite still passes all 261 checks after the
extraction. This qualifies only determinate progress at the tested 100% scale on
the pinned Firefox binary. Other Firefox controls and application interfaces,
scaled native transport, animation, broader input/accessibility and derivatives
remain required. See [Firefox qualification](../Experiments/FirefoxNativeUI/progress-qualification.json).


The optional Gecko checkbox/radio binding now uses actual native `NSButton`
objects for metrics, drawing, focus, tracking and key interpretation. Native
callbacks invoke Gecko's real trusted click path and document focus traversal.
Frame destruction, inactive tabs, cached-page freezing and renderer process
exit release native bindings; restored pages bind again without disabling
Firefox's cache. Forty checks and fifteen native-image comparisons pass,
including trusted model events, cancelled actions, early input, tab/cache
restoration, a frame replaced by its focus handler, renderer crash cleanup and
continued mouse/key actions after helper loss. The previous 21 native progress
checks also pass with interactive hooks enabled. The UI library/provider remain
unchanged, and the helper only gains generic destruction trace records. Radio
group arrow navigation, other controls and full browser application interfaces
remain open. See [interactive Gecko qualification](../Experiments/FirefoxNativeUI/input-qualification.json).

The pinned Gecko adapter additionally binds input push/submit/reset buttons to
the existing native `NSButton`, including its title drawing and interaction.
It uses the engine's real label accessor for localized defaults and suppresses
only the anonymous engine label after a complete native image is available.
Failed preparation restores the whole engine control, and unsupported style or
fractional size changes release native ownership. Fifty-four checks pass,
including thirty-three complete native images, trusted form submission/reset,
cancellation, Unicode titles, resizing, cache/tab restoration, renderer-crash
cleanup and continued input after helper loss. The forty checkbox/radio and
twenty-one progress checks pass with these hooks enabled. The UI library and
provider are unchanged. The actual native button cell now supplies preferred
metrics at Gecko's intrinsic/auto-size boundaries, retaining its CSS constraint
pipeline. Automatic sizes, title changes, basic flex/grid, min/max-content and
min/max constraints pass at horizontal scale 1. Default-button policy,
HTML `<button>` rich content, scaled/vertical output, broader layout and whole
browser interfaces remain open. See
[input-button qualification](../Experiments/FirefoxNativeUI/button-qualification.json).

The optional Gecko range binding uses the same actual `NSSlider` provider for
whole control drawing, mouse tracking, focus and logical keys. Engine accessors
supply min/max/value/step, and original drag lifecycle and user-value methods
retain capture, validation, cancellation and trusted input/change events.
The bridge supplies no slider geometry or key rules. Independent native images
and key results cover the tested fixed-size horizontal, vertical, disabled,
continuous, discrete and locked models. Continuous input, blur/Escape,
replacement/removal/style changes during tracking, cache/tab restoration,
renderer cleanup and helper-loss checks pass. Native automatic sizing, broader
step bases/endpoints, scaled output, touch/wheel/accessibility and browser
application interfaces remain open. See
[range qualification](../Experiments/FirefoxNativeUI/range-qualification.json).


The optional Gecko plain/password binding now uses the shared actual native
field editors for complete pixels, selection, caret and key interpretation.
Native pre-edit proposals enter Gecko's real insertion/deletion transactions;
canonical engine values return to the native editor after trusted events,
cancellation and script mutation. Tests cover native Emacs commands, engine
undo/validation, dynamic values/resize, form Return, page restoration, real caret
invalidation and failure recovery. Single-click/Shift-click/selection dragging
now use the actual native editor, including double/triple-click word/line selection; data dragging, clipboard and
menu command semantics, IME, other text types/scales and browser frontends
remain open. See [text qualification](../Experiments/FirefoxNativeUI/text-qualification.json).


## Shared application menu foundation

Workspace now selects detached-menu visibility for all applications by focused
window ownership. It allows that application's own native menu windows or the
acknowledged session host displaying its exported model, and hides other main
menus and submenus through the existing window-presentation interface. No
application names participate in this rule. The compositor dismisses other
windows' existing popup grabs before switching keyboard focus, so an open menu
cannot prevent the switch that selects the next application's menu.

The provider still uses the existing NSMenu/NSMenuItem implementation. Its
adoption hook applies the represented application's supplied title to the
native menu window and asks native layout to size it. Browser bridges restore
live models after native-host replacement; Firefox also restores a retained
textarea's canonical scroll position when a tab recreates its native binding.
See [desktop menu qualification](../Libraries/NativeUI/desktop-menu-qualification.json).
The shared Wayland backend also forwards AppKit's existing explicit main-menu
activation when an app has no document window. Application protocol v9 makes
that fallback opt-in, retains normal activation-token validation and prefers an
ordinary document when present. NativeUI proxy menus opt out through
`GSSuppressMenuActivation`, preserving their represented browser's keyboard
focus. No app-specific activation or copied menu/key implementation is needed.
The [activation qualification](../Libraries/NativeUI/menu-activation-qualification.json)
records 136 passing checks, including real icon double-clicks, native Quit,
browser focus during menu interaction and host replacement. Browser and AppKit
binaries are unchanged.
Other builds/derivatives, cross-desktop menu-only activation and remaining native
browser/application controls still need qualification.

Both pinned browser families can now request the desktop's existing shared
window frame through their system-decoration preferences. The compositor adds
GTK3's older KDE negotiation alongside xdg-decoration, with one existing frame
factory, renderer and input path. The bridge only prepares an owned stopped
profile; it contains no titlebar or window-control drawing. The
[frame qualification](../Libraries/NativeUI/browser-frame-qualification.json)
records 162 passing browser/protocol checks, all 153 Firefox native-control
desktop images, and the existing five-density frame regression. Tabs/toolbars,
other remaining controls, other builds, browser mixed-DPI and installed deployment
remain open.

The NativeUI provider now exposes optional application menus built from real
GNUstep NSMenu/NSMenuItem controls. Application models supply titles, hierarchy,
command IDs, state and native key-equivalent metadata; AppKit owns presentation
and interaction. Physical menu tracking, submenu actions, main-menu editing-key
routing and complete native images are qualified independently of browsers.
See [menu qualification](../Libraries/NativeUI/menu-qualification.json).
The shared helper now carries these menu models and authenticated owner
callbacks, including dispatch while idle, nested RPC reply ordering and native
cancellation on owner failure. Eighteen transport/lifetime checks and eighteen
physical menu/reference checks qualify that foundation; see
[menu transport qualification](../Libraries/NativeUI/menu-transport-qualification.json).
Browser menu-model extraction and connecting the dispatcher to each browser's
owner loop remain to implement. This foundation does not establish native
browser menus or coverage for GTK/Qt/KDE applications.

The next browser-frontend step now has a shared native tab foundation. NativeUI
creates ordinary GNUstep NSTabView/NSTabViewItem objects and exposes their model,
selection, native content/item geometry and bitmap through the shared helper.
Stable 64-bit application identities survive reorder and transport; no tab layout,
rendering, hit testing or key behavior is copied. Twenty whole images match actual
ordinary native desktop tabs at 100% and 200%. Direct/compatibility and C transport
checks pass, along with the existing browser desktop and NativeUI regressions.
See [tab qualification](../Libraries/NativeUI/tab-qualification.json).

The opt-in pinned Chromium adapter now presents its tab container through that
same NSTabView. Existing engine getters supply displayed titles/order; opaque
IDs survive reorder and retire with browser views. Native pointer selection
calls the original browser controller, while normal next/close/reorder commands
update the native model. Twelve complete tab-container images match the public
NativeUI reference in the actual desktop, including loading/title changes, host
recovery and resize.
The shared provider still matches ordinary native desktop tabs at 1x/2x.
See [Chromium tab qualification](../Experiments/ChromiumScrollers/tab-qualification.json).
This does not finish the browser interface: native tab icons/close/context/drag/
overflow/group features, pane/toolbar layout, broader input/accessibility/scaling,
The subsequent Firefox binding is described below; derivatives and installed
deployment remain open. GTK/Qt/KDE follow
the browser work. No native component is duplicated or browser recompiled.

The opt-in pinned Firefox adapter now binds its real XUL tab collection to that
same NSTabView and shared tab serializer. Gecko's native DOM getters supply the
ordered model; native pointer selection calls the original trusted XUL activation
and browser handlers. The original GLib UI queue invalidates the entire owner
after model changes so Gecko's retained background cannot keep old title pixels.
The actual Workspace fixture covers native images, cancellation, next/close/
reorder, title changes and host recovery alongside existing fields and menus.
See [Firefox tab qualification](../Experiments/FirefoxNativeUI/tab-qualification.json).
The NativeUI provider and AppKit are unchanged. This adds the second engine
binding; native new-tab/close buttons and the remaining tab features, whole
browser interfaces,
derivatives/deployment and subsequent GTK/Qt/KDE integration remain unfinished.


The next shared component is a native toolbar foundation: ordinary NSToolbar,
NSToolbarItem and GSToolbarView supply buttons, standard spaces/separators,
layout and the overflow menu. The provider accepts application IDs/labels/state;
AppKit owns presentation and interaction. Complete ordinary desktop comparisons
cover 100% and 200% toolbar images. Optional Cairo device-density readback reuses
its existing readback implementation, and the shared Wayland backend acknowledges
geometry immediately for windows without a compositor role so embedded menu
placement agrees with actual surface position. Neither change names an app.
See [toolbar qualification](../Libraries/NativeUI/toolbar-qualification.json).
Toolbar IPC, native composition with address fields and both browser toolbar
bindings remain unfinished. The browser/derivative/deployment requirements and
subsequent GTK/Qt/KDE integration remain open under the original objective.


The shared native radio binding now preserves original NSMatrix pointer-action
state and click counts for both pinned engines. Browser adapters route the
native-selected node through their original trusted pointer-click dispatchers,
with original preactivation/cancellation and fresh membership checks after page
callbacks. Removing or replacing a member ends its native tracking before model
updates. The native provider and UI library remain shared and unchanged; only
adapters and bridge lifetime/transport handling change. See the
[radio pointer qualification](../Experiments/FirefoxNativeUI/radio-pointer-qualification.json).
Label activation, other layouts/scales and session-supervisor group recovery
remain open. Browser toolbar, address bar and tabs stay original; future requested
UI changes use optional application patches over this same shared integration.


Pinned radio label activation now uses the same shared native controls. The
original browser label default handler owns association, interactive descendants,
text-selection drag and cancellation. Only its trusted forwarded control action
crosses the shared semantic activation transport to existing NSMatrix methods;
the original engine still constructs the forwarded event and owns DOM rollback.
The optional NativeUI extension also supports original NSButton performClick:
for later adapters. No label association, widget state machine or native control
is duplicated. See [label qualification](../Experiments/FirefoxNativeUI/radio-label-qualification.json).
The form activation checkpoint below adds non-radio labels; the previously
listed broader browser integration gaps remain unfinished. Future requested
browser UI changes use optional per-app patches over the shared library and bridge.


The pinned browser adapters also bind checkbox/button labels through this same
semantic operation. Shared `Bridge/ControlActions.inc` carries native action
state and host/source identity; it defines no control behavior. Each engine
uses its original preactivation journal and setters to apply the actual native
checkbox state, preserving original trusted events, application writes and
checked/mixed cancellation rollback. This fixes a verified divergence for
initially checked mixed checkboxes. Original submit/reset actions and label
filtering remain intact. See [form activation qualification](../Experiments/FirefoxNativeUI/form-activation-qualification.json).

The existing 528-byte NativeUI provider/loader/shim remains unchanged. All
widget behavior and rendering stay in the single underlying UI library.
Toolbar/address-bar/tab changes, if requested later, are optional per-app
patches above that shared layer; they are outside the current webpage-control
work. This separation applies equally to subsequent GTK and Qt/KDE adapters.


A shared flat-list provider now instantiates the existing one-column
`NSBrowser`, including its native cells, matrix and scrollbar. The optional
ABI 1 extension preserves the 528-byte prefix and appends row-model/state/
selection/geometry/scroll methods (568 bytes). It supplies data and native
actions to subsequent consumers without duplicating list selection, layout,
key interpretation or drawing. See the [provider qualification](../Libraries/NativeUI/list-qualification.json).
Browser listbox and multiple-select bindings are still unfinished; the shared
transport below prepares their original engine transactions and layout work.

The shared list transport now carries exact native selection/focus/action
snapshots, native row geometry, scrolling and pixels through the existing
owned host paths. Both browser engines can consume the same C serializer;
radio/list key packets also share one encoder. Provider/loader/shim and AppKit
binaries are unchanged from the native-list provider checkpoint. See the
[list wire qualification](../Libraries/NativeUI/list-wire-qualification.json).
The transport is ready for original Chromium/Gecko model, DOM/default-action
and layout bindings; those browser controls are still implementation work.
