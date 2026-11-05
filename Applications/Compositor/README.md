# nextspace-compositor

Native Wayland C/wlroots compositor. Build it with
Meson; keep NEXTSPACE applications on GNUmake:

```sh
meson setup .build/compositor Applications/Compositor
meson compile -C .build/compositor
meson test -C .build/compositor --print-errorlogs
```

The initial target is Debian 13 with wlroots **0.18.2**. The unstable wlroots API
is pinned exactly. The production dependency disables Xwayland and the X11
backend. The disposable runner builds it
from its verified upstream archive; its source hashes are retained with results.
`wlr_backend_autocreate` selects a nested Wayland or hardware
backend from the environment. Automated tests select `WLR_BACKENDS=headless` and
`WLR_RENDERER=pixman`; DRM/KMS and GPU support have not been qualified.

The compositor clears inherited `DISPLAY` and X11 authority. Its session uses
native Wayland clients exclusively; no X server or selection bridge is started.

The authorized shell imports all four existing `DragMaximizedWindow` modes.
The default keeps maximized size/state while moving; Escape restores the prior
frame and state. Fullscreen windows reject interactive movement and resizing.
Server title clicks wait for the legacy logical move threshold before applying
geometry-changing drag modes, preserving double-click gestures. Partially
maximized windows retain their axis mask and floating geometry through Escape.
Native requests require a valid pointer grab serial and a held button on the
requesting surface. Clients retain the actual logical output coordinates,
including negative origins.

The capability-scoped `ext-session-lock-v1` path hides ordinary surfaces, input,
IME grabs/popups and virtual-keyboard forwarding while locked. Every enabled
output presents an opaque blank frame before acknowledgement; locker loss keeps
the desktop hidden until an authorized replacement unlocks. Shell version 17 and
Ctrl-Alt-L ask the session supervisor to start its foreground PAM locker. Greeter
sessions ignore user lock requests. Headless tests cover five densities, native
GNUstep input/repeat isolation, newly opened apps, eight transforms, mixed and
negative layouts, output enable/hotplug and recovery. Physical modesets,
actual suspend/VT transitions and fractional-sharp locker artwork remain open.
The supervisor's logind sleep guard releases its delay inhibitor only after
protected output presentation, and prevents protocol unlock until trusted
resume. Owned-bus tests cover hung lockers and bus/owner recovery; Lima also
verifies real inhibitor ownership/removal without suspending the guest.

Clients using xdg-decoration can negotiate a compositor frame with a
density-aware title, close/minimize controls and move/resize input. Explicit
client-side preferences are honored; unspecified preferences select the server
frame. GNUstep's application-v7 adapter preserves its logical frame metrics and
submits its content through a viewport while the compositor draws the frame.
Owned edited-document metadata selects the existing NextSpace clean/broken-X
close artwork, including its pressed variant. Bezel and artwork edges use the
same physical rounding at each density. Native fullscreen API and full visual
parity checks and remaining title/group actions remain open.
Native titles support shade/unshade, Control/Shift axis toggles, selection
gestures and wheel pairs, including high-resolution wheel steps. Workspace
publishes the existing toolkit double-click interval through shell v15;
Mouse Preferences changes apply without adding a new preference.
Frame rendering adds the `pangocairo` build/runtime dependency. Building also
requires Python 3 with Pillow (`python3-pil` on Debian) and `rsvg-convert`
(`librsvg2-bin`) to compile the shared magnifier master. Generated artwork retains the repository's asset provenance and
is not relicensed by the compositor's source notices. Set
`NEXTSPACE_COMPOSITOR_CAPTURE_DIR` to an existing directory to capture title
buffers during validation; ordinary sessions do no capture I/O.

For a manual nested trial, run the compositor in an existing Wayland session. It
prints its actual `WAYLAND_DISPLAY`. In another terminal, launch the probe using
that socket with `DISPLAY` unset and `-GSBackend libgnustep-wayland`.
Workspace builds native support by default. Launch it through
[`nextspace-session`](../Session/README.md), which supplies its private shell capability.
For clipboard/Services trials, give `gpbs-wayland --no-fork` and all native clients
the same fresh UUID in `NEXTSPACE_SESSION_ID`. The supervisor manages that
context and process cleanup for normal sessions.

`-Dcomparators=true` additionally builds the independent GTK/Qt test clients.
Their dependencies are confined to this opt-in Meson option.
`-d` enables wlroots diagnostics.

The xdg/input/scene foundation derives from wlroots 0.18.2's tinywl. Its MIT notice
is preserved in `LICENSE.wlroots`. No Zac-OS-9 code is copied. Native GNUstep source
reuse and protocol provenance are recorded in `Protocols/manifest.json`.

See [`Tests/Wayland`](../../Tests/Wayland/README.md) for reproducible tests and open
migration gates, and [`Protocols`](../../Protocols/README.md) for coordinate and
controller contracts.
