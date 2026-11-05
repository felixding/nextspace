# Native controls across foreign applications

User requirement, 2026-11-05: use the actual NEXTSPACE controls throughout
applications, including Chromium, Chrome, Vivaldi, Firefox and their derivatives.
This includes native appearance, placement, input behavior, menus, text editing
and shortcuts. Existing control implementations must be reused. Bridges must remain separate
from the underlying UI library so appearance and interaction can be updated in
one place. Recompiling each application is excluded. The scrollbar experiment is a feasibility result, not
completion of this requirement.

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
| GTK and Qt widgets | Toolkit object/layout/input adapters | Existing adapters cover scrollbars only. |
| Chromium web controls | Blink layout, theme, input and renderer transport | One exact ARM64 binary has experimental native scrollbars and partial standard button/checkbox/radio integration. |
| Chrome/Chromium browser UI | Views controls, text editing and menu models | No native-control adapter implemented. |
| Vivaldi browser UI | Its HTML/CSS/JS frontend plus the underlying Chromium integration | No frontend adapter implemented; Chromium coverage cannot establish Vivaldi coverage. |
| Firefox web controls | Gecko widget/layout/input and process transport | No adapter implemented or binary qualified. |
| Firefox browser UI | HTML/XUL frontend, command/menu models and Gecko integration | No adapter implemented. |
| Derivative-specific controls | The derivative's actual frontend and binary interfaces | Must be inspected and tested; engine ancestry is insufficient. |

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
A shared host can avoid duplicating the native components, but coverage still
requires integrations for the engine and frontend surfaces above. Passing a
Chromium scrollbar test must not be reported as Chrome, Vivaldi, Firefox, menus,
text fields, or full native compatibility.

## Implementation and acceptance sequence

1. Keep the scrollbar prototype optional and add disabled/fitting-content and
   state-transition pixel checks. Record every visible control in the fixture,
   including empty scrollbars and corners; a crop of one bar is insufficient.
2. Extend the shared host with actual native button, checkbox, radio, text,
   popup, slider, progress, list/tree and tab controls. Transport native events
   and model updates without substituting host-side drawing or tracking rules.
3. Bind standard web controls in both Blink and Gecko, including metrics, focus,
   disabled/pressed state and model synchronization. Test shipped binaries with
   their sandboxes retained.
4. Bind browser frontends and command models. Native text editing, detached
   menus, command validation, file dialogs and shortcut routing must call the
   host application's real actions and preserve its data.
5. Qualify every advertised browser/build and normal/disabled/focused/pressed
   state at the supported scales. Require native pixel references and native
   interaction traces, plus reload/close/crash/resize/IME/accessibility checks.
   Unsupported coverage remains explicit rather than silently falling back to
   a lookalike and claiming completion.

The first implementation of step 2 is in
[`Libraries/NativeUI`](../Libraries/NativeUI/README.md): a C-only loader, an
independent GNUstep UI provider and the existing scrollbar ABI forwarding shim.
The provider hosts actual push buttons, checkboxes, radio buttons, sliders,
progress indicators and scrollbars using one shared view/event host. Native
tracking/model probes and 30 unchanged-scrollbar bitmap comparisons pass on the
private ARM64 test setup. The unchanged Chromium scrollbar path also passes
through this provider; changing the UI library's width setting changes its
layout and passes native pixels/input without a browser or bridge rebuild. Text, menus and the remaining controls are still open.
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
