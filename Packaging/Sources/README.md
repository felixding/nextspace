# Building NEXTSPACE from sources

The supported rewrite target is native Wayland on Debian 13. Use the pinned
disposable build and Debian package recipe in
[`Packaging/Debian`](../Debian/README.md). Its shared implementation is
`build-native-runtime.sh`, `native-foundation.sh`, `native-display.sh` and
`native-desktop.sh`; it builds no X11 backend or Window Maker.

OpenUp bundles `macunpack`, built by `build-macutils.py` from the archives and
patch pinned in `Protocols/manifest.json`. Its unsigned CRC polynomial fixes
Compact Pro extraction on ARM64 while retaining checksum validation. Packages
include its copyright and complete source inputs for offline replay. Debian's
`arj`, `lhasa` and `macutils` supply the other existing archive commands.

The native build renders only symbols marked `data-reconstructed="true"`, through
`build-images.py --reconstructed-only`. Display, Font, Date, Screen, Keyboard, Mouse, Sound, Services, Localization and Expert are corrected
reconstructions, compared against the original lettering, shapes and palette and
checked in the real Preferences matrix at all five target scales. Display keeps
the original 66×57 canvas, CRT inset, purple glass and low stand; its occupied
bounds match the original. Date retains its original eight hour marks, straight
hands, metal bevel and shaded face using continuous ellipse geometry and
gradients. `Tests/Wayland/date_fidelity.py` checks the device-selected original,
rejects pixel-stair outlines and enlarged bitmaps, and can verify all five
submitted TIFF representations with `--image`. Screen retains its two overlapping
beveled panels, purple glow and green indicator, with shared continuous panel
geometry and gradients. `Tests/Wayland/screen_fidelity.py` protects its borders,
indicator, original palette and smooth high-density shading; ten negative controls
reject redesigns and enlarged rasters. Keyboard preserves its original rectangular
chassis, 68-key layout, three indicators and cable. Shared keycap and bevel
gradients render at each backing density. `Tests/Wayland/keyboard_fidelity.py`
checks the original geometry, opacity, palette and continuous lighting, including
ten negative controls. Mouse preserves the original two-button chassis, curled
cable, button divisions and translucent highlights. `Tests/Wayland/mouse_fidelity.py`
checks its geometry, palette, lighting and genuine high-density curves with twelve
negative controls. Sound preserves the original cabinet, recessed grille, two
driver domes and cast shadow. Its continuous cone/dome geometry retains the
original highlight and shadow placement. `Tests/Wayland/sound_fidelity.py` checks
the selected color original, frame, palette and lighting, with fifteen negative
controls. Services preserves the three stacked panels, steel tray, supporting
hand and blue cuff. Shared frames, curved hand geometry and continuous lighting
retain the original pose and reflections. `Tests/Wayland/services_fidelity.py`
checks 703 exact stack pixels, the 47-pixel white rim, contour, palette and
reflection placement, with twenty negative controls. Localization preserves the
three waved flags, shared metal poles, individual hoist bindings and globe
contours. Its faces, lower bevels and translucent shadows use separate continuous
lighting. `Tests/Wayland/localization_fidelity.py` checks 160 exact landmarks,
original contours and palette, and rejects 29 image mutations plus four malformed
curve arguments. Expert preserves the UNIX certificate, asymmetric chisel-ended
foil spokes, ruby seal, olive/maroon/violet center contours, green mark, forked
ribbon and coral signature. Its tiny paragraph is reconstructed from the visible
ink contours; the original does not establish a readable transcription.
`Tests/Wayland/expert_fidelity.py` protects 51 exact paper pixels, feature weights
and positions, material shading and genuine high-density geometry, with 26
negative controls. These regressions share original-reference and
submitted-representation validation. Date, Screen, Sound and Expert contain separate
grayscale and color representations; AppKit selects the color one. Expert's
grayscale reconstruction is withdrawn. Inspect the device-selected representation
before authoring replacements. The ten module-icon originals are pinned under
`Tests/Wayland/artwork-originals` and checked by `artwork_reference.py --preferences`.
The four Sound Mixer controls also reconstruct their original blue speaker faces,
offset chrome edges, acoustic arcs, microphone capsule/fork/pedestal and six level
dots. Shared geometry preserves the three-point speaker shift and identical
microphone bodies. `Tests/Wayland/sound_controls_fidelity.py` checks all four
originals, material weights and positions, contours, high-density detail and forty
negative controls. `--images <Sound-module-resource-directory>` also checks the
twenty submitted representations. The native Mixer runner retains the original
Gorm positions, clipping and disabled-image opacity.
The source-qualified closed/unavailable folder master is
`Applications/Artwork/Folder.svg`: it preserves the original leather portfolio,
folded panels, maroon crease, binding, spine bevel and three-band cast shadow.
The unavailable state shares the geometry and applies the original color tint.
Its closed design is shared by sixteen original resource paths.
`build-folder-images.py` generates the six Workspace, one DesktopKit and ten
theme consumer paths from this shared source. The private native Workspace
trial passes 85 resource selections and ten exact Icon-view comparisons over all
five densities. Four source aliases and 1,966 unrelated installed files are
preserved. Open and deposit folders still use their originals.
`Tests/Wayland/folder_fidelity.py` checks the master and all ten submitted
representations with fifty-four negative controls.

