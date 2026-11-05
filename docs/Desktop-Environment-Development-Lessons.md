# Desktop environment development: reusable lessons

- Recorded: 2026-11-05.
- Purpose: carry the decisions and engineering lessons from the NEXTSPACE Wayland/HiDPI rewrite into future desktop-environment projects, including faithful recreations of an existing desktop experience.
- Scope: reusable engineering knowledge. Each future project defines its own reference desktop, release and UX specification.
- Source snapshot: NEXTSPACE `1f2257829c7d9e2eabe3fc669b2761adff60bdd4` on `codex/wayland-hidpi-arm64`.
- This is a handoff document. It does not select or start a new desktop project, and the NEXTSPACE rewrite is not fully qualified.

## What carries over, and what needs a new decision

The reusable goal is faithful recreation of a chosen desktop experience. Mac OS X Tiger and Leopard are examples, not selected targets. The reference desktop, exact release/build, toolkit, application inventory and compatibility promises remain open. Reuse the engineering foundations below while defining each project's appearance and behavior from its own reference system.

NEXTSPACE preserved existing Objective-C applications, GNUstep APIs, DesktopKit and Gorm layouts. That made a native GNUstep backend a practical investment. It does not establish GNUstep as the best toolkit for every new desktop. Likewise, NEXTSPACE's detached application menus, IconYard, shading and NeXT artwork are project-specific policies. Each new project needs its own measured contracts.

### Decisions made in this conversation

| Decision | Reason and boundary |
| --- | --- |
| Use native Wayland only | The user explicitly removed X11 and Xwayland compatibility from scope on 2026-10-30. Supporting two display stacks added work outside the requested result. Four legacy X11 workflows and their badges were removed. |
| Prioritize Debian 13 ARM64/aarch64 | Native ARM64 CI and the existing Lima guest are the current development targets. Intel/AMD qualification is deferred. Missing hardware or redistribution permission must not stall independent ARM implementation and personal-use validation. |
| Follow KISS and DRY | Reuse shared geometry, ownership, rendering and test helpers. Introduce an abstraction when it removes real duplication or establishes a necessary boundary. Keep changes reviewable. |
| Preserve design and behavior | A migration must retain workflows, geometry, control states and interaction semantics. A screenshot that merely resembles the target is insufficient. |
| Support genuine HiDPI | Target 100%, 125%, 150%, 175% and 200%, including mixed outputs. Rerender text, controls, decorations, icons and cursors at the required density. |
| Redraw faithfully | The user rejected enlarged low-resolution art and redraws that changed shapes or style. Preserve proportions, palette, shading, lettering and construction details using genuine higher-resolution masters or geometry. |
| Search NeXTSpirit first for large NEXTSPACE icons | Use a suitable existing high-resolution icon before constructing a missing one. This source preference belongs to the NeXT design; choose artwork appropriate to each new reference desktop. Attribution and source terms remain attached. |
| Preserve keyboard accessibility | Tab traversal, Return actions, disabled/read-only behavior and focus during scaling stay in scope. A new screen-reader bridge was excluded for NEXTSPACE; the separate project's accessibility scope still needs an explicit decision. |
| Use Lima for development and testing | Lima packaging is not the production desktop deliverable. The user wants to run the preview locally on an Apple Silicon MacBook and found screen sharing too low quality. An ISO was not required. |
| Keep reusable work during cleanup | Preserve source masters, generators, tests, the useful SDK/VM and verified evidence. Remove owned temporary or duplicate outputs after verification and organize retained material for later refinement. |
| Use logical Git commits and a reviewable PR | The user requested a new branch, grouped commits, push and a PR to `master`. Creating a PR did not authorize merging it. |
| Report progress against the whole plan | When hourly reports are requested, use an overall percentage and a supported time estimate. If the estimate is unsupported, say so. Prototype success is not full-plan completion. |

These are recorded NEXTSPACE decisions. Confirm the applicable platform and scope choices when opening a separate project; they are context for a new decision rather than automatically approved requirements.

### Keep reference-specific policy separate

Each reference release needs a coherent set of visual metrics, assets, fonts, interaction rules and animation behavior. Record differences between releases explicitly. Supporting another release should reuse suitable rendering, input, session and test mechanisms while supplying that release's own design and behavior contracts. Introduce shared helpers where implementations actually overlap; a universal theme or compatibility framework is not a prerequisite.

