/* Optional diagnostics for independent font probes. MIT license. */
#include <fontconfig/fontconfig.h>
#include <stdio.h>
#include <stdlib.h>

static void font_probe_debug(const char *label, FcPattern *pattern)
{
  if (!getenv("NEXTSPACE_FONT_DEBUG")) return;
  const char *names[] = {FC_FILE, FC_PIXEL_SIZE, FC_DPI, FC_ANTIALIAS, FC_HINT_STYLE,
    FC_HINTING, FC_AUTOHINT, FC_EMBEDDED_BITMAP, FC_RGBA};
  fprintf(stderr, "%s", label);
  for (unsigned i = 0; i < sizeof(names) / sizeof(*names); i++) {
    FcValue value;
    if (FcPatternGet(pattern, names[i], 0, &value) != FcResultMatch) continue;
    fprintf(stderr, " %s=", names[i]);
    switch (value.type) {
      case FcTypeString: fprintf(stderr, "%s", value.u.s); break;
      case FcTypeDouble: fprintf(stderr, "%g", value.u.d); break;
      case FcTypeInteger: fprintf(stderr, "%d", value.u.i); break;
      case FcTypeBool: fprintf(stderr, "%s", value.u.b ? "true" : "false"); break;
      default: break;
    }
  }
  fputc('\n', stderr);
}
