/* Compositor-mediated AppKit placement. LGPL-2.0-or-later. */
#include "wayland/WaylandServer.h"
#include <AppKit/AppKit.h>

static void work_areas_reset(void *data, struct nextspace_application_v1 *object)
{
  WaylandConfig *config = data;
  if (!config->pending_work_areas) config->pending_work_areas = [NSMutableDictionary new];
  [config->pending_work_areas removeAllObjects];
}
static void work_area(void *data, struct nextspace_application_v1 *object, const char *name,
    int32_t x, int32_t y, int32_t width, int32_t height)
{
  WaylandConfig *config = data;
  if (name && width > 0 && height > 0)
    [config->pending_work_areas setObject:[NSValue valueWithRect:NSMakeRect(x, y, width, height)]
      forKey:[NSString stringWithUTF8String:name]];
}
static void work_areas_done(void *data, struct nextspace_application_v1 *object)
{
  WaylandConfig *config = data;
  if ([config->work_areas isEqualToDictionary:config->pending_work_areas]) return;
  [config->work_areas release];
  config->work_areas = [config->pending_work_areas copy];
  WaylandOutputsChanged(config);
}
static const struct nextspace_application_v1_listener manager_listener = {
  .work_areas_reset = work_areas_reset, .work_area = work_area, .work_areas_done = work_areas_done
};
void WaylandSetupApplicationManager(WaylandConfig *config)
{
  if (nextspace_application_v1_get_version(config->application_manager) >= 6)
    nextspace_application_v1_add_listener(config->application_manager, &manager_listener, config);
}
#include <Foundation/NSNotificationQueue.h>

@interface NSWindow (WaylandPolicy)
- (void)_backendSetMiniaturized:(BOOL)minimized;
@end

void WaylandReportPosition(struct window *w)
{
  NSWindow *window = GSWindowWithNumber(w->window_id);
  if (!window || w->terminated || (!w->application_window && !w->popup)) return;
  NSRect frame = [w->instance windowbounds:w->window_id];
  if (NSEqualPoints([window frame].origin, frame.origin)) return;
  NSEvent *event = [NSEvent otherEventWithType:NSAppKitDefined
    location:NSZeroPoint modifierFlags:0 timestamp:0 windowNumber:w->window_id
    context:GSCurrentContext() subtype:GSAppKitWindowMoved data1:frame.origin.x data2:frame.origin.y];
  [window sendEvent:event];
}

void WaylandReportScreen(struct window *w)
{
  if (!w || w->terminated || !w->output) return;
  if (w->output->xdg_output && !w->output->logical_geometry) return;
  int screen = w->output->server_output_id;
  NSRect frame = [w->instance boundsForScreen:screen];
  if (w->screen_reported && w->reported_screen == screen && NSEqualRects(w->reported_screen_frame, frame)) return;
  w->screen_reported = YES; w->reported_screen = screen; w->reported_screen_frame = frame;
  NSWindow *window = GSWindowWithNumber(w->window_id);
  if (window) [[NSNotificationCenter defaultCenter]
    postNotificationName:NSWindowDidChangeScreenNotification object:window];
}

void WaylandSetPosition(struct window *w, float x, float y)
{
  WaylandConfig *config = w->wlconfig;
  int root = w->window_id;
  float dx = x - w->pos_x, dy = y - w->pos_y;
  w->pos_x = x; w->pos_y = y;
  NSArray *numbers = WaylandWindowNumbers(config);
  NSMutableArray *moved = [NSMutableArray arrayWithObject:[NSNumber numberWithInt:root]];
  /* Popups follow their parent scene tree without another configure event. */
  for (NSNumber *number in numbers) {
    struct window *child = get_window_with_id(config, [number intValue]);
    if (!child || !child->popup || child == w) continue;
    struct window *parent = child;
    NSUInteger depth;
    for (depth = 0; depth < [numbers count]; depth++) {
      parent = get_window_with_id(config, parent->parent_id);
      if (!parent) break;
      if (parent->window_id == root) {
        child->pos_x += dx; child->pos_y += dy;
        [moved addObject:number];
        break;
      }
    }
  }
  /* AppKit callbacks may close any of these windows. Re-resolve every ID. */
  for (NSNumber *number in moved) {
    struct window *window = get_window_with_id(config, [number intValue]);
    if (window) WaylandReportPosition(window);
  }
}

