/*
   WaylandDragView - Drag and drop for the Wayland backend.

   Copyright (C) 2026 Free Software Foundation, Inc.

   This file is part of GNUstep.

   This library is free software; you can redistribute it and/or
   modify it under the terms of the GNU Lesser General Public
   License as published by the Free Software Foundation; either
   version 2 of the License, or (at your option) any later version.

   This library is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
   Lesser General Public License for more details.

   You should have received a copy of the GNU Lesser General Public
   License along with this library; see the file COPYING.LIB.
   If not, see <http://www.gnu.org/licenses/> or write to the
   Free Software Foundation, 51 Franklin Street, Fifth Floor,
   Boston, MA 02110-1301, USA.
*/

#include <AppKit/AppKit.h>
#include <GNUstepGUI/GSDragView.h>
#include "wayland/WaylandServer.h"
#include "wayland/WaylandDragIcon.h"
#include <unistd.h>

extern NSWindow *GSWindowWithNumber(NSInteger number);

@interface WaylandServer (DragAndDrop)
- (WaylandConfig *)wlconfig;
- (id<NSDraggingInfo>)dragInfo;
@end

static NSDragOperation nativeActions(uint32_t actions)
{
  return ((actions & WL_DATA_DEVICE_MANAGER_DND_ACTION_COPY) ? NSDragOperationCopy : 0) |
    ((actions & WL_DATA_DEVICE_MANAGER_DND_ACTION_MOVE) ? NSDragOperationMove : 0);
}
static uint32_t waylandActions(NSDragOperation actions)
{
  /* Generic import (for example opening a file on an application icon) is
     non-destructive. Never advertise a move without an explicit Move bit. */
  return ((actions & (NSDragOperationCopy | NSDragOperationGeneric)) ? WL_DATA_DEVICE_MANAGER_DND_ACTION_COPY : 0) |
    ((actions & NSDragOperationMove) ? WL_DATA_DEVICE_MANAGER_DND_ACTION_MOVE : 0);
}
static struct window *dragOwner(struct window *window)
{
  if (!window) return NULL;
  WaylandConfig *config = window->wlconfig;
  NSUInteger remaining = [WaylandWindowNumbers(config) count];
  while (window && !window->application_window && remaining--)
    window = get_window_with_id(config, window->parent_id);
  return window && window->application_window ? window : NULL;
}
static void sourceFinished(id source, NSImage *image, NSPoint point, NSDragOperation operation)
{
  if ([source respondsToSelector:@selector(draggedImage:endedAt:operation:)])
    [source draggedImage:image endedAt:point operation:operation];
  else if ([source respondsToSelector:@selector(draggedImage:endedAt:deposited:)])
    [source draggedImage:image endedAt:point deposited:operation != NSDragOperationNone];
}

@interface WaylandDragView : GSDragView
{
  struct wl_data_source *_dataSource;
  NSPasteboard *_sourcePasteboard;
  NSDictionary *_sourceData;
  NSInteger _sourceWindow;
  NSDragOperation _sourceMask, _resultOperation;
  BOOL _dragActive, _sourceDropped, _sourceMoved;
  WaylandDragIcon *_icon;
  NSMutableArray *_events;
  struct wl_data_offer *_offer, *_ignoredOffer;
  NSMutableDictionary *_mimesByType;
  uint32_t _enterSerial;
  NSInteger _incomingWindow, _destinationWindow;
  NSPoint _incomingPoint;
  NSSize _imageOffset;
  NSInteger _nextToken, _pendingToken;
  GSAppKitSubtype _pendingType;
  BOOL _eventPending, _reading, _deferredClear, _failed;
  BOOL _ignoreIncoming, _blockedDestination, _ownsDestinationPasteboard;
  NSString *_acceptedMime;
  NSUInteger _visit, _receivedBytes;
  uint32_t _sourceGesture, _destinationGesture;
  BOOL _destinationLocal;
  NSTimeInterval _readRemaining;
}
+ (id)sharedDragView;
- (void)writeMime:(const char *)mime fd:(int)fd;
- (void)sourceEnded:(struct wl_data_source *)source operation:(NSDragOperation)operation;
- (void)sourceAction:(uint32_t)action;
- (void)sourceDropped;
- (void)entered:(struct window *)window offer:(struct wl_data_offer *)offer serial:(uint32_t)serial point:(NSPoint)point;
- (void)moved:(NSPoint)point;
- (void)enqueue:(GSAppKitSubtype)type window:(NSInteger)window offer:(struct wl_data_offer *)offer serial:(uint32_t)serial point:(NSPoint)point;
- (void)clearDestination;
- (void)scheduleQueue;
- (void)contextForWindow:(NSInteger)window identity:(uint32_t)identity phase:(uint32_t)phase local:(BOOL)local point:(NSPoint)point;
@end

