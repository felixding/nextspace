# Wayland prototype contracts

The compositor and GNUstep backend share `nextspace-geometry.h`. Layout and
AppKit sizes are logical units. Backing density is a numerator over 120; positive
toplevel extents round to nearest with ties up. Shared edges round their absolute
position once. Damage bounds round outward. Screen drawing uses Cairo's device
scale; printing and PDF surfaces keep their existing transforms.

Toolkit protocol XML has one source under
`Libraries/gnustep/back/Source/wayland/protocols/`; the privileged shell contract
lives in `Protocols/nextspace-shell-v1.xml`. Consumers
generate headers from those sources; generated code is not committed. The upstream
XML retains its license notices. `manifest.json` records provenance and hashes.

| Interface | Current use |
| --- | --- |
| wl_compositor v4 client / v5 server | Version-clamped surfaces, buffer damage, subsurfaces |
| xdg-shell v1 client / v3 server | Ordinary windows and parent-relative popups |
| xdg-decoration-unstable-v1 | Negotiated compositor frames for supporting clients; explicit client-side preferences are honored |
| fractional-scale-v1 v1 + viewporter v1 | Per-window density, buffer scale 1, logical viewport |
| xdg-output v2 | Logical output layout, separate from physical mode pixels |
| xdg-activation-v1 | Input-authorized activation of existing toplevels |
| wl_seat v5 client, wl_data_device v3 client | Logical input, keyboard repeat, focused clipboard offers and pointer DND |
| primary-selection-unstable-v1 | Focused primary offers, separate from the persistent clipboard |
| text-input-unstable-v3 | Native text-client focus, UTF-8 surrounding text, preedit, commit and deletion |
| input-method-unstable-v2 + virtual-keyboard-unstable-v1 | Session-authorized IME, candidate surfaces and forwarding of unconsumed keys |
| nextspace_application_v1 v1–8 | Owned placement, preferred output, focus hints, levels, ordering, minimization, frame metadata/extents, validated drag context, retained presentation, read-only work areas and gesture-authorized color selection |
| nextspace_shell_v1 v1–18 | Authorized window enumeration, placement, activation, window state, desktop assignment/shortcuts, icon tracking, output transactions, input settings, desktop color, work areas, maximized dragging, frame click timing/appearance, session locking and hardware gamma |
| wlr-layer-shell v1 client | Upstream client support; not advertised by the prototype compositor |

The compositor uses wlroots 0.18.2's scene policy for preferred output and scale.
A fractional-aware client uses both fractional-scale and viewporter. If either is
missing, it uses integer buffer scaling and may be resampled. Tests distinguish
this compatibility fallback from native fractional rendering. A version-1 surface
can still use a viewport. Without viewporter or buffer-scale support it stays at
100% backing density and preserves logical dimensions.

GNUstep preserves its AppKit frame layout and retained Cairo drawing coordinates,
then submits the content region through a cropped viewport when server frames
are negotiated. Application v7 carries the owned logical insets as one pending
value, applied at the next surface commit. Invalid insets leave the last valid
value intact. Style metadata controls close, minimize and resize availability.
Version 7 also carries the owned document's edited state independently of buffer
commits. It chooses the existing broken-X close artwork and survives hide,
minimize and order-out restoration; it grants no additional window authority.
Input, drag coordinates, IME caret rectangles and parent-relative popups share
the same frame/content conversion. The native path requires viewporter and the
metrics contract; other sessions retain the existing client-frame request.

Application v8 adds an explicit color-pick interaction after a recent left-button
release or Space/Enter press in the owning window. A gesture serial is consumed once and expires
after two seconds. The compositor owns the visible magnifier and reads one scene
pixel through the renderer, excluding software cursors. Preview and selection
events carry opaque RGB channel values. Escape, right click, owner teardown,
session locking and output-layout changes end the interaction. Ordinary clients
receive neither a screenshot capability nor clicks intended to select a color.
The GNUstep bridge restores the original panel color after cancellation; an
unavailable extension beeps and returns without starting a tracking loop.

