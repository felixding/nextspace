/* Shared native UI transport. GPL-2.0-or-later. */
#ifndef NXS_NATIVE_UI_BRIDGE_PROTOCOL_H
#define NXS_NATIVE_UI_BRIDGE_PROTOCOL_H
#include <stdint.h>
#define NXS_CHROMIUM_MAGIC 0x4e585343u
#define NXS_CHROMIUM_CONTROL_MAGIC 0x4e585549u
struct NXSRequest {
  uint32_t magic, operation, process, layer;
  uint64_t control;
  int32_t horizontal, reserved;
  double length, total, page, value;
};
struct NXSRectD { double x,y,width,height; };
struct NXSResponse {
  uint32_t magic, size;
  int32_t width,height,stride,reserved;
  struct NXSRectD parts[7];
};
/* Generic native-control transport. UTF-8 title bytes follow this header.
 * The leading control/sequence fields share the scrollbar envelope.
 * Operations: 1 configure/draw, 2 press, 3 move, 4 release, 5 poll, 6 destroy,
 * 9 native event/invalidation poll for this process (no widget required).
 * Response part 0: value, tracking, action count, state. Part 1: preferred size.
 * Part 4: process invalidation generation, next native delay (seconds or -1),
 * event capabilities. Bootstrap part 4.height advertises event capabilities.
 * Payloads above 64 KiB arrive in a sealed memfd via SCM_RIGHTS; size still
 * describes the header plus pixels. Small payloads remain inline. */
struct NXSControlRequest {
  uint32_t magic, operation, process, kind;
  uint64_t control;
  uint32_t text_size, reserved;
  double width, height, minimum, maximum, value, x, y;
  int32_t enabled, state, indeterminate;
  uint32_t modifiers;
};
/* Optional input extension, advertised by bootstrap part 4.width.
 * Operations 7 focus, 8 key. UTF-8 text then unmodified text follow this
 * header. Response part 3: input result, focused, supported capabilities.
 * Key/type/modifier values are the public NativeUI C ABI values. */
struct NXSControlInputRequest {
  uint32_t magic, operation, process, kind;
  uint64_t control;
  uint32_t text_size, reserved;
  uint32_t type, modifiers, key, repeat, unmodified_size;
  int32_t focused;
};
/* Optional operation 10: slider data quantum. Bootstrap part 5.width and
 * generic response part 5.width advertise range capabilities; part 5.x is
 * the configured quantum. The original 104-byte request stays unchanged. */
struct NXSControlStepRequest {
  uint32_t magic,operation,process,kind;
  uint64_t control;
  uint32_t text_size,reserved;
  double step;
};
/* Optional popup operation 11: item model. Each following item is two uint32s
 * (enabled/separator flags, UTF-8 byte length), then that many title bytes.
 * text_size covers the entire item payload. Existing request layouts remain.
 * Bootstrap part 6.width / generic part 5.height advertise popup capabilities.
 * Generic part 5.y reports native highlight; part 6 reports the native menu
 * frame. Operation 12 uses the ordinary request's x as item index and returns
 * that item's native rectangle in part 6. Operation 13 sets screen origin x/y.
 * Bootstrap part 6.height advertises explicit open/close operation 14, using
 * the ordinary request's state as the desired visibility.
 * Model/origin/open acceptance uses part 3.x. No menu metrics live in the wire. */
struct NXSControlPopupRequest {
  uint32_t magic,operation,process,kind;
  uint64_t control;
  uint32_t text_size,reserved,count;
  int32_t selected;
};
/* Optional text editing, bootstrap part 6.y. Operation 17 synchronizes a
 * UTF-8 value and native UTF-16 selection, without emitting a user edit.
 * Operation 18 uses the ordinary request and returns NXSTextResponse followed
 * by text_size UTF-8 bytes, with no bitmap and no terminating NUL. Never log
 * text payloads. Existing focus/key/input operations also apply to kinds 7/8.
 * Generic part 2.width/height report text edit/activation counts respectively.
 * UINT64_MAX leaves selection to the native editor (or denotes no range). */
struct NXSControlTextRequest {
  uint32_t magic,operation,process,kind;
  uint64_t control;
  uint32_t text_size,reserved;
  uint64_t selection_start,selection_length;
  int32_t editable;
  uint32_t padding;
};
struct NXSTextResponse {
  uint32_t text_size,flags; /* flags: editing=1, editable=2, secure=4 */
  uint64_t selection_start,selection_length,marked_start,marked_length;
};
/* Optional operation 21 (NXS_TEXT_COMMAND): ordinary text-control request,
 * part 3.x accepts it and its payload is the last actual native command
 * selector as UTF8 without NUL, possibly empty. No binding table is sent. */
