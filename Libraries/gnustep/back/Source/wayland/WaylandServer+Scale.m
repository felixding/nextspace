/* Fractional backing density and logical output geometry. LGPL-2.0-or-later. */
#include "wayland/WaylandServer.h"
#include "cairo/WaylandCairoShmSurface.h"
#include <AppKit/AppKit.h>

@interface NSWindow (WaylandBacking)
- (void)_backendBackingScaleDidChange:(CGFloat)oldScale;
@end

void WaylandSetScale(struct window *w, uint32_t scale)
{
  /* NSCachedImageRep supplies its own pixel dimensions. Monitor changes must
     not replace its offscreen backing and invalidate cached image contents. */
  if (w->unscaled) return;
  if (w->surface && !w->viewport && wl_proxy_get_version((struct wl_proxy *)w->surface) < 3) scale = 120;
  if (!scale || scale == w->scale120 || w->terminated) return;
  CGFloat old = w->scale120 / 120.0;
  w->scale120 = scale;
  [GSWindowWithNumber(w->window_id) _backendBackingScaleDidChange:old];
}

static void preferred(void *data, struct wp_fractional_scale_v1 *object, uint32_t scale)
{
  WaylandSetScale(data, scale);
}
static const struct wp_fractional_scale_v1_listener fractional_listener = {
  .preferred_scale = preferred
};

static void enter(void *data, struct wl_surface *surface, struct wl_output *object)
{
  struct window *w = data;
  WaylandConfig *config = w->wlconfig;
  int windowID = w->window_id;
  if (!w->application_window) w->output = wl_output_get_user_data(object);
  if (!w->fractional_scale && w->output) WaylandSetScale(w, MAX(1, w->output->scale) * 120);
  WaylandReportScreen(get_window_with_id(config, windowID));
}
static void leave(void *data, struct wl_surface *surface, struct wl_output *output) {}
static const struct wl_surface_listener surface_listener = {.enter = enter, .leave = leave};

void WaylandSetupSurface(struct window *w)
{
  wl_surface_set_user_data(w->surface, w);
  wl_surface_add_listener(w->surface, &surface_listener, w);
  if (w->wlconfig->viewporter)
    w->viewport = wp_viewporter_get_viewport(w->wlconfig->viewporter, w->surface);
  if (w->wlconfig->fractional_manager && w->viewport) {
    w->fractional_scale = wp_fractional_scale_manager_v1_get_fractional_scale(
      w->wlconfig->fractional_manager, w->surface);
    wp_fractional_scale_v1_add_listener(w->fractional_scale, &fractional_listener, w);
  }
  if (!w->viewport) WaylandSetScale(w, w->scale120);
}

void WaylandDestroySurface(struct window *w)
{
  WaylandAbandonColorPick(w->wlconfig, w->window_id);
  if (w->activation_token) {
    xdg_activation_token_v1_destroy(w->activation_token); w->activation_token = NULL;
  }
  if (w->wlconfig->pointer.focus == w) w->wlconfig->pointer.focus = NULL;
  if (w->wlconfig->pointer.captured == w) w->wlconfig->pointer.captured = NULL;
  if (w->wlconfig->keyboard_focus == w) {
    WaylandCancelRepeat(w->wlconfig);
    w->wlconfig->keyboard_focus = NULL;
  }
  [(WaylandCairoShmSurface *)w->wcs detach];
  if (w->application_window) nextspace_window_v1_destroy(w->application_window);
  w->application_window = NULL;
  free(w->preferred_output_name); w->preferred_output_name = NULL;
  if (w->fractional_scale) wp_fractional_scale_v1_destroy(w->fractional_scale);
  if (w->viewport) wp_viewport_destroy(w->viewport);
  if (w->surface) wl_surface_destroy(w->surface);
  w->fractional_scale = NULL; w->viewport = NULL; w->surface = NULL;
  w->server_frame = w->wants_server_frame = NO;
  w->pending_decoration_mode = 0;
}

static void logical_position(void *data, struct zxdg_output_v1 *object, int32_t x, int32_t y)
{
  struct output *o = data;
  o->alloc_x = x; o->alloc_y = y;
  [NSScreen resetScreens];
}
static void logical_size(void *data, struct zxdg_output_v1 *object, int32_t width, int32_t height)
{
  struct output *o = data;
  o->width = width; o->height = height; o->logical_geometry = YES;
  [NSScreen resetScreens];
}
static void output_done(void *data, struct zxdg_output_v1 *object)
{
  WaylandOutputsChanged(((struct output *)data)->wlconfig);
}
static void output_text(void *data, struct zxdg_output_v1 *output, const char *text) {}
static void output_name(void *data, struct zxdg_output_v1 *output, const char *name) {
  struct output *o = data;
  free(o->name); o->name = strdup(name);
  WaylandOutputsChanged(o->wlconfig);
}
static const struct zxdg_output_v1_listener logical_listener = {
  .logical_position = logical_position, .logical_size = logical_size, .done = output_done,
  .name = output_name, .description = output_text
};
void WaylandSetupOutput(struct output *o)
{
  if (!o->wlconfig->output_manager || o->xdg_output) return;
  o->xdg_output = zxdg_output_manager_v1_get_xdg_output(o->wlconfig->output_manager, o->output);
  zxdg_output_v1_add_listener(o->xdg_output, &logical_listener, o);
}

@implementation WaylandServer (Backing)
- (CGFloat)backingScaleForWindow:(int)window
{
  struct window *w = get_window_with_id(wlconfig, window);
  return w ? w->scale120 / 120.0 : 1.0;
}
- (CGFloat)backingScaleForScreen:(int)screen
{
  struct output *o;
  wl_list_for_each(o, &wlconfig->output_list, link) {
    if (o->server_output_id == screen) {
      int pixels = (o->transform & 1) ? o->mode_height : o->mode_width;
      return o->logical_geometry && o->width > 0 ? round(120.0 * pixels / o->width) / 120.0 : o->scale;
    }
  }
  return 1.0;
}
- (int)screenForWindow:(int)window
{
  struct window *w = get_window_with_id(wlconfig, window);
  return w && w->output ? w->output->server_output_id : -1;
}
- (NSSize)resolutionForScreen:(int)screen
{
  return NSMakeSize(72, 72);
}
@end
