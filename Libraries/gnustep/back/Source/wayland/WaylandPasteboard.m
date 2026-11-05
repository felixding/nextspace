/* Focused Wayland offers backed by per-session gpbs storage. LGPL-2.0-or-later. */
#define _GNU_SOURCE
#include "wayland/WaylandServer.h"
#include <AppKit/AppKit.h>
#include <GNUstepGUI/GSPasteboardServer.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <signal.h>
#include <poll.h>
#include <unistd.h>
#include <math.h>
#include <time.h>

NSTimeInterval WaylandMonotonicTime(void)
{
  struct timespec now;
  if (clock_gettime(CLOCK_MONOTONIC, &now)) return NAN;
  return now.tv_sec + now.tv_nsec / 1e9;
}

static NSArray *transferModes(void)
{
  return [NSArray arrayWithObjects:NSDefaultRunLoopMode, NSConnectionReplyMode,
    NSModalPanelRunLoopMode, NSEventTrackingRunLoopMode, nil];
}

/* Publishing reads gpbs over DO. Do not start it inside another DO reply. */
NSArray *WaylandApplicationModes(void)
{
  return [NSArray arrayWithObjects:NSDefaultRunLoopMode, NSModalPanelRunLoopMode,
    NSEventTrackingRunLoopMode, nil];
}

/* Clipboard and DND share MIME conversion and bounded pipe transfers. */
NSArray *WaylandMimesForType(NSString *type)
{
  if (![type length]) return [NSArray array];
  if ([type isEqual:NSStringPboardType])
    return [NSArray arrayWithObjects:@"text/plain;charset=utf-8", @"UTF8_STRING", @"text/plain", @"TEXT", nil];
  if ([type isEqual:NSFilenamesPboardType])
    return [NSArray arrayWithObjects:@"text/uri-list", type, nil];
  return [NSArray arrayWithObject:type];
}
NSString *WaylandTypeForMime(const char *mime)
{
  if (!mime) return nil;
  NSString *value = [NSString stringWithUTF8String:mime];
  if (!value) return nil;
  NSString *base = [[[value componentsSeparatedByString:@";"] objectAtIndex:0] lowercaseString];
  if ([base isEqual:@"text/plain"] || [value isEqual:@"UTF8_STRING"] || [value isEqual:@"TEXT"])
    return NSStringPboardType;
  if ([base isEqual:@"text/uri-list"]) return NSFilenamesPboardType;
  return value;
}
static BOOL uriListMime(NSString *mime)
{ return [[[[mime componentsSeparatedByString:@";"] objectAtIndex:0] lowercaseString] isEqual:@"text/uri-list"]; }
static BOOL localPath(id path)
{
  if (![path isKindOfClass:[NSString class]] || ![path hasPrefix:@"/"]) return NO;
  NSUInteger index, length = [path length];
  for (index = 0; index < length; index++) if ([path characterAtIndex:index] == 0) return NO;
  return YES;
}

static NSData *fileURIs(NSArray *paths)
{
  if (![paths isKindOfClass:[NSArray class]] || ![paths count] || [paths count] > 4096) return nil;
  NSMutableString *list = [NSMutableString string];
  NSUInteger index;
  for (index = 0; index < [paths count]; index++) {
    id path = [paths objectAtIndex:index];
    if (!localPath(path)) return nil;
    NSString *url = [[NSURL fileURLWithPath:path] absoluteString];
    if (!url) return nil;
    [list appendFormat:@"%@\r\n", url];
    if ([list length] > 4 * 1024 * 1024) return nil;
  }
  NSData *bytes = [list dataUsingEncoding:NSUTF8StringEncoding];
  return [bytes length] <= 4 * 1024 * 1024 ? bytes : nil;
}
static NSArray *filePaths(NSData *bytes)
{
  if ([bytes length] > 4 * 1024 * 1024) return nil;
  NSString *text = [[[NSString alloc] initWithData:bytes encoding:NSUTF8StringEncoding] autorelease];
  if (!text) return nil;
  NSScanner *scanner = [NSScanner scannerWithString:text];
  [scanner setCharactersToBeSkipped:nil];
  NSCharacterSet *newline = [NSCharacterSet newlineCharacterSet];
  NSMutableArray *paths = [NSMutableArray array];
  while (![scanner isAtEnd]) {
    NSString *line = nil;
    [scanner scanUpToCharactersFromSet:newline intoString:&line];
    [scanner scanCharactersFromSet:newline intoString:NULL];
    if (![line length] || [line hasPrefix:@"#"]) continue;
    NSURL *url = [NSURL URLWithString:line];
    NSString *host = [url host], *path = [url path];
    if (![url isFileURL] || !localPath(path) ||
        ([host length] && [host caseInsensitiveCompare:@"localhost"] != NSOrderedSame) ||
        [paths count] >= 4096) return nil;
    [paths addObject:path];
  }
  return [paths count] ? paths : nil;
}

