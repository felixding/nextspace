/* 
   WaylandServer - Wayland Server Class

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

#include "config.h"
#include <AppKit/AppKitExceptions.h>
#include <AppKit/NSApplication.h>
#include <AppKit/NSGraphics.h>
#include <AppKit/DPSOperators.h>
#include <AppKit/NSEvent.h>
#include <AppKit/NSWindow.h>
#include <AppKit/NSScreen.h>
#include <AppKit/NSMenu.h>
#include <Foundation/NSConnection.h>
#include <Foundation/NSRunLoop.h>
#include <Foundation/NSException.h>
#include <Foundation/NSDebug.h>
#include <Foundation/NSValue.h>

#include <unistd.h>
#include <errno.h>
#include <xkbcommon/xkbcommon.h>
#include <linux/input.h>
#include <sys/eventfd.h>
#include <sys/mman.h>

#include "wayland/WaylandServer.h"
#include "wayland/nextspace-geometry.h"
#include "wayland/WaylandInputServer.h"
#ifdef HAVE_EGL
#include "wayland/WaylandOpenGL.h"
#endif

extern const struct wl_output_listener output_listener;

extern const struct wl_seat_listener seat_listener;

static void signalEventWakeup(int fd)
{
  if (fd < 0) return;
  uint64_t pending = 1;
  ssize_t written;
  do written = write(fd, &pending, sizeof(pending));
  while (written < 0 && errno == EINTR);
  if (written < 0 && errno != EAGAIN)
    [NSException raise:NSWindowServerCommunicationException format:@"Unable to signal event wakeup"];
}

static void drainEventWakeup(int fd)
{
  if (fd < 0) return;
  uint64_t pending;
  while (read(fd, &pending, sizeof(pending)) < 0 && errno == EINTR) {}
}

static NSArray *eventRunLoopModes(void)
{
  return [NSArray arrayWithObjects:NSDefaultRunLoopMode, NSConnectionReplyMode,
    NSModalPanelRunLoopMode, NSEventTrackingRunLoopMode, nil];
}

static void
shm_format(void *data, struct wl_shm *wl_shm, uint32_t format)
{}

struct wl_shm_listener shm_listener = {shm_format};

extern const struct xdg_surface_listener xdg_surface_listener;

extern const struct xdg_toplevel_listener xdg_toplevel_listener;

extern const struct xdg_wm_base_listener wm_base_listener;

extern const struct zwlr_layer_surface_v1_listener layer_surface_listener;

extern const struct xdg_popup_listener xdg_popup_listener;

static void
handle_global(void *data, struct wl_registry *registry, uint32_t name,
	      const char *interface, uint32_t version)
{
  WaylandConfig *wlconfig = data;

  NSDebugLog(@"wayland: registering interface '%s'", interface);
  if (strcmp(interface, nextspace_application_v1_interface.name) == 0)
  {
      wlconfig->application_manager = wl_registry_bind(registry, name, &nextspace_application_v1_interface, MIN(version, 8));
    WaylandSetupApplicationManager(wlconfig);
  }
  else if (strcmp(interface, wp_fractional_scale_manager_v1_interface.name) == 0)
    wlconfig->fractional_manager = wl_registry_bind(registry, name,
      &wp_fractional_scale_manager_v1_interface, 1);
  else if (strcmp(interface, wp_viewporter_interface.name) == 0)
    wlconfig->viewporter = wl_registry_bind(registry, name, &wp_viewporter_interface, 1);
  else if (strcmp(interface, xdg_activation_v1_interface.name) == 0)
    wlconfig->activation = wl_registry_bind(registry, name, &xdg_activation_v1_interface, 1);
  else if (strcmp(interface, zwp_primary_selection_device_manager_v1_interface.name) == 0)
    wlconfig->primary_manager = wl_registry_bind(registry, name, &zwp_primary_selection_device_manager_v1_interface, 1);
  else if (strcmp(interface, zxdg_decoration_manager_v1_interface.name) == 0)
    wlconfig->decoration_manager = wl_registry_bind(registry, name, &zxdg_decoration_manager_v1_interface, 1);
  else if (strcmp(interface, zwp_text_input_manager_v3_interface.name) == 0)
    wlconfig->text_manager = wl_registry_bind(registry, name, &zwp_text_input_manager_v3_interface, 1);
  else if (strcmp(interface, zxdg_output_manager_v1_interface.name) == 0)
    wlconfig->output_manager = wl_registry_bind(registry, name,
      &zxdg_output_manager_v1_interface, MIN(version, 2));
  else if (strcmp(interface, xdg_wm_base_interface.name) == 0)
    {
      wlconfig->wm_base
	= wl_registry_bind(registry, name, &xdg_wm_base_interface, 1);
      xdg_wm_base_add_listener(wlconfig->wm_base, &wm_base_listener, NULL);
      NSDebugLog(@"wayland: found wm_base interface");
    }
  else if (strcmp(interface, wl_shell_interface.name) == 0)
    {
      wlconfig->shell
	= wl_registry_bind(registry, name, &wl_shell_interface, 1);
      NSDebugLog(@"wayland: found shell interface");
    }
  else if (strcmp(interface, wl_compositor_interface.name) == 0)
    {
      wlconfig->compositor
	= wl_registry_bind(registry, name, &wl_compositor_interface, MIN(version, 4));
      NSDebugLog(@"wayland: found compositor interface");
    }
  else if (strcmp(interface, wl_shm_interface.name) == 0)
    {
      wlconfig->shm = wl_registry_bind(registry, name, &wl_shm_interface, 1);
      NSDebugLog(@"wayland: found shm interface");
      wl_shm_add_listener(wlconfig->shm, &shm_listener, wlconfig);
    }
  else if (strcmp(interface, zwlr_layer_shell_v1_interface.name) == 0)
    {
      wlconfig->layer_shell
	= wl_registry_bind(registry, name, &zwlr_layer_shell_v1_interface, 1);
      NSDebugLog(@"wayland: found wlr-layer_shell interface");
    }
  else if (strcmp(interface, wl_output_interface.name) == 0)
    {
      struct output *output = (struct output *) malloc(sizeof(struct output));
      memset(output, 0, sizeof(struct output));
      output->wlconfig = wlconfig;
      output->scale = 1;
      output->output
	= wl_registry_bind(registry, name, &wl_output_interface, MIN(version, 2));
      output->server_output_id = name;
      NSDebugLog(@"wayland: found output interface");
      wl_list_insert(wlconfig->output_list.prev, &output->link);
      wlconfig->output_count++;
      wl_output_set_user_data(output->output, output);
      wl_output_add_listener(output->output, &output_listener, output);
      WaylandSetupOutput(output);
    }
  else if (strcmp(interface, wl_seat_interface.name) == 0)
    {
      wlconfig->pointer.wlpointer = NULL;
      wlconfig->seat_version = MIN(version, 5);
      wlconfig->seat
	= wl_registry_bind(wlconfig->registry, name, &wl_seat_interface, wlconfig->seat_version);
      NSDebugLog(@"wayland: found seat interface");
      wl_seat_add_listener(wlconfig->seat, &seat_listener, wlconfig);
    }
  else if (strcmp(interface, wl_data_device_manager_interface.name) == 0)
    {
      wlconfig->data_device_manager
	= wl_registry_bind(registry, name, &wl_data_device_manager_interface, MIN(version, 3));
      NSDebugLog(@"wayland: found data_device_manager interface");
    }
#ifdef HAVE_EGL
  else if (strcmp(interface, wl_subcompositor_interface.name) == 0)
    {
      wlconfig->subcompositor
	= wl_registry_bind(registry, name, &wl_subcompositor_interface, 1);
      NSDebugLog(@"wayland: found subcompositor interface");
    }
#endif
}

static void handle_global_remove(void *data, struct wl_registry *registry, uint32_t name)
{
  WaylandConfig *config = data;
  struct output *o, *next;
  wl_list_for_each_safe(o, next, &config->output_list, link) {
    if (o->server_output_id != name) continue;
    [config->cursor_outputs removeObject:[NSNumber numberWithUnsignedInt:name]];
    wl_list_remove(&o->link); config->output_count--;
    struct output *fallback = wl_list_empty(&config->output_list) ? NULL :
      wl_container_of(config->output_list.next, fallback, link);
    NSMutableArray *changed = [NSMutableArray array];
    struct window *w;
    wl_list_for_each(w, &config->window_list, link) {
      if (w->output == o) {
        w->output = fallback;
        [changed addObject:[NSNumber numberWithInt:w->window_id]];
      }
    }
    if (o->xdg_output) zxdg_output_v1_destroy(o->xdg_output);
    wl_output_destroy(o->output); free(o->make); free(o->model); free(o->name); free(o);
    WaylandOutputsChanged(config);
    for (NSNumber *number in changed) {
      int windowID = [number intValue];
      w = get_window_with_id(config, windowID);
      if (w && !w->fractional_scale && w->output) WaylandSetScale(w, MAX(1, w->output->scale) * 120);
      WaylandReportScreen(get_window_with_id(config, windowID));
    }
    break;
  }
}

static const struct wl_registry_listener registry_listener = {
    handle_global, handle_global_remove};

struct window *get_window_with_id(WaylandConfig *wlconfig, int winid) {
  /* This can return NULL. A relevant note has been added to the docstring
   * in the header. Callers should be handling this. */
  struct window *window;

  wl_list_for_each(window, &wlconfig->window_list, link) {
    if (window->window_id == winid) {
      return window;
    }
  }

  return NULL;
}

