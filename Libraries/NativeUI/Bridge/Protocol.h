/* Shared native UI transport. GPL-2.0-or-later. */
#ifndef NXS_NATIVE_UI_BRIDGE_PROTOCOL_H
#define NXS_NATIVE_UI_BRIDGE_PROTOCOL_H
#include <stdint.h>
#define NXS_CHROMIUM_MAGIC 0x4e585343u
#define NXS_CHROMIUM_CONTROL_MAGIC 0x4e585549u
#define NXS_LIST_ITEM_GEOMETRY 1u
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
/* Optional popup operation 42 uses NXSControlRequest. state=1 supplies an
 * independent UTF-8 display title (including empty); state=0 with no payload
 * restores the native selected-item title. Generic response part 1.x reports
 * its capability separately, preserving existing popup capability values.
 * Part 3.x accepts the mutation and returns the complete native bitmap.
 * The originating connection owns the request; native tracking stays native. */
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
/* Optional multiline viewport (text capability 16), kind 9. Ordinary request
 * 32 reads native document/clip geometry; 33 scrolls to x/y through native
 * clipping. Part 3.x reports acceptance, part 5 is the actual visible rect,
 * and part 6.width/height is native document size. No control layout or
 * scrolling rules are implemented by this protocol. */
/* Optional tabs, bootstrap part 4.x / generic part 2.y, kind 10. Operation 36
 * replaces an owned model; each wire item is followed by UTF8 title/tooltip
 * bytes, with no NULs. The requested scale is the native bitmap density, not
 * a logical layout scale. Operation 37 uses the ordinary request and returns
 * NXSTabWireState as its payload. Operation 38 returns the named item's cached
 * native rectangle in part 6. Other tab replies use part 6 for content geometry,
 * part 5.y for item count, and ordinary part 0.x for selected index. Selected
 * IDs are uint64 throughout; they never pass through floating-point fields.
 * Model acceptance uses part 3.x. No native layout/key policy crosses IPC. */
struct NXSControlTabsRequest {
  uint32_t magic,operation,process,kind;
  uint64_t control;
  uint32_t text_size,reserved,count,padding;
  uint64_t selected;
  double scale;
};
struct NXSTabWireItem {uint64_t identifier;uint32_t title_size,tooltip_size;};
struct NXSControlTabItemRequest {
  uint32_t magic,operation,process,kind;
  uint64_t control;
  uint32_t text_size,reserved;
  uint64_t identifier;
};
struct NXSTabWireState {
  uint32_t count;
  int32_t selected_index;
  uint64_t selected;
  struct NXSRectD content;
};
/* Radio groups use kind 12. Bootstrap part 4.y / generic part 1.y advertise
 * the optional capability. Operation 43 replaces application item data,
 * preserving uint64 identities throughout. Each item is followed by UTF8
 * title bytes. Operation 44 returns NXSRadioWireState; focus/key replies also
 * carry this snapshot, so a native action and its exact targets travel together.
 * Operation 45 returns native item geometry in part 6. Operation 46 returns
 * that native cell's pixels, cropped from the original matrix bitmap using
 * its native rectangle. Ordinary press/move/release coordinates remain group
 * coordinates. No control layout, key or tracking policy crosses the wire. */
struct NXSControlRadioRequest {
  uint32_t magic,operation,process,kind;
  uint64_t control;
  uint32_t text_size,reserved,count,columns;
  uint64_t selected,key_cell;
  double scale;
};
struct NXSRadioWireItem {uint64_t identifier;uint32_t enabled,title_size;};
struct NXSControlRadioItemRequest {
  uint32_t magic,operation,process,kind;
  uint64_t control;
  uint32_t text_size,reserved;
  uint64_t identifier;
  double width,height; /* Optional application cell bounds for operation 46. */
};
/* Optional operation 47 reuses this fixed item request for semantic native
 * performClick, without invented input events. kind 1/2/3 use identifier=0;
 * kind 12 names a matrix member. Width/height/text_size must be zero; reserved retains the request sequence.
 * Bootstrap part 4.y bit 4 advertises support; part 3.x accepts the operation.
 * Matrix replies contain the existing typed radio-state payload. */