NSDictionary *WaylandPasteboardRepresentations(NSPasteboard *pasteboard, NSString *type)
{
  NSMutableDictionary *data = [NSMutableDictionary dictionary];
  NSData *bytes = [type isEqual:NSStringPboardType] ?
    [[pasteboard stringForType:type] dataUsingEncoding:NSUTF8StringEncoding] : [pasteboard dataForType:type];
  for (NSString *mime in WaylandMimesForType(type)) {
    NSData *representation = uriListMime(mime) ? fileURIs([pasteboard propertyListForType:type]) : bytes;
    if (representation) [data setObject:representation forKey:mime];
  }
  return data;
}
id WaylandPasteboardValue(NSString *mime, NSData *bytes)
{
  if (!bytes) return nil;
  if (uriListMime(mime)) return filePaths(bytes);
  if ([mime isEqual:NSFilenamesPboardType]) {
    if ([bytes length] > 4 * 1024 * 1024) return nil;
    @try {
      id paths = [NSDeserializer deserializePropertyListFromData:bytes mutableContainers:NO];
      if (![paths isKindOfClass:[NSArray class]] || ![paths count] || [paths count] > 4096) return nil;
      for (id path in paths) if (!localPath(path)) return nil;
      return paths;
    } @catch (NSException *exception) { return nil; }
  }
  if ([WaylandTypeForMime([mime UTF8String]) isEqual:NSStringPboardType])
    return [[[NSString alloc] initWithData:bytes encoding:NSUTF8StringEncoding] autorelease];
  return bytes;
}
BOOL WaylandStorePasteboardValue(NSPasteboard *pasteboard, NSString *type, id value)
{
  if ([value isKindOfClass:[NSString class]]) return [pasteboard setString:value forType:type];
  if ([value isKindOfClass:[NSData class]]) return [pasteboard setData:value forType:type];
  return value ? [pasteboard setPropertyList:value forType:type] : NO;
}

@interface WaylandOffer : NSObject
{
@public
  NSMutableArray *mimes;
  uint32_t sourceActions, action;
}
@end
@implementation WaylandOffer
- (id)init
{
  if ((self = [super init])) { mimes = [NSMutableArray new]; sourceActions = WL_DATA_DEVICE_MANAGER_DND_ACTION_COPY; }
  return self;
}
- (void)dealloc { [mimes release]; [super dealloc]; }
@end
static void recordOfferMime(void *data, const char *mime)
{
  NSString *type = [NSString stringWithUTF8String:mime];
  if (type) [((WaylandOffer *)data)->mimes addObject:type];
}
static void offer_mime(void *data, struct wl_data_offer *offer, const char *mime)
{ recordOfferMime(data, mime); }
static void primary_offer_mime(void *data, struct zwp_primary_selection_offer_v1 *offer, const char *mime)
{ recordOfferMime(data, mime); }
static const struct zwp_primary_selection_offer_v1_listener primary_offer_listener = {.offer = primary_offer_mime};

