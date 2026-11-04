#!/bin/bash
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
bundle_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export LIMA_HOME="${NEXTSPACE_LIMA_HOME:-$HOME/.lima-nextspace}"
instance=nextspace
if [ -x "$bundle_dir/Runtime/bin/limactl" ]; then
  limactl="$bundle_dir/Runtime/bin/limactl"
else
  limactl=$(command -v limactl) || {
    echo "Lima was not found. Install or update Lima, then open Launch NEXTSPACE.command again."
    exit 1
  }
fi
version_text=$("$limactl" --version)
version=${version_text##* }
if [[ ! "$version" =~ ^v?([0-9]+)\.([0-9]+)\.([0-9]+)$ ]] ||
   ! (( 10#${BASH_REMATCH[1]:-0} > 2 ||
        (10#${BASH_REMATCH[1]:-0} == 2 && 10#${BASH_REMATCH[2]:-0} > 2) ||
        (10#${BASH_REMATCH[1]:-0} == 2 && 10#${BASH_REMATCH[2]:-0} == 2 && 10#${BASH_REMATCH[3]:-0} >= 1) )); then
  echo "NEXTSPACE requires Lima 2.2.1 or newer; found $version_text."
  echo "Run: brew update && brew upgrade lima"
  echo "Then open Launch NEXTSPACE.command again."
  exit 1
fi
if [ "$(uname -m)" != arm64 ]; then
  echo "This VM requires an Apple Silicon Mac."
  exit 1
fi
if [ "${1:-start}" = stop ]; then
  exec "$limactl" --tty=false stop "$instance"
fi
if [ "${1:-start}" != start ] && [ "${1:-start}" != password ]; then
  echo "Usage: nextspace.sh [start|stop|password]"
  exit 1
fi
if [ ! -d "$LIMA_HOME/$instance" ]; then
  mkdir -p "$LIMA_HOME"
  chmod 700 "$LIMA_HOME"
  import_dir=$(mktemp -d "$LIMA_HOME/.nextspace-import.XXXXXXXX")
  trap 'rm -rf -- "$import_dir"' EXIT
  echo "Importing the NEXTSPACE VM."
  if ! /bin/cp -c "$bundle_dir/Seed/disk" "$import_dir/disk" 2>/dev/null; then
    echo "Copying the sparse disk; this can take a few minutes."
    /usr/bin/tar -cf - -C "$bundle_dir/Seed" disk | /usr/bin/tar -xf - -C "$import_dir"
  fi
  for name in lima.yaml lima-version vz-efi; do
    /bin/cp "$bundle_dir/Seed/$name" "$import_dir/$name"
  done
  : > "$import_dir/vz-identifier"
  : > "$import_dir/nextspace-macbook-v1"
  mv "$import_dir" "$LIMA_HOME/$instance"
  trap - EXIT
elif [ ! -f "$LIMA_HOME/$instance/nextspace-macbook-v1" ]; then
  echo "An unrelated VM already exists at $LIMA_HOME/$instance. No files were changed."
  exit 1
fi
cd "$HOME"
echo "Starting NEXTSPACE. First-time password setup happens in this macOS Terminal window."
"$limactl" --tty=false start "$instance"
password_state=$("$limactl" shell --workdir /home/felixding.guest "$instance" sudo -n passwd -S nextspace | awk '{print $2}')
if [ "${1:-start}" = password ] || [ "$password_state" != P ]; then
  echo
  echo "Choose a Linux password for the NEXTSPACE account nextspace."
  echo "It can differ from your Mac password. Typing will be hidden."
  "$limactl" shell --workdir /home/felixding.guest "$instance" sudo -n passwd nextspace
fi
"$limactl" shell --workdir /home/felixding.guest "$instance" sudo -n systemctl enable --now greetd
echo
echo "NEXTSPACE is running in the Lima window. Log in as nextspace."
echo "Use Stop NEXTSPACE.command for a clean shutdown."