NSArray *WaylandWindowNumbers(WaylandConfig *config)
{
  NSMutableArray *numbers = [NSMutableArray array];
  struct window *window;
  wl_list_for_each(window, &config->window_list, link)
    [numbers addObject:[NSNumber numberWithInt:window->window_id]];
  return numbers;
}

double WaylandDesktopBottom(WaylandConfig *config)
{
  struct output *o;
  double bottom = 0;
  wl_list_for_each(o, &config->output_list, link)
    bottom = MAX(bottom, o->alloc_y + o->height);
  return bottom;
}

float
WaylandToNS(struct window *window, float wl_y)
{
  return ns_flip_y(wl_y, window->height, WaylandDesktopBottom(window->wlconfig));
}

int
NSToWayland(struct window *window, int ns_y)
{
  return ns_flip_y(ns_y, window->height, WaylandDesktopBottom(window->wlconfig));
}

@interface NSWindow (WaylandMenu)
- (NSMenu *)_menu;
@end

static BOOL clientOwnsZoomFrame(struct window *window)
{
  NSWindow *native = GSWindowWithNumber(window->window_id);
  SEL selector = @selector(windowWillUseStandardFrame:defaultFrame:);
  return [[native delegate] respondsToSelector:selector] || [native respondsToSelector:selector];
}

@implementation WaylandServer

/* Initialize AppKit backend */
+ (void)initializeBackend
{
  NSDebugLog(@"Initializing GNUstep Wayland backend");
  if (![NSWindow instancesRespondToSelector:@selector(_backendBackingScaleDidChange:)])
    [NSException raise:NSInternalInconsistencyException
                format:@"Wayland requires the NEXTSPACE GNUstep GUI backing patch"];
  [GSDisplayServer setDefaultServerClass:[WaylandServer class]];
}

- (id)_initWaylandContext
{
  wlconfig = (WaylandConfig *) malloc(sizeof(WaylandConfig));
  memset(wlconfig, 0, sizeof(WaylandConfig));
  wlconfig->last_window_id = 1;
  wlconfig->mouse_scroll_multiplier = 1.0f;
  wl_list_init(&wlconfig->output_list);
  wl_list_init(&wlconfig->window_list);

  wlconfig->display = wl_display_connect(NULL);
  if (!wlconfig->display)
    {
      [NSException raise:NSWindowServerCommunicationException
		  format:@"Unable to connect Wayland Server"];
    }

  wlconfig->registry = wl_display_get_registry(wlconfig->display);
  if (!wlconfig->registry)
    {
      [NSException raise:NSWindowServerCommunicationException
		  format:@"Unable to get global registry"];
    }
  wl_registry_add_listener(wlconfig->registry, &registry_listener, wlconfig);

  wl_display_dispatch(wlconfig->display);
  wl_display_roundtrip(wlconfig->display);
  struct output *o;
  wl_list_for_each(o, &wlconfig->output_list, link) WaylandSetupOutput(o);
  wl_display_roundtrip(wlconfig->display);

  /* Once the seat and the data device manager are both bound we can create
   * the data device used for drag and drop and clipboard transfers. */
  if (wlconfig->data_device_manager != NULL && wlconfig->seat != NULL
      && wlconfig->data_device == NULL)
    {
      extern const struct wl_data_device_listener data_device_listener;

      wlconfig->data_device = wl_data_device_manager_get_data_device(
	wlconfig->data_device_manager, wlconfig->seat);
      wl_data_device_add_listener(wlconfig->data_device,
	&data_device_listener, wlconfig);
      WaylandSetupPasteboard(wlconfig);
    }

  if (!wlconfig->compositor)
    {
      [NSException raise:NSWindowServerCommunicationException
		  format:@"Unable to get compositor"];
    }
  if (!wlconfig->wm_base)
    {
      /* Note: this was merged into Weston only as of Feb 2019, and is
	 probably in Weston only as of 6.0 release, therefore not in Weston
	 5.x present in Debian buster (current stable). See Weston merge request
	 !103. */
      [NSException
	 raise:NSWindowServerCommunicationException
	format:@"Unable to get xdg-shell / xdg_wm_base - your Wayland "
	       @"compositor must support the stable XDG Shell protocol"];
    }

  inputServer = [[WaylandInputServer allocWithZone: [self zone]]
                initWithConfig:wlconfig];
  [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(keyboardOptionsChanged:)
    name:NSUserDefaultsDidChangeNotification object:nil];

  return self;
}

- (void)receivedEvent:(void *)data
		 type:(RunLoopEventType)type
		extra:(void *)extra
	      forMode:(NSString *)mode
{
  if ((int)(intptr_t)data == event_wakeup_fd)
    {
      /* Keep the source ready until the waiting getter sees matching input.
         Other queued event types must not make a selective wait spin. */
      for (NSEvent *event in event_queue)
        if (waiting_event_mask & NSEventMaskFromType([event type])) return;
      drainEventWakeup(event_wakeup_fd);
      return;
    }
  if (type == ET_RDESC)
    {
      //	NSDebugLog(@"receivedEvent ET_RDESC");
      if (wl_display_dispatch(wlconfig->display) == -1)
        {
        [NSException raise:NSWindowServerCommunicationException
                format:@"Connection to Wayland Server lost"];
        }
      /* IME callbacks may not post an AppKit event. Apply them after dispatch
         in every registered mode, including synchronous service replies. */
      [inputServer synchronize];
      /* Callbacks can request a compositor move without posting an AppKit
         event. Flush before returning to a run loop that may otherwise sleep. */
      wl_display_flush(wlconfig->display);
    }
}

