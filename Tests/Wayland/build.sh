#!/bin/sh
# Build the pinned GUI, native backend and compositor in a disposable Linux tree.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
. "$repo/Tests/Wayland/copy-sources.sh"
build=${NEXTSPACE_WAYLAND_BUILD_DIR:-/tmp/nextspace-wayland-build}
mkdir -p "$build"
build=$(CDPATH= cd -- "$build" && pwd)
export NEXTSPACE_WAYLAND_BUILD_DIR="$build"
if [ -d "$build/results" ]; then
  previous_run=$(mktemp -d "$build/previous-run.XXXXXX")
  mv "$build/results" "$previous_run/results"
  if [ -f "$build/source-hashes.json" ]; then
    cp "$build/source-hashes.json" "$previous_run/source-hashes.json"
  fi
fi
python3 "$repo/Tests/Wayland/source-manifest.py" "$repo" "$build/source-hashes.json"
dpkg-query -W -f='${Package}=${Version}\n' > "$build/package-versions.txt"
set +u
. "${NEXTSPACE_GNUSTEP_SH:-/usr/share/GNUstep/Makefiles/GNUstep.sh}"
set -u

sh "$repo/Tests/Wayland/base.sh" "$build"
mkdir -p "$build/notification-fixture" "$build/results"
cp "$repo/Tests/GNUstep-GUI/GNUmakefile" "$repo/Tests/GNUstep-GUI/NotificationCenterProbe.m" "$build/notification-fixture/"
(cd "$build/notification-fixture" && make WAYLAND_TESTS=yes NotificationCenterProbe.all.tool.variables) > "$build/notification-probe-build.log" 2>&1 || {
  cat "$build/notification-probe-build.log"; exit 1;
}
"$build/notification-fixture/obj/NotificationCenterProbe" > "$build/results/notification-center.log" 2>&1 || {
  cat "$build/results/notification-center.log"; exit 1;
}

. "$repo/Packaging/Sources/native-display.sh"
copy_sources "$repo/Tests/GNUstep-GUI" "$build/fixture"
cp "$repo/Applications/Workspace/WSShellConnection.h" "$repo/Applications/Workspace/WSShellConnection.m" "$build/fixture/"
cp "$repo/Frameworks/SystemKit/OSESessionSettings.h" "$build/fixture/"
cp "$repo/Applications/Workspace/WSDockSettings.h" "$repo/Applications/Workspace/WSDockSettings.m" "$build/fixture/"
cp "$repo/Applications/Login/GreetdClient.h" "$repo/Applications/Login/GreetdClient.m" \
  "$repo/Applications/Login/LoginWindow.h" "$repo/Applications/Login/LoginWindow.m" "$build/fixture/"
(cd "$build/fixture" && make WAYLAND_TESTS=yes WORKSPACE_SHELL_TESTS=yes LOGIN_SESSION_TESTS=yes \
  NEXTSPACE_FRAMEWORKS_DIR="$repo/Frameworks" \
  NEXTSPACE_PROTOCOLS_DIR="$repo/Protocols" WaylandProbe.all.tool.variables \
  PasteboardProbe.all.tool.variables WorkspaceProbe.all.tool.variables DragProbe.all.tool.variables \
  PrintingProbe.all.tool.variables NameServerLockProbe.all.tool.variables \
  EventQueueProbe.all.tool.variables \
  ShellConnectionProbe.all.tool.variables OutputResultProbe.all.tool.variables DockSettingsProbe.all.tool.variables \
  LoginSessionProbe.all.tool.variables LoginWindowProbe.all.tool.variables) > "$build/probe-build.log" 2>&1 || {
  cat "$build/probe-build.log"; exit 1;
}
mkdir -p "$build/results/dock-settings"
python3 "$repo/Tests/Wayland/image_formats.py" --probe "$build/fixture/obj/WaylandProbe" \
  --artifacts "$build/results/image-formats"
python3 "$repo/Tests/Wayland/source_links.py" --repo "$repo" --artifacts "$build/results/source-links"
python3 "$repo/Tests/Wayland/artwork_reference.py" --probe "$build/fixture/obj/WaylandProbe" \
  --preferences --login --sound-controls --folders --root --terminal-strips --terminal-footer --recycler --textedit --timemon --artifacts "$build/results/original-artwork"