For example, a project targeting Leopard should use Leopard's reference captures and behavior throughout. Tiger-specific artwork, window rules or interactions are not defaults for that project. Keep those release-specific requirements in the chosen project's specification; this document records the shared lessons.

## Architecture worth reusing

Keep these responsibilities separate:

```text
Login and session supervisor
  ├── Wayland compositor: displays, seats, input, focus, stacking, window policy
  ├── Desktop shell: launcher/panels, file manager, application integration
  └── Applications: toolkit, native rendering, document and application behavior
```

The compositor owns authoritative window and output state. The shell communicates through a narrow, versioned interface rather than reaching into compositor structures. An application ID or a same-user connection is not sufficient authority to control other applications; NEXTSPACE uses a session-launched shell capability.

A shell crash should allow shell restart without terminating unrelated applications. A compositor crash ends its graphical session and must return cleanly to login. Output changes belong in compositor-owned transactions with validation, confirmation and timeout rollback, including recovery when the settings client exits.

For the selected reference desktop, define application activation, menu ownership, launcher/panel behavior, window controls, parent-child dialogs and panel placement before implementing broad shell policy. A Mac OS X-style target also needs explicit contracts for its menu bar, Dock and sheets. Decide which component draws each decoration so toolkit and compositor frames cannot overlap. Standard Wayland protocols cover common windows, input and transfers; custom desktop semantics need an explicit contract and a defined fallback when that contract is unavailable.

### Prove the toolkit early

The largest dependency was native application rendering and event behavior. Adding compositor protocol globals did not make GNUstep applications sharp or complete. The pinned GUI required real backing-scale, drawing, run-loop and input changes.

Before choosing a toolkit for a new project, build one representative native application containing text editing, buttons, scrollers, menus, modal interactions, images, resizing, clipboard and printing. Exercise it alongside a terminal and a document editor across the density matrix. Include the selected reference's menu, activation and dialog behavior in that feasibility gate. GTK and Qt were useful independent comparators in NEXTSPACE; using them for comparison did not select either as the desktop's application toolkit.

Existing dependency pins are reproducibility baselines, not a recommendation to adopt those versions indefinitely. NEXTSPACE's recorded stack includes wlroots 0.18.2, GNUstep GUI 0.32.0, Base 1.31.1 and a pinned upstream Wayland backend foundation with local adaptations. Preserve commits, archive hashes, protocol XML, patch order and notices; revalidate the set for the new target.

## HiDPI rules that prevented recurring bugs

1. Keep logical desktop/surface coordinates, client buffer pixels and physical output pixels distinct. Saved sizes, layout and pointer coordinates stay logical.
2. Represent fractional scale with an integer numerator over 120. For a positive logical dimension `n`, compute its fractional backing dimension as `(n * scale + 60) // 120`. At 125%, an 801×601 window therefore uses a 1001×751 buffer.
3. For the fractional-aware path, use surface buffer scale 1 and a viewport destination equal to the logical size. Avoid a second global font or geometry multiplier.
4. Preserve logical font metrics while rerasterizing glyphs. Invalidate scale-dependent glyph, image, decoration and cursor caches. Include negative output origins, rotated outputs and coordinate-axis conversion in tests.
5. Acknowledge configure events correctly, keep the shared-memory pool bounded and respect `wl_buffer.release`. Never repaint a buffer still owned by the compositor. Use frame callbacks for pacing.
6. Round damage outward and use consistent shared-edge rounding. Partial repaint and retained scrolling can fail even when a full-window redraw looks correct.
7. Treat printing, PDF export and image readback independently from screen backing density.

The tested output policy uses the greatest visible surface area, with a defined tie policy. Moving between displays must preserve logical size and trigger the correct backing redraw. A single buffer spanning different densities can still be resampled on one display; distinguish that case from a window wholly on its preferred output.

The initial working renderer used Cairo and shared memory. GPU acceleration can be added after measuring the real workload; selecting EGL or dma-buf does not by itself prove fidelity, latency or correct buffer ownership.

## Reconstructing the artwork

Faithful reconstruction means preserving the original design while adding real source detail. It does not require reproducing low-resolution stair steps as enlarged vector cells. SVG is a useful master format, but its output still needs comparison with the original design.