static void offer_actions(void *data, struct wl_data_offer *offer, uint32_t actions)
{ ((WaylandOffer *)data)->sourceActions = actions; }
static void offer_action(void *data, struct wl_data_offer *offer, uint32_t action)
{ ((WaylandOffer *)data)->action = action; }
static const struct wl_data_offer_listener offer_listener = {
  .offer = offer_mime, .source_actions = offer_actions, .action = offer_action
};
void WaylandRegisterOffer(struct wl_data_offer *offer)
{ wl_data_offer_add_listener(offer, &offer_listener, [WaylandOffer new]); }
static NSArray *selectionMimes(void *offer)
{
  WaylandOffer *state = offer ? wl_proxy_get_user_data(offer) : nil;
  return state ? state->mimes : [NSArray array];
}
NSArray *WaylandOfferMimes(struct wl_data_offer *offer) { return selectionMimes(offer); }
uint32_t WaylandOfferActions(struct wl_data_offer *offer)
{
  WaylandOffer *state = offer ? wl_data_offer_get_user_data(offer) : nil;
  return state ? state->sourceActions : 0;
}
uint32_t WaylandOfferAction(struct wl_data_offer *offer)
{
  WaylandOffer *state = offer ? wl_data_offer_get_user_data(offer) : nil;
  return !state ? 0 : wl_data_offer_get_version(offer) < 3 ? WL_DATA_DEVICE_MANAGER_DND_ACTION_COPY : state->action;
}
void WaylandDestroyOffer(struct wl_data_offer *offer)
{
  if (!offer) return;
  [(id)wl_data_offer_get_user_data(offer) release];
  wl_data_offer_destroy(offer);
}

/* Reads participate in the same modes as Wayland dispatch, including a Services
   DO reply. The UI keeps running while an external source supplies the pipe. */
@interface WaylandPasteboardRead : NSObject <RunLoopEvents>
{
  int fd;
  BOOL finished, failed;
  NSMutableData *bytes;
}
- (NSData *)receive:(void *)offer primary:(BOOL)primary mime:(NSString *)mime config:(WaylandConfig *)config timeout:(NSTimeInterval)timeout;
@end
@implementation WaylandPasteboardRead
- (void)receivedEvent:(void *)data type:(RunLoopEventType)type extra:(void *)extra forMode:(NSString *)mode
{
  unsigned char buffer[16384];
  ssize_t length;
  while ((length = read(fd, buffer, sizeof(buffer))) > 0) {
    if ([bytes length] + length > 64 * 1024 * 1024) { failed = finished = YES; return; }
    [bytes appendBytes:buffer length:length];
  }
  if (length == 0) finished = YES;
  else if (errno != EAGAIN && errno != EINTR) failed = finished = YES;
}
- (NSData *)receive:(void *)offer primary:(BOOL)primary mime:(NSString *)mime config:(WaylandConfig *)config timeout:(NSTimeInterval)timeout
{
  int pipeFDs[2];
  if (pipe2(pipeFDs, O_CLOEXEC)) return nil;
  fd = pipeFDs[0];
  fcntl(fd, F_SETFL, O_NONBLOCK);
  bytes = [NSMutableData new];
  NSRunLoop *loop = [NSRunLoop currentRunLoop];
  for (NSString *mode in transferModes())
    [loop addEvent:(void *)(intptr_t)fd type:ET_RDESC watcher:self forMode:mode];
  if (primary) zwp_primary_selection_offer_v1_receive(offer, [mime UTF8String], pipeFDs[1]);
  else wl_data_offer_receive(offer, [mime UTF8String], pipeFDs[1]);
  close(pipeFDs[1]);
  wl_display_flush(config->display);
  NSTimeInterval deadline = WaylandMonotonicTime() + MAX(0, MIN(5, timeout));
  while (!finished && WaylandMonotonicTime() < deadline)
    [loop runMode:NSDefaultRunLoopMode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.02]];
  for (NSString *mode in transferModes())
    [loop removeEvent:(void *)(intptr_t)fd type:ET_RDESC forMode:mode all:YES];
  close(fd);
  NSData *result = finished && !failed ? [[bytes copy] autorelease] : nil;
  [bytes release]; bytes = nil;
  return result;
}
@end

NSData *WaylandReadOffer(struct wl_data_offer *offer, NSString *mime, WaylandConfig *config, NSTimeInterval timeout)
{
  if (!offer || !mime || !config) return nil;
  WaylandPasteboardRead *reader = [WaylandPasteboardRead new];
  NSData *bytes = [reader receive:offer primary:NO mime:mime config:config timeout:timeout];
  [reader release];
  return bytes;
}

