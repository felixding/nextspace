# Native session supervisor

`nextspace-session` is built beside the compositor by its Meson project. It is
an opt-in process. A native greetd/Login candidate now uses the same supervisor
for its greeter compositor and private bus; real headless PAM/logind ownership
and logout/regreet pass. A headless real-PAM run also hands off to actual native
Workspace/Preferences, cancels logout, redraws at 125%/150%, then completes
ordinary logout through the visible button and returns to Login. Headless
session locking now passes with the compositor contract and packaged PAM locker
on both runtimes. Idle locking, actual suspend/VT transitions, physical
lifecycle and clean installed session packaging remain separate
migration gates. The current session and packages are native Wayland only.

```sh
nextspace-session --compositor /path/to/nextspace-compositor \
  --locker /path/to/nextspace-wayland-locker -- \
  /path/to/Workspace.app/Workspace -GSTheme NextSpace
```

The installed `nextspace-wayland-session` launcher selects `--private-bus` and,
without arguments, starts the installed native Workspace. It
requires an already authenticated user with a valid PAM/logind runtime and seat;
it does not perform authentication or install a login-screen session choice.
The compositor install places the launcher beside `nextspace-session`.
The user launcher also selects `--session-hook nextspace-session-hook`. The
Foundation helper reads `LoginHook` and `LogoutHook` from the authenticated
user's `Library/Preferences/.NextSpace/Login` file. Login runs once after the
native display is ready and before Workspace starts; shell recovery does not
repeat it. Logout runs after Workspace finishes and before display/service
teardown, including session failure and cancellation. Hook failures contribute
to the session exit status while allowing the remaining lifecycle to finish.
Empty hooks do nothing. Executable paths containing spaces and literal argument
arrays are supported; existing whitespace-separated commands retain their old
parsing. Hooks execute without shell interpretation or a privileged protocol
descriptor. The greeter cannot select this user-only option.

The sibling `nextspace-wayland-greeter` launcher requires an unprivileged greetd
session and selects Login by default. Both launchers accept explicit supervisor
arguments for staged binaries. The greeter publishes class `greeter`; the user
launcher selects `user` and clears `GREETD_SOCK`. See
[`Login/README.md`](../Login/README.md) for the candidate's remaining gates.

With `--private-bus`, the supervisor owns a fresh `dbus-daemon` and publishes the
actual display sockets, runtime directory, native backend and desktop metadata
before starting Workspace or an input method. `DISPLAY` remains unset.
Inherited X11 authority and capability descriptors
are cleared. This needs `dbus-daemon` and `dbus-update-activation-environment`.
It does not modify the account-wide systemd user environment. Bus loss ends the
graphical session; activated service descendants are included in owned-child
cleanup even when they ignore termination. Bus startup and environment
publication have bounded waits. Its socket lives in a private directory under
`XDG_RUNTIME_DIR`; cleanup removes that directory even after forced bus loss.
Address escaping preserves runtime paths containing spaces or delimiters.
Shared user services, portals, full Login/user-desktop integration
and installed greeter configuration remain separate integration gates.

An optional `--input-method /path/to/executable` starts a Wayland input method
on its own capability connection. Use an executable wrapper when the method
needs arguments. It receives input-method-v2 and virtual-keyboard-v1 access;
the public socket does not grant either. Two rapid method restarts are allowed,
then the session keeps ordinary keyboard input available. Real Fcitx5 Pinyin
passes native AppKit input on both runtimes and Terminal PTY input on the modern
runtime across five densities through the authorized relay. Installed engine
selection, supervisor/engine restart workflows, other engines and candidate
visual parity still require qualification.

`--locker /path/to/executable` selects a foreground session locker. The default
user launcher selects `nextspace-wayland-locker`, which runs Debian's packaged
PAM `swaylock` with a fixed configuration. Its private connection alone can bind
`ext-session-lock-v1`. Ctrl-Alt-L, shell version 17's `lock` request, or SIGUSR1
sent to the supervisor requests locking. The compositor hides ordinary surfaces
and input before the locker starts, then acknowledges only after blank frames
have been presented on every enabled output. The greeter ignores these user
lock requests.

