# Wayland implementation status

The compact [validation summary](Wayland-Validation.json) records the evidence
digests, supported target and remaining gates for review.

Current target (user scope change, 2026-10-30): native Wayland only. X11/Xwayland compatibility, fallback packages and their tests are outside the deliverable. Earlier compatibility results below are historical evidence. Native Workspace excludes the embedded Window Maker; upstream wlroots builds with Xwayland and the X11 backend disabled.

Current execution priority (2026-11-04) is ARM64/aarch64 on Debian 13, native
ARM64 CI and the existing Lima guest. Intel/AMD qualification is deferred.
Physical hardware and unrestricted artwork redistribution remain release gates;
they do not block ARM implementation and personal-use validation.

Current product qualification is native105/native106 on Debian 13/aarch64.
Cold build, network-disabled source replay, clean installation, live upgrade,
upgraded application workflows and removal pass in one uninterrupted consumer.
The independent audit verifies six packages, 170 ARM64 ELFs (164 private), 4,416
source inputs, 79 literal links, 321 external libraries and 510 result reports.
Both package phases complete 446 Review requests without timeout, seventy
archive extractions, three positive decoder cases and six CRC rejection controls.
The previous Review and directory failure points pass in this run; their
historical causes remain unestablished. Rendering, framework and application
inputs match the frozen cohort. Supervisor startup-error reporting now postdates
that freeze and awaits fresh package qualification. Backend/protocol/test
documentation and validation/development tools are recorded separately in the
current source audit.

The 1,029,821,535-byte capsule is
`native-current-native105-evidence.tar.gz`, SHA-256
`45a87f3d3b84418b3e1dd010286f7ebb6d0d72577d630684ca87ec873d8823c7`.
Its complete manifest and literal symlinks pass streaming verification.
The existing Lima guest runs native106 with Login preferences preserved.
Fresh systemd/greetd/PAM/virtual-DRM login/logout, user hooks and cleanup pass.
The 650,812-byte system-login capsule is
`system-greetd-native106-v2-evidence.tar.gz`, SHA-256
`8fec48481f056a913a7d23c1afd77c859e15e1c2e6c9129c559124d2977aa9fd`.
The first post-upgrade attempt encounters an older virtio-GPU kernel queue
deadlock that prevents console access and greetd shutdown. Kernel stacks and
failed-test artifacts are retained. Temporary settings are restored, the owned
guest is restarted, and temporary accounts are removed. The same unchanged
login test then passes with no blocked kernel tasks. The authoritative follow-up
is `.build/wayland-validation/after-native105-v2/state.json`; the failed v1 run
remains separate. After recovery, 4,400 installed files and 120 literal links
match native106 receipts; the check excludes three editable conffiles.
Recovery evidence is `arm64-lima-native106-recovery-v1-evidence.tar.gz`
(13,217 bytes), SHA-256
`0a13dd6505ab2cafe8b7ad6002e2d03435992eb400867d91cc17fa44945ee535`.
The current machine-readable checkpoint is
`.build/wayland-validation/arm64-current-qualification.json`.
These results qualify the virtual guest, not physical GPUs.