- Capture an independent reference at its original logical size. Record active, inactive, pressed, disabled, selected and animated states where relevant.
- Inspect the representation actually selected by the application. Multi-representation TIFFs and images embedded in Gorm archives can differ from the first or largest image a generic decoder exposes.
- Render each density directly from authored geometry or a sufficiently large genuine raster master. A matching high-resolution master can be downsampled; enlargement of a small original cannot supply missing detail.
- Share resource generators and design primitives. Keep logical dimensions and registration points stable across representations.
- Compare against the original at 100%, then inspect the image actually submitted by the native application at every density. Comparing a redraw only with its own generated output proves consistency, not fidelity.
- Use narrow, documented pixel tolerances and negative controls that reject changed shapes, lettering, placement, missing details and bitmap enlargement. Allow deliberate density-dependent antialiasing differences.

Build a new reference corpus for each selected desktop release. Verify its menus, launcher/panels, file browsing, window materials, controls, dialogs, typography, cursors, sounds and transitions. Record dimensions and behavior from that release, including application-specific variants. Keep reference captures labeled by version so details from another release do not silently enter the implementation. This is a reference-capture checklist; parity requirements still need to be specified for the chosen target.

Keep artwork provenance separate from code licensing. Existing NeXTSpirit packs have personal-use terms and an unresolved unrestricted-redistribution gate. Their availability does not settle the rights or suitability of artwork, fonts or sounds for the separate project.

## Concrete defects and their reusable lessons

| Observed problem | What the investigation established |
| --- | --- |
| Installed compositor loaded the wrong wlroots library | A successful build and a development `LD_LIBRARY_PATH` were insufficient. Preserve the installed RUNPATH and inspect the libraries loaded by the actual installed executable. |
| Popups went off-screen after repositioning | Initial placement was constrained, but repositioning bypassed that helper. Reuse the same policy for both paths and test real GTK/Qt popups near output edges. |
| Partly visible parents bypassed popup bounds | A parent's center could lie outside every output. Reuse the visible-area output policy and test partly off-screen parents. |
| Reused popup surfaces stopped receiving clicks | Stale pointer focus prevented a new enter event. Refresh focus on unmap/destruction and test activation, reuse and cleanup. Disabling animation did not fix the cause. |
| Mouse events exposed Linux button codes | AppKit needs zero-based public button numbers. Test press, drag and release for extra buttons as well as left/right/middle, using observed public events. |
| A desktop fixture treated a broadcast as an RPC reply | Wait for the matching completion event and retain the final state assertion. Do not replace synchronization with sleeps or weaker deadlines. |
| Clipboard reset lost ownership | Retry only the identified temporary ownership conflict. Preserve stale-write rejection and prove that a newer writer's data survives. |
| A shell marker preceded completed Terminal output | The child had written the text, but Terminal was still parsing it and cleared selection after Select All. Use an acknowledgement from the consumer: this fixture waits for a genuine cursor-position response after typed input. Restore TTY settings and keep clipboard readiness polling free of repeated resets and menu actions. |
| A live JSON log was read halfway through a record | Consume complete newline-terminated records. Keep partial-read diagnostics and continue rejecting malformed complete records. |
| Linux artifacts lost useful structure on macOS | Preserve filename case, literal symlinks and permissions inside tar archives. Verify transport hashes, payload hashes and extracted replays. |
| Failure logs contained no useful stack | Native CI lacked GDB; a package failure recorded denied attachment. Add debugger access only to disposable test containers, require an actual stack and record missing/denied/timed-out diagnostics explicitly. |
| A mapped loader cache was classified as a library | A filename containing `.so` is insufficient. Check ELF headers, retain real shared libraries and keep strict artifact-collector assertions. Test with deliberately mapped non-ELF resources so startup timing cannot hide the error. |

Wayland dispatch must keep working in default, modal, tracking and connection-reply run-loop modes. Avoid nested pasteboard publication during a mutating distributed-object request. Clipboard, Services, IME and menus expose these event-loop problems more readily than an idle sample window.

## What passing verification must demonstrate

Maintain a feature inventory and acceptance matrix before the broad rewrite. For each requirement, retain the exact revision, dependency/runtime identity, test inputs, assertions and results.