Large icons now prefer matching NeXTSpirit sources before new construction, per
the user direction of 2026-11-01. `Applications/Artwork/NextSpirit.json` pins both
complete source sets: 48 icons with 1024-pixel representations, both readmes and
the original disk-image hashes. `build-folder-images.py --nextspirit <pack-root>`
uses those verified masters for a personal-use preview; it never enlarges them.
The pack root contains the mounted `set1` and `set2` directories.
The closed, open and derived unavailable states pass 90 host/Linux frame
comparisons and 30 exact native Workspace comparisons. Five cancelled native
file drags and five completed Unicode-file copy drops preserve the expected image
transitions and data. The default SVG path passes ten regression comparisons. `Tests/Wayland/nextspirit.py` checks
the imports, full-resolution frames, tint alpha, alteration, incomplete sets and
enlargement rejection. The readmes restrict use to personal, non-commercial
purposes; unrestricted redistribution is not established. See
[artwork sources](../../docs/Artwork-Sources.md).
`build-nextspirit-images.py` accepts `--pack <pack-root>`,
`--output <bundle-resources>` and `--component terminal` (or `preferences`). It
generates three application-resource paths
through the same resource writer. Terminal uses the silver `Term-White` monitor;
Preferences replaces its static Info-panel logo while retaining its live clock.
Fifteen host/Linux frames and ten actual Info-panel comparisons pass at all five
densities. The original Terminal animation strips remain a separate task. These
explicit personal-preview generators do not change the public package defaults.
The same builder accepts `workspace`, `desktopkit` and `theme` components for Home and
the static Recycler states. Home is generated for all three consumers, including
the DesktopKit path used by the actual viewer. Recycler keeps its 64-point size
and count badge. These five paths pass twenty-five representation selections
and twenty actual native image comparisons at 100–200%. The matching first drag
animation pose now reuses the fitted empty-icon master through the same resource
writer. The remaining three poses use original-style SVG ribbons in
`Applications/Workspace/Artwork.svg`. The shared native artwork step renders
their existing resource paths before building Workspace, using the same image
writer as the other applications and frameworks. The complete personal-preview
animation passes twenty actual frame comparisons at all five densities.
The generic application monitor uses `DefaultApp.icns` for DesktopKit's
`NXApplication.tiff` and the matching Workspace copy. The same generator now
covers seven Workspace/DesktopKit/theme paths, with thirty-five native resource
selections. Fifteen exact Icon-view comparisons cover three application-wrapper
types over all five scales. The separate green-question-mark monitor stays
unchanged in that cohort. The following screen-construction cohort supplies
the question-mark and UNIX variants through `Applications/Artwork/MonitorScreens.svg`.
`NextSpiritArtwork` caches each imported master once and renders the SVG screen
directly at each requested density, keeping the housing unchanged. The twelve
Workspace/DesktopKit/theme paths pass sixty native resource selections and
fifty-five actual image comparisons. Original-design source checks reject
sixteen mutations, and fourteen frames verify the unchanged housing. These
combined assets retain the NeXTSpirit personal-preview restriction.
Recycler's two entries also declare `content_bounds` matching the native-reader
originals. The importer preserves the artist's aspect ratio and source pixels,
pads to the original center and renders each backing representation directly.
The resulting occupied bounds match the original 49×49-point footprint inside
the 64-point Dock icon. Animation resources are unchanged and remain unqualified
for HiDPI.
`Applications/Artwork/Root.svg` supplies the missing original-style root computer.
The existing resource writer generates DesktopKit's `NXRoot.tiff` and the theme's
`common_Root_PC.tiff` from the same vector master at all five backing densities.
Their native-reader originals are identical. Eight design controls, ten resource
selections and five exact Workspace root-path captures qualify the private asset
trial; full current-source package qualification remains open.
`build-images.py` also accepts a symbol's `data-files` list and uses the same
validated resource writer for equivalent ordinary/Gorm paths. Terminal's
reconstructed `ScrollingMach` and `ScrollingOutput` symbols use this facility;
the unqualified static Terminal draft remains excluded. All four strip paths
retain their logical dimensions and five directly rendered backing representations.
The private native trial passes eighty Info-panel/miniwindow frame comparisons.
The shared icon tile is reconstructed from its original bevel geometry and
continuous gradients. Its complete 100% image differs by at most one color level,
with identical alpha; the production icon view passes all five target scales.
Checkboxes, radio buttons and both scroller dimples preserve the original visible
pixels, alpha and logical dimensions at 100%. Shared frames and circular bevels
render at each backing density; the six states pass thirty native comparisons
over all five scales. `build-theme-images.py --reconstructed-only` selects these
six states and the tile while leaving the remaining draft artwork excluded.
Other application,
framework and theme resources retain the originals temporarily. The older
SVG redraws remain excluded because they changed the original appearance. Prior representation and
capture checks establish rendering behavior, not fidelity to the original art.
Genuine HiDPI replacements remain unfinished. Do not substitute bitmap upscaling
or a stylistic approximation. The compositor title glyphs share reconstructed
vector geometry with the AppKit theme; check their original-resource fidelity with
`python3 Tests/Wayland/artwork_fidelity.py --artifacts <output-directory>
--reference-probe <current-WaylandProbe>`; the probe decodes the packed originals.

