#!/bin/sh
# Qualify the unchanged default build in the disposable NEXTSPACE runtime.
set -eu
test -f /.dockerenv || { echo 'Run inside the disposable Docker test image.' >&2; exit 1; }
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
. "$repo/Tests/Wayland/copy-sources.sh"
build=${NEXTSPACE_WAYLAND_BUILD_DIR:-/tmp/nextspace-native-stack}
copy_sources "$repo/Libraries/gnustep/back" "$build/back-x11"
(
  cd "$build/back-x11"
  autoreconf -fi
  ./configure --enable-server=x11 --enable-graphics=cairo --with-name=x11
  make -j"${JOBS:-4}"
  make install
) > "$build/x11-backend-build.log" 2>&1 || { tail -60 "$build/x11-backend-build.log"; exit 1; }
copy_sources "$repo/Applications/Workspace" "$build/apps/Workspace-X11"
(
  cd "$build/apps/Workspace-X11"
  make -j"${JOBS:-4}" NEXTSPACE_BUILD_WAYLAND=0
) > "$build/x11-workspace-build.log" 2>&1 || { tail -60 "$build/x11-workspace-build.log"; exit 1; }
workspace="$build/apps/Workspace-X11/Workspace.app/Workspace"
ldd "$workspace" > "$build/x11-workspace-libraries.txt"
python3 - "$build/x11-workspace-libraries.txt" <<'PY'
from pathlib import Path
import sys
assert 'libwayland' not in Path(sys.argv[1]).read_text(), 'Default Workspace depends on Wayland'
PY
profile="$build/nextspace-x11-profile"
mkdir -p "$profile" "$build/results/x11-workspace"
if id nextspace-x11 >/dev/null 2>&1; then
  echo 'Reserved X11 test account already exists.' >&2; exit 1
fi
useradd --no-create-home --home-dir "$profile" nextspace-x11
cleanup_x11_user()
{
  pkill -TERM -u nextspace-x11 2>/dev/null || :
  sleep 0.2
  pkill -KILL -u nextspace-x11 2>/dev/null || :
  userdel nextspace-x11
}
trap cleanup_x11_user EXIT
chown nextspace-x11 "$profile" "$build/results/x11-workspace"
python3 "$repo/Tests/Wayland/x11-workspace.py" --workspace "$workspace" \
  --probe "$build/fixture/obj/WorkspaceProbe" --user nextspace-x11 \
  --textedit "$build/apps/TextEdit/TextEdit.app/TextEdit" \
  --review "$build/apps/Review/Review.app/Review" \
  --printing-probe "$build/fixture/obj/PrintingProbe" --artifacts "$build/results/x11-workspace"