static void ds_target(void *data, struct wl_data_source *source, const char *mime) {}
static void ds_send(void *data, struct wl_data_source *source, const char *mime, int32_t fd)
{ [(WaylandDragView *)data writeMime:mime fd:fd]; }
static void ds_cancelled(void *data, struct wl_data_source *source)
{ [(WaylandDragView *)data sourceEnded:source operation:NSDragOperationNone]; }
static void ds_drop(void *data, struct wl_data_source *source)
{ [(WaylandDragView *)data sourceDropped]; }
static void ds_finished(void *data, struct wl_data_source *source)
{ [(WaylandDragView *)data sourceEnded:source operation:NSDragOperationEvery]; }
static void ds_action(void *data, struct wl_data_source *source, uint32_t action)
{ [(WaylandDragView *)data sourceAction:action]; }
static const struct wl_data_source_listener sourceListener = {
  .target = ds_target, .send = ds_send, .cancelled = ds_cancelled,
  .dnd_drop_performed = ds_drop, .dnd_finished = ds_finished, .action = ds_action
};
static void dd_offer(void *data, struct wl_data_device *device, struct wl_data_offer *offer)
{ WaylandRegisterOffer(offer); }
static void dd_enter(void *data, struct wl_data_device *device, uint32_t serial,
    struct wl_surface *surface, wl_fixed_t x, wl_fixed_t y, struct wl_data_offer *offer)
{
  [[WaylandDragView sharedDragView] entered:surface ? wl_surface_get_user_data(surface) : NULL
    offer:offer serial:serial point:NSMakePoint(wl_fixed_to_double(x), wl_fixed_to_double(y))];
}
static void dd_motion(void *data, struct wl_data_device *device, uint32_t time, wl_fixed_t x, wl_fixed_t y)
{ [[WaylandDragView sharedDragView] moved:NSMakePoint(wl_fixed_to_double(x), wl_fixed_to_double(y))]; }
static void dd_leave(void *data, struct wl_data_device *device)
{ [[WaylandDragView sharedDragView] enqueue:GSAppKitDraggingExit window:0 offer:NULL serial:0 point:NSZeroPoint]; }
static void dd_drop(void *data, struct wl_data_device *device)
{ [[WaylandDragView sharedDragView] enqueue:GSAppKitDraggingDrop window:0 offer:NULL serial:0 point:NSZeroPoint]; }
static void dd_selection(void *data, struct wl_data_device *device, struct wl_data_offer *offer)
{ WaylandSelection(data, offer); }
const struct wl_data_device_listener data_device_listener = {
  .data_offer = dd_offer, .enter = dd_enter, .leave = dd_leave,
  .motion = dd_motion, .drop = dd_drop, .selection = dd_selection
};