/* A slow receiver must not block the application or its Wayland event loop. */
@interface WaylandPasteboardWrite : NSObject
{
  NSData *bytes;
  int fd;
}
- (id)initWithData:(NSData *)data fd:(int)descriptor;
- (void)run:(id)unused;
@end
@implementation WaylandPasteboardWrite
- (id)initWithData:(NSData *)data fd:(int)descriptor
{
  if ((self = [super init])) { bytes = [data copy]; fd = descriptor; }
  return self;
}
- (void)run:(id)unused
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  sigset_t signals;
  sigemptyset(&signals); sigaddset(&signals, SIGPIPE);
  pthread_sigmask(SIG_BLOCK, &signals, NULL);
  const unsigned char *cursor = [bytes bytes];
  NSUInteger left = [bytes length];
  fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | O_NONBLOCK);
  NSTimeInterval deadline = WaylandMonotonicTime() + 5;
  while (left && WaylandMonotonicTime() < deadline) {
    ssize_t count = write(fd, cursor, left);
    if (count < 0 && errno == EINTR) continue;
    if (count < 0 && errno == EAGAIN) {
      struct pollfd descriptor = {.fd = fd, .events = POLLOUT};
      if (poll(&descriptor, 1, 100) < 0 && errno != EINTR) break;
      continue;
    }
    if (count <= 0) break;
    left -= count; cursor += count;
  }
  close(fd);
  [pool drain];
}
- (void)dealloc { [bytes release]; [super dealloc]; }
@end

void WaylandWriteDataToFD(NSData *data, int fd)
{
  WaylandPasteboardWrite *writer = [[WaylandPasteboardWrite alloc] initWithData:data fd:fd];
  [NSThread detachNewThreadSelector:@selector(run:) toTarget:writer withObject:nil];
  [writer release];
}

@interface WaylandPasteboard : NSObject
{
  WaylandConfig *config;
  void *source, *selection;
  BOOL primary;
  NSDictionary *snapshot;
  NSString *marker;
  unsigned generation;
  BOOL pending, writing;
}
- (id)initWithConfig:(WaylandConfig *)value primary:(BOOL)isPrimary;
- (NSPasteboard *)pasteboard;
- (void)destroySource;
- (void)destroySelection;
- (void)focusLost;
- (void)changed:(NSNotification *)notification;
- (void)publish:(id)unused;
- (void)selection:(void *)offer;
- (void)importSelection:(id)unused;
- (void)send:(const char *)mime fd:(int)fd;
- (void)cancelled:(void *)object;
- (void)invalidate;
@end

static void source_target(void *data, struct wl_data_source *source, const char *mime) {}
static void source_send(void *data, struct wl_data_source *source, const char *mime, int32_t fd)
{ [(WaylandPasteboard *)data send:mime fd:fd]; }
static void source_cancelled(void *data, struct wl_data_source *source)
{ [(WaylandPasteboard *)data cancelled:source]; }
static const struct wl_data_source_listener source_listener = {
  .target = source_target, .send = source_send, .cancelled = source_cancelled
};

static void primary_source_send(void *data, struct zwp_primary_selection_source_v1 *source, const char *mime, int32_t fd)
{ [(WaylandPasteboard *)data send:mime fd:fd]; }
static void primary_source_cancelled(void *data, struct zwp_primary_selection_source_v1 *source)
{ [(WaylandPasteboard *)data cancelled:source]; }
static const struct zwp_primary_selection_source_v1_listener primary_source_listener = {
  .send = primary_source_send, .cancelled = primary_source_cancelled
};
static void primary_data_offer(void *data, struct zwp_primary_selection_device_v1 *device,
    struct zwp_primary_selection_offer_v1 *offer)
{ zwp_primary_selection_offer_v1_add_listener(offer, &primary_offer_listener, [WaylandOffer new]); }
static void primary_selection(void *data, struct zwp_primary_selection_device_v1 *device,
    struct zwp_primary_selection_offer_v1 *offer)
{ [((WaylandConfig *)data)->primary_bridge selection:offer]; }
static const struct zwp_primary_selection_device_v1_listener primary_device_listener = {
  .data_offer = primary_data_offer, .selection = primary_selection
};

