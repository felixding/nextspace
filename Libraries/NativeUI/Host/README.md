# Session native UI host

This foreground process hosts the shared bridge against the independent native
UI library. It reuses `Experiments/ChromiumScrollers/helper.py` and the D-Bus menu
binding modules. It adds session startup and consumer availability, without
implementing controls, key tables, artwork or editing rules. All widgets remain
GNUstep/AppKit objects supplied by the selected provider.

The ForeignScrollers CMake install places `nextspace-native-ui-host` in `bin`
and its Python modules in `libexec/nextspace-native-ui`. It also installs the
legacy scroller shim and the independent native UI loader/provider. The host
requires Python 3, PyGObject and the GLib/Gio introspection runtime. The optional
Debian package declares those dependencies. A provider-only build does not
install this transport host.

The session supervisor starts the host after the native display and private bus
are ready, then waits for its authenticated restoration handshake before
starting Workspace. The supervisor owns the listener and retains accepted
connections across host loss. The host requires class `user`, a private endpoint
parent and inherited SEQPACKET roles whose kernel peers are its parent
supervisor. Descriptors 3 (menus) and 4 (activation) are marked close-on-exec
before AppKit or D-Bus starts. The launcher supplies
`-GSBackend wayland` in the actual process arguments: changing Python's
`sys.argv` does not select Foundation's backend.

On the private bus, `com.canonical.AppMenu.Registrar` advertises the real Wayland
menu consumer. `GetMenus` returns an empty X11 registry. The compatibility
acknowledgment for Qt 6.8's legacy menubar call preserves its exported D-Bus
object. Menu selection still uses the Wayland surface owner. X11 registry queries
return an explicit unsupported error. Wayland addresses come from Workspace's
active surface and the existing authenticated D-Bus exporter binding. The
availability object uses an owned GLib context and worker so queries remain
responsive while AppKit waits or tracks a control. The worker never accesses
native menu models or widgets. All native UI work stays on the original thread.

`connections.py` restores original client sockets and authenticated notification,
lifetime and callback descriptors. Original kernel credentials still identify
request senders. It restores subscriptions before accepting requests, advances
callback serials to a new epoch and signals owners to reconstruct native objects
from their live models. It stores no native controls or application data and
replays no edits or commands. The supervisor's private `Activation.h` protocol
is separate from the provider's C ABI. A stop packet lets AppKit finish before
the session removes its display.

Menu selection prefers the active process's authenticated direct model over
its D-Bus exporter, avoiding two competing native main menus. Native menu busy
state comes from the provider. A reentrant key waits until validation returns,
with a bounded expiry that prevents late edits after application fallback.

The staged checks cover automatic launcher selection, native fields and menu
commands, Workspace replacement, surviving Firefox/Chromium request and callback
sockets, menu switching and teardown. See the
[recovery qualification](../../../Applications/Session/native-ui-recovery-qualification.json).
Automatic browser adapter installation and build selection, full installed
desktop deployment and other browser/toolkit controls remain open. Successful
host startup alone cannot establish native integration for an application.

See [supervisor behavior and qualification](../../../Applications/Session/README.md#shared-native-ui-host)
and [the broader requirement](../../../docs/Native-Control-Integration.md).
