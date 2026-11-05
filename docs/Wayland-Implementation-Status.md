# Wayland implementation status

NEXTSPACE's current target is native Wayland on Debian 13 ARM64/aarch64, at
100%, 125%, 150%, 175% and 200%. All eight bundled applications are included:
Login, Workspace, Preferences, Terminal, TextEdit, Review, TimeMon and OpenUp.
The [validation summary](Wayland-Validation.json) records exact revisions,
artifact digests and qualification boundaries. The full plan remains incomplete.

## Current ARM64 qualification

Both full ARM64 jobs pass at `00fe1e7c` in
[run 42050392096](https://github.com/felixding/nextspace/actions/runs/42050392096).
The native job builds and exercises the toolkit, compositor, applications,
transfers, input methods, portals and session supervisor. The package job covers
cold build, network-disabled source replay, installation, live upgrade and removal.
These results include the native-backend removal, obsolete explicit X11 development
dependencies and unused historical backend patches. Production runtime sources and
native fixtures are unchanged from the independently audited `0496e814` artifacts.
No X11 test cases were added.

The current package artifacts are independently inspected: six ARM64 DEBs, all
payload hashes and literal symlinks, 170 ELF headers, and both retained source
archives. The 4,209 desktop and 721 compositor input entries match their receipts
and the exact committed Git blobs. The ci1 and ci2 source maps agree. An independent
extracted replay passes. This inspection does not infer physical hardware behavior.

The audited ci2 packages are now installed in the 2 GiB Debian 13 development VM.
The installation verifies 4,396 regular payload files and 120 literal symlinks,
while preserving five configuration files. The prior native106 DEBs and configuration
backups remain available for rollback. Xorg, Xwayland and Xvfb are absent; the unused
Xvfb server was removed without removing shared libraries or stopping Docker.

The existing canonical PAM cycle passes against this installed runtime, with no
private runtime binds: ordinary test-account authentication, Workspace, Preferences,
TimeMon, cancelled and confirmed logout, user hooks and return to a rendered greeter.
All 64 authenticated-session and 25 returned-greeter process/library hashes match
package payloads. Service, account, configuration and VT cleanup pass. An initial
operator setup attempt used a root-only ancestor directory, preventing test-user
captures. Its failure is retained and excluded; correcting directory permissions
allows the unchanged fixture to pass. Independent extracted replay verifies the
retained installation and session evidence.

The earlier isolated ci2 PAM cycle and its 83 actual process/library hashes remain
retained separately. That cycle preserved native106 while testing private read-only
runtime mounts. The reusable private prefix, packages and probes remain available.

## Native-only cleanup

SystemKit now implements `OSEScreen`, `OSEDisplay`, keyboard and mouse settings
through the native models. Login retains its unprivileged greetd/Wayland lifecycle;
its old root PAM/Xorg path is removed. Terminal's X11 resize hints and direct
X11 links are gone. Workspace has one native build/session path, with its embedded
Window Maker, X11 adapter, notification bridge and compatibility fallback removed.

Four GitHub X11 workflows and their badges, the obsolete CircleCI Fedora build,
X11-only runners, fallback-package checks and optional Xwayland test branches are
removed. Twenty obsolete source-build,
installer and Xorg setup/session files are also removed. The maintained builder,
dependency pins, patches, asset generators, native session entry and user-hook
runner remain. Existing native scenarios validate this cleanup; no X11 coverage
was added. The temporary-account teardown race is fixed by retrying only the
transient busy-account result, and its hosted follow-up passes both ARM64 jobs.

The vendored backend's retired X11 server, X11-dependent ART renderer, Cairo X11
surfaces, X selection bridge and obsolete configure launchers are removed (56
files). Twelve unused historical patches for those retired renderers are removed
as well. The maintained Base and native GUI patch series remain. The obsolete
Red Hat X11 RPM pipeline and old Debian/Ubuntu Xorg dependency lists are also
removed. Configure now selects only Wayland/Cairo
and requires their native libraries; it no longer probes X11 or falls back to another renderer. Backend and
pasteboard builds pass with no direct X11 dependencies. Distribution Cairo/image
libraries can still have transitive X11 dependencies. The initial local application
suite stopped at a 175% Review Open-panel readiness timeout; its capture retains
the directory name and disabled OK button. The failure is preserved without causal
attribution. Both subsequent bounded runs of the unchanged 45-case Review matrix
pass, as do the normal ARM64 CI jobs. The independent five-density
Workspace/Preferences/OpenUp/Dock suite also passes with the rebuilt backend.
No cases are added.

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

Two complete matrices also exercise the current `0496e814` runtime, each with
75 phases and 24,000 requests. On the 4 GiB source VM, all 7,200 observed scroll events,
7,179 native buffer states and 21 coalesced states pass integrity and cleanup checks;
ten requests exceed one 60Hz period of producer lateness (maximum 88.347ms).
After a clean reboot at the existing 2 GiB MacBook preview setting and removal of
unused Xvfb, all 7,200 native buffer states pass with no coalescing, but 79 requests
are late (maximum 224.122ms). Both matrices retain all five trials, unchanged
workloads/criteria and no replacements. They remain unqualified for a steady-rate
comparison. Late input requests do not count missed display frames, and these
records establish no cause or isolated RAM effect. Docker and its running services
remain unchanged. Independent extracted replay passes for both retained capsules.

A bounded diagnostic identifies a repeatable benchmark-driver pause: a generation-1
garbage collection overlaps 28.733ms of one 29.167ms send/acknowledgment interval.
This is measured wall time, not CPU attribution or an explanation for every stall.
Moving producer collection before each phase and disabling automatic collection
only during timing removes all recorded GC overlap. The desktop, input events,
deadlines and cleanup assertions remain unchanged. A fresh five-trial matrix then
completes 75 phases and 24,000 requests, with all 7,200 observed scroll events,
7,184 verified native buffer states and 16 coalesced states. Integrity and cleanup
pass, but 16 requests exceed the original timing limit (maximum 130.644ms).
The result remains unqualified. All trials and earlier failures are retained,
with no replacements; independent extracted replay passes. The corrected producer
and replay tools remain in the evidence capsules for future refinement.

The remaining full-plan gates are controlled performance qualification, physical
display/input, modeset/hotplug/gamma,
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
