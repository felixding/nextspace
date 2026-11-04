# Pinned wlroots changes

The manifest records the upstream 0.18.2 archive and each patch checksum. The
disposable source runner verifies all inputs, applies these changes to a separate
tree and records its file hashes. The compositor retains wlroots' single XWM and
selection bridge.

- `wlroots-0.18.2-xdnd-mime.patch` advertises literal MIME atoms for XDND. GTK 4
  rejected offers containing only the clipboard aliases `TEXT` and `UTF8_STRING`.
  Clipboard conversion keeps those aliases.
- `wlroots-0.18.2-xdnd-completion.patch` preserves the negotiated operation after
  dropping, validates the final operation, cancels failed/closed receivers, ignores
  duplicate completion, handles source-less drags and avoids signed coordinate
  shifting. The native source previously received no successful operation even
  though the receiver obtained its text.
- `wlroots-0.18.2-incoming-xdnd.patch` adds X11 drag sources to that same bridge.
  It reuses the selection transfer and native drag machinery, preserves the X
  source's pointer grab, validates XDND peer messages and bounds release/drop
  waits. The compositor forwards logical pointer positions and excludes X11 drag
  icons from input. Incoming runtime qualification is in progress.

The GTK/native/Xwayland cases in `Tests/Wayland/drag.py` are the reproducers and
regression checks. These fixes should be submitted upstream with those cases;
remove a local patch only after a replacement release passes them. No upstream
submission or broader Xwayland DND qualification is claimed here.
