/* Density-aware cursor surfaces. LGPL-2.0-or-later. */
#include "wayland/WaylandServer.h"
#include "wayland/nextspace-geometry.h"
#include "cairo/WaylandCairoShmSurface.h"
#include "cairo/CairoContext.h"
#include "cairo/CairoGState.h"
#include <AppKit/AppKit.h>
#include <time.h>

/* The timer owns this adapter, never the display server. Cancel it before the
   configuration is freed, including when its pointer focus disappears. */
@interface WaylandCursorAnimator : NSObject
{
  WaylandConfig *config;
}
- (id)initWithConfig:(WaylandConfig *)value;
- (void)advance:(NSTimer *)timer;
@end
@implementation WaylandCursorAnimator
- (id)initWithConfig:(WaylandConfig *)value
{
  if ((self = [super init])) config = value;
  return self;
}
- (void)advance:(NSTimer *)timer { WaylandRefreshCursor(config); }
@end

static uint64_t cursorMilliseconds(void)
{
  struct timespec now;
  clock_gettime(CLOCK_MONOTONIC, &now);
  return (uint64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

static void stopCursorTimer(WaylandConfig *config)
{
  [config->cursor_timer invalidate];
  [config->cursor_timer release];
  config->cursor_timer = nil;
}

static void scheduleCursorFrame(WaylandConfig *config, uint32_t delay)
{
  if (!config->cursor_animator)
    config->cursor_animator = [[WaylandCursorAnimator alloc] initWithConfig:config];
  config->cursor_timer = [[NSTimer alloc] initWithFireDate:
    [NSDate dateWithTimeIntervalSinceNow:delay / 1000.0] interval:0
    target:config->cursor_animator selector:@selector(advance:) userInfo:nil repeats:NO];
  for (NSString *mode in [NSArray arrayWithObjects:NSDefaultRunLoopMode,
       NSModalPanelRunLoopMode, NSEventTrackingRunLoopMode, NSConnectionReplyMode, nil])
    [[NSRunLoop currentRunLoop] addTimer:config->cursor_timer forMode:mode];
}

static struct wl_cursor_image *cursorFrame(struct wl_cursor *theme, uint64_t elapsed, uint32_t *delay)
{
  if (!theme->image_count) return NULL;
  if (theme->image_count == 1) return theme->images[0];
  uint64_t duration = 0;
  unsigned index;
  for (index = 0; index < theme->image_count; index++)
    duration += MAX(1, theme->images[index]->delay);
  elapsed %= duration;
  for (index = 0; index < theme->image_count; index++) {
    uint32_t frameDuration = MAX(1, theme->images[index]->delay);
    if (elapsed < frameDuration) {
      *delay = frameDuration - elapsed;
      return theme->images[index];
    }
    elapsed -= frameDuration;
  }
  return NULL;
}

/* Draw image representations directly into a transparent, offscreen surface.
   This also lets vector/custom representations rerender at the target density. */
@interface WaylandImageSurface : CairoSurface
{
  NSSize logicalSize;
}
- (id)initWithBuffer:(struct pool_buffer *)buffer size:(NSSize)size scale:(CGFloat)scale;
@end
@implementation WaylandImageSurface
- (id)initWithBuffer:(struct pool_buffer *)buffer size:(NSSize)size scale:(CGFloat)scale
{
  if ((self = [super init])) {
    logicalSize = size;
    _surface = cairo_surface_reference(buffer->surface);
    cairo_surface_set_device_scale(_surface, scale, scale);
  }
  return self;
}
- (NSSize)size { return logicalSize; }
- (BOOL)isDrawingToScreen { return NO; }
@end

static struct wl_cursor *themeCursor(WaylandConfig *config, const char *name, unsigned size)
{
  if (!config->cursor_themes[size])
    config->cursor_themes[size] = wl_cursor_theme_load(getenv("XCURSOR_THEME"), size, config->shm);
  return config->cursor_themes[size] ?
    wl_cursor_theme_get_cursor(config->cursor_themes[size], name) : NULL;
}

struct pool_buffer *WaylandImageBuffer(WaylandConfig *config, NSImage *image, NSSize size, unsigned scale)
{
  struct pool_buffer *buffer = createShmBuffer(ns_buffer_extent(size.width, scale),
    ns_buffer_extent(size.height, scale), config->shm);
  if (!buffer) return NULL;
  WaylandImageSurface *surface = [[WaylandImageSurface alloc]
    initWithBuffer:buffer size:size scale:scale / 120.0];
  CairoContext *context = [[CairoContext alloc] initWithContextInfo:nil];
  [(CairoGState *)[context currentGState] GSSetSurface:surface :0 :size.height];
  [NSGraphicsContext saveGraphicsState];
  @try {
    [NSGraphicsContext setCurrentContext:context];
    NSDictionary *device = [NSDictionary dictionaryWithObject:
      [NSValue valueWithSize:NSMakeSize(72.0 * scale / 120, 72.0 * scale / 120)]
      forKey:NSDeviceResolution];
    NSImageRep *rep = [image bestRepresentationForDevice:device];
    [rep drawInRect:NSMakeRect(0, 0, size.width, size.height)];
    cairo_surface_flush(buffer->surface);
  } @finally {
    [NSGraphicsContext restoreGraphicsState];
    [context release]; [surface release];
  }
  return buffer;
}

void WaylandCursorOutputsChanged(WaylandConfig *config)
{
  if (config->cursor_fractional_scale) return;
  unsigned scale = 120;
  struct output *output;
  wl_list_for_each(output, &config->output_list, link) {
    if ([config->cursor_outputs containsObject:[NSNumber numberWithUnsignedInt:output->server_output_id]])
      scale = MAX(scale, output->scale * 120);
  }
  if (config->cursor_scale120 == scale) return;
  config->cursor_scale120 = scale;
  WaylandRefreshCursor(config);
}

static void cursor_enter(void *data, struct wl_surface *surface, struct wl_output *object)
{
  WaylandConfig *config = data;
  struct output *output = object ? wl_output_get_user_data(object) : NULL;
  if (!output) return;
  [config->cursor_outputs addObject:[NSNumber numberWithUnsignedInt:output->server_output_id]];
  WaylandCursorOutputsChanged(config);
}
static void cursor_leave(void *data, struct wl_surface *surface, struct wl_output *object)
{
  WaylandConfig *config = data;
  struct output *output = object ? wl_output_get_user_data(object) : NULL;
  if (!output) return;
  [config->cursor_outputs removeObject:[NSNumber numberWithUnsignedInt:output->server_output_id]];
  WaylandCursorOutputsChanged(config);
}
static const struct wl_surface_listener cursor_surface_listener = {.enter = cursor_enter, .leave = cursor_leave};
static void cursor_preferred(void *data, struct wp_fractional_scale_v1 *object, uint32_t scale)
{
  WaylandConfig *config = data;
  if (!scale || scale == config->cursor_scale120) return;
  config->cursor_scale120 = scale;
  WaylandRefreshCursor(config);
}
static const struct wp_fractional_scale_v1_listener cursor_fractional_listener = {.preferred_scale = cursor_preferred};

void WaylandRefreshCursor(WaylandConfig *config)
{
  stopCursorTimer(config);
  struct cursor *cursor = config->cursor;
  if (!cursor || !config->pointer.wlpointer || !config->pointer.focus || !config->cursor_enter_serial) return;
  if (config->cursor_hidden) {
    wl_pointer_set_cursor(config->pointer.wlpointer, config->cursor_enter_serial, NULL, 0, 0);
    wl_display_flush(config->display);
    return;
  }
  if (!config->cursor_surface) {
    config->cursor_surface = wl_compositor_create_surface(config->compositor);
    config->cursor_outputs = [NSMutableSet new];
    config->cursor_scale120 = 120;
    wl_surface_add_listener(config->cursor_surface, &cursor_surface_listener, config);
    if (config->viewporter)
      config->cursor_viewport = wp_viewporter_get_viewport(config->viewporter, config->cursor_surface);
    if (config->cursor_viewport && config->fractional_manager) {
      config->cursor_fractional_scale = wp_fractional_scale_manager_v1_get_fractional_scale(
        config->fractional_manager, config->cursor_surface);
      wp_fractional_scale_v1_add_listener(config->cursor_fractional_scale, &cursor_fractional_listener, config);
    }
  }
  unsigned scale = config->cursor_scale120;
  unsigned version = wl_proxy_get_version((struct wl_proxy *)config->cursor_surface);
  if (!config->cursor_viewport) scale = version >= 3 ? ((scale + 119) / 120) * 120 : 120;
  struct wl_buffer *buffer;
  uint32_t delay = 0;
  NSSize size = cursor->size;
  NSPoint hotspot = cursor->hotspot;
  if (cursor->image) {
    if (!cursor->custom || cursor->scale120 != scale) {
      struct pool_buffer *next = WaylandImageBuffer(config, cursor->image, cursor->size, scale);
      if (!next) return;
      /* These immutable shm buffers are never reused or repainted after attach.
         The server keeps its mapping if it still needs the destroyed buffer. */
      destroyShmBuffer(cursor->custom);
      cursor->custom = next; cursor->scale120 = scale;
    }
    buffer = cursor->custom->buffer;
  } else {
    unsigned pixels = MIN(WAYLAND_CURSOR_MAX_SIZE, MAX(1, ns_buffer_extent(WAYLAND_CURSOR_SIZE, scale)));
    struct wl_cursor *theme = themeCursor(config, cursor->name, pixels);
    if (!theme) return;
    uint64_t elapsed = cursorMilliseconds() - cursor->animation_start;
    struct wl_cursor_image *frame = cursorFrame(theme, elapsed, &delay);
    if (!frame) return;
    /* Themes can have fewer density variants, or different frame dimensions.
       Their base representation defines logical geometry at every density. */
    struct wl_cursor *base = themeCursor(config, cursor->name, WAYLAND_CURSOR_SIZE);
    uint32_t ignored = 0;
    struct wl_cursor_image *logical = base ? cursorFrame(base, elapsed, &ignored) : NULL;
    if (!logical) return;
    /* A third-party theme may only supply a smaller nearest-size match. Prefer
       its next integer-density representation over enlarging that buffer. */
    if (frame->width < ns_buffer_extent(logical->width, scale) ||
        frame->height < ns_buffer_extent(logical->height, scale)) {
      unsigned fallback = MIN(WAYLAND_CURSOR_MAX_SIZE,
        WAYLAND_CURSOR_SIZE * ((scale + 119) / 120));
      theme = themeCursor(config, cursor->name, fallback);
      if (!theme || !(frame = cursorFrame(theme, elapsed, &delay))) return;
    }
    buffer = wl_cursor_image_get_buffer(frame);
    size = NSMakeSize(logical->width, logical->height);
    hotspot = NSMakePoint(logical->hotspot_x, logical->hotspot_y);
  }
  if (!buffer) return;
  if (version >= 3) wl_surface_set_buffer_scale(config->cursor_surface,
    config->cursor_viewport ? 1 : scale / 120);
  if (config->cursor_viewport)
    wp_viewport_set_destination(config->cursor_viewport, size.width, size.height);
  wl_pointer_set_cursor(config->pointer.wlpointer, config->cursor_enter_serial,
    config->cursor_surface, hotspot.x, hotspot.y);
  wl_surface_attach(config->cursor_surface, buffer, 0, 0);
  wl_surface_damage(config->cursor_surface, 0, 0, INT32_MAX, INT32_MAX);
  wl_surface_commit(config->cursor_surface);
  wl_display_flush(config->display);
  if (delay) scheduleCursorFrame(config, delay);
}

void WaylandFinishCursor(WaylandConfig *config)
{
  stopCursorTimer(config);
  [config->cursor_animator release]; config->cursor_animator = nil;
  if (config->cursor_fractional_scale) wp_fractional_scale_v1_destroy(config->cursor_fractional_scale);
  if (config->cursor_viewport) wp_viewport_destroy(config->cursor_viewport);
  if (config->cursor_surface) wl_surface_destroy(config->cursor_surface);
  [config->cursor_outputs release];
  unsigned i;
  for (i = 1; i <= WAYLAND_CURSOR_MAX_SIZE; i++)
    if (config->cursor_themes[i]) wl_cursor_theme_destroy(config->cursor_themes[i]);
}

@implementation WaylandServer (CursorImages)
- (void)hidecursor { wlconfig->cursor_hidden = YES; WaylandRefreshCursor(wlconfig); }
- (void)showcursor { wlconfig->cursor_hidden = NO; WaylandRefreshCursor(wlconfig); }
- (void)standardcursor:(int)style :(void **)cid
{
  [self initializeMouseIfRequired];
  const char *name = NULL;
  *cid = NULL;
  switch (style) {
    case GSArrowCursor: name = "left_ptr"; break;
    case GSIBeamCursor: name = "xterm"; break;
    case GSDragLinkCursor: name = "dnd-link"; break;
    case GSOperationNotAllowedCursor: name = "X_cursor"; break;
    case GSDragCopyCursor: name = "dnd-copy"; break;
    case GSPointingHandCursor: name = "hand"; break;
    case GSOpenHandCursor: name = "grab"; break;
    case GSClosedHandCursor: name = "grabbing"; break;
    case GSContextualMenuCursor: name = "context-menu"; break;
    case GSResizeLeftCursor: name = "left_side"; break;
    case GSResizeRightCursor: name = "right_side"; break;
    case GSResizeLeftRightCursor: name = "sb_h_double_arrow"; break;
    case GSCrosshairCursor: name = "crosshair"; break;
    case GSResizeUpCursor: name = "top_side"; break;
    case GSResizeDownCursor: name = "bottom_side"; break;
    case GSResizeUpDownCursor: name = "sb_v_double_arrow"; break;
    case GSDisappearingItemCursor: name = "pirate"; break;
    default: break;
  }
  if (!name) return;
  struct wl_cursor *theme = themeCursor(wlconfig, name, WAYLAND_CURSOR_SIZE);
  if (!theme) return;
  struct cursor *cursor = calloc(1, sizeof(*cursor));
  if (!cursor) return;
  cursor->name = name;
  cursor->size = NSMakeSize(theme->images[0]->width, theme->images[0]->height);
  cursor->hotspot = NSMakePoint(theme->images[0]->hotspot_x, theme->images[0]->hotspot_y);
  *cid = cursor;
}
- (void)imagecursor:(NSPoint)hotspot :(NSImage *)image :(void **)cid
{
  [self initializeMouseIfRequired];
  *cid = NULL;
  NSSize size = [image size];
  if (!isfinite(size.width) || !isfinite(size.height) || size.width <= 0 || size.height <= 0 ||
      size.width > 512 || size.height > 512 || !isfinite(hotspot.x) || !isfinite(hotspot.y)) return;
  struct cursor *cursor = calloc(1, sizeof(*cursor));
  if (!cursor) return;
  cursor->image = [image retain];
  cursor->size = NSMakeSize(ceil(size.width), ceil(size.height));
  cursor->hotspot = NSMakePoint(MAX(0, MIN(cursor->size.width - 1, hotspot.x)),
    MAX(0, MIN(cursor->size.height - 1, hotspot.y)));
  *cid = cursor;
}
- (void)setcursor:(void *)cursor
{
  if (cursor && wlconfig->cursor != cursor)
    ((struct cursor *)cursor)->animation_start = cursorMilliseconds();
  wlconfig->cursor = cursor;
  WaylandRefreshCursor(wlconfig);
}
- (void)freecursor:(void *)cid
{
  struct cursor *cursor = cid;
  if (!cursor) return;
  if (wlconfig->cursor == cursor) {
    BOOL hidden = wlconfig->cursor_hidden;
    [self hidecursor]; wlconfig->cursor = NULL; wlconfig->cursor_hidden = hidden;
  }
  [cursor->image release];
  destroyShmBuffer(cursor->custom);
  free(cursor);
}
- (void)setcursorcolor:(NSColor *)foreground :(NSColor *)background :(void *)cursor
{ [self recolorcursor:foreground :background :cursor]; [self setcursor:cursor]; }
- (void)recolorcursor:(NSColor *)foreground :(NSColor *)background :(void *)cursor
{ NSDebugLog(@"Wayland cursor recoloring is unsupported"); }
@end
