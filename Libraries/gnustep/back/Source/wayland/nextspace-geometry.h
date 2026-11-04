/* Shared logical/buffer coordinate contract. SPDX-License-Identifier: MIT */
#ifndef NEXTSPACE_GEOMETRY_H
#define NEXTSPACE_GEOMETRY_H

#include <limits.h>
#include <math.h>
#include <stdint.h>

#define NS_SCALE_DENOMINATOR 120

struct ns_frame_extents { int left, top, right, bottom; };

static inline int ns_frame_extents_valid(struct ns_frame_extents frame)
{
  return frame.left >= 0 && frame.left <= 128 && frame.top >= 0 && frame.top <= 128 &&
    frame.right >= 0 && frame.right <= 128 && frame.bottom >= 0 && frame.bottom <= 128;
}

static inline int ns_frame_horizontal(struct ns_frame_extents frame)
{ return frame.left + frame.right; }

static inline int ns_frame_vertical(struct ns_frame_extents frame)
{ return frame.top + frame.bottom; }

/* Dimensions are positive; protocol rounding is nearest, ties away from zero. */
static inline int ns_buffer_extent(int logical, uint32_t scale)
{
  int64_t pixels = ((int64_t)logical * scale + 60) / NS_SCALE_DENOMINATOR;
  return logical > 0 && scale > 0 && pixels > 0 && pixels <= INT_MAX ? (int)pixels : 0;
}

static inline int ns_scale_edge(double logical, uint32_t scale)
{
  return (int)round(logical * scale / NS_SCALE_DENOMINATOR);
}

struct ns_pixel_rect { int x, y, width, height; };

/* Buffer damage encloses all touched pixels, including negative origins. */
static inline struct ns_pixel_rect ns_buffer_damage(double x, double y,
    double width, double height, uint32_t scale)
{
  double s = scale / 120.0;
  int left = (int)floor(x * s), top = (int)floor(y * s);
  return (struct ns_pixel_rect){left, top,
    (int)ceil((x + width) * s) - left, (int)ceil((y + height) * s) - top};
}

/* Convert one rectangle between top-left and bottom-left coordinate systems. */
static inline double ns_flip_y(double y, double height, double desktop_top)
{
  return desktop_top - y - height;
}
#endif