Locker exit never authorizes unlock. Only the authorized protocol request restores
the desktop. A crashed or hung locker receives up to three attempts; startup has
a ten-second deadline. Repeated failure leaves the desktop hidden. SIGUSR1 sent
to the supervisor retries recovery. SIGUSR1 remains blocked in locker children
because packaged swaylock otherwise uses it as a password-free unlock signal.
Five-density real-PAM tests cover wrong passwords, recovery, this signal mask,
zero-status helper exits, timeouts and owned-child cleanup. The existing eight
lifecycle modes also pass on both runtimes. One earlier installed-launcher failure
remains retained without a proven cause; subsequent serial installed runs pass.
The current external locker uses integer output scale. Fractional-sharp locker
artwork, idle locking, actual suspend transitions, physical displays and installed-session
release qualification remain open.

With a configured locker, the supervisor also watches its actual logind session.
`GetSessionByPID` resolves the session from the process; an inherited session ID
does not select it. Only that session's `Lock` signal from logind requests locking.
The compositor's acknowledgement and authenticated unlock publish `LockedHint`
asynchronously. Logind's `Unlock` signal does not bypass PAM. A missing session,
denied hint or lost system-bus connection leaves explicit locking available.
This adds the `libsystemd` build/runtime dependency.

Owned fake-bus tests pass on both runtimes, including wrong paths/senders, denied
hints and bus loss. A separate real greetd/PAM/logind session in Lima passes all
five densities, actual `loginctl lock-session`, locked-hint changes, authenticated
recovery, logout/regreet and complete account/service cleanup without changing
the active VT.

The supervisor holds a logind sleep-delay inhibitor. `PrepareForSleep(true)`
requests a compositor guard, which acknowledges only after every enabled output
has presented protected pixels. That acknowledgement releases the inhibitor;
it does not wait for a responsive locker. Authentication cannot reveal the
desktop until trusted logind resume state clears the guard. Resume keeps the
desktop locked, reacquires the delay inhibitor and still requires PAM unlock.
Queued resume/sleep notifications retain the newest sleep guard. Losing the
system bus or logind owner also guards the desktop until PID-based reconnection
confirms the current sleep state; a held inhibitor survives that disconnect.

Both runtimes pass owned-bus tests with measured presentation/release ordering,
a hung locker, guarded authentication, bus/owner restarts and inhibitor
reacquisition. Lima verifies a real delay inhibitor belongs to the authenticated
supervisor and disappears on exit. These tests do not suspend the guest.
Automatic idle locking, actual suspend/resume and VT switching remain open.

The caller supplies a private, user-owned `XDG_RUNTIME_DIR`. The supervisor creates
a fresh `NEXTSPACE_SESSION_ID`, selects the native backend, clears inherited
display descriptors and waits for the compositor's actual public socket and
optional Xwayland display. It passes a private shell endpoint as
`--nextspace-shell-fd FD`; Workspace never receives the broker. Other inherited
descriptors are closed in children. This Linux implementation requires
`close_range`, exercised in the Linux headless validation environment.

A failed Workspace receives a replacement capability. Existing clients and
compositor state survive. Three failures within ten seconds end the session.
Only the initial Workspace receives `--nextspace-restore-settings`: it restores
confirmed display profiles and saved input preferences before autolaunching apps.
Replacement shells preserve live compositor settings.

Greeter sessions can instead pass `--greeter-profile EXECUTABLE`. The supervisor
runs this helper once on its own authorized connection before starting Login.
`nextspace-display-profile` reuses Workspace's connection and SystemKit model to
restore the greeter account's confirmed display profile. Missing/invalid profiles
preserve the safe layout. Failure or a ten-second timeout closes the preparation
connection and still starts Login, which receives no shell descriptor. The
default greeter launcher selects this helper; ordinary user sessions reject the
option and continue restoring settings through Workspace.

An ordinary Workspace exit ends the session; exit 129 retains the existing
power-off result. Native Workspace sends the power request through the shared
SystemKit/logind API after applications agree to quit. The bounded request runs
off the UI thread; denial or timeout keeps the desktop and permits another
attempt. Acceptance completes Workspace teardown. Greetd itself does not
interpret 129 as a power request.
Compositor loss ends the session with an error.

The native UI passes nine owned-fake-bus power cases at 100%, 150% and 200%,
including repaint during a pending reply and Return-key error dismissal. No
actual power action is sent during these tests. Two earlier runs missed a quit
shortcut after a fresh Workspace restart; those failures remain retained without
an established cause. Later traced and uninstrumented runs pass. Actual power
policy, real-session shutdown and full release qualification remain open.