static void resolve_output(struct window *w)
{
  if (!w->preferred_output_name) return;
  struct output *o;
  wl_list_for_each(o, &w->wlconfig->output_list, link) {
    if (o->name && strcmp(o->name, w->preferred_output_name) == 0) {
      w->output = o;
      if (!w->fractional_scale) WaylandSetScale(w, MAX(1, o->scale) * 120);
      break;
    }
  }
}

void WaylandOutputsChanged(WaylandConfig *config)
{
  [NSScreen resetScreens];
  WaylandCursorOutputsChanged(config);
  for (NSNumber *number in WaylandWindowNumbers(config)) {
    struct window *w = get_window_with_id(config, [number intValue]);
    if (w) resolve_output(w);
    w = get_window_with_id(config, [number intValue]);
    if (w) WaylandReportPosition(w);
    w = get_window_with_id(config, [number intValue]);
    if (w) WaylandReportScreen(w);
  }
  if (NSApp) [[NSNotificationQueue defaultQueue] enqueueNotification:
    [NSNotification notificationWithName:NSApplicationDidChangeScreenParametersNotification object:NSApp]
    postingStyle:NSPostASAP coalesceMask:NSNotificationCoalescingOnName
    forModes:[NSArray arrayWithObjects:NSDefaultRunLoopMode, NSConnectionReplyMode,
      NSModalPanelRunLoopMode, NSEventTrackingRunLoopMode, nil]];
}

static void position(void *data, struct nextspace_window_v1 *object, int32_t x, int32_t y)
{
  struct window *w = data;
  WaylandSetPosition(w, x, y);
}

static void preferred_output(void *data, struct nextspace_window_v1 *object, const char *name)
{
  struct window *w = data;
  WaylandConfig *config = w->wlconfig;
  int windowID = w->window_id;
  free(w->preferred_output_name);
  w->preferred_output_name = strdup(name);
  resolve_output(w);
  WaylandReportScreen(get_window_with_id(config, windowID));
}

static void closed(void *data, struct nextspace_window_v1 *object)
{
  struct window *w = data;
  nextspace_window_v1_destroy(object);
  w->application_window = NULL;
  [GSWindowWithNumber(w->window_id) orderOut:nil];
}
static void minimized(void *data, struct nextspace_window_v1 *object, uint32_t minimized)
{
  struct window *w = data;
  if (w->minimized == (minimized != 0)) return;
  w->minimized = minimized != 0;
  [GSWindowWithNumber(w->window_id) _backendSetMiniaturized:minimized != 0];
}
static void drag_context(void *data, struct nextspace_window_v1 *object, struct wl_surface *surface,
    uint32_t identity, uint32_t phase, uint32_t local, wl_fixed_t x, wl_fixed_t y)
{
  WaylandDragContext(surface, identity, phase, local != 0,
    NSMakePoint(wl_fixed_to_double(x), wl_fixed_to_double(y)));
}

static void finish_color_pick(WaylandConfig *config, NSColor *selected)
{
  NSColorPanel *panel = config->color_pick_panel;
  NSColor *original = config->color_pick_original;
  config->color_pick_panel = config->color_pick_original = nil;
  config->color_pick_window = 0;
  /* Application color callbacks may close windows or start another pick. */
  @try { [panel setColor:selected ? selected : original]; }
  @finally { [panel release]; [original release]; }
}

void WaylandAbandonColorPick(WaylandConfig *config, int window_id)
{
  if (!config->color_pick_panel || (window_id && config->color_pick_window != window_id)) return;
  struct window *w = get_window_with_id(config, config->color_pick_window);
  if (w && w->application_window)
    nextspace_window_v1_cancel_color_pick(w->application_window, config->color_pick_id);
  /* Surface teardown cannot invoke application callbacks. The panel's next
   * run-loop turn restores its color while normal close processing completes. */
  NSColorPanel *panel = config->color_pick_panel;
  NSColor *original = config->color_pick_original;
  config->color_pick_panel = config->color_pick_original = nil;
  config->color_pick_window = 0;
  if (window_id) [panel performSelector:@selector(setColor:) withObject:original afterDelay:0];
  [panel release]; [original release];
}