Draft artwork builds require `librsvg2-bin` and Python Pillow, included in the
test builder. Cursor SVG masters and their alias/hotspot/animation manifest live
in `OS/Linux/usr/share/icons/NextSpace/scalable`. All 57 cursor designs are
reconstructed. Each of eleven sizes contains 59 frames, including the three busy
phases, preserving all original alias chains, hotspots and delays. The busy cursor uses fixed hue orientation
with changing shading. `watch_artwork.py --source <cursors.svg> --check` validates
its generated gradients against the embedded authoring model; omit `--check` to
regenerate them. The helper uses only the Python standard library. Title controls, scrollbar arrows,
radio buttons, checkboxes and knob dimples share
`Libraries/gnustep/nextspace-theme/Resources/ThemeImages/WindowControls.svg`.
The Login panel and controls use `Applications/Login/Resources/LoginArtwork.svg`;
the experimental renderer generates five TIFF representations from 100–200%.
Application `Artwork.svg` masters use the same `build-images.py` renderer;
Login enables all seven reconstructed symbols. The panel uses
shared letter contours, continuous cube geometry, lighting and bevel gradients;
the two field backgrounds reuse one inset. Original-reference and native-buffer
checks cover all five scales. Labels and button captions share manually drawn
letter geometry; the four button states preserve the original symbols, bevels,
palette and caption displacement. The native greeter checks all seven designs
and both button states at every target scale.
The loader uses the Gorm archive's original normal/highlighted button mapping.
TextEdit includes its icon/title and document icons, while Terminal includes its icon and scrolling
strips. SVG symbols declare geometry with a `viewBox` and may use `data-file` for a
relative TIFF resource path. Preferences includes its icon, clock tile and
all ten module icons, plus shared volume/microphone Mixer symbols. Review and OpenUp also include their document and
control artwork. Local SVG definition references share monitor/document geometry
under `Applications/Artwork`; the renderer inlines these definitions and rejects
network references, missing targets and duplicate IDs.
`data-logical-size` preserves original point dimensions when legacy TIFF
resolution metadata is fractional; otherwise the declared view box supplies
the logical size. The checkbox resources retain their original 15.003418-point
dimensions at every representation.
DesktopKit also supplies a shared clock-atlas master in `Frameworks/DesktopKit/Artwork.svg`;
the experimental renderer handles all ten locale atlases through the same image builder.
The icon-tile background shares the theme master;
the theme and `/Library/Images` install the same generated representations.
Experimental build helpers render these sources directly at each backing density; the
compositor compiles the same title geometry into Cairo primitives. Legacy small
bitmaps are retained as references and are not the input for these assets.

The obsolete numbered X11 build scripts and source-tree installers have been
removed. The shared native pipeline and Debian recipe above are the maintained
source-build path. They retain the pinned dependency archives, local patches,
asset generators and framework/application build helpers needed for refinement.
The retired Xorg session entry, Xresources defaults, `startx` home setup and
Raspberry Pi Xorg-mode snippets are removed as well. Native session entry and
user hooks remain available through the Debian package launchers and Login hook
runner.
