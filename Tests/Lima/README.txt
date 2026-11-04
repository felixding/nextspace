Optional Lima development/test preview

These helpers are for local VM development and testing. Lima is not included
in the NEXTSPACE Linux desktop packages. The bundled runtime in the MacBook
preview is a workaround for the tested Homebrew Lima 2.1.4 startup crash.

NEXTSPACE native Wayland preview for Apple Silicon

Open Launch NEXTSPACE.command. On first launch, choose a Linux password.
In the Lima window, log in as nextspace with that password.
Open Stop NEXTSPACE.command to shut down cleanly.

Includes the tested Lima 2.2.1 runtime for Apple Silicon. UTM and an ISO are not needed.
Debian 13 ARM64, NEXTSPACE native106, 2 CPUs, 2 GiB RAM, 24 GiB sparse disk.
The desktop starts at 2560 x 1600 with 200% scaling. Display settings can be
changed in Preferences. Use the Lima window's zoom control to fit the display.

The VM runs locally. No Screen Sharing or Mac mini connection is used after
transfer. No Mac folders are mounted. Your VM and its files live in
~/.lima-nextspace; your other Lima/UTM VMs are not modified.
The Seed folder is an initial cold copy; later changes live in the running VM.
Keep the launcher folder wherever convenient. It never overwrites an imported VM.

The helper account felixding is the existing Lima guest administrator; the
desktop account is nextspace. Lima generates its SSH identity on your Mac.
No Mac mini controller private key is included.

Personal preview only. Artwork redistribution clearance and physical GPU/60Hz
qualification remain pending. The guest uses the validated software renderer.

First-launch notes:
The launcher uses Runtime/bin/limactl. Your installed Lima version is unchanged.
The Linux password prompt is in macOS Terminal after the VM boots. Return to Terminal
if the Lima window covers it. To choose or reset it explicitly, open
Set NEXTSPACE Password.command. Enter the new password twice in macOS Terminal;
typing stays invisible. Then log in as nextspace in the Lima window.
The password helper uses the same bundled Lima runtime as the launcher.

Maintainers: this directory holds the reusable launcher sources. Copy them into
a portable bundle containing the stopped, mount-free Seed and the supported
Runtime. VM preparation records and the verified cold seed are retained locally
under .build/wayland-macbook/v1; generated disks and controller credentials stay
out of Git. The three .command files share nextspace.sh.

The tested Runtime is the official Lima 2.2.1 Darwin arm64 distribution.
Preserve Runtime/bin/limactl, Runtime/share/lima/lima-guestagent.Linux-aarch64.gz
and Runtime/share/doc/lima/LICENSE. The tested binary SHA-256 is
6d32fb0f880c0ea750434f2ac855a3f2129126752a301ce4d88adbd2fa599e1e;
the native guest-agent SHA-256 is
ed41b146a0aa9fb5e75d4b42d7af40c9ffb2cafadf4d8685762599e1960a72d7.

Developer sudo access:
The preview root password is locked. In macOS Terminal, use the installed
limactl or the bundle Runtime/bin/limactl to add the desktop account to sudo:
LIMA_HOME="$HOME/.lima-nextspace" limactl shell --workdir /home/felixding.guest nextspace sudo -n usermod -aG sudo nextspace
Then log out of NEXTSPACE and back in; sudo uses the nextspace password.
