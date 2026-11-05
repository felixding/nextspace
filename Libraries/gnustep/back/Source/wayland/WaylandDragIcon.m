/* Native drag-image surface. LGPL-2.0-or-later. */
#include "wayland/WaylandDragIcon.h"
#include "cairo/WaylandCairoShmSurface.h"
#include "wayland/nextspace-geometry.h"
#include <AppKit/AppKit.h>

static void entered(void *data, struct wl_surface *surface, struct wl_output *output)
{ [(WaylandDragIcon *)data output:output entered:YES]; }
static void left(void *data, struct wl_surface *surface, struct wl_output *output)
{ [(WaylandDragIcon *)data output:output entered:NO]; }
static const struct wl_surface_listener surfaceListener = {.enter = entered, .leave = left};
static void preferred(void *data, struct wp_fractional_scale_v1 *object, uint32_t scale)
{ [(WaylandDragIcon *)data preferredScale:scale]; }
static const struct wp_fractional_scale_v1_listener fractionalListener = {.preferred_scale = preferred};

@implementation WaylandDragIcon
- (id)initWithImage:(NSImage *)image offset:(NSPoint)offset config:(WaylandConfig *)config
{
  if (!(self = [super init])) return nil;
  _size = [image size];
  if (!config || !image || !isfinite(_size.width) || !isfinite(_size.height) ||
      _size.width <= 0 || _size.height <= 0 || _size.width > 4096 || _size.height > 4096 ||
      !isfinite(offset.x) || !isfinite(offset.y)) { [self release]; return nil; }
  _size = NSMakeSize(ceil(_size.width), ceil(_size.height));
  _config = config; _image = [image retain]; _offset = offset; _scale = 120;
  _outputs = [NSMutableSet new];
  _surface = wl_compositor_create_surface(config->compositor);
  if (!_surface) { [self release]; return nil; }
  wl_surface_add_listener(_surface, &surfaceListener, self);
  if (config->viewporter) _viewport = wp_viewporter_get_viewport(config->viewporter, _surface);
  if (_viewport && config->fractional_manager) {
    _fractional = wp_fractional_scale_manager_v1_get_fractional_scale(config->fractional_manager, _surface);
    wp_fractional_scale_v1_add_listener(_fractional, &fractionalListener, self);
  }
  [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(outputsChanged:)
    name:NSApplicationDidChangeScreenParametersNotification object:nil];
  return self;
}
- (void)dealloc
{
  [[NSNotificationCenter defaultCenter] removeObserver:self];
  if (_fractional) wp_fractional_scale_v1_destroy(_fractional);
  if (_viewport) wp_viewport_destroy(_viewport);
  if (_surface) wl_surface_destroy(_surface);
  destroyShmBuffer(_buffer);
  [_outputs release]; [_image release];
  [super dealloc];
}
- (struct wl_surface *)surface { return _surface; }
- (void)render
{
  if (!_started) return;
  unsigned version = wl_surface_get_version(_surface), scale = _scale;
  if (!_viewport) scale = version >= 3 ? ((scale + 119) / 120) * 120 : 120;
  uint64_t pixels = (uint64_t)ns_buffer_extent(_size.width, scale) * ns_buffer_extent(_size.height, scale);
  if (pixels > 64 * 1024 * 1024 / 4) return;
  struct pool_buffer *next = WaylandImageBuffer(_config, _image, _size, scale);
  if (!next) return;
  if (version >= 3) wl_surface_set_buffer_scale(_surface, _viewport ? 1 : scale / 120);
  if (_viewport) wp_viewport_set_destination(_viewport, _size.width, _size.height);
  /* Surface offsets are deltas. Apply the image's logical hotspot once. */
  int x = _offsetApplied ? 0 : round(_offset.x), y = _offsetApplied ? 0 : round(_offset.y);
  if (version >= 5) wl_surface_offset(_surface, x, y);
  wl_surface_attach(_surface, next->buffer, version >= 5 ? 0 : x, version >= 5 ? 0 : y);
  wl_surface_damage(_surface, 0, 0, INT32_MAX, INT32_MAX);
  wl_surface_commit(_surface); wl_display_flush(_config->display);
  _offsetApplied = YES;
  /* Submitted image buffers are immutable, just like custom cursor buffers. */
  destroyShmBuffer(_buffer); _buffer = next;
}
- (void)start { _started = YES; [self render]; }
- (void)preferredScale:(unsigned)scale
{
  if (!scale || scale == _scale) return;
  _scale = scale; [self render];
}
- (void)output:(struct wl_output *)object entered:(BOOL)entered
{
  struct output *output = object ? wl_output_get_user_data(object) : NULL;
  if (!output || _fractional) return;
  NSNumber *identity = [NSNumber numberWithUnsignedInt:output->server_output_id];
  if (entered) [_outputs addObject:identity]; else [_outputs removeObject:identity];
  [self outputsChanged:nil];
}
- (void)outputsChanged:(NSNotification *)notification
{
  if (_fractional) return;
  unsigned scale = 120;
  struct output *output;
  wl_list_for_each(output, &_config->output_list, link)
    if ([_outputs containsObject:[NSNumber numberWithUnsignedInt:output->server_output_id]])
      scale = MAX(scale, output->scale * 120);
  [self preferredScale:scale];
}
@end
