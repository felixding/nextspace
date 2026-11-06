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

The optional text transport advertises capabilities in bootstrap part 6.y.
Kinds 7/8 are native text/password fields. Operation 17 transfers UTF-8 model
data, editability and UTF-16 selection; operation 18 reads the real editor value
and ranges using the explicit `NXSTextResponse` payload. Focus and key requests
reuse operations 7/8, and native changes/Return are counted separately in generic
part 2.width/height. Existing message layouts stay unchanged. Text payloads are
excluded from diagnostics. This is an editor transport foundation; browser
engine/frontend model and input adapters remain to implement.

The optional pre-edit extension uses operations 19/20 and a separate Unix
SEQPACKET channel, bound to the existing process owner subscription. Actual
native replacement proposals and interpreted selectors travel on that channel;
the owner returns a decision before the native editor changes its value. The
shared transport permits nested and cross-process requests during validation,
and reacquires normal reply ownership before sending the decision. Peer loss
or the current two-second deadline vetoes the edit. Late decisions are drained
after frame removal, without a custom widget timer. Text payloads remain absent
from logs. Browser transaction adapters are still required.

Optional operation 23 enables/disables application command callbacks on that
same registered channel, using the ordinary request's state. Bootstrap part
5.y advertises this independently of existing text/input/pointer capabilities.
The existing kernel-owned subscription and callback endpoint must belong to the
same client/PID. `NXSNativeCommand` carries a native selector and validation or
execution phase; its 16-byte decision has a signed -1/0/1 result. The shared
RPC path preserves reentrant requests and reply ownership. Missing/expired
decisions reject the action, and late command replies are drained after frame
removal. A valid older command reply is also drained by serial when a newer
edit decision is pending. The channel supplies no key bindings, controller algorithms or widget
implementation. Existing edit messages and decision layouts remain unchanged.

The callback endpoint belongs to the UI thread that registered it. Background
invalidation polling shares the request socket but leaves command/edit packets
queued for that owner. Only the owner may replace callbacks or unregister the
endpoint; it can still unregister after peer loss. A thread-local ownership
marker prevents workers from consulting or consuming the callback descriptor,
and the process identity check retains fork recovery. Nested RPCs still release
and reacquire the shared request mutex around the owner's callback.
`native-command-thread-probe` tests validation, execution and pre-edit delivery
while worker requests are outstanding, plus rejected worker registration and
unregistration. The preceding transport executes all three callbacks on the
worker; the current transport executes them on the registering thread.
See [ownership qualification](../command-thread-qualification.json).

The command filter also remains usable without application menus. Detached
menu binding and idle command dispatch use the additional model transport and
owner-loop integration in the browser adapters.

The optional menu-model transport now also supports authenticated key queries.
Bootstrap part 5.height is a bit mask: 1 models, 2 shell-selected application
keys, 4 model-key queries. For operation 27 with a nonzero model ID,
`focused=-1` queries and `focused=1` executes; legacy `focused=0` still executes.
With model ID zero, the separate shell-selected role retains its existing
`focused=0` query / `focused=1` execution convention. Both use the same key
serializer. Queries call the native provider's `NSMenu` matching with action
actuation suppressed. They add no shortcut table. A shell-selected host also
requires current input ownership; both paths authenticate the controlling
connection and sender's lifetime. See the browser application-menu bindings
for current startup, focus and idle command integration.

In supervised sessions, generation metadata in response part 4.x also carries
the host epoch in its upper 32 bits. Callback serials start above that epoch's
floor. The transport observes newer epochs and drops older nonzero-epoch edit,
command and menu proposals before invoking an application handler. Legacy
standalone epoch-zero peers retain their existing behavior. Chromium's queued
menu UI tasks also check the captured epoch before executing. This rejects
stale work; it does not replay an interrupted action. The supervisor retains
the original socket/callback capabilities, so sandboxed renderers need no new
socket connection. See the [session host](../Host/README.md).

These are internal source includes, not a stable engine plugin ABI. Every
consumer must audit its own binary, signatures, layouts and lifecycle. Sharing
this machinery does not establish coverage for another engine or browser build.
The existing Chromium control suite passed all 261 checks after the extraction;
the first Firefox binding is documented in
[`Experiments/FirefoxNativeUI`](../../../Experiments/FirefoxNativeUI).
