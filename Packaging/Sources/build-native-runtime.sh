#!/bin/sh
# Build the native Wayland runtime in a disposable builder.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
build=$1
mkdir -p "$build"
build=$(CDPATH= cd -- "$build" && pwd)
export NEXTSPACE_STAGE_ROOT="$build/stage"
export NEXTSPACE_WAYLAND_STAGE_ROOT="$build/stage-wayland"
. "$repo/Packaging/Sources/native-foundation.sh"
. "$repo/Packaging/Sources/native-display.sh"
python3 "$repo/Packaging/Sources/build-capture.py" --repo "$repo" --build "$build/capture" \
  --stage "$NEXTSPACE_WAYLAND_STAGE_ROOT"
. "$repo/Packaging/Sources/native-desktop.sh"
build_runtime_frameworks
build_runtime_applications
