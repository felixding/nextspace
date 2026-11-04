# Large icon sources

The user selected NeXTSpirit as the first source for large icons on 2026-11-01.
Use a suitable existing high-resolution icon before constructing missing artwork.
Keep the existing logical sizes, layouts and native density behavior.

NeXTSpirit is by Gaël Elegoët (galgot). The original [first set](http://galgot.free.fr/wordpress/?p=1380)
and [second set](http://galgot.free.fr/wordpress/?p=1410) provide Retina disk images.
The [artist's announcement](https://blenderartists.org/t/nextspirit-osx-icons/614511)
and [NEXTSPACE discussion](https://github.com/trunkmaster/nextspace/discussions/385)
provide additional provenance. The downloaded packs contain 48 icons with genuine
1024×1024 representations. Their exact source and archive hashes are pinned in
[NextSpirit.json](../Applications/Artwork/NextSpirit.json).

Both readmes say, “For non-commercial and only personal use of course.” They also
require redistribution to retain the complete set and readme. The later
NEXTSPACE discussion offers artwork for this project, but the scope of permission
for the high-resolution packs is not established. Current NeXTSpirit builds are
local personal-use builds; unrestricted redistribution is not qualified.
Keep the complete original disk images and both readmes with the source cache.

| Existing role | NeXTSpirit source | Current verification |
| --- | --- | --- |
| Closed folder | Set1 `Folder-Original.icns` | All five densities in real Workspace views |
| Unavailable folder | Same master with the existing unavailable tint | All five densities in real Workspace views |
| Open folder | Set1 `Folder-Original-Open.icns` | Native drag entry, exit, cancellation and completed copy drops at all five densities |
| Preferences static Info-panel logo | Set1 `Preferences.icns` | All five densities in the real Info panel; live desktop clock preserved |
| Terminal application and Info-panel monitor | Set1 `Term-White.icns` | Light housing matches the original; all five densities in the real Info panel |
| Home directory | Set1 `Home01.icns` | Three resource paths; actual Workspace Icon viewer at all five densities |
| Empty/full Recycler and first hover pose | Set2 `Recycler-RETINA.icns` and `Recycler-Full-RETINA.icns` | Actual 64-point Dock icon and item-count badge at all five densities; the matching first pose reuses the fitted empty master |
| Generic application monitor | Set1 `DefaultApp.icns` | Two resource paths; `.app`, `.debug` and `.profile` wrappers in the actual Icon viewer at all five densities |
| Unknown-application question mark | Original SVG screen on Set1 `DefaultApp.icns` housing | Three invalid application-file types in the actual Icon viewer at all five densities |
| UNIX tool monitor | Original SVG screen on the same housing | Actual executable-file icon at all five densities |
| Generic mounted filesystem disc | Set1 `Disk04.icns` | Five actual mount-icon comparisons in Workspace at all target densities |
| Compact-disc volume | Set1 `Disk04-CDROM.icns` | Both resource paths select all five densities; five actual Icon-view comparisons use a custom-folder fixture |
| Processes panel skull and crossbones | Set1 `Kill-App.icns` | Original live 48×48 canvas and occupied bounds; five actual button-image comparisons at 100–200% |
| File Attributes Compute Size | Set1 `Folder-Original.icns` with original vector ruler | Enabled/disabled native buttons at all five densities; real Sizer results and original disabled opacity |
| Specialized folders and other large icons | Both sets contain candidates | Further mapping and native checks pending |

The shared importer verifies every icon and both readmes, selects the actual
1024px representation and downsamples directly for each backing density. It
rejects enlargement and modified or incomplete sets. It preserves the source
pixels; no recoloring is applied except the existing unavailable-folder tint.
The current import check covers 140 master-derived frames and four negative controls.
The closed/open/unavailable preview passes 90 host/Linux representation
comparisons and 30 exact native Workspace image comparisons across 100–200%.
Five real Wayland file drags cancel cleanly and restore the closed image; five
completed drops copy a Unicode-named file with identical bytes and retain the
source. The drag image also adopts each destination density. The original SVG
fallback retains ten exact native comparisons after the test-runner changes.

The Terminal and Preferences preview covers three resource paths and fifteen
identical host/Linux representation frames. Ten real Info-panel comparisons
differ by at most one color level. Preferences retains its live 64-point clock
at every density. Terminal's static capture delays its two animation timers in
the test only. That static-logo cohort leaves the scrolling strips unchanged;
the later reconstruction below covers them.
Both application executables and 223 unrelated bundle files remain unchanged.
The shared resource writer also preserves all 85 folder frames and four aliases.

Home resolves through DesktopKit's `NXHomeDirectory`, so the preview covers that
consumer as well as its Workspace and theme copies. Home and Recycler pass
twenty actual image comparisons and twenty-five resource selections at all five
densities. Recycler stays anchored to Workspace's primary display; that display
is scaled while the other display retains a different density. Its empty, full
and restored states retain the existing badge behavior. All four original
Recycler drag-animation frames are unchanged and still need high-resolution
replacements.

The latest cohort also passes thirty real folder drag comparisons and ten
Terminal/Preferences comparisons. The independent host audit verifies all sixty
captures, 115 identical host/Linux Workspace resource frames, 288 source
snapshots and 1,978 unchanged bundle files. NXTIcon's legacy composition clips
against both the backing-aligned destination and the fractional image rectangle;
the reference preserves that existing clipping at fractional scales.

The generic-application cohort adds fifteen exact comparisons. All three
application-wrapper types resolve the DesktopKit `NXApplication` fallback and
keep their 48-point size. The Workspace copy is also generated and decoded at
all five densities. The green-question-mark variant is a separate original
design; both its DesktopKit and theme resources remain byte-identical. The
cohort's independent host audit covers seventy-five native comparisons, 125
host/Linux Workspace frames, all 56 preceding master frames, 290 source
snapshots and 1,981 unchanged bundle files. These remain personal previews using
retained native runtime binaries.

The missing question-mark and UNIX variants now use shared, genuine SVG screen
geometry in `MonitorScreens.svg`. The question's hook, stem, glowing dot and
purple checker retain their original weights, positions and colors. UNIX keeps
all four letter shapes, its title strip, window frame and five Dock marks. Its
brighter paper uses the original variant's palette. The two scenes reuse the
author's full-resolution housing; fourteen frame checks confirm that every pixel
outside the screen layer is unchanged. Each overlay renders directly at its
target density.

Source CI compares both scenes with the native-reader originals and rejects
sixteen changed-design controls, including missing details, shifts, bitmap
enlargement and a flat background. Five consumer paths preserve identical screen
RGB designs in the originals; their legacy alpha encodings differ. Twenty new
native comparisons are exact, covering three invalid application-file types and
a real ELF executable. Final review corrected the UNIX X's cap height. Source
checks now protect ink overlap as well as weight and position, including a
mirrored-N control. The latest host audit verifies all ninety-five native
comparisons, 150 host/Linux Workspace frames, 299 source snapshots and 1,980
unchanged bundle files. Deposit artwork, animation frames and other missing
designs remain open. This is still a personal preview using retained binaries;
the full current-source package and release gates remain unfinished.

Neither NeXTSpirit set has the original root computer's front-drive chassis.
`Root.svg` therefore reconstructs that design as paths and continuous gradients,
preserving its purple glass, white bevels, shaded stand, drive slots and green
indicators. DesktopKit's `NXRoot.tiff` and the theme's `common_Root_PC.tiff` have
identical native-reader originals and share this master. Both retain 48-point
logical dimensions and five directly rendered backing representations.

Eight negative controls reject changed details, translation, mirroring,
desaturation and bitmap enlargement. The real Workspace root-path icon passes
five exact native image comparisons. Thirty folder drag/copy regression captures
are also exact. The independent host audit verifies 100 representation frames,
305 source snapshots, 405 mapped/linked runtime paths and nine executable
identities. Only the two root resources change; 1,981 bundle files and literal
aliases are preserved. This private asset trial does not qualify a full current-source
build or package lifecycle.

Terminal's `MACH` and `OUT` scrolling strips have no matching NeXTSpirit asset.
They now use shared SVG glyph geometry in `Applications/Terminal/Artwork.svg`,
retaining the original colors, five rows, seven-point period and logical strip
sizes. The shared image writer updates both ordinary resources and their Gorm
copies. Forty-five original-reference glyph checks and twelve negative controls
protect the designs; seven native-reader cases verify the original encodings.

The private native trial checks eight scrolling/reset positions in both the real
Info panel and an active miniwindow at all five densities. Its timers are paused
and positions pinned for capture. The independent host audit verifies all eighty
frames and twenty host/Linux resource frames. Fifty-two of 133,088 compared pixels
differ by two color levels; the remaining pixels differ by at most one. Both the
bitmap's source bounds and the cropped destination are included in the reference.
Five earlier root captures remain exact with the shared reference helper, and
fourteen existing Preferences resources remain byte-identical with the shared
writer. Only four Terminal resources change; its executable and sixty-nine other
bundle files remain unchanged. Recycler animation artwork remains unfinished.

Recycler's imported empty/full designs now fit the original occupied rectangle,
`(7,9)–(56,58)`, inside the unchanged 64-point canvas. The earlier import filled
more of that canvas and caused a size jump on entering the original animation.
The importer removes transparent margins, pads the untouched artist pixels around
the original center, then downsamples once per requested density. Source aspect
ratio is preserved; resampling lobes stay within the original occupied rectangle.
Nine negative controls protect layout, including off-center padding. Ten frame
checks verify original bounds and untouched source pixels. The other sixty-three
master-derived frames remain unchanged.

The private native trial passes 100 exact HiDPI image comparisons and twenty
exact comparisons of the retained low-resolution animation poses. Five real move
drags cycle through all four poses, cancel cleanly and restore the fitted icon;
their source file remains unchanged. The full/empty/count-badge states also pass
at all five scales. Only the two static Recycler resources change, preserving
1,981 other bundle files and all literal symlink targets. At that checkpoint,
all four animation resources remained low resolution.

The matching first hover pose now reuses the same fitted NeXTSpirit master and
resource writer as the empty state. Its TIFF representations are byte-identical
to the static icon. The other three animated designs have no match in the cached
complete sets. They now use curved SVG ribbons with the original footprints,
green palette and fold shading in `Applications/Workspace/Artwork.svg`.
Heavy-outline and noise experiments remain unused. The selected source keeps
thin outer rims and paints soft fold shadows inside the ribbon material,
rendering directly at each target density. Nine original ribbon silhouettes,
eighteen light/shadow zones and twenty-seven negative controls protect the
reconstruction.

The complete private animation passes twenty actual frame comparisons across
100–200%. Five real move drags visit every pose, cancel cleanly and restore the
fitted static icon. The source file remains unchanged. Fifteen direct SVG
representations and thirty retained NeXTSpirit resource frames are identical
between host and Linux. Only the three constructed resource paths change;
1,980 other bundle files and every literal symlink target are preserved.
The first frame still uses the existing NeXTSpirit source. Full current-source
package, redistribution, session, hardware and release qualification remain open.

The original-style SVG folder master remains available as independently
qualified construction work. Its private native trial also passes all ten
comparisons. Neither trial establishes full current-source package or release
qualification. The deposit state and additional large icon mappings remain unfinished.

Terminal's `DEVELOPED WITH GNUSTEP` credit has no NeXTSpirit counterpart. The
128×10-point footer now uses shared handwritten SVG glyph outlines, preserving
the original thin angular caption, heavier curved name, spacing, gray field and
white emboss. No font file or enlarged raster is embedded. Twenty glyph checks
and eleven negative controls protect the original design. Both original TIFFs
remain unchanged; generated ordinary/Gorm copies have five representations.

The live Info panel previously retained Gorm's embedded 1× bitmap. It now loads
the installed Gorm resource on opening and preserves the archived layout. Five
native footer captures match exactly across 100–200%; the independent audit
also verifies eighty scrolling frames, 120 Workspace comparisons, thirty
host/Linux resource frames and unchanged existing strips. Only the rebuilt
Terminal executable and its installed Gorm credit change. This component trial
uses the retained native runtime and does not qualify a full package lifecycle
or release.

Neither NeXTSpirit set contains TextEdit's original paper-and-pencil design.
`Applications/TextEdit/Artwork.svg` now reconstructs its frame, translucent
shadows, warm pencil coating, tapered wood facets, graphite point and sixteen
paragraph rows. Shared miniature letter contours preserve the original word
footprints; their wording is illustrative because the low-resolution original
does not establish the literal text. Fourteen changed-design controls, including
component enlargement, protect genuine geometric detail.

Five native NXTIcon comparisons across 100–200% differ by at most one color
level; all five host/Linux resource frames match. Independent evidence
`textedit-edit-v1-evidence.tar.gz` preserves 334 source inputs, 269 runtime paths
and three executable identities, with no new runtime blob. Only `Edit.tiff`
changes; the executable and 27 other bundle files remain unchanged. TextEdit's
actual Info panel, title banner, document icons and a new complete package
lifecycle remain unqualified.

TextEdit's 232×56-point title now uses seven shared Bézier glyph outlines from
[TeX Gyre Termes](https://ctan.org/pkg/tex-gyre-termes), with spacing, vertical
proportions, dot position, dark extrusion and soft gray shadow fitted to the
original title. The unmodified source font, original readme, manifest, GUST Font
License and LPPL 1.3c are retained under `Applications/Artwork/Fonts/TeXGyreTermes`.
The native build uses embedded paths and requires no installed font. Nine letter
parts, seven shadow zones and sixteen negative controls protect the design.

The independent title cohort verifies five NXTIcon comparisons, five actual
Info-panel main-icon comparisons, five actual title comparisons and ten identical
host/Linux resource frames. The archived title cell clips its oversized image;
its original layout and native backing-pixel alignment are preserved. The shared
comparison helper now models that clipping for image cells. Only `EditTitle.tiff`
changes; the executable and 27 other bundle files remain unchanged.
`textedit-title-v5-evidence.tar.gz` preserves 342 sources, 501 validation-probe
compilation inputs, 276 runtime paths and five executable identities. This is a
scoped trial on the retained installed native51 runtime, with a probe compiled
in the retained source2 SDK. Document icons, a full latest-source package
lifecycle and broader release gates remain unfinished.

TextEdit's three document icons now share the reconstructed paper frame and
miniature alphabet. They preserve 39 paragraph rows, purple type, cyan heading
glints, word footprints and nine color zones in the RTFD inset. The inset uses
continuous colored surfaces and curves; its original subject cannot be
established from the tiny source. Miniature wording remains illustrative.
Thirty negative controls protect these designs, including component enlargement.
The common frame now fixes the two near-shadow corner joins as well.

The document cohort passes twenty native icon-view comparisons, five actual
Info-panel main-icon comparisons and five title comparisons. Forty AppKit
representation selections and twenty-five host/Linux resource frames pass.
Only the three document TIFFs and corrected main-icon shadow change; the title,
executable and 24 other bundle files remain unchanged. Independent evidence
`textedit-documents-v1-evidence.tar.gz` freezes 343 source inputs, 276 runtime
paths and five executables, with no new runtime blob. These component results
do not qualify a complete latest-source package lifecycle or release.

The normal native build now selects the qualified NeXTSpirit mappings whenever
the complete sources are present in `Applications/Artwork/NeXTSpirit`. One shared
hook serves the theme, DesktopKit, Workspace, Terminal and Preferences. It runs
after constructed artwork so matching artist originals take priority. Source
archives capture all 48 original icons and both readmes; package staging retains
the complete sets and pinned manifest under `/usr/NextSpace/share/artwork/NeXTSpirit`.
These remain local personal builds under the original terms.

The installed native51 component trial passes 130 image comparisons and 195
identical host/Linux resource frames, including both application logos, live
clock geometry, folders, Home, generic applications, screen variants, Recycler
badges, four animation poses and the constructed root computer. Five cancelled
folder drags, five completed copy drops and five cancelled Recycler move drags
pass. Only 34 TIFF paths change; 2,170 other bundle files, literal links and
application/framework binaries remain unchanged. The independent evidence is
`nextspirit-native-hook-v1-evidence.tar.gz`. A complete latest-source package
lifecycle and unrestricted release permission remain open.

Review's seven document icons now have reconstructed paper geometry, a smooth
purple gradient, compatible serif outlines and the original torn-paper design.
Neither NeXTSpirit set contains these document designs. The five labels use
TeX Gyre Termes Regular contours; the original font file was not recovered.
Seventeen character placements, 42 gradient zones and 77 negative controls
protect proportions, weight, transparency, palette and genuine high-resolution
geometry. The twelve untouched Review originals have pinned native-reader
fixtures, including the still-unqualified application icon and page controls.

`review-documents-v1-evidence.tar.gz` independently verifies 35 native Wayland
icon-view comparisons, 70 AppKit representation selections and 35 identical
host/Linux resource frames. Only seven document TIFFs change; the executable,
application icon, page controls, literal links and eighteen other bundle files
are preserved. This is a component qualification on the installed native51
runtime, not a complete latest-source build or package lifecycle.

Review's four page controls now also have qualified vector geometry. A shared
chamfered outline and two triangular faces reproduce every visible original
base-size pixel exactly, including the gray edge and opaque highlighted state.
Forty negative controls reject changed designs and enlarged components.
`review-pages-v2-evidence.tar.gz` verifies twenty comparisons in Review's real
buttons and ten real pointer actions at five densities. Normal controls compare
all opaque artwork pixels; highlighted controls compare the entire image patch.
All twenty page resource frames agree between host and Linux; the thirty-five
document frames remain unchanged. Only four page TIFFs change; twenty-one other
bundle files and the application executable are preserved. The sole new runtime
blob is the validation probe, with all 501 compilation inputs retained. Review's
main application icon and the full latest-source package lifecycle remain open.


Neither inspected NeXTSpirit set has OpenUp's closed-carton or inward-arrow
paper design. The available open-carton designs change the original shape.
Two constructed designs now preserve the carton faces, flap seams, paper
shading, arrow contours, color weights and nine miniature paragraph rows.
TextEdit and OpenUp share twenty authored microtype contours in
`Applications/Artwork/Microtype.svg`; all twenty-five TextEdit resource frames
remain unchanged. The tiny document wording remains illustrative.

`openup-icons-partial-v1-evidence.tar.gz` verifies ten native icon-view
comparisons, ten identical host/Linux resource frames, 33 negative controls
and eleven native-reader originals. Only two OpenUp TIFFs change; fifteen other
bundle files, literal links, the executable and original narrow logo remain
unchanged. This is explicitly partial: the actual Info-panel gate fails because
the original logo has one representation. No comparison or requirement was
weakened, and the full Info panel remains unqualified.


OpenUp's 184×19 logo now also uses continuous vector geometry: the original
long P and L bars, three-part ampersand and seven-letter miniature caption.
The caption follows the original small-capital shapes; no source font was
recovered or substituted. Ten shape/letter parts and 36 negative controls
protect contours, weight, placement, transparency and genuine vector detail.
The L's base-size alpha geometry matches exactly.

The shared Info-panel checker now uses the actual image-cell drawing rectangle
for both TextEdit and OpenUp, including backing alignment and clipping. It also
compares OpenUp's logo pixels. Five actual OpenUp logo comparisons are exact
across 100–200%. Five main-icon views, five Info icons and fifteen TextEdit
regression comparisons pass; fifteen OpenUp and twenty-five preserved TextEdit
frames match host/Linux. Only the narrow logo TIFF changes in this cohort;
the two icon TIFFs, executable and sixteen other bundle files remain unchanged.
`openup-logo-v2-evidence.tar.gz` supersedes the earlier partial Info-panel result.
This remains installed native51 component evidence, without a full latest-source
package lifecycle or release claim.

TimeMon's pause mark has no matching design in either NeXTSpirit set. Its new
SVG preserves the original red stipple, circular ring and diagonal slash using
continuous geometry. Seven negative controls reject design changes and bitmap
enlargement. The existing custom image callback now draws the mark after the
CPU rings; pausing redraws that custom representation instead of locking a
bitmap focus. The native baseline lost the mark at all five densities.

`timemon-pause-v4-evidence.tar.gz` verifies five native pause comparisons across
100–200%, scale changes while paused and five resume cycles. The resumed rings
match the old baseline exactly. A separate real-load run verifies live updates,
a stable two-second pause and updates after resuming. Five host/Linux resource
frames and five native-reader original/alpha cases pass. Only the application
executable and root pause TIFF change; twelve other bundle files are preserved.
The evidence retains 508 application and 501 probe compilation inputs. TimeMon's
startup and Info artwork, normal user quit and broader workflow remain open.

TimeMon's transparent startup rings and colored Info diagram now also use shared
circle and axis geometry. Neither NeXTSpirit set contains these designs. The
twelve colored sectors preserve all 942 solid-color original samples; eighteen
negative controls protect the rings, axis, palette, sector geometry and genuine
high-resolution edges. The existing DesktopKit bundle-image helper replaces the
Info image embedded in Gorm. TimeMon now links the same DesktopKit/SystemKit
pair used by the other bundled applications.

`timemon-static-v4-evidence.tar.gz` verifies five native icon-view comparisons,
five real Info-panel comparisons, the actual pointer menu action and normal
keyboard quit. Twenty native resource selections and ten unique host/Linux
frames pass. Five pause frames retain identical resource bytes, and pause/resume,
live updates and scale changes while paused still pass. Three existing TIFFs and
the executable change; one root Info TIFF is added. Ten other bundle files stay
unchanged. The subsequent `timemon-controls-v1-evidence.tar.gz` changes only the
application executable to save timing-field edits through their existing
setters. All artwork comparisons pass again; fourteen other bundle files remain
unchanged. It also qualifies README scrolling, saved settings and native color
transfers across all five scales. The retained hammer image and complete
latest-source packaging remain open.

The shared color wheel now also regenerates its original procedural HSV/alpha
bitmap at the window's actual density. Its 100% native pixels remain identical.
`color-wheel-v4-evidence.tar.gz` checks every new cache pixel, native interior
colors, five display scales and return to 100%, with actual wheel and brightness
input. This preserves the original formula and logical margin.

The four Gray/RGB/CMYK/HSB diagrams now use shared rectangle geometry and
continuous gradients in `Libraries/gnustep/Artwork.svg`. Both complete NeXTSpirit
sets lack matching designs. At 100%, their alpha and geometry match the original
36×24 diagrams exactly, with at most one color-level difference. The distinct
white marker positions and eight gray swatches are preserved. Thirty-two
negative controls reject altered designs and bitmap enlargement.

`color-picker-v1-evidence.tar.gz` verifies 100 exact native button-image
comparisons and twenty real mode actions at the five target scales. Twenty
unique TIFF frames match direct host/Linux renders. The wheel and TimeMon
workflow regressions also pass. Only four resource files change; fifteen peer
picker files and all product executables remain unchanged. Original TIFFs,
native-reader references and the upstream license are retained under
`Tests/Wayland/artwork-originals/color-panel`. The magnifier, named-color diagram
and static wheel icon remain unqualified.


The shared color-panel magnifier also has no matching NeXTSpirit design. Its
32×32 original is reconstructed with a circular rim, split rounded crosshair,
transparent lens and shaded brown handle, retaining the dark band and tip.
`magnifier_fidelity.py` uses the pinned native-reader original and twelve negative
controls. Five generated frames match direct host/Linux renders.

`magnifier-v1-evidence.tar.gz` verifies five actual panel images and five exact
full cursor buffers at 100–200%, including the original hotspot and tracking
exit. Five original-resource baselines and 100 picker-image regressions also
pass. Only the magnifier TIFF changes; 180 peer files and all product binaries
are preserved. This qualifies the artwork and cursor lifecycle. Screen-color
sampling remains open: a retained real-input test confirms that the inherited
Wayland screen-reading method leaves the selected color unchanged.


The named-color and static wheel icons also have no matching NeXTSpirit design.
The named-color heading uses fitted TeX Gyre Heros regular outlines, retaining
its original layout and ink weight; the purple swatch and pseudo-text geometry
remain pixel-identical at 100%. The unmodified authoring face, upstream readme
and GFL/LPPL terms are under `Applications/Artwork/Fonts/TeXGyreHeros`. The
original font's identity remains unknown. The wheel uses shared angular geometry,
radial color gradients, shaded rim and a separate translucent center mark.

`picker-icons-v1-evidence.tar.gz` qualifies nineteen original-design negatives,
ten new TIFF frames, twenty exact actual-button comparisons and ten real mode
actions across 100–200%. All 25 preceding shared-panel frames, 100 slider-button
regressions and ten original-reader cases also pass. Only two TIFFs change;
179 peer files and all product binaries are preserved. The artwork for all seven
pinned shared-panel originals is now qualified. The functional screen-color
sampling gap remains separate and open.


Workspace's plain-disc and compact-disc designs now use the matching NeXTSpirit
masters `Disk04.icns` and `Disk04-CDROM.icns`. The normal build hook writes
`HDD.fs.tiff`, `CDROM.fs.tiff` and `CDROM.openfs.tiff` from their genuine 1024px
sources. Both original CD resources have identical artwork, so both use the same
master. Logical size stays 48×48. The highlighted generic disc, NTFS overlay,
floppy images and other unqualified designs remain separate work.

`volume-icons-v1-evidence.tar.gz` (18,402,868 bytes, SHA-256
`f43b2a968fdb347857ea9f566ab60f0a428c3a45ebc8132cb9097ee6b0bdd5a1`) retains the frozen component.
Ten actual Workspace image comparisons across 100–200% are exact on Linux and
in an independent host rerender. The generic case uses the real `/dev/shm` mount;
the compact-disc case uses the same generated bytes as a custom-folder image.
Physical optical media and the ISO-detection branch are not exercised by this
artwork fixture. All 1,767 other Workspace files, including its executable,
remain unchanged. Existing folder, application-monitor, Recycler and root-icon
checks pass too. Both complete artist sets and their terms are still verified;
this remains a personal-use component qualification, not release approval.

The accompanying native reader inventory decodes 715 distinct image groups at
1,816 installed paths, including all 228 files the earlier Pillow inventory
could not read. It records actual RGB-context density selections, with a delta
for these three new resources. Reader coverage does not prove that every file is
active or has a qualified HiDPI design; active-consumer classification remains
open. Historical help illustrations and unused resource copies stay visible in
the inventory rather than being counted as completed interface artwork.

### Processes panel and Terminal resource paths

The Processes panel now uses NeXTSpirit's `Kill-App.icns`. Its original live
button image is 48×48 with occupied bounds `(3,2)–(46,46)`; the separate TIFF is
43×44. The importer preserves the live canvas and fits the untouched 1024px
master to those bounds. The [native original reference](../Tests/Wayland/artwork-originals/workspace-processes/reference.json)
binds that observation to the original Gorm data. The controller reloads one
canonical resource after Gorm initialization so its five backing representations
reach the real button. The probe observes the cell's actual image; the public
image getter returns nil for this titled cell.

`process-artwork-v1-evidence.tar.gz` is 83,533,478 bytes, SHA-256
`26b4d56d5766fd08d5c6f4a4baef2b2545858efbd8a781e339d005e27e2dbbc5`.
Five native comparisons are exact in an independent host rerender, and the
100% drawing rectangle matches the original. The other 130 icon comparisons
and existing file-drag checks pass. The original executable still uses its
embedded 48px bitmap even with the new file present; the negative control
rejects its single representation. The Gorm layout and original embedded data
are retained. Workspace's executable and canonical `Kill.tiff` are the two
changed paths; 1,768 peer files and literal links are preserved.

The archive retains 429 validation sources, 501 probe compilation inputs,
773 Workspace compilation inputs and 2,555 frozen Workspace/framework/protocol
sources. It embeds all 296 distinct runtime blobs for 290 library paths and
seven executables. Workspace is the changed product executable. The independent
audit found unused stale entries in a copied source cache; they are preserved
separately, and the final cache matches the repository and actual compilation
snapshots. All recorded actors are reaped by controlled fixture shutdown;
Workspace returns SIGTERM, and the test does not invoke the Kill action.

The native53/native54 consumer also caught an incorrect Terminal import target.
The normal source hook now writes `Resources/Terminal.tiff` and
`English.lproj/Info.gorm/Terminal.tiff` before make. An actual GNUmake build
copies both into its application wrapper, with five master-derived frames each.
The same archive retains its 181 source inputs, hook/build logs and both payload
resources. This qualifies the resource-copy correction; a complete package
lifecycle with the later source remains open. Remaining artwork, physical
hardware/session tests and unrestricted release permission remain open too.

### Multiple-selection fan and highlight

Neither complete retained NeXTSpirit set contains the seven-card fan and hand.
`Selection.svg` reconstructs that design with continuous card edges, hand curves
and the original pastel palette. The native RGB reference retains its 48×48
canvas, occupied bounds and partial opacity. Shape overlap is 0.966975, with
the silhouette within one original pixel; eleven palette regions and seven
negative controls pass. The 66×52 selection backdrop preserves opaque gray
corners and a rounded white center. Its high-resolution edges are rendered
from geometry. The original TIFFs remain the design references.

The shared resource writer generates Workspace's `MultipleSelection.tiff` and
`hilite.tiff`, plus the theme's `common_MultipleSelection.tiff`, at five backing
densities. Actual selected path icons and the Inspector button pass ten native
comparisons over 100–200%; five complete selection backdrops also pass.
Independent host rerendering is exact for the icon and differs by at most one
color level for fractional backdrop clipping. The other 135 native image
comparisons and file-drag regressions pass. Normal stage commands and actual
GNUmake resource copying verify all three wrapper paths, using retained
Workspace objects; this is not a new cold build.

The audited `selection-artwork-v1-evidence.tar.gz` is 16,629,904 bytes, SHA-256
`2788b19f578c369b1b94315b78d722cabc65f655fba9abd91a5bc8cc37e1210b`.
It retains 438 source inputs, four literal source links and 501 diagnostic
compilation inputs. Unchanged runtime blobs depend on the retained
`process-artwork-v1-evidence.tar.gz` above. Only three resource paths change;
1,823 resource peers and product executables remain unchanged. Successful
fixture actors are reaped by controlled shutdown. The theme resource has five
verified representations; its separate theme-lookup consumer remains untested.
Current-source package lifecycle, physical hardware and full-plan gates remain
open.

### Highlighted disc and NTFS flag

The NeXTSpirit disc now also supplies `HDD.openfs.tiff` and `NTFS_HDD.fs.tiff`.
Neither inspected complete set contains the original yellow highlight or NTFS
flag, so `VolumeOverlays.svg` reconstructs those marks. The existing monitor
screen compositor now uses the general `overlay_artwork`/`overlay_symbol`
fields for both uses. All 98 earlier master-derived frames remain identical.
Fourteen additional frames preserve the untouched disc outside the marks.
The native RGB originals bind the ray layout, wavy flag outline, four panel
colors and fragmented trail. Six negative controls reject altered marks and
bitmap enlargement.

Five real mount drags exercise the production opened-directory icon and its
restoration after cancellation. The source receives cancellation and remains
unchanged. All 25 volume comparisons over 100–200% are exact in an independent
host rerender. This includes NTFS artwork displayed through a custom-folder
fixture; physical NTFS and optical media remain untested. The complete
Workspace run passes 160 image comparisons and five selected backdrops.
The normal shared hook and actual GNUmake resource copying verify both paths
using retained Workspace objects.

The audited `volume-overlays-v1-evidence.tar.gz` is 19,301,919 bytes, SHA-256
`aa8eab1d15eb3a4f448c3a0be5f20fda9330a3cdcd2992e545222cf75829d511`.
It freezes 447 validation inputs and four literal source links, reusing the
runtime and diagnostic binaries from the selection archive above. Only two
resource files change; 1,766 resource peers and all product executables remain
unchanged. Successful fixture actors are reaped by controlled shutdown. This
headless component result does not qualify a new package lifecycle, physical
hardware, remaining artwork or unrestricted redistribution.

### DOS floppy states

Neither complete inspected NeXTSpirit set has a matching floppy.
`Floppy.svg` reconstructs the original case, metal shutter, white label and DOS
lettering with shared vector geometry. The original open image also moves its
shutter four logical points left; adding only a yellow highlight would lose
that state change. Both native RGB references retain their original 48×48
canvas, occupied bounds and translucent black shadow. Shape overlap exceeds
99% for both states. Material regions and lettering preserve mean channel
colors within eight levels. Eight negative controls reject changed lettering,
metal, shutter pose, shine, shadow opacity and bitmap enlargement.

The normal Workspace stage emits `DOS_FD.fs.tiff` and `DOS_FD.openfs.tiff` with
five backing representations each. The shared volume fixture exercises both
through a custom folder's `.dir.tiff` and `.opendir.tiff`, including five actual
hover/cancel/restore cycles. Physical FAT media remains untested. All forty
volume comparisons are exact in independent host rerendering over 100–200%.
The complete Workspace regression passes 175 image comparisons and five
selection backdrops. Actual GNUmake resource copying also passes using
retained Workspace objects.

The audited `floppy-v1-evidence.tar.gz` is 21,573,891 bytes, SHA-256
`f7e47460ec02ab2c67bd1cf1d05b78046228a5578e52e896552d36934b0527df`.
It freezes 454 validation inputs and four literal source links. The 289
observed runtime library paths and seven executable identities reuse the disc
variant archive above. Both resource files change; 1,766 resource peers and
product executables remain unchanged. All 112 NeXTSpirit master-derived frames
remain identical. Successful fixture actors are reaped by controlled shutdown.
Remaining artwork, workflow, current-source package lifecycle, physical
hardware and release gates remain open.

### Generic and unreadable document sheets

Both complete retained NeXTSpirit sets were searched first. `Untitled.icns`
uses stacked letters and an envelope; `Folder-Documents-RETINA.icns` uses a
folder. Their silhouettes differ from the original question-mark sheet.
`Applications/Artwork/Documents.svg` therefore reconstructs the missing design
with shared paper, text marks and lettering geometry. It supplies Workspace's
`common_Unknown.tiff` and `badFile.tiff`, DesktopKit's `NXUnknown.tiff`, and the
theme's opaque `common_Unknown.tiff`. The source TIFFs remain unchanged.

All 1,841 pixels outside the lettering regions match the original visible
premultiplied colors, and the complete alpha planes match. The fitted TeX Gyre
Termes question hook retains 94.05% thresholded shape overlap, with ink-weight
and centroid limits; its separately drawn rounded-square period retains 100%
overlap. The original font is unknown. Twelve deliberate geometry, palette,
opacity and raster-enlargement mutations fail the fidelity check.

Actual GNUmake resource copying passes for all four paths, each containing
48/60/72/84/96-pixel representations at a constant 48-point logical size.
Workspace's unknown binary and genuinely unreadable file pass ten native
Icon-view comparisons. Public named lookups of `NXUnknown`, `common_Unknown`
and the existing `common_MultipleSelection` load the intended framework/theme
paths and pass fifteen independent native captures. The Workspace artwork suite
passes 185 image comparisons and five selection backdrops.

The independently audited `document-icons-v1-evidence.tar.gz` is 14,586,985
bytes, SHA-256
`10bf32bf44c277375a618c6ff0566f43ce30c52388343b3c657fd0895a9b7745`.
It freezes 472 validation inputs and 503 diagnostic compilation inputs, checks
205 retained PNG pairs, and independently rerenders all ten new file icons and
recomposites all fifteen named-image captures. Exactly four of 1,849 resource
paths change; product executables and literal links remain unchanged. Runtime
libraries reuse pinned component archives. This qualifies headless component
usage. The remaining plain-text, bundle, photographic and other artwork,
complete current-source package lifecycle, physical hardware and release
gates remain open.

### Plain-text document sheet

Neither complete retained NeXTSpirit set has the purple-text sheet. The existing
`Documents.svg` now reuses its paper and shadow geometry for Workspace's
`TextFile.tiff`. Continuous purple marks and their sixteen original ink colors
remain SVG paths. All 2,304 original pixels match in visible premultiplied color
and alpha at 100%; fractional-density rendering resolves their boundaries from
geometry. Both nearest-neighbor and Lanczos enlargement fail the source check.
The shared document suite now rejects eighteen deliberate fidelity mutations
and rejects embedded raster images.

The normal Workspace artwork hook and actual GNUmake resource copy produce
five 48-point representations. A readable plain-text file with an unregistered
extension exercises the actual content-type fallback in Workspace at all five
scales. The full document fixture passes fifteen native comparisons, and the
Workspace artwork regression passes 190 image comparisons and five selection
backdrops. The host independently rerenders all fifteen document cases and
checks all 195 retained image pairs.

The audited `text-file-v1-evidence.tar.gz` is 13,272,106 bytes, SHA-256
`ce3767ef34e9428e49b2da6fae884ec3492d666957f2fc25fd4c6359bbd318c0`.
It freezes 474 validation inputs and reuses all observed runtime identities
from the preceding document archive. Exactly one of 1,849 resource paths
changes. The other document resources, executables and literal links retain
their hashes. This qualifies the headless Workspace fallback; bundle,
photographic and other remaining artwork, complete current-source packaging,
physical hardware and release gates remain open.

### Bundle wrapper monitor

NeXTSpirit's `DefaultApp.icns` supplies the matching high-resolution monitor
housing. Its application windows differ from the original bundle design, so
`MonitorScreens.svg` adds the original small window using shared glass, purple
background and Dock geometry. The bundle and UNIX originals have identical
background pixels in their common exposed regions; the gradient is shared.
All 104 window pixels and all 45 Dock detail samples match the original at
100%. Twenty-six fidelity mutations are rejected. Twenty-one rendered frames
verify that all three monitor overlays preserve the housing outside the glass.

The normal NeXTSpirit hook, its actual stage functions and GNUmake resource
copy produce five resolutions for Workspace's `bundle.tiff`. The real viewer
uses it for all four configured wrapper extensions: `.bundle`, `.preferences`,
`.inspector` and `.service`. Twenty native comparisons cover these roles at
100–200%. Their fixture uses a separate folder so every icon remains fully
visible. The Workspace artwork regression passes 210 image comparisons and
five selection backdrops.

The independently audited `bundle-artwork-v1-evidence.tar.gz` is 16,318,153
bytes, SHA-256
`12f321afd9b92bd31990897975382dbbadfdf2cb5481f227c3e2ed4e3bb041db`.
It freezes 476 validation inputs, retains the used NeXTSpirit master and both
readmes, recomposites all five bundle images and rerenders all twenty native
cases. All 215 retained image pairs pass. Exactly one of 1,849 resource paths
changes; nineteen existing NeXTSpirit derivatives still match their masters.
Executables, other resource bytes and literal links remain unchanged. This is
a headless personal preview; unrestricted redistribution permission, other
artwork, full packaging/session qualification, physical hardware and release
gates remain open.

The shared `common_Root_Apple` resource is an alias of the reconstructed root
computer in `Applications/Artwork/Root.svg`: its original TIFF is byte-identical
to the original PC resource. Both installed theme aliases share the generated
five-density TIFF. The alias changes no computer geometry or style.

The selected-tab left highlight in `Libraries/gnustep/Artwork.svg` reconstructs
the original GNUstep GUI resource with two joined continuous Bézier curves.
Its native 13×17 RGB/alpha pixels match the original exactly. Native higher
representations are rendered from the curves, and both nearest-neighbor and
Lanczos enlargement fail the fidelity checker. The pinned original TIFF, native
reader PNG and LGPL text are under `Tests/Wayland/artwork-originals/tabs`.
The remaining tab and page-orientation qualification is recorded below.

The two GUI page-orientation illustrations use `Libraries/gnustep/PageOrientation.svg`.
Their original paper/shadow alpha and square paper/photo frames are preserved
exactly. The pink header, small grayscale vignette and two/three-column layouts
retain the original footprints and measured palette/ink contrast. The miniature
print is reconstructed with TeX Gyre Heros vector outlines; the low-resolution
original does not establish its exact wording. The actual source TIFFs and
native-reader PNGs are pinned under `Tests/Wayland/artwork-originals/page-orientation`.
Both complete NeXTSpirit sets and the author's references were checked before
constructing this design; no matching page-orientation master was found there.
The contour-only experiment was rejected because its high-resolution ink became
rounded blobs, despite a lower numerical pixel error.

All fourteen top and bottom tab states share `Libraries/gnustep/TabEdges.svg`.
Their original TIFFs and actual native-reader PNGs are pinned under
`Tests/Wayland/artwork-originals/tabs`. The left highlight retains every original
100% pixel, as do four additional white-highlight states. Continuous beveled
contours, neighboring highlights and gradient tails reconstruct the other designs;
independent original-reference
checks bound dark-edge displacement to a quarter logical pixel and protect
contrast, palette and construction. The bottom states retain their original
18-point height, including transparent padding and soft shadow tips. Repeated
contours and paints share vector definitions. All seventy native named-image
canvases match the installed representations; thirty real pointer selections
exercise every state at all five densities without undersampling candidates.

The four original stepper buttons use `Libraries/gnustep/StepperButtons.svg`.
One shared bevel, face and pair of continuous triangle contours supply both
orientations and highlighted states. Every original 18×13 RGB/alpha pixel matches
at 100%; higher densities rasterize the original geometry directly. The pinned
GNUstep TIFFs, native-reader PNGs and LGPL text are under
`Tests/Wayland/artwork-originals/steppers`. Thirty-two negative controls reject
altered parts and bitmap enlargement. Twenty actual named-image canvases match
the installed representations. Real NSStepper increments/decrements and held
faces pass at all five densities, with all three 100% widget captures unchanged
from the original resources. All four observed undersampling candidates are
removed. These assets follow the native71/native72 source freeze.

The four ruler markers share `Libraries/gnustep/RulerMarkers.svg`. Continuous
vertical/horizontal strokes preserve the original left, right and center forms;
a three-stop opacity gradient preserves the original decimal marker. Every 8×8
RGB/alpha pixel matches. Fractional scales render the strokes directly. Integer
scales naturally coincide with nearest enlargement for these axis-aligned forms;
that coincidence does not require changing the original straight geometry.
The pinned TIFFs, actual native-reader PNGs and LGPL text are under
`Tests/Wayland/artwork-originals/ruler-markers`.

Twenty named-image canvases match the installed representations. TextEdit's
actual font panel and four real ruler marker types pass at all five scales with
no undersampling candidates. The original 100% font content and ruler strip are
unchanged; a separate fifteen-pixel insertion-caret difference is retained and
visually identified below the ruler. Thirty-three negative controls pass.
These assets and their panel validation follow the native71/native72 freeze.


The six original indeterminate progress-bar resources now share
`Libraries/gnustep/ProgressStripes.svg`. One repeating vector gradient renders
continuous diagonal bands with the measured black/153-gray palette. The original
six states contain three phases repeated twice; all six original 24×24 RGB/alpha
images match exactly. The rejected polygon drafts each gained four edge pixels
through clipped-edge snapping. The gradient preserves the same design without
pixel cells or per-pixel corrections. Pinned TIFF/RGB references and LGPL text
are in `Tests/Wayland/artwork-originals/progress-stripes`.

Source checks reject shifted phase, reversed direction, changed gray, lost
opacity, nearest enlargement and Lanczos enlargement. Normal Linux generation,
GNUmake installation and all thirty actual named-image canvases pass. The real
NSProgressIndicator test performs thirty public button/animate actions at the
five scales. Ordinary and traced routes pass sixty captures, 16,912 known pixel
checks, sixty stale-frame negative controls and normal close. All six original
100% bar interiors remain byte-identical. Tracing covers actual pattern-color
representation selection, and all six resources have sufficient selected pixel
extent at all five densities. Spinner reconstruction remains a private prototype
and is not qualified by the stripe evidence.


The eight original progress spinner frames share `Libraries/gnustep/ProgressSpinners.svg`.
They retain the stepped black/white disk and its eight original orientations.
The four cardinal states match every original RGB/alpha pixel. The four diagonal
originals have different one-pixel raster fringes. Their reconstruction preserves
every certain interior pixel, the 802-pixel opaque coverage, full bounds and
centroid to one pixel of its 802-pixel numerator. Two silhouette pixels differ
per diagonal state within a one-pixel outline band; the associated-RGBA mean
error stays below 2.5/255. These are explicit raster-edge differences, not an
all-original-pixels-identical claim. Source checks reject fifty-six mutations,
including changed placement, ink, cut, opacity and bitmap enlargement.

Normal Linux rendering/GNUmake installation and forty actual named-image canvases
pass with zero pixel difference from the submitted master. The shared real
NSProgressIndicator fixture exercises both styles. Its original-resource run
verifies the flipped image orientation. Eighty reconstructed spinner captures
and public button/animate actions pass, with 30,530 independently replayed known
original pixel checks and eighty wrong-phase controls. All four 100% native
cardinal bodies remain byte-identical. All eight resources select sufficient
pixel extent at every scale. The same helper also passes thirty stripe captures
after the shared fixture extension. These changes follow the native73/native74
source freeze.

Workspace's Dock autostart `CheckMark` shares continuous beveled strokes in
`Applications/Artwork/CheckGlyphs.svg` with the existing checkbox. Two short
shadow ribbons retain the different original tips; each caller supplies its
original gray. The standalone reconstruction preserves every 10×10 RGB/alpha
pixel and renders genuine fractional/high-resolution strokes. Eight mutations,
five native canvases and five actual Dock cell captures pass. The 100% cell is
identical to the original, while all five scales select sufficient pixel extent.
All 165 existing theme symbol/density renders and the compositor frame header
remain unchanged. Pinned TIFF, native-reader PNG and license are under
`Tests/Wayland/artwork-originals/workspace-checkmark`. This follows native73's
source freeze.

Workspace's UNIX Permissions indicators (`PermYes`, `PermNo`, `PermNoChange`)
retain their 44×16 logical footprints and exact original RGBA pixels at 100%.
Their original AppKit-selected RGB exports are pinned under
`Tests/Wayland/artwork-originals/workspace-permissions`. The check shares
`CheckGlyphs.svg`'s checkbox geometry and original #555 shadow; the cross uses
continuous beveled diagonals and the dash retains its white/black edges.
`Applications/Workspace/Artwork.svg` routes all three generated TIFFs into the
Inspector bundle's localized resources. Twenty-one fidelity mutations and actual
native Inspector comparisons protect the shapes, palette and density selection.
The full original 100% Inspector panel is byte-identical after replacement.

Workspace's Copy and Duplicate mini icons share the continuous sheet and bevel
geometry in `Applications/Artwork/Operations.svg`. The original 16×16 RGBA
pixels, colors and overlapping-sheet shape are exact. Both generated aliases
provide five independently rendered densities; their fractional edges reject
nearest and Lanczos enlargement. Original TIFF, native-reader PNG and license
are pinned under `Tests/Wayland/artwork-originals/workspace-operations`.

The same master now includes Link, Move, Delete, permission, ruler and disc
miniatures. The first four also match original RGBA exactly. Their arrows,
bevels, bones and permission marks use continuous vector planes. The ruler
preserves every tick and its original footprint, replacing orange pixel dither
with continuous wood material. The plain disc preserves its original optical
palette, hub and rim using continuous circular geometry; its bounded shape and
material comparison does not claim exact original RGBA. NeXTSpirit's CD-ROM and
CD-player candidates contain foreground lettering or music notes absent from
this miniature. Thirty actual Processes-row canvases match the new resources,
including Copy/Move/Link conflicts and owned Mount/Unmount/Eject notification
fixtures. Fifteen real Stop clicks preserve both files and reap the workers.
The media-artwork fixture does not request kernel device operations.

`Applications/Artwork/Sizers.svg` supplies the five active resize arrows in
Browser, Icon View and Shelf preferences. Shared bar, shaft, arrowhead and bevel
planes reproduce both original 9×15 RGBA images exactly; each density is rendered
from the master. Explicit Workspace-local loading replaces Gorm's embedded
copies without altering the layouts or DesktopKit API. Twenty-five native
canvases match exactly and 25 real drag/Revert pairs restore their initial
geometry. File Copy's two unused Gorm arrow files are excluded. References and
license are pinned in `Tests/Wayland/artwork-originals/workspace-sizers`.
The combined permanent source tests reject 57 altered-source controls. Full
package qualification of this later source batch remains pending.

The home hover state shares the unchanged `Home01.icns` master and adds only
original lit panes, entrance and chimney smoke in `HomeStates.svg`. The two
continuous smoke strokes reproduce the ten original RGBA samples at 100%.
`HomeLights` is shared with the missing two-house neighborhood construction;
that construction keeps its rear/front 32-point house layout, one foreground
tree, original closed reflections and its own diffuse chimney plume. The
1536-pixel assembly retains both 1024-pixel source instances without enlargement.
`Neighborhood.svg` contains only continuous masks, reflection/ground materials
and smoke geometry. The private neighborhood qualification passes 15 native
canvases and five actual drag cancellations. Its sealed archive is 37,820,900
bytes, SHA-256 `88b8fd8d3b14b31b1f49897f0ec2a9425452ae9139cd2c563b74b8a1f194e731`.

`RootStates.svg` references the existing computer in `Root.svg` and adds eight
yellow highlight rays. Its original-design comparison permits the documented
one-pixel antialias fringe and northwest cap difference; it does not claim exact
RGBA. `GNUstepExample.svg` reconstructs the bundled gray circle/step image with
continuous shaded geometry, rather than cropping the differently styled Info
logo. Its silhouette overlap is 0.9965, six black bevel positions are exact and
ten source controls reject geometry/material regressions. The official
GNUstep/icons-rik monochrome SVG was inspected as a construction reference;
its path data and black style are not copied into this gray reconstruction.
The private logo qualification passes ten native preference views. Its
1,757,546-byte archive has SHA-256
`17ffa106ff0c8043f6af4652ee9854dc805d9f3b3e73832b87960443ec9fc6fe`.
The canonical build now stages these masters. A new complete package lifecycle
is required to qualify the combined source batch.

The compact file-panel controls now share `FilePanel.svg` and the fitted
NeXTSpirit house. The original 24-point logical size and house footprint are
preserved. Mount reproduces the original alpha exactly; Unmount retains all 56
maroon arrow pixels. Its footer antialias differs within the recorded source
bounds. The live Open/Save checks pass thirty independently audited canvases
with zero channel difference and ten cancellations; the permanent test also
passes. Fifteen source controls reject changes to shape, bevels, materials,
arrow palette and enlargement. The backing loader is shared by the two panel
classes through their existing parent and introduces no public API.

`Navigation.svg` also contains the original 12-point blue Help link as five
continuous planes/strokes. Its premultiplied RGBA and alpha match the original
exactly. One original fully transparent pixel has different hidden RGB; visible
output is unchanged. The real GNUstep text-attachment renderer passes five
independent native comparisons, with its link target and marker retained.
Thirteen source controls reject geometry, palette and enlargement changes. The
174,902-byte component capsule has SHA-256
`822e7e025eeccad3dd640ce531e5307f809eafe84e048bc740e4e2f2027893c7`.
The permanent helper passes separately. A fresh complete package lifecycle is
required for this panel/Help source batch.

The Login preference module has a separate 66-by-57 monitor icon. Its new
`Applications/Login/Preferences/Artwork.svg` shares the qualified Display
monitor housing through `Monitor.svg`; only the glass and miniature login panel
differ. This avoids duplicating the case, foot and shading. The original two
white fields and white top/left bevels are exact RGBA matches. Glass and panel
material checks, silhouette overlap 0.9601 and original occupied bounds are
recorded separately; the entire raster is not claimed to be identical.
Ten source mutations are rejected. All eleven Preferences modules pass 55 real
matrix comparisons at the five densities, with zero channel difference, while
170 preceding Terminal/Review/Preferences frames stay unchanged. The temporary
VM overlay restores the original resource and changes no executable. The
4,686,174-byte component capsule has SHA-256
`ea391d3962fb0749ba6dc6a44eaca1a88e21b2c29c54f6c222a1ce9b231d85d4`.

Slider and scroller tracks share a procedural reconstruction of the original
SharedGrayAlpha crop at `(49,88,12,12)`. The opaque one-point checker alternates
device-gray 85 and 170, preserving its original phase. An NSCustomImageRep draws
the material at backing density; no cached bitmap or added runtime asset is
needed. The entire original 100% widget canvas matches exactly. The permanent
test passes six fresh native comparisons at 100–200% and back to 100%, with zero
channel difference against independent vector geometry. The original native
crop and atlas hash are pinned under `Tests/Wayland/artwork-originals`.
