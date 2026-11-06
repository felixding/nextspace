# Native menus from existing D-Bus models

This experiment binds `com.canonical.dbusmenu` data to the existing independent
NativeUI provider. GNUstep owns the actual `NSMenu`/`NSMenuItem` controls, sizing,
tracking, highlighting, submenu placement and key matching. The bridge carries
application model data and sends the existing D-Bus activation event. It contains
no control drawing, menu layout, browser command table or browser DOM access.

Firefox's pinned Linux build already exports its real menubar when both
`widget.gtk.global-menu.enabled` and `widget.gtk.global-menu.wayland.enabled` are
true. Its runtime also needs `libdbusmenu-glib.so.4`, `libdbusmenu-gtk3.so.4`, a
session-bus registrar name and `org_kde_kwin_appmenu_manager`. The two small Debian
runtime packages were extracted privately for the fixture. Firefox, libxul and
AppKit were not rebuilt. No additional Firefox binary hooks were added for menus.

The compositor accepts the standard app-menu address only for the requesting
client's own surface. The authorized shell receives it with the window PID in a
version-19 snapshot; version-18 clients retain their previous events. The address
is untrusted metadata. `host.py` resolves its unique D-Bus owner, verifies its PID
matches the selected window, and pins subsequent calls to that unique name.
Owner or bus loss cancels the native menu. Wrong-PID addresses are rejected before
native UI initialization.

For an isolated Firefox run, `FirefoxNativeUI/run-frontend-fixture.py` accepts
`--export-menus --hold --compositor PATH`, in addition to its existing pinned
browser/provider/adapter/backend/capture arguments. Add the privately extracted
runtime directories with `--library-path`. It starts a private bus and the
Wayland-only test name holder in `Tests/NativeUI/dbus-menu-registrar.py`; this
fixture is not a production desktop registrar. The fixture's `runtime.json`
contains its private bus and Wayland environment. Its authenticated compositor
window inventory supplies the browser PID and advertised menu address.

In that environment, launch the bridge with:

```sh
python3 Experiments/DBusMenus/host.py \
  --library PATH/TO/libnextspace-native-scroller.so.1 \
  --service UNIQUE_BUS_NAME --path OBJECT_PATH --owner WINDOW_PID \
  --title Firefox --output ARTIFACT_DIRECTORY -GSBackend BACKEND_NAME
```

`SIGUSR1` records current NativeUI item frames and highlights for diagnostics.
`check-firefox.py` uses those actual measurements and waits for a fresh native
highlight before releasing the physical mouse button. Compositor acknowledgment
alone does not establish that AppKit processed the input. The optional
`--owner-loss` case terminates only the browser whose PID was verified through
its owned Marionette session, while a native submenu is held.

The retained runs verify actual File > New Tab activation, native menubar and
submenu mapping, browser exit during a held submenu and clean native-host exit.
The existing 83 Firefox clipboard checks pass with menu export enabled. See
[source receipts](source-audit.json) and [qualification](qualification.json).

This remains a single-window experiment. Automatic active-window/shell
association, a production registrar, and keyboard routing shared with the native
text-editor host are not connected. Native submenu lifecycle callbacks are needed
for Firefox's lazy bookmarks/history and Edit command updates. Do not replace
those callbacks by opening every application submenu during initialization.
Live property/hierarchy handling, complete special-key and multi-chord metadata,
window/bus replacement and broader application integration remain unqualified.
The 99 projected entries do not prove that every menu command works.