python3 "$repo/Tests/Wayland/date_fidelity.py" --artifacts "$build/results/date-fidelity"
python3 "$repo/Tests/Wayland/screen_fidelity.py" --artifacts "$build/results/screen-fidelity"
python3 "$repo/Tests/Wayland/keyboard_fidelity.py" --artifacts "$build/results/keyboard-fidelity"
python3 "$repo/Tests/Wayland/mouse_fidelity.py" --artifacts "$build/results/mouse-fidelity"
python3 "$repo/Tests/Wayland/sound_fidelity.py" --artifacts "$build/results/sound-fidelity"
python3 "$repo/Tests/Wayland/services_fidelity.py" --artifacts "$build/results/services-fidelity"
python3 "$repo/Tests/Wayland/localization_fidelity.py" --artifacts "$build/results/localization-fidelity"
python3 "$repo/Tests/Wayland/expert_fidelity.py" --artifacts "$build/results/expert-fidelity"
python3 "$repo/Tests/Wayland/sound_controls_fidelity.py" --artifacts "$build/results/sound-controls-fidelity"
python3 "$repo/Tests/Wayland/folder_fidelity.py" --artifacts "$build/results/folder-fidelity"
python3 "$repo/Tests/Wayland/monitor_screens_fidelity.py" --artifacts "$build/results/monitor-screens-fidelity"
python3 "$repo/Tests/Wayland/root_fidelity.py" --artifacts "$build/results/root-fidelity"
python3 "$repo/Tests/Wayland/document_fidelity.py" --artifacts "$build/results/document-fidelity"
python3 "$repo/Tests/Wayland/navigation_fidelity.py" --artifacts "$build/results/navigation-fidelity"
python3 "$repo/Tests/Wayland/debian_fidelity.py" --artifacts "$build/results/debian-fidelity"
python3 "$repo/Tests/Wayland/return_fidelity.py" --artifacts "$build/results/return-fidelity"
python3 "$repo/Tests/Wayland/terminal_strips_fidelity.py" --artifacts "$build/results/terminal-strips-fidelity"
python3 "$repo/Tests/Wayland/terminal_footer_fidelity.py" --artifacts "$build/results/terminal-footer-fidelity"
python3 "$repo/Tests/Wayland/textedit_fidelity.py" --artifacts "$build/results/textedit-fidelity"
python3 "$repo/Tests/Wayland/textedit_title_fidelity.py" --artifacts "$build/results/textedit-title-fidelity"
python3 "$repo/Tests/Wayland/textedit_document_fidelity.py" --artifacts "$build/results/textedit-document-fidelity"
python3 "$repo/Tests/Wayland/review_document_fidelity.py" --artifacts "$build/results/review-document-fidelity"
python3 "$repo/Tests/Wayland/review_page_fidelity.py" --artifacts "$build/results/review-page-fidelity"
python3 "$repo/Tests/Wayland/openup_fidelity.py" --artifacts "$build/results/openup-fidelity"
python3 "$repo/Tests/Wayland/openup_logo_fidelity.py" --artifacts "$build/results/openup-logo-fidelity"
python3 "$repo/Tests/Wayland/timemon_pause_fidelity.py" --artifacts "$build/results/timemon-pause-fidelity"
python3 "$repo/Tests/Wayland/timemon_static_fidelity.py" --artifacts "$build/results/timemon-static-fidelity"
if [ -d "$repo/Applications/Artwork/NeXTSpirit" ]; then
  python3 "$repo/Tests/Wayland/nextspirit.py" --pack "$repo/Applications/Artwork/NeXTSpirit" \
    --artifacts "$build/results/nextspirit-sources"
  python3 "$repo/Tests/Wayland/embedded_button_fidelity.py" \
    --artifacts "$build/results/embedded-button-fidelity"
