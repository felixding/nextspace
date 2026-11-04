#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
protocols="$root/Source/wayland/protocols"
out="$root/Source/wayland/generated"
mkdir -p "$out"
for protocol in xdg-shell xdg-decoration-unstable-v1 wlr-layer-shell fractional-scale-v1 viewporter xdg-output-unstable-v1 xdg-activation-v1 primary-selection-unstable-v1 text-input-unstable-v3 nextspace-application-v1; do
  case "$protocol" in
    wlr-layer-shell) xml=wlr-layer-shell-unstable-v1.xml ;;
    *) xml=$protocol.xml ;;
  esac
  "${WAYLAND_SCANNER:-wayland-scanner}" client-header "$protocols/$xml" "$out/$protocol-client-protocol.h"
  "${WAYLAND_SCANNER:-wayland-scanner}" private-code "$protocols/$xml" "$out/$protocol-protocol.c"
done
