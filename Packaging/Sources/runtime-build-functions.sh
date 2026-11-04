# Shared build logging and optional package staging. Source with build set.
stage()
{
  stage_name=$1; shift
  if ! "$@" > "$build/native-$stage_name.log" 2>&1; then
    tail -60 "$build/native-$stage_name.log" >&2; exit 1
  fi
}
# Install for subsequent link steps, and optionally retain a package stage.
runtime_install()
{
  install_name=$1; shift
  stage "$install_name-install" "$@"
  if [ -n "${NEXTSPACE_STAGE_ROOT:-}" ]; then
    case "$1" in
      make|gmake|*/make|*/gmake) stage "$install_name-stage" "$@" DESTDIR="$NEXTSPACE_STAGE_ROOT" ;;
      *) stage "$install_name-stage" env DESTDIR="$NEXTSPACE_STAGE_ROOT" "$@" ;;
    esac
  fi
}

# Use the verified local artist sources when present. Source packages retain
# this directory, so an offline replay selects the same artwork automatically.
render_nextspirit_artwork()
{
  artwork_component=$1
  artwork_output=$2
  artwork_pack="$repo/Applications/Artwork/NeXTSpirit"
  [ -d "$artwork_pack" ] || return 0
  case "$artwork_component" in
    workspace|desktopkit|theme)
      stage "$artwork_component-nextspirit-folders" python3 "$repo/Packaging/Sources/build-folder-images.py" \
        --component "$artwork_component" --output "$artwork_output" --nextspirit "$artwork_pack"
      ;;
  esac
  if [ -n "${NEXTSPACE_STAGE_ROOT:-}" ]; then
    stage "$artwork_component-nextspirit" python3 "$repo/Packaging/Sources/build-nextspirit-images.py" \
      --pack "$artwork_pack" --component "$artwork_component" --output "$artwork_output" \
      --source-copy "$NEXTSPACE_STAGE_ROOT/usr/NextSpace/share/artwork/NeXTSpirit"
  else
    stage "$artwork_component-nextspirit" python3 "$repo/Packaging/Sources/build-nextspirit-images.py" \
      --pack "$artwork_pack" --component "$artwork_component" --output "$artwork_output"
  fi
}
