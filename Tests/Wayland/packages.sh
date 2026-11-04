#!/bin/sh
# Component packaging checks on the complete disposable NEXTSPACE runtime.
set -eu
test -f /.dockerenv && test "$(id -u)" = 0 && test "${NEXTSPACE_PACKAGE_TEST_DISPOSABLE:-0}" = 1 || {
  echo 'Use a fresh disposable root container with NEXTSPACE_PACKAGE_TEST_DISPOSABLE=1.' >&2; exit 1;
}
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
build=${NEXTSPACE_WAYLAND_BUILD_DIR:-/tmp/nextspace-native-stack}
output="$build/results/packages"
version=${NEXTSPACE_PACKAGE_VERSION_BASE:-0.1.0~ci}
architecture=$(dpkg --print-architecture)
mkdir -p "$output"
python3 "$repo/Packaging/Debian/build-wayland.py" --repo "$repo" \
  --build-dir "$build/package-build" --output "$output" --version "${version}1" \
  > "$build/package-build.log" 2>&1 || { tail -60 "$build/package-build.log"; exit 1; }
first="$output/nextspace-wayland-compositor_${version}1_$architecture"
python3 "$repo/Tests/Wayland/package_source.py" --archive "$first.source.tar.gz" --receipt "$first.json" \
  --work-dir "$build/package-source-replay" --version "${version}2" \
  > "$build/package-source.log" 2>&1 || { tail -60 "$build/package-source.log"; exit 1; }
cp "$build/package-source-replay/packages/"* "$output/"
cp "$build/package-source-replay/results.json" "$output/source-replay.json"
set --
if [ -n "${NEXTSPACE_PACKAGE_CANDIDATE:-}" ]; then
  set -- --candidate "$NEXTSPACE_PACKAGE_CANDIDATE"
fi
python3 "$repo/Tests/Wayland/package_lifecycle.py" "$@" \
  --packages "$first.deb" "$output/nextspace-wayland-compositor_${version}2_$architecture.deb" \
  --workspace "${NEXTSPACE_PACKAGE_WORKSPACE:-$build/apps/Workspace-X11/Workspace.app/Workspace}" \
  --workspace-probe "${NEXTSPACE_PACKAGE_WORKSPACE_PROBE:-$build/fixture/obj/WorkspaceProbe}" \
  --native-probe "${NEXTSPACE_PACKAGE_NATIVE_PROBE:-$build/compositor/registry-probe}" \
  --artifacts "$build/results/package-lifecycle"
