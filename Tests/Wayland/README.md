# Native Wayland feasibility tests

These runners cover the native Wayland rewrite in
[`Wayland-HiDPI-Rewrite-Plan.md`](../../docs/Wayland-HiDPI-Rewrite-Plan.md).
It does **not** complete the desktop migration or qualify a daily-use session.
The current target is native Wayland only (user scope change, 2026-10-30).
The production build excludes Window Maker, X11 sessions and Xwayland. Earlier
compatibility results in this evidence history are outside the current scope.

Automatic pull-request and master CI runs the `Wayland ARM64` workflow on
Debian 13/aarch64, including native backend and desktop package lifecycle checks.
The former X11 source and RPM workflows are removed.
Each uploaded artifact contains a tar archive that preserves Linux filename case,
private fixture permissions and literal symlinks. The native archive retains logs
and test results; the desktop archive also includes its package build inputs.

Native and package consumer containers include GDB and add only `SYS_PTRACE`
for failure diagnostics inside their private PID namespaces. `process_failure.py`
requires a real stack from an owned live child, verifies the debugger detaches
and checks that an exited child is not attached. Failure JSON distinguishes a
collected stack from a missing debugger, denied attachment or debugger timeout.
The diagnostic retains its fifteen-second deadline and disables debuginfod
network requests. This does not alter installed desktop privileges.
Its runtime inventory checks ELF headers before classifying mapped library-like
paths. The regression keeps the loader cache and a non-ELF `.so` file mapped,
excludes both from library evidence and retains real shared libraries. The package
collector's strict ELF assertion remains unchanged.

## Reproduce on Linux or Docker

```sh
docker build -f Tests/Wayland/Dockerfile -t nextspace-wayland-test .
docker run --rm --init -v "$PWD/wayland-results:/results" \
  -e NEXTSPACE_WAYLAND_BUILD_DIR=/results nextspace-wayland-test
```

The container installs build dependencies. The runner builds patched Base 1.31.1
and pinned GUI 0.32.0
with the existing NEXTSPACE patches plus backing/session IPC patches and NextSpace theme,
the native Cairo
backend and the separate Meson compositor. It installs only inside the disposable
container. Do not run `build.sh` on a workstation whose GNUstep install must be
preserved. GNUmake remains the application/backend build system.

On a prepared Debian 13 development machine, `sh Tests/Wayland/build.sh` runs the
same checks. Build logs and native PNG captures go in
`$NEXTSPACE_WAYLAND_BUILD_DIR` (default `/tmp/nextspace-wayland-build`).
Use a fresh build directory after changing the GUI patch set.
`NEXTSPACE_WAYLAND_CAPTURE_DIR` enables the backend's optional buffer captures;
normal applications do no capture I/O.

Headless fixtures use a private defaults database and user-library directory.
This prevents an old backend in the user's `Library/Bundles` from shadowing
the configured package or private runtime. System and local library paths
still come from that runtime's GNUstep configuration.

The native integration run also exercises GTK and Qt clipboard shortcuts in both
directions with AppKit at all five densities. Each producer writes a distinct
UTF-8 payload for each density; every transfer exceeds 64KiB. Exact data checks
retain the original buffer-size and logical-pointer assertions. The probes use
Ctrl-C/Ctrl-V, and the existing native probe publishes its text with `c`.
The focused qualification rejects both the original Qt probe without clipboard
support and a producer that acknowledges a new copy while reusing old text.
The same GTK/Qt comparisons open a 200×120 native popup near the output edge,
check its density and constraints, move its parent, then activate it through real
pointer input. `p` opens the popup. GTK's `--popup-controls` allocates its menu
button before presentation. An original-compositor control preserves the
off-screen failure from a later positioner request; the fixed compositor passes
all ten popup cases and keeps the clipboard checks unchanged. Each density also
opens and activates another popup while its parent is partly visible and its
center lies outside every output. These twenty popup cases cover output selection
and pointer focus when GTK reuses a popup surface. Calibration mode preserves the
existing 801×601 minimum, and the native reference window returns to its intended
output after the comparisons.

