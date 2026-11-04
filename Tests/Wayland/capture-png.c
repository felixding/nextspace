/* Independently checked diagnostic capture channels and alpha. MIT license. */
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <cairo.h>
#include "WaylandCapture.h"

int main(int argc, char **argv)
{
  assert(argc == 4);
  int kind = atoi(argv[1]);
  cairo_surface_t *image = cairo_image_surface_create(kind ? CAIRO_FORMAT_RGB24 : CAIRO_FORMAT_ARGB32, 257, 259);
  unsigned char *data = cairo_image_surface_get_data(image);
  int stride = cairo_image_surface_get_stride(image);
  for (unsigned y = 0; y < 259; y++) {
    uint32_t *row = (uint32_t *)(data + y * stride);
    for (unsigned x = 0; x < 257; x++) {
      unsigned alpha = kind ? 255 : (x + 3*y) % 256;
      unsigned r = ((x & 255) * alpha + 128) / 256, g = ((y & 255) * alpha + 128) / 256;
      unsigned b = (((x ^ y) & 255) * alpha + 128) / 256;
      row[x] = (alpha << 24) | (r << 16) | (g << 8) | b;
    }
  }
  cairo_surface_mark_dirty(image);
  if (kind >= 2) assert(!WaylandWriteCapture(image, "/nonexistent-nextspace-capture/output.png"));
  else {
    assert(WaylandWriteCapture(image, argv[2]));
    assert(cairo_surface_write_to_png(image, argv[3]) == CAIRO_STATUS_SUCCESS);
    cairo_surface_t *decoded = cairo_image_surface_create_from_png(argv[2]);
    assert(cairo_surface_status(decoded) == CAIRO_STATUS_SUCCESS);
    assert(cairo_image_surface_get_width(decoded) == 257 && cairo_image_surface_get_height(decoded) == 259);
    cairo_surface_destroy(decoded);
  }
  cairo_surface_destroy(image);
  return 0;
}