The installed native106 backend also passes an independent Weston 14.0.2
headless/Pixman check on Debian 13/aarch64. Without NEXTSPACE extensions or
xdg-decoration, its 801×601 logical window submits 801×601 and 1602×1202 buffers
at 100% and 200%. Backing conversions, readback and sampled image pixels pass;
six loaded private runtime files match package receipts. The exact guest package
inventory and greetd states are restored after removing 38 temporary test
packages. Foreign input workflows and fractional density remain unqualified.
The [backend contract](../Libraries/gnustep/back/Source/wayland/README.md#other-wayland-compositors)
now documents the behavior limits outside the NEXTSPACE compositor.
The 741,098-byte capsule is `arm64-weston-fallback-v1-evidence.tar.gz`, SHA-256
`c9965eea8e7ce0ef7f7c6cac2509eb6d206f49dad96cd715b674f77304a5e8a3`.
The ARM64 native CI runner now includes this fixture after its protocol-removal
matrix. Its test image pins Weston 14.0.2-1 and wayland-utils 1.2.0-2. Dependency
resolution, shell syntax and Docker's build check pass; no X server installation
is planned by those additional dependencies. This is a configuration check plus
the separately recorded native106 fixture run, not a hosted Actions result.
The configuration record is
`.build/wayland-validation/arm64-foreign-ci-v1/state.json`.

Controlled ARM64 headless comparisons now cover native100 and native106 with
three traced repetitions per version and two observer-off controls: 120 phases
and 38,400 offered inputs across all five densities. Runtime bytes match package
receipts; external package versions and 277 loaded external files agree. The
fixed output is 2400×1800 pixels, Terminal stays 585×410 logical units, and the
CPU allocation is two cores. Median CPU differences are at most 0.87 percentage
points of one core; median trial-p95 rendered-state latency differences are at
most 0.70ms. Observer-off CPU differences stay within 0.82 percentage points,
including run variation. The same five shared mappings stay stable at each
density and all disappear after every client closes. No cgroup throttling occurs.

Offered input averages 59.952–60.0002Hz; scheduling jitter and coalesced states
are recorded. Synthetic feedback runs around 44–53Hz. The pinned headless
backend rearms a relative timer after output commit and provides no hardware
timing flags or refresh period. These measurements do not establish physical
input/scanout latency, missed vblanks or hardware performance thresholds. Both
cohorts have identical key Terminal/backend rendering sources; the comparison
characterizes the native stack rather than migration cost from X11. The
2,986,534-byte capsule is `arm64-performance-v1-evidence.tar.gz`, SHA-256
`74353a9aee4f4582cbfdb098d56fe7fdc284224eade116adb0b833f9e84e9792`.
Raw traces, endpoint memory samples, actual observers, analysis and pilot failures
are retained with a 260-file manifest. Full measurements and limitations are in
`.build/wayland-validation/arm64-performance-v1/REPORT.md`.

The installed native106 Lima session now also passes a virtual-DRM software
measurement matrix: three traced trials and two observer-off controls, with
75 eight-second phases across all five scales. The output stays 2560×1600
pixels and Terminal stays 505×323 logical units on two vCPUs. The producer
offers 24,000 requests at 59.947–60.008 requests/s. All 7,200 traced wheel
events reach Terminal; 7,197 native states have matching sampled buffer hashes
at the compositor and three intermediate states coalesce. Every scroll event
changes the retained scroll position. Across densities, median trial-p95 time
from injection request to native buffer arrival is 3.884–4.779ms. All measured
Terminal mappings disappear after each client exits, and canonical PAM/session/
VT cleanup passes in every trial. CPU on/off median differences are at most
2.561 percentage points of one core, including trial variation. Memory values
are endpoint mapping/RSS samples rather than continuous peaks.

These are guest input, handler and buffer-transport measurements. Each movement
request sends the fixture's separate X/Y SYN reports; the wheel workload sends
one coarse event per request. DRM feedback has flags 15, but the pinned backend
assigns those flags from page-flip/backend properties. They do not establish host
scanout, photons or physical 60Hz qualification for this virtual device. The first
pilot's clamped scroll direction is retained and excluded; the corrected pilot
precedes the full matrix. The independently replayed 3,908,384-byte capsule is
`arm64-vz-performance-v1-evidence.tar.gz`, SHA-256
`3d133d03b56a592f9c24df4cd921934e4205231494fec63a05412a75c8444520`.
All 81 payload files and seven guest archives verify. Details are in
`.build/wayland-validation/arm64-vz-performance-v1/REPORT.txt`.

Current native106 kernel-input diagnostics reproduce a longer unpaced burst
failure at 100% in fullscreen. All 514 synthetic kernel key events are observed,
but Terminal receives 480 Wayland key events and 240 of 257 expected raw PTY
bytes. Keyboard focus does not change during the failed trace. Five preceding
paced/unpaced cases pass; later densities do not run after this failure. The
diagnostic's initial raw-PTY newline error is corrected separately: Return is
correctly delivered as carriage return. Current application/private-library
hashes match native106 receipts, and all guest settings, accounts, service and VT
are restored. Further tracing observes `SYN_DROPPED` on the compositor's evdev
consumer before libinput; downstream libinput, wlroots, seat and Wayland key
sequences agree. The unpaced stress limit remains unresolved. An unmodified
native106 control passes twenty normal/fullscreen cases across all five
densities at 10ms per key event: 6,280 keys at every stage, 3,130 exact PTY bytes
and no kernel-consumer overruns. The cursor-hide prototype is not promoted.
Evidence is retained under `.build/wayland-validation/arm64-kernel-burst-v2/`
through `arm64-kernel-burst-v6/`; the independent replay is
`.build/wayland-validation/arm64-kernel-input-audit-v1/audit.json`.
The 6,904,352-byte sealed capsule is `arm64-kernel-input-v1-evidence.tar.gz`,
SHA-256 `86172ba1d146da6dc3f42d27976a2c3bd2bce0e302727049ba0d45124765aa01`.
All 76 payload files and seven retained guest archives pass verification, and
the audit reproduces independently from an extracted copy with its own receipts.

The untraced follow-up also reproduces an endpoint failure: at 125% in a normal
window, the long burst delivers 225 of 257 PTY bytes after 26 successful cases.
A C reader avoids per-event formatting and disk writes, but can itself overflow:
its first fullscreen trial observes 482 of 514 keys while Terminal receives all
257 expected bytes. Observer integrity and endpoint correctness are therefore
reported independently. A further untraced run passes 41 cases before a 150%
normal-window burst delivers 228 of 257 bytes; its independent reader also
overflows. That burst injects 514 key events in 45ms. The complete scheduling
bottleneck remains unestablished, and later cases do not run after failure.
All temporary session settings, accounts, service state and VT are restored.
These diagnostics are under `arm64-kernel-burst-v7/` through
`arm64-kernel-burst-v9/`; no product patch is promoted.
Their independent replay checks 81 endpoint cases, including both failures,
all private runtime hashes and every cleanup result. The 2,250,835-byte capsule
is `arm64-kernel-untraced-v1-evidence.tar.gz`, SHA-256
`b83622f6ab8dabe0f07d330d8d9f531b0648d3d6f50e494f31c1d88a9ff323cb`.
All 42 payload files and four guest archives verify; extracted replay agrees.

A bounded external profiling run passes three pilot cases and 26 matrix cases,
then reproduces 222/257 PTY bytes at 150% in a normal window. All 514 key events
reach the independent reader without overrun; injection takes 61.293ms. Kernel
trace buffers and CPU samples report no losses, and fourteen private runtime
files match native106 receipts. The longest recorded input-read gap is 3.874ms,
with about 0.040ms scheduled; this does not prove that gap caused the loss.
CPU stacks include both input handling and rendering. Profiler overhead is not
excluded, the full bottleneck remains unestablished, and no product patch is
promoted. Cleanup and private trace-instance removal pass. The 1,605,872-byte
capsule is `arm64-kernel-profile-v1-evidence.tar.gz`, SHA-256
`b78ec1b61282078146bb07fc6f32665e24f163430bbb99b785572e0bd48f382e`.
The reusable `Tests/Wayland/compositor_profile.py` also passes a separate
two-second headless CLI check. Its three small guest dependencies are retained
as developer tools for future refinement.

A bounded scheduling comparison retains 31 unpaced long bursts at 150% in
a normal window. At nice 0, twelve of fifteen pass and three lose PTY bytes
despite all 514 ingress keys being observed. At nice -5, fifteen of sixteen pass;
the last case loses Return and retains 240 PTY bytes, while its independent reader
also overruns. The planned final control does not run. Injection durations vary,
so this does not establish the complete bottleneck or qualify a priority fix.
Fourteen private runtime files match native106; priorities and canonical session
state are restored. The independently replayed 1,239,802-byte capsule is
`arm64-kernel-scheduling-v1-evidence.tar.gz`, SHA-256
`974688e0409ba220e912f8ff6a2025a148e904d5e6e93559798a46453147d0c6`.

The 200% native106 desktop was shown in the Mac mini's Lima window. At the
user's request, that preview then ended cleanly for local MacBook delivery;
its home files were saved before the temporary account was removed. A stopped
VM clone removes all host mounts and imports those files into `/home/nextspace`.
The portable launcher passes a fresh Lima-home import, newly generated
controller credentials, interactive password setup and clean shutdown. Both
the prepared clone and the fresh import pass two ordinary PAM login cycles,
native Workspace/Preferences/TimeMon startup and persistent 2560×1600/200%
display settings. The seed account remains locked until the MacBook user sets
a password. These are local VZ/software-renderer checks; MacBook execution and
physical GPU/60Hz qualification are not yet established. Preparation records
are under `.build/wayland-macbook/v1/`. The ready personal-use transfer is
`.build/wayland-macbook/NEXTSPACE-MacBook.tar.gz` (1,968,758,132 bytes), SHA-256
`a9b095868935c8a30298718a999ca82cd092d2703a883fdb31cf29862f63d8d0`.
All nine payload hashes pass streaming archive verification. Both disposable
preparation/test VMs are removed after their audits; the original Lima guest,
portable seed and verified transfer archive remain.
The MacBook's Lima 2.1.4 crashes before starting this 2.2.1 export. A small
launcher update now bundles the tested Lima 2.2.1 executable, native guest agent
and license, checks the selected version before importing, and identifies the
macOS Terminal as the place for first-time password setup. A fresh isolated
import passes interactive password creation, native greeter startup and clean
shutdown using only the bundled runtime. The 19,344,257-byte update is
`.build/wayland-macbook/NEXTSPACE-MacBook-launcher-update.tar.gz`, SHA-256
`0cb615b5a0cc817f6730e4c4833de68ec79474d3b21306d20374dd31ca9f6bdf`.
It preserves the VM disk and the original full archive; MacBook execution still
awaits user confirmation.

The latest recovery update adds `Set NEXTSPACE Password.command`, which uses the
same bundled Lima and can force a new password even when the account already has
one. A disposable fresh import passes initial password creation, a second forced
reset and PAM authentication with the reset password. The native greeter remains
active with no host mounts. The test VM and its temporary controller are removed
after clean shutdown. The 19,344,454-byte update is
`.build/wayland-macbook/NEXTSPACE-MacBook-password-update.tar.gz`, SHA-256
`b7a92b5b63d05d2785f8fcb056d61e05acc85796866e58acad9d6579c1f34032`.
These are local tests; successful MacBook execution still awaits user confirmation.

The existing ARM64 Lima guest passes the kernel freezer self-test through real
logind sleep notifications. Its device-suspend test fails because kernel
`6.12.113+deb13-arm64` reports that virtio-fs suspend/resume is unsupported
(`-95`). The kernel test setting is restored and the guest remains reachable;
its later GPU queue deadlock requires the restart described above. These VM
limitations do not qualify device suspend/resume or block ARM implementation.

The native ARM64 CI uses `ubuntu-24.04-arm` for both jobs and `linux/arm64`
for Docker. The first hosted native job reaches the PAM fixture, then fails
because its root-owned temporary installation directory has mode 0700. Artifact
collection also cannot traverse private fixture homes. The test runner now makes
only the staged installation root traversable; collection takes ownership after
the container exits. Both five-density PAM tests and artifact collection now pass
in the hosted rerun. The four former X11 source/RPM workflows and their badges
are removed.

The same native job next encounters an old title-reference test requiring Xvfb.
Its original Window Maker/Xft metrics and glyphs are now fixed inputs: 169 records,
25 rasters, source/font hashes and rendering options. Native CI keeps the exact
original pixel assertions without starting an X server. Two 460-case layout runs
and nine configured fonts pass. A fresh Debian 13 ARM64 container with native106
and no Xvfb passes 147 live title snapshots and six protocol/client checks.
Independent replay verifies the original glyph comparisons. All 4,386 present
payload files and 120 literal links match package receipts; the image's dpkg
policy omits seventeen documentation files. The 846,891-byte capsule is
`arm64-title-reference-v1-evidence.tar.gz`, SHA-256
`8e28421427310d7039b2b5e7b3258abdc9d62b8272e78683666ca4987f4b3a77`.

The package job reaches the shared color-picker workflow, where the fixture
clicks tab zero and selects Named Colors instead of Sliders. Picker order follows
bundle discovery. The controls probe now reports remote picker identities and
both artwork fixtures select by identity. Native106 passes 120 image comparisons
and thirty real pointer actions across all five scales with unchanged assertions
and pixel tolerances. The 1,972,295-byte capsule is
`arm64-color-picker-order-v1-evidence.tar.gz`, SHA-256
`5627e4c47db109b1658940cf2e2ae4f351adea33b4cdd5bf59d165328e99edb1`.
These title and picker changes affect test tooling and reference data while
retaining the qualified product inputs. Full hosted-suite confirmation remains
pending.

The title fixtures load the repository fonts through a private Fontconfig
environment before DesktopKit installs Helvetica. Both 460-case suites and 147
live snapshots now pass in hosted ARM64 CI. Nine exact original font raster/metric
comparisons also pass locally without installed DesktopKit fonts or Xvfb, and
system font selection stays unchanged. The next decoration fixture incorrectly
requires more than the valid four-color monochrome palette. It now checks title
ink, both controls and the bevels directly; its full local density/input/lifecycle
fixture and missing-component controls pass. The native runner also explicitly
builds the Printing and name-server probes that its later tests require.

Hosted run `41863138262` passes the ARM64 package job: cold build, network-disabled
replay with 4,448 identical inputs, clean installation, live upgrade, application
workflows and removal. All three containers exit successfully, preferences remain
intact and no X server is installed. Its original upload reports case collisions
between ZIP and zip captures. CI now wraps results in tar archives; Linux checks
preserve both names, private modes/owners and literal links without changing the
source permissions. A second hosted ARM64 package job also passes. The latest
native job fails at installed-session startup before Workspace reports ready;
its complete tar archive uploads successfully. Its stderr does not
identify the exit cause. The launcher passes a local check with its production
Login helper, shell recovery and owned-process cleanup. The supervisor fixture
now preserves complete stdout, exit status and failure state; a real failing-shell
control verifies those diagnostics. Full hosted native-suite confirmation remains
pending.

A local full-stack continuation later times out while replacing Review's large
TIFF buffer from 175% to 200%. A separate Review run passes all 124 workflow
records with the original assertions and deadlines, including the same image
formats and save/open panels. This does not establish the earlier timeout's cause;
both results are retained and the remaining application checks continue.

The continuation completes 147 application records and 24 TextEdit printing
cases, then finds that native CI omits the desktop package's Fontconfig file.
Without it, AppKit and compositor titles select different fallback faces when
the Font panel toggles antialiasing. The runner now installs that existing
configuration after DesktopKit and refreshes its font cache. Fontconfig selects
the bundled Helvetica; all three unchanged Font-panel checks retain Helvetica
Bold at 12px. The 147 application records and 24 printing cases also pass under
this package-matching configuration. Workspace/Preferences/archive workflows,
Terminal IME and real Pinyin/Hangul also pass in the completed continuation.
The 506,866,160-byte capsule is `arm64-native-continuation-v1-evidence.tar.gz`,
SHA-256 `26550b425abcd6400ab1358dad7485ba9ae025a25cc1deb8689eabc1904a2391`.
Streaming verification checks 9,994 files, 412 literal links, modes and owners.
After a second source comparison, 1,412,707,210 bytes of duplicate test outputs
are removed; the compiled runtime and installed-bin pointer remain available.

Another hosted run reproduces the startup exit after D-Bus publication and input
method readiness. The supervisor now reports fork failures, failed polling,
closed readiness/broker channels, unexpected broker events and compositor/bus
exit codes. Six local lifecycle modes, including the installed launcher, retain
their original recovery and cleanup assertions. Compositor-loss and bus-loss
controls verify the new diagnostics. The hosted startup cause remains open;
this reporting change does not establish a fix.

Native101/native102 cold build, network-disabled
replay, clean installation and live upgrade pass. The same consumer stops during
upgraded directory artwork: after nine successful native canvases, the second
Home-viewer query returns status 1 with empty output. The failed installation is
preserved for focused diagnosis. That cohort does not complete lifecycle
qualification and was not installed into the Lima guest.
The failed query overlaps disposal of obsolete Docker containers. That timing
does not establish a cause; subsequent cleanup is kept outside active GUI checks.

A separate ARM64 component test reproduces missing OpenUp legacy extractors
and qualifies a minimal fix: runtime dependencies on `arj`, `lhasa` and
`macutils`, with OpenUp calling Debian's `arj` directly. Five negative cases and
55 native common/legacy extractions pass at all five densities. Each positive
case checks exact payload bytes, the Workspace viewer's native buffer, source
preservation and viewer closure. The original bundle and loaded private runtime
match native100 receipts; all application actors are reaped. Its 8,632,830-byte
capsule is `arm64-openup-tools-v1-evidence.tar.gz`, SHA-256
`3e93b0f64541552769a2d22c311e79f33835cd68b3295d205be574facf348c48`.
The fix and shared regression extension are now in the repository. Earlier
fixture setup errors are retained. A subsequent native103 component test covers
StuffIt, Compact Pro and PackIt: fifteen native extractions pass at all five
densities, checking both data and nonempty resource forks. It uses a private
bundle-local macunpack with an unsigned CRC polynomial; the Debian ARM64 helper
rejects the same valid Compact Pro archive. Six corrupt-header/data controls
remain rejected. The recipe reproduces the tested helper byte for byte. Its
pinned archives, minimal patch, bundle installation and shared 70-case regression
are now in the repository and included in qualified native105/native106 packages.
The 13,147,356-byte component capsule is
`openup-remaining-formats-v1-evidence.tar.gz`, SHA-256
`c60fa67ae9d329563626a17c4e455539d1a671701f77ea42485780f04b9b16ff`.
It retains the original CRC failure, fixed recipe, both focused native runs,
six checksum rejection controls and nine receipt-matched private runtime files.
Cursor staging now copies the first render rather than rendering twice; a
native comparison verifies all 118 files and 57 literal links, including modes
and ownership.
The completed private container is removed; the existing SDK and Lima remain.

Three focused repetitions of the directory workflow pass 135 native canvases
and 45 real drag cancellations on the exact native102 installation. Independent
masked pixel comparisons have maximum channel difference zero; fourteen loaded
private files match package receipts. The original failure remains unresolved.
The 16,468,018-byte diagnostic capsule is
`native101-directory-diagnostics-v1-evidence.tar.gz`, SHA-256
`2d0574d25052daf7d3fd5ccffe80295f8e0246ab7da131905e323b6663ef8483`.
The probe now identifies missing controller/viewer failures; its caller records
query timing and failed process/window state. Deadlines and visual assertions
are unchanged. Native103/native104 freezes these diagnostics and the OpenUp fix
with 4,407 source inputs, 79 literal links and fifty artist files. Its standard
cold build, network-disabled replay and independent six-package/168-ARM64-ELF
audit pass. The clean consumer stops in Review's XPM density transition:
100%, 125%, 150% and 175% pass, then a 200% preference retains a 175% buffer.
The failed consumer is preserved for focused tracing. Live upgrade and the
remaining lifecycle checks do not run for that cohort; it does not advance the
Lima installation.

Two focused native103 Review runs pass the complete 124-record workflow,
including the original XPM transition, with capture files on the container and
host filesystems respectively. These repeats do not reproduce the original
failure and do not establish its cause. Native105/native106 freezes the archive
helper, 70-case coverage, CRC controls and cursor staging simplification with
4,405 repository inputs and eleven pinned archives. Its cold build and
independent audit pass: three packages, 85 ARM64 ELFs and 4,416 source inputs.
Offline replay passes with identical source inputs, networking disabled and
source downloads blocked. The independent six-package audit passes 170 ARM64
ELFs, including 164 private ELFs, and identical input maps. Clean installation
and live upgrade pass. The same uninterrupted consumer completes upgraded
application checks and removal, and the independent lifecycle audit passes.
The complete evidence capsule is sealed and independently verified.
Both package phases pass seventy native archive cases and nine decoder checks,
and Review passes the original XPM transition. Both input engines pass all five
densities and four run-loop modes. Failed-process traces
now have gdb available in disposable consumers; an actual ARM64 attach succeeds.
The 286,658,518-byte Review diagnostic capsule is
`native103-review-density-v1-evidence.tar.gz`, SHA-256
`86e5991e8d625cf0532f5e15d96b6480a1e6bc942875200740b44b518db89e57`.
Both focused runs complete 446 requests without timeout. The later uninterrupted
native105/native106 consumer passes the same transitions without the tracer.

Previous product qualification is native99/native100 on Debian 13/aarch64.
Cold build, network-disabled replay, clean installation, live upgrade and
removal pass. The lifecycle uses an audited checkpoint: the original consumer
supplies the completed installation and live upgrade; an immutable upgraded
snapshot repeats the failed application group and completes every remaining
canonical check. This is not a single uninterrupted consumer run.
The independent audit checks six packages, 162 private ELFs, 4,401 frozen
inputs, 79 literal links, 321 external libraries and 508 result reports. It also
checks snapshot lineage, 18,041 retained prefix artifacts and both validation
source maps. Five test helpers differ from the frozen archive; their exact
executed bytes and readiness checks are retained. Product inputs match the
qualified packages.

The 1,034,547,360-byte package capsule is
`native-current-native99-consumer-resume-v4-seal-v2-evidence.tar.gz`, SHA-256
`c8d9f157a25dc3bb5a7758935780299222ef18520372619129c14a7a5fdb9df2`.
Its complete manifest and literal symlinks pass streaming verification. An
earlier seal checker rejected a tar hardlink for a duplicate driver-result
entry; the corrected writer stores regular payload entries and preserves
symlinks. The failed checker log and diagnosis remain available.

Before the current upgrade, the Lima guest runs native100. Its systemd/greetd/PAM/virtual-DRM
login/logout, user hooks and cleanup pass with Login preferences preserved.
The 651,240-byte system-login capsule is
`system-greetd-native100-v1-evidence.tar.gz`, SHA-256
`b06a953e0ff656fde5ee24e5db6d2ddc14f53e6948cb1f5d5f19d3baa354884a`.
The unmodified installed Sound module passes ten playback/input cases and
thirty native pointer volume/mute actions at five densities against independent
PulseAudio state. Its application and loaded framework bytes match native100
receipts. The 296,869-byte capsule is
`sound-controls-native100-v1-evidence.tar.gz`, SHA-256
`229b22af1d36d1cc0c86f659deeddbaac49440eea9abc87a9a42fed3c39ef6e7`.
These audio tests use a virtual stereo sink/monitor and qualify device controls;
physical audio and per-application stream controls are outside that proof.
An additional unmodified native100 application test qualifies per-application
playback and recording volume/mute controls at all five densities. Ten cases
with real private streams pass thirty native pointer control actions and ten stream
selections, checked against independent PulseAudio state. Recording uses a
non-monitor null input; the first fixture's monitor source was intentionally
excluded by SoundKit. Two subsequent fixture schema errors and their raw logs
are retained. All 23 loaded private files and the complete application bundle
match package receipts; all owned processes exit. The 551,967-byte capsule is
`sound-stream-controls-native100-v1-evidence.tar.gz`, SHA-256
`ec7b29c6b903651770126f30c6c26c78bc5364ad4d1fe78d4f7d132ddc7a4c0b`.
This extends virtual audio coverage; physical audio remains unqualified.
Short same-client idle samples are retained and do not qualify controlled
60 Hz latency, physical GPU performance or release thresholds.

Remaining full-plan gates are physical display, input, modeset, hotplug and gamma
validation; supported physical suspend/resume and VT cycles; hardware latency,
CPU and buffer-memory thresholds; and release/default promotion after those gates
and applicable artwork redistribution permission. Intel/AMD work remains deferred.
The reproduced unpaced kernel-keyboard stress loss also needs resolution;
the earlier paced trials do not explain it. Lima's virtual DRM checks do not
establish hardware results. Overall progress is approximately 93%; remaining time
is not yet reliably estimable.

Earlier implementation logs are retained locally under `.build/evidence/history/`.
