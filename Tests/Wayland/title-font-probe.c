/* Exercise the compositor's real Fontconfig/title helpers. MIT license. */
#include <stdio.h>
#include <stdlib.h>
#include <pango/pangofc-font.h>
#include "font-probe-debug.h"
#include "../../Applications/Compositor/src/title-font.h"
#include "../../Applications/Compositor/src/title-text.h"

static void probe_substitute(FcPattern *pattern, gpointer data)
{
  title_font_substitute(pattern, data);
  font_probe_debug("SUBSTITUTE", pattern);
}

int main(int argc, char **argv)
{
  if (argc != 6) return 2;
  int density = atoi(argv[3]);
  struct title_font *font = title_font_create(argv[1], atoi(argv[2]) != 0);
  if (!font || density < 1) { title_font_destroy(font); return 3; }
  font_probe_debug("SELECTED", font->pattern);
  if (getenv("NEXTSPACE_FONT_DEBUG")) pango_fc_font_map_set_default_substitute(PANGO_FC_FONT_MAP(font->map),
    probe_substitute, FcPatternDuplicate(font->pattern), title_font_pattern_destroy);
  cairo_surface_t *surface = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, 1602, 46);
  cairo_t *cr = cairo_create(surface);
  cairo_scale(cr, density / 120., density / 120.);
  PangoLayout *layout = title_text_layout(cr, argv[4], 10000, font->description, font->antialiased, font->map, font->options);
  cairo_set_source_rgb(cr, 0, 0, 0); cairo_paint(cr);
  cairo_set_source_rgb(cr, 1, 1, 1); cairo_move_to(cr, 1, 1);
  title_text_draw(cr, layout);
  GSList *run = pango_layout_get_line_readonly(layout, 0)->runs;
  if (run) font_probe_debug("Pango", pango_fc_font_get_pattern(PANGO_FC_FONT(
    ((PangoGlyphItem *)run->data)->item->analysis.font)));
  if (run && getenv("NEXTSPACE_FONT_DEBUG")) {
    cairo_font_options_t *options = cairo_font_options_create();
    cairo_scaled_font_get_font_options(pango_cairo_font_get_scaled_font(PANGO_CAIRO_FONT(
      ((PangoGlyphItem *)run->data)->item->analysis.font)), options);
    fprintf(stderr, "Cairo antialias=%d hintstyle=%d hintmetrics=%d\n",
      cairo_font_options_get_antialias(options), cairo_font_options_get_hint_style(options),
      cairo_font_options_get_hint_metrics(options));
    cairo_font_options_destroy(options);
  }
  int width, height;
  title_text_size(layout, &width, &height);
  char *encoded = g_base64_encode((const guchar *)font->description, strlen(font->description));
  printf("{\"width\":%d,\"height\":%d,\"antialiased\":%s,\"unknown_glyphs\":%d,\"font_base64\":\"%s\"}\n",
    width, height, font->antialiased ? "true" : "false", pango_layout_get_unknown_glyphs_count(layout), encoded);
  int result = cairo_surface_write_to_png(surface, argv[5]) == CAIRO_STATUS_SUCCESS ? 0 : 4;
  g_free(encoded); g_object_unref(layout); title_font_destroy(font);
  cairo_destroy(cr); cairo_surface_destroy(surface);
  return result;
}
