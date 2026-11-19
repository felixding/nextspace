#!/bin/sh
set -eu

vm_support_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
vm_home="$HOME/Downloads/nextspace-lima"
vm_instance="$vm_home/nextspace-gui"
vm_lima="$vm_support_dir/NEXTSPACE Preview.app/Contents/MacOS/limactl"

if [ "$(uname -m)" != arm64 ]; then
  echo 'This ARM64 virtual machine requires an Apple Silicon Mac and a native Terminal.' >&2
  exit 1
fi
if [ ! -f "$vm_instance/disk" ]; then
  echo "Put the copied VM disk at: $vm_instance/disk" >&2
  exit 1
fi

mkdir -p "$vm_home/_config"
chmod 700 "$vm_home" "$vm_home/_config" "$vm_instance"
for vm_name in lima.yaml vz-efi vz-identifier cidata.iso lima-version; do
  if [ ! -e "$vm_instance/$vm_name" ]; then
    cp -p "$vm_support_dir/vm-state/nextspace-gui/$vm_name" "$vm_instance/$vm_name"
  fi
done
for vm_name in user user.pub; do
  if [ -e "$vm_home/_config/$vm_name" ]; then
    if ! cmp -s "$vm_support_dir/vm-state/_config/$vm_name" "$vm_home/_config/$vm_name"; then
      echo "Existing guest SSH identity differs: $vm_home/_config/$vm_name" >&2
      echo 'It has been preserved. Ask for help before replacing it.' >&2
      exit 1
    fi
  else
    cp -p "$vm_support_dir/vm-state/_config/$vm_name" "$vm_home/_config/$vm_name"
  fi
done
chmod 600 "$vm_home/_config/user"

vm_expected=$(cat "$vm_support_dir/VM-DISK.sha256")
if [ ! -f "$vm_instance/.preview-disk-verified" ] ||
   [ "$(cat "$vm_instance/.preview-disk-verified")" != "$vm_expected" ]; then
  echo 'Checking the copied VM disk before its first start. This may take a few minutes.'
  if ! (cd "$vm_instance" && shasum -a 256 -c "$vm_support_dir/VM-DISK.sha256"); then
    echo 'The disk does not match the stopped source VM. Nothing has been started.' >&2
    exit 1
  fi
  printf '%s\n' "$vm_expected" > "$vm_instance/.preview-disk-verified"
fi

export LIMA_HOME="$vm_home"
vm_mount="$vm_support_dir/project"
case "$vm_mount" in
  *'"'*|*'\'*) echo 'Use a support-folder path without quotes or backslashes.' >&2; exit 1 ;;
esac
# Apply the approved one-time NEXTSPACE disk expansion.
/bin/sh "$vm_support_dir/project/Tests/Lima/preview-capacity.sh" "$vm_lima" "$vm_instance"

# Reuse a running preview VM; configuration edits require a stopped VM.
vm_state=$("$vm_lima" list --format '{{.Status}}' nextspace-gui)
case "$vm_state" in
  Running) ;;
  Stopped)
    "$vm_lima" --tty=false edit nextspace-gui --set ".mounts = [{\"location\": \"$vm_mount\", \"mountPoint\": \"/workspace\", \"writable\": false}] | .user.name = \"felixding\" | .user.uid = 501 | .user.home = \"/home/felixding.guest\" | .ssh.localPort = 0"
    "$vm_lima" --tty=false start nextspace-gui
    ;;
  *) echo "VM is not ready for the preview: $vm_state" >&2; exit 1 ;;
esac

echo 'Starting the desktop and both browsers. Keep this terminal open.'
echo 'Press Ctrl+C here when you want to end the preview.'
exec "$vm_lima" shell --workdir / nextspace-gui \
  sudo -n /usr/bin/setpriv --reuid=501 --regid=44 --init-groups --reset-env -- \
  python3 /workspace/.build/native-ui/macbook-preview.py