Other clients can negotiate server frames through xdg-decoration; an unspecified preference selects
the compositor frame, while an explicit client-side preference keeps the client
frame. Changes apply with the acknowledged surface commit. The frame uses
default logical extents of one point on each side, a 22-point title and a
nine-point resize bar. Native metrics preserve their existing logical layout,
including GNUstep's 23-point title. The title rerenders at the content's preferred output density.
Maximization includes the frame in the work area; fullscreen omits it. Input on
the frame belongs to the compositor and does not reach client content. Complete
native frame/fullscreen API, legacy X11 decoration and visual parity remain open.
The privileged shell global is hidden from ordinary clients.

The private test controller reports complete logical window bounds as
`width`/`height` (`frame_width`/`frame_height` are aliases). `surface_width` and
`surface_height` describe the content surface; `viewport_source` records its
actual crop in buffer pixels. Submitted native buffers retain the full AppKit
frame allocation, while the visible client surface contains only content.

## Output settings transactions

Shell version 13 reserves logical output edges for the Dock and IconYard. Insets
survive shell replacement and mode rollback, and disappear with their output.
They stay aligned to the logical desktop through scale and rotation changes.
An axis falls back to its full extent if its reservations would consume more
than half the available space. Insets do not change the hardware configuration
revision. Maximization uses the effective work area; fullscreen uses the output.

Application version 6 publishes complete read-only work-area snapshots by output
name. GNUstep maps them to `NSScreen.visibleFrame` in AppKit coordinates. A batch
replaces the preceding snapshot at its done event. Older compositors retain the
toolkit's existing visible-frame behavior. Workspace imports `NoWindowOverDock`
and `NoWindowOverIcons`, reserves 67 logical points at the primary output's right
edge and 64 at the IconYard edge, and releases reservations when those components
are hidden. The Dock follows the configured primary output.

Native `NSWindow.zoom:` uses standard xdg-shell maximization through optional
display-server hooks. The compositor retains the floating frame even when the
window has no autosave name. AppKit retains delegate vetoes and autosave handling;
custom standard-frame delegates keep their existing sizing path. Configure states
drive `isZoomed`, and leaving a bounded state preserves the accepted floating
size without applying the interactive resize grid again.

Shell version 14 imports Window Maker's `DragMaximizedWindow` preference.
`Move` keeps the maximized dimensions/state and saved floating frame;
`RestoreGeometry` restores the floating size under the same title-bar fraction;
`Unmaximize` clears the state while keeping the current size; `NoMove` denies
the drag. Fullscreen windows remain fixed. The compositor accepts moves only
with an active pointer button on the requesting window. Native requests also
validate the input serial. Escape restores both geometry and state. A moved
maximized window retains its logical displacement through output changes;
unmaximizing still restores its original floating frame. The mode survives
shell replacement and invalid values preserve the preceding mode.

Native server titles preserve left double-click shade/unshade and Control/Shift
axis toggles. Horizontal and vertical maximization share one saved floating
frame; fullscreen temporarily supersedes them. Moving a partially maximized
window updates its unmaximized coordinate, as the legacy manager does. Server
title presses begin tracking, while geometry-changing drag modes wait for the
legacy five-logical-unit move threshold. Escape restores the axis mask and frame;
the matching button release stays with the compositor even after cancellation.
Shift clicks and middle double-clicks preserve selection state and its border.
Wheel pairs preserve the legacy first-event behavior, including accumulated
high-resolution v120 steps. Remaining group actions, title menus, Command/Alternate
actions and X11 frame/axis parity are separate open gates.

Shell version 15 publishes the existing `GSDoubleClickTime` through
`set_double_click_time`; it adds no stored setting. Workspace refreshes it on
`GSMouseOptionsDidChangeNotification`, so the existing Mouse Preferences control
updates toolkit and compositor-owned gestures. Valid intervals are 1–60000 ms;
invalid values leave the previous interval intact. An actual change clears an
incomplete click pair and the interval survives shell replacement. A standalone
compositor uses Window Maker's 350 ms fallback until the shell publishes the
user's setting; the separately recorded legacy reference configuration uses
250 ms.

