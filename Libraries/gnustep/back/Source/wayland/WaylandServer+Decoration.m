/* Preserve AppKit logical frames while presenting server-decorated content.
   LGPL-2.0-or-later. */
#include "wayland/WaylandServer.h"
#include <AppKit/AppKit.h>

struct ns_frame_extents WaylandFrameInsets(struct window *w)
{ return w && w->server_frame && !w->fullscreen ? w->frame : (struct ns_frame_extents){0}; }

NSSize WaylandSurfaceSize(struct window *w)
{
  struct ns_frame_extents frame = WaylandFrameInsets(w);
  return NSMakeSize(MAX(1, w->width - ns_frame_horizontal(frame)),
                   MAX(1, w->height - ns_frame_vertical(frame)));
}

NSPoint WaylandSurfacePoint(struct window *w, NSPoint point)
{
  struct ns_frame_extents frame = WaylandFrameInsets(w);
  return NSMakePoint(point.x + frame.left, w->height - point.y - frame.top);
}

NSPoint WaylandSurfaceOrigin(struct window *w)
{
  struct ns_frame_extents frame = WaylandFrameInsets(w);
  return NSMakePoint(w->pos_x + frame.left, w->pos_y + frame.top);
}

void WaylandUpdateFrameMetrics(struct window *w)
{
  /* Preserve negotiated normal metrics for restoration after fullscreen. */
  if (w->fullscreen) return;
  NSWindow *window = GSWindowWithNumber(w->window_id);
  NSRect frame = [window frame], content = [window contentRectForFrameRect:frame];
  struct ns_frame_extents metrics = {
    lround(NSMinX(content) - NSMinX(frame)), lround(NSMaxY(frame) - NSMaxY(content)),
    lround(NSMaxX(frame) - NSMaxX(content)), lround(NSMinY(content) - NSMinY(frame))};
  if (!window || !ns_frame_extents_valid(metrics)) metrics = (struct ns_frame_extents){0};
  w->frame = metrics;
  if (w->application_window && nextspace_window_v1_get_version(w->application_window) >= 7)
    nextspace_window_v1_set_frame_extents(w->application_window, metrics.left, metrics.top,
      metrics.right, metrics.bottom);
}

static void decoration_configure(void *data, struct zxdg_toplevel_decoration_v1 *object, uint32_t mode)
{
  ((struct window *)data)->pending_decoration_mode = mode;
}
static const struct zxdg_toplevel_decoration_v1_listener decoration_listener = {.configure = decoration_configure};

void WaylandSetupDecoration(struct window *w)
{
  if (!w->wlconfig->decoration_manager || !w->viewport || !w->toplevel) return;
  if (!w->application_window) WaylandUpdateFrameMetrics(w);
  /* The private metrics contract preserves NeXT geometry. Other compositors
     retain the existing client frame unless they explicitly select SSD. */
  id preference = [[NSUserDefaults standardUserDefaults] objectForKey:@"GSWaylandServerDecorations"];
  w->wants_server_frame = w->application_window && nextspace_window_v1_get_version(w->application_window) >= 7 &&
    ns_frame_vertical(w->frame) + ns_frame_horizontal(w->frame) > 0 &&
    (!preference || [preference boolValue]);
  w->decoration = zxdg_decoration_manager_v1_get_toplevel_decoration(w->wlconfig->decoration_manager, w->toplevel);
  zxdg_toplevel_decoration_v1_add_listener(w->decoration, &decoration_listener, w);
  zxdg_toplevel_decoration_v1_set_mode(w->decoration, w->wants_server_frame ?
    ZXDG_TOPLEVEL_DECORATION_V1_MODE_SERVER_SIDE : ZXDG_TOPLEVEL_DECORATION_V1_MODE_CLIENT_SIDE);
}

void WaylandConfigureViewport(struct window *w, int width, int height)
{
  NSSize content = WaylandSurfaceSize(w);
  if (w->server_frame && !w->fullscreen) {
    struct ns_frame_extents frame = w->frame;
    /* Crop shared edges once in buffer pixels, including odd fractional sizes.
       Retained drawing keeps its original AppKit frame and device transform. */
    int left = MAX(0, MIN(width - 1, ns_scale_edge(frame.left, w->scale120)));
    int top = MAX(0, MIN(height - 1, ns_scale_edge(frame.top, w->scale120)));
    int right = MAX(left + 1, MIN(width, ns_scale_edge(w->width - frame.right, w->scale120)));
    int bottom = MAX(top + 1, MIN(height, ns_scale_edge(w->height - frame.bottom, w->scale120)));
    wp_viewport_set_source(w->viewport, wl_fixed_from_int(left), wl_fixed_from_int(top),
      wl_fixed_from_int(right - left), wl_fixed_from_int(bottom - top));
  } else {
    wp_viewport_set_source(w->viewport, wl_fixed_from_int(-1), wl_fixed_from_int(-1),
      wl_fixed_from_int(-1), wl_fixed_from_int(-1));
  }
  wp_viewport_set_destination(w->viewport, content.width, content.height);
}