@implementation WaylandDragView
+ (id)sharedDragView
{
  static WaylandDragView *view;
  if (!view) view = [self new];
  return view;
}
- (id)init
{
  /* GSDragView's normal initializer creates an X11-style drag window. The
     Wayland source and destination state need no extra application toplevel. */
  if ((self = [super initWithFrame:NSZeroRect])) {
    dragCell = [[NSCell alloc] initImageCell:nil];
    _events = [NSMutableArray new];
    [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(windowClosed:)
      name:NSWindowWillCloseNotification object:nil];
  }
  return self;
}
- (void)dealloc
{
  [NSObject cancelPreviousPerformRequestsWithTarget:self];
  [[NSNotificationCenter defaultCenter] removeObserver:self];
  [_events release]; [_mimesByType release]; [_acceptedMime release];
  [_sourcePasteboard release]; [_sourceData release]; [dragPasteboard release]; [dragSource release]; [dragCell release];
  [_icon release];
  [super dealloc];
}
- (WaylandConfig *)config { return [(WaylandServer *)GSCurrentServer() wlconfig]; }
- (id)draggingSource
{
  if (!_offer) return dragSource;
  return _destinationLocal && _destinationGesture == _sourceGesture ? dragSource : nil;
}
- (NSImage *)draggedImage { return [self draggingSource] ? [dragCell image] : nil; }
- (NSPoint)draggedImageLocation
{
  return [self draggingSource] ? NSMakePoint(dragPoint.x + _imageOffset.width, dragPoint.y + _imageOffset.height) : dragPoint;
}
- (NSArray *)namesOfPromisedFilesDroppedAtDestination:(NSURL *)destination
{
  id source = [self draggingSource];
  return [source respondsToSelector:@selector(namesOfPromisedFilesDroppedAtDestination:)] ?
    [source namesOfPromisedFilesDroppedAtDestination:destination] : nil;
}
- (void)writeMime:(const char *)mime fd:(int)fd
{
  NSString *type = mime ? [NSString stringWithUTF8String:mime] : nil;
  WaylandWriteDataToFD(type ? [_sourceData objectForKey:type] : nil, fd);
}
- (void)sourceAction:(uint32_t)action { _resultOperation = nativeActions(action); }
- (void)sourceDropped { _sourceDropped = YES; DESTROY(_icon); }
- (void)sourceEnded:(struct wl_data_source *)source operation:(NSDragOperation)operation
{
  if (source != _dataSource || !_dataSource) return;
  if (operation != NSDragOperationEvery) _resultOperation = operation;
  _dragActive = isDragging = NO;
  wl_data_source_destroy(_dataSource); _dataSource = NULL;
  DESTROY(_icon);
}
- (void)dragImage:(NSImage *)image at:(NSPoint)location offset:(NSSize)initialOffset
    event:(NSEvent *)event pasteboard:(NSPasteboard *)pasteboard source:(id)source slideBack:(BOOL)slide
{
  if (_sourcePasteboard) return;
  WaylandConfig *config = [self config];
  uint32_t serial = config ? config->pointer.serial : 0;
  struct window *window = config ? get_window_with_id(config, [[event window] windowNumber]) : NULL;
  NSInteger origin = window ? window->window_id : 0;
  struct window *owner = dragOwner(window);
  BOOL hasContext = owner && nextspace_window_v1_get_version(owner->application_window) >= 4;
  /* Pasteboard IPC and source callbacks can dispatch pending window moves.
     Capture both screen coordinates against the same AppKit geometry. */
  NSPoint mouse = [[event window] convertBaseToScreen:[event locationInWindow]];
  NSSize imageOffset = NSMakeSize(location.x - mouse.x, location.y - mouse.y);
  NSDragOperation mask = [source respondsToSelector:@selector(draggingSourceOperationMaskForLocal:)] ?
    [source draggingSourceOperationMaskForLocal:NO] : NSDragOperationCopy;
  uint32_t externalActions = waylandActions(mask), localActions = externalActions;
  if (hasContext && [source respondsToSelector:@selector(draggingSourceOperationMaskForLocal:)])
    localActions = waylandActions([source draggingSourceOperationMaskForLocal:YES]);
  uint32_t actions = externalActions | localActions;
  if (!window || !config->data_device_manager || !config->data_device ||
      wl_data_device_manager_get_version(config->data_device_manager) < 3 || !actions) {
    sourceFinished(source, image, location, NSDragOperationNone);
    return;
  }
  NSMutableDictionary *representations = [NSMutableDictionary dictionary];
  NSMutableArray *buffers = [NSMutableArray array];
  NSUInteger total = 0, index;
  NSArray *types = [pasteboard types];
  /* The named drag pasteboard is shared between applications. Freeze this
     gesture's bytes before another application can replace that name. */
  for (index = 0; index < [types count]; index++) {
    NSDictionary *data = WaylandPasteboardRepresentations(pasteboard, [types objectAtIndex:index]);
    for (NSData *bytes in [data allValues]) {
      if ([buffers indexOfObjectIdenticalTo:bytes] != NSNotFound) continue;
      total += [bytes length]; [buffers addObject:bytes];
      if (total > 64 * 1024 * 1024) {
        sourceFinished(source, image, location, NSDragOperationNone);
        return;
      }
    }
    [representations addEntriesFromDictionary:data];
  }
  if (![representations count]) {
    sourceFinished(source, image, location, NSDragOperationNone);
    return;
  }
  window = get_window_with_id(config, origin);
  if (!window) {
    sourceFinished(source, image, location, NSDragOperationNone);
    return;
  }
  _sourceData = [representations copy];
  ASSIGN(_sourcePasteboard, pasteboard); ASSIGN(dragPasteboard, pasteboard); ASSIGN(dragSource, source);
  _sourceWindow = [[event window] windowNumber]; _sourceMask = nativeActions(actions);
  _sourceGesture = 0;
  dragMask = _sourceMask; operationMask = NSDragOperationEvery;
  dragPosition = location; slideBack = slide;
  _imageOffset = imageOffset;
  _icon = [[WaylandDragIcon alloc] initWithImage:image
    offset:NSMakePoint(_imageOffset.width, -_imageOffset.height - [image size].height) config:config];
  [dragCell setImage:image];
  _dataSource = wl_data_device_manager_create_data_source(config->data_device_manager);
  wl_data_source_add_listener(_dataSource, &sourceListener, self);
  for (NSString *mime in _sourceData) wl_data_source_offer(_dataSource, [mime UTF8String]);
  wl_data_source_set_actions(_dataSource, actions);
  _resultOperation = NSDragOperationNone; _sourceDropped = _sourceMoved = NO; _dragActive = isDragging = YES;
  @try {
    if ([source respondsToSelector:@selector(draggedImage:beganAt:)]) [source draggedImage:image beganAt:location];
    if (_dragActive) {
      window = get_window_with_id(config, origin);
      owner = dragOwner(window);
      if (hasContext && owner) nextspace_window_v1_prepare_drag(owner->application_window, localActions, externalActions);
      if (!window) { [self sourceEnded:_dataSource operation:NSDragOperationNone]; }
    }
    if (_dragActive) {
      wl_data_device_start_drag(config->data_device, _dataSource, window->surface, [_icon surface], serial);
      [_icon start];
      wl_display_flush(config->display);
    }
    while (_dragActive && wl_display_get_error(config->display) == 0) {
      NSEvent *next = [NSApp nextEventMatchingMask:NSAnyEventMask
        untilDate:[NSDate dateWithTimeIntervalSinceNow:0.02] inMode:NSEventTrackingRunLoopMode dequeue:YES];
      if (next && _sourceDropped && ([next type] == NSLeftMouseDown || [next type] == NSRightMouseDown ||
          [next type] == NSOtherMouseDown || [next type] == NSKeyDown)) {
        /* A receiver may be waiting for a user decision. New source input
           cancels that pending gesture before an edit or another drag starts. */
        [NSApp postEvent:next atStart:YES];
        [self sourceEnded:_dataSource operation:NSDragOperationNone];
        break;
      }
      if (next) [NSApp sendEvent:next];
      if (_sourceMoved && _dragActive) {
        _sourceMoved = NO;
        if ([source respondsToSelector:@selector(draggedImage:movedTo:)])
          [source draggedImage:image movedTo:dragPosition];
      }
    }
    if (_dragActive) [self sourceEnded:_dataSource operation:NSDragOperationNone];
    sourceFinished(source, image, dragPosition, _resultOperation);
  } @finally {
    if (_dataSource) [self sourceEnded:_dataSource operation:NSDragOperationNone];
    DESTROY(_sourcePasteboard); DESTROY(_sourceData); DESTROY(dragSource); _sourceWindow = 0;
    if (!_offer) DESTROY(dragPasteboard);
  }
}

