# NEXTSPACE Wayland rewrite plan

- Date: 2026-10-27
- Status: Implementation in progress. Both ARM64 CI jobs pass at `d33dff61`; cleaned-up ci2 packages pass isolated Lima login/logout validation. Physical qualification and the extreme keyboard-burst limit remain open; see [verified status](Wayland-Implementation-Status.md).
- Scope updated 2026-10-30 at the user's request: native Wayland only. X11 sessions, Xwayland compatibility, fallback packages and their validation are excluded. Historical X11 references below describe migration boundaries rather than continuing compatibility requirements.
- Accessibility scope clarified 2026-11-03: preserve existing keyboard accessibility. Adding screen-reader support is excluded at the user's request.
- Execution priority updated 2026-11-04: focus on Debian 13 ARM64/aarch64, native ARM64 CI and the existing Lima guest. Intel/AMD qualification is deferred. Physical hardware and unrestricted artwork redistribution gates do not block continued ARM implementation or personal-use validation.
- NEXTSPACE baseline: `e5d55eff8cdb4f6949e16ab45f22c504cdab4f9d`
- Reference: [Zac-OS-9 at `93769cb`](https://github.com/chromasystemprofessional/Zac-OS-9/tree/93769cb314a03e6da448cc86bba19885da070926)

## Goal and scope

Replace NEXTSPACE's X11 display stack with a Wayland compositor and native Wayland application rendering. Support independent display scales of 100%, 125%, 150%, 175% and 200%, including mixed-scale monitors, without changing the NeXTSTEP appearance, logical control sizes or desktop workflows. Keep the coordinate model extensible to other scale values.

Follow Zac-OS-9's separation of compositor and desktop shell. Preserve NEXTSPACE's Objective-C applications, GNUstep APIs, DesktopKit components, `.gorm` layouts and application data. Rewrite the display-dependent parts around them. A wholesale Qt application rewrite would also require rebuilding these contracts and is outside this initial scope; Qt remains a feasibility fallback if the native GNUstep prototype fails.

The two essential deliverables are a compositor that understands per-output scaling and a toolkit that redraws each window at its preferred density. The delivered session runs native Wayland applications without an X server.

### Completion criteria

- Workspace, Preferences, Terminal, TextEdit and the remaining bundled GUI applications render natively on Wayland. The login screen also renders correctly at the configured density.
- At every target scale, text, controls, decorations, icons and cursors use appropriate rendering resolution. Small bitmap artwork may require replacement representations; enlarging a screenshot of the existing desktop is insufficient.
- Artwork must preserve the original shape, proportions, palette, shading and style. SVG is an implementation format, not permission to redesign. Compare replacements with the original resources at 100%, then verify native rendering at every target density. Comparisons with a redraw's own output do not establish fidelity. Upscaling the original bitmap does not count as a completed HiDPI replacement.
- Large icons use matching high-resolution NeXTSpirit artwork first (user direction, 2026-11-01). Construct an original-style replacement only when that collection lacks a suitable icon. Preserve logical dimensions and verify native density selection. Keep the artist's attribution and usage terms with imported assets; the downloaded packs' personal-use terms do not establish permission for an unrestricted release.
- Reconstruct the original design as genuine high-resolution geometry. Fidelity refers to the design, including lettering and construction details; it does not require copying low-resolution pixel stair steps. Density-dependent antialiasing may differ. Keeping the original raster resources is a temporary fallback, not completion of the artwork work.
- Moving a window between differently scaled outputs preserves its logical dimensions, updates its backing buffer and keeps pointer, popup, selection and drag coordinates aligned.
- Display changes, rotation, hotplug, suspend/resume and login/logout preserve a usable desktop and valid saved layout.
- Existing Dock, IconYard, application menus, hide/unhide, miniaturization, shading, workspaces, modal panels, Services, clipboard and drag-and-drop behavior have explicit passing parity checks.
- The installed session, backend, compositor and bundled applications work with `DISPLAY` unset and without Xorg or Xwayland installed.

## Existing architecture and required changes

| Component | Current implementation | Required change |
| --- | --- | --- |
| Workspace and window management | [Workspace_main.m](../Applications/Workspace/Workspace_main.m) starts the embedded Window Maker code. [Controller.m](../Applications/Workspace/Controller.m) and `Workspace+WM.h` (removed) use `WScreen`, `WWindow` and X window IDs directly. | Extract a shell/window-management interface. Move display-server and window-management responsibilities into a separate compositor; keep file browsing and application integration in Workspace. |
| Display model | [OSEScreen](../Frameworks/SystemKit/OSEScreen.m) and [OSEDisplay](../Frameworks/SystemKit/OSEDisplay.h) expose XRandR concepts. Mode pixel sizes feed geometry that callers treat as logical. | Separate physical mode pixels, logical bounds, output scale, transform and stable display identity. Hide X11 types inside the legacy backend. |
| Display preferences | [Display.m](../Applications/Preferences/Modules/Display/Display.m) applies resolution/rate changes and offers countdown reversion. | Add per-output scale and effective logical size. Move transaction validation and timeout rollback into the compositor. |
| Screen preferences | [Screen.m](../Applications/Preferences/Modules/Screen/Screen.m) controls output activation, primary display and layout. | Apply these settings through the same validated output transaction as resolution and scale. |
| Input settings | [OSEMouse.m](../Frameworks/SystemKit/OSEMouse.m) and [OSEKeyboard.m](../Frameworks/SystemKit/OSEKeyboard.m) configure X pointer and XKB state. | Keep the public settings model where practical, with compositor implementations using libinput and xkbcommon. Explicitly migrate settings that have different semantics. |
| Login and session | [Login_main.m](../Applications/Login/Login_main.m) starts Xorg; [Controller.m](../Applications/Login/Controller.m) selects an X11 session and `UserSession.m` (removed) forces `DISPLAY=:0`. | Add a Wayland session lifecycle, runtime socket discovery, seat ownership and native Wayland environment. |
| GNUstep backend | [GSBackend.m](../Libraries/gnustep/back/Source/GSBackend.m) initializes XGServer. [configure.ac](../Libraries/gnustep/back/configure.ac) has no supported Wayland server build. [CairoContext.m](../Libraries/gnustep/back/Source/cairo/CairoContext.m) references Wayland classes that are absent. | Implement and build a real Wayland `GSDisplayServer`, with Cairo drawing into Wayland buffers. Existing conditional hooks are incomplete scaffolding. |
| GNUstep GUI | [environment.sh](../Packaging/environment.sh) pins GUI `0_32_0`; `6_build_libs-gui.sh` (removed) downloads it and applies patches. GUI sources are not vendored here. | Maintain a reproducible GUI patch set or pinned fork for per-window backing scale, coordinate conversion and scale-change notifications. |
| Pasteboard service | [gpbs.service](../Libraries/gnustep/gpbs.service) is installed as a system service; `xpbs.m` (removed) implemented its X selection bridge. | Define per-session pasteboard integration with native client offer/serial ownership without an X selection bridge. |
| Application-specific X11 | [TerminalWindow.m](../Applications/Terminal/TerminalWindow.m) sets X11 resize hints through native window handles. | Replace direct native-handle access with toolkit interfaces. Preserve character-cell sizing even though xdg-shell has no direct X11 resize-increment equivalent. |
| Assets and drawing | [DesktopKit resources](../Frameworks/DesktopKit/Resources), [GNUstep theme](../Libraries/gnustep/nextspace-theme) and WM drawing include fixed-resolution artwork and pixel assumptions. | Keep dimensions in logical units; render fonts and primitives at backing density and select suitable image/cursor representations. |
| Build and tests | `7_build_libs-back.sh` (removed) builds ART and Cairo; the former X11 source CI built the stack without exercising a desktop. | [ARM64 CI](../.github/workflows/wayland.yml) builds and exercises the native Wayland session, backend and Debian packages. Real Linux display validation remains required. |

The pinned GNUstep GUI makes this more than a window-manager replacement: both [`NSScreen.backingScaleFactor`](https://github.com/gnustep/libs-gui/blob/gui-0_32_0/Source/NSScreen.m#L416-L443) and [`NSWindow.backingScaleFactor`](https://github.com/gnustep/libs-gui/blob/gui-0_32_0/Source/NSWindow.m#L5976-L5979) return `1.0`. A global `GSScaleFactor` cannot represent windows on different-density displays. Toolkit scale semantics are therefore on the critical path.

## What to adopt from Zac-OS-9

The inspected reference uses a C/wlroots compositor, a separate shell with Qt components and native Wayland helpers, and a separate session launcher. Its build targets wlroots 0.18. Adopt the process boundaries, nested development approach and explicit shell integration while retaining NEXTSPACE's toolkit and appearance. Select and pin the wlroots release against NEXTSPACE's target distributions during phase 0; the reference's dependency version is not an automatic choice. [Reference build](https://github.com/chromasystemprofessional/Zac-OS-9/blob/93769cb314a03e6da448cc86bba19885da070926/compositor/meson.build), [reference shell](https://github.com/chromasystemprofessional/Zac-OS-9/tree/93769cb314a03e6da448cc86bba19885da070926/shell), [reference session](https://github.com/chromasystemprofessional/Zac-OS-9/tree/93769cb314a03e6da448cc86bba19885da070926/session).

Its compositor creates both fractional-scale and viewporter globals. Its preferences code accepts 1.25, 1.5 and 1.75 scales, stores output-specific settings, and refreshes surface scale preferences after changes. These are useful implementation references, including the distinction between fractional-aware clients and integer-buffer fallback. Treat explicit refresh workarounds as version-specific and test the chosen wlroots version. [Protocol setup](https://github.com/chromasystemprofessional/Zac-OS-9/blob/93769cb314a03e6da448cc86bba19885da070926/compositor/src/main.c#L146-L154), [scale settings and refresh](https://github.com/chromasystemprofessional/Zac-OS-9/blob/93769cb314a03e6da448cc86bba19885da070926/compositor/src/prefs.c#L66-L188).

Source implementation is evidence of design, not proof that NEXTSPACE will work across GPUs and toolkits. In particular, do not copy the reference's [Xwayland scaling heuristics](https://github.com/chromasystemprofessional/Zac-OS-9/blob/93769cb314a03e6da448cc86bba19885da070926/compositor/src/xwayland.c#L32-L77) or infer that a protocol global alone makes applications sharp. The independent [Wayland architecture](https://wayland.freedesktop.org/architecture.html) and [Qt HiDPI model](https://doc.qt.io/qt-6/highdpi.html) both place drawing resolution responsibilities in the client/toolkit as well as the compositor. Review file-level licenses before reusing reference code.

Adopt the reference's distinction between [protocol scale tests](https://github.com/chromasystemprofessional/Zac-OS-9/blob/93769cb314a03e6da448cc86bba19885da070926/compositor/tests/test_fractional_scale.py) and [rendered pixel tests](https://github.com/chromasystemprofessional/Zac-OS-9/blob/93769cb314a03e6da448cc86bba19885da070926/compositor/tests/test_menubar_scale.py). NEXTSPACE needs both, using its own fonts, artwork and interaction fixtures.

## Target architecture

```text
Login / session supervisor
  ├── nextspace-compositor (C, wlroots)
  │     ├── DRM/KMS, libinput, xkbcommon and seat integration
  │     ├── output layout, scaling, focus, stacking and decorations
  │     ├── trusted NEXTSPACE shell interface
  └── user session clients
        ├── Workspace: file manager, Dock, IconYard and desktop policy
        ├── Preferences and SystemKit adapters
        ├── GNUstep applications → native Wayland + Cairo backend
        └── other native Wayland applications
```

The compositor owns authoritative window state and renders server decorations. Workspace supplies application grouping, launcher and desktop behavior through a versioned interface; it must not dereference compositor internals. A Workspace crash should permit shell restart without killing the compositor or unrelated applications. A compositor crash ends the graphical session and must return cleanly to login rather than pretending clients survived.

### Proposed source boundaries

| Location | Responsibility |
| --- | --- |
| `Applications/Compositor/` (new) | Meson-built compositor, scene, outputs, input, window policy, decorations and native application integration. |
| `Protocols/` (new) | Versioned NEXTSPACE shell/application extensions and a manifest of pinned upstream protocols. |
| `Applications/Workspace/` | An adapter boundary with a native Wayland implementation; existing file-manager logic retained. |
| `Libraries/gnustep/back/Source/wayland/` (new) | Wayland display server, event dispatch, windows, input, selections and cursors. |
| `Libraries/gnustep/back/Source/cairo/` | Wayland shared-memory surfaces and density-aware rendering. |
| `Libraries/gnustep/patches/` | Reproducible GUI changes for backing-store APIs and notifications. |
| `Frameworks/SystemKit/` and `Frameworks/DesktopKit/` | Display/input adapters, logical geometry, assets and application-facing integration. |
| `Applications/Login/`, `OS/`, `Packaging/` | Session launching, installed defaults, dependency pins and separate session packages. |
| `Tests/Wayland/` (new) | Protocol fixtures, geometry tests, image comparisons and integration runners. |

Keep the existing GNUmake-based application build. Introduce Meson only for the new compositor/protocol generation unless a later build change has a separate justification.

### Protocol and behavior contracts

- Use `xdg-shell` for ordinary windows and popups, `xdg-decoration` negotiation for server frames, `wl_seat` for input, and Wayland data-device/primary-selection support for clipboard and drag-and-drop. Include xdg-activation and text-input/input-method integration in the supported protocol matrix.
- Redesign the `gpbs` integration explicitly: focused native clients own Wayland selection offers and input serials, while per-session pasteboard storage preserves GNUstep types and Services behavior. Any trusted clipboard persistence component needs a supported compositor protocol. Keep selection ownership and persistence within the native Wayland session.
- Use layer-shell where appropriate for desktop/Dock surfaces. Add a narrow NEXTSPACE extension for application grouping, floating or torn-off menus, hide/unhide, shade, miniwindow metadata and shell window control. Separate client-owned window metadata from privileged operations on other applications.
- Bind privileged shell control to the session-launched shell connection or an equivalent capability. An application ID or same-user socket access alone must not grant shell authority. Version requests and define restart/reconnection behavior.
- Audit AppKit's absolute window positioning and synchronous geometry assumptions. Ordinary Wayland clients do not know global surface positions. Use standard parent-relative popup placement where possible and a compositor-mediated extension for NEXTSPACE-owned window placement/state restoration. Define degraded behavior under other compositors explicitly. [Wayland surface and input model](https://wayland.freedesktop.org/docs/book/Protocol.html#surfaces).
- Preserve application menus and levels deliberately. The current semantics are recorded in [original GNUstep hints](../Tests/Wayland/fixtures/title-reference/originals/GNUstep.h); ordinary xdg-shell does not express all of them.
- Exclude the embedded Window Maker and Xwayland from the native session.

## HiDPI and fractional scaling contract

### Coordinates and buffers

Use three explicit coordinate spaces: logical desktop/surface coordinates, client buffer pixels and physical output pixels. Keep layout, saved window sizes and input in logical units. Convert AppKit's coordinate orientation at the backend boundary, including negative output origins and rotated monitors. Do not multiply existing `.gorm` dimensions or apply a global font-size multiplier.

Represent a protocol scale as an integer numerator over 120. For example, 150 means 125%, and 180 means 150%. A fractional-aware toplevel with logical dimensions `W × H` allocates `round_half_away_from_zero(W × scale) × round_half_away_from_zero(H × scale)` buffer pixels, sets `wl_surface` buffer scale to 1, and sets the viewport destination to `W × H`. For positive dimensions the rounding is `floor(value + 0.5)`. These rules come from the [fractional-scale protocol XML](https://github.com/wayland-mirror/wayland-protocols/blob/main/staging/fractional-scale/fractional-scale-v1.xml); integer ceiling is not the toplevel buffer-size rule.

An 800 × 600 logical window at 150% therefore draws into 1200 × 900 pixels. Keep explicit tests for odd dimensions such as 801 × 601 at 125%, where rounding matters. Subsurface rounding is not fully specified by that protocol; define a consistent edge-based policy in the backend and test seams and popup alignment.

Track the chosen output's scale for each surface and notify it when output membership or settings change. Use the tested wlroots scene policy for the output containing the largest visible surface area, and cover spanning windows and ties in tests. A single buffer spanning differently scaled displays may still be resampled on one display; the sharpness target applies when it is wholly on its preferred output. Current [wlroots scene documentation](https://wlroots.pages.freedesktop.org/wlroots/wlr/types/wlr_scene.h.html#wlr_scene_surface_create) describes automatic fractional-scale handling; confirm behavior for the pinned release.

For clients without fractional-scale support, offer the appropriate integer preferred scale and let the compositor resample as necessary. Native NEXTSPACE clients must use the fractional path. Test missing viewporter/fractional-scale globals and never require unsupported protocol versions.

### Native GNUstep rendering

- Start with Cairo image surfaces backed by `wl_shm` buffers. Maintain a bounded buffer pool, respect `wl_buffer.release`, acknowledge configure events before the corresponding commits, and pace rendering with frame callbacks. Never resize or paint a buffer still owned by the compositor.
- Implement genuine per-window backing scale, backing-coordinate conversions, backing-change notifications and screen updates in GNUstep GUI/backend. Treat `NSDeviceResolution`, logical font size and backing pixel density as distinct concepts.
- Apply the backing transform consistently to Cairo drawing, glyph rasterization, clipping, image selection and readback. Keep logical font metrics stable while rerasterizing glyphs at the new density. Invalidate glyph, decoration and image caches on a scale change. Preserve printing/PDF behavior independently from screen density.
- Round damage outward in buffer coordinates so edge pixels are repainted. Snap shared drawing edges consistently; avoid cumulative rounding and double scaling in the toolkit and compositor.
- Integrate Wayland dispatch with the Foundation/CF run loop, including modal loops and tracking modes, without blocking application event handling. Add IME/preedit, keyboard repeat, cursor hotspot and selection tests.
- Establish a working shared-memory path before optional EGL/dma-buf acceleration. Audit any OpenGL users and choose an EGL-backed native path where required; do not make unmeasured GPU acceleration a prerequisite for the first text/control prototype.

### Artwork and preferences

Render NeXT borders, bevels and simple symbols from logical primitives where practical. Supply multiple representations or suitable vector masters for icons and cursor assets; keep original proportions and colors. Use scalable font faces where available and inspect the existing `.nfont` packages. At fractional scales, a logical one-pixel line need not occupy exactly one physical pixel; choose consistent rasterization rather than claiming every legacy bitmap remains pixel-identical.

Render each representation from authored vector geometry or a master with enough native pixels for the target density. Upscaling a small bitmap or drawing its enlarged pixel cells does not add source detail. Verify the actual submitted image, including resources embedded inside Gorm archives.

For multi-representation originals, inspect the representation selected by the
actual RGB application context. A TIFF's first or largest representation may be
a grayscale alternative and is insufficient as the sole design reference.

Add a per-display scale selector to Display Preferences with physical resolution, refresh rate and effective logical dimensions. Store scale, layout and primary-display choice under a versioned schema keyed by a stable display identity, with a connector fallback for ambiguous hardware. Preserve existing application data while storing native display preferences separately. The compositor must validate the entire layout, keep at least one usable output, apply it as a transaction and revert on timeout or settings-client failure.

## Implementation phases

Each phase ends with observable behavior and recorded evidence. Phases 1 and 2 can run in parallel after the coordinate and interface contracts in phase 0 are agreed. Phase 2 is the architecture gate for the larger application migration.

### Phase 0 — Baseline and dependency decisions

1. Inventory direct X11 calls, native window handles, display/input settings, window levels, application menus, `gpbs` ownership/lifecycle and GUI patch dependencies. Record every bundled GUI application and its parity scenarios.
2. Capture baseline screenshots and interaction recordings at the existing 100% layout. Include Workspace menus, Dock, IconYard, open/save panels, Terminal selection, font panels and TextEdit.
3. Choose the first supported Linux distribution and GPU test machines. Check its wlroots, Wayland, wayland-protocols, libinput, xkbcommon and seat-management versions; pin a compatible set with reproducible package/source inputs. Use the pinned native runtime for the supported target.
4. Define the logical/physical coordinate API, shell/application protocol responsibilities and versioned preference schema. Record how existing window-position APIs and terminal cell increments will behave.
5. Identify maintained upstream GNUstep Wayland work, if any, and evaluate it against the pinned GUI and local changes before choosing reuse or implementation. Record code ownership, license obligations and an upstreaming strategy.

The implementation reuses the GNUstep Wayland foundation pinned in
[`Protocols/manifest.json`](../Protocols/manifest.json), with local adaptations
for the pinned GUI, fractional backing, input, selections and NEXTSPACE window
semantics. The imported backend files retain their original authorship and
LGPL-2.0-or-later notices. The compositor's tinywl foundation retains its
[`MIT notice`](../Applications/Compositor/LICENSE.wlroots). Artwork provenance
and terms remain recorded separately in [Artwork Sources](Artwork-Sources.md).

Prepare upstream contributions as separate, reviewable changesets: Base
run-loop and message-port fixes; generic GUI backing, printing and control
changes; then backend changes with standard Wayland protocol behavior. Include
the focused regression fixtures and exact supported dependency versions with
each changeset. Keep NEXTSPACE shell policy and private application/shell
extensions in this repository. Retain the pinned integration until an upstream
replacement passes the same native behavior and density matrix. This records
the contribution strategy; no upstream submission or acceptance is claimed.

Exit: a feature inventory, selected dependency set, architecture decision and executable test specification. Do not estimate the full migration from compositor size alone.

### Phase 1 — Compositor and independent scaling proof

1. Add `nextspace-compositor` with nested/headless backends first, followed by DRM/KMS through the chosen seat integration. Keep input/output work on the compositor event loop.
2. Implement xdg-shell lifecycle, focus, movement/resizing, basic decorations, output layout and the fractional/viewporter contracts. Exercise hotplug and live scale changes from a small test controller.
3. Run a simple protocol test client plus representative native Qt and GTK applications. Verify advertised scale, committed buffer dimensions, pointer coordinates and popup placement at all target scales.
4. Verify native window lifecycle, focus, clipboard and shutdown without an X server.

Exit: reproducible two-output tests at 100%/200% and 125%/150%, plus a real display smoke test. Bundled applications migrate through the native toolkit gate.

### Phase 2 — Native GNUstep feasibility gate

1. Implement the Wayland server build path and a Cairo shared-memory surface. Add the required pinned GUI patches for backing scale and coordinate conversion.
2. Run an expanded [GNUstep GUI test application](../Tests/GNUstep-GUI) with text, buttons, scrollers, images, menus, modal panels and window resizing.
3. Move the same live window between outputs and change scale while it remains on an output. Check correct buffer dimensions, stable logical geometry, event locations, font rendering and resource release.
4. Prove menu/popup placement, a detached menu, native clipboard and a basic Services round trip. Implement the per-session `gpbs` boundary and verify selection ownership, serial handling and native clipboard and primary-selection transfers. Prototype the compositor-mediated placement contract before porting Workspace.
5. Run minimal native TextEdit and Terminal trials before broad Workspace migration, allowing an early replacement or guard for Terminal's X11 resize-hint access. Check text layout, selection and retained scrolling contents during scale changes.

Exit: the test application runs with `DISPLAY` unset and produces native buffers at every target scale. If this fails, resolve the toolkit contract or make an explicit architecture decision about a targeted Qt port; a scaled Xwayland screenshot does not pass this gate.

### Phase 3 — Workspace and window behavior

1. Use the native Workspace adapter and exclude the embedded X11 window manager from its build. Remove direct WM structs and X IDs from shared Workspace application logic.
2. Move focus/stacking, decoration rendering, shade, miniaturization and workspace policy into the compositor. Port Dock/IconYard integration and app grouping through the shell interface.
3. Implement app hide/unhide, activation, detached menus, modal/floating levels, launch feedback and window restoration. Test shell disconnect/reconnect and compositor-owned state recovery.
4. Rebuild shell assets and decorations at backing density; verify 100% appearance against the baseline before approving each fractional-scale rendering change.

Exit: Workspace runs natively, preserves its file-manager behavior and passes the recorded desktop workflow tests across mixed-scale displays.

### Phase 4 — Settings and bundled applications

1. Add SystemKit Wayland display/input adapters and preserve existing notification contracts such as `OSEScreenDidChangeNotification`.
2. Extend Display Preferences with scale selection and compositor-owned test/apply/revert. Route Screen Preferences output activation, primary-display selection and layout through the same transaction. Cover disconnected monitors, rotated layouts, duplicate display identities and restart persistence.
3. Translate keyboard and mouse preferences to libinput/xkbcommon. Document settings that cannot retain identical X11 semantics rather than silently mapping them to unrelated options.
4. Remove direct X11 assumptions from Terminal and other apps. Complete native clipboard/primary selection, drag-and-drop, IME, cursors, existing keyboard accessibility and application Services integration. Preserve focus navigation and native control actions across scale changes; a screen-reader bridge is outside scope.
5. Audit every bundled GUI app and DesktopKit drawing path, update assets, and test printing/readback independently from screen backing scale.

Exit: every bundled application has a recorded native launch and functional result at 100%, 150% and 200%; shared rendering fixtures cover the full scale matrix. No X server is required by the native session's core applications.

### Phase 5 — Login, integration and packaging

1. Replace Login's hard-coded Xorg lifecycle with the native Wayland session launcher. Retain PAM authentication and use PAM/logind-created runtime and seat context for the user compositor. Separate the greeter compositor lifecycle from the authenticated user session.
2. Set `XDG_SESSION_TYPE=wayland`, `WAYLAND_DISPLAY` and desktop metadata from the actual session. Keep `DISPLAY` unset; propagate the native environment to D-Bus/user services.
3. Preserve login/logout hooks, restart and power actions. Implement locking with a proper session-lock contract before exposing the session for daily use; verify suspend/resume and VT switching.
4. Add the Wayland session entry, compositor/backend packages, protocol generation, runtime dependencies and required SELinux policy changes. Verify clean installation, live upgrade and removal of the native packages.
5. Integrate desktop portals/PipeWire for supported capture and screen sharing, with per-output coordinate and scale tests. Record any unsupported desktop integration as a release blocker or an explicitly scoped follow-up.

Exit: fresh install, login, logout, native session entry, lock/unlock and package upgrade work on the first supported distribution with no X server installed.

### Phase 6 — Release qualification and default switch

1. Run the full matrix below on nested/headless CI and selected physical machines. Record dependency versions, GPU/driver, output modes/scales and known failures.
2. Compare rendering, interaction latency, CPU usage and buffer memory against the recorded baseline. Investigate missed frames during ordinary 60 Hz movement/scrolling; set hardware-specific performance thresholds from phase 0 measurements.
3. Publish native Wayland rendering and workflow results. Resolve core functionality or sharpness failures before changing the default.
4. Ship Wayland as opt-in first. Make it default only after native app, workflow, session and hardware gates pass.

## Verification matrix

| Area | Required cases | Passing evidence |
| --- | --- | --- |
| Scale math | 100%, 125%, 150%, 175%, 200%; odd sizes; reversed coordinate axes | Expected buffer dimensions and logical geometry; no accumulated drift after repeated transitions. |
| Native rendering | Text, thin lines, bevels, selections, icons, cursors, drag images | Buffer inspection and reference images at each density; no persistent low-resolution buffer enlargement or double scaling. |
| Mixed outputs | 100%/200%, 125%/150%, 150%/200%; negative origins; spanning windows | Correct preferred scale and redraw after transition; stable logical window size and aligned hit testing. |
| Window behavior | Detached menus, popups near edges, modal panels, hide/unhide, shade, miniaturize, Dock/IconYard, workspaces | Behavior matches the baseline; no focus traps, duplicate decorations or inaccessible windows. |
| Text and transfers | Keyboard layouts, repeat, IME/preedit, clipboard/primary selection, file/text drag-and-drop, Services | Correct data and focus across native apps and between native applications. |
| Keyboard accessibility | Tab/Shift-Tab focus traversal, disabled/read-only controls, Return actions during density changes | Existing keyboard behavior remains usable; focus and text survive scale transitions. Screen-reader support is outside scope. |
| Display lifecycle | Hotplug, rotation, mode/scale changes, settings crash, timeout rollback | Usable layout remains; windows recover onto an available output; persisted settings restore safely. |
| Session lifecycle | Login/logout, shell restart, compositor failure, lock, suspend/resume, VT switching | Correct ownership/cleanup, no orphaned session, reliable return to login after compositor failure. |
| Native comparators | Native Qt and GTK applications | Correct density, input, clipboard and window behavior. |
| Hardware and performance | At least available Intel/AMD hardware; NVIDIA before claiming its support; nested software renderer | Recorded frame timing, CPU/memory trends and successful real display modesets. Headless tests alone do not establish GPU support. |
| Packaging | Clean install, upgrade, native session entry and removal | Reproducible build inputs; applications use the native backend with no X server installed. |

Add geometry and protocol tests under `Tests/Wayland/`; extend existing GUI/DesktopKit fixtures instead of recreating them. Exercise Terminal's scrolling/copy operations and partial repaint paths to detect corrupted retained content. Use repeated move/resize/scale cycles to catch buffer and cache leaks. Keep screenshot tolerances narrow enough to detect blur and seams while accounting for deliberate font rasterizer differences. The planning work does not constitute runtime validation.

## Main risks and decision gates

| Risk | Response |
| --- | --- |
| GNUstep backing APIs or run-loop behavior require deeper work than expected | Prove the native test application in phase 2 before broad shell/application migration. Budget GUI work explicitly. |
| NeXT window/menu semantics conflict with ordinary Wayland client assumptions | Define limited extensions and parity tests early; keep authoritative placement/focus in the compositor. |
| Existing bitmap assets look soft at fractional scales | Separate rendering bugs from missing source resolution; redraw primitives and add appropriate asset representations. |
| Reference code depends on old wlroots behavior | Pin a supported dependency set and test the matching API/protocol behavior; do not mix examples from different versions blindly. |
| Native application rendering differs across monitors | Verify logical dimensions, per-output buffers, text and input at each density. |
| Display settings make a monitor unusable | Validate as a transaction and implement compositor-side timeout rollback plus a known-good startup configuration. |
| Scope grows into an unrelated desktop redesign | Preserve the existing appearance, applications and workflows; track optional effects, HDR/VRR and broad toolkit replacement separately. |

The first implementation milestone is a nested compositor and one native GNUstep window that remains correctly rendered and interactive while moving between 100% and 150% outputs. That proves both halves of the scaling design before the larger Workspace rewrite begins.