@implementation WaylandPasteboard
- (id)initWithConfig:(WaylandConfig *)value primary:(BOOL)isPrimary
{
  if (!(self = [super init])) return nil;
  config = value; primary = isPrimary;
  marker = [[@"application/x-nextspace-session-" stringByAppendingString:
    [[[[NSProcessInfo processInfo] environment] objectForKey:@"NEXTSPACE_SESSION_ID"]
      stringByAppendingString:primary ? @"-primary" : @""]] copy];
  [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(changed:)
    name:GSPasteboardDidChangeNotification object:nil];
  return self;
}
- (NSPasteboard *)pasteboard
{ return primary ? [NSPasteboard pasteboardWithName:@"Selection"] : [NSPasteboard generalPasteboard]; }
- (void)destroySource
{
  if (!source) return;
  if (primary) zwp_primary_selection_source_v1_destroy(source);
  else wl_data_source_destroy(source);
  source = NULL;
}
- (void)destroySelection
{
  if (selection && primary) {
    [(id)wl_proxy_get_user_data(selection) release];
    zwp_primary_selection_offer_v1_destroy(selection);
  } else WaylandDestroyOffer(selection);
  selection = NULL;
}
- (void)focusLost
{
  /* Selection offers expire when this client loses keyboard focus. Keep the
     shared pasteboard and any unpublished local copy, but cancel old imports. */
  [NSObject cancelPreviousPerformRequestsWithTarget:self selector:@selector(importSelection:) object:nil];
  generation++;
  [self destroySelection];
}
- (void)dealloc
{
  [self invalidate];
  [snapshot release]; [marker release];
  [super dealloc];
}
- (void)invalidate
{
  [NSObject cancelPreviousPerformRequestsWithTarget:self];
  [[NSNotificationCenter defaultCenter] removeObserver:self];
  [self destroySource]; [self destroySelection];
}
- (void)changed:(NSNotification *)notification
{
  if (writing || ![[[notification object] name] isEqual:(primary ? @"Selection" : NSGeneralPboard)]) return;
  generation++;
  pending = YES;
  [NSObject cancelPreviousPerformRequestsWithTarget:self selector:@selector(publish:) object:nil];
  [self performSelector:@selector(publish:) withObject:nil afterDelay:0 inModes:WaylandApplicationModes()];
}
- (void)publish:(id)unused
{
  if (!pending || !config->keyboard_focus || !config->selection_serial) return;
  if (writing || GSPasteboardOperationInProgress()) {
    [NSObject cancelPreviousPerformRequestsWithTarget:self selector:@selector(publish:) object:nil];
    [self performSelector:@selector(publish:) withObject:nil afterDelay:0.01 inModes:WaylandApplicationModes()];
    return;
  }
  pending = NO;
  NSPasteboard *pasteboard = [self pasteboard];
  NSMutableDictionary *data = [NSMutableDictionary dictionary];
  /* Some GNUstep DO runtimes return a proxy despite the bycopy contract.
     Fast enumeration would marshal a stack pointer to the other process. */
  NSArray *types = [pasteboard types];
  NSUInteger i, count = [types count];
  for (i = 0; i < count; i++) {
    NSString *type = [types objectAtIndex:i];
    [data addEntriesFromDictionary:WaylandPasteboardRepresentations(pasteboard, type)];
  }
  if (primary && ![data count]) {
    [self destroySource];
    [snapshot release]; snapshot = nil;
    zwp_primary_selection_device_v1_set_selection(config->primary_device, NULL, config->selection_serial);
    wl_display_flush(config->display);
    return;
  }
  [data setObject:[NSData data] forKey:marker];
  [self destroySource];
  [snapshot release]; snapshot = [data copy];
  if (primary) {
    source = zwp_primary_selection_device_manager_v1_create_source(config->primary_manager);
    zwp_primary_selection_source_v1_add_listener(source, &primary_source_listener, self);
    for (NSString *mime in snapshot) zwp_primary_selection_source_v1_offer(source, [mime UTF8String]);
    zwp_primary_selection_device_v1_set_selection(config->primary_device, source, config->selection_serial);
  } else {
    source = wl_data_device_manager_create_data_source(config->data_device_manager);
    wl_data_source_add_listener(source, &source_listener, self);
    for (NSString *mime in snapshot) wl_data_source_offer(source, [mime UTF8String]);
    wl_data_device_set_selection(config->data_device, source, config->selection_serial);
  }
  wl_display_flush(config->display);
}
- (void)cancelled:(void *)object
{
  if (object == source) [self destroySource];
}
- (void)send:(const char *)mime fd:(int)fd
{
  NSData *data = [snapshot objectForKey:[NSString stringWithUTF8String:mime]];
  WaylandWriteDataToFD(data, fd);
}
- (void)selection:(void *)offer
{
  [NSObject cancelPreviousPerformRequestsWithTarget:self selector:@selector(importSelection:) object:nil];
  generation++;
  if (selection != offer) [self destroySelection];
  selection = offer;
  if ((!offer && pending) || [selectionMimes(offer) containsObject:marker]) return;
  pending = NO;
  [self performSelector:@selector(importSelection:) withObject:nil afterDelay:0 inModes:WaylandApplicationModes()];
}
- (void)importSelection:(id)unused
{
  if (!config->keyboard_focus) return;
  if (!selection) {
    /* Keep shared storage on focus loss. A focused, idle receiver imports
       explicit clearing for either clipboard or primary selection. */
    if (config->keyboard_focus && !pending) {
      writing = YES;
      @try { [[self pasteboard] declareTypes:[NSArray array] owner:nil]; }
      @finally { writing = NO; }
    }
    return;
  }
  if ([selectionMimes(selection) containsObject:marker]) return;
  unsigned started = generation;
  NSArray *mimes = [[selectionMimes(selection) copy] autorelease];
  NSMutableDictionary *data = [NSMutableDictionary dictionary];
  for (NSString *mime in mimes) {
    NSString *type = WaylandTypeForMime([mime UTF8String]);
    if ([data objectForKey:type]) continue;
    WaylandPasteboardRead *reader = [WaylandPasteboardRead new];
    NSData *bytes = [reader receive:selection primary:primary mime:mime config:config timeout:5];
    [reader release];
    if (generation != started || !config->keyboard_focus) return;
    id value = WaylandPasteboardValue(mime, bytes);
    if (value) [data setObject:value forKey:type];
  }
  if (generation != started || !config->keyboard_focus || ![data count]) return;
  NSPasteboard *pasteboard = [self pasteboard];
  writing = YES;
  @try {
    [pasteboard declareTypes:[data allKeys] owner:nil];
    for (NSString *type in data) {
      WaylandStorePasteboardValue(pasteboard, type, [data objectForKey:type]);
    }
  } @finally { writing = NO; }
}
@end