- (void)setupRunLoopInputSourcesForMode:(NSString *)mode
{
  NSRunLoop *currentRunLoop = [NSRunLoop currentRunLoop];
  long	     fdWaylandHandle = wl_display_get_fd(wlconfig->display);

  [currentRunLoop addEvent:(void *) fdWaylandHandle
		      type:ET_RDESC
		   watcher:(id<RunLoopEvents>) self
		   forMode:mode];
  /* Reply loops dispatch protocol callbacks without retrieving AppKit events. */
  if (![mode isEqualToString:NSConnectionReplyMode])
    [currentRunLoop addEvent:(void *)(intptr_t)event_wakeup_fd
                        type:ET_RDESC watcher:(id<RunLoopEvents>)self forMode:mode];
}

- (id)initWithAttributes:(NSDictionary *)info
{
  NSDebugLog(@"WaylandServer initWithAttributes");
  event_wakeup_fd = -1;
  [super initWithAttributes:info];
  event_wakeup_fd = eventfd(0, EFD_NONBLOCK | EFD_CLOEXEC);
  if (event_wakeup_fd < 0)
    [NSException raise:NSWindowServerCommunicationException format:@"Unable to create event wakeup"];
  [self _initWaylandContext];

  for (NSString *mode in eventRunLoopModes())
    [self setupRunLoopInputSourcesForMode:mode];

  return self;
}

- (void)textInputClientDidChange
{
  [inputServer scheduleUpdate];
}

- (NSArray *)pendingTextInputTransactions
{
  NSMutableArray *transactions = [NSMutableArray array];
  for (NSEvent *event in event_queue)
    if ([event isKindOfClass:[WaylandTextInputEvent class]])
      [transactions addObject:[(WaylandTextInputEvent *)event transaction]];
  return transactions;
}

- (void)postEvent:(NSEvent *)event atStart:(BOOL)flag
{
  [super postEvent:event atStart:flag];
  /* Protocol callbacks may run in nested loops before AppKit starts polling. */
  signalEventWakeup(event_wakeup_fd);
}

- (NSEvent *)getEventMatchingMask:(unsigned)mask beforeDate:(NSDate *)limit
                         inMode:(NSString *)mode dequeue:(BOOL)flag
{
  unsigned previous_mask = waiting_event_mask;
  waiting_event_mask = mask;
  drainEventWakeup(event_wakeup_fd);
  @try {
    for (;;) {
      [inputServer synchronize];
      NSEvent *event = [super getEventMatchingMask:mask beforeDate:limit inMode:mode dequeue:NO];
      if ([event isKindOfClass:[WaylandTextInputEvent class]]) {
        if (![inputServer canHandleEvent:(WaylandTextInputEvent *)event]) return nil;
        [super getEventMatchingMask:mask beforeDate:limit inMode:mode dequeue:YES];
        [inputServer handleEvent:(WaylandTextInputEvent *)event];
        continue;
      }
      if (!event || [event type] != NSAppKitDefined || [event subtype] != GSAppKitWindowFocusIn ||
          (wlconfig->keyboard_focus && [event windowNumber] == wlconfig->keyboard_focus->window_id)) {
        if (event && flag) [super getEventMatchingMask:mask beforeDate:limit inMode:mode dequeue:YES];
        return event;
      }
      /* Protocol callbacks can queue enter and leave before AppKit consumes the
       * enter event. Delivering that stale event would reactivate its old window.
       * Remove it even for a peek, while leaving other queued events intact. */
      [super getEventMatchingMask:mask beforeDate:limit inMode:mode dequeue:YES];
    }
  } @finally {
    waiting_event_mask = previous_mask;
    /* A nested getter may leave input for its caller's different mask. */
    if (previous_mask) signalEventWakeup(event_wakeup_fd);
  }
}

- (void)dealloc
{
  NSDebugLog(@"Destroying Wayland Server");
  NSRunLoop *loop = [NSRunLoop currentRunLoop];
  for (NSString *mode in eventRunLoopModes())
    {
      if (event_wakeup_fd >= 0)
        [loop removeEvent:(void *)(intptr_t)event_wakeup_fd type:ET_RDESC forMode:mode all:YES];
      if (wlconfig && wlconfig->display)
        [loop removeEvent:(void *)(intptr_t)wl_display_get_fd(wlconfig->display)
                     type:ET_RDESC forMode:mode all:YES];
    }
  [NSObject cancelPreviousPerformRequestsWithTarget:self];
  [[NSNotificationCenter defaultCenter] removeObserver:self];
  DESTROY(inputServer);
  if (wlconfig != NULL)
    {
      WaylandAbandonColorPick(wlconfig, 0);
      WaylandFinishCursor(wlconfig);
      WaylandCancelRepeat(wlconfig);
      [wlconfig->pasteboard_bridge performSelector:@selector(invalidate)];
      [wlconfig->pasteboard_bridge release];
      [wlconfig->primary_bridge performSelector:@selector(invalidate)];
      [wlconfig->primary_bridge release];
      [wlconfig->work_areas release];
      [wlconfig->pending_work_areas release];
      if (wlconfig->decoration_manager) zxdg_decoration_manager_v1_destroy(wlconfig->decoration_manager);
      xkb_state_unref(wlconfig->xkb.state);
      xkb_compose_state_unref(wlconfig->compose_state);
      xkb_compose_table_unref(wlconfig->compose_table);
      xkb_keymap_unref(wlconfig->xkb.keymap);
      xkb_context_unref(wlconfig->xkb_context);
      if (wlconfig->display != NULL)
	{
	  wl_display_disconnect(wlconfig->display);
	}
      free(wlconfig);
      wlconfig = NULL;
    }
  if (event_wakeup_fd >= 0) close(event_wakeup_fd);
  event_wakeup_fd = -1;
  [super dealloc];
}

- (BOOL)handlesWindowDecorations
{
  /* Keep AppKit's frame layout and drawing coordinates. Negotiated SSD
     presents only its content viewport; the compositor paints the frame. */
  return NO;
}

- (void)restrictWindow:(int)win toImage:(NSImage *)image
{
  NSDebugLog(@"restrictWindow");
}

- (NSRect)boundsForScreen:(int)screen
{
  NSDebugLog(@"boundsForScreen: %d", screen);
  struct output *output;

  wl_list_for_each(output, &wlconfig->output_list, link)
  {
    if (output->server_output_id == screen)
      {
	NSDebugLog(@"screen found: %dx%d", output->width, output->height);
	return NSMakeRect(output->alloc_x,
          ns_flip_y(output->alloc_y, output->height, WaylandDesktopBottom(wlconfig)),
          output->width, output->height);
      }
  }

  NSDebugLog(@"can't find screen");
  return NSZeroRect;
}

- (NSRect)workAreaForScreen:(int)screen
{
  struct output *output;
  wl_list_for_each(output, &wlconfig->output_list, link) {
    if (output->server_output_id != screen || !output->name) continue;
    NSValue *value = [wlconfig->work_areas objectForKey:[NSString stringWithUTF8String:output->name]];
    if (!value) break;
    NSRect area = [value rectValue];
    area.origin.y = ns_flip_y(area.origin.y, area.size.height, WaylandDesktopBottom(wlconfig));
    return area;
  }
  return NSZeroRect;
}

/* Native top-left desktop coordinates, including negative output origins.
   NSScreen frames use AppKit coordinates and cannot supply this flip origin. */
