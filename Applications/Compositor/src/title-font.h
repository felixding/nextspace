/* Native interpretation of existing Fontconfig title preferences. MIT license. */
#ifndef NEXTSPACE_TITLE_FONT_H
#define NEXTSPACE_TITLE_FONT_H

#include <pango/pangofc-fontmap.h>
#include <pango/pangocairo.h>
#include <math.h>
#include <stdbool.h>
#include <string.h>

struct title_font {
  char *description;
  bool antialiased;
  FcPattern *pattern;
  PangoFontMap *map;
  cairo_font_options_t *options;
};

static void title_font_substitute(FcPattern *pattern, gpointer data)
{
  FcPattern *selected = data;
  const char *names[] = {FC_FILE, FC_INDEX, FC_ANTIALIAS, FC_HINTING, FC_HINT_STYLE,
    FC_AUTOHINT, FC_EMBEDDED_BITMAP, FC_RGBA, FC_LCD_FILTER, FC_FONT_VARIATIONS};
  for (unsigned i = 0; i < sizeof(names) / sizeof(*names); i++) {
    FcValue value;
    if (FcPatternGet(selected, names[i], 0, &value) != FcResultMatch) continue;
    FcPatternDel(pattern, names[i]);
    for (int n = 0; FcPatternGet(selected, names[i], n, &value) == FcResultMatch; n++)
      FcPatternAdd(pattern, names[i], value, FcTrue);
  }
}

static void title_font_pattern_destroy(gpointer pattern)
{ FcPatternDestroy(pattern); }

static void title_font_destroy(struct title_font *font)
{
  if (!font) return;
  g_object_unref(font->map);
  cairo_font_options_destroy(font->options);
  FcPatternDestroy(font->pattern);
  g_free(font->description);
  g_free(font);
}

static struct title_font *title_font_create(const char *name, bool antialiased)
{
  if (!name || !*name || strlen(name) > 4096 || !g_utf8_validate(name, -1, NULL)) return NULL;
  FcPattern *pattern = FcNameParse((const FcChar8 *)name);
  if (!pattern) return NULL;
  FcBool effective;
  /* Match WM's fallback before normal Fontconfig substitutions. */
  if (!antialiased && FcPatternGetBool(pattern, FC_ANTIALIAS, 0, &effective) != FcResultMatch)
    FcPatternAddBool(pattern, FC_ANTIALIAS, FcFalse);
  double dpi;
  /* Point-sized legacy patterns use a stable logical DPI. Pixel sizes, as
     written by Preferences, and explicit DPI values retain their meaning. */
  if (FcPatternGetDouble(pattern, FC_DPI, 0, &dpi) != FcResultMatch)
    FcPatternAddDouble(pattern, FC_DPI, 96);
  FcConfigSubstitute(NULL, pattern, FcMatchPattern);
  FcDefaultSubstitute(pattern);
  FcResult result;
  FcPattern *match = FcFontMatch(NULL, pattern, &result);
  FcPatternDestroy(pattern);
  if (!match) return NULL;
  double pixels;
  struct title_font *font = NULL;
  if (FcPatternGetDouble(match, FC_PIXEL_SIZE, 0, &pixels) == FcResultMatch &&
      isfinite(pixels) && pixels > 0 && pixels <= 512) {
    font = g_new0(struct title_font, 1);
    PangoFontDescription *description = pango_fc_font_description_from_pattern(match, false);
    pango_font_description_set_absolute_size(description, pixels * PANGO_SCALE);
    font->description = pango_font_description_to_string(description);
    pango_font_description_free(description);
    effective = FcTrue;
    FcPatternGetBool(match, FC_ANTIALIAS, 0, &effective);
    font->antialiased = effective;
    font->options = cairo_font_options_create();
    cairo_font_options_set_antialias(font->options, effective ? CAIRO_ANTIALIAS_GRAY : CAIRO_ANTIALIAS_NONE);
    cairo_font_options_set_hint_metrics(font->options, CAIRO_HINT_METRICS_ON);
    FcBool hinting = FcTrue;
    int hintstyle = FC_HINT_FULL;
    FcPatternGetBool(match, FC_HINTING, 0, &hinting);
    FcPatternGetInteger(match, FC_HINT_STYLE, 0, &hintstyle);
    cairo_hint_style_t styles[] = {CAIRO_HINT_STYLE_NONE, CAIRO_HINT_STYLE_SLIGHT,
      CAIRO_HINT_STYLE_MEDIUM, CAIRO_HINT_STYLE_FULL};
    cairo_font_options_set_hint_style(font->options, !hinting ? CAIRO_HINT_STYLE_NONE :
      hintstyle >= FC_HINT_NONE && hintstyle <= FC_HINT_FULL ? styles[hintstyle] : CAIRO_HINT_STYLE_DEFAULT);
    font->pattern = FcPatternDuplicate(match);
    font->map = pango_cairo_font_map_new();
    pango_fc_font_map_set_default_substitute(PANGO_FC_FONT_MAP(font->map), title_font_substitute,
      FcPatternDuplicate(match), title_font_pattern_destroy);
  }
  FcPatternDestroy(match);
  return font;
}

#endif
