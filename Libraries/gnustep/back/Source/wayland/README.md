# NEXTSPACE native Wayland backend

Adapted from GNUstep libs-back commit `d378734ea82e2900b8e1f7882fd5a0d19919849e`.
Original LGPL notices remain in the source. NEXTSPACE changes add fractional
scale/viewport support, logical output geometry, safe shared-memory presentation,
configure sequencing, version negotiation and pinned GUI backing hooks.

See `Tests/Wayland/README.md` and `Protocols/README.md` at the repository root for
tested behavior and outstanding hardware/release gates. Build with `autoreconf -fi`, then
`./configure --enable-server=wayland --enable-graphics=cairo --with-name=wayland`.
The build generates protocol bindings from the checked-in XML using
`wayland-regenerate.sh`. EGL is intentionally outside this shared-memory gate.

## Other Wayland compositors

NEXTSPACE's complete desktop requires its compositor and the session-launched
shell capability. The backend can render ordinary GNUstep windows on other
compositors with stable xdg-shell, wl_compositor and wl_shm. The following limits
apply when the corresponding protocols are absent:

| Missing protocol | Behavior |
| --- | --- |
| `nextspace_application_v1` | Absolute window positions remain local estimates. Restored global placement, window levels, ordering and nonactivating detached menus cannot retain NEXTSPACE's compositor policy. Standard parent-relative xdg popups still use their parent surface. |
| Native frame metrics contract or viewporter | Request the existing client frame instead of a NEXTSPACE server frame. Without xdg-decoration, retain that client frame without negotiation. |
| Fractional-scale or viewporter | Use the output's integer buffer scale. A compositor may resample that buffer. If neither viewporter nor `wl_surface.set_buffer_scale` is available, retain 100% backing and logical dimensions. |
| Application v8 color-pick interaction | Beep and return without entering a screen-color tracking loop. |

Workspace requires its authorized shell connection and fails explicitly when
that connection is unavailable. It cannot supply the full NEXTSPACE desktop
under an unrelated compositor. Per-session pasteboard storage and Services
still require the shared session context described in the protocol contracts.

`Tests/Wayland/foreign_compositor.py` checks the installed backend against
Debian 13's Weston 14.0.2 headless/Pixman renderer, with no NEXTSPACE extensions
or xdg-decoration. It verifies 801×601 logical windows, native 100%/200% buffers,
backing conversions, readback and submitted image pixels. This check does not
qualify foreign desktop input workflows or fractional density. The existing
protocol-removal fixtures cover fractional/viewporter and older-surface fallbacks
under the NEXTSPACE compositor.
