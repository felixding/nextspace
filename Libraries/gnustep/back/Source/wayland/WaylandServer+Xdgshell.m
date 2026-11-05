/* 
   WaylandServer - XdgShell Protocol Handling

   Copyright (C) 2020 Free Software Foundation, Inc.

   Author: Riccardo Canalicchio <riccardo.canalicchio(at)gmail.com>
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

#include "wayland/WaylandServer.h"
#include <AppKit/NSEvent.h>
#include <AppKit/NSApplication.h>
#include <AppKit/NSGraphics.h>
#include <AppKit/NSWindow.h>
#include <math.h>

@interface NSWindow (WaylandFullscreen)
- (void) _backendSetFullscreen: (BOOL)fullscreen;
@end

void WaylandApplySizeHints(struct window *window)
{
  if (!window || !window->toplevel) return;
  NSWindow *nswindow = GSWindowWithNumber(window->window_id);
  NSSize minimum = [nswindow minSize], maximum = [nswindow maxSize];
  struct ns_frame_extents frame = window->server_frame || (!window->configured && window->wants_server_frame) ?
    window->frame : (struct ns_frame_extents){0};
  minimum.width -= ns_frame_horizontal(frame); minimum.height -= ns_frame_vertical(frame);
  maximum.width -= ns_frame_horizontal(frame); maximum.height -= ns_frame_vertical(frame);
  int minWidth = MAX(1, ceil(minimum.width)), minHeight = MAX(1, ceil(minimum.height));
  int maxWidth = MAX(minWidth, floor(maximum.width)), maxHeight = MAX(minHeight, floor(maximum.height));
  xdg_toplevel_set_min_size(window->toplevel, minWidth, minHeight);
  xdg_toplevel_set_max_size(window->toplevel, maxWidth, maxHeight);
  if (window->configured) wl_surface_commit(window->surface);
}

static int constrain_extent(int desired, CGFloat minimum, CGFloat maximum, CGFloat increment)
{
  CGFloat size = MAX(minimum, MIN(maximum, desired));
  if (increment > 1) size = minimum + floor((size - minimum) / increment) * increment;
  return MAX(1, round(size));
}

static void
xdg_surface_on_configure(void *data, struct xdg_surface *xdg_surface,
                         uint32_t serial)
{
  struct window *window = data;
  WaylandConfig *config = window->wlconfig;
  int windowID = window->window_id;

  NSDebugLog(@"xdg_surface_on_configure: win=%d", window->window_id);

  if (window->terminated) return;

  NSEvent  *ev = nil;
  NSWindow *nswindow = GSWindowWithNumber(window->window_id);

  // NSDebugLog(@"Acknowledging surface configure %p %d (window_id=%d)",
  // xdg_surface, serial, window->window_id);

  xdg_surface_ack_configure(xdg_surface, serial);
  window->configured = YES;
  if (window->pending_decoration_mode) {
    BOOL serverFrame = window->pending_decoration_mode == ZXDG_TOPLEVEL_DECORATION_V1_MODE_SERVER_SIDE;
    if (window->server_frame != serverFrame) window->buffer_needs_attach = YES;
    window->server_frame = serverFrame;
    window->pending_decoration_mode = 0;
  }
  BOOL fullscreenChanged = window->fullscreen != window->pending_fullscreen;
  if (fullscreenChanged) {
    window->fullscreen = window->pending_fullscreen;
    [nswindow _backendSetFullscreen:window->fullscreen];
    window->buffer_needs_attach = YES;
  }
  int width = window->pending_width, height = window->pending_height;
  window->pending_width = window->pending_height = 0;
  if (window->toplevel) {
    struct ns_frame_extents frame = WaylandFrameInsets(window);
    if (width > 0) width += ns_frame_horizontal(frame);
    else if (window->was_bounded && !window->bounded) width = window->normal_width;
    if (height > 0) height += ns_frame_vertical(frame);
    else if (window->was_bounded && !window->bounded) height = window->normal_height;
    if (width > 0 && height > 0 && !window->bounded && !window->was_bounded) {
      NSSize minimum = [nswindow minSize], maximum = [nswindow maxSize], increments = [nswindow resizeIncrements];
      width = constrain_extent(width, minimum.width, maximum.width, increments.width);
      height = constrain_extent(height, minimum.height, maximum.height, increments.height);
    }
    window->was_bounded = NO;
  }
  if (width > 0 && height > 0 && (fullscreenChanged || window->width != width || window->height != height)) {
    window->width = width; window->height = height;
    ev = [NSEvent otherEventWithType:NSAppKitDefined
      location:[nswindow frame].origin modifierFlags:0 timestamp:0
      windowNumber:window->window_id context:GSCurrentContext()
      subtype:GSAppKitWindowResized data1:window->width data2:window->height];
    [nswindow sendEvent:ev];
    window = get_window_with_id(config, windowID);
    if (!window) return;
  }
  if (window->pending_position) {
    struct window *parent = get_window_with_id(config, window->parent_id);
    window->pending_position = NO;
    if (parent) {
      NSPoint origin = WaylandSurfaceOrigin(parent);
      WaylandSetPosition(window, origin.x + window->pending_x, origin.y + window->pending_y);
    }
    window = get_window_with_id(config, windowID);
    if (!window) return;
  }

  if (window->buffer_needs_attach)
    {
      [window->instance flushwindowrect:NSMakeRect(window->pos_x, window->pos_y,
                                                   window->width, window->height)
                                      :window->window_id];
      window = get_window_with_id(config, windowID);
      if (!window) return;
    }


}

static void
xdg_toplevel_configure(void *data, struct xdg_toplevel *xdg_toplevel,
                       int32_t width, int32_t height, struct wl_array *states)
{
  struct window *window = data;

  NSDebugLog(@"[%d] xdg_toplevel_configure %dx%d", window->window_id, width,
             height);

  window->maximized = NO;
  window->pending_fullscreen = NO;
  BOOL bounded = NO;
  uint32_t *state;
  wl_array_for_each(state, states) {
    if (*state == XDG_TOPLEVEL_STATE_MAXIMIZED) window->maximized = YES;
    if (*state == XDG_TOPLEVEL_STATE_FULLSCREEN) window->pending_fullscreen = YES;
    if (*state == XDG_TOPLEVEL_STATE_FULLSCREEN || *state == XDG_TOPLEVEL_STATE_MAXIMIZED) bounded = YES;
  }
  BOOL wasBounded = window->bounded;
  window->was_bounded = wasBounded;
  if (bounded && !wasBounded) {
    window->normal_width = MAX(1, round(window->width));
    window->normal_height = MAX(1, round(window->height));
  }
  window->bounded = bounded;
  window->pending_width = width;
  window->pending_height = height;
}

static void
xdg_toplevel_close_handler(void *data, struct xdg_toplevel *xdg_toplevel)
{
  struct window *window = data;
  [GSWindowWithNumber(window->window_id) performClose:nil];
}

static void
xdg_popup_configure(void *data, struct xdg_popup *xdg_popup, int32_t x,
                    int32_t y, int32_t width, int32_t height)
{
  struct window *window = data;

  NSDebugLog(@"[%d] xdg_popup_configure [%d,%d %dx%d]", window->window_id, x, y,
             width, height);
  window->pending_x = x; window->pending_y = y;
  window->pending_position = YES;
  window->pending_width = width; window->pending_height = height;
}

static void
xdg_popup_done(void *data, struct xdg_popup *xdg_popup)
{
  struct window *window = data;
  [GSWindowWithNumber(window->window_id) orderOut:nil];
}

static void
wm_base_handle_ping(void *data, struct xdg_wm_base *xdg_wm_base,
                    uint32_t serial)
{
  NSDebugLog(@"wm_base_handle_ping");
  xdg_wm_base_pong(xdg_wm_base, serial);
}

const struct xdg_surface_listener xdg_surface_listener = {
  xdg_surface_on_configure,
};

const struct xdg_wm_base_listener wm_base_listener = {
  .ping = wm_base_handle_ping,
};

const struct xdg_popup_listener xdg_popup_listener = {
  .configure = xdg_popup_configure,
  .popup_done = xdg_popup_done,
};

const struct xdg_toplevel_listener xdg_toplevel_listener = {
  .configure = xdg_toplevel_configure,
  .close = xdg_toplevel_close_handler,
};