- Test actual applications and workflows. NEXTSPACE's inventory includes Login, Workspace, Preferences, Terminal, TextEdit, TimeMon, Review and OpenUp. Each new project needs its own inventory and behavior references.
- Check native buffer dimensions, real submitted pixels and logical hit coordinates together. Include repeated mixed-output transitions, odd sizes, partial repaint and resource release.
- Exercise keyboard layouts, repeat, IME/preedit, focus navigation and modifiers. Pinyin and Hangul checks exposed behavior that Latin text alone did not cover.
- Verify clipboard in both directions with independent GTK/Qt clients, fresh producer values and exact bytes, including payloads larger than 64KiB. Include primary selection, persistence after owner exit, Unicode file drags and Services.
- Verify native menu activation, modal behavior, app activation/hide/minimize and shell reconnect. A mapped window or successful launch is insufficient.
- Run clean installation, live upgrade and removal in a fresh consumer, plus a network-disabled source replay. Check actual installed runtime paths and the absence of an X server.
- Test real login/PAM/logind ownership, locking, logout and failure recovery separately from a synthetic greeter UI fixture.
- Match every claim to the scope of its evidence. Headless Pixman, another compositor, virtual DRM and physical hardware are distinct qualification environments.

Producer completion is not consumer completion. A file written by a child process does not prove the application displayed or parsed its output. Wait for an acknowledgement at the boundary being tested. A readiness predicate should observe completion; repeatedly issuing actions or resetting the value it is observing can interfere with valid asynchronous work.

A useful regression rejects the original faulty implementation with the same meaningful assertion, then passes the fixed version. Keep the original deadlines and tolerances unless evidence justifies changing the contract. A controlled failure should also prove that diagnostics capture the state needed for the next investigation.

### Performance evidence needs its own boundary

Software-rendered and virtual-DRM trials provide useful CPU, buffer-memory and rendered-state measurements. They do not establish physical 60Hz input-to-scanout latency, missed vblanks or GPU-specific thresholds. Record the renderer, hardware, mode, scale, workload and sampling method, and compare controlled cohorts. Set physical thresholds from measured hardware baselines.

A requested injection period does not establish the actual rate. In one scheduler-tracing comparison, the median injection duration increased by about 25% despite the same requested period. All eight endpoint cases passed, but the cohorts were not matched well enough for a causal conclusion. Record actual producer and consumer timing and measure observer overhead before accepting a comparison.

Unpaced synthetic keyboard bursts lost input in the two-vCPU guest. Captures establish evdev overflow and a small queue boundary in that environment; they do not establish the complete scheduling bottleneck or a product fix. Paced tests passing does not explain the failing burst. Keep that distinction when reusing the test harness.

## Development, delivery and cleanup

Use disposable headless containers for fast repeatable tests and a persistent ARM Linux guest for installed-session work. Lima is a development tool. Production packaging should install the desktop on the chosen Linux target without requiring Lima.

Local VM delivery needs the same care as application delivery. The MacBook encountered an older Lima import/start crash. The preview helper therefore checks its supported Lima version and guides first-time password setup in the macOS terminal. Validate existing VM state before repair, preserve user data and document the desktop account and administrative path. The preview uses a locked root account and explicit setup of the `nextspace` account; do not distribute a guessed/shared root password.

Keep one organized evidence store with manifests, source/runtime hashes, replay scripts and receipts. Verify an archive and a fresh extracted replay before deleting duplicate captures. Preserve the useful VM/SDK and source masters. Delete only owned test processes, containers and files; a shared guest or checkout may contain another task's work. Permission to interrupt a service for one cleanup is not standing permission to disrupt unrelated services later.

When a build or test is live, observe the same process or job until authoritative state says it ended. An observation timeout is not a reason to restart it. When one path is blocked, continue independent work. Once only external gates remain, name the missing evidence rather than generating unrelated changes or repeating passing tests indefinitely.

## Evidence boundary at handoff