fi
python3 "$repo/Tests/Wayland/recycler_footprint.py" --artifacts "$build/results/recycler-footprint"
python3 "$repo/Tests/Wayland/recycler_pose_fidelity.py" --artifacts "$build/results/recycler-pose-fidelity"
python3 "$repo/Tests/Wayland/folder_resources.py" --artifacts "$build/results/folder-resources"
python3 "$repo/Tests/Wayland/login_fidelity.py" --artifacts "$build/results/login-fidelity"
python3 "$repo/Tests/Wayland/theme_images.py" --probe "$build/fixture/obj/WaylandProbe" \
  --images "$build/theme/Resources/ThemeImages" --artifacts "$build/results/theme-images"
"$build/fixture/obj/OutputResultProbe" > "$build/results/output-results.log" 2>&1
"$build/fixture/obj/DockSettingsProbe" "$build/results/dock-settings"
python3 "$repo/Tests/Wayland/login_auth.py" --probe "$build/fixture/obj/LoginSessionProbe" \
  --artifacts "$build/results/login-auth"
cc -shared -fPIC "$repo/Tests/Wayland/defaults-lock-delay.c" -ldl \
  -o "$build/fixture/obj/defaults-lock-delay.so"
python3 "$repo/Tests/Wayland/pasteboard.py" --server "$build/back/Tools/obj/gpbs-wayland" \
  --probe "$build/fixture/obj/PasteboardProbe" --artifacts "$build/results/pasteboard"
python3 "$repo/Tests/Wayland/wlroots.py" "$repo" "$build" > "$build/wlroots-build.log" 2>&1 || {
  tail -60 "$build/wlroots-build.log"; exit 1;
}
wlroots_libdir=$(pkg-config --variable=libdir wlroots-0.18)
test "$(pkg-config --variable=prefix wlroots-0.18)" = /usr/local
# The distro GNUstep environment also adds its system library directory. Keep
# the qualified dependency ahead of that unpatched library at runtime.
export LD_LIBRARY_PATH="$wlroots_libdir${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
if [ ! -d "$build/compositor" ]; then
  meson setup "$build/compositor" "$repo/Applications/Compositor" -Dcomparators=true
else
  # A restored source snapshot can be older than cached generated headers.
  meson setup --wipe "$build/compositor" "$repo/Applications/Compositor" -Dcomparators=true
fi
meson compile -C "$build/compositor"
ldd "$build/compositor/nextspace-compositor" > "$build/compositor-libraries.txt"
meson test -C "$build/compositor" --print-errorlogs
python3 "$repo/Tests/Wayland/cursor_artwork.py" --theme /usr/share/icons/NextSpace \
  --compositor "$build/compositor/nextspace-compositor" --probe "$build/fixture/obj/WaylandProbe" \
  --pasteboard-server "$build/back/Tools/obj/gpbs-wayland" \
  --images "$build/theme/Resources/ThemeImages" \
  --artifacts "$build/results/cursor-artwork"
python3 "$repo/Tests/Wayland/event_queue.py" --compositor "$build/compositor/nextspace-compositor" \
  --probe "$build/fixture/obj/EventQueueProbe" --artifacts "$build/results/event-queue"
python3 "$repo/Tests/Wayland/gamma.py" --compositor "$build/compositor/nextspace-compositor" \
  --probe "$build/compositor/shell-probe" --workspace-probe "$build/fixture/obj/ShellConnectionProbe" \
  --artifacts "$build/results/gamma"
python3 "$repo/Tests/Wayland/shutdown.py" --compositor "$build/compositor/nextspace-compositor" \
  --artifacts "$build/results/shutdown"
python3 "$repo/Tests/Wayland/locked_shutdown.py" --compositor "$build/compositor/nextspace-compositor" \
  --locker "$build/compositor/lock-probe" --client "$build/compositor/gtk-probe" \
  --artifacts "$build/results/locked-shutdown"
python3 "$repo/Tests/Wayland/capture.py" --compositor "$build/compositor/nextspace-compositor" \
  --probe "$build/compositor/capture-probe" --shell-probe "$build/compositor/shell-probe" \
  --registry-probe "$build/compositor/registry-probe" --lock-probe "$build/compositor/lock-probe" \
  --client "$build/compositor/gtk-probe" --artifacts "$build/results/capture"
