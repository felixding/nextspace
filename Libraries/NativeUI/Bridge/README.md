# Shared engine bridge support

This directory contains the Linux transport and ARM64 instruction adapter
machinery shared by the Chromium and Firefox experiments. It contains no
native control implementations and has no GNUstep, GTK or Qt dependency.
Actual control drawing, metrics and input stay in the separate NativeUI
provider and its underlying UI library.

`Protocol.h` preserves the existing request/reply layouts, including their
historical Chromium-prefixed constant names. The old experimental `protocol.h`
is a forwarding include. `Transport.inc` supplies the same fork-aware identities,
process-shared robust mutex, sequence matching, descriptor transfer and bounded
RPC as the original Chromium adapter. `AArch64Detours.inc` supplies its guarded
instruction relocation and hook installation. Consumers supply their binary
base, memory-protection operation and log function.

These are internal source includes, not a stable engine plugin ABI. Every
consumer must audit its own binary, signatures, layouts and lifecycle. Sharing
this machinery does not establish coverage for another engine or browser build.
The existing Chromium control suite passed all 261 checks after the extraction;
the first Firefox binding is documented in
[`Experiments/FirefoxNativeUI`](../../../Experiments/FirefoxNativeUI).
