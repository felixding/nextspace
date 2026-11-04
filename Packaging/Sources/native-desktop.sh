# Shared framework/application build for native CI and Debian package staging.
# Source with repo/build and the GNUstep environment set.
. "$repo/Packaging/Sources/runtime-build-functions.sh"
. "$repo/Packaging/Sources/copy-sources.sh"

render_runtime_artwork()
{
  if [ -f "$2" ]; then
    stage "$1-artwork" python3 "$repo/Packaging/Sources/build-images.py" \
      --source "$2" --output "$3" --reconstructed-only
  fi
}

build_runtime_frameworks()
{
  mkdir -p "$build/frameworks" "$build/apps"
  for framework in SystemKit DesktopKit SoundKit; do
    copy_sources "$repo/Frameworks/$framework" "$build/frameworks/$framework"
    if [ "$framework" = DesktopKit ]; then
      stage DesktopKit-folders python3 "$repo/Packaging/Sources/build-folder-images.py" \
        --component desktopkit --output "$build/frameworks/DesktopKit/Resources/Images"
      stage DesktopKit-root python3 "$repo/Packaging/Sources/build-folder-images.py" \
        --source "$repo/Applications/Artwork/Root.svg" \
        --component desktopkit --output "$build/frameworks/DesktopKit/Resources/Images"
      stage DesktopKit-documents python3 "$repo/Packaging/Sources/build-folder-images.py" \
        --source "$repo/Applications/Artwork/Documents.svg" \
        --component desktopkit --output "$build/frameworks/DesktopKit/Resources/Images"
      stage DesktopKit-example python3 "$repo/Packaging/Sources/build-folder-images.py" \
        --source "$repo/Applications/Artwork/GNUstepExample.svg" \
        --component desktopkit --output "$build/frameworks/DesktopKit/Resources/Images"
      stage DesktopKit-file-panel python3 "$repo/Packaging/Sources/build-folder-images.py" \
        --source "$repo/Applications/Artwork/FilePanel.svg" \
        --component desktopkit --output "$build/frameworks/DesktopKit/Resources/Images"
    fi
    artwork="$repo/Frameworks/$framework/Artwork.svg"
    render_runtime_artwork "$framework" "$artwork" "$build/frameworks/$framework"
    if [ "$framework" = DesktopKit ]; then
      render_nextspirit_artwork desktopkit "$build/frameworks/DesktopKit/Resources/Images"
    fi
    (
      cd "$build/frameworks/$framework"
      stage "$framework-build" make -j"${JOBS:-4}"
      runtime_install "$framework" make install
    )
  done
}