/* Optional operation 22: native mouse press with click count in state, using
 * the original 104-byte request. Bootstrap part 5.x advertises pointer
 * capabilities independently of focus/keyboard. Part 3.x accepts the request;
 * move/release remain operations 3/4. Counts are supplied event metadata; no
 * click aggregation or word-selection rules live in the transport. */
/* Optional pre-edit channel. Operation 19 registers one AF_UNIX SEQPACKET
 * endpoint for a process with an existing operation-15 owner subscription.
 * Operation 20 unregisters it. Both use the ordinary request (kind/control 0).
 * Bootstrap text capabilities include NXS_TEXT_FILTER when supported.
 * While a native edit is on the stack, the helper sends this proposal on the
 * dedicated endpoint; the owner answers before the actual native mutation.
 * Existing requests may be serviced recursively while the owner validates an
 * edit. No editing/key-binding algorithms or text diagnostics live here. */
#define NXS_NATIVE_TEXT_EDIT_MAGIC 0x4e585445u
struct NXSNativeTextEdit {
  uint32_t magic,size,process,kind;
  uint64_t control,serial,range_start,range_length,selection_start,selection_length;
  uint32_t text_size,command_size;
};
struct NXSNativeTextDecision {
  uint32_t magic,accepted;
  uint64_t serial;
};
/* Optional operation 23 enables application command validation/execution on
 * the existing owner callback channel; state=0 disables it. Bootstrap part
 * 5.y advertises support separately from the unchanged text capability bits.
 * phase and signed result use the public NativeUI command contract. */
#define NXS_NATIVE_COMMAND_MAGIC 0x4e58434du
struct NXSNativeCommand {
  uint32_t magic,size,process,kind;
  uint64_t control,serial;
  uint32_t phase,command_size;
};
struct NXSNativeCommandDecision {
  uint32_t magic;
  int32_t result;
  uint64_t serial;
};
/* Optional menu transport, bootstrap part 5.height: bit 1 models, bit 2 shared
 * shell-selected application keys, bit 4 model key queries. Operations 24 enable/
 * disable menu callbacks on the existing owner endpoint; 25 replace menu data,
 * 26 show/hide (state), 27 key (ControlInputRequest), 28 state (item index in
 * state), 29 destroy, 30 cancel. Menu kind is zero, control is a nonzero ID.
 * A model request is followed by title_size UTF8 bytes, then count wire items,
 * each followed by title_size and key_size UTF8 bytes. text_size covers all
 * payload bytes. No NULs, native pointers, geometry or widget code cross IPC. */
/* Operation 27 with a nonzero control preserves focused=0 legacy execution;
 * focused=-1 queries, focused=1 executes with input-owner checks. With control
 * zero, the shared shell-selected role instead uses focused=0 query/1 execute. */
struct NXSMenuModelRequest {
  uint32_t magic,operation,process,kind;
  uint64_t control;
  uint32_t text_size,reserved,count,title_size;
};
struct NXSMenuWireItem {
  int32_t parent;
  uint32_t flags;
  uint64_t command;
  uint32_t modifiers,title_size,key_size,reserved;
};
#define NXS_NATIVE_MENU_COMMAND_MAGIC 0x4e584d43u
#define NXS_NATIVE_MENU_ACK_MAGIC 0x4e584d41u
struct NXSNativeMenuCommand {
  uint32_t magic,size,process,phase;
  uint64_t control,serial,command;
};
struct NXSNativeMenuAck {
  uint32_t magic,request_sequence;
  uint64_t serial;
};
/* Before running a menu callback, acknowledge its serial and the owner's
 * pending RPC sequence (zero when idle). The helper defers that RPC's reply
 * while nested requests run. Operation 31 resumes this reply after callback
 * completion, including endpoint removal/replacement; it is one-way and uses
 * control=callback serial. It never contributes an unsolicited shared reply. */
/* Menu decisions use the same 16-byte envelope, with result zero or one.
 * Response part 0: action count/tracking; parts 1/2: native menu/item frame;
 * part 3: acceptance, visibility, enabled, native highlight respectively. */
/* Menu bootstrap capability bit 2 additionally permits operation 27 with
 * kind/control zero for the shell-selected application menu. focused=0 queries
 * native matching without executing; focused=1 dispatches the key. The helper
 * requires the live notification owner's connection/kernel PID and active
 * browser ancestry. No model registration or window selection is granted. */
/* Optional invalidation notifications, bootstrap part 6.x. Operation 15 uses
 * the ordinary 104-byte control request (kind/control zero, value = last seen
 * process generation) and one SCM_RIGHTS nonblocking eventfd. Operation 16
 * unregisters it. The helper uses kernel SCM_CREDENTIALS and pidfd readiness
 * to release an active subscription if its sender dies without unregistering.
 * Part 3.x reports acceptance. Native invalidations make this
 * descriptor readable; the renderer then queries operation 9 and schedules
 * its own UI thread. No widget timer or unsolicited shared-channel reply. */
#endif
