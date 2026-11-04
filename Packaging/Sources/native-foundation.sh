#!/bin/sh
# Shared Debian source-build foundation. Source with repo/build set in a fresh
# disposable root container; NEXTSPACE_STAGE_ROOT additionally retains DESTDIR.
test -f /.dockerenv && test "$(id -u)" = 0 || {
  echo 'Build the runtime foundation in a disposable root container.' >&2; exit 1;
}
: "${repo:?Set repo before sourcing the runtime foundation}"
: "${build:?Set build before sourcing the runtime foundation}"
sources="$build/native-sources"
mkdir -p "$sources"

python3 - "$repo/Tests/Wayland/native-stack-sources.json" "$sources" "$repo" <<'PY'
import hashlib, json, pathlib, shutil, subprocess, sys
root = pathlib.Path(sys.argv[2])
for name, package in json.load(open(sys.argv[1])).items():
    archive = root / (name + '.tar.gz')
    if not archive.exists():
        bundled = pathlib.Path(sys.argv[3]) / 'sources/native' / archive.name
        if bundled.is_file(): shutil.copyfile(bundled, archive)
        else: subprocess.run(['curl', '-fLsS', 'https://codeload.github.com/' + package['repository'] +
            '/tar.gz/' + package['revision'], '-o', str(archive)], check=True)
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == package['sha256'], name
    source = root / name
    if not source.exists():
        source.mkdir()
        subprocess.run(['tar', 'xzf', str(archive), '--strip-components=1', '-C', str(source)], check=True)
PY
cp "$repo/Tests/Wayland/native-stack-sources.json" "$build/native-stack-sources.json"

. "$repo/Packaging/Sources/runtime-build-functions.sh"
cmake_project()
{
  project_name=$1; shift
  stage "$project_name-configure" cmake -S "$sources/$project_name" -B "$sources/$project_name-build" \
    -G Ninja -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
    -DCMAKE_INSTALL_PREFIX=/usr/NextSpace -DCMAKE_INSTALL_LIBDIR=lib "$@"
  stage "$project_name-build" cmake --build "$sources/$project_name-build" -j"${JOBS:-4}"
  runtime_install "$project_name" cmake --install "$sources/$project_name-build"
}
cmake_project dispatch -DINSTALL_PRIVATE_HEADERS=YES -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=Release \
  '-DCMAKE_C_FLAGS=-Wno-error=unused-but-set-variable -Wno-error=cast-function-type-mismatch'
cmake_project robin-map
cmake_project objc -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DCMAKE_OBJC_COMPILER=clang \
  -DCMAKE_OBJCXX_COMPILER=clang++ -DCMAKE_PREFIX_PATH=/usr/NextSpace \
  -DGNUSTEP_INSTALL_TYPE=NONE -DTESTS=OFF -DCMAKE_BUILD_TYPE=Release
# Keep libdispatch's public Blocks header, as in the existing packaging scripts.
cp "$sources/dispatch/src/BlocksRuntime/Block.h" /usr/NextSpace/include/Block.h
if [ -n "${NEXTSPACE_STAGE_ROOT:-}" ]; then
  install -D "$sources/dispatch/src/BlocksRuntime/Block.h" "$NEXTSPACE_STAGE_ROOT/usr/NextSpace/include/Block.h"
fi
(
  cd "$sources/corefoundation"
  patch_file="$repo/Libraries/libcorefoundation/CFStream-linux-thread-name.patch"
  if ! patch --reverse --dry-run -p1 < "$patch_file" >/dev/null 2>&1; then
    patch -p1 < "$patch_file"
  fi
)
cmake_project corefoundation -DCF_DEPLOYMENT_SWIFT=NO -DBUILD_SHARED_LIBS=YES -DCMAKE_BUILD_TYPE=Release \
  '-DCMAKE_C_FLAGS=-I/usr/NextSpace/include -Wno-switch -Wno-enum-conversion' \
  '-DCMAKE_SHARED_LINKER_FLAGS=-L/usr/NextSpace/lib -luuid'

export CC=clang CXX=clang++
export PKG_CONFIG_PATH=/usr/NextSpace/lib/pkgconfig
export LD_LIBRARY_PATH=/usr/NextSpace/lib
cp "$repo/Libraries/gnustep/nextspace.fsl" "$sources/make/FilesystemLayouts/nextspace"
(
  cd "$sources/make"
  stage make-configure env 'CFLAGS=-F/usr/NextSpace/Frameworks -I/usr/NextSpace/include' \
    LDFLAGS=-L/usr/NextSpace/lib ./configure --prefix=/ \
    --with-config-file=/Library/Preferences/GNUstep.conf --with-layout=nextspace \
    --enable-native-objc-exceptions --with-library-combo=ng-gnu-gnu
  runtime_install make make install
)
set +u
. /Developer/Makefiles/GNUstep.sh
set -u
(
  cd "$sources/base"
  python3 "$repo/Tests/Wayland/base-patches.py" "$repo" "$sources/base.tar.gz" > "$build/base-patches.log"
  sh "$repo/Libraries/gnustep/patches/apply-base-patches.sh" "$sources/base"
  stage base-configure env CPPFLAGS=-I/usr/NextSpace/include LDFLAGS=-L/usr/NextSpace/lib ./configure
  stage base-build make -j"${JOBS:-4}"
  runtime_install base make install
)
export NEXTSPACE_GNUSTEP_SH=/Developer/Makefiles/GNUstep.sh
export NEXTSPACE_PREBUILT_BASE_SOURCE="$sources/base"
export NEXTSPACE_WAYLAND_BUILD_DIR="$build"
