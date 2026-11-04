# Native greeter candidate

The default build is native Wayland only. Startup requires greetd's
`GREETD_SOCK`; Login rejects root execution and
requires the native Wayland backend. The existing Gorm panel and NeXT alerts
handle the asynchronous PAM conversation. The GUI verifies the IPC peer is root;
greetd owns authentication, account checks, credentials, PAM sessions and the
transition to the authenticated user.

`nextspace-wayland-greeter` runs Login through the existing `nextspace-session`
supervisor. Each greeter and user role owns its compositor, private bus and
children. The greeter role publishes `XDG_SESSION_CLASS=greeter`; the user launcher
selects `user` and clears the greeter socket. Both launchers find the supervisor
beside themselves. No additional privileged authentication daemon is introduced.
Login does not use the Workspace control protocol, so the supervisor withholds
that capability from the greeter and its toolkit helpers.

Before starting Login, the default greeter launcher runs `nextspace-display-profile`
on a separate, short-lived authorized connection. It restores the greeter account's
`~/Library/Preferences/.NextSpace/WaylandDisplays.plist` through the same SystemKit
model, stable display identities and compositor transactions used by Workspace.
An administrator can copy a confirmed display profile into that account's private
preferences directory. Disconnected heads are ignored; new heads retain their
safe settings. Missing, invalid or all-disabled profiles keep the usable startup
layout. Preparation has a ten-second deadline; helper failure also permits Login
to start. Login never inherits this connection. A fresh greeter after logout
restores its own profile independently of the authenticated user's preferences.

The default authenticated command is
`/usr/NextSpace/bin/nextspace-wayland-session`. A system Login preference named
`NativeSessionCommand` can select an argument array instead. Each argument is
quoted literally for greetd's shell execution; greeter display sockets, bus and
capability descriptors are not passed as session environment variables.
Native panel animations advance by elapsed time and await AppKit's asynchronous
move acknowledgments before restoration. The final five-density UI matrix
measures 0.24–0.32 seconds between authentication success and the session request.

Greeter power buttons retain their confirmation dialogs and send normal logind
requests through SystemKit. Policy denial or failure leaves the panel usable.
Requests run off the UI thread. The adapter is tested against a private fake bus;
actual shutdown/reboot and policy/inhibitor qualification remain open.

The tested manager is Debian greetd0.10.3-4. Its IPC and exact extracted source
were checked; its package/service has not been enabled as the default manager.
Do not run the greeter script directly as root. An example configuration for an
already prepared unprivileged greeter account is:

```toml
[terminal]
vt = 1
[general]
service = "greetd"
[default_session]
user = "greeter"
service = "greetd-greeter"
command = "/usr/NextSpace/bin/nextspace-wayland-greeter"
```

This example is not installed or enabled automatically. PAM services, seat/VT
ownership and a private user-owned `XDG_RUNTIME_DIR` must be supplied by the
manager. Physical seat/VT integration remains under qualification.
The headless PAM fixture also starts the actual native Workspace and its
autolaunched Preferences, redraws at 125%/150%, cancels logout, then uses the
visible Log out button to close the user session and return to a fresh greeter.
Owned user processes and the private bus are removed. This exposed and fixed a
native application registration race and a window-manager callback after model
teardown. Three further real-PAM cases cancel logout, redraw at 125%/150%, then
confirm normal logout with Return and reach a fresh greeter. The shared alert
initialization now registers the loaded default button; ten native alerts at
five densities and all seven Login UI modes pass. An earlier traced old-library
run also passed, so the original intermittent keyboard failure remains retained
without a proven cause.

Installed greeter configuration, active-VT/GPU behavior,
lock, shared user services, asset parity and final packaging/release gates
remain open.

The native build reconstructs all seven Login designs at 100%, 125%, 150%, 175%
and 200%. The panel preserves the original OPENSTEP lettering, colored NeXT cube,
shaded background, separators and frame using continuous geometry and gradients.
Repeated letter outlines share one definition. The fields share one inset shape,
with their original logical dimensions, transparent gap, white fill and gray
bevels. Name/Password labels and Power/Restart captions use shared, manually
drawn letter geometry. The buttons retain the original closed power ring,
restart arrow, bevels, palette and pressed-caption displacement. Their curves
render independently at each density; source TIFFs remain the design references.

The archived Gorm model establishes gray normal button images (`*buttonup`) and
white/red highlighted images (`*buttondown`). The loader preserves that mapping.
Seven device-selected originals are pinned under `Tests/Wayland/artwork-originals`.
`login_fidelity.py` checks all seven reconstructions against those originals.
Forty-seven negative controls reject changed geometry, palette, lettering,
raster-grid shading, traced captions and bitmap enlargement.
`login_fields.py` checks the real greeter's panel, fields, labels, image assignments
and twenty normal/pressed button states across all five scales. This qualifies
the Login artwork in the private native fixture; installed PAM/session
integration and the full package lifecycle remain separate gates.
