/* Lossless diagnostic captures must not delay Wayland buffer submission.
 * LGPL-2.0-or-later. */
#ifndef WAYLAND_CAPTURE_H
#define WAYLAND_CAPTURE_H

#include <cairo.h>
#include <png.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static bool WaylandWriteCapture(cairo_surface_t *surface, const char *path)
{
  if (cairo_surface_get_type(surface) != CAIRO_SURFACE_TYPE_IMAGE) return false;
  cairo_format_t format = cairo_image_surface_get_format(surface);
  if (format != CAIRO_FORMAT_ARGB32 && format != CAIRO_FORMAT_RGB24) return false;
  int width = cairo_image_surface_get_width(surface), height = cairo_image_surface_get_height(surface);
  if (width <= 0 || height <= 0 || (size_t)width > SIZE_MAX / 4) return false;
  unsigned char *row = malloc((size_t)width * 4);
  FILE *file = fopen(path, "wb");
  png_structp png = png_create_write_struct(PNG_LIBPNG_VER_STRING, NULL, NULL, NULL);
  png_infop info = png ? png_create_info_struct(png) : NULL;
  volatile bool success = false;
  if (row && file && info && !setjmp(png_jmpbuf(png))) {
    png_init_io(png, file);
    png_set_IHDR(png, info, width, height, 8, PNG_COLOR_TYPE_RGBA,
      PNG_INTERLACE_NONE, PNG_COMPRESSION_TYPE_DEFAULT, PNG_FILTER_TYPE_DEFAULT);
    /* One filter and fast deflate preserve every pixel without the expensive
       adaptive-filter search used for archival PNG compression. */
    png_set_compression_level(png, 1);
    png_set_filter(png, PNG_FILTER_TYPE_BASE, PNG_FILTER_SUB);
    png_write_info(png, info);
    cairo_surface_flush(surface);
    const unsigned char *data = cairo_image_surface_get_data(surface);
    int stride = cairo_image_surface_get_stride(surface);
    int y, x;
    unsigned component;
    for (y = 0; y < height; y++) {
      const uint32_t *pixels = (const uint32_t *)(data + (size_t)y * stride);
      for (x = 0; x < width; x++) {
        uint32_t pixel = pixels[x];
        unsigned alpha = format == CAIRO_FORMAT_RGB24 ? 255 : pixel >> 24;
        for (component = 0; component < 3; component++) {
          unsigned value = (pixel >> (16 - 8 * component)) & 255;
          row[4 * x + component] = alpha ? (value * 255 + alpha / 2) / alpha : 0;
        }
        row[4 * x + 3] = alpha;
      }
      png_write_row(png, row);
    }
    png_write_end(png, info);
    success = true;
  }
  if (png) png_destroy_write_struct(&png, info ? &info : NULL);
  if (file && fclose(file) != 0) success = false;
  free(row);
  return success;
}

#endif
