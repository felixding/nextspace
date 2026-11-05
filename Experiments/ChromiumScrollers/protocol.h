/* Experimental native UI transport. GPL-2.0-or-later. */
#ifndef NXS_CHROMIUM_PROTOCOL_H
#define NXS_CHROMIUM_PROTOCOL_H
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
 * Model/origin acceptance uses part 3.x. No menu metrics live in the wire. */
struct NXSControlPopupRequest {
  uint32_t magic,operation,process,kind;
  uint64_t control;
  uint32_t text_size,reserved,count;
  int32_t selected;
};
#endif
