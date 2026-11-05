# Native scrollbars in foreign applications

Verified 2026-11-05 on Debian 13 ARM64, native NEXTSPACE `0.1.0~native106`,
GTK3 3.24.49, GTK4 4.18.6 and Qt6 6.8.2, using the headless Wayland compositor
with its Pixman renderer. Physical display/GPU behavior is not qualified here.

The optional adapters host the installed GNUstep `NSScroller`; they do not copy
its artwork, geometry, drawing or mouse tracking. Existing GTK/Qt adjustments,
content and text direction remain in place. Neither application sources nor
`NSScroller` sources are patched. Konsole's custom terminal layout uses its
existing scrollbar-side option through a launcher.

The installed Release package passed 48 baseline/native cases: Qt scroll areas,
tables, trees, plain text and an overlapping parent style; GTK4 with plain and
`GtkApplication` startup; and GTK3. Native cases cover 100%, 125%, 150%, 175% and
200%. Checks include native pixels, left placement, pressed artwork, arrow
repeat, dragging outside the bar, resize/header alignment, normal shutdown and
absence of extra mapped backing windows. Ten live fractional-scale transitions
also passed. GTK3 uses integer backing scale; fractional pixel comparisons omit
the host-composited outermost row/column.

Separate checks passed for late-loaded PyGObject GTK4, distribution Konsole
25.04.2, native alternate-key tracking, preserved session environment, repeated
activation, opt-out and keeping AppKit/GTK out of unrelated processes.

Local evidence and the installable package are under `.build/foreign-scrollbars/`:
`installed-v13-matrix/results.json`, `installed-auxiliary-v13.json`, screenshots,
and `nextspace-foreign-scrollbars_0.1.0~scrollbars13_arm64.{deb,json,source.tar.gz}`.
The receipt records source/payload hashes and resolved package dependencies.
See [build and activation instructions](../Libraries/ForeignScrollers/README.md).

Chromium/Blink, Qt Quick and other custom renderers remain outside this adapter's
coverage. Qt5 and sandboxed runtimes are unqualified. Menu and shortcut
integration are separate from this scrollbar change.
The [Chromium source and binary audit](Chromium-Native-Scrollbar-Boundary.md)
records why the shared adapters cannot replace its web-content control.

An optional [Chromium runtime experiment](../Experiments/ChromiumScrollers/README.md)
now passes basic native pixel and mouse-tracking checks on the exact audited
ARM64 build without recompiling it. It is not installed or included in the
GTK/Qt package qualification above. General Chromium support remains open.

The expanded [native-control requirement](Native-Control-Integration.md) covers
whole non-GNUstep applications, including GTK, Qt/KDE and browser applications:
controls, detached menus, editing, focus, shortcuts, dialogs and desktop behavior.
The toolkit implementations above remain
scrollbar-only. An earlier Chromium screenshot exposed a disabled-bar fallback;
eight added enabled/disabled pixel comparisons now pass, while the exact earlier
trigger remains unconfirmed.

The native implementation now lives in the separate
[`NativeUI` provider](../Libraries/NativeUI/README.md), with a C scrollbar ABI
forwarding shim. Private native/control and Chromium checks pass through this
split. The installed v13 package matrix above predates it; the full GTK/Qt
package matrix still needs to be rerun before activating the new provider.