- (NSRect)logicalDesktopBounds
{
  NSRect bounds = NSZeroRect;
  BOOL first = YES;
  struct output *output;
  wl_list_for_each(output, &wlconfig->output_list, link) {
    if (output->width <= 0 || output->height <= 0) continue;
    NSRect frame = NSMakeRect(output->alloc_x, output->alloc_y, output->width, output->height);
    bounds = first ? frame : NSUnionRect(bounds, frame);
    first = NO;
  }
  return bounds;
}

/* Read-only bootstrap information. wl_output has no exact fractional per-head
   scale or stable serial; zero explicitly denotes an unavailable scale. The
   session display service supplies those fields and disabled connectors later. */
- (NSArray *)nativeOutputDescriptions
{
  NSMutableArray *heads = [NSMutableArray array];
  struct output *o;
  wl_list_for_each(o, &wlconfig->output_list, link) {
    NSDictionary *mode = [NSDictionary dictionaryWithObjectsAndKeys:
      [NSNumber numberWithInt:o->mode_width], @"width", [NSNumber numberWithInt:o->mode_height], @"height",
      [NSNumber numberWithInt:o->mode_refresh], @"refresh", [NSNumber numberWithBool:YES], @"preferred", nil];
    NSMutableDictionary *head = [[mode mutableCopy] autorelease];
    [head addEntriesFromDictionary:[NSDictionary dictionaryWithObjectsAndKeys:
      [NSNumber numberWithUnsignedInt:o->server_output_id], @"id",
      o->name ? [NSString stringWithUTF8String:o->name] : @"", @"name",
      o->make ? [NSString stringWithUTF8String:o->make] : @"", @"make",
      o->model ? [NSString stringWithUTF8String:o->model] : @"", @"model", @"", @"serial",
      [NSNumber numberWithBool:YES], @"enabled", [NSNumber numberWithBool:![heads count]], @"primary",
      [NSNumber numberWithInt:0], @"scale", [NSNumber numberWithInt:o->transform], @"transform",
      [NSNumber numberWithInt:o->alloc_x], @"x", [NSNumber numberWithInt:o->alloc_y], @"y",
      [NSNumber numberWithInt:o->width], @"logical_width", [NSNumber numberWithInt:o->height], @"logical_height",
      [NSNumber numberWithInt:o->physical_width], @"width_mm", [NSNumber numberWithInt:o->physical_height], @"height_mm",
      [NSArray arrayWithObject:mode], @"modes", nil]];
    [heads addObject:[[head copy] autorelease]];
  }
  return heads;
}

- (NSWindowDepth)windowDepthForScreen:(int)screen
{
  NSDebugLog(@"windowDepthForScreen: %d", screen);
  return (_GSRGBBitValue | 8);
}

- (const NSWindowDepth *)availableDepthsForScreen:(int)screen
{
  NSZone	*zone = NSDefaultMallocZone();
  NSWindowDepth *depths;

  NSDebugLog(@"availableDepthsForScreen");
  depths = NSZoneMalloc(zone, sizeof(NSWindowDepth) * 2);
  depths[0] = (_GSRGBBitValue | 8);
  depths[1] = 0;
  return depths;
}

- (NSArray *)screenList
{
  NSDebugLog(@"screenList");
  NSMutableArray *screens =
    [NSMutableArray arrayWithCapacity:wlconfig->output_count];
  struct output *output;

  wl_list_for_each(output, &wlconfig->output_list, link)
  {
    [screens addObject:[NSNumber numberWithInt:output->server_output_id]];
    NSDebugLog(@"adding screen with output_id=%d", output->server_output_id);
    NSDebugLog(@"output dimensions: %dx%d %dx%d", output->alloc_x,
	       output->alloc_y, output->width, output->height);
  }

  return screens;
}

- (void *)serverDevice
{
  NSDebugLog(@"serverDevice");
  return NULL;
}

- (void *)windowDevice:(int)win
{
  NSDebugLog(@"windowDevice: %d", win);
#ifdef HAVE_EGL
  return get_window_with_id(wlconfig, win);
#else
  return NULL;
#endif
}

- (void)beep
{
  NSDebugLog(@"beep");
}

#ifdef HAVE_EGL
- glContextClass
{
  return [WaylandGLContext class];
}

- glPixelFormatClass
{
  return [WaylandGLPixelFormat class];
}
#endif

@end

@implementation WaylandServer (InputMethod)

- (NSString *) inputMethodStyle
{
  return inputServer
    ? [(WaylandInputServer *) inputServer inputMethodStyle] : nil;
}

- (NSString *) fontSize: (int *)size
{
  return inputServer
    ? [(WaylandInputServer *) inputServer fontSize: size] : nil;
}

- (BOOL) clientWindowRect: (NSRect *)rect
{
  return inputServer
    ? [(WaylandInputServer *) inputServer clientWindowRect: rect] : NO;
}

- (BOOL) statusArea: (NSRect *)rect
{
  return inputServer
    ? [(WaylandInputServer *) inputServer statusArea: rect] : NO;
}

- (BOOL) preeditArea: (NSRect *)rect
{
  return inputServer
    ? [(WaylandInputServer *) inputServer preeditArea: rect] : NO;
}

- (BOOL) preeditSpot: (NSPoint *)p
{
  return inputServer
    ? [(WaylandInputServer *) inputServer preeditSpot: p] : NO;
}

- (BOOL) setStatusArea: (NSRect *)rect
{
  return inputServer
    ? [(WaylandInputServer *) inputServer setStatusArea: rect] : NO;
}

- (BOOL) setPreeditArea: (NSRect *)rect
{
  return inputServer
    ? [(WaylandInputServer *) inputServer setPreeditArea: rect] : NO;
}

- (BOOL) setPreeditSpot: (NSPoint *)p
{
  return inputServer
    ? [(WaylandInputServer *) inputServer setPreeditSpot: p] : NO;
}

@end

@implementation
WaylandServer (WindowOps)

- (int)window:(NSRect)
	frame:(NSBackingStoreType)type
	     :(unsigned int)style
	     :(int)screen
{
  NSDebugLog(@"window: screen=%d frame=%@", screen, NSStringFromRect(frame));
  struct window *window;
  struct output *output;
  int		 width;
  int		 height;
  int		 altered = 0;

  /* We're not allowed to create a zero rect window */
  if (NSWidth(frame) <= 0 || NSHeight(frame) <= 0)
    {
      NSDebugLog(@"trying to create a zero rect window");
      frame.size.width = 2;
      frame.size.height = 2;
    }

  window = malloc(sizeof(struct window));
  memset(window, 0, sizeof(struct window));

  wl_list_for_each(output, &wlconfig->output_list, link)
  {
    if (output->server_output_id == screen)
      {
	window->output = output;
	break;
      }
  }

  if (!window->output)
    {
      NSDebugLog(@"can't find screen %d", screen);
      free(window);
      return 0;
    }

  window->wlconfig = wlconfig;
  window->instance = self;
  window->is_out = 0;
  window->width = width = NSWidth(frame);
  window->height = height = NSHeight(frame);
  window->pos_x = frame.origin.x;
  window->pos_y = NSToWayland(window, frame.origin.y);
  window->window_id = wlconfig->last_window_id;
  window->title_state = NEXTSPACE_WINDOW_V1_TITLE_STATE_NORMAL;
  window->unscaled = (style & NSUnscaledWindowMask) != 0;
  window->scale120 = window->unscaled ? 120 : window->output->scale * 120;

  window->xdg_surface = NULL;
  window->toplevel = NULL;
  window->popup = NULL;
  window->layer_surface = NULL;
  window->configured = NO;

  window->buffer_needs_attach = NO;
  window->terminated = NO;

  window->moving = NO;
  window->resizing = NO;
  window->ignoreMouse = NO;
#ifdef HAVE_EGL
  window->usesOpenGL = NO;
#endif

  if (NO)
    {
      window->pos_x = 0;
      altered = 1;
    }

  NSDebugLog(@"creating new window with id=%d: pos=%fx%f, size=%fx%f",
	     window->window_id, window->pos_x, window->pos_y, window->width,
	     window->height);

  wl_list_insert(wlconfig->window_list.prev, &window->link);
  wlconfig->last_window_id++;
  wlconfig->window_count++;

  // creates a buffer for the window
  [self _setWindowOwnedByServer:(int) window->window_id];

  if (altered)
    {
      NSEvent *ev =
	[NSEvent otherEventWithType:NSAppKitDefined
			   location:NSZeroPoint
		      modifierFlags:0
			  timestamp:0
		       windowNumber:(int) window->window_id
			    context:GSCurrentContext()
			    subtype:GSAppKitWindowMoved
			      data1:window->pos_x
			      data2:WaylandToNS(window, window->pos_y)];
      [(GSWindowWithNumber(window->window_id)) sendEvent:ev];
      NSDebugLog(@"window: notifying of move=%fx%f", window->pos_x,
		 WaylandToNS(window, window->pos_y));
    }

  return window->window_id;
}

