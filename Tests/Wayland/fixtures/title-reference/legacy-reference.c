/*
 *  Workspace window manager
 *  Copyright (c) 2015-2021 Sergii Stoian
 *
 *  Window Maker window manager
 *  Copyright (c) 1997-2003 Alfredo K. Kojima
 *
 *  This program is free software; you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation; either version 2 of the License, or
 *  (at your option) any later version.
 *
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License along
 *  with this program; if not, write to the Free Software Foundation, Inc.,
 *  51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
 */
/*
 *  Workspace window manager
 *  Copyright (c) 2015-2021 Sergii Stoian
 *
 *  WINGs library (Window Maker)
 *  Copyright (c) 1998 scottc
 *  Copyright (c) 1999-2004 Dan Pascu
 *  Copyright (c) 1999-2000 Alfredo K. Kojima
 *  Copyright (c) 2014 Window Maker Team
 *
 *  This program is free software; you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation; either version 2 of the License, or
 *  (at your option) any later version.
 *
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License along
 *  with this program; if not, write to the Free Software Foundation, Inc.,
 *  51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
 */
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/Xft/Xft.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "wfont.h"
#define wmalloc malloc
#define wassertrv(c,r) do { if (!(c)) return (r); } while (0)
int WMWidthOfString(WMFont *font, const char *text, int length)
{
#ifdef USE_PANGO
  const char *previous_text;
  int width;
#else
  XGlyphInfo extents;
#endif

  wassertrv(font != NULL && text != NULL, 0);
#ifdef USE_PANGO
  previous_text = pango_layout_get_text(font->layout);
  if ((previous_text == NULL) || (strncmp(text, previous_text, length) != 0) || previous_text[length] != '\0')
    pango_layout_set_text(font->layout, text, length);
  pango_layout_get_pixel_size(font->layout, &width, NULL);

  return width;
#else
  XftTextExtentsUtf8(font->screen->display, font->font, (XftChar8 *) text, length, &extents);

  return extents.xOff;	/* don't ask :P */
#endif
}
char *ShrinkString(WMFont *font, const char *string, int width)
{
  int w, w1 = 0;
  int p;
  char *pos;
  char *text;
  int p1, p2, t;

  p = strlen(string);
  w = WMWidthOfString(font, string, p);
  text = wmalloc(strlen(string) + 8);
  strcpy(text, string);
  if (w <= width)
    return text;

  pos = strchr(text, ' ');
  if (!pos)
    pos = strchr(text, ':');

  if (pos) {
    *pos = 0;
    p = strlen(text);
    w1 = WMWidthOfString(font, text, p);
    if (w1 > width) {
      p = 0;
      *pos = ' ';
      *text = 0;
    } else {
      *pos = 0;
      width -= w1;
      p++;
    }
    string += p;
    p = strlen(string);
  } else {
    *text = 0;
  }
  strcat(text, "...");
  width -= WMWidthOfString(font, "...", 3);

  p1 = 0;
  p2 = p;
  t = (p2 - p1) / 2;
  while (p2 > p1 && p1 != t) {
    w = WMWidthOfString(font, &string[p - t], t);
    if (w > width) {
      p2 = t;
      t = p1 + (p2 - p1) / 2;
    } else if (w < width) {
      p1 = t;
      t = p1 + (p2 - p1) / 2;
    } else
      p2 = p1 = t;
  }
  strcat(text, &string[p - p1]);

  return text;
}

int main(int argc, char **argv) {
  if (argc != 4 && argc != 5) return 2;
  Display *display = XOpenDisplay(NULL); if (!display) return 3;
  WMScreen screen = {.display = display, .screen = DefaultScreen(display)};
  WMFont font = {.screen = &screen};
  font.font = XftFontOpenName(display, screen.screen, argv[3]);
  if (!font.font) return 4;
  char *result = ShrinkString(&font, argv[2], atoi(argv[1]));
  fprintf(stderr, "%d %d %d\n", font.font->ascent + font.font->descent,
    WMWidthOfString(&font, argv[2], strlen(argv[2])),
    WMWidthOfString(&font, result, strlen(result)));
  fwrite(result, 1, strlen(result), stdout);
  if (argc == 5) {
    int number = screen.screen, width = 1602, height = 46;
    Pixmap pixmap = XCreatePixmap(display, RootWindow(display, number), width, height, DefaultDepth(display, number));
    GC gc = XCreateGC(display, pixmap, 0, NULL);
    XSetForeground(display, gc, BlackPixel(display, number));
    XFillRectangle(display, pixmap, gc, 0, 0, width, height);
    XftDraw *draw = XftDrawCreate(display, pixmap, DefaultVisual(display, number), DefaultColormap(display, number));
    XftColor white;
    if (!XftColorAllocName(display, DefaultVisual(display, number), DefaultColormap(display, number), "white", &white)) return 5;
    XftDrawStringUtf8(draw, &white, font.font, 1, 1 + font.font->ascent, (const FcChar8 *)result, strlen(result));
    XImage *image = XGetImage(display, pixmap, 0, 0, width, height, AllPlanes, ZPixmap);
    FILE *file = fopen(argv[4], "wb"); if (!file) return 6;
    fprintf(file, "P6\n%d %d\n255\n", width, height);
    for (int y = 0; y < height; y++) for (int x = 0; x < width; x++) {
      unsigned long pixel = XGetPixel(image, x, y);
      unsigned char rgb[] = {pixel >> 16, pixel >> 8, pixel};
      fwrite(rgb, 1, 3, file);
    }
    fclose(file); XDestroyImage(image);
    XftColorFree(display, DefaultVisual(display, number), DefaultColormap(display, number), &white);
    XftDrawDestroy(draw); XFreeGC(display, gc); XFreePixmap(display, pixmap);
  }
  free(result);
  XftFontClose(display, font.font); XCloseDisplay(display); return 0;
}