python3 "$repo/Tests/Wayland/session_lock.py" --compositor "$build/compositor/nextspace-compositor" \
  --probe "$build/compositor/lock-probe" --input-probe "$build/compositor/registry-probe" \
  --shell-probe "$build/compositor/shell-probe" --gui-probe "$build/fixture/obj/WaylandProbe" \
  --artifacts "$build/results/session-lock"
python3 "$repo/Tests/Wayland/session_lock.py" --compositor "$build/compositor/nextspace-compositor" \
  --probe "$build/compositor/lock-probe" --input-probe "$build/compositor/registry-probe" \
  --shell-probe "$build/compositor/shell-probe" --greeter --artifacts "$build/results/greeter-lock-requests"
python3 "$repo/Tests/Wayland/login_window.py" --compositor "$build/compositor/nextspace-compositor" \
  --probe "$build/fixture/obj/LoginWindowProbe" --image "$repo/Applications/Login/Resources/loginwindow.tiff" \
  --artifacts "$build/results/login-window"
install_root=$(mktemp -d "$build/install.XXXXXX")
# PAM/session fixtures execute these installed binaries as a disposable user.
chmod 755 "$install_root"
meson install -C "$build/compositor" --no-rebuild --destdir "$install_root"
installed_bin=$(python3 - "$install_root" <<'PY'
from pathlib import Path
import sys
paths = list(Path(sys.argv[1]).rglob('nextspace-wayland-session'))
assert len(paths) == 1 and paths[0].is_file(), paths
print(paths[0].parent)
PY
)
if [ "${NEXTSPACE_TEST_LOCK_PAM:-0}" = 1 ]; then
  python3 "$repo/Tests/Wayland/lock_pam.py" --supervisor "$installed_bin/nextspace-session" \
    --compositor "$installed_bin/nextspace-compositor" --locker "$installed_bin/nextspace-wayland-locker" \
    --disposable-container --artifacts "$build/results/session-lock-pam"
  python3 "$repo/Tests/Wayland/lock_pam.py" --supervisor "$installed_bin/nextspace-session" \
    --compositor "$installed_bin/nextspace-compositor" --locker "$installed_bin/nextspace-wayland-locker" \
    --logind-probe "$build/compositor/logind-service-probe" --disposable-container \
    --artifacts "$build/results/session-lock-logind"
fi
python3 "$repo/Tests/Wayland/title_layout.py" --probe "$build/compositor/title-layout-probe" \
  --artifacts "$build/results/title-layout"
python3 "$repo/Tests/Wayland/title_layout.py" --probe "$build/compositor/title-layout-probe" \
  --antialiased --artifacts "$build/results/title-layout-antialiased"

python3 "$repo/Tests/Wayland/title_appearance.py" --compositor "$build/compositor/nextspace-compositor" \
  --shell-probe "$build/compositor/shell-probe" --workspace-shell-probe "$build/fixture/obj/ShellConnectionProbe" \
  --gui-probe "$build/fixture/obj/WaylandProbe" --artifacts "$build/results/title-appearance"
python3 "$repo/Tests/Wayland/decorations.py" --compositor "$build/compositor/nextspace-compositor" \
  --probe "$build/compositor/decoration-probe" --shell-probe "$build/compositor/shell-probe" \
  --artifacts "$build/results/decorations"
python3 "$repo/Tests/Wayland/native_frames.py" --compositor "$build/compositor/nextspace-compositor" \
  --gui-probe "$build/fixture/obj/WaylandProbe" --application-probe "$build/fixture/obj/WorkspaceProbe" \
  --artifacts "$build/results/native-frames"
for print_profile in portrait crop landscape; do
  for print_view in flipped unflipped; do
    print_flat="$build/results/printing-$print_profile-$print_view"
    for print_tree in flat nested; do
      set -- --profile "$print_profile"
      if [ "$print_view" = unflipped ]; then set -- "$@" --unflipped; fi
      print_output="$print_flat"
      if [ "$print_tree" = nested ]; then
        set -- "$@" --nested --reference "$print_flat"
        print_output="$print_flat-nested"
      fi
      python3 "$repo/Tests/Wayland/printing.py" --compositor "$build/compositor/nextspace-compositor" \
        --probe "$build/fixture/obj/PrintingProbe" --artifacts "$print_output" \
        --pasteboard-server "$build/back/Tools/obj/gpbs-wayland" \
        --pasteboard-probe "$build/fixture/obj/PasteboardProbe" "$@"
    done
  done
