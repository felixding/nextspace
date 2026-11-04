#!/bin/sh
# Reusable clean consumer; cold build/source replay artifacts are immutable.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
output=$(CDPATH= cd -- "$1" && pwd)
first=$2
second=$3
name=${4:-nextspace-desktop-consumer-$$}
test ! -e "$output/lifecycle" || { echo 'Use a new lifecycle result directory.' >&2; exit 1; }
cleanup()
{
  status=$?
  if [ "$status" = 0 ]; then docker rm "$name" >/dev/null
  else echo "Retained disposable consumer $name for diagnosis." >&2; fi
}
trap cleanup EXIT
docker create --init --name "$name" -v "$repo:/src:ro" -v "$output:/results" \
  -e NEXTSPACE_PACKAGE_TEST_DISPOSABLE=1 -e FIRST="$first" -e SECOND="$second" \
  debian:trixie-slim@sha256:62bd423aeee912639ca8ee681c2b762cb3e25137e0a92b20be455898a9f034ad sh -c '
    set -eu
    apt-get update > /results/consumer-tools.log 2>&1
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      python3 python3-pil python3-dbus python3-gi dbus procps gdb librsvg2-bin poppler-utils ghostscript \
      fcitx5=5.1.12-2 fcitx5-pinyin=5.1.8-1 fcitx5-hangul=5.1.6-1 >> /results/consumer-tools.log 2>&1
    python3 /src/Tests/Wayland/package_source.py --extract-only \
      --archive "/results/packages/nextspace-desktop_$FIRST.source.tar.gz" \
      --receipt "/results/packages/nextspace-desktop_$FIRST.json" \
      --work-dir /opt/nextspace-desktop-validation --version "$FIRST" > /results/consumer-source.log 2>&1
    python3 /opt/nextspace-desktop-validation/nextspace/Tests/Wayland/desktop_lifecycle.py \
      --receipts "/results/packages/nextspace-desktop_$FIRST.json" \
        "/results/replay/packages/nextspace-desktop_$SECOND.json" \
      --probes /results/probes/bin --artifacts /results/lifecycle > /results/lifecycle.log 2>&1
    dpkg-query -W > /results/consumer-package-versions.txt
  ' >/dev/null
docker inspect "$name" > "$output/consumer-container.json"
consumer_status=0
docker start -a "$name" || consumer_status=$?
docker inspect "$name" > "$output/consumer-container-finished.json"
exit "$consumer_status"