Native integration also checks the public `NSEvent` button number and event type
for press, drag and release across all five densities. Forty cases cover the
eight standard mouse buttons, producing 120 checked events with stable logical
coordinates. Button numbers follow the [GNUstep event constructor contract](https://www.gnustep.org/resources/documentation/Developer/Gui/Reference/NSEvent.html):
zero for left, one for right and two for middle. Extra buttons produce other-mouse
drag events. Probe logging observes events before ordinary AppKit dispatch;
the real NSTextField middle-click paste checks remain enabled.

`source_links.py --artifacts ...` checks source snapshots and replay before a
cold package build. It preserves all 57 cursor alias chains, rejects flattened
or shortened links, and includes targets outside the initially selected folders.
It also runs original-artwork fidelity from the compositor's isolated source
tree, so checkout-only Python helpers or image archives cannot hide missing
package inputs. This check needs the same Pillow and librsvg tools as the build.

Use `WaylandProbe --image-reference original.tiff reference.png` to export the
RGB representation GNUstep actually selects at 100%, including correct alpha.
The JSON output identifies the selected representation. Do not choose the first
or largest TIFF frame as a design reference: equal-sized grayscale and color
frames can contain different artwork. `artwork_reference.py --probe ...
--artifacts ... --preferences` checks all ten pinned module-icon originals,
including the second color representations selected for Date, Screen, Sound and
Expert at all eleven densities. The source and package runners include this
exact-pixel check. `--sound-controls` also checks the four pinned mixer originals
at all eleven density selections. These references do not qualify their
high-resolution replacements. `--folders` checks all nineteen selected folder
resource paths, including fifteen additional aliases of the closed design.
The shared alias check verifies each resource hash, selected representation and
RGB pixels. The source and package runners include it; the focused helper run
passes 22 cases including alpha and both grayscale/color TIFF orders.
`--expert <original.tiff>` remains available for a focused
Expert check. The regular image-format suite also tests
RGB selection in both TIFF frame orders and partially transparent reference pixels.
`artwork_fidelity.py --artifacts ... --reference-probe ...` compares all enabled
theme reconstructions against these device-selected originals. The two checkbox
states match exactly at 100%, and native button checks cover all five target
scales. `theme_images.py --image ...` can qualify selected reconstructions while
the default still requires the full library. Enlarged-bitmap checks include
fractional densities because an aligned vector rectangle can legitimately match
nearest scaling at 200%.

`date_fidelity.py --artifacts ...` checks the clock against the pinned RGB
original: outline, 49 dark marking anchors, face/bevel palette and high-density
curvature. Nine negative controls reject altered markings, position, palette,
shading, traced pixel outlines and bitmap enlargement. `--image <Date.tiff>` also
requires all five submitted representations to match the qualified SVG and
retain their logical size. Source CI and installed/upgraded package checks run
this regression. The Preferences coordinate probe focuses the matrix while
measuring its image rectangle, using the same backing-pixel alignment as drawing;
the native comparison retains its existing one-level tolerance.

`screen_fidelity.py --artifacts ...` checks both overlapping panels against the
selected RGB original, including 189 exact black/white border anchors, both green
indicator pixels, proportions, 67 shading regions and smooth shading at 800%.
Ten negative controls reject changed geometry, palette, lighting, indicators,
traced dither cells and enlarged bitmaps. `--image <Screen.tiff>` validates all
five submitted representations. It runs in source CI and installed/upgraded
package checks. Screen and Date share pinned-original and representation checks
in `artwork_reference.py`.

`keyboard_fidelity.py --artifacts ...` checks the Keyboard icon against the
device-selected original. It preserves 240 frame pixels, 240 black key pixels,
68 white key highlights, six indicator pixels and the face opacity. It checks
the chassis/cable silhouette, palettes and smooth high-density keycap/face
lighting. Ten negative controls reject missing/moved parts, changed palettes,
traced shading and enlarged bitmaps. `--image <Keyboard.tiff>` verifies all five
submitted representations. Source CI and installed/upgraded package checks run
this comparison; `preferences_artwork.py --module Keyboard` checks the real icon
matrix at all five scales.

`mouse_fidelity.py --artifacts ...` checks the Mouse icon against its selected
original, preserving 38 gray frame pixels, 82 white highlights, twenty black edge
pixels and the translucent face material. It checks both button divisions,
chassis/cable contours, palette and continuous lighting. Twelve negative controls
reject moved/missing parts, changed palettes, traced curves/shading and enlarged
bitmaps. `--image <Mouse.tiff>` validates all five submitted representations.
Source CI and installed/upgraded package checks run this regression;
`preferences_artwork.py --module Mouse` checks the live icon matrix at all five
scales.

`sound_fidelity.py --artifacts ...` checks the original speaker cabinet, recessed
grille and two driver domes. It preserves 79 gray frame pixels, 65 white
highlights, 49 black aperture pixels and 52 blue edge pixels. Highlight/shadow
weight and centroids protect driver shape and placement separately from regional
color differences. It also checks continuous cabinet and cast-shadow lighting.
Fifteen negative controls reject moved/missing drivers, altered materials, traced
shading and enlarged bitmaps. `--image <Sound.tiff>` validates all five submitted
representations. Source CI and installed/upgraded checks run this regression;
`preferences_artwork.py --module Sound` checks the actual icon matrix at all five
scales. Keyboard, Mouse, Sound, Services, Localization and Expert share associated-alpha regional error metrics.

`services_fidelity.py --artifacts ...` checks the original stack, tray, hand and
blue cuff. It preserves all 703 occupied stack pixels and 47 white rim pixels,
and checks the contour, opacity, regional palette and three reflection positions
and weights. Each hand, tray, cuff and shadow detail must be rendered from
geometry at higher density. Twenty negative controls reject changed shapes,
materials, missing details, traced shading and bitmap enlargement.
`--image <Services.tiff>` validates all five submitted representations. Source CI
and installed/upgraded checks include the regression;
`preferences_artwork.py --module Services` checks the real matrix at five scales.

`localization_fidelity.py --artifacts ...` protects the three flags, metal poles,
individual hoist bindings, globe contours, lighting and transparent lower edges.
All 160 landmarks, including 111 white shaft pixels, match the selected color
original exactly. Contour weights and centers are checked separately from
regional color differences. Each curved/lit detail must be rendered from
geometry; 800% field and shadow samples must vary smoothly. Twenty-nine image
mutations reject changes to geometry, materials, bindings, globe details, bevels,
shadows and high-density rendering. Four malformed curve cases protect against
SVG renderers silently truncating path data. `--image <Localization.tiff>` checks
all five submitted representations. Source CI and installed/upgraded checks
include the regression; `preferences_artwork.py --module Localization` checks the
actual icon matrix at all five scales.

`expert_fidelity.py --artifacts ...` checks the original UNIX certificate,
asymmetric foil spokes, ruby ring, colored center contours, green mark, forked
ribbon, three ink rows and coral signature. It checks 51 exact black/white paper
pixels, the alpha contour and area, seven material regions and eleven feature
weights/centers. Small paragraph shapes preserve visible ink contours without
inventing a text transcription. Ten detail crops must render genuine geometry
at 800%. Twenty-six negative controls reject changes to the design, plain-rule
substitutions for the ink, traced details and enlarged bitmaps.
`--image <Expert.tiff>` checks all five submitted representations. Source CI and
installed/upgraded checks include the regression;
`preferences_artwork.py --module Expert` checks the actual matrix at five scales.

`sound_controls_fidelity.py --artifacts ...` protects the four original Sound
Mixer designs: the blue speaker and its offset chrome edge, acoustic arcs,
microphone capsule/fork/pedestal, and chrome level dots. It checks occupied bounds,
opacity-weighted area, material errors and separate blue/neutral weights and
centers. Every detail must render genuine geometry at 800%. Forty negative
controls reject missing parts, shifted or desaturated art, traced details and
enlarged bitmaps. `--images <Sound-module-resource-directory>` verifies all twenty
submitted TIFF representations. Source CI and installed/upgraded checks include
this gate. `sound_artwork.py` checks the actual Mixer image views at five scales,
including initial images and both modes, with native backing-pixel alignment and
half-opacity disabled images. The original Gorm geometry is pinned in
`artwork-originals/sound-mixer-layout.json`: the application group clips the bottom
of the original microphone images. Eight native original-raster comparisons
establish this baseline; the redraw checks preserve its positions and clipping.
The 44 visible-symbol and halo comparisons qualify image rendering with an absent
audio server; they do not qualify audio transport.

`folder_fidelity.py --artifacts ...` checks the shared closed/unavailable leather
portfolio master in `Applications/Artwork/Folder.svg`. It protects 54 spine and
binding landmarks, occupied bounds, covered area, six leather regions, the upper
bevel, rolled fold, bottom edge, cast shadow and thirteen high-density maroon
crease samples. Separate material weights and centers retain the original
lighting. Fifty-four negative controls reject missing parts, changed hues,
traced details and enlarged bitmaps. `--images <directory>` also checks the ten
submitted TIFF representations named `closed.tiff` and `bad.tiff`. Source CI
includes this source-design gate. `folder_resources.py` checks all 17 consumer
paths, 85 frames, four source aliases and five unsafe-target controls.
`folder_artwork.py` checks the real Workspace Icon viewer at all five densities,
including a directory made unreadable by removing permissions and, for root
fixtures, filesystem override capabilities. Its independent reference includes
NSImage destination clipping. The installed lifecycle invokes both the original
design and native consumer checks. A private trial passes ten exact image
comparisons; the full current-source package lifecycle remains open.

`nextspirit.py --pack <pack-root> --artifacts ...` verifies both complete
NeXTSpirit sets and 77 master-derived frames. The folder generator and native
runner accept `--nextspirit <pack-root>` for the personal-use preview. All 90
resource frames and 30 native comparisons pass for closed, open and unavailable
folders. The runner uses the actual `DragProbe` from the adjacent probe directory
(or `--drag-probe`) for five cancelled file drags and five completed Unicode-file
copy drops. It checks the pointer hit target before pressing, the destination
density of the drag image, exact copied bytes, source retention and closed-image
restoration. The SVG fallback passes ten regression comparisons. Deposit artwork
and additional large icons remain open. The artist's usage terms are recorded in
[artwork sources](../../docs/Artwork-Sources.md).

`nextspirit_apps.py` checks the actual Terminal and Preferences Info-panel logos
using the same importer and resource writer. Its private native trial covers
three TIFF paths, fifteen host/Linux representation comparisons and ten native
captures over all five densities, with at most one color level difference.
`WorkspaceProbe --application-logo Terminal|Preferences` reports the actual
image-cell placement after every density change. Terminal's animation timers
are delayed for static captures only; its animation strips remain unqualified.
Preferences' live 64-point clock stays active and adopts all five densities.
The runner records the owned Terminal PTY child and verifies process cleanup.
Both application executables and 223 unrelated bundle files remain unchanged.

`nextspirit_workspace.py` adds Home, the static empty/full Recycler states and
the generic application monitor to the existing owned Workspace artwork session.
Its thirteen resource paths pass sixty-five native representation selections.
Fifty-five real image comparisons cover Home, empty/full/restored Recycler,
`.app`, `.debug` and `.profile` wrappers without custom icons, three invalid
application-file types and a real ELF executable at all five
densities. A uniquely named owned file exercises the actual filesystem
notifications and count badge, then is removed. The test scales the display
that contains the managed Recycler, rather than relying on output enumeration
order. Its background reference uses the pinned theme tile. NXTIcon references
intersect the backing-aligned legacy clip with the fractional image destination.
`WorkspaceProbe --workspace-home` selects an Icon viewer; `--workspace-recycler`
reports the actual Dock image and badge. The matching first animation pose reuses
the static NeXTSpirit master; the other three poses retain their original artwork.
The generic-application fallback resolves DesktopKit's `NXApplication`; its
fifteen visible-image comparisons are exact. The distinct green-question-mark
and UNIX screen constructions add twenty exact comparisons.

`monitor_screens_fidelity.py` checks the two original screen designs in
`MonitorScreens.svg`, independently of the imported housing. It protects the
question's hook, stem and dot; individual UNIX letters; variant lighting;
checker spacing; five Dock marks; window border, gadgets and title strip.
Sixteen negative controls reject design changes, omitted details, translation,
bitmap enlargement and a flat background. Source CI invokes this check without
the NeXTSpirit pack. `--pack <pack-root>` also checks fourteen density frames for
unchanged housing pixels outside the SVG screen layer. Both source checks and
the actual native captures pass in the private `monitor-screens-v2` cohort.
Ink-overlap checks protect stroke shape, including the N's diagonal; final
review also preserves the X's full cap height.

`root_fidelity.py` checks the original computer's monitor, purple glass, stand,
drive housing, slots and green indicators. Eight negative controls reject altered
designs and bitmap enlargement. `artwork_reference.py --root` verifies both
original resource paths through the actual image reader. `WorkspaceProbe
--workspace-root` selects the real `/` component in the Path view. The folder
runner's `--root-artwork` option checks its native rendering at all five densities,
reusing the existing isolated Workspace session and pixel reference. Installed
desktop lifecycle checks enable this option. The private `root-artwork-v2` cohort
passes five exact root captures and thirty exact folder regression captures.
The source manifest now includes shared `Applications/Artwork` inputs.

`terminal_strips_fidelity.py` protects both scrolling strips' original lettering,
palette, row spacing and high-resolution geometry, with forty-five glyph checks
and twelve negative controls. `artwork_reference.py --terminal-strips` verifies
the ordinary and Gorm originals. `terminal_animation.py` checks eight scrolling
and reset positions in the real Info panel and active miniwindow at all five
scales. It runs an owned shell/foreground job, pauses the Info timers, pins the
capture positions and verifies cleanup. The reference models bitmap bounds,
cropped destination clipping and the miniwindow's half-point image origin.
It waits for a changed presented buffer before comparing a new frame. Clipped
sampling has a two-level channel limit, with at most 2% of pixels above one level;
the qualified cohort has 52 such pixels across 133,088 compared pixels. Installed
desktop lifecycle checks include this runner. Other workflow and release gates
remain separate.

`recycler_footprint.py` compares the import layout with the native-reader original
empty/full bounds. It rejects invalid rectangles, translations, full-canvas
replacement and off-center source padding. `--pack` additionally verifies ten
frames and that every cropped artist pixel is preserved before downsampling.
`artwork_reference.py --recycler` covers the two static originals and four
animation poses. Legacy logical dimensions come from the reader's metadata.

The NeXTSpirit Workspace runner also exercises real Recycler move-drag entry,
four-pose cycling, cancellation and restoration at all five scales. Its ten
static-image comparisons and twenty HiDPI animation comparisons are recorded
separately. The first pose must contain the same five native representations and
bytes as the fitted NeXTSpirit static icon. The three missing poses use
`Applications/Workspace/Artwork.svg`; fifteen native resource selections must
match their direct SVG renders. Source fixtures remain unchanged, and the owned
drag-source process is reaped.

`recycler_pose_fidelity.py` checks nine separate original ribbon silhouettes,
their occupied bounds and ink weights, original green palettes and eighteen
highlight/shadow zones. Twenty-seven negative controls reject translations,
wrong poses, mirroring, changed palettes, flat lighting, missing arrows and
nearest/Lanczos bitmap enlargement. Only the fold shadows are blurred; the
ribbon edges and curved geometry render directly at each target density.

`timemon_pause_fidelity.py` protects the original red stipple, round counter and
diagonal slash; seven negative controls reject changed designs and enlarged
bitmaps. `artwork_reference.py --timemon` checks the native-selected original and
its Gorm alias. `timemon_pause.py` exercises the real application at all five
densities, compares paused pixels against the selected TIFF frame and unchanged
running graph, and changes density while paused. A separate real CPU-load case
verifies timer updates, a stable pause and updates after resuming. The installed
desktop lifecycle runs these checks. This covers the pause mark and rendering;
TimeMon's full user workflow remains open.

`timemon_static_fidelity.py` checks the transparent startup rings and colored
Info diagram against native-reader originals. All 942 solid-color samples in
twelve sectors match exactly; eighteen negative controls reject altered designs
and enlargement. `timemon_static_artwork.py` opens the actual Info panel through
its menu popup, checks the image's five representations and native pixels, then
quits through the normal keyboard shortcut. The native icon-view checker covers
the startup resource. Gorm's embedded bitmap is replaced through the existing
DesktopKit bundle-image helper. Source and installed lifecycle checks include
both designs. The legacy hammer resource remains unqualified.

`timemon_workflow.py` opens Preferences through the actual menu and edits the
period, lag and layer fields with native keyboard input at all five scales.
It checks saved defaults, normal quit and restart, minimum values, exact README
scroll restoration, five cancelled and ten completed color transfers across
mixed-density outputs. A period edit while paused must keep the icon frozen
under CPU load and take effect after resuming. `WorkspaceProbe --timemon
controls` reads public widget metadata; `DragProbe -ColorDrag YES` offers and
receives an archived native color. The default file and text drag paths remain
available. The installed lifecycle runs this workflow.

`drag_start.py` moves the pointer to the destination while the source's real
AppKit began callback is delayed, then stops moving it. Ten actual color drops
must enter and complete across separate/shared clients and all five densities.
The compositor must pick the current target when the protocol drag starts;
another pointer motion must not be necessary. `DragProbe -DragBeginDelay .5`
provides the callback delay. Installation and upgrade both run this regression.

`color_wheel.py` uses TimeMon's real Set button, brightness slider and wheel
input to exercise the shared color panel at all five densities, then returns to
100%. It exports the existing cached bitmap without copying the live image
object. Every cache pixel is checked against an independent HSV/alpha formula;
native interior colors are checked separately from the marker and fractional
edge coverage. The original 100% pixels and the two-point margin are preserved.
The Wayland GUI patch regenerates this cache at the window's backing scale.
Static picker artwork has separate checks below.

`color_picker_fidelity.py` compares the four Gray/RGB/CMYK/HSB diagrams with
their pinned native-reader originals: alpha and geometry match exactly, colors
differ by at most one level, and 32 negative controls reject altered layouts,
palettes, missing markers, flat ramps and enlargement. `artwork_reference.py
--color-panel` checks all seven original panel resources. Their TIFFs, reader
references and upstream license are retained in `artwork-originals/color-panel`.
`color_picker_artwork.py` exercises the actual panel's four mode buttons at all
five scales, compares their images and the main picker image, and quits normally.
The pinned GNUstep subpickers report mode masks rather than enum values; the
fixture records that existing behavior. Picker tabs are selected by their actual
remote picker class, so bundle discovery order does not change the target. Both
this runner and `color_wheel.py`
use the shared setup in `color_panel.py`. The normal GUI build renders qualified
symbols from `Libraries/gnustep/Artwork.svg` before building the picker bundles.
`magnifier_fidelity.py` protects the original magnifier's circular rim, split
crosshair, transparent lens and shaded brown handle with twelve negative controls.
`magnifier_artwork.py` checks its actual button, full premultiplied cursor buffer,
hotspot and tracking exit at all five scales. Tab moves keyboard focus away
between captures so the focus ring does not overlap its translucent artwork.
These checks cover the image and cursor; color values have separate checks.
`color_pick.py` exercises gesture-authorized selection from an independent
ordinary Wayland client: all eight output transforms, five densities, mixed
outputs, exact magnifier buffers, denied forged/expired/replayed/foreign serials,
busy requests, swallowed selection clicks and eight cancellation/cleanup paths.
Space, Enter and keypad Enter also require a fresh owned keyboard gesture;
foreign clients and replayed keyboard serials are rejected. Five actual output
captures check the visible cursor independently of its buffer metadata.
`color_pick_native.py` drives TimeMon's actual shared NSColorPanel button and
checks preview, selected RGB values, opaque sample alpha and restoration after
Escape/right-button cancellation at all five densities. Native checks also seed partial alpha, verify its
restoration, activate the focused magnifier with Space and select with Enter.
Both run during the installed package lifecycle. `capture.py --sample-color` independently compares
the cursor-free scene sampler with captured output pixels; transparent content,
negative output origins and transformed outputs are included. These headless
checks do not establish physical GPU behavior or complete the rewrite.
`picker_icons_fidelity.py` checks the named-color heading, exact purple swatch
and pseudo-text layout, plus the static wheel's outline, hue order, saturation,
shaded rim and translucent center mark against the pinned originals. Nineteen
negative controls reject altered designs and enlargement. The heading uses
fitted TeX Gyre Heros regular contours; its original font is not identified.
`picker_icons_artwork.py` compares both actual mode-button images in named and
wheel modes, checks density selection and exercises ten mode actions across all
five scales. It identifies the buttons from control metadata and shares the
existing panel setup and image-placement comparison.

`login_fidelity.py --artifacts ...` checks all seven Login designs against
the pinned originals. Panel checks cover the wordmark contours and face material,
all four cube-letter bounds/palettes/ink weights, shaded faces, background lighting,
frame and separators. The 800% background must vary smoothly away from the source
raster grid. Field checks retain exact alpha, 17,608 fill/bevel pixels and 1,640
transparent pixels. Label checks cover alpha contours, lettering, palette and
the transparent gap. Button checks cover the original symbols, frame, captions,
pressed displacement and palette. Forty-seven negative controls reject design
changes, raster-grid traces, traced captions and bitmap enlargement.
`--images <Login.gorm>` verifies every submitted representation against its SVG
geometry. These source comparisons are separate from native qualification.

`login_fields.py` runs the actual greeter at all five target scales, compares panel
regions, field borders, labels and normal/pressed buttons with independently
composited TIFFs using measured image placement. It exports both images assigned
to each button. The panel
regions cover the wordmark, cube, separators and frame; field masks exclude the
overlaid text controls and their carets. Original-reference fidelity checks run
separately from this native-buffer comparison. The normal/highlighted assignments
must match the original Gorm archive; the older real binary is rejected for
reversing them. This fixture also checks keyboard authentication against the
synthetic root peer. It shares account setup with the existing greeter tests.
Their default whole-panel check and the full seven-image representation gate
remain unchanged and pass with all seven reconstructed designs. This fixture
does not qualify installed PAM/session integration or the full package lifecycle.

`gamma.py` checks two unsupported headless outputs, correlated rejection replies
and older shell-version negotiation. With `--workspace-probe`, it exercises the
actual Objective-C client in all four run-loop modes. Meson's `gamma` test checks
LUT endpoints, power curves, clipping, invalid inputs and wlroots state storage.
`GammaModelProbe` covers public SystemKit mapping, rejected-state preservation,
worker-thread dispatch and fades. Native CI and future package lifecycle runs
include the model probe. These are software tests; Lima reports gamma size zero,
so successful hardware LUT application is still a release qualification gate.

The real-app suite also checks Review scrolling with a patterned image at 200%
zoom. Five density cases move the actual scroll origin with wheel input and
require the complete image/scroller frame to match exactly after scrolling back.
The previous GUI fails at 125%. NSClipView now redraws for fractional physical
translations and rounds reusable rectangle edges in backing pixels. Logical
scroll coordinates remain unchanged. This regression runs automatically whenever
`integration.py` receives `--review` and `--review-probe`; it reuses the existing
Review RPC, capture and runtime checks. The TIFF page/zoom cases remain separate.

`rectangles.py` checks 70 native rectangle/path/transform cases at all five
densities and forces ten input-driven redraws. Integral UI primitives must have
stable pixel edges, while explicit paths and fractional/transformed geometry
retain their antialias setting. Use `--baseline` with the old backend, then
`--reference /path/to/baseline --backend libgnustep-wayland` for exact explicit
geometry comparisons. Supply `--pasteboard-server` and `--pasteboard-probe`;
the runner starts and reaps private session storage before launching its minimal
window. `build.sh` includes the candidate checks. The application runner also
compares Terminal's complete frame and scroller after scrolling, separately from
its retained text. The original backend fails at 125%; the pixel-grid candidate
passes all five densities, native integration and the twelve-profile printing
matrix. The frozen evidence has an independent host audit. The native9/native10
package cohort includes this renderer and passes cold build, offline replay and
clean install/live upgrade/removal with the strict Terminal frame check. Its
archive audit verifies 3,823 inputs, six packages and 94 validation sources.

`printing.py --compositor ... --probe ... --artifacts ...
--pasteboard-server ... --pasteboard-probe ...` uses `PrintingProbe`
to export a portrait page through PDF, EPS and the normal printer save path.
Run again with `--unflipped` for bottom-origin view coordinates. Both modern and
classic runtimes pass all five densities and a return to 100%: page dimensions,
mark placement, extracted text and per-format raster pixels remain identical.
A persistent image changes its screen representation with backing density;
printing consistently uses its highest-resolution representation. The old GUI
fails the flipped-view orientation check. The pinned patch shares the PDF/EPS
drawing routine and restores the root view's flip without using screen scale.
The runner owns per-session pasteboard storage and waits for an AppKit-dispatched
readiness event before sending input. It requires Poppler and Ghostscript,
included in the test image.
`gpbs-startup.json` retains readiness replies and server state for startup
failures; the readiness deadline is unchanged.
`x11-workspace.py --printing-probe ...` reuses its existing unprivileged
Workspace/Xvfb setup for both printing orientations. A bare Xvfb display does
not provide GNUstep's normal window-manager startup contract. These tests do
not spool a physical print job; broader application print workflows and physical
queues remain separate qualification gates.

`event_queue.py --compositor ... --probe ... --artifacts ...` exercises six
backend event-delivery contracts: nested reply loops, selective waits, unmatched
event retention, nested getters with different masks, peeking/dequeuing, and
idle selective timeouts. The CPU checks detect spinning while waiting for a
different event type. Source CI and installed/upgraded package checks include
this regression through `EventQueueProbe`.

The extended matrix adds `--profile crop` and `--profile landscape` to the same
fixture. Both runtimes pass 36 density/view/profile cases, 108 format checks each.
Cropped PDF/EPS pages normalize the requested rectangle origin; landscape exports
retain its logical dimensions while normal printer jobs keep physical paper
rotation. The previous candidate deterministically fails both geometry checks.
All six printing profiles also pass with the rebuilt X11 backend under Workspace,
alongside its eight existing workflows. Early private configurations omitted
printing bundles, fallback PPD and GUI panel resources; those setup failures are
retained. The initial landscape raster check also assumed the wrong rotation;
its correction follows the actual physical page marks. Both complete matrices
pass without changing screen density, printer margins or pagination behavior.

The printing fixture now supports `--nested --reference /path/to/flat/results`.
Nested and flat output must match exactly for PDF, EPS and printer save files.
Both runtimes pass 72 density/view/profile/tree cases. This exposed incoherent
printing-root inverse/descendant caches; the old GUI fails the printer raster
comparison. A real TextEdit trial also exposed fractional paper fitting adding
endless numerical sliver pages. The fix compares final edges at machine
precision. `printing_textedit.py` checks continuous/paged documents and both
orientations through six density transitions: all sixty lines, full pagination
and exact page rasters must survive. The modern native run passes 24 cases and
72 printed pages, with owned pasteboard storage started before the application.
The unprivileged X11 fixture additionally passes twelve flat/nested exports,
four TextEdit print combinations and its eight Workspace workflows. These are
save-only document API checks; print-dialog interaction and physical queues
remain open. Initial mode-recreation, resource lookup and converter-rotation
fixture errors are retained alongside the failing prototypes.

The second runner builds the complete NEXTSPACE runtime, SystemKit, DesktopKit,
Terminal, TextEdit, Review and TimeMon inside another disposable container:

```sh
docker build -f Tests/Wayland/Dockerfile.native-stack -t nextspace-native-stack-test .
docker run --rm --init --cap-add=SYS_PTRACE -v "$PWD/wayland-native-results:/results" \
  -e NEXTSPACE_WAYLAND_BUILD_DIR=/results nextspace-native-stack-test
```

Build the base image above first. Runtime sources are pinned by revision and
archive checksum in `native-stack-sources.json`: libdispatch/CoreFoundation 5.9.2,
libobjc2 2.2.1, GNUstep make 2.9.2 and base 1.31.1. This runner uses the modern
Objective-C ABI and the repository's filesystem layout. It records compiler flags
and linked libraries alongside the test results.
Use an init process for containers so orphaned GNUstep helpers are
reaped between scenarios. Keep runtime installs separate from active tests.
Build every fixture from the same source snapshot as its runner, including
`PasteboardProbe`; older fixtures do not recognize the primary-selection modes.
The headless GTK comparisons use Cairo, matching the compositor's software
renderer. They do not qualify GPU rendering.
Run the complete GUI suites serially while shared per-user helpers remain under
qualification. A captured Dock-client abort exposed reentrant distributed
notification registration in Base. `NotificationCenterProbe` deterministically
reproduces the original exception; the pinned connection patch passes on both
Objective-C runtimes. Three direct-exec Workspace workflows pass with the fix.
Broader launch stress and a separately retained pasteboard-clear failure remain
open; passing reruns do not erase those failures.

`session_lock.py` drives independent lock, ordinary-client, IME and shell
connections. It checks every output's actual pixels before acknowledgement,
exact fractional lock buffers with opaque rounding margins, input isolation,
held input, native GNUstep repeat cancellation and resumed input, eight output
transforms, mixed density, negative origins, disable/re-enable, hotplug and
fail-closed crash recovery. The initial ten groups and six normal signal shutdowns pass
on both Objective-C runtimes; the exact modern compositor also passes the public
display model and eight Workspace groups. This core contract is included in the
normal build runner. Frozen evidence is under
`.build/wayland-validation/lock-{modern,classic}-*`.

`lock_pam.py` is a separate opt-in check requiring root, an explicit
`--disposable-container` flag and a container environment. It creates and removes
a temporary account, runs compositor and packaged `swaylock` as that user, and
requires real wrong-password rejection before successful unlock at all five
densities and after a locker crash. Debian `swaylock` 1.8.2-1 passes. The test
does not replace the system PAM policy. Automatic idle locking, suspend/VT,
fractional-sharp locker artwork and installed session locking remain open.

The integrated candidate adds shell version 17's immediate blanking request,
ordinary apps opened while locked, and a separate `--greeter` request-isolation
case. `lock_pam.py --supervisor /path/to/nextspace-session` tests the actual
supervisor and installed foreground launcher. It checks Ctrl-Alt-L and supervisor
SIGUSR1, real PAM rejection/success at five densities, blocked password-free
locker SIGUSR1, crash recovery, three bounded zero-status exits, ten-second
startup timeout, manual recovery and cleanup. Actual loaded compositor/locker/PAM
libraries and authentication module hashes are recorded. The final supervisor
also passes all eight existing lifecycle modes, 63 checks, on both runtimes.
One earlier installed-launcher run failed after its first unlock while another
native matrix ran; its cause remains unproven and the desktop stayed locked.
Subsequent serial installed checks pass. The disposable Docker image explicitly
enables this PAM suite with `NEXTSPACE_TEST_LOCK_PAM=1`; direct Linux builds leave
account creation opt-in.

Add `--logind-probe /path/to/logind-service-probe` to the supervised PAM test to
use an owned fake system bus. It verifies PID-derived session lookup despite a
forged environment ID, wrong-session and wrong-sender rejection, ignored Unlock,
locked/unlocked hints, nonfatal hint denial and preserved locking after bus loss.
Both runtimes pass; the disposable build runner includes this case separately
from its missing-session fallback test.

`lock_logind_guest.py` reuses the greetd/PAM fixture for a real logind check. Its
test-only user agent launches the supervisor as an authenticated user's child,
preserving the actual PAM/logind scope. The guest driver checks the resolved ID,
`loginctl lock-session`, true/false `LockedHint` at five densities, PAM unlock,
recovery, close_session, regreet and cleanup. This passes headlessly in Lima with
the active VT unchanged. Pass its explicit `--disposable-guest` opt-in and the
stream-capable `LoginSessionProbe`; the earlier non-stream selection failure is
retained. The agent and its control files are test fixtures only.

The supervised fake-logind case also measures the suspend guard: a pipe-backed
delay inhibitor must remain held until all outputs present opaque protection,
even with a hung locker. Monotonic timestamps bind frame protection to FD
release. Valid PAM authentication before resume cannot expose the desktop;
resume retains locking and reacquires the inhibitor. Tests cover queued
resume/prepare notifications, unlocked system-bus loss, login1 owner replacement,
PID-based reconnection and locked-hint reconciliation. Both runtimes pass.
`lock_logind_guest.py --check-sleep-inhibitor` additionally verifies the real
logind lease's UID/PID and its removal after the owned supervisor exits. This
passes in Lima with tty1 unchanged. No test here requests actual suspend or VT
switching; those release gates remain open.

`workspace_power.py --compositor ... --workspace ... --probe ... --artifacts ...`
reuses the normal Workspace harness and creates its own fake logind bus. It
drives the real logout panel's Power off button through denial, a five-second
timeout and acceptance at 100%, 150% and 200%. A live density change must repaint
while the reply is pending; failures retain the desktop and dismiss with Return,
while acceptance finishes normal exit 129. The test guards the private bus
address before sending any UI power request. Native traced and uninstrumented
runs pass all nine cases. Earlier fresh-process quit-shortcut misses are retained
with their cause unresolved. This does not exercise real power authorization or
actually power off the host or guest.

The driver uses `AlertProbe --power-layout` to measure the actual DesktopKit
panel and button geometry before opening the modal panel. It verifies that the
dialog fits its owning output, then clicks the measured Power off button. The
layouts include a gap, a different owning monitor and negative origins. The
timeout redraw changes that owning output. The shared `alerts.py` bounds check
also covers the ordinary ten-alert fixture. The retained old DesktopKit library
fails the gap check deterministically.

`workspace_power_pam.py --supervised --disposable-guest` runs those nine cases
as an actual greetd/PAM user through `workspace_power_session.py` and the
production private-bus supervisor. It waits for Workspace readiness, verifies
the inherited PAM scope and records the mapped libraries. Every accepted case
must return 129 through the supervisor, reap all owned processes and remove its
private bus. The outer fixture checks PAM closure, regreet, account/service/unit
cleanup and an unchanged active VT. This mode passes in Lima; all power requests
remain on the owned fake bus.

## Live Linux display validation

`live-display.py` exercises an already-running native Workspace session through
its production display settings service. Run it as that session's user with
the supervisor's `NEXTSPACE_SESSION_ID`, `WAYLAND_DISPLAY`, `XDG_RUNTIME_DIR` and
GNUstep runtime environment. Use current fixtures from the same runtime build:

```sh
python3 Tests/Wayland/live-display.py \
  --probe /path/to/fixture/obj/WaylandProbe \
  --workspace-probe /path/to/fixture/obj/WorkspaceProbe \
  --artifacts /path/to/new-results-directory \
  --mode 2560x1600
```

The optional mode must appear in the primary output's advertised modes. The
runner checks native buffers at all five densities, logical dimensions, image
readback, all eight output transforms, explicit cancellation and timeout
rollback. It restores the starting layout on exit. Use a fresh artifacts
directory and a dedicated test desktop with one enabled output; the test visibly
changes its display configuration. Mixed-output checks remain in `outputs.py`.
With a current `WorkspaceProbe` and an initially active native document, add
`--zoom-application Terminal` to check maximize/unzoom, work-area containment and
exact floating-frame restoration at every density. The fixture tracks the
document's public window number after focus moves to the rendering probe.

This passes on Lima 2.2.1 with a Debian 13 arm64 guest, the `vz` display,
virtio-gpu DRM/KMS, logind seat ownership and the Pixman renderer. The standard
`linux-image-arm64` kernel supplies DRM support absent from the cloud kernel
used by this VM. The checked run used kernel `6.12.113+deb13-arm64`, a transferred
modern GNUstep test runtime and a compositor rebuilt inside Lima. This is a
virtual display qualification, not a clean-install or physical GPU result.
Artifacts are retained locally under `.build/wayland-validation/lima-gui/`.

`linux_input.py` is an opt-in DRM/libinput check for the dedicated Linux test
desktop with an idle Terminal shell. It needs `python3-evdev`, `udevadm` and
noninteractive sudo access to the selected input nodes and `/dev/uinput`:

```sh
python3 Tests/Wayland/linux_input.py \
  --workspace-probe /path/to/current/WorkspaceProbe \
  --keyboard /dev/input/event1 --pointer /dev/input/event2 \
  --artifacts /path/to/new-input-results --mode 2560x1600
```

Select the VM's actual keyboard and absolute pointer nodes first. The fixture
creates disposable copies without grabbing or writing to the source devices.
Ten normal/fullscreen trials check key/main focus, paced keyboard delivery to
Terminal's PTY, backing scale and exact fullscreen restoration at all five
densities. Typed commands create unique markers under `/tmp`. Original display
settings are restored, and the virtual devices are removed on exit. Display
transactions share `display_service.py` with `live-display.py`.
For host screenshots, `--snapshot-scales 120 240` pauses fullscreen at those
densities: save the image after `snapshot-ready.json` reports that density, then
create `continue-120` or `continue-240` in the artifacts directory within 45 seconds.
This checks synthetic Linux input through libinput in Lima; physical host input,
real GPUs and the retained unpaced burst-input failure remain unqualified.

## Checks

- `supervisor.py --private-bus` activates an actual GDBus service and checks its
  Wayland/Xwayland address, runtime directory, backend and desktop context.
  It retains shell-recovery checks and verifies forced cleanup of an activated
  service that ignores termination. Bus loss, compositor loss, failed bus startup,
  failed publication and a hanging publisher are covered. `--launcher` also
  exercises the opt-in user entry point. Original supervisor modes remain covered.
  Private runtime paths contain address delimiters and spaces; every exit path
  must remove the owned bus socket directory.

Live JSONL event readers consume only newline-terminated records. The first
partial read is retained beside its log; malformed complete records still fail.
This keeps producer scheduling from turning an incomplete write into a parser
failure without weakening behavior assertions or deadlines.

- `decorations.py` uses an independent xdg-decoration client to test default,
  explicit and changing frame preferences, acknowledged commits and invalid-mode
  rejection. It checks actual title pixels and backing extents at all five
  densities, content coordinates, frame move/resize, Escape, mixed outputs and
  negative origins, shell replacement, shade, minimize, maximize/fullscreen,
  close-button cancellation and normal close. Client input barriers ensure
  frame press/release events do not leak into content. Actual title pixels also
  update after shell-driven minimize/restore while the client is stopped.
  Application-v7 trials also check atomic frame metrics, invalid requests,
  style-specific controls, borderless geometry and restoration after metric
  changes. Content grabs retain their release when crossing a server frame.
  `integration.py --server-frames` requires actual native frame selection,
  cropped surface extents, viewport source pixels and compositor title buffers.
  Owned document-edited metadata repaints without requiring a surface commit.
  X11 frames, remaining title/group actions and full visual parity remain open.
- `titlebar.py`, called by `decorations.py`, exercises the 13-state retained
  X11 gesture baseline at all five native frame densities. It also checks XOR
  axis transitions, fullscreen restoration, partial-maximize drags and Escape
  in all four drag modes, the five-unit logical threshold, compositor-only
  releases after cancellation, selection borders, high-resolution wheel steps,
  configured click intervals and shell replacement. The real Mouse Preferences
  workflow separately verifies interval publication and restores its initial
  value.
- `state_requests.py`, also called by `decorations.py`, sends independent
  client maximize, restore and fullscreen requests during armed and moving
  frame grabs. Its 480 cases cover five densities, all maximize axes and all
  four drag modes. Requests must cancel the move, preserve the original floating
  frame and prior fullscreen axis state, and retain the frame button release.
- `native_frames.py` uses public AppKit APIs through the existing application
  connection. Independent client-drawn close controls provide the visual oracle
  for clean/edited and normal/pressed server controls at all five densities.
  It also checks edited state before mapping (including deferred windows) and
  after hide, miniaturize and order-out restoration, retaining actual library
  mappings and PNGs. Whole bezels and artwork use shared physical edge rounding.
  An edited close request still passes through the AppKit delegate's veto and
  acceptance before its surface disappears.
- `native_fullscreen.py` calls the actual AppKit `toggleFullScreen:` API and
  checks public frame/content/screen geometry, complete backing extents and
  content input in the former title/resize bands. Thirty cases cover five
  densities, floating/maximized state, client/server frames and transparency.
  Captured buffer corners remain opaque for opaque windows and preserve alpha
  for transparent windows. Real popups, density changes while fullscreen,
  exact restoration and removal of the fullscreen output also pass in the
  staged modern runtime. Classic-runtime and real-display qualification remain
  separate gates.
- `title_layout.py` uses the compositor's actual layout helper and fixed
  references captured from the original Window Maker functions and Xft. It checks
  density-independent metrics, prefix/tail shortening, intact Unicode clusters,
  malformed UTF-8 and actual ink at all five scales. The generated GPL reference
  retains the original notices and is separate from the MIT compositor.
  Both the legacy monochrome default and `--antialiased` mode compare ASCII
  metrics and exact 1x glyph pixels. The [reference manifest and maintenance
  instructions](fixtures/title-reference/README.md) pin source/font hashes and
  rendering options. Native CI does not start or require an X server.
- The optional historical `font_config.py` reference tool compares matched
  Fontconfig properties with actual Xft:
  global antialias/hinting rules, explicit face files, hinting/autohint/bitmap
  settings and the legacy antialias fallback. Metrics stay logical across five
  densities; complete 1x glyph pixels match, and CJK font fallback is checked.
  Matrix, variation and subpixel properties, legacy XLFD names and complete
  frame raster parity remain open.
- `title_appearance.py` checks actual trusted-shell font/antialias/justification
  changes against the same fixed original glyph pixels, including explicit hinting and
  face-file changes, an actually stopped
  application, all five densities, shell replacement, invalid inputs and four
  Objective-C run-loop modes. `--legacy-compositor` additionally verifies that
  the new client safely declines the operation on an older frozen compositor.
- `title_states.py` compares real AppKit client frames with server-rendered
  normal, main and key titles at all five densities. Fifty captures check the
  background and text palette, a real modal panel, foreign application focus
  and restoration. A paused client retains its main hint while the compositor
  repaints from actual focus. Fixture notifications observe the modal state
  directly; distributed-object calls do not answer in that loop. The independent
  protocol fixture also checks invalid hints and ensures an unfocused key/main
  hint cannot claim focus or another connection's active appearance.
- `window_states.py` drives GTK maximize/fullscreen requests on native Wayland
  and managed Xwayland. It checks all five densities, negative origins, exact
  floating-frame restoration, nested state changes, initial requests, transient
  dialogs, mode changes and output removal. Native requests also choose an
  explicit output. A small translucent protocol surface checks centering and
  actual black-border pixels at every density, plus focus transfer to another
  application. A separate connection creates a non-focusable icon and verifies
  that it cannot reactivate its document over the focused application. These
  checks run through `build.sh` on both runtime paths.
  The standard GDK move path also checks all four `DragMaximizedWindow` modes
  at five densities, Escape restoration, retained displacement after scaling,
  invalid input and shell replacement. Native and Xwayland drags include negative origins.
  At each density, GTK also requests unmaximize/fullscreen while a move is
  active, then verifies exact floating restoration. Failures retain the current
  case, hit target, pointer focus and recent client input events.
  Xwayland keeps a floating frame that fits the smallest work area. Twenty
  exact pointer checks alternate positive and negative output origins through
  all five densities. GTK's actual X server configure events acknowledge the
  translated geometry before input is sent. Both runtime paths pass the full
  negative-origin window-state matrix. `drag.py --negative-origin --file-drag`
  also checks Unicode file-URI copies, negotiation, cancellation and completion
  across native/X11, GTK/X11 and X11/X11 in both directions. Five routes cover
  thirty mixed-density drops per runtime. Runtime records retain actual backend
  bundles, including filenames without `.so`, and every trial's output/window
  positions. Independent host audits reapply the pinned wlroots patches and
  check all recorded payloads and logical coordinates.
  `outputs.py --state-client /path/to/gtk-probe` keeps both states alive through
  the production rotation/rollback/hotplug suite. Covered clients are brought
  into view before requiring new backing pixels. Both window paths also reserve
  and release logical Dock space while maximized; fullscreen keeps the full
  output. Actual `NSScreen.visibleFrame` values match the compositor through the
  production output suite in all four Workspace run-loop modes. The real
  AppKit zoom API also maximizes and restores the native fixture in every rotated
  layout, including a delegate veto and windows without autosave names. The real
  Workspace visibility/restart test checks Dock and IconYard work areas, and the
  settings fixture preserves the existing overlap preferences. This latest GUI
  API has been qualified in the staged modern Lima runtime; the classic runtime
  and complete server-frame parity remain release gates.
  `workspace.py` drives actual AppKit title bars through five density changes,
  maximized movement, exact unzoom and Escape cancellation. It also checks that
  a stale apply preserves a completed rollback result, records recent display
  RPC results on failure and bounds cleanup of an unresponsive shell. The
  intermittent native Dock-launch disappearance has also occurred in isolated
  runs; an instrumented-launch pass does not close that stress gate.
- An inherited supervisor capability authorizes exactly one shell connection.
  Public registry access and guessed binds fail even with a Workspace app ID.
  Invalid passed descriptors are released. Replacement, shell crash/reconnect,
  complete state recovery and supervisor revocation preserve unrelated clients.
  Workspace's actual Objective-C shell client receives complete metadata and
  controls windows in default, connection-reply, modal and menu-tracking run loops.
  Its private descriptor is consumed before helper launch, is close-on-exec, and
  cannot share ownership with the toolkit's public connection. Public endpoints
  supplied through the private descriptor argument still cannot bind the shell.
- The standalone C supervisor creates fresh session names, discovers native and
  optional Xwayland displays, and passes only the intended shell capability.
  Its actual shell client launches a GTK child, survives a shell crash/restart,
  and preserves its window state. Normal exit and compositor loss end the
  session and reap descendants, including an adopted child that ignores
  termination. Invalid runtime permissions, compositor startup failure and a
  repeatedly failing shell are rejected. Login/user-service integration remains open.
- Geometry: all five densities, odd dimensions, negative coordinates, shared-edge
  rounding, outward damage and coordinate orientation.
- Two headless 1600×1200 outputs with software rendering and `DISPLAY` unset.
- The existing GNUstep GUI fixture builds a native 801×601 window with text,
  controls and a selection field. The compositor inspects actual committed buffer
  dimensions; application notifications verify the backing conversion round trip.
- Image representation selection accounts for backing density separately from
  logical device resolution. A two-representation fixture selects the denser
  asset above 100%; a fine vector pattern must match direct primitive drawing
  inside its one-pixel image-clip boundary at every density. Both AppKit readback
  and submitted PNGs are checked, with separate cropped-opacity samples.
  Allocated view gstates must redraw into the current backing surface. Higher-density screen drawing bypasses fixed-resolution
  intermediate image caches. Explicit offscreen image storage stays unchanged.
- Glyph drawing honors AppKit's supplied advances at every density. A deliberate
  custom-advance fixture checks the logical pen position, independent of device
  hinting. Existing X11 and print/PDF glyph paths remain unchanged.
- Move the same window repeatedly between 100% and each target scale. Inject real
  Wayland pointer events and verify the same logical click position at every scale.
- Change scale while mapped, confirm it, and test compositor timeout/disconnect
  rollback. Invalid scales and confirmation without a pending transaction fail.
- Resize through xdg configure/ack, verify largest-area output selection on both
  sides of a spanning window, and check stable tie behavior. Close native windows
  using the actual client-drawn close button. Snap configure sizes to an AppKit
  cell grid; skip Terminal's X11-only base-size access on native backends.
- Validate owned placement, reject invalid surface roles, recover offscreen
  requests, and align a real fractional popup after edge adjustment and parent
  movement. Add/remove a scaled headless output three times and recover windows.
- Exercise special keys, UTF-8, configured Control mapping, repeat and release.
  Read back known colors, bitmap drawing, cached image compositing, image buttons
  and overlapping retained copies at every backing density.
- Render an odd-size custom/vector cursor at all five densities and inspect its
  actual pixels, logical hotspot and buffer extents. Keep its window spanning
  mixed-density outputs and move only the cursor across them. Verify themed
  cursor size/hotspot stability, hide/unhide across a scale change, and all
  missing-global/old-surface fallbacks.
  `cursors.py` also loads a synthetic animated theme with distinct frame sizes,
  hotspots and delays. Actual submitted pixels must advance through every frame
  in all four AppKit run loops at each density; hiding, pointer focus changes,
  custom-image replacement and an explicit alternate theme remain covered.
  The complete cursor test requires authored geometry at eleven densities, with
  aliases, hotspots and frame timing stored in a shared manifest. Native builds
  select reconstructed designs and preserve original files for pending designs.
  `cursor_fidelity.py` checks original opaque pixels or foreground/ink regions,
  gray hand creases, pencil/skull details, opaque palm fills and menu shades,
  soft-shadow appearance over black and
  white backgrounds, every generated
  representation, hotspots and aliases.
  Color-region comparisons preserve the original green, pink and bevel palettes;
  straight wireframe segments retain their original opacity. Negative controls
  reject translated, recolored or faded designs. It also rejects
  bitmap enlargement. `cursor_artwork.py` drives the reconstructed designs through
  actual native buffers at all five densities, sharing the animation test's
  buffer checker. It owns and reaps native session storage through
  `--pasteboard-server`, using the adjacent `PasteboardProbe` fixture.
  Startup and cursor-observation failures save process state, mapped libraries
  and optional backtraces before cleanup. The ping and native-buffer deadlines
  are unchanged. Source CI and installed/upgraded package tests include it.
  All 57 designs are reconstructed, with 649 representations and no original
  fallbacks. The three busy-cursor phases use continuous color fields with the
  original hue orientation, shading, gray hub and shadow. `watch_fidelity.py`
  independently checks their common outline, interior colors, hue and hub; seven
  negative controls per phase reject design changes. `watch_artwork.py` regenerates
  the SVG gradients from their authoring model using only the Python standard
  library. The complete native check has 300 cases and 340 frame observations,
  including animation in all four run-loop modes. One partially transparent
  pencil edge near the binary ink threshold has an explicit 64-level visible
  antialias bound. Its other ink labels and original gray details remain
  protected; a flat replacement of the uncertain edge is rejected. Earlier
  intermittent startup failures and complete current-source package qualification
  remain open.
  `theme_images.py` checks reconstructed theme images for logical size and density
  selection. The five hand/drag images share faithful cursor geometry and are
  compared with the original TIFFs selected by AppKit. Original alias chains are
  retained when a cursor is rebuilt; the fidelity check rejects flattened chains.
  `image_formats.py` also verifies thirty density selections for square, rectangular
  and one-pixel strip images in both representation orders. TIFF metadata must
  preserve logical size when only one axis differs from 72 DPI.
  The compositor draws the same title-control geometry with Cairo.
  Login's panel, field labels and power/restart buttons use a shared SVG master.
  `login_artwork.py` verifies 35 AppKit density selections, logical dimensions
  and independently rendered high-density pixels. Odd dimensions must select
  the rounded fractional representation instead of falling back to the largest.
  Diagnostic PNG capture runs after buffer submission and uses fast lossless
  encoding. `capture_png.py` verifies odd dimensions, RGB/alpha channels, exact
  agreement with Cairo's encoder and failed writes. Capture compression must not
  hold a resized buffer back from the compositor.
- Open a real detached menu, invoke its item with pointer input and preserve
  document keyboard focus. Track a held pointer through two nested submenu
  popups and invoke the leaf action; captured coordinates and global pointer
  polling must agree across differently sized logical outputs.
  Complete a modal panel through AppKit's modal run loop
  and restore document focus after it closes. Version 2 of the application
  extension lets owned auxiliary windows decline keyboard focus; version 1
  placement clients remain covered.
- Version 3 preserves floating levels during focus changes and keeps a real
  AppKit popup clickable above an overlapping floating client. Miniaturize and
  restore at every density, changing output scale while hidden; require stable
  logical dimensions, AppKit state/notifications and submitted image-button pixels.
- Shade/unshade native client frames across all densities without changing logical
  geometry or backing extents. Verify title/body hit regions, retained content,
  pointer focus and popup dismissal. Shell protocol versions 1 and 2 remain covered.
- Select the native backend for child applications through the session environment,
  preserving explicit backend arguments. Separate Workspace RPC, distributed
  notifications and the live application registry between two concurrent sessions.
- Stress 64 additional output transitions and check shm mapping/descriptor counts.
  Close another window inside a backing-change callback and require clean exit.
- Repeat with fractional-scale, viewporter or owned placement missing, and with
  surface version 1 both with/without viewporter. Expected fallback densities are
  reported separately; unsupported surface requests must never be sent.
- Start managed rootless Xwayland, verify focus, placement, logical pointer input,
  WM_DELETE_WINDOW and clean shutdown. Verify its privileged shell global is hidden
  from normal clients. Legacy buffers keep their original density and are resampled;
  this does not establish sharp mixed-density X11 rendering.
- Keep native pasteboards/Services names separate across sessions. Prove Unicode
  and opaque-type storage across client exits; perform a real `NSPerformService`
  round trip between native clients. Send Unicode clipboard data larger than
  64 KiB through an independent protocol client and through Xwayland in both
  directions, including INCR. Verify imported GNUstep storage after the owner exits. Independently read the
  compositor-owned selection after native, raw Wayland and X11 producers exit,
  including opaque bytes. Explicitly clear a selection, then publish a stalled
  source; require capture timeout, freed payload storage and successful redraw
  during the stalled transfer.
- Suspend the native fixture while queuing repeated keyboard enter/leave events,
  then resume it and require a fresh redraw, retained foreign keyboard focus and
  unchanged clipboard storage. Stale AppKit focus events must not reactivate the
  old window; imports must not read offers invalidated by focus loss.
- Keep primary selection in the separate session `Selection` pasteboard. Reuse
  the clipboard MIME/pipe code and the same XWM for native/protocol/X11 Unicode
  transfers over 64 KiB at 100%, 150% and 200%. Reject an unknown input serial,
  preserve data on focus loss and clear it after source exit for a focused client.
  Verify real text-field selection from an initially empty pasteboard and actual
  middle-click insertion, including batched mouse drag/release delivery. Seed and
  independently verify the clipboard before checking that primary operations
  leave it unchanged. Both runtime configurations exercise this path.
- Compare independent GTK 4.18 and Qt 6.8 raster clients with `DISPLAY` unset:
  actual odd-size buffer extents and identical logical clicks at all five densities.
  Their test windows omit toolkit frames to make the coordinate comparison explicit.
- On the complete runtime, type into Terminal's PTY, select/copy 400 lines of
  scrollback and retain those contents across all five densities. The owned shell
  waits for a genuine cursor-position report before publishing its typed marker;
  this proves Terminal parsed the preceding output and echo. `terminal_output.py`
  consumes the response without echo and restores the original TTY settings.
  Issue Select All/Copy once after that barrier, then poll without resetting the
  clipboard. The original content assertions and deadlines remain unchanged.
  Open a plain-text
  document in TextEdit, replace its contents, save it and change density without
  altering the saved text. Open a known PNG in Review and verify all four quadrant
  colors and native buffer extents through the density matrix.
  Review additionally opens a three-page TIFF through its existing document
  API, checks page selection and 100%/200% zoom, and retains a zoomed page while
  moving between outputs through all five densities. All 49 native checks
  compare actual buffer pixels with the selected page and logical image size.
  The previous application deterministically shows a different page after zoom.
  The same page/zoom sequence passes seven X11 checks using actual Xvfb pixels
  under the existing unprivileged Workspace fixture. The runners share their
  document, action sequence and assertions. They restore changed output scales
  and reposition the main fixture before subsequent resource checks.
  TimeMon's real custom-vector icon graph redraws under changing CPU load at
  every density, retaining its logical size and using native buffer extents.
  OpenUp extracts a 108,000-byte Unicode archive member with spaces in its path,
  opens the result in Workspace, cancels its real modal archive chooser during
  a density change and removes its working directory on normal Quit. Its
  supported-format panel retains logical size at 100%, 150% and 200%.
  The five common suffixes (zip, ZIP, tar, tgz and gz) and nine legacy suffixes
  (lha, lzh, arj, hqx, bin, macbin, sit, pit and cpt) extract exact owned payloads at all five
  densities. All 70 cases check the actual native Workspace buffer, preserve the
  source archive and close its viewer before the next case. Legacy fixtures and
  their provenance are in `fixtures/openup`. StuffIt, Compact Pro and PackIt
  also preserve a nonempty resource fork. A bundle-local pinned macunpack fixes
  signed polynomial extension when generating CRC tables on ARM64. Three
  decoder cases verify both forks; six corrupt-header/data controls must fail
  CRC validation. Disposable consumers include gdb for failed-process traces. The runtime package supplies
  `unzip`, `arj`, `lhasa` and `macutils`; OpenUp calls Debian's `arj` directly.
  The source-test image supplies the same helpers. Copy, generic and rejected
  move-only offers retain the existing 25 native file-drag checks.
  These applications retain distinct xdg application IDs and their native client
  PIDs throughout the matrix. Application IDs grant no shell authority.
  These are minimal functional trials, with rendered
  buffers retained for visual review.
  Image assertions cover close-button cache survival and replacement of TextEdit's
  original line in the rendered pixels. Offscreen image caches keep their explicit
  pixel dimensions when monitor density changes.
  At every density, real Wayland wheel events scroll Terminal into its retained
  history and back; the rendered tail must match its previous pixels exactly.
- The complete runtime also builds an opt-in native Workspace. Start it with a
  private shell capability and no `DISPLAY`, open a file viewer through its
  existing distributed API and double-click the native Recycler icon. Check
  actual document/menu/icon/Recycler buffer PNGs at all five densities. Two GTK
  instances verify grouped process tracking, focus and independent removal.
  Restart Workspace with those clients alive and recover their unchanged windows.
  Grow an output without moving documents, then place both displays above and
  left of the origin. Dock icons follow the actual output bounds and retain
  pointer input. Global screen-change notifications are coalesced across output
  batches; application readbacks may follow a backing notification.
  Seed an isolated native Dock configuration and launch a native app and GTK by
  double-clicking their pinned icons. Adopt the running native icon, activate GTK
  without another process, and restore the launcher after exit. Exercise the real
  Dock/Advanced preference views through Workspace's existing connection, persist
  edits/collapse through restart, and hide/show Dock and IconYard independently.
  Hide and Hide Others followed by native Dock unhide retain the same toplevel,
  logical geometry and shade state. Client-hidden reusable menus and miniwindows
  remain separate from the shell's presentation policy.
  The shared Desktops view edits names, count and custom switching prefixes
  through the window-manager adapter. Restart Workspace with those settings
  active, verify the new keys and restore the preceding value. Native edits
  preserve the X11 files. Both runtimes exercise atomic shortcut replacement,
  invalid/duplicate rejection, shifted keys and restoration in four run-loop modes.
  Check normal/keep-on-top ordering and timed automatic raising/lowering against
  a partially overlapping document. Keep overflow pins accessible in IconYard.
  Application and launcher icons share one backend tracker with miniwindows.
  Real serial-validated drags cover logical jitter thresholds, Escape, pin/unpin,
  unlocked slot swaps and locked pins through all five densities. Save free
  positions in the separate native settings and recover them after Workspace
  replacement, including replacement during a live grab. Miniwindow dragging
  and double-click restoration pass at 100%, 150% and 200%. Foreign groups
  receive one IconYard tile when unpinned and keep their existing process on
  double-click and re-pinning.
  The Foundation model separately verifies legacy import, height profiles,
  persistence and unchanged X11 settings. Icon dragging, full hide/workspace,
  remaining preferences, assets and session policy remain open.

`drag.py --matrix` drives actual AppKit and GTK drag APIs through the compositor's
normal pointer path. Forty-seven cases cover Unicode text, file URI lists, copy/move,
two processes and one shared connection, distinct local/external masks, rejected
prepare, deprecated completion callbacks, leave/reentry and desktop/Escape
cancellation. Every transfer crosses mixed outputs through all five densities.
It asserts destination and source completion coordinates, stable gesture IDs,
local source identity, logical image offsets, actual drag-image pixels and odd-size
buffers. Native images follow their own output with fractional and integer
fallbacks. Raw invalid-grab requests are rejected, and valid source-less gestures
also run with Xwayland enabled. Native/GTK sources transfer into Xwayland GTK
receivers, including an INCR payload over 64 KiB. Failed and closed receivers
cancel the source. Remote, malformed and NUL file URIs are rejected. Delayed
mixed-format drops distinguish transfer deadlines from time spent hovering.
X11 sources also transfer into AppKit/GTK and other X11 clients. The receiver-close
regression pauses an X11 source until its native receiver has disappeared, then
checks failed completion without requesting deletion. The bridge retains the
reply state until XdndDrop arrives instead of losing its cancellation response.
X11 leave/reentry waits for the source's actual action acknowledgement.
All 47 scenarios pass in the modern GNUstep Lima runtime. Each native case owns
its session pasteboard process. Full modifier/action policy, promises, broader
failure stress, return animation and application file operations remain open.

The runner builds wlroots 0.18.2 from its checksum-pinned source plus the manifest's
XDND patches. These fix MIME advertisement and completion in its existing
XWM and add incoming-source handling. Clipboard
text aliases keep their previous behavior. Source-cache hashes
are checked before reuse and retained with the validation results.

The full NEXTSPACE runner also builds the default X11 backend and Workspace,
checks that the latter has no Wayland link dependency, and exercises the shared
Dock/Advanced preferences and a legacy client's lifecycle under an isolated Xvfb
and disposable user profile.

The CI job retains logs, JSON dimensions and rendered PNGs. These checks establish
native buffer allocation and interaction, not full visual/workflow parity.

## Remaining release gates

`outputs.py` uses the production shell version 7 output configuration object,
with an independent C driver and the actual Workspace client. It checks all eight
transforms, five densities, mixed scales, negative origins, primary selection,
mode changes, disabling/re-enabling, stale/invalid proposals, compositor timeout,
object destruction, shell crash, hotplug and confirmed state across shell restart.
Private fault injection simulates failure after one or two committed heads and
checks full rollback. Both Objective-C runtimes run all four run-loop modes. The
complete native runtime also keeps a GNUstep window alive and verifies its
logical size, backing density and pointer coordinates during the transactions.
Headless tests do not qualify physical modesetting or rollback failure on hardware.
The complete runtime additionally runs `DisplayModelProbe` against the real
Workspace service: public SystemKit geometry/identity, preview/confirmation,
versioned profile save/load, timeout and last-head rejection. A separate bootstrap
run has no Workspace/settings capability and reads native toolkit geometry. The
first full output-controller run caught ordinary output-removal recovery being
suppressed; the corrected path has a dedicated live-window regression check.
Profile-changing probe modes require a disposable Linux container and reject
other environments before AppKit initialization; the read-only bootstrap mode
remains available elsewhere. Failed probe runs retain their exit status and
separate stdout/stderr in `display-model-status.json`.

`shutdown.py` starts the compositor six times and requires normal exit for both
SIGTERM and SIGINT, retaining per-thread signal masks for diagnosis. It catches
font workers inheriting an unblocked signal mask when font initialization runs
before the Wayland event loop's signal setup. `build.sh` runs this check on each
runtime before the GUI integration suites.

`workspace.py --alert-probe` runs the actual DesktopKit `AlertProbe`: a loaded
default action, pointer cancellation and Return on a second alert at every
target density. The common alert initialization handles both Gorm and fallback
panels. Probe exit is followed by actual surface removal before continuing.
Every Workspace fixture seeds its private Dock so installed autolaunch entries
cannot change its initial application set; real Preferences autolaunch remains
covered by the separate authenticated-desktop fixture.

The default-X11 fixture records the actual executable and loaded backend/libraries.
It puts an ordinary client on a middle desktop, rejects removal of that occupied
desktop without changing any names/count/shortcuts, and checks the client's
published desktop. After the client exits, removal succeeds. This covers the
shared deletion preflight, zero-based indices and window-desktop notification;
failure snapshots retain root and individual window properties.

`--input-settings` also exercises shell v8 keymap/repeat/numlock validation and
normalized pointer intent in all four run-loop modes on both runtimes. A native
window receives actual layout-dependent keys and enabled/disabled repeat.
The full runtime builds Preferences and drives real Display/Screen controls,
Keep/timeout rollback, primary and enable state, last-head protection and an
arrangement drag. Module switching preserves logical panel extents. SystemKit
tests preserve X11 input defaults, reject dark profiles and restore partial
hardware profiles. Workspace startup restores saved settings once; replacement
shells retain live changes. The independent activation client checks input
provenance and token reuse; the real Recycler panel reactivates after scaling
and negative-origin layout changes.

Shell v10 tests desktop count/assignment, sticky visibility, hidden-window hit
testing and focus, retained minimization, activation onto another desktop, count
reduction and state across shell replacement. A real native window changes
density while its desktop is inactive, then returns with the expected backing
size. C and both Objective-C clients exercise default Control shortcuts;
Command+Tab/reverse and the absence of a prototype Alt+Escape exit are checked.
The actual Workspace imports desktop names separately from X11 and keeps its
Dock/Recycler visible while documents change desktops.
The real Preferences menu follows application activation while its document
remains available. Native application hide and Workspace Hide Others both
restore through actual Dock double-clicks without launching a replacement
process. Foreign group unhide restores all windows while retaining an
independently minimized member. Keyboard leave/enter within one connection
coalesces before AppKit deactivation, including modal and tracking run loops.

| Plan phase | Verified on the available target | Remaining qualification |
| --- | --- | --- |
| 0 | Debian 13 / wlroots 0.18.2 pins, upstream provenance, coordinate contract and executable workflow fixtures | Physical GPU selection and controlled hardware baseline measurements |
| 1 | Nested/headless compositor, xdg lifecycle, server frames, focus/move/resize, maximize/fullscreen, work areas, per-output scales, output transactions/rollback and hotplug recovery; native Qt/GTK checks; Lima virtual-DRM modesets, rotation and rollback | Physical display modesets, hotplug and GPU/driver validation |
| 2 | Native Cairo buffers and backing APIs, bounded buffers, placement/popups/detached menus, modal focus, Terminal cell increments, keyboard repeat/remapping/compose, clipboard/primary/Services, native/GTK drag-and-drop, Fcitx5 Pinyin/Hangul and secure-input handling, original-style cursors and native Terminal/TextEdit workflows | Physical input/display testing and controlled frame timing |
| 3–4 | Native Workspace without Window Maker, shell reconnect, window levels/hide/shade/miniaturization, Dock/IconYard/desktops and real file operations; Display/Screen transaction controls and timeout rollback; native bundled applications, printing/readback, original-referenced artwork and keyboard accessibility | Physical gamma, input devices and mixed-monitor interaction |
| 5–6 | Native-only session/backend packages, private bus and user-service environment, real systemd/greetd/PAM login/logout and hooks, lock/power software checks, portals/PipeWire capture, cold build/offline rebuild, clean installation/live upgrade/removal, independent package audit and repeated ARM headless CPU/memory/latency comparisons | Supported physical suspend/resume, VT/GPU validation, physical frame timing and hardware performance thresholds, artwork redistribution permission and release/default promotion |

The native105/native106 product cohort passes cold build, offline replay and an
independently audited uninterrupted installation/live-upgrade/removal lifecycle:
six packages, 170 ARM64 ELFs and 510 successful result reports. The existing Lima
guest runs native106 and passes the installed system-login/logout cycle. Earlier
native100 component evidence covers thirty real-server device-volume/mute actions
and thirty per-application playback/recording volume/mute actions at five densities.
The headless performance comparison covers three repetitions per Wayland package
version and two observer-off controls, with 120 phases and 38,400 offered inputs.
It records scheduling jitter, rendered-state coverage and shared-buffer release;
synthetic output feedback does not establish physical 60Hz smoothness or latency.
See [the verified status](../../docs/Wayland-Implementation-Status.md)
for evidence hashes, scope and remaining gates. Short virtual-machine samples
do not establish hardware performance. Existing keyboard accessibility is in
scope; screen-reader support is excluded at the user's request.

Client-owned placement uses the narrow application extension; ordinary xdg-shell
does not provide global AppKit positioning. Server frames retain AppKit layout
and full Cairo backing. The compositor does not advertise layer-shell; owned
NEXTSPACE shell roles provide its desktop/Dock contract.

`foreign_compositor.py` additionally checks ordinary native GNUstep rendering
under Debian 13's Weston 14.0.2, with neither NEXTSPACE extension nor
xdg-decoration. The 100%/200% cases preserve an 801×601 logical frame and verify
native buffer dimensions, backing conversions, readback and submitted pattern
pixels. Input workflows and fractional densities are not qualified by this
independent-compositor check. See the [backend contract](../../Libraries/gnustep/back/Source/wayland/README.md#other-wayland-compositors)
for the explicit behavior limits outside the NEXTSPACE desktop. On a prepared
Linux system with `weston` and `wayland-utils` installed, run:

```sh
python3 Tests/Wayland/foreign_compositor.py --probe /path/to/WaylandProbe \
  --artifacts /tmp/nextspace-weston-results
```

The native build runner also runs this check and retains its captures, globals
and loaded-library hashes under `results/foreign-compositor`. The ARM64 CI image
pins Weston 14.0.2-1 and wayland-utils 1.2.0-2 as test dependencies.

`compositor_profile.py` is an optional Linux developer tool for an existing
NEXTSPACE compositor. With `linux-perf` installed, run it as root with the actual
compositor PID, a fresh artifact directory and a duration of at most 60 seconds.
It records CPU stacks and scheduler/read events in a private trace instance,
then removes that instance. The retained output includes raw samples, resolved
stacks, buffer-loss counters and descriptor targets. Profiling adds overhead;
these diagnostics do not independently qualify input performance.
Its two-second headless CLI check passes on the ARM Lima guest. The separate
burst diagnostic preserves its reproduced negative result in the verified status.
The [kernel tracing reference](https://docs.kernel.org/trace/ftrace.html) describes
the recorded events and per-instance buffer counters.

Optional Lima dev/test launchers live in `Tests/Lima/`; they are separate from the Linux desktop packages. Local compact evidence
capsules are organized under `.build/evidence/`; older development trees are
preserved as verified archives under `.build/history/`, with receipts, per-path
manifests and restoration instructions. Working VMs, current ARM diagnostics and
the current/comparison package cohorts remain available for continued refinement.

The earlier `packages.sh` fixture qualified the isolated compositor/supervisor
component and included an X11 reference before the Wayland-only scope change.
Those compatibility results are historical. Use `desktop-packages.sh` for the
complete native desktop lifecycle. Package fixtures require a fresh disposable
root container with explicit `NEXTSPACE_PACKAGE_TEST_DISPOSABLE=1`; see
[`Packaging/Debian`](../../Packaging/Debian/README.md).

`desktop-packages.sh` adds full desktop qualification in separate cold-build,
offline-replay and clean Debian consumer containers. It reuses the production
source recipe and existing native application, Workspace and Login fixtures.
`desktop-probes.sh` builds clients against the installed toolkit. The lifecycle
runner checks exact package payloads, preserved shared configuration, a live
native toolkit/compositor upgrade and package removal. It requires a clean
consumer with neither Xorg nor Xwayland installed.

The current lifecycle also runs the flat/nested portrait, crop and landscape
printing matrix in both view orientations, plus real TextEdit continuous/paged
printing after installation and upgrade. The consumer installs Ghostscript and
Poppler for independent output inspection. Current product inputs are qualified;
the five validation-helper changes are separately hashed and checked against
their executed phase source maps.

The native7/native8 cold build, offline replay and clean install/live-upgrade/removal pass. A host audit
verifies all six packages, 3,822 identical source inputs, 156 private ELFs,
126 external library paths and 93 frozen validation sources. The first
consumer's host-filesystem socket failure is retained; the fixture relay now
places its private control socket in `XDG_RUNTIME_DIR`.
Fractional Terminal frame repaint differences are recorded
separately from its exact retained-text comparisons.

The test image pins its base digest, wlroots release and protocol XML. The full
installed package set is recorded, including GNUstep base and GTK/Qt; remaining
APT packages are resolved from Debian repositories rather than an immutable
snapshot. This is a repeatable source runner, not a bit-for-bit image claim.

`text_input.py` uses independent client and input-method modes of the registry
probe. It checks capability isolation (including a guessed global), late method
startup, stale transactions, focus changes, UTF-8 preedit/deletion, raw-key
forwarding without a loop, candidate bounds and method replacement. Native
field editors, including secure fields, run at five densities in all four run-loop
modes on both runtimes. The native-stack runner additionally checks Terminal's
marked overlay and exact committed PTY bytes.

`fcitx5.py` starts a real Fcitx5 Pinyin engine with a private profile, bus and
authorized input-method connection, with `DISPLAY` unset. Twenty cases cover all
five densities, output movement and all four AppKit run-loop modes on both
runtimes. The optional `--nested` hook queues transactions during a nested
connection-reply loop. The native-stack runner also requires exact Terminal PTY
bytes, no preedit leakage and covered preedit glyphs at every density. Candidate
popups must fit their owning output. These checks are in `build.sh` and
`native-stack.sh`. The shared harness also supports `--engine hangul`, selected
text replacement and `--no-wire-trace`. Hangul checks partial syllable commits,
glyph coverage, exact Terminal bytes and two rapid words with forwarded Spaces
in each run-loop mode. Both engines run after clean package installation and
live upgrade. Candidate visual parity and broader multilingual workflows remain
open.

IME edits now share the backend's existing keyboard event queue with forwarded
keys, preserving their order through nested reply loops. The pinned wlroots
patch exposes borrowed pending edits without replacing its current state for
mismatched serials. The relay accepts delayed edits from the active activation,
rejects old focus/content-type and future serials, and retains the last accepted
preedit for caret-only acknowledgements. `text_input.py` checks these boundaries
with independent protocol clients. The previous compositor deterministically
drops the delayed-commit regression; the previous backend also misorders Hangul
under the forced nested reply. Earlier Pinyin results remain valid evidence for
those cases alone.

The custom-shortcut clean native run exposed a test setup error: Keyboard
Preferences saved its modifier changes, while the test restored only the live
compositor state. The session correctly reapplied those saved modifiers. The test
now restores the actual controls before testing desktop shortcuts, checks the
compositor's authoritative desktop and waits for Workspace's notification.
The corrected Workspace/Preferences/OpenUp workflow and default X11 lifecycle pass.

`login_auth.py` checks the production Foundation greetd transport against a
synthetic root peer. Its 16 cases cover fragmented framing, all PAM message
kinds, cancellation, input/reply validation, root-peer rejection, literal shell
arguments and the actual 30-second deadline. `login_window.py` checks production
native Login panel placement and animations at five densities, including observed
intermediate geometry and exact final frame, controls and pixels. Both run in the
standard headless build; the complete modern stack also builds the Login app and
its existing Preferences module. Those panel/transport checks alone do not
qualify native Login startup.
The panel fixture waits for the client to acknowledge output and window moves
before invoking `center`, and bounds each animation to five seconds. It keeps
continuous buffer capture enabled for exact final-pixel comparisons.
The later opt-in greeter candidate is exercised by `login_greeter.py`: actual
Gorm UI, all PAM prompt kinds at five densities, literal service errors and
responsive timeout/focus recovery. Its default root Docker runner creates a
locked disposable account, runs the UI unprivileged and removes the account.
The root peer starts after the initial panel capture, retaining its existing IPC
deadlines. Subsequent animation frames run without PNG compression; a redacted
wire trace records the post-authentication transition time.
`power.py` uses an owned fake logind bus; `PowerProbe` refuses other bus addresses.

`page_layout.py` checks the actual AppKit Page Layout panel on large and small
logical work areas, live 100–200% transitions and the sheet path. The panel keeps
its original document geometry inside a scrollable viewport when it cannot fit.
Actual pointer/wheel events reach Cancel; returning to 100% restores the original
pixels. Closing restores the content view, size and minimum-size constraints.
Both installed and upgraded packages run these checks alongside PDF/EPS export.

`session_hooks.py --disposable-container` exercises the real supervisor and
Foundation hook helper as a temporary unprivileged user. It checks literal
arguments, paths containing spaces, hook ordering, one login hook across shell
recovery, compositor failure, failed hooks, cancellation of an unresponsive
hook, empty/invalid profiles, user identity and complete child reaping. The
native display remains available through normal logout hooks. Both installed
and upgraded packages run these checks in `desktop_lifecycle.py`.

`system_greetd.py` tests the installed systemd service, ordinary user PAM login,
stock Preferences/TimeMon startup, cancelled logout and confirmed logout to a
fresh rendered greeter. Run it as root only in an idle disposable systemd Linux
guest with installed native packages, Pillow, python3-evdev and sudo:

```sh
python3 Tests/Wayland/system_greetd.py --disposable-guest \
  --artifacts /var/tmp/nextspace-installed-greetd \
  --probe /path/to/WorkspaceProbe --stderr-trace /path/to/stderr-trace.so \
  --keyboard /dev/input/event1 --pointer /dev/input/event2 --vt 8
```

Add `--user-hooks` to verify that the user-owned LoginHook runs before Workspace,
LogoutHook runs after confirmation, cancellation runs no logout hook, and both
hooks retain the authenticated identity and native display. The hook script path
contains a space, and its preferences are checked unchanged.

The service must initially be disabled and inactive. The test creates temporary
accounts and a greeter-only PAM service, uses a runtime service override and
restores the service, Login preferences and original foreground VT. Passwords
stay in memory; per-client protocol diagnostics begin after authentication.
The ordinary `/etc/pam.d/greetd` is checked unchanged. `desktop-probes.sh` builds
the read-only stderr observer. This test qualifies the selected DRM/seat and
renderer; a virtual Pixman result does not qualify physical GPU hardware.

`login_pam.py` is a separate opt-in test for an owned disposable systemd Linux
guest. Run as root with `--disposable-guest`, an extracted greetd binary,
`LoginSessionProbe`, and a runtime wrapper readable by temporary users:

```sh
python3 Tests/Wayland/login_pam.py --disposable-guest \
  --greetd /path/to/extracted/greetd --probe /path/to/LoginSessionProbe \
  --wrapper /path/to/runtime.sh --artifacts /path/to/new-results
```

It creates two temporary accounts, an extra group, uniquely named PAM services
and a separate transient greetd unit. It tests real password/account rejection,
information prompts, cancellation/recovery, user identity/groups/environment,
headless logind sessions, PAM closure and greeter restart; then removes those
accounts, PAM services and its owned socket. The fixture clears greetd's seat0
and uses VT0 with VT-none startup. It does not switch the active VT or install a
display manager. The test code, binaries, wrapper and parent directories must be
readable/executable by the temporary accounts; a private developer home is not
suitable. Credentials travel over pipes and are not saved in result files.
The standalone mode does not qualify native greeter UI, console/VT, full desktop
handoff, power or lock.

Add `--native-greeter /path/to/prepared-public-candidate` to use
`login_native_pam.py` with that same PAM/account cleanup fixture. This requires
publicly readable candidate libraries, backend/theme bundles, Login and the
supervisor/role launchers. It drives the actual native UI, validates greeter
compositor/private-bus teardown before a fixture user command, and checks fresh
native greeter creation after logout. It checks every process owned by the
disposable greeter account and verifies that Login receives no unused Workspace
capability. Its private control relay is fixture code; production exposes no
such endpoint. Credentials remain in memory and raw key
events are not recorded. This initial mode passes in headless Lima at 125% using
a fixture user command; actual Workspace coverage follows below. Saved greeter
scale, physical VT/GPU and installed-session gates remain open. The first attempt
exposed a fixture error: preferences need
`GNUSTEP_SYSTEM_LIBRARY`, distinct from the shared-library directory variable.

`greeter_profile.py` drives the real supervisor and Login under a temporary
unprivileged account. Thirteen cases cover all five densities, negative output
positions, exact native buffer/pixel dimensions and panel centering, disconnected
heads, invalid/missing profiles and failed/missing/hung preparation helpers.
The helper shares Workspace's SystemKit transaction provider and leaves Login
without a shell descriptor. Its save mode exports XML for profile transfer while
preserving the model's on-disk format. Two real-PAM trials additionally restore
the saved 200% greeter profile before authentication and after logout, with actual
Workspace cancellation/keyboard logout and complete owned-process cleanup.
Source, binary, loaded-library and capture archives passed host audits; the
helper/supervisor/Workspace binaries match across Docker and Lima. Installed
greeter setup, session choice and physical lifecycle remain open.

Add `--user-desktop` to launch actual Workspace through the authenticated user
launcher. The prepared candidate also needs `Workspace.app`, complete framework
bundles and `WorkspaceProbe`. Its private system-library overlay inherits the
configured installed library's images and other resources. The test checks
Workspace's own application registry through `--managed-applications`, live
125%/150% buffers, logout cancellation, visible button confirmation, owned user
process/bus teardown, PAM closure and native regreet. Native application promotion
and shutdown callback ordering are covered by the retained failing binaries and
the passing full workflow. Add `--logout-keyboard` to confirm with Return after
cancelling once; three clean real-PAM cases pass this route. A traced old-library
case also passed, so the earlier intermittent keyboard failure remains retained
without a proven cause. A modal application-state query remains unqualified. Optional
`NEXTSPACE_PAM_DEBUG_WORKSPACE=1` attaches guest GDB only to the fixture's user
Workspace process and saves a shutdown backtrace.

`tab_artwork.py` checks all fourteen top/bottom tab states against pinned original
RGB/alpha pixels. Five states retain every original pixel; the remaining bevels
have narrow color, silhouette and dark-edge displacement bounds. Shared continuous
curves render each density directly. Negative controls reject changed geometry,
highlights, shadows, borders and bitmap enlargement. Installation and upgrade
check all five TIFF representations and seventy actual named-image canvases.
`tab_views.py` also selects all three real top and bottom tabs at every scale
through pointer input, retains thirty native captures and checks normal close.
Its optional `--usage-observer` verifies that all fourteen resources draw at all
five densities without undersampling candidates.

`buffer_stress.py` measures 150 actual resize/scale/move frames across two window
sizes and all five densities. It reuses the native integration pixel checker
for submitted vectors, bitmap-density selection and cropped opacity, and waits
for complete content after asynchronous AppKit repaints. Five batches warm the
caches; subsequent samples bound file descriptors, shared-buffer mappings/bytes
and RSS. Normal window close must release every client shared mapping in the
compositor. It selects the main window explicitly, preserving the application
icon as part of the ordinary workload. Installation and upgrade run this check.
Its software-rendered timings are diagnostics; physical GPU performance remains
a separate gate. A single stalled pasteboard readiness query is reaped and
retried within the existing readiness budget.

`page_orientation.py` checks both original page silhouettes and shadow alpha,
exact square frames, the photo/header palette, and each text column's ink density
and contrast. Twenty negative controls reject changed geometry, missing parts,
flat print, unrelated photography and bitmap enlargement. Five submitted TIFF
representations and ten actual named-image canvases are included in the package
lifecycle. The original microscopic wording is not claimed to be recovered.

`stepper_artwork.py` compares all four original stepper states pixel-for-pixel,
including transparent padding, bevels, face colors and arrows. Thirty-two
negative controls reject altered geometry and enlargement. A shared vector
master renders five submitted representations, checked in twenty native canvases.
`ArtworkProbe -ArtworkSteppers YES` creates a real NSStepper. `stepper_views.py`
checks ten pointer-driven increments/decrements and fifteen normal/held captures
at all five densities. It waits for the actual gray/white face pixels, and its
optional image observer checks all four states without undersampling candidates.
Installation and upgrade run both the fidelity and real-widget checks.

`ruler_artwork.py` checks every original RGB/alpha pixel in the four 8×8 tab
markers, including the decimal marker's original contrast gradient. Thirty-three
negative controls protect the strokes, feet, padding, colors and source geometry.
Its enlargement check includes fractional scales: integer-aligned straight
strokes correctly match nearest enlargement at integer densities, so integer
captures alone cannot distinguish these sources. Twenty native named-image
canvases verify the five submitted representations.

`textedit_panels.py` opens TextEdit's actual font panel, closes it normally, and
sets four tab styles in a disposable rich-text document through the existing
application connection. The helper reads back the four actual NSRulerMarker
objects, types, images and locations. Ten native captures cover both views at all
five scales. The optional observer verifies all four markers at every density,
with no resolution candidates in the exercised panels. The disk document remains
unchanged. Installation and upgrade run this check.


`pattern_fill.py` verifies actual submitted pixels for bitmap/vector pattern
colors and physical density, including unsaturated unassociated alpha. Its nine
transform profiles compare patterns with ordinary tiled image references at known
colors. All five densities must preserve phase changes, saved state, scale,
rotation, reflection, even-odd holes and empty clips. It also checks ordinary
image rendering through the same complex clips and normal window close. The
complete desktop lifecycle runs it after installation and upgrade.


`progress_artwork.py` checks every original RGB/alpha pixel in the six stripe
frames, continuous fractional diagonal geometry and thirty-six source mutations.
`ArtworkProbe -ArtworkProgress YES` uses a real NSProgressIndicator and an ordinary
Next Frame button calling its public animate action. `progress_views.py` requires
all six frames at every density, known submitted pixels for the requested phase,
three distinct repeated original phases and normal close. An early draw event is
insufficient: the checker waits for the correct completed image and retains a
pending stale capture. Optional ImageUsageTrace also records representation
selection inside pattern-color setting; its recursion guard prevents image-size
queries from re-entering the observer. It remains test-only. The complete desktop
lifecycle checks the real widget and named-image canvases after install/upgrade.


`ArtworkProbe -ArtworkProgress YES -ArtworkSpinner YES` selects the real spinning
style through the same progress fixture. `progress_views.py --spinner` checks all
eight frames at every scale against certain pixels in the pinned RGB originals,
including their baseline native flipped orientation. It requires eight distinct
frames, sufficient observed image resolution and normal close. `spinner_artwork.py`
protects four exact cardinal designs and the measured diagonal contours, opaque
coverage, centroid and unchanged interior colors; it explicitly bounds the old
one-pixel diagonal raster fringes. Fifty-six source mutations must fail. The
complete lifecycle runs both progress styles and all spinner image canvases after
installation and upgrade.

`checkmark_artwork.py` protects every original Workspace Dock CheckMark pixel,
shared beveled geometry and eight negative controls. `WorkspaceProbe
--dock-checkmark` reads the actual autostart cell, and `workspace_checkmark.py`
captures it at all five scales during the full Workspace profile. Installation
and upgrade also run source fidelity and direct-file image canvases. Direct
canvas drawing preserves fractional clipping; its expected pixels do not use
NSImageCell's backing-pixel alignment.

Page Layout captures correlate explicit metadata requests with a synchronous
panel display/flush and confirmed client focus. The document selector excludes
the identically titled app icon. Restoration still compares the entire panel
with the original one-channel-unit tolerance, including its keyboard-focus ring.

`permission_fidelity.py` checks Workspace's three permission indicators against
pinned native RGB originals, including all RGBA pixels, logical dimensions,
submitted TIFF representations and 21 rejected mutations. Its check mark shares
the existing beveled-check master. The original TIFFs contain packed RGB data;
the references use the AppKit-selected representation.

`folder_artwork.py` also runs `permissions_artwork.py` in the actual UNIX
Permissions Inspector. Two owned files with modes 0644 and 0600 exercise allowed,
denied and mixed indicators at all five scales. Forty-five symbol/halo comparisons
and ten pointer actions verify drawing and reversible cell changes while the
files retain their modes. The Inspector closes before the existing selection and
document checks continue. `WorkspaceProbe --workspace-permissions <fixture> init`
selects the two fixture files and opens the Inspector; `state` reads its current
mode, mixed mask, geometry and image metadata. This query requires a test session.

`embedded_button_artwork.py` checks the live File Attributes Compute Size and
Finder Find/Stop controls at all five densities. It compares twenty native
canvases and performs twenty pointer actions against owned fixtures, including
an exact Sizer result, a bounded filename search and queued cancellation.
`embedded_button_fidelity.py` pins original TIFF/PNG references, exact Stop RGBA,
Find glass and handle materials, and Compute's disabled opacity. The shared
NeXTSpirit renderer composes the fitted folder, vector ruler, clipping and opacity
without changing the previous artist frames. Running-worker cancellation remains
outside this test's coverage.

`pasteboard.py` also sends SIGTERM while `defaults-lock-delay.c` holds a private
defaults lock. The native server must exit successfully and release it. Both the
standalone build and installed/upgraded package lifecycles compile and run this
regression; it needs no display or compositor. The delay library is a test
fixture and is not part of the installed runtime.

Its standalone storage checks use `PasteboardProbe --clear-race` to insert a real
competing writer between declaration and reset. Stale data must stay rejected,
the newer writer must survive, and a fresh reset must succeed. `--clear` reports
EX_TEMPFAIL (75) only when ownership changes; application copy fixtures retry
that case with bounded polling and fail other errors immediately.

`file_operation_conflicts.py` checks Copy, Link and Move with Stop, controller
disconnect, Skip All and Overwrite All against owned existing files. It verifies
bytes and file identity, observes the conflict prompt and requires the worker to
exit. The installed and upgraded lifecycle runs it with the owned system bus.

`operation_artwork.py`, called by `folder_artwork.py`, loads eight operation
resources at five densities. It checks actual Copy, Move and Link conflict rows
and fifteen real Stop clicks that preserve both files and reap the workers.
Fifteen additional Mounter rows exercise Mount, Unmount and Eject notification
consumers without requesting kernel device operations. All thirty native regions
must match the vector references. `operation_fidelity.py` verifies five exact
original RGBA designs, the ruler's marks and material, the disc's measured shape
and optical materials, and the byte-identical Duplicate alias; it rejects
47 source mutations.

`preference_artwork.py` checks five active resize arrows in Browser, Icon View
and Shelf preferences. It verifies both original RGBA designs, rejects ten source
mutations, checks all resource representations and compares 25 native image
regions. Twenty-five actual pointer drags followed by Revert must restore the
original geometry. The two arrow files in File Copy's Gorm directory are unused
by its loaded panel and are excluded. Image comparison clears every opaque
image-view pixel before reconstruction; neighboring controls only supply the
backdrop outside the qualified image view.

Directory states reuse one native drag fixture for home, root and neighborhood
icons. The users-directory role points to an owned temporary directory in the
private GNUstep configuration. All three roles exercise closed, actual hover and
restored images at 100%, 125%, 150%, 175% and 200%: 45 native comparisons and
15 cancelled file drags. Original artwork guards cover lighting, smoke, ray
geometry and unchanged reflections. The preference suite also checks the two
48-point GNUstep example images, bringing its native comparison count to 35;
its 25 real resize/Revert pairs remain required. These tests do not qualify a
physical GPU or supported suspend cycle.

`preferences_artwork.py` includes the Login module discovered inside Login.app,
so the application matrix suite checks eleven modules and 55 native canvases.
Every module must be mapped from its installed bundle. The test waits for the
requested icon to paint after scrolling and stabilizes only floating-point noise
at integral pixel boundaries. `login_preferences_fidelity.py` checks the pinned
original fields and white bevels exactly, bounds glass/panel material and
silhouette differences, requires unchanged shared monitor housing, and rejects
ten source mutations and bitmap enlargements.

The file-panel artwork test uses the actual Review Open and Save dialogs, with
read-only image-draw metadata from the validation observer. It waits for all
three controls to paint, compares thirty native canvases at the five densities,
and cancels all ten dialogs while preserving the owned document. The original
Home footprint, floppy alpha, maroon arrow and materials have separate source
checks. The observer does not export images while a view is drawing.

The inline Help test uses GSHelpLinkAttachment in a real NSTextView and verifies
five native canvases, representation selection and unchanged link target/marker.
Its visible original RGBA is exact; thirteen source mutations are rejected.
Importer checks support the 1536-pixel neighborhood assembly while retaining the
1024-pixel source-house requirement and all four source-protection controls.

`track_pattern.py` exercises real sliders and scrollers plus their shared track
material at all five densities and on returning to 100%. It compares six fresh
native captures with independent vector geometry and the pinned original crop.
The theme keeps a logical 12-point tile in an NSCustomImageRep, drawing the
original one-point gray checker at the current backing density.

`RunLoopTimerProbe --bounded` registers and cancels 10,000 timers across four
modes while only two modes are polled. At most two timer objects may remain;
a valid future timer must survive, duplicate registration must fire once, and
final cleanup must release every timer. Both installed and upgraded toolkit
checks run it. The Base patch prunes invalid timers during its existing duplicate
scan, preventing retention and increasingly slow scans in inactive modes.
The real Display and Screen preference tests also exercise automatic timeout
reverts. Countdown alerts own their timer across modal-loop teardown; invalidated
timers must not depend on an inactive mode to keep an unretained pointer alive.

Review workflow tests distinguish documents by full represented filename and
wait for the opened document's native focus event after a modal reply. Timed-out
requests retain process diagnostics before termination. Integration cleanup
records shutdown failures, reaps owned processes and preserves the original
test exception; a shutdown failure still fails an otherwise successful run.
