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
AppKit were not rebuilt. Menu extraction uses that existing exporter; the
optional lifecycle callback binding is described below.

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
The earlier static-menu fixture passed 83 Firefox clipboard checks with export enabled. See
[source receipts](source-audit.json) and [qualification](qualification.json).

## Native submenu lifecycle

Pass `--lifecycle` with a provider advertising `NXS_MENU_LIFECYCLE` to prepare
lazy submenus through real native open/close callbacks. This sends the exporter
its actual opened/closed events, then reads the current layout. Only the branch
being opened is replaced before GNUstep sizes and tracks it.

Firefox may rebuild every exported item when a submenu opens. `menu_model.py`
keeps opaque native identities separate from exporter IDs. It matches stable
IDs first, then uniquely matching sibling metadata, and retires ambiguous
identities. Layout updates continue during tracking; command execution resolves
the latest exporter ID. The model contains no native widget implementation.

`check-lifecycle.py` uses an owned Firefox fixture to exercise native Edit Undo
and Redo and a three-level real Places bookmark menu. Clear the navigation
fragment before each bookmark gesture. Opening the real native branch must
initialize or refresh its lazy Places model; closed views can stop observing it.
`Tests/NativeUI/check-dbus-menu-model.py` checks identity churn and atomic
rejection independently of the browser.

The optional pinned Firefox adapter lifecycle binding uses Gecko's existing
trusted-event dispatcher to keep its hidden internal menubar inactive after
exported popup events. `run-frontend-fixture.py --export-menus` enables
`NEXTSPACE_FIREFOX_MENU_LIFECYCLE=1`. This fixes the empty internal toolbar and
the clipboard suite's dismissal failure without changing DOM attributes or
copying Firefox's toolbar logic. The expanded lifecycle check accepts
`--require-menu-lifecycle-binding` and checks geometry while native menus are held.

`menu_events.py` refreshes and resolves an identity again only after libdbusmenu
explicitly rejects that exact ID before queueing any event. Recovery is bounded;
uncertain results, timeouts and disconnects are never retried. Its protocol test
is `Tests/NativeUI/check-dbus-menu-events.py`.

## Share the native text and menu responder host

`binding.py` contains the single reusable D-Bus model binding. `host.py` runs it
as a standalone CLI; the existing control helper can host the same binding in
its own `NSApplication`. This lets GNUstep's real application menu match key
equivalents before its real field editor interprets editing keys. The bridge
translates exported shortcut metadata and contains no application shortcut table.

`FirefoxNativeUI/run-frontend-fixture.py --export-menus --shared-menus` supplies
the owned browser's real compositor window/address metadata through an inherited
Unix SEQPACKET descriptor. The helper accepts this opt-in role through
`--dbus-menu-fd`; renderer connections cannot register application menus.
Each address is authenticated against the unique D-Bus owner's kernel PID.
Text focus/key requests additionally require the control's own connection, its
authenticated notification connection and live PID, and ancestry under the
bound browser. A rejected replacement preserves the existing menu. Clear,
replacement, channel loss and application exit cancel and dispose the binding
without shutting down the shared field helper.

Key-triggered application actions are queued until the helper has returned the
native input RPC reply. Their opaque identities are then resolved against the
current real exporter before delivery. Waiting synchronously inside that RPC
would deadlock a browser UI thread awaiting the helper. GLib's public poll
descriptors/deadlines join the provider's existing native descriptor sources;
there is no widget polling timer. The embedding pump services descriptors
without recursively dispatching native tracking events.

`check-shortcuts.py` verifies physical native Undo/Redo and Emacs navigation in
both webpage and address fields. `check-shared-host.py` checks ownership,
rejection, clear/rebind and idle behavior. The existing clipboard checker adds
`--command-filter --application-menus` to require exactly one native menu queue
and actual exported activation for Paste with empty helper storage. Its default
field-command callback assertions remain intact. Shared snapshots use the
inherited descriptor; signals may wait while Python is inside a blocking native
dispatch. The owner-loss check requires the shared helper to remain alive.

## Workspace window association

Workspace now binds shell protocol 19 and receives each real window's advertised
address in its complete private compositor batch. `activeApplicationMenu` selects
the focused native Wayland window; legacy/unpresented/minimized and no-menu
applications do not supply a foreign menu. `WSNativeMenuConnection` forwards the
selection over an optional `--nextspace-native-menu-fd` inherited SEQPACKET role.
Workspace consumes it before AppKit can start helpers and marks it CLOEXEC.
The helper retains unique D-Bus-owner/PID authentication.

This connection uses native run-loop descriptor events, nonblocking writes and
one outstanding reply. Later focus changes coalesce to the latest address.
Geometry updates do not rebind. Rejecting the current address clears the old
application's menu and suppresses retries of that unchanged rejected identity.
Shell/channel loss clears the menu while the field helper survives. The role
packet limit is 8192 bytes, accommodating bounded protocol address metadata.

`run-frontend-fixture.py --export-menus --shared-menus --menu-shell-probe PATH`
uses the actual Workspace connection classes rather than manually sending bind
requests. `check-workspace.py` verifies two Firefox windows, real native menu
commands from their address fields, switching to TextEdit and back, and shell
role loss. `Tests/Wayland/appmenu.py --workspace-probe PATH` independently checks
metadata, rejection, delayed replies/coalescing and descriptor inheritance.

The current experiment does not complete browser integration. Standard session
supervision still needs to launch/package the shared host and supply its role;
the installed desktop is not automatically enabled by this change. A retained
live failure also establishes that shortcuts from the webpage body never reach
the helper: current keyboard hooks cover native fields only. Global browser
shortcut routing, ambiguous rebuilt sibling identities, changes to an already
visible branch, special-key metadata, registrar/bus recovery and other
browser/toolkit controls remain open. See [Workspace association qualification](workspace-qualification.json)
and the preceding [shared-host qualification](shared-host-qualification.json).

See the Firefox [menu lifecycle qualification](../FirefoxNativeUI/menu-lifecycle-qualification.json)
for the current toolbar, root-window and event-delivery fixes.
[lifecycle-qualification.json](lifecycle-qualification.json) retains the preceding
checkpoint and its failure; [qualification.json](qualification.json) records the
earlier static menu checkpoint.