static void color_pick(void *data, struct nextspace_window_v1 *object,
    uint32_t request_id, uint32_t phase, uint32_t red, uint32_t green, uint32_t blue)
{
  struct window *w = data;
  WaylandConfig *config = w->wlconfig;
  if (!config->color_pick_panel || config->color_pick_window != w->window_id ||
      config->color_pick_id != request_id) return;
  if (phase == NEXTSPACE_WINDOW_V1_COLOR_PICK_PHASE_PREVIEW) {
    NSColorPanel *panel = [config->color_pick_panel retain];
    @try { [panel setColor:[NSColor colorWithDeviceRed:red/255.0 green:green/255.0 blue:blue/255.0 alpha:1]]; }
    @finally { [panel release]; }
  } else if (phase == NEXTSPACE_WINDOW_V1_COLOR_PICK_PHASE_SELECTED) {
    finish_color_pick(config, [NSColor colorWithDeviceRed:red/255.0 green:green/255.0 blue:blue/255.0 alpha:1]);
  } else {
    finish_color_pick(config, nil);
    if (phase == NEXTSPACE_WINDOW_V1_COLOR_PICK_PHASE_UNAVAILABLE) NSBeep();
  }
}
static const struct nextspace_window_v1_listener application_listener = {
  .position = position, .preferred_output = preferred_output, .closed = closed, .minimized = minimized,
  .drag_context = drag_context, .color_pick = color_pick
};

void WaylandUpdateTitleState(struct window *w)
{
  if (w->application_window && nextspace_window_v1_get_version(w->application_window) >= 7)
    nextspace_window_v1_set_title_state(w->application_window, w->title_state);
}

void WaylandUpdateWindowHints(struct window *w)
{
  WaylandUpdateTitleState(w);
  WaylandUpdateFrameMetrics(w);
  if (w->application_window && nextspace_window_v1_get_version(w->application_window) >= 7)
    nextspace_window_v1_set_document_edited(w->application_window,
      [GSWindowWithNumber(w->window_id) isDocumentEdited]);
  if (w->application_window && nextspace_window_v1_get_version(w->application_window) >= 3)
  {
    NSWindow *window = GSWindowWithNumber(w->window_id);
    unsigned titleHeight = MAX(0, MIN(128, w->frame.top));
    nextspace_window_v1_set_metadata(w->application_window, w->window_id,
      [window styleMask] & ~NSFullScreenWindowMask, titleHeight);
    nextspace_window_v1_set_level(w->application_window, w->level);
  }
  if (w->application_window && nextspace_window_v1_get_version(w->application_window) >= 2)
    nextspace_window_v1_set_accepts_focus(w->application_window,
      w->level != NSMainMenuWindowLevel && w->level != NSSubmenuWindowLevel &&
      [GSWindowWithNumber(w->window_id) canBecomeKeyWindow]);
}

void WaylandSetupApplicationWindow(struct window *w)
{
  if (!w->wlconfig->application_manager) return;
  w->application_window = nextspace_application_v1_get_window(w->wlconfig->application_manager, w->surface);
  nextspace_window_v1_add_listener(w->application_window, &application_listener, w);
  WaylandUpdateWindowHints(w);
  nextspace_window_v1_set_position(w->application_window, w->pos_x, w->pos_y);
}

@implementation WaylandServer (InteractiveColorPick)
- (BOOL)GSpickScreenColor:(NSColorPanel *)panel
{
  if (wlconfig->color_pick_panel) return YES;
  struct window *w = get_window_with_id(wlconfig, [panel windowNumber]);
  uint32_t serial = wlconfig->color_pick_serial;
  if (!w || !w->application_window || nextspace_window_v1_get_version(w->application_window) < 8 ||
      !serial || wlconfig->color_pick_input_window != w->window_id) {
    NSBeep(); return YES;
  }
  wlconfig->color_pick_serial = 0;
  WaylandCancelRepeat(wlconfig);
  wlconfig->color_pick_panel = [panel retain];
  wlconfig->color_pick_original = [[panel color] retain];
  wlconfig->color_pick_window = w->window_id;
  if (++wlconfig->next_color_pick_id == 0) ++wlconfig->next_color_pick_id;
  wlconfig->color_pick_id = wlconfig->next_color_pick_id;
  nextspace_window_v1_begin_color_pick(w->application_window, wlconfig->color_pick_id, serial);
  wl_display_flush(wlconfig->display);
  return YES;
}
@end
