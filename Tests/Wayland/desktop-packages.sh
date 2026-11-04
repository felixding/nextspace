#!/bin/sh
# Host-side cold build, offline source replay and clean Debian lifecycle checks.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
output=${1:-$repo/.build/desktop-packages}
image=${2:-nextspace-native-stack-test}
mkdir "$output"
output=$(CDPATH= cd -- "$output" && pwd)
name=nextspace-desktop-packages-$$
echo "Desktop package containers: $name"
first=${NEXTSPACE_DESKTOP_VERSION_FIRST:-0.1.0~ci1}
second=${NEXTSPACE_DESKTOP_VERSION_SECOND:-0.1.0~ci2}
architecture=$(docker run --rm "$image" dpkg --print-architecture)
docker image inspect "$image" > "$output/builder-image.json"
cleanup()
{
  status=$?
  if [ "$status" != 0 ]; then
    echo "Retained failed or unfinished containers with prefix $name for diagnosis." >&2
  fi
}
trap cleanup EXIT

start_container()
{
  container_status=0
  docker start -a "$1" || container_status=$?
  docker inspect "$1" > "$output/$2-container-finished.json"
  return "$container_status"
}

docker create --init --name "$name-build" -v "$repo:/src:ro" -v "$output:/results" \
  -e NEXTSPACE_DESKTOP_BUILD_DISPOSABLE=1 -e JOBS="${JOBS:-4}" -e VERSION="$first" "$image" sh -c '
    set -eu
    trap '\''find /opt/nextspace-desktop -name "*.log" -print0 | tar --null -T - -czf /results/build-logs.tar.gz 2>/dev/null || :'\'' EXIT
    python3 /src/Tests/Wayland/source_links.py --repo /src --artifacts /results/source-links
    python3 /src/Packaging/Debian/build-desktop.py --repo /src --build-dir /opt/nextspace-desktop \
      --output /results/packages --version "$VERSION" > /results/build.log 2>&1
    sh /opt/nextspace-desktop/source/Tests/Wayland/desktop-probes.sh /results/probes
    python3 - <<"PY"
import json,shutil
from pathlib import Path
receipt=next(Path("/results/packages").glob("nextspace-wayland-compositor_*.json"))
root=Path(json.loads(receipt.read_text())["build"])
for name in ("registry-probe", "lock-probe", "capture-probe", "decoration-probe", "shell-probe"):
    shutil.copy2(root/"build"/name, Path("/results/probes/bin")/name)
PY
    dpkg-query -W > /results/builder-package-versions.txt
  ' >/dev/null
docker inspect "$name-build" > "$output/build-container.json"
start_container "$name-build" build
docker rm "$name-build" >/dev/null

docker create --init --network none --name "$name-replay" -v "$repo:/src:ro" -v "$output:/results" \
  -e NEXTSPACE_DESKTOP_BUILD_DISPOSABLE=1 -e JOBS="${JOBS:-4}" -e FIRST="$first" -e VERSION="$second" "$image" sh -c '
    set -eu
    trap '\''find /opt/nextspace-replay -name "*.log" -print0 | tar --null -T - -czf /results/replay-logs.tar.gz 2>/dev/null || :'\'' EXIT
    python3 /src/Tests/Wayland/package_source.py --desktop \
      --archive "/results/packages/nextspace-desktop_$FIRST.source.tar.gz" \
      --receipt "/results/packages/nextspace-desktop_$FIRST.json" \
      --work-dir /opt/nextspace-replay --version "$VERSION" > /results/replay.log 2>&1
    mkdir /results/replay
    cp -R /opt/nextspace-replay/packages /results/replay/
    cp /opt/nextspace-replay/results.json /results/replay/
  ' >/dev/null
docker inspect "$name-replay" > "$output/replay-container.json"
start_container "$name-replay" replay
docker rm "$name-replay" >/dev/null

sh "$repo/Tests/Wayland/desktop-consumer.sh" "$output" "$first" "$second" "$name-consumer"

echo "Complete desktop package qualification: PASS ($architecture)"