- (void)termwindow:(int)win
{
  NSDebugLog(@"termwindow: win=%d", win);
  struct window *window = get_window_with_id(wlconfig, win);

  if (window == NULL)
    return;

  [self destroyWindowShell:window];
  // FIXME should wait for buffer release before detroying it
  //
  // wl_buffer_destroy(window->buffer);
  wl_list_remove(&window->link);
  wlconfig->window_count--;
  window->terminated = YES;
  if (wlconfig->keyboard_focus == window) {
    WaylandCancelRepeat(wlconfig);
    wlconfig->keyboard_focus = NULL;
  }
  if (wlconfig->pointer.focus == window) wlconfig->pointer.focus = NULL;
  if (wlconfig->pointer.captured == window) wlconfig->pointer.captured = NULL;
  if (window->surface_refs == 0) free(window);
}

- (int)nativeWindow:(void *)
	     winref:(NSRect *)frame
		   :(NSBackingStoreType *)type
		   :(unsigned int *)style
		   :(int *)screen
{
  NSDebugLog(@"nativeWindow");
  return 0;
}

- (void)stylewindow:(unsigned int)style:(int)win
{
  struct window *window = get_window_with_id(wlconfig, win);
  if (window) WaylandUpdateWindowHints(window);
  wl_display_flush(wlconfig->display);
}

- (void)windowbacking:(NSBackingStoreType)type:(int)win
{
  NSDebugLog(@"windowbacking");
}

- (void)titlewindow:(NSString *)window_title:(int)win
{
  NSDebugLog(@"titlewindow: win=%d title=%@", win, window_title);
  if ([window_title isEqualToString: @"Window"])
    {
      return;
    }

  struct window *window = get_window_with_id(wlconfig, win);
  const char    *cString = [window_title UTF8String];

  if (window == NULL)
    return;

  if (window->toplevel)
    {
      xdg_toplevel_set_title(window->toplevel, cString);
      wl_surface_commit(window->surface);
      wl_display_flush(window->wlconfig->display);
    }
}

- (void)miniwindow:(int)win
{
  struct window *window = get_window_with_id(wlconfig, win);

  NSDebugLog(@"miniwindow");
  if (window == NULL)
    return;

  if (window->toplevel)
    {
      xdg_toplevel_set_minimized(window->toplevel);
      wl_display_flush(wlconfig->display);
    }
  else
    {
      NSDebugLog(@"trying to miniaturize a not toplevel window");
    }
}

- (BOOL)zoomwindow:(int)win
{
  struct window *window = get_window_with_id(wlconfig, win);
  if (!window || !window->toplevel || (!window->maximized && clientOwnsZoomFrame(window))) return NO;
  window->maximized = !window->maximized;
  if (window->maximized) xdg_toplevel_set_maximized(window->toplevel);
  else xdg_toplevel_unset_maximized(window->toplevel);
  wl_display_flush(wlconfig->display);
  return YES;
}

- (NSInteger)zoomstate:(int)win
{
  struct window *window = get_window_with_id(wlconfig, win);
  return window && window->toplevel && (window->maximized || !clientOwnsZoomFrame(window)) ? window->maximized : -1;
}

- (BOOL)fullscreenwindow:(int)win:(BOOL)fullscreen
{
  struct window *window = get_window_with_id(wlconfig, win);
  if (!window || !window->toplevel) return NO;
  if (fullscreen) xdg_toplevel_set_fullscreen(window->toplevel, NULL);
  else xdg_toplevel_unset_fullscreen(window->toplevel);
  wl_display_flush(wlconfig->display);
  return YES;
}

- (BOOL)handlesWindowPlacement { return YES; }

- (void)setWindowdevice:(int)winId forContext:(NSGraphicsContext *)ctxt
{
  NSDebugLog(@"[%d] setWindowdevice", winId);
  struct window *window;

  window = get_window_with_id(wlconfig, winId);
  if (window == NULL)
    return;

  // FIXME we could resize the current surface instead of creating a new one
  if (window->wcs)
    {
      NSDebugLog(@"[%d] window has already a surface", winId);
    }
  GSSetDevice(ctxt, window, 0.0, window->height);
  DPSinitmatrix(ctxt);
  DPSinitclip(ctxt);
}

- (void)orderwindow:(int)op:(int)otherWin:(int)win
{
  struct window *window = get_window_with_id(wlconfig, win);

  if (window == NULL)
    return;

  if (op == NSWindowOut)
    {
      NSDebugLog(@"[%d] orderwindow: NSWindowOut", win);
      if (window->application_window && nextspace_window_v1_get_version(window->application_window) >= 5) {
        nextspace_window_v1_set_presented(window->application_window, 0);
        window->is_out = 1;
      } else [self destroyWindowShell:window];
    }
  else
    { //  NSWindowAbove || NSWindowBelow,

      // currently it only creates a new shell for the window which results
      // in popping in front of the window manager
      NSDebugLog(@"[%d] orderwindow to: %fx%f", win, window->pos_x,
		 window->pos_y);
      if ([self windowSurfaceHasRole:window] == NO)
	{
	  [self createSurfaceShell:window];
	}
      if (window->application_window && nextspace_window_v1_get_version(window->application_window) >= 3) {
        struct window *other = get_window_with_id(wlconfig, otherWin);
        if (nextspace_window_v1_get_version(window->application_window) >= 5)
          nextspace_window_v1_set_presented(window->application_window, 1);
        window->is_out = 0;
        nextspace_window_v1_set_minimized(window->application_window, 0);
        nextspace_window_v1_order(window->application_window, op,
          other ? other->application_window : NULL);
      }
      NSRect rect = NSMakeRect(window->pos_x, window->pos_y, window->width,
			       window->height);
      [window->instance flushwindowrect:rect:window->window_id];
    }
  wl_display_flush(window->wlconfig->display);
}

- (void)movewindow:(NSPoint)loc:(int)win
{
  struct window *window = get_window_with_id(wlconfig, win);
  if (!window) return;
  window->pos_x = loc.x; window->pos_y = NSToWayland(window, loc.y);
  if (window->application_window)
    nextspace_window_v1_set_position(window->application_window, window->pos_x, window->pos_y);
  wl_display_flush(wlconfig->display);
}

