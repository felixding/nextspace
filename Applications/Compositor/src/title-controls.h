/* Shared SVG title glyphs rendered from geometry at the output scale. MIT license. */
#include <cairo.h>
#include <stdint.h>
#include "nextspace-geometry.h"
#include "frame-controls.h"

static void decoration_draw_glyph(cairo_t *cr, const struct decoration_glyph *glyph,
    int x, int y, int scale)
{
  cairo_save(cr);
  cairo_identity_matrix(cr);
  cairo_translate(cr, ns_scale_edge(x, scale), ns_scale_edge(y, scale));
  cairo_scale(cr, scale / 120., scale / 120.);
  cairo_set_antialias(cr, CAIRO_ANTIALIAS_NONE);
  for (unsigned i = 0; i < glyph->count; i++) {
    const struct decoration_primitive *shape = &glyph->primitives[i];
    cairo_set_source_rgb(cr, ((shape->rgb >> 16) & 255) / 255.,
      ((shape->rgb >> 8) & 255) / 255., (shape->rgb & 255) / 255.);
    cairo_append_path(cr, shape->path);
    cairo_fill(cr);
  }
  cairo_restore(cr);
}
