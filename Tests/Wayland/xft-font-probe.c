/* Independent original Xft rendering, including WM's AA fallback. MIT license. */
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/Xft/Xft.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "font-probe-debug.h"

int main(int argc, char **argv)
{
  if (argc != 5) return 2;
  const char *suffix = !atoi(argv[2]) && !strstr(argv[1], ":antialias=") ? ":antialias=false" : "";
  char *pattern = malloc(strlen(argv[1]) + strlen(suffix) + 1);
  if (!pattern) return 3;
  strcpy(pattern, argv[1]); strcat(pattern, suffix);
  Display *display = XOpenDisplay(NULL);
  if (!display) { free(pattern); return 4; }
  int screen = DefaultScreen(display), width = 1602, height = 46;
  XftFont *font = XftFontOpenName(display, screen, pattern);
  free(pattern);
  if (!font) { XCloseDisplay(display); return 5; }
  font_probe_debug("Xft", font->pattern);
  Pixmap pixmap = XCreatePixmap(display, RootWindow(display, screen), width, height, DefaultDepth(display, screen));
  GC gc = XCreateGC(display, pixmap, 0, NULL);
  XSetForeground(display, gc, BlackPixel(display, screen));
  XFillRectangle(display, pixmap, gc, 0, 0, width, height);
  XftDraw *draw = XftDrawCreate(display, pixmap, DefaultVisual(display, screen), DefaultColormap(display, screen));
  XftColor white;
  if (!XftColorAllocName(display, DefaultVisual(display, screen), DefaultColormap(display, screen), "white", &white)) return 6;
  XftDrawStringUtf8(draw, &white, font, 1, 1 + font->ascent, (const FcChar8 *)argv[3], strlen(argv[3]));
  XGlyphInfo extents;
  XftTextExtentsUtf8(display, font, (const FcChar8 *)argv[3], strlen(argv[3]), &extents);
  XImage *image = XGetImage(display, pixmap, 0, 0, width, height, AllPlanes, ZPixmap);
  FILE *file = fopen(argv[4], "wb"); if (!file) return 7;
  fprintf(file, "P6\n%d %d\n255\n", width, height);
  for (int y = 0; y < height; y++) for (int x = 0; x < width; x++) {
    unsigned long pixel = XGetPixel(image, x, y);
    unsigned char rgb[] = {pixel >> 16, pixel >> 8, pixel};
    fwrite(rgb, 1, 3, file);
  }
  fclose(file);
  FcBool antialiased = FcTrue;
  FcPatternGetBool(font->pattern, FC_ANTIALIAS, 0, &antialiased);
  printf("{\"width\":%d,\"height\":%d,\"antialiased\":%s}\n",
    extents.xOff, font->ascent + font->descent, antialiased ? "true" : "false");
  XDestroyImage(image);
  XftColorFree(display, DefaultVisual(display, screen), DefaultColormap(display, screen), &white);
  XftDrawDestroy(draw); XFreeGC(display, gc); XFreePixmap(display, pixmap);
  XftFontClose(display, font); XCloseDisplay(display);
  return 0;
}