build_runtime_applications()
{
  copy_sources "$repo/Applications/Artwork" "$build/apps/Artwork"
  copy_sources "$repo/Applications/Workspace" "$build/apps/Workspace"
  stage Workspace-folders python3 "$repo/Packaging/Sources/build-folder-images.py" \
    --component workspace --output "$build/apps/Workspace/Resources"
  stage Workspace-selection python3 "$repo/Packaging/Sources/build-folder-images.py" \
    --source "$repo/Applications/Artwork/Selection.svg" \
    --component workspace --output "$build/apps/Workspace/Resources"
  stage Workspace-floppy python3 "$repo/Packaging/Sources/build-folder-images.py" \
    --source "$repo/Applications/Artwork/Floppy.svg" \
    --component workspace --output "$build/apps/Workspace/Resources"
  stage Workspace-documents python3 "$repo/Packaging/Sources/build-folder-images.py" \
    --source "$repo/Applications/Artwork/Documents.svg" \
    --component workspace --output "$build/apps/Workspace/Resources"
  stage Workspace-root-states python3 "$repo/Packaging/Sources/build-folder-images.py" \
    --source "$repo/Applications/Artwork/RootStates.svg" \
    --component workspace --output "$build/apps/Workspace/Resources"
  stage Workspace-example python3 "$repo/Packaging/Sources/build-folder-images.py" \
    --source "$repo/Applications/Artwork/GNUstepExample.svg" \
    --component workspace --output "$build/apps/Workspace/Resources"
  stage Workspace-navigation python3 "$repo/Packaging/Sources/build-folder-images.py" \
    --source "$repo/Applications/Artwork/Navigation.svg" \
    --component workspace --output "$build/apps/Workspace/Resources"
  stage Workspace-debian python3 "$repo/Packaging/Sources/build-folder-images.py" \
    --source "$repo/Applications/Artwork/Debian.svg" \
    --component workspace --output "$build/apps/Workspace/Resources"
  stage Workspace-debian-attribution cp "$repo/Applications/Artwork/Debian.svg" \
    "$repo/Applications/Artwork/Debian-LICENSE.txt" "$build/apps/Workspace/Resources/"
  render_runtime_artwork Workspace "$build/apps/Workspace/Artwork.svg" "$build/apps/Workspace"
  render_runtime_artwork Workspace-Finder "$build/apps/Artwork/Finder.svg" "$build/apps/Workspace"
  render_runtime_artwork Workspace-operations "$build/apps/Artwork/Operations.svg" "$build/apps/Workspace"
  render_runtime_artwork Workspace-sizers "$build/apps/Artwork/Sizers.svg" "$build/apps/Workspace"
  render_nextspirit_artwork workspace "$build/apps/Workspace/Resources"
  render_nextspirit_artwork inspectors "$build/apps/Workspace/Inspectors/English.lproj"
  (
    cd "$build/apps/Workspace"
    stage Workspace-build make -j"${JOBS:-4}" NEXTSPACE_BUILD_WAYLAND=1 NEXTSPACE_PROTOCOLS_DIR="$repo/Protocols"
    if [ -n "${NEXTSPACE_STAGE_ROOT:-}" ]; then
      runtime_install Workspace make install NEXTSPACE_BUILD_WAYLAND=1 NEXTSPACE_PROTOCOLS_DIR="$repo/Protocols"
    fi
  )
  for app in Terminal TextEdit Review TimeMon Preferences OpenUp Login; do
    copy_sources "$repo/Applications/$app" "$build/apps/$app"
    if [ "$app" = Login ]; then
      artwork="$build/apps/$app/Resources/LoginArtwork.svg"
      image_output="$build/apps/$app/Resources/Login.gorm"
    else
      artwork="$build/apps/$app/Artwork.svg"
      image_output="$build/apps/$app"
    fi
    render_runtime_artwork "$app" "$artwork" "$image_output"
    case "$app" in
      Terminal) render_nextspirit_artwork terminal "$build/apps/$app" ;;
      Preferences) render_nextspirit_artwork preferences "$build/apps/$app" ;;
      Login) render_runtime_artwork Login-preferences "$build/apps/$app/Preferences/Artwork.svg" "$build/apps/$app/Preferences" ;;
      Review) render_nextspirit_artwork review "$build/apps/$app" ;;
    esac
    (
      cd "$build/apps/$app"
      stage "$app-build" make -j"${JOBS:-4}"
      if [ "$app" = OpenUp ]; then
        stage OpenUp-macunpack python3 "$repo/Packaging/Sources/build-macutils.py" \
          --repo "$repo" --build "$build/macutils" --output "$build/apps/OpenUp/OpenUp.app/Resources/macunpack"
      fi
      if [ -n "${NEXTSPACE_STAGE_ROOT:-}" ]; then
        runtime_install "$app" make install
        if [ "$app" = OpenUp ]; then
          runtime_install OpenUp-macunpack sh -c 'install -D -m755 "$1" "${DESTDIR:-}/Applications/OpenUp.app/Resources/macunpack"' \
            sh "$build/apps/OpenUp/OpenUp.app/Resources/macunpack"
        fi
      fi
    )
  done
}
