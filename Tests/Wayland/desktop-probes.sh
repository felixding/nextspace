#!/bin/sh
# Build validation clients against the installed packaged runtime.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
build=$1
mkdir -p "$build"
build=$(CDPATH= cd -- "$build" && pwd)
set +u
. /Developer/Makefiles/GNUstep.sh
set -u
. "$repo/Packaging/Sources/copy-sources.sh"
copy_sources "$repo/Tests/GNUstep-GUI" "$build/source"
cp "$repo/Frameworks/SystemKit/OSESessionSettings.h" "$build/source/"
for name in WSShellConnection WSDockSettings WSIconTileView; do
  cp "$repo/Applications/Workspace/$name.h" "$repo/Applications/Workspace/$name.m" "$build/source/"
done
cp "$repo/Applications/Terminal/TerminalIcon.h" "$repo/Applications/Terminal/TerminalIcon.m" "$build/source/"
(
  cd "$build/source"
  make -j"${JOBS:-4}" WAYLAND_TESTS=yes SYSTEMKIT_TESTS=yes WORKSPACE_SHELL_TESTS=yes ARTWORK_TESTS=yes TERMINAL_ARTWORK_TESTS=yes \
    NEXTSPACE_FRAMEWORKS_DIR="$repo/Frameworks" \
    NEXTSPACE_PROTOCOLS_DIR="$repo/Protocols" \
    WaylandProbe.all.tool.variables WorkspaceProbe.all.tool.variables DragProbe.all.tool.variables \
    PasteboardProbe.all.tool.variables PrintingProbe.all.tool.variables \
    EventQueueProbe.all.tool.variables \
    DisplayModelProbe.all.tool.variables GammaModelProbe.all.tool.variables NameServerLockProbe.all.tool.variables \
    AlertProbe.all.tool.variables PowerProbe.all.tool.variables ShellConnectionProbe.all.tool.variables \
    OutputResultProbe.all.tool.variables ArtworkProbe.all.tool.variables TerminalArtworkProbe.all.tool.variables \
    ClockNotificationProbe.all.tool.variables
) > "$build/build.log" 2>&1 || { tail -60 "$build/build.log"; exit 1; }
mkdir -p "$build/bin"
gnustep-config --objc-flags > "$build/compiler-flags.txt"
gnustep-config --gui-libs >> "$build/compiler-flags.txt"
for name in WaylandProbe WorkspaceProbe DragProbe PasteboardProbe PrintingProbe EventQueueProbe DisplayModelProbe GammaModelProbe NameServerLockProbe AlertProbe PowerProbe ShellConnectionProbe OutputResultProbe ArtworkProbe TerminalArtworkProbe ClockNotificationProbe; do
  cp "$build/source/obj/$name" "$build/bin/$name"
  patchelf --set-rpath /usr/NextSpace/lib:/Library/Libraries "$build/bin/$name"
done
cc "$repo/Tests/Wayland/pipewire-probe.c" -o "$build/bin/pipewire-probe" \
  $(pkg-config --cflags --libs libpipewire-0.3) >> "$build/build.log" 2>&1
cc -shared -fPIC "$repo/Tests/Wayland/stderr-trace.c" -o "$build/bin/stderr-trace.so" >> "$build/build.log" 2>&1
cc -shared -fPIC "$repo/Tests/Wayland/defaults-lock-delay.c" -ldl \
  -o "$build/bin/defaults-lock-delay.so" >> "$build/build.log" 2>&1
clang $(gnustep-config --objc-flags) -shared -fPIC \
  "$repo/Tests/GNUstep-GUI/ImageUsageTrace.m" -o "$build/bin/image-usage-trace.so" \
  $(gnustep-config --gui-libs) -Wl,-rpath,/usr/NextSpace/lib -Wl,-rpath,/Library/Libraries \
  >> "$build/build.log" 2>&1
for name in HelpAttachmentProbe TrackPatternProbe RunLoopTimerProbe; do
  clang $(gnustep-config --objc-flags) "$repo/Tests/GNUstep-GUI/$name.m" \
    -o "$build/bin/$name" $(gnustep-config --gui-libs) \
    -Wl,-rpath,/usr/NextSpace/lib -Wl,-rpath,/Library/Libraries >> "$build/build.log" 2>&1
done