- (void)placewindow:(NSRect)rect:(int)win
{
  struct window *window = get_window_with_id(wlconfig, win);

  NSDebugLog(@"[%d] placewindow: %@", win, NSStringFromRect(rect));
  if (window == NULL)
    return;

  NSRect frame;
  BOOL	 resize = NO;
  BOOL	 move = NO;

  frame = [(GSWindowWithNumber(window->window_id)) frame];
  if (NSEqualRects(rect, frame) == YES)
    return;
  if (NSEqualSizes(rect.size, frame.size) == NO)
    {
      resize = YES;
      move = YES;
    }
  if (NSEqualPoints(rect.origin, frame.origin) == NO)
    {
      move = YES;
    }



	NSDebugLog(@"[%d] placewindow: oldpos=%fx%f", win, window->pos_x,
		   window->pos_y);
	window->width = rect.size.width;
	window->height = rect.size.height;
	window->pos_x = rect.origin.x;
	window->pos_y = NSToWayland(window, rect.origin.y);
  if (window->application_window)
    nextspace_window_v1_set_position(window->application_window, window->pos_x, window->pos_y);

	[window->instance flushwindowrect:rect:window->window_id];
	if (window->xdg_surface)
	  {
      NSSize content = WaylandSurfaceSize(window);
	    xdg_surface_set_window_geometry(window->xdg_surface, 0, 0,
					    content.width, content.height);
	    wl_surface_commit(window->surface);
	  }

	if (resize == YES)
	  {
	    NSDebugLog(@"[%d] placewindow: newsize=%fx%f", win, window->width,
		       window->height);
	    NSEvent *ev = [NSEvent otherEventWithType:NSAppKitDefined
					     location:rect.origin
					modifierFlags:0
					    timestamp:0
					 windowNumber:win
					      context:GSCurrentContext()
					      subtype:GSAppKitWindowResized
						data1:rect.size.width
						data2:rect.size.height];
	    NSDebugLog(@"notify resize=%fx%f", rect.size.width,
		       rect.size.height);
	    [(GSWindowWithNumber(window->window_id)) sendEvent:ev];
	    NSDebugLog(@"notified resize=%fx%f", rect.size.width, rect.size.height);
	    // we have a new buffer
	  }
	else if (move == YES)
	  {
	    NSDebugLog(@"[%d] placewindow: newpos=%fx%f", win, window->pos_x,
		       window->pos_y);
	  }
	wl_display_flush(wlconfig->display);
}

- (NSRect)windowbounds:(int)win
{
  struct window *window = get_window_with_id(wlconfig, win);

  if (window == NULL)
    return NSZeroRect;

  NSDebugLog(@"windowbounds: win=%d, pos=%fx%f size=%fx%f", window->window_id,
	     window->pos_x, window->pos_y, window->width, window->height);

  return NSMakeRect(window->pos_x, WaylandToNS(window, window->pos_y),
		    window->width, window->height);
}

- (void)setParentWindow:(int)parentWin forChildWindow:(int)childWin
{
  struct window *child = get_window_with_id(wlconfig, childWin);
  struct window *parent = get_window_with_id(wlconfig, parentWin);
  if (!child) return;
  child->parent_id = parentWin;
  if (child->toplevel)
    xdg_toplevel_set_parent(child->toplevel, parent ? parent->toplevel : NULL);
}

- (void)setwindowlevel:(int)level:(int)win
{
  struct window *window = get_window_with_id(wlconfig, win);

  if (window == NULL)
    return;

  window->level = level;
  WaylandUpdateWindowHints(window);
  wl_display_flush(wlconfig->display);

  NSDebugLog(@"setwindowlevel: level=%d win=%d", level, win);
}

- (int)windowlevel:(int)win
{
  NSDebugLog(@"windowlevel: %d", win);
  struct window *window = get_window_with_id(wlconfig, win);

  if (window == NULL)
    return 0;

  return window->level;
}

- (int)windowdepth:(int)win
{
  NSDebugLog(@"windowdepth");
  return 0;
}

- (void)setmaxsize:(NSSize)size:(int)win
{
  WaylandApplySizeHints(get_window_with_id(wlconfig, win));
}

- (void)setminsize:(NSSize)size:(int)win
{
  WaylandApplySizeHints(get_window_with_id(wlconfig, win));
}

- (void)setresizeincrements:(NSSize)size:(int)win
{
  /* xdg-shell has no cell-increment request. Configure replies snap locally. */
}

- (void)flushwindowrect:(NSRect)rect:(int)win
{
  NSDebugLog(@"[%d] flushwindowrect: %f,%f %fx%f", win, NSMinX(rect),
	     NSMinY(rect), NSWidth(rect), NSHeight(rect));
  struct window *window = get_window_with_id(wlconfig, win);
  if (window == NULL)
    return;

#ifdef HAVE_EGL
  if (window->usesOpenGL)
    {
      NSDebugLog(@"[%d] skipping cairo flush for OpenGL-backed window", win);
      return;
    }
#endif

  [[GSCurrentContext() class] handleExposeRect:rect forDriver:window->wcs];
}

- (void)styleoffsets:(float *)
		   l:(float *)r
		    :(float *)t
		    :(float *)b
		    :(unsigned int)style
{
  NSDebugLog(@"styleoffsets");
  /* XXX - Assume we don't decorate */
  *l = *r = *t = *b = 0.0;
}

- (void)docedited:(int)edited:(int)win
{
  struct window *window = get_window_with_id(wlconfig, win);
  if (window && window->application_window &&
      nextspace_window_v1_get_version(window->application_window) >= 7)
    {
      nextspace_window_v1_set_document_edited(window->application_window, edited != 0);
      wl_display_flush(window->wlconfig->display);
    }
}

- (void)setinputstate:(int)state:(int)win
{
  if (state < 0 || state > NEXTSPACE_WINDOW_V1_TITLE_STATE_MAIN) return;
  struct window *window = get_window_with_id(wlconfig, win);
  if (!window) return;
  window->title_state = state;
  WaylandUpdateTitleState(window);
  wl_display_flush(wlconfig->display);
}

static void activation_done(void *data, struct xdg_activation_token_v1 *token, const char *name)
{
  struct window *window = data;
  xdg_activation_v1_activate(window->wlconfig->activation, name, window->surface);
  xdg_activation_token_v1_destroy(token);
  window->activation_token = NULL;
  wl_display_flush(window->wlconfig->display);
}
static const struct xdg_activation_token_v1_listener activation_listener = { .done = activation_done };

- (BOOL)dragIconWindow:(int)win event:(NSEvent *)event
{
  struct window *window = get_window_with_id(wlconfig, win);
  if (!window || !window->application_window) return NO;
  if (!window->toplevel || wlconfig->pointer.focus != window || !wlconfig->pointer.serial) return YES;
  NSPoint start = [event locationInWindow];
  uint32_t serial = wlconfig->pointer.serial;
  int x = window->pos_x, y = window->pos_y;
  NSInteger threshold = [[NSUserDefaults standardUserDefaults] integerForKey:@"GSMouseMoveThreshold"];
  if (threshold <= 0) threshold = 3;
  for (;;) {
    window = get_window_with_id(wlconfig, win);
    if (!window || wlconfig->pointer.focus != window || wlconfig->pointer.serial != serial) return YES;
    NSEvent *next = [NSApp nextEventMatchingMask:NSLeftMouseDraggedMask | NSLeftMouseUpMask
      untilDate:[NSDate dateWithTimeIntervalSinceNow:0.1] inMode:NSEventTrackingRunLoopMode dequeue:YES];
    if (!next) continue;
    if ([next type] == NSLeftMouseUp) return YES;
    NSPoint location = [next locationInWindow];
    if (fabs(location.x - start.x) < threshold && fabs(location.y - start.y) < threshold) continue;
    /* The surface may have disappeared while the tracking run loop dispatched. */
    window = get_window_with_id(wlconfig, win);
    if (window && window->toplevel && window->application_window &&
        wlconfig->pointer.serial == serial) {
      xdg_toplevel_move(window->toplevel, wlconfig->seat, serial);
      nextspace_window_v1_set_position(window->application_window,
        x + lround(location.x - start.x), y - lround(location.y - start.y));
      wl_display_flush(wlconfig->display);
    }
    return YES;
  }
}

