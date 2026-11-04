#!/bin/sh
# Build the pinned Base fix, or verify the runtime already built by native-stack.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
build=$1
if [ -n "${NEXTSPACE_PREBUILT_BASE_SOURCE:-}" ]; then
  sh "$repo/Libraries/gnustep/patches/apply-base-patches.sh" "$NEXTSPACE_PREBUILT_BASE_SOURCE" check
  exit 0
fi
archive="$build/base.tar.gz"
python3 - "$repo/Tests/Wayland/native-stack-sources.json" "$archive" <<'PY'
import hashlib, json, pathlib, subprocess, sys
package = json.load(open(sys.argv[1]))['base']
archive = pathlib.Path(sys.argv[2])
if not archive.exists():
    subprocess.run(['curl', '-fLsS', 'https://codeload.github.com/' + package['repository'] +
        '/tar.gz/' + package['revision'], '-o', str(archive)], check=True)
assert hashlib.sha256(archive.read_bytes()).hexdigest() == package['sha256'], 'Base archive checksum'
PY
python3 "$repo/Tests/Wayland/base-patches.py" "$repo" "$archive" > "$build/base-patches.log"
if [ ! -d "$build/base" ]; then
  mkdir "$build/base"
  tar xzf "$archive" --strip-components=1 -C "$build/base"
fi
sh "$repo/Libraries/gnustep/patches/apply-base-patches.sh" "$build/base"
(cd "$build/base" && ./configure && make -j"${JOBS:-4}" && make install) > "$build/base-build.log" 2>&1 || {
  tail -60 "$build/base-build.log"; exit 1;
}
ldconfig
