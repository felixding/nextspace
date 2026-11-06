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

Implementation priority, 2026-11-05: first make the Chromium-based and
Firefox-based browser families native, including their application interfaces
and web controls. Then continue with the remaining non-GNUstep applications.
Both stages use the same native UI library and keep the no-duplication and
no-application-recompile requirements.

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
across reflow and invalidates retained backgrounds after committed title changes.
See the [HTML button qualification](../Experiments/FirefoxNativeUI/html-button-qualification.json).
Rich button content, select controls and the broader browser/application scope
remain unfinished.
The full host-replacement capture also shows a menu-presentation gap: Firefox
remains focused and its D-Bus menu is bound, while the detached menu shows
TimeMon. Native control-image recovery does not qualify that menu behavior.

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
Menu-only application activation, other builds/derivatives and remaining native
browser/application controls still need qualification.

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