void WaylandSetupPasteboard(WaylandConfig *config)
{
  if ([GSPasteboardServerName() isEqual:PBSNAME]) return;
  config->pasteboard_bridge = [[WaylandPasteboard alloc] initWithConfig:config primary:NO];
  if (config->primary_manager && config->seat) {
    config->primary_bridge = [[WaylandPasteboard alloc] initWithConfig:config primary:YES];
    config->primary_device = zwp_primary_selection_device_manager_v1_get_device(config->primary_manager, config->seat);
    zwp_primary_selection_device_v1_add_listener(config->primary_device, &primary_device_listener, config);
  }
}
void WaylandSelection(WaylandConfig *config, struct wl_data_offer *offer)
{
  if (config->pasteboard_bridge) [config->pasteboard_bridge selection:offer];
  else WaylandDestroyOffer(offer);
}
void WaylandPasteboardFocusLost(WaylandConfig *config)
{
  [config->pasteboard_bridge focusLost];
  [config->primary_bridge focusLost];
}
void WaylandPasteboardInput(WaylandConfig *config, uint32_t serial)
{
  config->selection_serial = serial;
  [config->pasteboard_bridge performSelector:@selector(publish:) withObject:nil afterDelay:0 inModes:WaylandApplicationModes()];
  [config->primary_bridge performSelector:@selector(publish:) withObject:nil afterDelay:0 inModes:WaylandApplicationModes()];
}