struct NXSRadioWireState {
  uint32_t count,rows,columns,reserved;
  uint64_t selected,key_cell,actions;
};
/* Flat lists use kind 13. Bootstrap part 3.x advertises list capabilities,
 * leaving all existing capability fields unchanged. Operation 48 replaces an
 * existing owned list model; each wire item is followed by title_size UTF8
 * bytes (no NULs). Scale must equal the control's actual backing density.
 * Operation 49 reads NXSListWireState followed by selected_count uint64 IDs.
 * Focus/key and list scroll/wheel replies carry the same complete snapshot.
 * Owned list replies also expose actual native backing density in part 5.y;
 * consumers need not infer it from raster bounds or hard-code a scale.
 * Operation 50 returns original native row geometry in part 6. Operation 51
 * uses NXSControlRequest x/y for native scroll position; existing operation
 * 35 delivers native wheel input. Generic configure/draw/press/move/release/
 * poll/destroy retain their original envelopes. No list behavior crosses IPC. */
struct NXSControlListRequest {
  uint32_t magic,operation,process,kind;
  uint64_t control;
  uint32_t text_size,reserved,count,flags;
  uint64_t key_cell;
  double scale;
};
struct NXSListWireItem {
  uint64_t identifier;
  uint32_t enabled,selected,title_size,reserved;
};
struct NXSControlListItemRequest {
  uint32_t magic,operation,process,kind;
  uint64_t control;
  uint32_t text_size,reserved;
  uint64_t identifier;
};
struct NXSListWireState {
  uint32_t count,selected_count,flags,reserved;
  uint64_t primary,key_cell,actions;
  struct NXSRectD visible;
  double content_width,content_height;
};
/* Bootstrap part 3.y advertises NXSScrollCapability independently of the
 * existing list capability. Owned operation 52 (NXSControlRequest, kind 9/13)
 * returns NXSScrollGeometry using the same layout as legacy text geometry.
 * Providers without the appended method advertise zero and reject the query. */
/* Bootstrap part 2.y advertises NXS_LIST_ITEM_GEOMETRY. Operation 50 retains
 * its original row rectangle in part 6 and additionally carries the existing
 * list state/selection payload from the same native dispatch. This pairs a
 * row's visible rectangle with its native viewport without another RPC.
 * Earlier rectangle-only consumers can ignore the optional payload. */
/* Bootstrap part 2.x advertises optional native item hit queries independently
 * of list/scroll capabilities. Owned operation 53 uses NXSControlRequest x/y.
 * Accepted replies (part 3.x=1) contain one uint64 model ID, zero for a native
 * non-item area, with no bitmap. No row metrics or hit rules cross IPC. */
/* Optional text capability NXS_TEXT_PLACEHOLDER (512). Owned operation 54
 * uses NXSControlRequest for kinds 7/8/14. state=1 supplies UTF8 placeholder
 * bytes (including empty); state=0 and no payload removes it. Native cells
 * own presentation. Reply part 3.x accepts the mutation, with native pixels.
 * Older providers advertise no capability and reject the request. */
/* Bootstrap part 2.width advertises NXSSpecializedCapability. Kinds 15/16/17
 * are original native stepper/color/date controls. Steppers use configure,
 * input, state and step operation 10. Owned operations 55/57 synchronize
 * color/date data; 56/58 use NXSControlRequest and return the corresponding
 * public model with no bitmap. Accepted mutations return native pixels.
 * Calendar and numeric behavior remain in the native UI library. */
struct NXSControlColorRequest {
  uint32_t magic,operation,process,kind;
  uint64_t control;
  uint32_t text_size,reserved;
  double red,green,blue,alpha;
};
struct NXSControlDateRequest {
  uint32_t magic,operation,process,kind;
  uint64_t control;
  uint32_t text_size,reserved,flags,elements,style,padding;
  double value,minimum,maximum;
};
#endif
