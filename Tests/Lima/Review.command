#!/bin/bash
# Stable MacBook entry point for reviewing any NEXTSPACE change.
set -euo pipefail

downloads="$HOME/Downloads"
support_dir="$downloads/nextspace-preview-support"
update_dir="$downloads/nextspace-browser-controls-update"
archive_name="nextspace-browser-controls-update.tar.gz"
source_dir="home:/Users/felixding/projects/nextspace/.build/native-ui"
vm_lima="$support_dir/NEXTSPACE Preview.app/Contents/MacOS/limactl"
export LIMA_HOME="$downloads/nextspace-lima"

if [[ ! -x "$vm_lima" || ! -f "$support_dir/Start.command" ]]; then
  printf 'Existing preview installation not found at: %s\n' "$support_dir" >&2
  exit 1
fi

staging_dir=$(mktemp -d "${TMPDIR:-/tmp}/nextspace-review.XXXXXX")
cleanup() { rm -rf -- "$staging_dir"; }
trap cleanup EXIT

printf 'Downloading the latest preview update…\n'
scp "$source_dir/$archive_name" "$source_dir/$archive_name.sha256" "$staging_dir/"
(cd "$staging_dir" && shasum -a 256 -c "$archive_name.sha256")
mv -f "$staging_dir/$archive_name" "$downloads/$archive_name"
tar -xzf "$downloads/$archive_name" -C "$downloads"
(cd "$update_dir" && shasum -a 256 -c MANIFEST.sha256 >/dev/null)

vm_state=$("$vm_lima" list --format '{{.Status}}' nextspace-gui)
case "$vm_state" in
  Running)
    printf 'Closing the running preview…\n'
    "$vm_lima" shell --workdir / nextspace-gui python3 - <<'PY'
from pathlib import Path
import os
import signal
import time

def preview_identity(process):
    try:
        command = (process / 'cmdline').read_bytes()
        arguments = command.split(b'\0')
        if not any(arg.endswith(b'/.build/native-ui/macbook-preview.py') for arg in arguments):
            return None
        # Include the original start time to avoid acting on a reused PID.
        start = (process / 'stat').read_text().rsplit(')', 1)[1].split()[19]
        return command, start
    except (OSError, IndexError):
        return None

owned = {}
for process in Path('/proc').iterdir():
    if process.name.isdigit():
        identity = preview_identity(process)
        if identity is not None:
            owned[int(process.name)] = identity
for pid, identity in owned.items():
    if preview_identity(Path('/proc') / str(pid)) == identity:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
deadline = time.monotonic() + 60
while any(preview_identity(Path('/proc') / str(pid)) == identity
          for pid, identity in owned.items()):
    if time.monotonic() >= deadline:
        raise SystemExit('The preview is still closing. Wait, then run Review.command again.')
    time.sleep(.1)
PY
    ;;
  Stopped) ;;
  *) printf 'VM is not ready for an update: %s\n' "$vm_state" >&2; exit 1 ;;
esac

printf 'Installing the preview update…\n'
bash "$update_dir/Update.command" "$support_dir"
cleanup
trap - EXIT
printf 'Launching the preview. Press Ctrl+C here to end it.\n'
exec /bin/bash "$support_dir/Start.command"