The nine cases also pass under a real greetd/PAM/logind user scope through the
production supervisor. Three accepted exits return 129, reap all 21 owned
processes and remove their private buses before PAM closure and regreet.
Dialog placement is checked against its owning monitor, including gaps and
negative origins. Temporary accounts/services are removed and the active VT
stays unchanged. Power methods still target an owned fake bus, so actual
authorization and shutdown remain unqualified.

The supervisor owns its process group and adopts orphaned descendants, including
applications that GNUstep's `NSTask` starts in separate groups. Teardown sends
termination, then force-stops and reaps remaining owned children. Shared user
daemons must be placed outside the graphical session's ownership during Login
integration; concurrent user-service lifecycles and logind scopes remain
unqualified. No workstation login/session entry is installed by this prototype.

## Shared native UI host

The user launcher automatically selects a sibling `nextspace-native-ui-host`
when the optional foreign-control package installs it. `NEXTSPACE_NATIVE_UI=off`
disables that selection. An explicit supervisor invocation can instead pass
`--private-bus --native-ui-host EXECUTABLE`; use a foreground wrapper for host
arguments. This option requires an authenticated user session and is rejected
for the greeter or without a private bus.

The supervisor creates a private directory, owns the mode-0600 listener and
publishes `NEXTSPACE_NATIVE_UI_SOCKET` to ordinary children and D-Bus activation.
Before starting LoginHook or Workspace, it waits for the owned host's
authenticated preparation and restoration handshake. The host receives a
private menu role on descriptor 3 and a connection activation role on descriptor
4; Workspace receives its separate menu relay as
`--nextspace-native-menu-fd 4`, alongside its shell descriptor 3. Neither receives
the compositor broker, and inherited capabilities close on child execution.

Workspace supplies active-window menu addresses through the relay. The host
uses the shared bridge and actual GNUstep controls; the supervisor interprets
no menu models. The latest opaque selection is replayed after host restart.
The supervisor also announces its ready host's actual PID (zero while absent)
as a separate `host` notice on the private Workspace role. This does not
acknowledge a selection request. Workspace uses that authenticated identity to
present the active foreign application's native menus and hide inactive native
applications' menus. Replacement therefore works without changing browser focus
or guessing ownership from a process name or window title.
Workspace restart replaces its private role while preserving the browser and
host. Serial correlation prevents replies to an obsolete request from reaching
a replacement shell. One request is in flight; request/reply sizes and waits
are bounded. Startup has a ten-second deadline; a menu reply has thirty seconds.
After three failures the optional host is disabled and desktop startup proceeds.
Ordinary teardown stops owned processes and removes the private native state
without following symlinks.

Accepted client sockets and verified owner capabilities remain in the supervisor
across host loss. A replacement receives duplicates of those original endpoints,
eventfds, pidfds and callback sockets. Sandboxed renderers keep their existing
connection and original kernel sender credentials; they do not reconnect or
gain another sandbox permission. The supervisor stores no control, text or menu
model and never proxies application RPCs. Dead owners are discarded. A new host
epoch invalidates older callback proposals and queued Chromium menu actions;
the adapters rebuild native objects from their live application models. Edits
and commands are not replayed. Ordinary teardown asks the host to stop before
its display and private bus are removed, with bounded signal escalation.

The shared host selects one application menu for the active process. An
authenticated direct browser model takes precedence over that process's D-Bus
exporter. Both paths use the same native menu implementation. Keys received
reentrantly during native menu validation wait for that native call to return;
expired keys return unhandled without applying a late edit.

The host advertises the real Wayland menu consumer on the private bus. Its
availability service explicitly rejects X11 window registration. Only these
read-only availability calls use a worker; native models, widgets and actions
stay on the host UI thread. See [host details](../../Libraries/NativeUI/Host/README.md).

The headless staged checks use actual Workspace connection classes and unchanged
Firefox and Chromium binaries. They cover native fields and application menu
commands before and after host loss, switching between the two browsers,
activation inheritance, retained Firefox renderer sandboxing and complete
teardown. Chromium's recovery keys enter through the real compositor seat;
Firefox field transactions use Marionette and its menu keys use that seat.
The normal user launcher runs with a private backend configuration and a no-op
test hook. Full installed Workspace/PAM login, automatic browser adapter
installation/selection, additional controls and derivative builds remain open.
See the [recovery qualification](native-ui-recovery-qualification.json) and
[earlier startup qualification](native-ui-qualification.json).
