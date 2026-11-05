/* 
   WaylandServer - Output Handling

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
#include <AppKit/NSScreen.h>

static void
handle_geometry(void *data, struct wl_output *wl_output, int x, int y,
		int physical_width, int physical_height, int subpixel,
		const char *make, const char *model, int transform)
{
  NSDebugLog(@"handle_geometry");
  struct output *output = data;

  if (!output->logical_geometry) { output->alloc_x = x; output->alloc_y = y; }
  output->transform = transform;
  output->physical_width = physical_width; output->physical_height = physical_height;

  if (output->make)
    free(output->make);
  output->make = strdup(make);

  if (output->model)
    free(output->model);
  output->model = strdup(model);
}

static void
handle_done(void *data, struct wl_output *wl_output)
{
  WaylandOutputsChanged(((struct output *)data)->wlconfig);
}

static void
handle_scale(void *data, struct wl_output *wl_output, int32_t scale)
{
  NSDebugLog(@"handle_scale");
  struct output *output = data;

  output->scale = MAX(1, scale);
  if (!output->logical_geometry) {
    output->width = output->mode_width / output->scale;
    output->height = output->mode_height / output->scale;
  }
  WaylandConfig *config = output->wlconfig;
  int outputID = output->server_output_id, scale120 = output->scale * 120;
  for (NSNumber *number in WaylandWindowNumbers(config)) {
    struct window *w = get_window_with_id(config, [number intValue]);
    if (w && w->output && w->output->server_output_id == outputID && !w->fractional_scale)
      WaylandSetScale(w, scale120);
  }
}

static void
handle_mode(void *data, struct wl_output *wl_output, uint32_t flags, int width,
	    int height, int refresh)
{
  NSDebugLog(@"handle_mode");
  struct output *output = data;

  if (flags & WL_OUTPUT_MODE_CURRENT)
    {
      output->mode_width = width; output->mode_height = height; output->mode_refresh = refresh;
      if (!output->logical_geometry) {
        output->width = (output->transform & 1 ? height : width) / output->scale;
        output->height = (output->transform & 1 ? width : height) / output->scale;
      }
      NSDebugLog(@"handle_mode output=%dx%d", width, height);

      //  XXX - Should we implement this?
      //        if (display->output_configure_handler)
      //            (*display->output_configure_handler)
      //            (output, display->user_data);
      //
    }
}

const struct wl_output_listener output_listener
  = {handle_geometry, handle_mode, handle_done, handle_scale};