done
python3 "$repo/Tests/Wayland/rectangles.py" --compositor "$build/compositor/nextspace-compositor" \
  --probe "$build/fixture/obj/WaylandProbe" --pasteboard-server "$build/back/Tools/obj/gpbs-wayland" \
  --pasteboard-probe "$build/fixture/obj/PasteboardProbe" --artifacts "$build/results/rectangles"
python3 "$repo/Tests/Wayland/native_fullscreen.py" --compositor "$build/compositor/nextspace-compositor" \
  --gui-probe "$build/fixture/obj/WaylandProbe" --application-probe "$build/fixture/obj/WorkspaceProbe" \
  --artifacts "$build/results/native-fullscreen"
python3 "$repo/Tests/Wayland/title_states.py" --compositor "$build/compositor/nextspace-compositor" \
  --gui-probe "$build/fixture/obj/WaylandProbe" --registry-probe "$build/compositor/registry-probe" \
  --artifacts "$build/results/title-states"
python3 "$repo/Tests/Wayland/title_repaint.py" --artifacts "$build/results/title-states"
python3 "$repo/Tests/Wayland/title_states.py" --compositor "$build/compositor/nextspace-compositor" \
  --gui-probe "$build/fixture/obj/WaylandProbe" --registry-probe "$build/compositor/registry-probe" \
  --transparent --artifacts "$build/results/title-states-transparent"
python3 "$repo/Tests/Wayland/title_repaint.py" --artifacts "$build/results/title-states-transparent"
python3 "$repo/Tests/Wayland/native_styles.py" --compositor "$build/compositor/nextspace-compositor" \
  --gui-probe "$build/fixture/obj/WaylandProbe" --application-probe "$build/fixture/obj/WorkspaceProbe" \
  --registry-probe "$build/compositor/registry-probe" --artifacts "$build/results/native-styles"
for window_mode in native; do
  set --
  python3 "$repo/Tests/Wayland/window_states.py" --compositor "$build/compositor/nextspace-compositor" \
    --client "$build/compositor/gtk-probe" --registry-probe "$build/compositor/registry-probe" \
    --shell-probe "$build/compositor/shell-probe" \
    --artifacts "$build/results/window-states-$window_mode" "$@"
done
python3 "$repo/Tests/Wayland/cursors.py" --compositor "$build/compositor/nextspace-compositor" \
  --probe "$build/fixture/obj/WaylandProbe" --artifacts "$build/results/cursors"
python3 "$repo/Tests/Wayland/text_input.py" --compositor "$build/compositor/nextspace-compositor" \
  --probe "$build/compositor/registry-probe" --native-probe "$build/fixture/obj/WaylandProbe" \
  --pasteboard-probe "$build/fixture/obj/PasteboardProbe" --pasteboard-server "$build/back/Tools/obj/gpbs-wayland" \
  --artifacts "$build/results/text-input"
python3 "$repo/Tests/Wayland/fcitx5.py" --compositor "$build/compositor/nextspace-compositor" \
  --probe "$build/fixture/obj/WaylandProbe" --nested --artifacts "$build/results/fcitx5"
python3 "$repo/Tests/Wayland/fcitx5.py" --compositor "$build/compositor/nextspace-compositor" \
  --probe "$build/fixture/obj/WaylandProbe" --nested --engine hangul --replace-selection --no-wire-trace \
  --artifacts "$build/results/fcitx5-hangul"
python3 "$repo/Tests/Wayland/shell.py" --compositor "$build/compositor/nextspace-compositor" \
  --shell-probe "$build/compositor/shell-probe" --registry-probe "$build/compositor/registry-probe" \
  --gui-probe "$build/fixture/obj/WaylandProbe" \
  --workspace-shell-probe "$build/fixture/obj/ShellConnectionProbe" \
  --artifacts "$build/results/shell"
