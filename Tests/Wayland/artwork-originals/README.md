These PNGs preserve the original theme artwork selected and exported by GNUstep
at 100% scale. They were captured before the title-path reconstruction, not
rendered from its SVG. The manifest records each original TIFF's SHA-256, export
hash and representation selection, plus the frozen probe and evidence archive.
The source resources retain their existing licenses.

`artwork_fidelity.py` checks the original resource hash before using a fixture.
With `--reference-probe`, it exports directly from that resource instead. This
keeps compositor checks independent of a local GNUstep installation while the
integration checks still exercise the actual decoder and representation choice.

The `preferences_*.png` fixtures also preserve the ten original Preferences module
icons selected for an RGB device. Date, Screen, Sound and Expert select their
second representation; the first grayscale preview is a different design.
`artwork_reference.py --preferences` checks source and PNG hashes, all eleven
density selections and the complete exported pixels. The source and installed
package runners use this check before subsequent artwork comparisons. These
fixtures are design references, not replacement HiDPI assets.

The seven `login_*.png` fixtures preserve GNUstep's selections from the original
`Login.gorm` resources. Some legacy TIFFs cannot be read directly by Pillow;
the references were exported through `WaylandProbe --image-reference` instead.
`artwork_reference.py --login` checks their source hashes, pixels and all eleven
density selections. Source and package checks include both Login and Preferences
groups. The Gorm archive's embedded button images independently establish the
normal/highlighted assignments; filenames alone do not establish those states.
