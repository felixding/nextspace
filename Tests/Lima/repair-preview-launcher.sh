#!/bin/sh
# Repair the existing preview launcher without replacing unrelated local edits.
set -eu
launcher=${1:?Pass the existing Start.command path}
marker='# Reuse a running preview VM; configuration edits require a stopped VM.'
capacity_marker='# Apply the approved one-time NEXTSPACE disk expansion.'
capacity_command='/bin/sh "$vm_support_dir/project/Tests/Lima/preview-capacity.sh" "$vm_lima" "$vm_instance"'
if grep -Fqx "$capacity_marker" "$launcher"; then
  if ! grep -Fqx "$marker" "$launcher" || ! grep -Fqx "$capacity_command" "$launcher"; then
    echo 'The preview capacity launch block was modified; it was preserved.' >&2
    exit 1
  fi
  /bin/sh -n "$launcher"
  exit 0
fi
pending=$(mktemp "$launcher.nextspace.XXXXXX")
scratch=$(mktemp "$launcher.nextspace.XXXXXX")
cleanup() { rm -f "$pending" "$scratch"; }
trap cleanup EXIT HUP INT TERM
cp -p "$launcher" "$pending"
if ! grep -Fqx "$marker" "$launcher"; then
  awk '
  /^"\$vm_lima" --tty=false edit nextspace-gui --set / {
    if (changed++) exit 1
    edit = $0
    if (getline <= 0 || $0 != "\"$vm_lima\" --tty=false start nextspace-gui") exit 1
    print "# Reuse a running preview VM; configuration edits require a stopped VM."
    print "vm_state=$(\"$vm_lima\" list --format '\''{{.Status}}'\'' nextspace-gui)"
    print "case \"$vm_state\" in"
    print "  Running) ;;"
    print "  Stopped)"
    print "    " edit
    print "    \"$vm_lima\" --tty=false start nextspace-gui"
    print "    ;;"
    print "  *) echo \"VM is not ready for the preview: $vm_state\" >&2; exit 1 ;;"
    print "esac"
    next
  }
  { print }
  END { if (changed != 1) exit 1 }
' "$launcher" > "$scratch" || {
  echo 'The existing preview launcher has an unrecognized launch block; it was preserved.' >&2
  exit 1
}
  cat "$scratch" > "$pending"
fi
awk -v marker="$marker" -v capacity_marker="$capacity_marker" -v capacity_command="$capacity_command" '
  $0 == marker {
    if (changed++) exit 1
    print capacity_marker
    print capacity_command
    print ""
  }
  { print }
  END { if (changed != 1) exit 1 }
' "$pending" > "$scratch" || {
  echo 'The existing preview launcher has an unrecognized launch block; it was preserved.' >&2
  exit 1
}
cat "$scratch" > "$pending"
/bin/sh -n "$pending"
mv -f "$pending" "$launcher"
rm -f "$scratch"
trap - EXIT HUP INT TERM
