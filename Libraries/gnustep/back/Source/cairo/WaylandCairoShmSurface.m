/* WaylandCairoSurface

   WaylandCairoShmSurface - A cairo surface backed by a wayland
   shared memory buffer.
   After the wayland surface is configured, the buffer needs to be
   attached to the surface. Subsequent changes to the cairo surface
   needs to be notified to the wayland server using wl_surface_damage
   and wl_surface_commit. The buffer is freed after the compositor
   releases it and the cairo surface is not in use.

   Copyright (C) 2020 Free Software Foundation, Inc.

   Author: Sergio L. Pascual <slp@sinrega.org>
   Rewrite: Riccardo Canalicchio <riccardo.canalicchio(at)gmail.com>
   Date: November 2021

   This file is part of the GNU Objective C Backend Library.

   This library is free software; you can redistribute it and/or
   modify it under the terms of the GNU Lesser General Public
   License as published by the Free Software Foundation; either
   version 2 of the License, or (at your option) any later version.

   This library is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
   Lesser General Public License for more details.

   You should have received a copy of the GNU Lesser General Public
   License along with this library; see the file COPYING.LIB.
   If not, see <http://www.gnu.org/licenses/> or write to the
   Free Software Foundation, 51 Franklin Street, Fifth Floor,
   Boston, MA 02110-1301, USA.
*/

#define _GNU_SOURCE
#include "wayland/WaylandServer.h"
#include "wayland/nextspace-geometry.h"
#include "cairo/WaylandCairoShmSurface.h"
#include "cairo/WaylandCapture.h"
#include <AppKit/NSColor.h>
#include <AppKit/NSGraphics.h>
#include <AppKit/NSWindow.h>
#include <sys/mman.h>
#include <unistd.h>
#include <limits.h>
#include <string.h>

void destroyShmBuffer(struct pool_buffer *b)
{
  if (!b) return;
  wl_buffer_destroy(b->buffer);
  cairo_surface_destroy(b->surface);
  munmap(b->data, b->size);
  free(b);
}

static void released(void *data, struct wl_buffer *buffer)
{
  struct pool_buffer *b = data;
  b->busy = false;
  [b->owner present];
}
static const struct wl_buffer_listener buffer_listener = {.release = released};

struct pool_buffer *createShmBuffer(int width, int height, struct wl_shm *shm)
{
  int stride = cairo_format_stride_for_width(CAIRO_FORMAT_ARGB32, width);
  if (width <= 0 || height <= 0 || stride <= 0 || height > INT_MAX / stride)
    return NULL;
  size_t size = (size_t)stride * height;
  int fd = memfd_create("nextspace-buffer", MFD_CLOEXEC);
  if (fd < 0) return NULL;
  if (ftruncate(fd, size) != 0) { close(fd); return NULL; }
  void *pixels = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
  if (pixels == MAP_FAILED) { close(fd); return NULL; }
  struct pool_buffer *b = calloc(1, sizeof(*b));
  if (!b) { munmap(pixels, size); close(fd); return NULL; }
  struct wl_shm_pool *pool = wl_shm_create_pool(shm, fd, size);
  b->buffer = wl_shm_pool_create_buffer(pool, 0, width, height, stride,
                                        WL_SHM_FORMAT_ARGB8888);
  wl_shm_pool_destroy(pool);
  close(fd);
  b->data = pixels; b->size = size; b->width = width; b->height = height;
  b->surface = cairo_image_surface_create_for_data(pixels, CAIRO_FORMAT_ARGB32,
                                                   width, height, stride);
  wl_buffer_add_listener(b->buffer, &buffer_listener, b);
  return b;
}

static void frame_done(void *data, struct wl_callback *callback, uint32_t time)
{
  struct window *w = data;
  wl_callback_destroy(callback);
  w->frame_callback = NULL;
  [(WaylandCairoShmSurface *)w->wcs present];
}
static const struct wl_callback_listener frame_listener = {.done = frame_done};

