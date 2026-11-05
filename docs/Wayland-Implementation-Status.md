# Wayland implementation status

NEXTSPACE's current target is native Wayland on Debian 13 ARM64/aarch64, at
100%, 125%, 150%, 175% and 200%. All eight bundled applications are included:
Login, Workspace, Preferences, Terminal, TextEdit, Review, TimeMon and OpenUp.
The [validation summary](Wayland-Validation.json) records exact revisions,
artifact digests and qualification boundaries. The full plan remains incomplete.

## Current ARM64 qualification

Both full ARM64 jobs pass at `d33dff61` in
[run 42022229984](https://github.com/felixding/nextspace/actions/runs/42022229984).
The native job builds and exercises the toolkit, compositor, applications,
transfers, input methods, portals and session supervisor. The package job covers
cold build, network-disabled source replay, installation, live upgrade and removal.
These results qualify the earlier dead-code cleanup and the existing OpenUp
fixture's action/MIME-acceptance synchronization. Subsequent native-backend
source removal requires its own normal ARM64 CI result.

The B9 package artifacts are independently inspected: six ARM64 DEBs, all payload
hashes and literal symlinks, 170 ELF headers, and both retained source archives.
The 4,295 desktop and 727 compositor input entries match their receipts and the
exact committed Git blobs. The ci1 and ci2 source maps agree. This inspection
qualifies those artifacts; it does not infer physical hardware behavior.

The same cleaned-up B9 ci2 packages pass an isolated Lima PAM cycle: authentication,
Workspace, Preferences, TimeMon, cancelled and confirmed logout, user hooks and
return to a rendered greeter. All 64 authenticated-session and 19 returned-greeter
process/library hashes match package payloads. Private read-only mounts preserve
the installed native106 desktop, package database and service configuration.
Maintained runtime/build inputs are unchanged through `4ca9560d`. An independent
extracted replay verifies the retained session evidence.

## Native-only cleanup

SystemKit now implements `OSEScreen`, `OSEDisplay`, keyboard and mouse settings
through the native models. Login retains its unprivileged greetd/Wayland lifecycle;
its old root PAM/Xorg path is removed. Terminal's X11 resize hints and direct
X11 links are gone. Workspace has one native build/session path, with its embedded
Window Maker, X11 adapter, notification bridge and compatibility fallback removed.

Four X11 workflows and their badges, X11-only runners, fallback-package checks
and optional Xwayland test branches are removed. Twenty obsolete source-build,
installer and Xorg setup/session files are also removed. The maintained builder,
dependency pins, patches, asset generators, native session entry and user-hook
runner remain. Existing native scenarios validate this cleanup; no X11 coverage
was added. The temporary-account teardown race is fixed by retrying only the
transient busy-account result, and its hosted follow-up passes both ARM64 jobs.

The vendored backend's retired X11 server, X11-dependent ART renderer, Cairo X11
surfaces, X selection bridge and obsolete configure launchers are removed (56
files). The obsolete Red Hat X11 RPM pipeline and old Debian/Ubuntu Xorg
dependency lists are also removed. Configure now selects only Wayland/Cairo
and requires their native libraries; it no longer probes X11 or falls back to another renderer. Backend and
pasteboard builds pass with no direct X11 dependencies. Distribution Cairo/image
libraries can still have transitive X11 dependencies. The unchanged application
suite passes Review multipage/density and five-density retained scrolling, then
stops at a 175% Open-panel readiness timeout; its capture retains the directory
name and disabled OK button. The failure is preserved without attributing it to
the cleanup. The independent five-density Workspace/Preferences/OpenUp/Dock suite
passes with the rebuilt backend. No cases are added.

Seven unchanged original title-font and application-hint files remain under
`Tests/Wayland/fixtures/title-reference/originals`, with provenance, licenses and
hashes. They support original-design comparisons and are excluded from the
runtime. Artwork sources and usage terms remain in [Artwork Sources](Artwork-Sources.md).

Useful SDK and guest runtimes, source masters, generators and native fixtures are
retained. Verified sources, receipts and offline replay tools are organized under
`.build/evidence/`. Duplicate transports, temporary session captures and the
superseded guest staging copy are removed after verification. Lima remains a
development/test tool rather than a production packaging requirement.

## Performance and remaining work

Earlier controlled headless and virtual-DRM workloads measured native buffer
transport, scrolling, CPU and buffer lifetimes. They establish neither physical
60Hz input-to-scanout latency nor hardware-specific release thresholds. The
retained native106 virtual VT checks likewise do not qualify physical VT or
suspend/resume behavior.

Reader-TID captures on the recorded `225292aa` ci2 runtime identify the compositor
main thread as the input reader. All four attribution trials deliver exact input.
A subsequent normal/raised-priority comparison still fails one raised-priority
trial: 68 input records arrive during a 4.268ms read gap, including 2.633ms when
the reader is runnable but waiting for CPU time. The independent reader retains
all 514 key transitions; the compositor observes `SYN_DROPPED`. Priority is
restored after every trial. No scheduling-policy change or keyboard-stress fix
is promoted, and these captures do not explain every historical failure.

A corrected injector-CPU-accounting matrix on the retained B9 ci2 runtime completes
75 phases: 24,000 requests, all 7,200 observed scroll events, 7,198 verified native
buffer states and two coalesced states. Identity, buffer lifetime and session
cleanup pass. Timing remains unqualified: the original control has ten requests
more than one 60Hz period late (maximum 40.503ms), and its single registered
replacement has 148 (maximum 183.966ms). Both captures are retained, the replacement
is ineligible, and further replacements are not used to select a passing result.
The earlier B9 matrix's 578 late requests and 1.321-second maximum remain recorded.

A separate bounded scheduler/profile diagnostic does not reproduce that long
stall. It corrects the sampled injector PID (the actual Python worker rather than
its sudo launcher), observes host paging and verifies trace cleanup. These
observations establish no cause for the historical stall. The actual-injector PID
is now included in the existing helper's ready message; event handling is unchanged.
Independent extracted replay passes for both retained diagnostic capsules.

The remaining full-plan gates are physical display/input, modeset/hotplug/gamma,
physical suspend/resume and VT cycles, hardware latency/CPU/buffer-memory
comparisons, the extreme synthetic keyboard-burst limit, MacBook execution
confirmation and release/default promotion. Intel/AMD qualification and artwork
permission for unrestricted distribution remain deferred. They do not block
continued ARM development or personal-use validation.

Overall progress is approximately 94%; remaining time is not reliably estimable.
The [earlier implementation record](history/Wayland-Implementation-Status-4ca9560d.md)
and [historical validation data](history/Wayland-Validation-1f225782.json) retain
previous evidence and failure investigations without presenting them as current
qualification.
