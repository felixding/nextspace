#!/bin/sh
# Apply the pinned GUI series once and reject a stale cached patch set.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
target=$(CDPATH= cd -- "$1" && pwd)
wayland=${2:-0}
case "$wayland" in 0|1) ;; *) exit 1 ;; esac
cd "$target"
mkdir -p .nextspace-patches
for series in common wayland; do
  if [ "$series" = wayland ] && [ "$wayland" != 1 ]; then continue; fi
  while IFS= read -r source; do
    [ -n "$source" ] || continue
    patch_file="$root/$source"
    marker=".nextspace-patches/$(basename "$source").sha256"
    checksum=$(sha256sum "$patch_file" | cut -d ' ' -f 1)
    if [ -f "$marker" ]; then
      if [ "$(cat "$marker")" != "$checksum" ]; then
        echo "GUI patch set changed; use a fresh GUI source tree instead of $target" >&2
        exit 1
      fi
      if ! patch --batch --force --reverse --dry-run -p1 < "$patch_file" >/dev/null 2>&1; then
        echo "GUI patch marker does not match the source: $source; use a fresh GUI source tree" >&2
        exit 1
      fi
      continue
    fi
    # Adopt an already applied, identical series without reversing local sources.
    if ! patch --batch --force --reverse --dry-run -p1 < "$patch_file" >/dev/null 2>&1; then
      if ! patch --batch --forward --dry-run -p1 < "$patch_file" >/dev/null 2>&1; then
        echo "GUI patch does not match $target: $source; use a fresh GUI source tree" >&2
        exit 1
      fi
      patch --batch --forward -p1 < "$patch_file"
    fi
    printf '%s\n' "$checksum" > "$marker"
  done < "$root/patches/gui-0_32_0-$series.series"
done