Shell version 7 exposes a batched inventory of connectors, hardware identity,
physical modes in pixels/millihertz, logical bounds, scale numerators and all
eight Wayland transforms. Its separate configuration object accepts exactly one
entry per connected head and the inventory revision. It rejects stale revisions,
unknown or duplicate heads, invalid scales/transforms, an entirely disabled
layout, and ambiguous primary selection before touching hardware. Physical
outputs accept advertised modes; nested outputs may test custom modes.

The compositor tests the complete backend configuration, captures the previous
layout, commits the heads, then applies all logical positions. Window recovery
runs once against the final layout. An applied configuration has a compositor
owned confirmation deadline of 1–30 seconds. Confirm retains it; cancel, object
destruction, shell loss, timeout and hotplug restore the surviving previous heads.
If the previous sole active head disappeared, rollback enables a surviving head.
Backend commits are not guaranteed atomic, so a failed commit also restores the
complete previous configuration. The private development controller can inject
a partial commit failure; this verifies recovery policy, not physical modesetting.

Workspace's protocol client publishes complete immutable output batches and
handles results in all four application run-loop modes. Both Objective-C
runtimes pass scale/transform/primary/mode/disable/re-enable and failure tests.
A real native window retains its logical size, redraws at the preferred density
and receives aligned input through rotated layouts and rollback. Physical DRM modesets
remain separate gates.

SystemKit keeps physical modes, logical frames, scale and hardware identity
separate. Workspace's session service exchanges encoded property lists, avoiding
distributed-object proxies in model values. Native profiles use a separate
schema-2 file without compositor IDs. Startup restores matching hardware and
preserves new heads; rejected profiles leave the usable initial layout in place.
Preferences Display and Screen use the same compositor transaction and shared
Keep/Revert panel. Shell v18 publishes each output's gamma ramp size and accepted
RGB exponents/brightness in the same inventory batch. Only its authorized shell
can request a LUT; results carry the request serial and follow the refreshed
inventory. Channels use SystemKit's existing power-curve convention, bounded to
0.1–10 with brightness 0–2. Requests during a pending layout and unsupported or
disabled heads fail without changing published settings. Mode changes restore
accepted ramps. Unsupported native gamma controls remain disabled; no software
fallback is presented as hardware support.

## Input settings and activation

Shell version 8 supplies keyboard rules, repeat delay/rate, numlock and normalized
libinput acceleration/profile settings. Keymaps compile before replacement;
failed device changes restore previous settings. New devices inherit the current
intent. X11 acceleration ratios remain separate from libinput's -1..1 speed.
Headless checks verify saved pointer intent and real synthetic-keyboard input;
physical device acceleration remains unqualified.

Shell version 9 carries the desktop RGB color. The compositor draws a single
opaque scene rectangle below all windows and updates its logical bounds with
the output layout. Components outside 0..1 leave the preceding color unchanged.
SystemKit and the existing Preferences color well use that same session service;
confirmed user color preferences restore at initial startup. Background drawing
does not allocate a full-screen application buffer or take pointer/keyboard focus.

Shell version 10 adds desktop count/current state and per-window assignment or
sticky visibility. The compositor retains this state across shell replacement.
Switching removes hidden desktops from drawing, hit testing and focus, dismisses
their popups and cancels active drags. Minimization remains independent. Removing
desktops recovers their windows onto the final remaining desktop; activation
selects a window's desktop. Workspace imports names into separate Wayland defaults
and keeps its Dock, Recycler and menu available across desktops. Default Control
desktop shortcuts and Command application switching have headless checks. Version
12 adds atomic custom bindings; broader keyboard-layout and desktop-menu parity
remain open.

Existing AppKit windows request focus through xdg-activation. Tokens require a
seat, a serial given to the requesting client and a focused source surface;
wlroots validates provenance at creation. Tokens expire after five seconds and
are consumed once. Missing provenance, invalid serials, unfocused sources,
unknown tokens and reuse do not change focus. Application IDs grant no authority.

## Shell connection capability

