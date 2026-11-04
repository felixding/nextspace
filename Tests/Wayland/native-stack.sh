#!/bin/sh
# Full runtime and real applications; installs only in a disposable Docker guest.
set -eu
test -f /.dockerenv || { echo "Run native-stack.sh inside the disposable Docker test image." >&2; exit 1; }
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
. "$repo/Tests/Wayland/copy-sources.sh"
build=${NEXTSPACE_WAYLAND_BUILD_DIR:-/tmp/nextspace-native-stack}
mkdir -p "$build"
build=$(CDPATH= cd -- "$build" && pwd)
. "$repo/Packaging/Sources/native-foundation.sh"
sh "$repo/Tests/Wayland/build.sh"
python3 "$repo/Tests/Wayland/name_server_lock.py" --probe "$build/fixture/obj/NameServerLockProbe" \
  --artifacts "$build/results/name-server-lock"
python3 "$repo/Packaging/Sources/build-capture.py" --repo "$repo" --build "$build/capture" \
  --stage "$build/capture-stage"
meson configure "$build/compositor" -Dportals=true
meson compile -C "$build/compositor"
gnustep-config --objc-flags > "$build/native-runtime.txt"
ldd "$build/fixture/obj/WaylandProbe" >> "$build/native-runtime.txt"

. "$repo/Packaging/Sources/native-desktop.sh"
build_runtime_frameworks
# Match the desktop package's font discovery before launching its applications.
install -m644 "$repo/OS/Linux/etc/fonts/conf.d/25-nextspace-fonts.conf" /etc/fonts/conf.d/25-nextspace-fonts.conf
fc-cache /Library/Fonts
(cd "$build/fixture"; stage DisplayModelProbe-build make WAYLAND_TESTS=yes SYSTEMKIT_TESTS=yes \
  NEXTSPACE_FRAMEWORKS_DIR="$repo/Frameworks" \
  DisplayModelProbe.all.tool.variables GammaModelProbe.all.tool.variables PowerProbe.all.tool.variables AlertProbe.all.tool.variables)
"$build/fixture/obj/GammaModelProbe" > "$build/results/gamma-model.log" 2>&1
python3 "$repo/Tests/Wayland/power.py" --probe "$build/fixture/obj/PowerProbe" \
  --artifacts "$build/results/power-api"
python3 "$repo/Tests/Wayland/outputs.py" --compositor "$build/compositor/nextspace-compositor" \
  --shell-probe "$build/compositor/shell-probe" --registry-probe "$build/compositor/registry-probe" \
  --readonly-probe "$build/fixture/obj/DisplayModelProbe" --artifacts "$build/results/display-bootstrap"
build_runtime_applications
# The installed user launcher also needs Login's production hook executable.
installed_bin=$(cat "$build/results/installed-session-bin.txt")
install -m755 "$build/apps/Login/obj/nextspace-session-hook" "$installed_bin/nextspace-session-hook"
ldd "$installed_bin/nextspace-compositor" >> "$build/native-runtime.txt"
WAYLAND_DEBUG=client python3 "$repo/Tests/Wayland/supervisor.py" --supervisor "$installed_bin/nextspace-session" \
  --compositor "$installed_bin/nextspace-compositor" --shell-probe "$build/fixture/obj/ShellConnectionProbe" \
  --client "$build/compositor/gtk-probe" --input-method-probe "$build/compositor/registry-probe" \
  --private-bus --launcher "$installed_bin/nextspace-wayland-session" \
  --artifacts "$build/results/supervisor-native-launcher"
XDG_DESKTOP_PORTAL_DIR="$repo/OS/Linux/usr/share/xdg-desktop-portal/portals" \
python3 "$repo/Tests/Wayland/portal.py" --compositor "$build/compositor/nextspace-compositor" \
  --shell-probe "$build/compositor/shell-probe" --receiver "$build/compositor/pipewire-probe" \
  --chooser "$build/apps/Workspace/obj/nextspace-screencast-chooser" --client "$build/compositor/gtk-probe" \
  --client-argument=--capture-pattern \
  --backend "$build/capture-stage/usr/NextSpace/libexec/nextspace-wayland/portal/xdg-desktop-portal-wlr" \
  --native-chooser --supervisor "$build/compositor/nextspace-session" \
  --workspace-probe "$build/fixture/obj/ShellConnectionProbe" --lock-probe "$build/compositor/lock-probe" \
  --pasteboard-server "$build/back/Tools/obj/gpbs-wayland" \
  --portal-configuration "$repo/OS/Linux/usr/share/xdg-desktop-portal/nextspace-portals.conf" \
  --artifacts "$build/results/portal"
python3 "$repo/Tests/Wayland/greeter_profile.py" --compositor "$build/compositor/nextspace-compositor" \
  --supervisor "$build/compositor/nextspace-session" \
  --helper "$build/apps/Workspace/obj/nextspace-display-profile" \
  --application "$build/apps/Login/Login.app/Login" --artifacts "$build/results/greeter-profile"