/* Keep protocol callbacks free of pasteboard IPC. Serialize AppKit delivery so
   queued enter/motion/drop events cannot overwrite a view's NSDraggingInfo while
   it fetches data through a reentrant Foundation run loop. */
- (void)scheduleQueue
{
  [NSObject cancelPreviousPerformRequestsWithTarget:self selector:@selector(processQueue) object:nil];
  [self performSelector:@selector(processQueue) withObject:nil afterDelay:0 inModes:WaylandApplicationModes()];
}
- (void)contextForWindow:(NSInteger)window identity:(uint32_t)identity phase:(uint32_t)phase local:(BOOL)local point:(NSPoint)point
{
  if (phase == NEXTSPACE_WINDOW_V1_DRAG_PHASE_ENTER) {
    for (NSMutableDictionary *entry in [_events reverseObjectEnumerator]) {
      if ([[entry objectForKey:@"type"] integerValue] == GSAppKitDraggingEnter &&
          [[entry objectForKey:@"window"] integerValue] == window && ![entry objectForKey:@"gesture"]) {
        [entry setObject:[NSNumber numberWithUnsignedInt:identity] forKey:@"gesture"];
        [entry setObject:[NSNumber numberWithBool:local] forKey:@"local"];
        [self scheduleQueue]; break;
      }
    }
    return;
  }
  if (window != _sourceWindow || !_sourcePasteboard) return;
  if (phase == NEXTSPACE_WINDOW_V1_DRAG_PHASE_BEGIN) _sourceGesture = identity;
  if (_sourceGesture != identity) return;
  NSPoint position = NSMakePoint(point.x + _imageOffset.width,
    WaylandDesktopBottom([self config]) - point.y + _imageOffset.height);
  if (!NSEqualPoints(position, dragPosition)) _sourceMoved = YES;
  dragPosition = position;
}
- (void)entered:(struct window *)window offer:(struct wl_data_offer *)offer serial:(uint32_t)serial point:(NSPoint)point
{
  if (_eventPending && _pendingType == GSAppKitDraggingDrop) {
    /* One AppKit drop can be waiting for a user decision. Refuse a second
       gesture without cancelling its source while it moves to another app. */
    _ignoreIncoming = YES; _ignoredOffer = offer;
    if (offer) wl_data_offer_accept(offer, serial, NULL);
    return;
  }
  _incomingWindow = window ? window->window_id : 0;
  _incomingPoint = window ? WaylandSurfacePoint(window, point) : NSZeroPoint;
  [self enqueue:GSAppKitDraggingEnter window:_incomingWindow offer:offer serial:serial point:_incomingPoint];
}
- (void)moved:(NSPoint)point
{
  if (_ignoreIncoming) return;
  struct window *window = get_window_with_id([self config], _incomingWindow);
  if (!window) return;
  _incomingPoint = WaylandSurfacePoint(window, point);
  [self enqueue:GSAppKitDraggingUpdate window:0 offer:NULL serial:0 point:_incomingPoint];
}
- (void)enqueue:(GSAppKitSubtype)type window:(NSInteger)window offer:(struct wl_data_offer *)offer serial:(uint32_t)serial point:(NSPoint)point
{
  if (_ignoreIncoming) {
    if (type == GSAppKitDraggingExit) {
      WaylandDestroyOffer(_ignoredOffer); _ignoredOffer = NULL; _ignoreIncoming = NO;
    }
    return;
  }
  if (type == GSAppKitDraggingDrop) point = _incomingPoint;
  if (type == GSAppKitDraggingExit) _incomingWindow = 0;
  if (type == GSAppKitDraggingUpdate && [[[_events lastObject] objectForKey:@"type"] integerValue] == type)
    [_events removeLastObject];
  [_events addObject:[NSMutableDictionary dictionaryWithObjectsAndKeys:
    [NSNumber numberWithInteger:type], @"type", [NSNumber numberWithInteger:window], @"window",
    [NSValue valueWithPointer:offer], @"offer", [NSNumber numberWithUnsignedInt:serial], @"serial",
    [NSValue valueWithPoint:point], @"point", nil]];
  [self scheduleQueue];
}
- (void)postType:(GSAppKitSubtype)type point:(NSPoint)point
{
  _eventPending = YES; _pendingType = type; _pendingToken = ++_nextToken;
  NSEvent *event = [NSEvent otherEventWithType:NSAppKitDefined location:point modifierFlags:0 timestamp:0
    windowNumber:_destinationWindow context:GSCurrentContext() subtype:type data1:_pendingToken data2:dragMask];
  /* This runs from the deferred queue, outside Wayland dispatch. A timer
     posting to GSDisplayServer's queue does not wake its input wait; deliver
     through AppKit now so a stationary pointer can negotiate the drop. */
  [NSApp sendEvent:event];
}
- (void)processQueue
{
  if (_eventPending || _reading) return;
  while ([_events count]) {
    NSDictionary *entry = [[[_events objectAtIndex:0] retain] autorelease];
    GSAppKitSubtype type = [[entry objectForKey:@"type"] integerValue];
    WaylandConfig *config = [self config];
    if (type == GSAppKitDraggingEnter && config->application_manager &&
        nextspace_application_v1_get_version(config->application_manager) >= 4 &&
        ![entry objectForKey:@"gesture"]) return;
    [_events removeObjectAtIndex:0];
    if (type == GSAppKitDraggingEnter) {
      if (_destinationWindow) {
        [_events insertObject:entry atIndex:0];
        [self postType:GSAppKitDraggingExit point:dragPoint]; return;
      }
      _offer = [[entry objectForKey:@"offer"] pointerValue];
      _destinationWindow = [[entry objectForKey:@"window"] integerValue];
      _enterSerial = [[entry objectForKey:@"serial"] unsignedIntValue];
      _destinationGesture = [[entry objectForKey:@"gesture"] unsignedIntValue];
      _destinationLocal = [[entry objectForKey:@"local"] boolValue];
      destWindow = GSWindowWithNumber(_destinationWindow);
      if (!_offer || !destWindow) { [self clearDestination]; continue; }
      if ([NSApp modalWindow] && [NSApp modalWindow] != destWindow) {
        _blockedDestination = YES;
        wl_data_offer_accept(_offer, _enterSerial, NULL);
        continue;
      }
      _mimesByType = [NSMutableDictionary new];
      for (NSString *mime in WaylandOfferMimes(_offer)) {
        NSString *typeName = WaylandTypeForMime([mime UTF8String]);
        if (![typeName length]) continue;
        NSMutableArray *mimes = [_mimesByType objectForKey:typeName];
        if (!mimes) { mimes = [NSMutableArray array]; [_mimesByType setObject:mimes forKey:typeName]; }
        if ([mime isEqual:@"text/plain;charset=utf-8"] || [mime isEqual:@"text/uri-list"]) [mimes insertObject:mime atIndex:0];
        else [mimes addObject:mime];
      }
      ASSIGN(dragPasteboard, [NSPasteboard pasteboardWithUniqueName]);
      _ownsDestinationPasteboard = YES;
      [dragPasteboard declareTypes:[_mimesByType allKeys] owner:self];
      dragMask = nativeActions(WaylandOfferActions(_offer)); operationMask = NSDragOperationEvery;
      dragSequence = _destinationGesture ? _destinationGesture : _enterSerial;
      _failed = NO; _receivedBytes = 0; _readRemaining = 5; _visit++;
      /* Legacy file-manager views assume a nonempty list of local paths. Do
         not expose a remote or malformed URI list as an accepted file type. */
      if ([_mimesByType objectForKey:NSFilenamesPboardType] &&
          ![[dragPasteboard propertyListForType:NSFilenamesPboardType] count]) {
        [_mimesByType removeObjectForKey:NSFilenamesPboardType];
        [dragPasteboard declareTypes:[_mimesByType allKeys] owner:self];
        _failed = NO;
      }
    }
    if (_blockedDestination) {
      if (type == GSAppKitDraggingExit) [self clearDestination];
      continue;
    }
    if (!_destinationWindow || !GSWindowWithNumber(_destinationWindow)) { [self clearDestination]; continue; }
    NSPoint point = [[entry objectForKey:@"point"] pointValue];
    if (type == GSAppKitDraggingEnter || type == GSAppKitDraggingUpdate || type == GSAppKitDraggingDrop) {
      dragPoint = point;
      /* Native gesture coordinates arrive in protocol order. A delayed local
         destination event must not overwrite a later motion or drop. */
      if (_sourcePasteboard && !_sourceGesture) {
        NSPoint screen = [destWindow convertBaseToScreen:point];
        dragPosition = NSMakePoint(screen.x + _imageOffset.width, screen.y + _imageOffset.height);
      }
    }
    [self postType:type point:dragPoint]; return;
  }
}
- (void)clearDestination
{
  _visit++; _pendingToken = 0; _eventPending = NO;
  if (_reading) { _deferredClear = YES; return; }
  WaylandDestroyOffer(_offer); _offer = NULL;
  if (_ownsDestinationPasteboard && dragPasteboard) [dragPasteboard releaseGlobally];
  DESTROY(dragPasteboard); DESTROY(_mimesByType); DESTROY(_acceptedMime);
  _readRemaining = 0;
  _ownsDestinationPasteboard = _blockedDestination = NO;
  _destinationWindow = 0; destWindow = nil; dragMask = _sourceMask;
  _destinationLocal = NO; _destinationGesture = 0;
  _deferredClear = NO;
  ASSIGN(dragPasteboard, _sourcePasteboard);
}
- (void)windowClosed:(NSNotification *)notification
{
  NSInteger number = [[notification object] windowNumber];
  if (number == _sourceWindow) [self sourceEnded:_dataSource operation:NSDragOperationNone];
  if (number == _destinationWindow) { [self clearDestination]; [self scheduleQueue]; }
}
- (void)pasteboard:(NSPasteboard *)pasteboard provideDataForType:(NSString *)type
{
  if (!_offer || _reading || _deferredClear) return;
  NSUInteger visit = _visit;
  BOOL provided = NO;
  _reading = YES;
  @try {
    for (NSString *mime in [_mimesByType objectForKey:type]) {
      if (_readRemaining <= 0) break;
      ASSIGN(_acceptedMime, mime);
      wl_data_offer_accept(_offer, _enterSerial, [mime UTF8String]);
      /* Charge time spent transferring, rather than the user's hover or
         decision time between requests for different representations. */
      NSTimeInterval started = WaylandMonotonicTime();
      NSData *bytes = WaylandReadOffer(_offer, mime, [self config], _readRemaining);
      _readRemaining = MAX(0, _readRemaining - (WaylandMonotonicTime() - started));
      if (visit != _visit) return;
      if (!bytes || _receivedBytes + [bytes length] > 64 * 1024 * 1024) break;
      _receivedBytes += [bytes length];
      id value = WaylandPasteboardValue(mime, bytes);
      if (value && WaylandStorePasteboardValue(pasteboard, type, value)) { provided = YES; break; }
    }
    if (!provided) _failed = YES;
  } @finally {
    _reading = NO;
    if (_deferredClear) { [self clearDestination]; [self scheduleQueue]; }
  }
}
- (void)eventComplete
{
  _pendingToken = 0; _eventPending = NO;
  [self scheduleQueue];
}
- (void)draggingExitProcessed:(NSEvent *)event
{
  if ([event data1] != _pendingToken || !_eventPending) return;
  [self clearDestination]; [self scheduleQueue];
}
- (void)postDragEvent:(NSEvent *)event
{
  if (!_eventPending || [event data1] != _pendingToken || !_offer) return;
  WaylandConfig *config = [self config];
  if ([event subtype] == GSAppKitDraggingStatus) {
    uint32_t actions = waylandActions([event data2]) & waylandActions(dragMask);
    NSArray *types = [dragPasteboard types];
    NSString *mime = actions ? _acceptedMime : nil;
    if (actions && !mime && [types count]) mime = [[_mimesByType objectForKey:[types objectAtIndex:0]] objectAtIndex:0];
    if (wl_data_offer_get_version(_offer) >= 3)
      wl_data_offer_set_actions(_offer, actions, actions & WL_DATA_DEVICE_MANAGER_DND_ACTION_COPY ?
        WL_DATA_DEVICE_MANAGER_DND_ACTION_COPY : actions & WL_DATA_DEVICE_MANAGER_DND_ACTION_MOVE);
    wl_data_offer_accept(_offer, _enterSerial, [mime UTF8String]);
    wl_display_flush(config->display);
    [self eventComplete];
  } else if ([event subtype] == GSAppKitDraggingFinished) {
    if ([event data2] && !_failed && WaylandOfferAction(_offer) && wl_data_offer_get_version(_offer) >= 3)
      wl_data_offer_finish(_offer);
    [self clearDestination]; [self scheduleQueue];
    wl_display_flush(config->display);
  }
}
@end

void WaylandDragContext(struct wl_surface *surface, uint32_t identity, uint32_t phase, BOOL local, NSPoint point)
{
  struct window *window = surface ? wl_surface_get_user_data(surface) : NULL;
  if (window) [[WaylandDragView sharedDragView] contextForWindow:window->window_id
    identity:identity phase:phase local:local point:point];
}

@implementation WaylandServer (DragAndDrop)
- (WaylandConfig *)wlconfig { return wlconfig; }
- (id<NSDraggingInfo>)dragInfo { return [WaylandDragView sharedDragView]; }
@end
