# NEXTSPACE review and testing

Use this same workflow whenever the user reviews or tests any NEXTSPACE change.
The paths and commands stay the same across features and revisions. Replace the
archive at the source path with each qualified update. The historical browser
wording in its filename does not limit the preview to browser work.

The user-requested automation script is the stable entry point for this process.
Copy it to the MacBook once:

```sh
scp home:/Users/felixding/projects/nextspace/Tests/Lima/Review.command ~/Downloads/Review.command
```

For every subsequent review or test, run:

```sh
bash ~/Downloads/Review.command
```

It downloads and verifies the update, gracefully closes the current preview,
applies the existing installer, and runs the existing Start.command in the same
Terminal. It leaves the VM disk in place. Keep this script path unchanged.

The updater also repairs the existing `Start.command` launch block. A running
`nextspace-gui` instance is reused directly; configuration edits and VM startup
run only when it is stopped. Updating the launcher preserves its other contents,
the VM disk and its existing identity.

The underlying manual steps remain available:

Close the running preview with Ctrl+C in its Terminal. On the MacBook, run:

```sh
scp home:/Users/felixding/projects/nextspace/.build/native-ui/nextspace-browser-controls-update.tar.gz ~/Downloads/
tar -xzf ~/Downloads/nextspace-browser-controls-update.tar.gz -C ~/Downloads
bash ~/Downloads/nextspace-browser-controls-update/Update.command
```

Then run the existing `~/Downloads/nextspace-preview-support/Start.command`.

The support folder stays at `~/Downloads/nextspace-preview-support`. The existing
VM stays at `~/Downloads/nextspace-lima/nextspace-gui`. Ordinary updates reuse
that VM disk and the existing preview app and launcher.

Before starting the desktop, the launcher checks space inside the VM for the
runtime, private browser resources and profile growth. If needed, it removes
only closed previews' disposable profiles/caches and verified unused runtime
copies. Live sessions, the current runtime, evidence and uncertain files stay
intact. If space remains insufficient, it stops before launching the desktop
and reports the available and required space. The review command stays the same.
The cleaner recognizes the original, intermediate and current shipped teardown
receipt formats. Older receipts do not need fields introduced by later
launchers. Every accepted format still requires completed process exits and no
live references; incomplete or unknown receipts remain protected.

The approved capacity repair expands the existing 24GiB preview disk to 28GiB
on its next normal start. Before stopping or editing the VM, it checks for 6GiB
of free space on the Mac. It preserves the existing disk, identity and data,
backs up the configuration, and leaves disks already 28GiB or larger unchanged.
This runs once through the same review command; it requires no host Python.

The runtime installer verifies every shipped file before use. A damaged cached
installation is preserved while a complete replacement is copied, flushed and
verified in a separate directory. The replacement is published only after
verification and is reused on later launches. A bad source update or interrupted
copy cannot become the active runtime. No VM disk or browser profile is replaced.

Internal build names and runtime hashes are implementation details. They do
not change these user-facing paths or commands.

## Before offering a review

The agent completes regression testing; the user reviews the experience. For
each candidate, first use the real preview window through its ordinary launcher.
Observe each result while selecting, editing, scrolling, resizing, zooming,
opening, cancelling and reopening controls. Click the actual caption again
while its panel is open, including near screen edges. Use the display density
that reproduced the report; nearby scale values are not equivalent. Record
visible defects before running scripted checks. Passing fixtures cannot replace
this desktop review.

Minimize each browser and restore it through its actual application icon, then
repeat the control interactions. Also check that activating an application with
an open window leaves its other minimized windows minimized.

For browser control changes, `Tests/Lima/check-preview-desktop.py` runs fresh ordinary
desktop sessions at 100%, 125%, 150%, 175% and 200% inside the review VM, using the same preview helper
and delivery runtime. It exercises real seat input without setting focus for the
interaction assertions, then verifies the mapped runtime against its manifest.
Startup, interaction and payload failures keep its result incomplete. Preserve
the receipts and inspect the resulting screenshots before refreshing the existing
archive. Isolated native API checks complement this gate; they do not replace it.
Repeated colour/calendar keyboard opening after switching apps is part of this
gate at every scale. Retention, current parent ownership and the single current
app menu must pass without focus overrides or changed key sequences.
