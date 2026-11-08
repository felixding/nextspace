# Native file portal

This backend translates the standard FileChooser portal's models and results
into the shared NativeUI API. Chromium, Firefox and later GTK/Qt consumers use
the same backend; no browser is rebuilt and no file dialog is implemented in
the adapters.

`GNUstep/FilePanel.m` obtains the original `NSOpenPanel` or `NSSavePanel` from
its native factory and calls its original modal method. The installed AppKit
owns file browsing, editing, selection, drawing, validation and save overwrite
confirmation. Accessories are ordinary `NSPopUpButton`, `NSButton` and
`NSTextField` objects in that provider. Python retains application filter rules,
choice identities and D-Bus requests. It supplies no visible controls.

The standalone backend owns `org.freedesktop.impl.portal.desktop.nextspace`.
Only the unique owner of `org.freedesktop.portal.Desktop` may invoke its backend
methods. Application identity and document access remain the frontend's
responsibility. Each pending request exports the standard backend Request.Close
method. Requests are serialized; withdrawal and frontend departure cancel the
actual native panel. The bus runs on an owned GLib context. A UI-thread mailbox
uses the provider's descriptor callback in default, tracking and native modal
run-loop modes, so Close remains responsive during a panel or native alert.

External cancellation posts a native application event after changing the modal
session state: `stopModalWithCode:` alone does not wake GNUstep's pending event
peek. For nested overwrite alerts, an original deferred-perform request cancels
the parent panel after AppKit restores its modal session. That deferred request
is removed before the panel wrapper is released. No modal loop is copied.

The install rules provide the launcher, D-Bus activation service and portal
descriptor. NEXTSPACE's preferred portal configuration selects `nextspace-native`
for FileChooser while keeping the existing ScreenCast backend. A desktop using
these files still needs the regular portal frontend and Python's Gio bindings.

The owned browser fixture supports `--file-portal --hold` with a private bus,
the real portal frontend and the same GNUstep provider used by webpage controls.
`Tests/NativeUI/check-file-portal.py --fixture DIR` checks public frontend
requests and real native input. Its compositor focus operation is explicit:
cross-client parent import, reliable activation on repeated dialogs and focus
restoration are not qualified. Sandboxed document exports, multi-file gestures,
filter/choice changes, broader styles/scales and installed session activation
also need qualification. Browser file inputs' inline buttons/labels remain a
separate adapter gap. This backend does not establish full native browser form
coverage.

Reference contracts: [FileChooser backend](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.impl.portal.FileChooser.html)
and [backend Request](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.impl.portal.Request.html).
