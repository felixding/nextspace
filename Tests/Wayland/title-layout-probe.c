/* Exercise the compositor's actual logical title layout. MIT license. */
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include "../../Applications/Compositor/src/title-text.h"

int main(int argc, char **argv)
{
  if (argc < 4 || argc > 7) return 2;
  int density = atoi(argv[1]), available = atoi(argv[2]);
  if (density < 1 || available < 0) return 2;
  cairo_surface_t *surface = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, 1602, 46);
  cairo_t *cr = cairo_create(surface);
  cairo_scale(cr, density / 120.0, density / 120.0);
  PangoLayout *layout = title_text_layout(cr, argv[3], available,
    argc == 7 ? argv[6] : "Helvetica Bold 12px", argc >= 6 && atoi(argv[5]), NULL, NULL);
  if (argc >= 5 && *argv[4]) {
    cairo_set_source_rgb(cr, 0, 0, 0);
    cairo_paint(cr);
    cairo_set_source_rgb(cr, 1, 1, 1);
    cairo_move_to(cr, 1, 1);
    title_text_draw(cr, layout);
    if (cairo_surface_write_to_png(surface, argv[4]) != CAIRO_STATUS_SUCCESS) return 3;
  }
  int width, height;
  title_text_size(layout, &width, &height);
  const char *text = pango_layout_get_text(layout);
  char *encoded = g_base64_encode((const guchar *)text, strlen(text));
  printf("{\"width\":%d,\"height\":%d,\"text_base64\":\"%s\"}\n", width, height, encoded);
  g_free(encoded);
  g_object_unref(layout);
  cairo_destroy(cr);
  cairo_surface_destroy(surface);
  return 0;
}
