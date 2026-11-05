#include <assert.h>
#include <stdio.h>
#include "nextspace-geometry.h"

int main(void)
{
  const unsigned scales[] = {120, 150, 180, 210, 240};
  const int widths[] = {801, 1001, 1202, 1402, 1602};
  const int heights[] = {601, 751, 902, 1052, 1202};
  for (unsigned i = 0; i < 5; ++i) {
    assert(ns_buffer_extent(801, scales[i]) == widths[i]);
    assert(ns_buffer_extent(601, scales[i]) == heights[i]);

  }
  /* Three adjacent unit cells at 125% occupy 1, 2 and 1 pixels. */
  assert(ns_scale_edge(0, 150) == 0);
  assert(ns_scale_edge(1, 150) == 1);
  assert(ns_scale_edge(2, 150) == 3);
  assert(ns_scale_edge(3, 150) == 4);
  assert(ns_buffer_extent(800, 180) == 1200);
  assert(ns_buffer_extent(0, 120) == 0);
  assert(ns_buffer_extent(INT_MAX, UINT32_MAX) == 0);
  assert(ns_scale_edge(-1, 180) == -2);
  struct ns_pixel_rect r = ns_buffer_damage(-1.1, 0.2, 2, 1, 150);
  assert(r.x == -2 && r.y == 0 && r.width == 4 && r.height == 2);
  assert(ns_flip_y(ns_flip_y(-300, 601, 1080), 601, 1080) == -300);
  struct ns_frame_extents frame = {1, 23, 1, 9};
  assert(ns_frame_extents_valid(frame) && ns_frame_horizontal(frame) == 2 && ns_frame_vertical(frame) == 32);
  assert(ns_frame_extents_valid((struct ns_frame_extents){0, 0, 0, 0}));
  assert(ns_frame_extents_valid((struct ns_frame_extents){128, 128, 128, 128}));
  assert(!ns_frame_extents_valid((struct ns_frame_extents){-1, 23, 1, 9}));
  assert(!ns_frame_extents_valid((struct ns_frame_extents){1, 129, 1, 9}));
  puts("scale, odd dimensions, damage and coordinate orientation: PASS");
}
