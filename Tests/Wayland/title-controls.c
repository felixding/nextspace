/* Render the compositor's production title paths without a display server. */
#include <stdlib.h>
#include "title-controls.h"

int main(int argc, char **argv)
{
  if (argc != 6) return 2;
  const struct decoration_glyph *glyphs[] = {
    &common_close, &common_closeh, &common_closebroken, &common_closebrokenh,
    &common_miniaturize, &common_miniaturizeh};
  int index = atoi(argv[1]), scale = atoi(argv[2]), x = atoi(argv[3]), y = atoi(argv[4]);
  if (index < 0 || index > 5 || scale < 120 || scale > 960) return 2;
  cairo_surface_t *surface = cairo_image_surface_create(CAIRO_FORMAT_ARGB32,
    ns_scale_edge(12, scale), ns_scale_edge(12, scale));
  cairo_surface_set_device_offset(surface, -ns_scale_edge(x, scale), -ns_scale_edge(y, scale));
  cairo_t *cr = cairo_create(surface);
  decoration_draw_glyph(cr, glyphs[index], x, y, scale);
  cairo_status_t status = cairo_status(cr);
  if (status == CAIRO_STATUS_SUCCESS) status = cairo_surface_write_to_png(surface, argv[5]);
  cairo_destroy(cr);
  cairo_surface_destroy(surface);
  return status == CAIRO_STATUS_SUCCESS ? 0 : 1;
}