The compositor's optional `-S` argument receives an inherited AF_UNIX
SOCK_SEQPACKET descriptor. The session supervisor keeps its peer. A one-byte
`C` packet with exactly one SCM_RIGHTS descriptor supplies a connected AF_UNIX
SOCK_STREAM endpoint for a new authorized Wayland client. The shell receives the
other endpoint through `--nextspace-shell-fd FD` for Workspace's private connection;
the toolkit opens a separate public connection using `WAYLAND_DISPLAY`. The shell
never receives the broker descriptor. The independent C protocol driver uses
`WAYLAND_SOCKET` instead, since it has no separate toolkit connection.
The private descriptor is close-on-exec before helper startup. Passing its number
as a private argument also avoids GNUstep's cached `NSProcessInfo.environment`
being copied into later `NSTask` environments after a C `unsetenv`.
Both compositor descriptors have close-on-exec set. Malformed messages and
unexpected descriptors are closed without replacing the current shell.

Only that exact Wayland connection can see or bind `nextspace_shell_v1`.
Application IDs, PIDs and same-user public connections grant no authority.
Replacing the connection closes the old shell; its replacement receives a full
snapshot of compositor-owned window IDs, metadata, positions and focus. Shell
failure leaves other clients alive. Losing the supervisor broker revokes the
shell connection. The opt-in native Workspace adapter and standalone
`nextspace-session` supervisor consume this capability. Login/PAM and installed
session selection remain pending.

## Levels and retained minimization

Application extension version 3 carries AppKit levels and orders owned peers
within a level. Focus raises within the level, preserving floating windows.
Popup scene holders inherit logical parent coordinates while stacking above
ordinary/floating windows; nested popup placement and hit testing use that same
scene. Levels are constrained to -1000 through 1000 and grant no lock authority.

Minimization disables the compositor scene without destroying retained window
contents or its shell ID. The shell can restore/activate a window. Native AppKit
state notifications, miniwindow cleanup and redraw follow the authoritative state.
When a backend owns placement, AppKit leaves logical dimensions intact on
restoration or explicit frame changes; the compositor keeps the title accessible.
X11 retains its existing client-side screen constraints. Client-frame shading
clips the scene and input to the declared title height without resizing the
logical window or its buffer. Minimize/shade dismiss child popups and refresh
pointer focus even without motion. Desktop grouping, hide/unhide and workspace
policy remain open.

Shell version 4 also suppresses mapped surfaces independently of minimization.
Dock/IconYard visibility therefore preserves AppKit state, buffers and IDs.
Suppressed windows leave hit testing and focus selection; activation restores
presentation. This is presentation policy, separate from application hide events.

Application version 5 supplies client-owned presentation without recreating the
toplevel. Client suppression and shell suppression are independent; both must
permit presentation for a window to be visible. Hide/unhide therefore retains
shade, desktop, geometry and identity, and shell icon layout cannot reopen an
AppKit-hidden miniwindow or menu. Older clients retain their previous contract.

Shell version 12 replaces all 18 desktop key bindings as one validated array.
Keysyms use the active layout's unshifted level, with explicit Shift/Control/Alt/
Logo masks; Caps Lock and Num Lock do not change matching. Duplicate bindings,
unsupported masks and malformed array lengths preserve the preceding table.
Workspace imports existing WM accelerators and stores native edits separately
under `WaylandShortcuts`. Its existing Desktops view controls names, count and
switching prefixes through the same session settings service.

## Image representations

Image selection includes the current window's backing density without changing
its logical device resolution. Higher-density screen contexts draw original
representations directly, avoiding fixed-resolution intermediate caches and
fractional boundary resampling. Printing and 100% screen caching retain their
existing paths. Vector image compositing uses Cairo groups at the target density, preserving
cropping, opacity and device-pixel phase. Allocated view graphics states rebind
when backing storage changes. Submitted-buffer PNG checks compare fine vector
interiors with direct drawing, excluding only the outer pixel affected by image
clipping; separate checks cover cropped opacity and distinct 1x/2x bitmap assets.

## Cursor density

