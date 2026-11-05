#!/bin/sh
# Apply pinned Base fixes; reject stale cached patch markers.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
target=$(CDPATH= cd -- "$1" && pwd)
mode=${2:-apply}
case "$mode" in apply|check) ;; *) exit 1 ;; esac
apply_base_patch()
{
patch_file=$1
marker="$target/.nextspace-patches/$2.sha256"
checksum=$(sha256sum "$patch_file" | cut -d ' ' -f 1)
if [ -f "$marker" ] && [ "$(cat "$marker")" != "$checksum" ]; then
  echo "Base patch changed; use a fresh Base source tree instead of $target" >&2
  exit 1
fi
cd "$target"
if ! patch --batch --force --reverse --dry-run -p1 < "$patch_file" >/dev/null 2>&1; then
  if [ "$mode" = check ] || [ -f "$marker" ] ||
      ! patch --batch --forward --dry-run -p1 < "$patch_file" >/dev/null 2>&1; then
    echo "Base patch does not match $target; use a fresh Base source tree" >&2
    exit 1
  fi
  patch --batch --forward -p1 < "$patch_file"
fi
if [ "$mode" = apply ]; then
  mkdir -p .nextspace-patches
  printf '%s\n' "$checksum" > "$marker"
fi
}
apply_base_patch "$root/base-1_31_1-notification-connect.patch" base-notification-connect
apply_base_patch "$root/base-1_31_1-message-port-lock.patch" base-message-port-lock
apply_base_patch "$root/base-1_31_1-run-loop-invalid-timers.patch" base-run-loop-invalid-timers