# Login remains unprivileged even though the disposable build runner is root.
# The UI fixture owns its temporary account and synthetic root IPC peer.
systemkit_library=$(find /usr/NextSpace/Frameworks/SystemKit.framework -name libSystemKit.so.0.3 -type f)
test -n "$systemkit_library"
for density in 120 150 180 210 240; do
  python3 "$repo/Tests/Wayland/login_greeter.py" --compositor "$build/compositor/nextspace-compositor" \
    --application "$build/apps/Login/Login.app/Login" --systemkit "$systemkit_library" \
    --extended --scale "$density" --artifacts "$build/results/login-greeter-$density"
done
python3 "$repo/Tests/Wayland/login_greeter.py" --compositor "$build/compositor/nextspace-compositor" \
  --application "$build/apps/Login/Login.app/Login" --systemkit "$systemkit_library" \
  --deadline --artifacts "$build/results/login-greeter-deadline"
python3 "$repo/Tests/Wayland/login_greeter.py" --compositor "$build/compositor/nextspace-compositor" \
  --application "$build/apps/Login/Login.app/Login" --systemkit "$systemkit_library" \
  --failure --artifacts "$build/results/login-greeter-failure"
# Preferences discovers modules through the normal application search paths.
(cd "$build/apps/Preferences"; stage Preferences-install make install)
# Each disposable run owns a live system bus. A leftover socket from a stopped
# container is not evidence that the daemon is still available.
bus_runtime=$(mktemp -d /tmp/nextspace-system-bus.XXXXXX)
chmod 755 "$bus_runtime"
bus_pid=$(dbus-daemon --system --fork --nopidfile --address="unix:path=$bus_runtime/bus" --print-pid=1)
trap 'kill "$bus_pid" 2>/dev/null || :; rm -rf "$bus_runtime"' EXIT
export DBUS_SYSTEM_BUS_ADDRESS="unix:path=$bus_runtime/bus"
python3 "$repo/Tests/Wayland/integration.py" --compositor "$build/compositor/nextspace-compositor" \
  --probe "$build/fixture/obj/WaylandProbe" --registry-probe "$build/compositor/registry-probe" \
  --pasteboard-probe "$build/fixture/obj/PasteboardProbe" --pasteboard-server "$build/back/Tools/obj/gpbs-wayland" \
  --terminal "$build/apps/Terminal/Terminal.app/Terminal" --textedit "$build/apps/TextEdit/TextEdit.app/TextEdit" \
  --review "$build/apps/Review/Review.app/Review" \
  --review-probe "$build/fixture/obj/WorkspaceProbe" \
  --timemon "$build/apps/TimeMon/TimeMon.app/TimeMon" \
  --artifacts "$build/results/applications"
python3 "$repo/Tests/Wayland/printing_textedit.py" --compositor "$build/compositor/nextspace-compositor" \
  --textedit "$build/apps/TextEdit/TextEdit.app/TextEdit" --probe "$build/fixture/obj/WorkspaceProbe" \
  --pasteboard-server "$build/back/Tools/obj/gpbs-wayland" --pasteboard-probe "$build/fixture/obj/PasteboardProbe" \
  --artifacts "$build/results/printing-textedit"
python3 "$repo/Tests/Wayland/workspace.py" --compositor "$build/compositor/nextspace-compositor" \
  --workspace "$build/apps/Workspace/Workspace.app/Workspace" --probe "$build/fixture/obj/WorkspaceProbe" \
  --display-probe "$build/fixture/obj/DisplayModelProbe" \
  --alert-probe "$build/fixture/obj/AlertProbe" \
  --preferences "$build/apps/Preferences/Preferences.app/Preferences" \
  --openup "$build/apps/OpenUp/OpenUp.app/OpenUp" \
  --client "$build/compositor/gtk-probe" --gui-probe "$build/fixture/obj/WaylandProbe" \
  --artifacts "$build/results/workspace"
python3 "$repo/Tests/Wayland/text_input.py" --compositor "$build/compositor/nextspace-compositor" \
  --probe "$build/compositor/registry-probe" --terminal "$build/apps/Terminal/Terminal.app/Terminal" \
  --pasteboard-probe "$build/fixture/obj/PasteboardProbe" --pasteboard-server "$build/back/Tools/obj/gpbs-wayland" \
  --workspace-probe "$build/fixture/obj/WorkspaceProbe" --artifacts "$build/results/text-input-terminal"
python3 "$repo/Tests/Wayland/fcitx5.py" --compositor "$build/compositor/nextspace-compositor" \
  --probe "$build/fixture/obj/WaylandProbe" --nested \
  --terminal "$build/apps/Terminal/Terminal.app/Terminal" --workspace-probe "$build/fixture/obj/WorkspaceProbe" \
  --artifacts "$build/results/fcitx5-terminal"
python3 "$repo/Tests/Wayland/fcitx5.py" --compositor "$build/compositor/nextspace-compositor" \
  --probe "$build/fixture/obj/WaylandProbe" --nested --engine hangul --replace-selection --no-wire-trace \
  --terminal "$build/apps/Terminal/Terminal.app/Terminal" --workspace-probe "$build/fixture/obj/WorkspaceProbe" \
  --artifacts "$build/results/fcitx5-hangul-terminal"
