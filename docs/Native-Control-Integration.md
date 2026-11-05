# Native controls across foreign applications

User requirement, 2026-11-05: use the actual NEXTSPACE controls throughout
applications, including Chromium, Chrome, Vivaldi, Firefox and their derivatives.
This includes native appearance, placement, input behavior, menus, text editing
and shortcuts. Existing control implementations must be reused. Recompiling each
application is excluded. The scrollbar experiment is a feasibility result, not
completion of this requirement.

## Shared implementation and distinct integration boundaries

Keep one native host using installed GNUstep/AppKit and DesktopKit controls.
`Libraries/ForeignScrollers` already hosts the real `NSScroller`; extend that
boundary as additional control types are implemented. Do not copy native
artwork, geometry, editing rules, tracking loops or menu behavior into adapters.
Native focus, hit testing, pressed/disabled state, keyboard interpretation, IME,
selection, accessibility and lifecycle must be part of the contract, not just
paint requests.

Adapters connect host application semantics to that shared native host. The
required integration surfaces differ:

| Surface | Required integration | Current evidence |
| --- | --- | --- |
| GTK and Qt widgets | Toolkit object/layout/input adapters | Existing adapters cover scrollbars only. |
| Chromium web controls | Blink layout, theme, input and renderer transport | One exact ARM64 binary has experimental native scrollbars. |
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

No step after the scrollbar work is implemented or qualified yet. This document
records the expanded requirement and integration audit; it is not a support claim.
