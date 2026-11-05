# Chromium native scrollbar experiment

This opt-in prototype replaces web-content scrollbars in **one unchanged Debian
ARM64 Chromium build** with the existing NEXTSPACE `NSScroller` bridge. Only the
small preload library is compiled. Chromium, GNUstep and `NSScroller` are not
rebuilt or overwritten. Closing the isolated browser removes the memory patches.
It is not enabled by the installed NEXTSPACE session.

The helper calls the unchanged `Libraries/ForeignScrollers` C interface for
geometry, drawing and synchronous native mouse tracking. Its bitmap is transported
to Chromium's paint canvas; no native artwork or tracking algorithm is copied.
Blink retains the document layout and scroll ranges, with vertical bars placed
on the left without changing text direction. Native actions are applied through
Chromium's absolute scroll-offset setter on the owning renderer thread.

The preload patches guarded ARM64 instructions and internal vtables before the
renderer sandbox starts. A preconnected socket survives the zygote boundary;
AppKit stays in the separate helper. Chromium's compositor scrollbar press
handler returns its own unhandled result so the press reaches Blink and
`NSScroller` without starting a second compositor scrollbar animation. Wheel and
content handlers are not replaced. Native tracking stops when Blink disconnects
a scrollbar, including reload during a held arrow.

## Exact supported binary

- Debian package: `chromium 156.0.8078.79-1~deb13u1`, ARM64.
- Executable SHA-256:
  `7bcc9f719bc77d34358194026b4f148a468e97e4ddc45366e6ce02c119fb9bd1`.
- GNU build ID: `eeeef03b83096958e9eb6385a4a92aa8d2aa404e`.
- Upstream commit: `a21ce95c24ce3964416f09ae1862f53f319eb4d0`.
- Matching Debian debug package SHA-256:
  `85055cc575d3828caf72ca2f45efc28c206ea6f3e00597fb7d88b65b7476ca28`.

Offsets and instruction guards were derived from that executable, its matching
Debian debug symbols and exact upstream sources. Runtime use needs neither the
debug package nor GDB/Frida. An update needs a newly audited pin; changing only
the accepted build ID or hash is insufficient. The launcher rejects other
executables. The preload leaves unsupported builds or missing-helper startup
unchanged, with a diagnostic in its log.

## Build and run

Requires Linux ARM64, Python 3.11+, Clang, an existing NEXTSPACE Wayland session,
and the existing `libnextspace-native-scroller.so.1` built by
[ForeignScrollers](../../Libraries/ForeignScrollers/README.md). Run from the
repository root, substituting paths to the matching executable and native bridge:

```sh
python3 Experiments/ChromiumScrollers/build.py --output /tmp/libnextspace-chromium-hook.so
python3 Experiments/ChromiumScrollers/run.py \
  --chromium /path/to/chromium \
  --native-library /path/to/libnextspace-native-scroller.so.1 \
  --hook /tmp/libnextspace-chromium-hook.so \
  --log-directory /tmp/nextspace-chromium-logs \
  -- file:///absolute/path/to/Experiments/ChromiumScrollers/test-page.html
```

The launcher creates a private temporary profile and socket, starts the helper,
and cleans up both processes. It retains the sandbox. It selects non-overlay
scrollbars and software rendering, matching the tested configuration. It does
not disable smooth or threaded content scrolling. `--backend NAME` optionally
selects an existing GNUstep backend for the helper alone; it does not change
user preferences. The test guest had an old user backend alias, so qualification
used a temporary alias to its installed native106 backend.

## Qualification and limits

Verified 2026-11-05 on Debian 13 ARM64, installed NEXTSPACE native106, headless
Wayland/Pixman, 100% scale and a 868×571 content viewport. The renderer retained
`Seccomp: 2`. The test used the previously built native bridge with SHA-256
`5a11964eeb514900fdd7d706b370f419543f4ebc9896bf68c9d8e560584f6042`.

Checks passed for exact native pixels at positions 0 and 700; a single arrow
step; native held-arrow repeat and release; thumb dragging outside the bar;
nested and horizontal controls; retained LTR text direction; reload during
tracking; launcher startup/cleanup; unsupported-build rejection; and
missing-helper startup. The final build's 18×553 scrollbar crop at position 0
again matched every RGB pixel of the native bridge output. See
[qualification.json](qualification.json) for the measured results.

This establishes feasibility, not general Chromium support. Physical GPU and
HiDPI operation, custom CSS scrollbars, accessibility, touch, keyboard parity,
large documents, multiple simultaneous browser instances, helper failure during
use, and performance remain unqualified. Pixel transport emits many paint
rectangles and synchronous IPC can stall rendering. A tab/helper crash or timeout
still needs stronger recovery. Default metrics currently cover the tested native
control size. This experiment changes neither browser chrome menus nor shortcut
bindings, and does not cover other Chromium versions or architectures.

Local raw evidence is under `.build/foreign-scrollbars/chromium-prototype/`:
`qualified-input-checks.json`, `qualified-native.jsonl`, `qualified-hook.log`,
`qualified-zero.png`, native references, earlier comparison screenshots and
source inputs. The stock executable and the existing native bridge passed their
hash checks afterward. Downloaded packages were extracted in a private test
folder; the guest package inventory was unchanged.
