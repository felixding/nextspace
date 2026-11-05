/* Logical title metrics and legacy prefix/tail shortening. MIT license. */
#ifndef NEXTSPACE_TITLE_TEXT_H
#define NEXTSPACE_TITLE_TEXT_H

#include <pango/pangocairo.h>
#include <stdbool.h>
#include <string.h>

static PangoGlyphString *title_text_glyphs(PangoGlyphItem *item)
{
  PangoGlyphString *glyphs = pango_glyph_string_copy(item->glyphs);
  cairo_scaled_font_t *font = pango_cairo_font_get_scaled_font(PANGO_CAIRO_FONT(item->item->analysis.font));
  if (!font || cairo_scaled_font_status(font) != CAIRO_STATUS_SUCCESS) return glyphs;
  cairo_matrix_t matrix, identity;
  cairo_scaled_font_get_font_matrix(font, &matrix);
  cairo_matrix_init_identity(&identity);
  cairo_font_options_t *options = cairo_font_options_create();
  cairo_scaled_font_get_font_options(font, options);
  cairo_scaled_font_t *logical = cairo_scaled_font_create(cairo_scaled_font_get_font_face(font),
    &matrix, &identity, options);
  cairo_font_options_destroy(options);
  /* Retain Xft's logical Cairo advances; HarfBuzz's natural advances can
     differ after hinting. Pango still supplies shaping and font fallback. */
  if (cairo_scaled_font_status(logical) == CAIRO_STATUS_SUCCESS) {
    for (int i = 0; i < glyphs->num_glyphs; i++) {
      PangoGlyphInfo *info = &glyphs->glyphs[i];
      if ((info->glyph & PANGO_GLYPH_UNKNOWN_FLAG) || info->glyph == PANGO_GLYPH_EMPTY ||
          !info->geometry.width) continue;
      cairo_glyph_t glyph = {.index = info->glyph};
      cairo_text_extents_t extents;
      cairo_scaled_font_glyph_extents(logical, &glyph, 1, &extents);
      info->geometry.width = (int)(extents.x_advance * PANGO_SCALE + 0.5);
    }
  }
  cairo_scaled_font_destroy(logical);
  return glyphs;
}

static void title_text_size(PangoLayout *layout, int *width, int *height)
{
  pango_layout_get_pixel_size(layout, width, height);
  int advance = 0;
  for (GSList *run = pango_layout_get_line_readonly(layout, 0)->runs; run; run = run->next) {
    PangoGlyphString *glyphs = title_text_glyphs(run->data);
    advance += pango_glyph_string_get_width(glyphs);
    pango_glyph_string_free(glyphs);
  }
  *width = PANGO_PIXELS_CEIL(advance);
}

static void title_text_draw(cairo_t *cr, PangoLayout *layout)
{
  double x, y;
  cairo_get_current_point(cr, &x, &y);
  y += pango_layout_get_baseline(layout) / (double)PANGO_SCALE;
  for (GSList *run = pango_layout_get_line_readonly(layout, 0)->runs; run; run = run->next) {
    PangoGlyphItem *item = run->data;
    PangoGlyphString *glyphs = title_text_glyphs(item);
    cairo_move_to(cr, x, y);
    pango_cairo_show_glyph_string(cr, item->item->analysis.font, glyphs);
    x += pango_glyph_string_get_width(glyphs) / (double)PANGO_SCALE;
    pango_glyph_string_free(glyphs);
  }
}

static int title_text_width(PangoLayout *layout, const char *text)
{
  int width;
  pango_layout_set_text(layout, text, -1);
  title_text_size(layout, &width, NULL);
  return width;
}

static PangoLayout *title_text_layout(cairo_t *cr, const char *text, int width,
    const char *font_name, bool antialiased, PangoFontMap *map, const cairo_font_options_t *font_options)
{
  /* Shape in logical units; the drawing context supplies backing density. */
  cairo_save(cr);
  cairo_identity_matrix(cr);
  cairo_font_options_t *options = cairo_font_options_create();
  cairo_font_options_set_antialias(options, antialiased ? CAIRO_ANTIALIAS_GRAY : CAIRO_ANTIALIAS_NONE);
  cairo_font_options_set_hint_style(options, CAIRO_HINT_STYLE_DEFAULT);
  cairo_font_options_set_hint_metrics(options, CAIRO_HINT_METRICS_ON);
  cairo_set_font_options(cr, font_options ? font_options : options);
  cairo_font_options_destroy(options);
  PangoContext *context = pango_font_map_create_context(map ? map : pango_cairo_font_map_get_default());
  pango_cairo_update_context(cr, context);
  PangoLayout *layout = pango_layout_new(context);
  g_object_unref(context);
  cairo_restore(cr);
  PangoFontDescription *font = pango_font_description_from_string(font_name);
  pango_layout_set_font_description(layout, font);
  pango_font_description_free(font);
  PangoAttrList *attributes = pango_attr_list_new();
  pango_attr_list_insert(attributes, pango_attr_font_features_new("kern=0,liga=0,clig=0"));
  pango_layout_set_attributes(layout, attributes);
  pango_attr_list_unref(attributes);
  pango_layout_set_single_paragraph_mode(layout, true);

  char *valid = g_utf8_make_valid(text, -1);
  if (title_text_width(layout, valid) <= width) {
    g_free(valid);
    return layout;
  }
  const char *separator = strchr(valid, ' ');
  if (!separator) separator = strchr(valid, ':');
  char *prefix = separator ? g_strndup(valid, separator - valid) : g_strdup("");
  const char *tail = separator ? separator + 1 : valid;
  if (title_text_width(layout, prefix) > width) {
    *prefix = '\0';
    tail = valid;
  }

  /* Keep combining sequences intact while retaining the longest fitting tail. */
  pango_layout_set_text(layout, tail, -1);
  int count;
  const PangoLogAttr *positions = pango_layout_get_log_attrs_readonly(layout, &count);
  GArray *boundaries = g_array_new(false, false, sizeof(int));
  const char *cursor = tail;
  for (int i = 0; i < count; i++) {
    int offset = cursor - tail;
    if (positions[i].is_cursor_position) g_array_append_val(boundaries, offset);
    if (*cursor) cursor = g_utf8_next_char(cursor);
  }
  unsigned first = 0, last = boundaries->len - 1;
  while (first < last) {
    unsigned middle = first + (last - first) / 2;
    char *candidate = g_strconcat(prefix, "...", tail + g_array_index(boundaries, int, middle), NULL);
    if (title_text_width(layout, candidate) <= width) last = middle;
    else first = middle + 1;
    g_free(candidate);
  }
  char *shortened = g_strconcat(prefix, "...", tail + g_array_index(boundaries, int, first), NULL);
  pango_layout_set_text(layout, shortened, -1);
  g_free(shortened);
  g_array_free(boundaries, true);
  g_free(prefix);
  g_free(valid);
  return layout;
}

#endif
