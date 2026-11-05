/* Experimental transport to the existing NSScroller bridge. GPL-2.0-or-later. */
#ifndef NXS_CHROMIUM_PROTOCOL_H
#define NXS_CHROMIUM_PROTOCOL_H
#include <stdint.h>
#define NXS_CHROMIUM_MAGIC 0x4e585343u
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
#endif
