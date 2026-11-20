# Native scrollbars in foreign applications

This is the initial scrollbar component of the broader
[native application integration](../../docs/Native-Control-Integration.md).
The project goal covers native appearance and behavior throughout non-GNUstep
applications, including GTK and Qt/KDE applications and browsers.

These adapters host the existing GNUstep `NSScroller`. They contain no scrollbar
drawing, geometry, arrow repeat, jump-to-point or drag implementations.
`NativeScroller.c` forwards the existing C interface to the separate
[native UI provider](../NativeUI/README.md). Its GNUstep provider calls the real
`NSScroller` and translates the host's range and pointer events. The application's
existing scroll model, content widget and accessibility object remain in place.

Rendering uses the installed NextSpace theme through ordinary AppKit drawing,
including its shared artwork and backing-density selection. During mouse
tracking a private, unshown backing window supplies NSCell's focus contract.
The native tracking loop dispatches the host toolkit on the same thread.

GTK3 and GTK4 adapters install through the shared session environment, including
GtkBuilder-created widgets. Qt6 loads a generic plugin. Its scrollbar wrapper supplies native metrics and drawing.
Placement changes do not change the application's text or layout direction.

Qt's standard scroll areas have no independent public scrollbar-side setting,
so their adapter moves the existing bar and viewport, keeping item-view headers
aligned. Konsole has its own terminal layout. The small launcher selects its
existing `ScrollBarPosition=0` option; the shared adapter still supplies its
native scrollbar. No application is patched or recompiled.

## Build and check

On Debian 13 ARM64 with the installed native NEXTSPACE SDK, Clang, CMake,
`libgtk-3-dev`, `libgtk-4-dev`, `libdbusmenu-gtk3-dev`, `libwayland-dev`,
`qt6-base-dev` and `qt6-wayland`:

```sh
cmake -S Libraries/ForeignScrollers -B .build/foreign-scrollbars \
  -DCMAKE_OBJC_COMPILER=clang
cmake --build .build/foreign-scrollbars -j2
python3 Tests/ForeignScrollers/run.py --build .build/foreign-scrollbars \
  --artifacts .build/foreign-scrollbar-results
```

The tests run ordinary Qt/GTK apps with and without the adapters on native
Wayland. They check placement without RTL changes, native pixels, arrow actions,
dragging outside the scrollbar, pressed artwork, arrow repeat, repainting during
tracking, clean shutdown, resizing and table/tree-header alignment at 100%,
125%, 150%, 175% and 200%, including live fractional scale changes in Qt/GTK4.
Fractional pixel comparisons exclude the last pixel
column/row where host-widget clipping composites against the application's
background. GTK3 uses its toolkit's integer backing scale.

Build an optional package against the installed native SDK:

```sh
python3 Packaging/Debian/build-foreign-scrollbars.py \
  --build-dir .build/foreign-scrollbar-package \
  --output .build/packages --version '0.1.0~scrollbars1'
```

This branch's native user launcher sources the integration only when this optional
package is installed. For an existing installation with the older launcher,
`nextspace-native-scrollbars` starts its standard user session with integration
enabled; `nextspace-native-scrollbars COMMAND` enables it for a test command.
Existing sessions need a fresh login. `NEXTSPACE_SCROLLBARS=off`
before launching a session disables integration; removing the package restores
the existing launcher behavior. Existing GTK modules, Qt plugins and preload
entries are preserved. No system loader configuration or application profiles
are overwritten.

The install also supplies the [shared native UI host](../NativeUI/Host/README.md)
and its transport modules. The current user launcher automatically starts this
foreground host through the session supervisor when present; set
`NEXTSPACE_NATIVE_UI=off` to disable the session host independently of the local scrollbar adapter.
Python 3, PyGObject and GLib/Gio introspection are runtime dependencies. Native
widgets remain in the separate provider library. Browser adapters still require
their individual build checks and launch configuration; installing this package
does not by itself make browser controls native. The Debian package builds the shared host and its toolkit adapters together.

## Coverage boundary

This integrates GTK3/GTK4 scrollbars and Qt6 Widgets scrollbars. It cannot replace
scrollbars painted internally by Chromium/Blink, Qt Quick, games or other custom
renderers: they do not expose a GTK/Qt scrollbar widget to host `NSScroller`.
That remains an open integration gap, not a claim of native scrollbar support.
Qt5 and sandboxed application runtimes are not qualified by this package.

## Toolkit bridge

The GTK3 and Qt Widgets adapters use the shared NativeUI provider to draw
ordinary labeled push buttons, checkboxes and radio buttons. The original
toolkit owns the widget, accessibility, actions and focus order. The same
provider resolves editing keys for GTK entries and text views and for Qt line,
plain-text and rich-text editors. The adapter applies supported commands to the
original editor. Unsupported commands follow the toolkit's ordinary path.

On the NEXTSPACE Wayland desktop, GTK3 exports its GtkMenuBar through
libdbusmenu. KDE's platform theme exports Qt menu bars. The same session host
binds both exports to the active compositor surface and presents the menus
through GNUstep. The Qt XDG desktop portal theme wraps the KDE theme when both
are installed. File dialogs using the standard portal receive the existing
GNUstep chooser and the original Wayland parent. GTK3 menus opened through the
public pointer-popup entry point can use the shared native context menu host.

The local packaged preview exercised Konsole and Kate through the KDE binding
and Mousepad and Thunar through the GTK3 binding. Konsole Save Output As and
Kate Open used the native file panel. Thunar's native context menu ran the
original Rename action and accepted Escape. Mousepad uses its internal GTK
editor menu and encoding-aware file chooser. Qt context menus, additional
control types and the fractional-density release gate remain open.

Applications can set `nextspace-original-control` on a GTK widget or
`nextspaceOriginalControl` on a Qt widget before it is mapped or polished. A
custom button that uses the toolkit's standard painting path can opt into a
provider kind with `nextspace-control-kind` or `nextspaceControlKind`. Kate's
KTextEditor minimap retains its custom scrollbar. Konsole's launcher selects
left placement for its terminal scrollbar.

Set `NEXTSPACE_TOOLKIT_UI=off` before starting the session to disable the
toolkit adapters. `NEXTSPACE_NATIVE_CONTROLS`, `NEXTSPACE_NATIVE_EDITING`,
`NEXTSPACE_NATIVE_MENUS`, `NEXTSPACE_NATIVE_CONTEXT_MENUS` and
`NEXTSPACE_SCROLLBARS` accept `off` for their respective adapter paths.
`KDE_NO_GLOBAL_MENU` controls the stock KDE menu export.