python3 "$repo/Tests/Wayland/outputs.py" --compositor "$build/compositor/nextspace-compositor" \
  --shell-probe "$build/compositor/shell-probe" --registry-probe "$build/compositor/registry-probe" \
  --state-client "$build/compositor/gtk-probe" \
  --input-settings --artifacts "$build/results/outputs"
for output_mode in 0 1 2 3; do
  python3 "$repo/Tests/Wayland/outputs.py" --compositor "$build/compositor/nextspace-compositor" \
    --shell-probe "$build/compositor/shell-probe" --registry-probe "$build/compositor/registry-probe" \
    --workspace-shell-probe "$build/fixture/obj/ShellConnectionProbe" --mode "$output_mode" --input-settings \
    --state-client "$build/compositor/gtk-probe" \
    --gui-probe "$build/fixture/obj/WaylandProbe" --artifacts "$build/results/outputs-client-$output_mode"
done
set -- --compositor "$build/compositor/nextspace-compositor" \
  --client "$build/compositor/gtk-probe" --registry-probe "$build/compositor/registry-probe" \
  --native-probe "$build/fixture/obj/DragProbe" \
  --pasteboard-probe "$build/fixture/obj/PasteboardProbe" --pasteboard-server "$build/back/Tools/obj/gpbs-wayland"
python3 "$repo/Tests/Wayland/drag.py" "$@" --matrix --framed \
  --artifacts "$build/results/drag"
python3 "$repo/Tests/Wayland/drag.py" "$@" --pair native-native \
  --artifacts "$build/results/drag-borderless"

for pair in native-native gtk-native native-gtk; do
  python3 "$repo/Tests/Wayland/drag.py" "$@" --pair "$pair" --negative-origin --file-drag --framed \
    --artifacts "$build/results/drag-negative-$pair"
done
for supervisor_mode in native compositor-loss private-bus bus-loss private-bus-compositor-loss native-launcher; do
  supervisor="$build/compositor/nextspace-session"
  compositor="$build/compositor/nextspace-compositor"
  case "$supervisor_mode" in
    native) set -- ;;
    compositor-loss) set -- --compositor-loss ;;
    private-bus) set -- --private-bus ;;
    bus-loss) set -- --private-bus --bus-loss ;;
    private-bus-compositor-loss) set -- --private-bus --compositor-loss ;;
    native-launcher)
      supervisor="$installed_bin/nextspace-session"
      compositor="$installed_bin/nextspace-compositor"
      set -- --private-bus --launcher "$installed_bin/nextspace-wayland-session"
      ;;
  esac
  python3 "$repo/Tests/Wayland/supervisor.py" --supervisor "$supervisor" \
    --compositor "$compositor" --shell-probe "$build/fixture/obj/ShellConnectionProbe" \
    --client "$build/compositor/gtk-probe" --input-method-probe "$build/compositor/registry-probe" \
    --artifacts "$build/results/supervisor-$supervisor_mode" "$@"
done
for mode in native no-fractional no-viewporter no-placement surface-v1 surface-v1-no-viewporter; do
  if [ "$mode" = native ]; then
    set -- --primary-selection --server-frames --registry-probe "$build/compositor/registry-probe" \
      --pasteboard-probe "$build/fixture/obj/PasteboardProbe" --pasteboard-server "$build/back/Tools/obj/gpbs-wayland"
    set -- "$@" --gtk-probe "$build/compositor/gtk-probe" --qt-probe "$build/compositor/qt-probe"
    set -- "$@" --workspace-probe "$build/fixture/obj/WorkspaceProbe"
  else
    set --
  fi
  python3 "$repo/Tests/Wayland/integration.py" \
    --compositor "$build/compositor/nextspace-compositor" \
    --probe "$build/fixture/obj/WaylandProbe" --protocol-mode "$mode" \
    --artifacts "$build/results/$mode" "$@"
done
python3 "$repo/Tests/Wayland/foreign_compositor.py" \
  --probe "$build/fixture/obj/WaylandProbe" --artifacts "$build/results/foreign-compositor"