@implementation WaylandCairoShmSurface
- (id)initWithDevice:(void *)device
{
  self = [super init];
  if (!self) return nil;
  struct window *w = device;
  uint32_t scale = w->scale120 ? w->scale120 : 120;
  int width = ns_buffer_extent((int)w->width, scale);
  int height = ns_buffer_extent((int)w->height, scale);
  WaylandCairoShmSurface *existing = (WaylandCairoShmSurface *)w->wcs;
  if (existing) {
    double sx, sy;
    cairo_surface_get_device_scale(existing->_surface, &sx, &sy);
    if (NSEqualSizes(existing->logicalSize, NSMakeSize(w->width, w->height)) &&
        existing->fullscreen == w->fullscreen &&
        cairo_image_surface_get_width(existing->_surface) == width &&
        cairo_image_surface_get_height(existing->_surface) == height &&
        sx == scale / 120.0 && sy == sx) {
      /* Rebinding a context must preserve retained and NSImage cache pixels. */
      [self release];
      return [existing retain];
    }
  }
  gsDevice = device;
  w->surface_refs++;
  logicalSize = NSMakeSize(w->width, w->height);
  fullscreen = w->fullscreen;
  _surface = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, width, height);
  if (cairo_surface_status(_surface) != CAIRO_STATUS_SUCCESS) {
    [self release]; return nil;
  }
  cairo_surface_set_device_scale(_surface, scale / 120.0, scale / 120.0);
  /* Rounded buffer edges may extend beyond the logical drawing clip. An
     opaque window needs its background there too; image caches keep alpha. */
  NSWindow *window = GSWindowWithNumber(w->window_id);
  NSColor *background = [[window backgroundColor] colorUsingColorSpaceName:NSDeviceRGBColorSpace];
  if (!w->unscaled && [window isOpaque] && background) {
    cairo_t *context = cairo_create(_surface);
    cairo_set_source_rgb(context, [background redComponent], [background greenComponent], [background blueComponent]);
    cairo_paint(context);
    cairo_destroy(context);
  }
  /* Drawing always targets this retained image. Submitted shm buffers are
     immutable until release, even when AppKit repaints between frames. */
  w->wcs = self;
  w->buffer_needs_attach = YES;
  return self;
}

- (void)detach
{
  struct window *w = gsDevice;
  if (w->frame_callback) {
    wl_callback_destroy(w->frame_callback);
    w->frame_callback = NULL;
  }
  pending = YES;
}

- (void)dealloc
{
  struct window *w = gsDevice;
  if (!w) { [super dealloc]; return; }
  if (w->wcs == self) { [self detach]; w->wcs = nil; }
  unsigned i;
  for (i = 0; i < 3; ++i) destroyShmBuffer(buffers[i]);
  w->surface_refs--;
  if (w->terminated && !w->surface_refs) free(w);
  [super dealloc];
}

- (NSSize)size
{
  return logicalSize;
}

- (void)present
{
  struct window *w = gsDevice;
  if (!pending || w->wcs != self || !w->configured || !w->surface || w->frame_callback || w->terminated)
    return;
  int width = cairo_image_surface_get_width(_surface);
  int height = cairo_image_surface_get_height(_surface);
  struct pool_buffer *b = NULL;
  unsigned i;
  for (i = 0; i < 3; ++i) {
    if (buffers[i] && buffers[i]->busy) continue;
    if (buffers[i] && (buffers[i]->width != width || buffers[i]->height != height)) {
      destroyShmBuffer(buffers[i]); buffers[i] = NULL;
    }
    if (!buffers[i]) buffers[i] = createShmBuffer(width, height, w->wlconfig->shm);
    b = buffers[i]; break;
  }
  if (!b) return;
  cairo_surface_flush(_surface);
  memcpy(b->data, cairo_image_surface_get_data(_surface), b->size);
  b->owner = self;
  b->busy = true;
  if (w->viewport) {
    if (wl_proxy_get_version((struct wl_proxy *)w->surface) >= 3) wl_surface_set_buffer_scale(w->surface, 1);
    WaylandConfigureViewport(w, width, height);
  } else if (wl_proxy_get_version((struct wl_proxy *)w->surface) >= 3) {
    wl_surface_set_buffer_scale(w->surface, w->scale120 / 120);
  }
  w->frame_callback = wl_surface_frame(w->surface);
  wl_callback_add_listener(w->frame_callback, &frame_listener, w);
  wl_surface_attach(w->surface, b->buffer, 0, 0);
  if (w->xdg_surface) {
    NSSize content = WaylandSurfaceSize(w);
    xdg_surface_set_window_geometry(w->xdg_surface, 0, 0, content.width, content.height);
  }
  /* All buffers contain a full retained image. Full damage is intentional:
     an idle pool entry may predate several partial repaints. */
  if (wl_proxy_get_version((struct wl_proxy *)w->surface) >= 4)
    wl_surface_damage_buffer(w->surface, 0, 0, width, height);
  else wl_surface_damage(w->surface, 0, 0, logicalSize.width, logicalSize.height);
  wl_surface_commit(w->surface);
  wl_display_flush(w->wlconfig->display);
  w->buffer_needs_attach = NO;
  pending = NO;
  const char *capture = getenv("NEXTSPACE_WAYLAND_CAPTURE_DIR");
  if (capture) {
    char path[PATH_MAX], temporary[PATH_MAX];
    int n = snprintf(path, sizeof(path), "%s/window-%d-%u.png", capture, w->window_id, w->scale120);
    if (n > 0 && n < sizeof(path)) {
      n = snprintf(temporary, sizeof(temporary), "%s.tmp", path);
      if (n > 0 && n < sizeof(temporary)) {
        if (WaylandWriteCapture(_surface, temporary)) rename(temporary, path);
        unlink(temporary);
      }
    }
  }
}

- (void)handleExposeRect:(NSRect)rect
{
  pending = YES;
  [self present];
}
@end
