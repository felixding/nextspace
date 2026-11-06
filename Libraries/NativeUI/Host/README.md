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
are ready, then waits for its authenticated listening socket before starting
Workspace. The host requires class `user`, a private endpoint parent and an
inherited SEQPACKET role whose kernel peer is its parent supervisor. Descriptor
3 is marked close-on-exec before AppKit or D-Bus starts. The launcher supplies
`-GSBackend wayland` in the actual process arguments: changing Python's
`sys.argv` does not select Foundation's backend.

On the private bus, `com.canonical.AppMenu.Registrar` advertises the real Wayland
menu consumer. `GetMenus` returns an empty X11 registry; X11 registration methods
return an explicit unsupported error. Wayland addresses come from Workspace's
active surface and the existing authenticated D-Bus exporter binding. The
availability object uses an owned GLib context and worker so queries remain
responsive while AppKit waits or tracks a control. The worker never accesses
native menu models or widgets. All native UI work stays on the original thread.

The staged session test covers automatic launcher selection, real native menu
commands, Workspace replacement, host menu replay and teardown. It does not
establish recovery of a surviving browser's request/callback sockets after host
loss. Automatic browser adapter installation and build selection, full installed
desktop deployment and other browser/toolkit controls remain open. The host's
successful startup alone cannot establish native integration for an application.

See [supervisor behavior and qualification](../../../Applications/Session/README.md#shared-native-ui-host)
and [the broader requirement](../../../docs/Native-Control-Integration.md).
