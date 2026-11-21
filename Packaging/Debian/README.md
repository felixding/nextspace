# Debian native Wayland desktop

The current target is native Wayland on Debian 13 ARM64. `build-desktop.py` produces
three packages: `nextspace-runtime`, `nextspace-session-wayland` and
`nextspace-wayland-compositor`. It builds the pinned toolkit, frameworks and
eight applications through the shared helpers in `Packaging/Sources`.
Native Workspace excludes the embedded Window Maker. The pinned wlroots build
disables Xwayland and the X11 backend; no X11 session package is produced.

CI uses native `ubuntu-24.04-arm` runners. Build the two disposable test images
and run the qualification from an ARM64 Docker host:

```sh
docker build -f Tests/Wayland/Dockerfile -t nextspace-wayland-test .
docker build -f Tests/Wayland/Dockerfile.native-stack -t nextspace-native-stack-test .
sh Tests/Wayland/desktop-packages.sh .build/desktop-package-results
```

The runner cold-builds the desktop, replays its source archive without networking
and checks a fresh Debian consumer with no X server installed. It verifies exact
package payloads, native application and Workspace workflows, saved-profile
Login, live toolkit/compositor upgrade, retained configuration and removal.
`desktop-consumer.sh` can repeat the clean consumer using existing build/replay
artifacts. The native7/native8 cold build, offline source replay and complete
clean-consumer lifecycle pass, with an independent host evidence audit.
The newer native9/native10 cohort also passes those checks with the fractional
UI pixel-grid fix and strict Terminal full-frame repaint assertion: 3,823 identical
offline inputs, six packages and 94 frozen validation sources pass archive audit.
New runs build their probes from the cold build's source snapshot and run their
lifecycle checks from its verified source archive. Ongoing checkout edits do not
change the validation cohort. The shared extractor checks both the archive hash
and every input against the receipt before using it.

Source manifests record SHA-256 values for regular files and `link:<target>` for
literal symlink targets. Both recipes preserve links during snapshots, and replay
checks their type and target as well as regular-file contents. The source-link
fixture protects all 57 cursor alias chains and rejects changes that preserve
resolved cursor bytes while changing the original links. Earlier regular-file
source archives remain readable. The fixture also executes the original-artwork
check from the compositor's isolated source selection, which includes the shared
SVG renderer and stock GNUstep image archive required by its tests.

The installed ARM64 greeter/PAM/virtual-seat and native workflow results are
recorded in [the current status](../../docs/Wayland-Implementation-Status.md).
Physical hardware and unrestricted artwork redistribution remain release gates;
Intel/AMD qualification is deferred while ARM development continues.

Each build writes packages, a source archive and JSON receipts with input,
payload and package hashes. The source archive contains the pinned upstream
archives, local patches, build tools, protocols and assets. Extract it and run
its `Packaging/Debian/build-desktop.py` in a fresh disposable root builder with
`NEXTSPACE_DESKTOP_BUILD_DISPOSABLE=1`, a new `--build-dir`, `--output` and
`--version`. Build dependencies must already be installed; bundled dependency
archives are reused and Meson downloads are disabled. These are repeatable source
builds, not a claim of bit-for-bit package reproducibility.

`build-wayland.py` also builds the compositor/supervisor component separately,
including its launchers and private checksum-pinned wlroots library under
`/usr/NextSpace/lib/nextspace-wayland`. This component recipe works as an ordinary
user with the dependencies from `Tests/Wayland/Dockerfile` and `dpkg-dev`:

```sh
python3 Packaging/Debian/build-wayland.py \
  --build-dir .build/debian-wayland --output .build/debian-packages \
  --version '0.1.0~local1'
```

The component alone does not provide the backend, applications or
`nextspace-display-profile` helper required by the default greeter launcher.
Earlier `packages.sh` X11-reference results are historical evidence and are
outside the current delivery scope. Installing these packages does not enable
or replace the host display manager.

## Toshy shortcut compatibility

```sh
python3 Packaging/Debian/build-toshy.py \
  --build-dir .build/debian-toshy --output .build/debian-packages \
  --cache .build/source-cache --version '26.11.0~nextspace1'
```

The recipe pins Toshy `Toshy_v26.11.0` at
`c76b5ec702e188a793c542e940d4e066d838c654`. The source archive SHA-256 is
`6a87d489ad8b19d3b21faa1e68e94139b8d9c8f95fa722cad292d45dd675d441`.
Its stable bundled xwaykeyz comes from
`3895ab4c5f29f6415cdfc66b4ad53b76db2fb090`. The same checks apply when the
archive is supplied in the cache for an offline build. Refresh the tag,
revision, checksum and bundled revision together in the recipe and here.
Rebuild and rerun the shortcut acceptance checks before publishing.

The optional package uses the current session supervisor and compositor. See
[Toshy keyboard shortcuts](../../docs/Toshy-Keyboard-Shortcuts.md) for the
session setting and per-app overrides.
