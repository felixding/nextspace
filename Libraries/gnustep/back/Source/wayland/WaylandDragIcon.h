/* Native drag-image surface. LGPL-2.0-or-later. */
#include "wayland/WaylandServer.h"

@interface WaylandDragIcon : NSObject
{
  WaylandConfig *_config;
  NSImage *_image;
  NSSize _size;
  NSPoint _offset;
  struct wl_surface *_surface;
  struct wp_viewport *_viewport;
  struct wp_fractional_scale_v1 *_fractional;
  struct pool_buffer *_buffer;
  NSMutableSet *_outputs;
  unsigned _scale;
  BOOL _started, _offsetApplied;
}
- (id)initWithImage:(NSImage *)image offset:(NSPoint)offset config:(WaylandConfig *)config;
- (struct wl_surface *)surface;
- (void)start;
- (void)output:(struct wl_output *)output entered:(BOOL)entered;
- (void)preferredScale:(unsigned)scale;
@end