- (void)setinputfocus:(int)win
{
  struct window *window = get_window_with_id(wlconfig, win);
  if (!window || !window->toplevel || window->activation_token || !wlconfig->activation ||
      wlconfig->keyboard_focus == window || ![GSWindowWithNumber(win) canBecomeKeyWindow]) return;
  struct window *source = wlconfig->pointer.focus ?: wlconfig->keyboard_focus;
  uint32_t serial = wlconfig->pointer.focus ? wlconfig->pointer.serial : wlconfig->event_serial;
  if (!source || !source->surface || !serial) return;
  window->activation_token = xdg_activation_v1_get_activation_token(wlconfig->activation);
  xdg_activation_token_v1_add_listener(window->activation_token, &activation_listener, window);
  xdg_activation_token_v1_set_surface(window->activation_token, source->surface);
  xdg_activation_token_v1_set_serial(window->activation_token, serial, wlconfig->seat);
  xdg_activation_token_v1_commit(window->activation_token);
  wl_display_flush(wlconfig->display);
}

- (void)setalpha:(float)alpha:(int)win
{
  // NSDebugLog(@"setalpha");
}

- (void)setShadow:(BOOL)hasShadow:(int)win
{
  // NSDebugLog(@"setshadow");
}

@end

@implementation
WaylandServer (SurfaceRoles)
- (void)createSurfaceShell:(struct window *)window
{
  int win = window->window_id;
  NSDebugLog(@"[%d] createSurfaceShell", win);

  switch (window->level)
    {
    case NSMainMenuWindowLevel:
      NSDebugLog(@"[%d] NSMainMenuWindowLevel", win);
      [self createLayerShell:window
	       withLayerType:ZWLR_LAYER_SHELL_V1_LAYER_TOP
	       withNamespace:@"gnustep-mainmenu"];
      break;
    case NSSubmenuWindowLevel:
      NSDebugLog(@"[%d] NSSubmenuWindowLevel", win);
      [self createSubMenuShell:window];
      break;
    case NSDesktopWindowLevel:
      NSDebugLog(@"[%d] NSDesktopWindowLevel", win);
      [self createLayerShell:window
	       withLayerType:ZWLR_LAYER_SHELL_V1_LAYER_BACKGROUND
	       withNamespace:@"gnustep-desktop"];
      break;
    case NSPopUpMenuWindowLevel:
      NSDebugLog(@"[%d] NSPopUpMenuWindowLevel", win);
      [self createPopup:window];
      break;
    case NSScreenSaverWindowLevel:
      NSDebugLog(@"[%d] NSScreenSaverWindowLevel", win);
      [self createLayerShell:window
	       withLayerType:ZWLR_LAYER_SHELL_V1_LAYER_OVERLAY
	       withNamespace:@"gnustep-screensaver"];
      break;
    case NSStatusWindowLevel:
      NSDebugLog(@"[%d] NSStatusWindowLevel", win);
    case NSFloatingWindowLevel:
      NSDebugLog(@"[%d] NSFloatingWindowLevel", win);
    case NSModalPanelWindowLevel:
      NSDebugLog(@"[%d] NSModalPanelWindowLevel", win);
    case NSNormalWindowLevel:
    default:
      NSDebugLog(@"[%d] NSNormalWindowLevel", win);
      [self createTopLevel:window];

      break;
    }
  window->is_out = 0;
}

- (BOOL)windowSurfaceHasRole:(struct window *)window
{
  return window->toplevel != NULL || window->layer_surface != NULL
	 || window->popup != NULL;
}

- (void)createTopLevel:(struct window *)window
{
  int win = window->window_id;
  NSDebugLog(@"[%d] createTopLevel", win);

  if ([self windowSurfaceHasRole:window])
    {
      // if the role is already assigned skip
      return;
    }

  if (window->surface)
    {
      WaylandDestroySurface(window);
    }
  window->surface = wl_compositor_create_surface(wlconfig->compositor);

  if (!window->surface)
    {
      NSDebugLog(@"can't create wayland surface");
      return;
    }

  WaylandSetupSurface(window);
  if (window->xdg_surface == NULL)
    {
      window->xdg_surface
	= xdg_wm_base_get_xdg_surface(wlconfig->wm_base, window->surface);
      window->toplevel = xdg_surface_get_toplevel(window->xdg_surface);
      xdg_toplevel_set_title(window->toplevel, [[GSWindowWithNumber(window->window_id) title] UTF8String]);
      NSString *appID = [[NSBundle mainBundle] bundleIdentifier];
      if (![appID length]) appID = [@"org.nextspace." stringByAppendingString:[[NSProcessInfo processInfo] processName]];
      xdg_toplevel_set_app_id(window->toplevel, [appID UTF8String]);
      struct window *parent = get_window_with_id(wlconfig, window->parent_id);
      if (parent && parent->toplevel) xdg_toplevel_set_parent(window->toplevel, parent->toplevel);

      WaylandSetupApplicationWindow(window);
      WaylandSetupDecoration(window);
      WaylandApplySizeHints(window);
      xdg_toplevel_add_listener(window->toplevel, &xdg_toplevel_listener,
				window);
      xdg_surface_add_listener(window->xdg_surface, &xdg_surface_listener,
			       window);

      xdg_surface_set_window_geometry(window->xdg_surface, 0, 0, window->width,
				      window->height);
    }

  wl_surface_commit(window->surface);
  wl_display_flush(window->wlconfig->display);
}

- (void)createLayerShell:(struct window *)window
	   withLayerType:(enum zwlr_layer_shell_v1_layer)layerType
	   withNamespace:(NSString *)namespace
{
  int win = window->window_id;
  NSDebugLog(@"[%d] createLayerShell: %@", win, namespace);

  if ([self windowSurfaceHasRole:window])
    {
      // if the role is already assigned skip
      return;
    }

  if (!wlconfig->layer_shell)
    {
      NSDebugLog(@"layer shell not supported, fallback to xdg toplevel");
      [self createTopLevel:window];
      return;
    }

  if (window->surface)
    {
      WaylandDestroySurface(window);
    }

  window->surface = wl_compositor_create_surface(wlconfig->compositor);
  WaylandSetupSurface(window);

  const char *cString = [namespace UTF8String];
  window->layer_surface
    = zwlr_layer_shell_v1_get_layer_surface(wlconfig->layer_shell,
					    window->surface,
					    window->output ? window->output->output : NULL, layerType,
					    cString);
  assert(window->layer_surface);
  zwlr_layer_surface_v1_set_size(window->layer_surface, window->width,
				 window->height);

  zwlr_layer_surface_v1_set_anchor(window->layer_surface,
				   ZWLR_LAYER_SURFACE_V1_ANCHOR_TOP
				     | ZWLR_LAYER_SURFACE_V1_ANCHOR_LEFT);

  zwlr_layer_surface_v1_set_exclusive_zone(window->layer_surface, 1);

  zwlr_layer_surface_v1_set_margin(window->layer_surface, window->pos_y, 0, 0,
				   window->pos_x);

  NSDebugLog(@"layer margins: %f,%f,%f,%f", window->pos_y, 0.0f, 0.0f,
	     window->pos_x);
  zwlr_layer_surface_v1_add_listener(window->layer_surface,
				     &layer_surface_listener, window);

  wl_surface_commit(window->surface);
  wl_display_flush(window->wlconfig->display);
}
- (struct window *)getSuperMenuWindow:(struct window *)window
{
  NSWindow *nswin = GSWindowWithNumber(window->window_id);
  if (!nswin || ![nswin respondsToSelector:@selector(_menu)])
    {
      NSDebugLog(@"makeSubmenu can't find nswin");
      return NULL;
    }
  NSMenu *menu = [nswin _menu];
  if (!menu)
    {
      NSDebugLog(@"makeSubmenu can't find menu");
      return NULL;
    }
  NSMenu *supermenu = [menu supermenu];
  if (!supermenu)
    {
      NSDebugLog(@"makeSubmenu can't find supermenu");
      return NULL;
    }
  NSWindow *parent = [supermenu window];
  if (!parent)
    {
      NSDebugLog(@"makeSubmenu can't find the parent");
      return NULL;
    }

  struct window *parentwindow
    = get_window_with_id(wlconfig, [parent windowNumber]);

  return parentwindow;
}

