# Native scrollbars in foreign applications

These adapters host the existing GNUstep `NSScroller`. They contain no scrollbar
drawing, geometry, arrow repeat, jump-to-point or drag implementations.
`NativeScroller.m` calls `NSScroller` for those operations and translates the
host's range and pointer events across a small C interface. The application's
existing scroll model, content widget and accessibility object remain in place.

Rendering uses the installed NextSpace theme through ordinary AppKit drawing,
including its shared artwork and backing-density selection. During mouse
tracking a private, unshown backing window supplies NSCell's focus contract.
The native tracking loop dispatches the host toolkit on the same thread.

GTK3 and GTK4 adapters install through the shared session environment, including
GtkBuilder-created widgets. Qt6 loads a generic plugin; its style wrapper is
limited to scrollbar metrics and drawing. Other application styling is retained.
Placement changes do not change the application's text or layout direction.

Qt's standard scroll areas have no independent public scrollbar-side setting,
so their adapter moves the existing bar and viewport, keeping item-view headers
aligned. Konsole has its own terminal layout. The small launcher selects its
existing `ScrollBarPosition=0` option; the shared adapter still supplies its
native scrollbar. No application is patched or recompiled.

## Build and check

On Debian 13 ARM64 with the installed native NEXTSPACE SDK, Clang, CMake,
`libgtk-3-dev`, `libgtk-4-dev`, `qt6-base-dev` and `qt6-wayland`:

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

## Coverage boundary

This integrates GTK3/GTK4 scrollbars and Qt6 Widgets scrollbars. It cannot replace
scrollbars painted internally by Chromium/Blink, Qt Quick, games or other custom
renderers: they do not expose a GTK/Qt scrollbar widget to host `NSScroller`.
That remains an open integration gap, not a claim of native scrollbar support.
Qt5 and sandboxed application runtimes are not qualified by this package.
