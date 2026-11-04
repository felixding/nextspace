#!/bin/sh
# Keep Linux path case, private modes and literal fixture links in CI artifacts.
set -eu
if [ "$#" -ne 3 ]; then
  echo "Usage: collect-artifacts.sh RESULTS ARCHIVE native|desktop" >&2
  exit 2
fi
[ -d "$1" ] || exit 0
results=$(CDPATH= cd -- "$1" && pwd)
archive=$2
case "$3" in
  native)
    (
      cd "$results"
      for member in *.log package-versions.txt native-runtime.txt native-stack-sources.json \
        source-hashes.json wlroots-source-hashes.json compositor-libraries.txt results; do
        if [ -e "$member" ] || [ -L "$member" ]; then
          printf '%s\0' "$member"
        fi
      done
    ) | tar -czf "$archive" -C "$results" --null -T -
    ;;
  desktop) tar -czf "$archive" -C "$results" . ;;
  *) echo "Unknown result set: $3" >&2; exit 2 ;;
esac
chmod 644 "$archive"