- (void)createSubMenuShell:(struct window *)window
{
  int win = window->window_id;

  if ([self windowSurfaceHasRole:window])
    {
      // if the role is already assigned skip
      return;
    }

  if (wlconfig->layer_shell)
    {
      // the preferred way to create a submenu is to use an overlay
      [self createLayerShell:window
	       withLayerType:ZWLR_LAYER_SHELL_V1_LAYER_TOP
	       withNamespace:@"gnustep-submenu"];
      return;
    }
  else
    {
      NSDebugLog(@"layer shell not supported, fallback to xdg popup");
    }
  // if the layer shell is not available then we use the xdg popup
  // for that we need a parent toplevel window

  NSWindow *nswindow = GSWindowWithNumber(win);
  NSMenu *menu = [nswindow respondsToSelector:@selector(_menu)] ? [nswindow _menu] : nil;
  struct window *parentwindow = [self getSuperMenuWindow:window];
  if ([menu isTornOff] || !parentwindow || parentwindow == window ||
      ![self windowSurfaceHasRole:parentwindow]) {
    [self createTopLevel:window];
    return;
  }
  NSDebugLog(@"new popup: %d parent id: %d", win, parentwindow->window_id);
  NSDebugLog(@"parent: %d [%f,%f %fx%f]", parentwindow->window_id,
	     parentwindow->pos_x, parentwindow->pos_y, parentwindow->width,
	     parentwindow->height);

  [self createPopupShell:window withParentShell:parentwindow];
}

- (void)createPopup:(struct window *)window
{
  struct window *parent = get_window_with_id(wlconfig, window->parent_id);
  if (!parent) parent = get_window_with_id(wlconfig, [[NSApp keyWindow] windowNumber]);
  if (!parent || parent == window) parent = wlconfig->pointer.focus;
  if (parent && parent != window && [self windowSurfaceHasRole:parent])
    [self createPopupShell:window withParentShell:parent];
  else [self createTopLevel:window];
}

- (void)createPopupShell:(struct window *)child
	 withParentShell:(struct window *)parent
{
  NSDebugLog(@"createPopupShell");

  if (!parent || (parent->toplevel == NULL && parent->popup == NULL && parent->layer_surface == NULL))
    {
      NSDebugLog(@"popup has no mapped parent");
      return;
    }
  if ([self windowSurfaceHasRole:child])
    {
      [self destroySurfaceRole:child];
    }

  child->parent_id = parent->window_id;
  child->output = parent->output;
  WaylandSetScale(child, parent->scale120);
  child->surface = wl_compositor_create_surface(wlconfig->compositor);
  WaylandSetupSurface(child);

  child->xdg_surface
    = xdg_wm_base_get_xdg_surface(wlconfig->wm_base, child->surface);
  struct xdg_positioner *positioner
    = xdg_wm_base_create_positioner(wlconfig->wm_base);

  xdg_positioner_set_size(positioner, child->width, child->height);

  NSSize parentContent = WaylandSurfaceSize(parent);
  NSPoint parentOrigin = WaylandSurfaceOrigin(parent);
  xdg_positioner_set_anchor_rect(positioner, 0, 0, parentContent.width, parentContent.height);
  xdg_positioner_set_anchor(positioner, XDG_POSITIONER_ANCHOR_TOP_LEFT);
  xdg_positioner_set_gravity(positioner, XDG_POSITIONER_GRAVITY_BOTTOM_RIGHT);
  xdg_positioner_set_constraint_adjustment(positioner,
    XDG_POSITIONER_CONSTRAINT_ADJUSTMENT_FLIP_X | XDG_POSITIONER_CONSTRAINT_ADJUSTMENT_FLIP_Y |
    XDG_POSITIONER_CONSTRAINT_ADJUSTMENT_SLIDE_X | XDG_POSITIONER_CONSTRAINT_ADJUSTMENT_SLIDE_Y);

  xdg_positioner_set_offset(positioner, child->pos_x - parentOrigin.x, child->pos_y - parentOrigin.y);

  child->popup = xdg_surface_get_popup(child->xdg_surface, parent->xdg_surface,
				       positioner);

  if (parent->layer_surface)
    {
      zwlr_layer_surface_v1_get_popup(parent->layer_surface, child->popup);
    }

  xdg_popup_add_listener(child->popup, &xdg_popup_listener, child);
  if (wlconfig->pointer.button_state == WL_POINTER_BUTTON_STATE_PRESSED && wlconfig->pointer.serial)
    xdg_popup_grab(child->popup, wlconfig->seat, wlconfig->pointer.serial);
  xdg_surface_add_listener(child->xdg_surface, &xdg_surface_listener, child);

  xdg_surface_set_window_geometry(child->xdg_surface, 0, 0, child->width,
				  child->height);

  NSDebugLog(@"child_geometry : %f,%f %fx%f", child->pos_x - parent->pos_x,
	     child->pos_y - parent->pos_y, child->width, child->height);
  wl_surface_commit(child->surface);
  wl_display_flush(wlconfig->display);
  xdg_positioner_destroy(positioner);
}

- (void)destroySurfaceRole:(struct window *)window
{
  NSDebugLog(@"[%d] destroySurfaceRole", window->window_id);

  if (window == NULL)
    {
      return;
    }
  if (window->layer_surface)
    {
      zwlr_layer_surface_v1_destroy(window->layer_surface);
      window->layer_surface = NULL;
    }
  if (window->xdg_surface)
    {
      if (window->decoration) {
        zxdg_toplevel_decoration_v1_destroy(window->decoration);
        window->decoration = NULL;
      }
      if (window->toplevel)
	{
	  xdg_toplevel_destroy(window->toplevel);
	  window->toplevel = NULL;
	}
      if (window->popup)
	{
	  xdg_popup_destroy(window->popup);
	  window->popup = NULL;
	}
      xdg_surface_destroy(window->xdg_surface);
      window->xdg_surface = NULL;
    }
  if (window->wcs)
    {
    //  [window->wcs destroySurface];
    }
  WaylandDestroySurface(window);
  window->configured = NO;
}

- (void)destroyWindowShell:(struct window *)window
{
  NSDebugLog(@"[%d] destroyWindowShell", window->window_id);

  [self destroySurfaceRole:window];

  window->is_out = 1;

  wl_display_flush(window->wlconfig->display);
}

@end
