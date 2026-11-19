#!/bin/sh
# User-approved, one-time expansion of the existing NEXTSPACE preview disk.
# Uses only the bundled Lima CLI and standard macOS tools; no host Python needed.
set -eu
umask 077
vm_lima=${1:?Pass the bundled limactl path}
vm_instance=$(CDPATH= cd -- "${2:?Pass the existing preview instance}" && pwd -P)
if [ "${vm_instance##*/}" != nextspace-gui ] ||
   [ "$(stat -f %u "$vm_instance")" != "$(id -u)" ]; then
  echo 'Only the owned nextspace-gui preview instance can be expanded.' >&2
  exit 1
fi
vm_disk="$vm_instance/disk"
vm_config="$vm_instance/lima.yaml"
for vm_file in "$vm_disk" "$vm_config"; do
  if [ -L "$vm_file" ] || [ ! -f "$vm_file" ]; then
    echo 'The preview disk and configuration must be ordinary files.' >&2
    exit 1
  fi
done
vm_bytes=$(stat -f %z "$vm_disk")
case "$vm_bytes" in ''|*[!0-9]*) echo 'Invalid preview disk size.' >&2; exit 1 ;; esac
if [ "$vm_bytes" -le 0 ]; then echo 'The preview disk is empty.' >&2; exit 1; fi
vm_target=30064771072 # 28 GiB; never increase beyond this approved target.
if [ "$vm_bytes" -ge "$vm_target" ]; then
  exit 0
fi
if [ "$(od -An -tx1 -N4 "$vm_disk" | tr -d ' \n')" = 514649fb ]; then
  echo 'This repair requires the original raw VZ preview disk.' >&2
  exit 1
fi
export LIMA_HOME=${vm_instance%/*}
vm_type=$("$vm_lima" list --format '{{.VMType}}' nextspace-gui)
vm_dir=$("$vm_lima" list --format '{{.Dir}}' nextspace-gui)
if [ "$vm_type" != vz ] || [ "$(CDPATH= cd -- "$vm_dir" && pwd -P)" != "$vm_instance" ]; then
  echo 'The Lima instance identity differs from the NEXTSPACE preview.' >&2
  exit 1
fi
vm_configured=$("$vm_lima" list --format '{{.Disk}}' nextspace-gui)
case "$vm_configured" in ''|*[!0-9]*) echo 'Invalid configured preview disk size.' >&2; exit 1 ;; esac
# Preserve an existing larger configuration, including an interrupted restart.
vm_desired=$vm_target
if [ "$vm_configured" -gt "$vm_desired" ]; then vm_desired=$vm_configured; fi
vm_free_kib=$(LC_ALL=C df -kP "$vm_instance" | awk 'NR == 2 {print $4}')
case "$vm_free_kib" in ''|*[!0-9]*) echo 'Cannot measure Mac free space.' >&2; exit 1 ;; esac
vm_required=$((vm_desired - vm_bytes + 2147483648))
if [ "$((vm_free_kib * 1024))" -lt "$vm_required" ]; then
  echo "Preview disk expansion requires $((vm_required / 1048576)) MiB free on this Mac; $((vm_free_kib / 1024)) MiB is available. The VM was not changed." >&2
  exit 1
fi
vm_identity=$(stat -f '%d:%i:%z' "$vm_disk")
vm_uuid=$(shasum -a 256 "$vm_instance/vz-identifier")
vm_state=$("$vm_lima" list --format '{{.Status}}' nextspace-gui)
case "$vm_state" in
  Running) "$vm_lima" stop nextspace-gui ;;
  Stopped) ;;
  *) echo "VM is not ready for disk expansion: $vm_state" >&2; exit 1 ;;
esac
if [ "$("$vm_lima" list --format '{{.Status}}' nextspace-gui)" != Stopped ] ||
   [ "$(stat -f '%d:%i:%z' "$vm_disk")" != "$vm_identity" ]; then
  echo 'The preview VM did not stop cleanly; no disk edit was attempted.' >&2
  exit 1
fi
if [ "$vm_configured" -lt "$vm_target" ]; then
  vm_backup="$vm_instance/lima.yaml.before-preview-disk-growth"
  if [ -e "$vm_backup" ] || [ -L "$vm_backup" ]; then
    if [ -L "$vm_backup" ] || ! cmp -s "$vm_backup" "$vm_config"; then
      echo 'The previous configuration backup differs; it was preserved.' >&2
      exit 1
    fi
  else
    (set -C; cat "$vm_config" > "$vm_backup")
  fi
  echo 'Preparing the approved NEXTSPACE VM disk expansion to 28 GiB…'
  "$vm_lima" --tty=false edit nextspace-gui --disk 28
  if [ "$("$vm_lima" list --format '{{.Disk}}' nextspace-gui)" != "$vm_target" ]; then
    echo 'Lima did not retain the requested disk capacity. The VM remains stopped.' >&2
    exit 1
  fi
fi
if [ "$(stat -f '%d:%i:%z' "$vm_disk")" != "$vm_identity" ] ||
   [ "$(shasum -a 256 "$vm_instance/vz-identifier")" != "$vm_uuid" ]; then
  echo 'The preview disk or identity changed unexpectedly before startup.' >&2
  exit 1
fi
echo 'The existing preview disk will expand on the next normal VM start.'
