#!/bin/sh
# Shared pinned GUI, theme and Cairo backends. Source with repo/build set.
. "$repo/Packaging/Sources/runtime-build-functions.sh"
. "$repo/Packaging/Sources/copy-sources.sh"
archive="$build/gui.tar.gz"
gui_commit=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["gnustep_gui"]["commit"])' "$repo/Protocols/manifest.json")
gui_checksum=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["gnustep_gui"]["sha256"])' "$repo/Protocols/manifest.json")
if [ ! -f "$archive" ]; then
  if [ -f "$repo/sources/gui.tar.gz" ]; then cp "$repo/sources/gui.tar.gz" "$archive"
  else curl -fLsS "https://codeload.github.com/gnustep/libs-gui/tar.gz/$gui_commit" -o "$archive"; fi
fi
echo "$gui_checksum  $archive" | sha256sum -c -
python3 "$repo/Tests/Wayland/gui-patches.py" "$repo" "$archive"
python3 - "$repo" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
for entry in json.loads((root / 'Protocols/manifest.json').read_text())['protocols']:
    assert hashlib.sha256((root / entry['path']).read_bytes()).hexdigest() == entry['sha256'], entry['path']
PY
if [ ! -d "$build/gui" ]; then
  mkdir "$build/gui"
  tar xzf "$archive" --strip-components=1 -C "$build/gui"
fi
sh "$repo/Libraries/gnustep/patches/apply-gui-patches.sh" "$build/gui" 1
stage gui-artwork python3 "$repo/Packaging/Sources/build-images.py" \
  --source "$repo/Libraries/gnustep/Artwork.svg" --output "$build/gui" --reconstructed-only
(
  cd "$build/gui"
  stage gui-image-formats pkg-config --print-errors --exists MagickCore
  stage gui-configure ./configure --enable-imagemagick
  stage gui-build make -j"${JOBS:-4}"
  runtime_install gui make install
)
ldconfig
stage cursors-install python3 "$repo/Packaging/Sources/build-cursors.py" \
  --source "$repo/OS/Linux/usr/share/icons/NextSpace" --reconstructed-only
cursor_stage=${NEXTSPACE_WAYLAND_STAGE_ROOT:-${NEXTSPACE_STAGE_ROOT:-}}
if [ -n "$cursor_stage" ]; then
  stage cursors-stage sh -c 'mkdir -p "$1/usr/share/icons"; cp -a /usr/share/icons/NextSpace "$1/usr/share/icons/"' sh "$cursor_stage"
fi
copy_sources "$repo/Libraries/gnustep/nextspace-theme" "$build/theme"
stage theme-folders python3 "$repo/Packaging/Sources/build-folder-images.py" \
  --component theme --output "$build/theme/Resources/ThemeImages"
stage theme-root python3 "$repo/Packaging/Sources/build-folder-images.py" \
  --source "$repo/Applications/Artwork/Root.svg" \
  --component theme --output "$build/theme/Resources/ThemeImages"
stage theme-selection python3 "$repo/Packaging/Sources/build-folder-images.py" \
  --source "$repo/Applications/Artwork/Selection.svg" \
  --component theme --output "$build/theme/Resources/ThemeImages"
stage theme-documents python3 "$repo/Packaging/Sources/build-folder-images.py" \
  --source "$repo/Applications/Artwork/Documents.svg" \
  --component theme --output "$build/theme/Resources/ThemeImages"
stage theme-navigation python3 "$repo/Packaging/Sources/build-folder-images.py" \
  --source "$repo/Applications/Artwork/Navigation.svg" \
  --component theme --output "$build/theme/Resources/ThemeImages"
stage theme-file-panel python3 "$repo/Packaging/Sources/build-folder-images.py" \
  --source "$repo/Applications/Artwork/FilePanel.svg" \
  --component theme --output "$build/theme/Resources/ThemeImages"
# Render only replacements verified against the original artwork.
stage theme-artwork python3 "$repo/Packaging/Sources/build-theme-images.py" \
  --source "$repo/Libraries/gnustep/nextspace-theme/Resources/ThemeImages/WindowControls.svg" \
  --cursors "$repo/OS/Linux/usr/share/icons/NextSpace/scalable/cursors.svg" \
  --output "$build/theme/Resources/ThemeImages" --reconstructed-only
render_nextspirit_artwork theme "$build/theme/Resources/ThemeImages"
(
  cd "$build/theme"
  stage theme-build make
  runtime_install theme make install
)
runtime_install icon-tile sh -c 'install -D -m644 "$1" "${DESTDIR:-}/Library/Images/common_Tile.tiff"' \
  sh "$build/theme/Resources/ThemeImages/common_Tile.tiff"

backend_tree="$build/back"
copy_sources "$repo/Libraries/gnustep/back" "$backend_tree"
(
  cd "$backend_tree"
  stage wayland-autoreconf autoreconf -fi
  stage wayland-configure ./configure --enable-server=wayland --enable-graphics=cairo --with-name=wayland
  stage wayland-build make -j"${JOBS:-4}"
  NEXTSPACE_STAGE_ROOT="${NEXTSPACE_WAYLAND_STAGE_ROOT:-${NEXTSPACE_STAGE_ROOT:-}}" runtime_install wayland make install
)