Cursor surfaces have their own output membership and preferred fractional scale,
independent of the focused window. Custom images select a suitable representation
and render into a fresh immutable Cairo/shm buffer. Logical size and hotspot stay
fixed; ordinary theme cursors select a higher-resolution theme at fractional
scales. Hide/unhide preserves the current image. Older surfaces and missing
viewporter/fractional-scale globals follow the same integer/100% fallback rules.
The compositor refreshes cursor output membership during movement to cover a
wlroots 0.18 behavior that otherwise waits for an image commit. Tests cross the
same spanning window between outputs without changing its backing preference.

## Owned window placement

`nextspace_application_v1` accepts only an owned `xdg_toplevel` surface. Each
surface has at most one window object. `set_position` requests logical top-left
coordinates; the compositor returns its authoritative position and preferred
output name. These names match xdg-output names. Requests must retain an accessible
title strip; invalid or disconnected-output positions recover onto an enabled
output. Version 2 lets auxiliary windows decline keyboard focus. A menu then
receives pointer input while its application's document keeps the keyboard;
the hint cannot activate another window or application. Version 1 placement
clients remain supported. The extension grants no access to other clients or
output settings.

The backend converts returned positions into AppKit's bottom-left space and
updates `NSWindow.frame`/`screen`. Xdg popup offsets remain parent-relative; edge
constraints and movement of the parent also update the popup's AppKit coordinates.
Without this extension, absolute placement remains a local estimate. Standard
xdg-shell still supplies logical sizing, fractional backing and popup placement.
The [backend's other-compositor contract](../Libraries/gnustep/back/Source/wayland/README.md#other-wayland-compositors)
records the remaining window-policy limits and the independent Weston check.

Ordinary configure replies honor AppKit min/max sizes and snap cell increments
relative to the minimum size. Fullscreen/maximized replies accept the compositor's
dimensions. The native Terminal path skips its X11-only base-size hint.

## Pasteboard and Services boundary

The session launcher must supply a fresh `NEXTSPACE_SESSION_ID` (1–64 ASCII
letters, digits, hyphens or underscores) to native clients and `gpbs-wayland`.
Storage and Services registration names include it. Unset IDs preserve the
existing X11 names; `gpbs-wayland` rejects an unset ID. The native executable uses
the existing GNUstep storage implementation without its X selection component.

Focused clients offer snapshots of the general pasteboard after a valid key or
button serial. Native writes are coalesced after the AppKit operation completes;
publication never starts inside a DO reply. Transfers use pipes, asynchronous
writes with nonblocking backpressure, and run-loop reads with a size/timeout bound.
GNUstep types remain in per-session storage; Unicode text maps to UTF-8 MIME types.
A session marker prevents reimporting that session's existing data. It grants no
authority. External offers are materialized into storage before their owner exits.

Xwayland uses the compositor's single wlroots selection bridge. Native and X11
Unicode transfers over 64 KiB pass in both directions, including X11 INCR. The
existing Services API passes Unicode and opaque data through the same storage.
The compositor asynchronously snapshots clipboard offers, then owns the copied
data after the originating native, protocol or X11 client exits. A global 64 MiB
payload budget includes MIME aliases and snapshots retained by active readers;
capture and transfer deadlines are five seconds, with at most 16 outgoing
transfers. A stalled producer times out without blocking output changes.
Explicit empty selections cancel capture and clear compositor ownership.
The GNUstep storage bridge does not yet mirror external selection clearing;
primary selection and broader transfer qualification remain open.

## Pointer drag boundary

The compositor validates the origin's pointer-grab serial before starting DND.
Its scene drag image ignores input. Leaving a surface clears the drag grab's
focus, so releasing over the desktop cannot drop into the previous target.
Escape and source-window destruction cancel the gesture.

Native sources freeze their bytes before starting. Clipboard and DND share MIME
conversion and bounded nonblocking transfers. Local file lists use `text/uri-list`,
with a 4 MiB/4096-entry limit and validation of absolute local paths. Malformed
UTF-8, remote hosts and NUL paths are rejected. AppKit enter/motion/drop delivery
is deferred outside Wayland callbacks and serialized across reentrant pasteboard
reads. Successful completion follows the target's prepare/perform result. A
five-second cumulative I/O budget excludes time spent hovering or deciding.

Application extension version 4 reports a compositor-assigned gesture ID,
connection locality and logical desktop pointer coordinates to owned surfaces.
It preserves the same sequence across leave/reentry and supplies the source's
completion coordinates. `prepare_drag` provides local/external copy/move masks;
the compositor intersects them with the advertised source actions before creating
each destination offer. IDs and process names confer no authority. Standard
data-device completion remains authoritative. Older servers retain transfers
with reduced metadata.

Native/GTK transfers and transfers into Xwayland GTK receivers cover text, file
URIs, copy/move, cancellation and receiver/source closure. The pinned wlroots
patches keep literal MIME atoms in XDND offers and retain/validate completion,
including failed or closed receivers and source-less gestures. They preserve its
single XWM and selection bridge. Incoming X11 DND, complete modifier/action and
promised-file semantics, return animation and application workflows remain open.

## Private development controller

`nextspace-compositor -c FD` accepts an inherited AF_UNIX/SOCK_SEQPACKET descriptor.
There is no named control socket, app-ID authorization or same-user grant. The
launcher must pass the descriptor only to its trusted controller. Each packet is
one ASCII request; each response is a JSON packet. This is a development API,
version 1, not the final Workspace protocol.

Requests: `outputs`, `windows`, `popups`, `cursor-state`, `drag-state`, `pointer-focus`, `hit X Y`, `selection`, `selection-state`, `move ID X Y`,
`resize ID WIDTH HEIGHT`, `close ID`, `focus ID`, `pointer X Y`,
`button LINUX_CODE [PRESSED]`, `scroll DELTA`, `key LINUX_CODE PRESSED`, `x-display`, `add-output`, `remove-output NAME`,
`resize-output NAME PHYSICAL_WIDTH PHYSICAL_HEIGHT`, `output-position NAME X Y`,
`test-scale OUTPUT NUMERATOR TIMEOUT_MS`, `confirm`, `quit`. Input injection is
available only through this inherited capability. Scale tests allow one pending
change, validate before applying, and revert on timeout or controller disconnect.
The synthetic keyboard exists only with this descriptor. Output add/remove is
limited to headless outputs and refuses to remove the last enabled output.
Physical-mode and layout-position test changes also require headless outputs.
Unplugging the affected output cancels that pending transaction. Confirmed scale
changes last for this compositor process; preference persistence is not implemented.

Without the control descriptor the compositor accepts ordinary Wayland clients
and real input devices. `-F` and `-V` suppress fractional-scale or viewporter for
compatibility tests. `-A` omits owned placement; `-1` advertises surface version 1.
SIGINT/SIGTERM shut down clients and the display cleanly.
`-d` enables wlroots diagnostics.

### Text input and the input method

Text-input-v3 is public. Input-method-v2 and virtual-keyboard-v1 are visible only
to the exact connection passed with broker role `I`; role `C` remains Workspace.
`nextspace-session --input-method EXECUTABLE` creates the optional connection,
sets `WAYLAND_SOCKET` in that child, restarts a failed method at most twice in a
10-second failure window, and falls back to direct keys on repeated failure.
The method cannot bind shell control. Supervisor loss revokes both capabilities.

The compositor sends text focus only to the owning client, invalidates method
transactions on focus changes and forwards accepted preedit/commit/delete batches.
Physical keys go to an active method grab after desktop shortcuts; virtual keys
from that method go to the application without looping through the grab. Candidate
surfaces follow the logical caret and remain inside the selected output.

GNUstep applies batches on the application run loop. Surrounding text excludes
preedit, is bounded below the protocol's 4,000-byte limit, and is empty for secure
field editors. UTF-8 byte boundaries are validated before deleting UTF-16 text.
Missing text-input support retains ordinary keyboard and local compose behavior.
Terminal exposes composition at its cursor without treating scrollback as editable
surrounding text. The protocol fixtures do not qualify a particular IME engine.
