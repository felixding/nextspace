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
| Chromium web controls | Blink layout, theme, input and renderer transport | One exact ARM64 binary has experimental native scrollbars, partial button/checkbox/radio/slider/select integration and native progress animation. |
| Chrome/Chromium browser UI | Views controls, text editing and menu models | No native-control adapter implemented. |
| Vivaldi browser UI | Its HTML/CSS/JS frontend plus the underlying Chromium integration | No frontend adapter implemented; Chromium coverage cannot establish Vivaldi coverage. |
| Firefox web controls | Gecko widget/layout/input and process transport | One exact unchanged ARM64 Firefox ESR build has experimental determinate progress, checkbox/radio drawing/input, input push/submit/reset buttons with native intrinsic sizing and native range drawing/input through the shared provider. Other controls, scaled output, animation, radio-group arrow navigation and broader input remain open. |
| Firefox browser UI | HTML/XUL frontend, command/menu models and Gecko integration | No adapter implemented. |
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
Webpage and browser address-bar text bindings remain unimplemented; provider
and transport checks cannot establish browser text integration.
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