At the recorded source snapshot, `1f225782`, the native and package lifecycle jobs passed in [run 41957255179](https://github.com/felixding/nextspace/actions/runs/41957255179). The native audit includes real debugger stacks, non-ELF resource exclusion and the Terminal output acknowledgement, including the actual cursor response, restored TTY, exact input and all 400 scrollback lines. The package audit verifies the completed job, exact revision, full logged lifecycle pass and artifact identity; it does not independently extract that run's package payload.

These results qualify the recorded NEXTSPACE scope. A future project needs its own implementation, visual references and verification. Consult the [implementation status](Wayland-Implementation-Status.md) and [validation summary](Wayland-Validation.json) for continuing NEXTSPACE qualification rather than treating this reusable document as a live progress report.

Still open in NEXTSPACE:

- Physical display/input, modeset, hotplug, gamma, supported suspend/resume and VT qualification; physical performance thresholds and release/default promotion.
- The unpaced keyboard stress loss described above.
- An earlier large-TIFF Review density timeout and upgraded Terminal-copy timeout whose causes remain unestablished despite passing follow-ups. Twenty fresh Terminal sessions passed 100 density cases, but did not replay the historical upgrade context.
- Confirmation of actual MacBook execution and unrestricted artwork redistribution permission. Intel/AMD qualification remains deferred.

Give every new project its own plan and evidence ledger. NEXTSPACE's estimated completion percentage, package qualification and visual references apply to its recorded scope.

## Where to start reading and reusing code

Paths below are relative to the NEXTSPACE repository. If this document is copied elsewhere, resolve those paths against the [recorded NEXTSPACE snapshot](https://github.com/felixding/nextspace/tree/1f2257829c7d9e2eabe3fc669b2761adff60bdd4). Generic mechanisms are candidates for reuse; audit dependencies, policy coupling, licenses and tests before copying them into the separate project.

| Source | Reusable knowledge |
| --- | --- |
| [Rewrite plan](Wayland-HiDPI-Rewrite-Plan.md) | Coordinate contracts, architecture, phases and acceptance matrix. |
| [Implementation status](Wayland-Implementation-Status.md) and [validation summary](Wayland-Validation.json) | Evidence references, qualified scope and unresolved gates. |
| [Compositor](../Applications/Compositor/) and [protocols](../Protocols/) | Outputs, input, transactions, focus, popups, shell authority, locking and capture. |
| [Dependency/protocol manifest](../Protocols/manifest.json) | Exact source pins, patch hashes, versions and notices. |
| [Wayland backend](../Libraries/gnustep/back/Source/wayland/) and [Cairo surfaces](../Libraries/gnustep/back/Source/cairo/) | Native event dispatch, input, selections, configure/buffer lifecycle and backing density. |
| [GNUstep patches](../Libraries/gnustep/patches/) | Run-loop fixes, backing APIs, image handling, retained scrolling, printing and controls. |
| [SystemKit](../Frameworks/SystemKit/) and [Workspace adapter](../Applications/Workspace/WaylandWindowManager.m) | Application-facing settings and the shell/compositor boundary. |
| [Wayland tests](../Tests/Wayland/README.md) and [GUI probes](../Tests/GNUstep-GUI/) | Behavior, pixels, negative controls, real toolkit comparators and reproducible runners. |
| [Debian packaging](../Packaging/Debian/README.md) | Reproducible build inputs, offline replay and installed lifecycle checks. |
| [Lima helpers](../Tests/Lima/README.txt) | Optional development VM launch, compatibility and password setup. |
| [Artwork provenance](Artwork-Sources.md) | Source selection, original-reference comparisons and usage-term records. |

## Suggested opening sequence for the separate project

1. Select the reference desktop and precise release/build, then capture its original visuals and interactions. Define what faithful recreation covers, including application behavior and any deliberately excluded compatibility promises. If multiple releases are supported, record their differences and acceptance criteria separately.
2. Confirm platform, architecture, accessibility and distribution scope. Keep unresolved hardware or redistribution gates separate from work that can proceed.
3. Evaluate the toolkit with a small native rendering and interaction gate. Reuse the working Wayland foundations where suitable, then verify the selected reference's menu, activation, panel and drawing requirements explicitly.
4. Establish shared design metrics, resource masters and versioned shell/application contracts. Centralize repeated rendering and geometry logic.
5. Build a vertical slice: session entry, shell, file browsing, the reference's launcher and menu model, a text editor and terminal. Verify real workflows and native density before broadening the application inventory.
6. Grow the reference-based behavior/pixel matrix alongside implementation. Add reproducible packaging and installed-session tests early, followed by measured hardware qualification.
