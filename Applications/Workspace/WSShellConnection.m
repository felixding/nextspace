/* Private shell protocol client; it never connects to the public socket.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import "WSShellConnection.h"
#import <AppKit/NSApplication.h>
#import "nextspace-shell-v1-client-protocol.h"
#include <wayland-client.h>
#include <xkbcommon/xkbcommon.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <math.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <time.h>

NSString *WSShellWindowsDidChangeNotification = @"WSShellWindowsDidChange";
NSString *WSShellConnectionDidCloseNotification = @"WSShellConnectionDidClose";
NSString *WSShellOutputsDidChangeNotification = @"WSShellOutputsDidChange";
NSString *WSShellOutputResultNotification = @"WSShellOutputResult";
NSString *WSShellInputSettingsDidChangeNotification = @"WSShellInputSettingsDidChange";
NSString *WSShellDesktopsDidChangeNotification = @"WSShellDesktopsDidChange";
NSString *WSShellInteractiveMoveNotification = @"WSShellInteractiveMove";

static int descriptorFromString(const char *value)
{
  if (!value || !*value) return -1;
  const char *p;
  for (p = value; *p; p++) if (*p < '0' || *p > '9') return -1;
  errno = 0;
  char *end;
  long descriptor = strtol(value, &end, 10);
  return errno || *end || descriptor < 3 || descriptor > INT_MAX ? -1 : (int)descriptor;
}

int WSConsumeShellDescriptor(void)
{
  static BOOL consumed = NO;
  if (consumed) return -1;
  consumed = YES;
  int descriptor = -1;
  BOOL seen = NO;
  NSArray *arguments = [[NSProcessInfo processInfo] arguments];
  NSUInteger index;
  for (index = 1; index < [arguments count]; index++) {
    if (![[arguments objectAtIndex:index] isEqualToString:@"--nextspace-shell-fd"]) continue;
    if (seen || index + 1 == [arguments count]) return -1;
    seen = YES;
    descriptor = descriptorFromString([[arguments objectAtIndex:++index] UTF8String]);
  }
  int publicDescriptor = descriptorFromString(getenv("WAYLAND_SOCKET"));
  if (descriptor < 0) return -1;
  /* Two wl_display instances must never own the same descriptor. */
  if (descriptor == publicDescriptor) return -1;
  int flags = fcntl(descriptor, F_GETFD);
  int type;
  socklen_t length = sizeof(type);
  struct sockaddr_un address;
  socklen_t addressLength = sizeof(address);
  if (flags < 0 || fcntl(descriptor, F_SETFD, flags | FD_CLOEXEC) < 0 ||
      getsockopt(descriptor, SOL_SOCKET, SO_TYPE, &type, &length) < 0 || type != SOCK_STREAM ||
      getpeername(descriptor, (struct sockaddr *)&address, &addressLength) < 0 ||
      address.sun_family != AF_UNIX) {
    close(descriptor);
    return -1;
  }
  return descriptor;
}

@interface WSShellConnection (ProtocolEvents)
- (void)recordInputSettings:(NSDictionary *)settings;
- (void)recordBackground:(NSDictionary *)color;
- (void)recordDesktop:(NSUInteger)index count:(NSUInteger)count;
- (void)recordMove:(NSDictionary *)event;
- (void)recordInputResult:(NSDictionary *)result;
- (void)resetOutputs:(uint32_t)revision;
- (void)recordOutput:(NSDictionary *)output;
- (void)recordOutputInfo:(NSDictionary *)info identifier:(NSNumber *)identifier;
- (void)recordOutputMode:(NSDictionary *)mode identifier:(NSNumber *)identifier;
- (void)publishOutputs;
- (void)recordOutputResult:(NSDictionary *)result;
- (void)resetWindows;
- (void)recordPointerWindow:(uint32_t)identifier;
- (void)recordWindow:(NSDictionary *)window;
- (void)recordGammaResult:(NSDictionary *)result;
- (void)recordWindowInfo:(NSDictionary *)info identifier:(NSNumber *)identifier;
- (void)removeWindow:(NSNumber *)identifier;
- (void)publishWindows;
- (void)bindRegistry:(struct wl_registry *)registry name:(uint32_t)name version:(uint32_t)version;
- (void)removeGlobal:(uint32_t)name;
- (void)flush;
@end

static NSString *shellString(const char *value)
{
  return [NSString stringWithUTF8String:value] ?: @"";
}
static NSNumber *shellNumber(long long value) { return [NSNumber numberWithLongLong:value]; }
static NSArray *orderedValues(NSDictionary *entries)
{
  NSMutableArray *result = [NSMutableArray arrayWithCapacity:[entries count]];
  for (NSNumber *identifier in [[entries allKeys] sortedArrayUsingSelector:@selector(compare:)])
    [result addObject:[entries objectForKey:identifier]];
  return result;
}
static void mergeEntry(NSMutableDictionary *entries, NSDictionary *info, NSNumber *identifier)
{
  NSDictionary *entry = [entries objectForKey:identifier];
  if (!entry) return;
  NSMutableDictionary *updated = [[entry mutableCopy] autorelease];
  [updated addEntriesFromDictionary:info];
  [entries setObject:[[updated copy] autorelease] forKey:identifier];
}
static void shellReset(void *data, struct nextspace_shell_v1 *shell)
{ [(WSShellConnection *)data resetWindows]; }
static void shellWindow(void *data, struct nextspace_shell_v1 *shell, uint32_t identifier,
    const char *appID, const char *title, int32_t pid, uint32_t flags,
    int32_t x, int32_t y, int32_t width, int32_t height)
{
  [(WSShellConnection *)data recordWindow:[NSDictionary dictionaryWithObjectsAndKeys:
    shellNumber(identifier), @"id", shellString(appID), @"app_id", shellString(title), @"title",
    shellNumber(pid), @"pid", shellNumber(flags), @"flags", shellNumber(x), @"x", shellNumber(y), @"y",
    shellNumber(width), @"width", shellNumber(height), @"height", nil]];
}
static void shellClosed(void *data, struct nextspace_shell_v1 *shell, uint32_t identifier)
{ [(WSShellConnection *)data removeWindow:shellNumber(identifier)]; }
static void shellDone(void *data, struct nextspace_shell_v1 *shell)
{ [(WSShellConnection *)data publishWindows]; }
static void shellWindowInfo(void *data, struct nextspace_shell_v1 *shell, uint32_t identifier,
    uint32_t clientID, uint32_t style, uint32_t titleHeight, int32_t level)
{
  [(WSShellConnection *)data recordWindowInfo:[NSDictionary dictionaryWithObjectsAndKeys:
    shellNumber(clientID), @"client_id", shellNumber(style), @"style",
    shellNumber(titleHeight), @"title_height", shellNumber(level), @"level", nil]
    identifier:shellNumber(identifier)];
}
static void shellPointerFocus(void *data, struct nextspace_shell_v1 *shell, uint32_t identifier)
{ [(WSShellConnection *)data recordPointerWindow:identifier]; }
static void shellOutputsReset(void *data, struct nextspace_shell_v1 *shell, uint32_t revision)
{ [(WSShellConnection *)data resetOutputs:revision]; }
static void shellOutput(void *data, struct nextspace_shell_v1 *shell, uint32_t identifier,
    const char *name, uint32_t enabled, uint32_t primary, int32_t width, int32_t height,
    int32_t refresh, uint32_t scale, uint32_t transform, int32_t x, int32_t y,
    int32_t logicalWidth, int32_t logicalHeight)
{
  [(WSShellConnection *)data recordOutput:[NSDictionary dictionaryWithObjectsAndKeys:
    shellNumber(identifier), @"id", shellString(name), @"name", shellNumber(enabled), @"enabled",
    shellNumber(primary), @"primary", shellNumber(width), @"width", shellNumber(height), @"height",
    shellNumber(refresh), @"refresh", shellNumber(scale), @"scale", shellNumber(transform), @"transform",
    shellNumber(x), @"x", shellNumber(y), @"y", shellNumber(logicalWidth), @"logical_width",
    shellNumber(logicalHeight), @"logical_height", [NSArray array], @"modes", nil]];
}
static void shellOutputIdentity(void *data, struct nextspace_shell_v1 *shell, uint32_t identifier,
    const char *make, const char *model, const char *serial, int32_t width, int32_t height)
{
  [(WSShellConnection *)data recordOutputInfo:[NSDictionary dictionaryWithObjectsAndKeys:
    shellString(make), @"make", shellString(model), @"model", shellString(serial), @"serial",
    shellNumber(width), @"width_mm", shellNumber(height), @"height_mm", nil] identifier:shellNumber(identifier)];
}
static void shellOutputMode(void *data, struct nextspace_shell_v1 *shell, uint32_t identifier,
    int32_t width, int32_t height, int32_t refresh, uint32_t preferred)
{
  [(WSShellConnection *)data recordOutputMode:[NSDictionary dictionaryWithObjectsAndKeys:
    shellNumber(width), @"width", shellNumber(height), @"height", shellNumber(refresh), @"refresh",
    shellNumber(preferred), @"preferred", nil] identifier:shellNumber(identifier)];
}
static void shellOutputsDone(void *data, struct nextspace_shell_v1 *shell)
{ [(WSShellConnection *)data publishOutputs]; }
static void shellOutputGamma(void *data, struct nextspace_shell_v1 *shell, uint32_t identifier,
    uint32_t size, wl_fixed_t red, wl_fixed_t green, wl_fixed_t blue, wl_fixed_t brightness)
{
  NSDictionary *gamma = [NSDictionary dictionaryWithObjectsAndKeys:
    [NSNumber numberWithDouble:wl_fixed_to_double(red)], @"red",
    [NSNumber numberWithDouble:wl_fixed_to_double(green)], @"green",
    [NSNumber numberWithDouble:wl_fixed_to_double(blue)], @"blue",
    [NSNumber numberWithDouble:wl_fixed_to_double(brightness)], @"brightness", nil];
  [(WSShellConnection *)data recordOutputInfo:[NSDictionary dictionaryWithObjectsAndKeys:
    shellNumber(size), @"gamma_size", gamma, @"gamma", nil] identifier:shellNumber(identifier)];
}
static void shellGammaResult(void *data, struct nextspace_shell_v1 *shell,
    uint32_t serial, uint32_t success, const char *reason)
{
  [(WSShellConnection *)data recordGammaResult:[NSDictionary dictionaryWithObjectsAndKeys:
    shellNumber(serial), @"serial", shellNumber(success), @"success", shellString(reason), @"reason", nil]];
}
static void shellWorkArea(void *data, struct nextspace_shell_v1 *shell, uint32_t identifier,
    int32_t x, int32_t y, int32_t width, int32_t height)
{
  [(WSShellConnection *)data recordOutputInfo:[NSDictionary dictionaryWithObjectsAndKeys:
    shellNumber(x), @"work_x", shellNumber(y), @"work_y", shellNumber(width), @"work_width",
    shellNumber(height), @"work_height", nil] identifier:shellNumber(identifier)];
}
static void shellOutputResult(void *data, struct nextspace_output_configuration_v1 *configuration,
    uint32_t status, const char *reason)
{
  [(WSShellConnection *)data recordOutputResult:[NSDictionary dictionaryWithObjectsAndKeys:
    shellNumber(status), @"status", shellString(reason), @"reason", nil]];
}
static const struct nextspace_output_configuration_v1_listener outputListener = {.result = shellOutputResult};
static void shellInputs(void *data, struct nextspace_shell_v1 *shell, const char *model, const char *layout,
    const char *variant, const char *options, uint32_t delay, uint32_t rate, uint32_t numlock,
    wl_fixed_t speed, uint32_t profile, uint32_t devices)
{
  [(WSShellConnection *)data recordInputSettings:[NSDictionary dictionaryWithObjectsAndKeys:
    shellString(model), @"model", shellString(layout), @"layout", shellString(variant), @"variant",
    shellString(options), @"options", shellNumber(delay), @"delay", shellNumber(rate), @"rate",
    shellNumber(numlock), @"numlock", [NSNumber numberWithDouble:wl_fixed_to_double(speed)], @"speed",
    shellNumber(profile), @"profile", shellNumber(devices), @"accelerated_devices", nil]];
}
static void shellInputResult(void *data, struct nextspace_shell_v1 *shell, uint32_t serial,
    uint32_t success, const char *reason)
{
  [(WSShellConnection *)data recordInputResult:[NSDictionary dictionaryWithObjectsAndKeys:
    shellNumber(serial), @"serial", [NSNumber numberWithBool:success], @"success", shellString(reason), @"reason", nil]];
}
static void shellBackground(void *data, struct nextspace_shell_v1 *shell,
    wl_fixed_t red, wl_fixed_t green, wl_fixed_t blue)
{
  [(WSShellConnection *)data recordBackground:[NSDictionary dictionaryWithObjectsAndKeys:
    [NSNumber numberWithDouble:wl_fixed_to_double(red)], @"Red",
    [NSNumber numberWithDouble:wl_fixed_to_double(green)], @"Green",
    [NSNumber numberWithDouble:wl_fixed_to_double(blue)], @"Blue", nil]];
}
static void shellDesktops(void *data, struct nextspace_shell_v1 *shell, uint32_t current, uint32_t count)
{ [(WSShellConnection *)data recordDesktop:current count:count]; }
static void shellWindowDesktop(void *data, struct nextspace_shell_v1 *shell, uint32_t identifier,
    uint32_t index, uint32_t sticky)
{
  [(WSShellConnection *)data recordWindowInfo:[NSDictionary dictionaryWithObjectsAndKeys:
    shellNumber(index), @"desktop", [NSNumber numberWithBool:sticky != 0], @"sticky", nil] identifier:shellNumber(identifier)];
}
static void shellInteractiveMove(void *data, struct nextspace_shell_v1 *shell,
    uint32_t identifier, uint32_t phase, int32_t x, int32_t y,
    int32_t screenX, int32_t screenY, int32_t screenWidth, int32_t screenHeight)
{
  [(WSShellConnection *)data recordMove:[NSDictionary dictionaryWithObjectsAndKeys:
    shellNumber(identifier), @"id", shellNumber(phase), @"phase", shellNumber(x), @"x", shellNumber(y), @"y",
    shellNumber(screenX), @"screen_x", shellNumber(screenY), @"screen_y",
    shellNumber(screenWidth), @"screen_width", shellNumber(screenHeight), @"screen_height", nil]];
}
static const struct nextspace_shell_v1_listener shellListener = {
  .reset = shellReset, .window = shellWindow, .closed = shellClosed,
  .done = shellDone, .window_info = shellWindowInfo, .pointer_focus = shellPointerFocus,
  .outputs_reset = shellOutputsReset, .output = shellOutput, .output_identity = shellOutputIdentity,
  .output_mode = shellOutputMode, .outputs_done = shellOutputsDone,
  .input_settings = shellInputs, .input_result = shellInputResult, .background = shellBackground,
  .desktops = shellDesktops, .window_desktop = shellWindowDesktop, .interactive_move = shellInteractiveMove,
  .output_work_area = shellWorkArea, .output_gamma = shellOutputGamma,
  .output_gamma_result = shellGammaResult
};
static void registryGlobal(void *data, struct wl_registry *registry, uint32_t name,
    const char *interface, uint32_t version)
{
  if (strcmp(interface, nextspace_shell_v1_interface.name) == 0)
    [(WSShellConnection *)data bindRegistry:registry name:name version:version];
}
static void registryRemove(void *data, struct wl_registry *registry, uint32_t name)
{ [(WSShellConnection *)data removeGlobal:name]; }
static const struct wl_registry_listener registryListener = { registryGlobal, registryRemove };

static void syncDone(void *data, struct wl_callback *callback, uint32_t serial)
{ *(BOOL *)data = YES; }
static const struct wl_callback_listener syncListener = { syncDone };

static int64_t monotonicMilliseconds(void)
{
  struct timespec now;
  clock_gettime(CLOCK_MONOTONIC, &now);
  return (int64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

/* Bound startup when an inherited descriptor is connected to a dead helper. */
static BOOL shellRoundtrip(struct wl_display *display)
{
  BOOL done = NO, success = NO;
  struct wl_callback *callback = wl_display_sync(display);
  if (!callback) return NO;
  wl_callback_add_listener(callback, &syncListener, &done);
  int64_t deadline = monotonicMilliseconds() + 5000;
  while (wl_display_dispatch_pending(display) >= 0) {
    if (done) { success = YES; break; }
    int remaining = (int)(deadline - monotonicMilliseconds());
    if (remaining <= 0) break;
    short events = POLLIN;
    if (wl_display_flush(display) < 0) {
      if (errno != EAGAIN) break;
      events |= POLLOUT;
    }
    struct pollfd socket = { wl_display_get_fd(display), events, 0 };
    int result = poll(&socket, 1, remaining);
    if (result < 0 && errno == EINTR) continue;
    if (result <= 0 || (socket.revents & (POLLERR | POLLHUP | POLLNVAL))) break;
    if ((socket.revents & POLLIN) && wl_display_dispatch(display) < 0) break;
  }
  wl_callback_destroy(callback);
  return success;
}

@implementation WSShellConnection
- (id)initWithFileDescriptor:(int)descriptor
{
  if (!(self = [super init])) { if (descriptor >= 0) close(descriptor); return nil; }
  _windows = [NSMutableDictionary new];
  _moveEvents = [NSMutableArray new];
  _pendingOutputs = [NSMutableDictionary new];
  _outputs = [NSDictionary new];
  _runLoop = [[NSRunLoop currentRunLoop] retain];
  _modes = [[NSArray alloc] initWithObjects:NSDefaultRunLoopMode, NSConnectionReplyMode,
    NSModalPanelRunLoopMode, NSEventTrackingRunLoopMode, nil];
  if (descriptor < 0) { [self release]; return nil; }
  _display = wl_display_connect_to_fd(descriptor);
  /* libwayland closes the supplied descriptor on connect failure too. */
  if (!_display) { [self release]; return nil; }
  _registry = wl_display_get_registry(_display);
  wl_registry_add_listener(_registry, &registryListener, self);
  _dispatching = YES;
  BOOL connected = shellRoundtrip(_display) && _shell && shellRoundtrip(_display) && _ready;
  _dispatching = NO;
  if (!connected || _invalidated) {
    [self release]; return nil;
  }
  _changed = NO;
  for (NSString *mode in _modes)
    [_runLoop addEvent:(void *)(intptr_t)wl_display_get_fd(_display)
      type:ET_RDESC watcher:self forMode:mode];
  [self flush];
  return self;
}
- (void)dealloc
{
  [self invalidate];
  [_windows release]; [_modes release]; [_runLoop release];
  [_moveEvents release]; [_movingWindow release];
  [_outputs release]; [_pendingOutputs release]; [_outputResult release];
  [_outputReply release];
  [_inputs release]; [_inputResult release]; [_background release];
  [_gammaResult release];
  [_outputToken release]; [_outputLeaseResult release];
  [super dealloc];
}
- (NSDictionary *)failedOutputResult
{
  return [NSDictionary dictionaryWithObjectsAndKeys:[NSNumber numberWithInt:4], @"status",
    @"invalid or stale output transaction", @"reason", nil];
}
- (BOOL)hasPendingOutputLayout
{ return _outputToken && [[_outputLeaseResult objectForKey:@"status"] intValue] == 1; }
- (void)clearOutputLease
{
  [_outputToken release]; _outputToken = nil;
  [_outputLeaseResult release]; _outputLeaseResult = nil;
}
- (bycopy NSData *)nextspaceSettingsRequest:(bycopy NSData *)bytes
{
  NSDictionary *request = OSESessionSettingsDecode(bytes);
  if ([[request objectForKey:@"schema"] integerValue] != 1) return nil;
  NSString *action = [request objectForKey:@"action"];
  if (![action isKindOfClass:[NSString class]]) return nil;
  NSDictionary *result = nil;
  if ([action isEqual:@"background"]) {
    result = [request objectForKey:@"color"] ? [self setBackgroundColor:[request objectForKey:@"color"]] :
      [self backgroundColor];
  } else if ([action isEqual:@"input-state"]) {
    if ([self refreshInputSettings]) result = [self inputSettings];
  } else if ([action isEqual:@"keyboard"]) result = [self setKeyboardSettings:[request objectForKey:@"settings"]];
  else if ([action isEqual:@"pointer"]) result = [self setPointerSettings:[request objectForKey:@"settings"]];
  else if ([action isEqual:@"gamma"]) result = [self setOutput:[request objectForKey:@"id"]
    gamma:[request objectForKey:@"settings"]];
  else if ([action isEqual:@"state"]) result = [self nextspaceDisplayState];
  else if ([action isEqual:@"test"])
    result = [self nextspaceTestDisplayLayout:[request objectForKey:@"layout"]
      revision:[[request objectForKey:@"revision"] unsignedIntegerValue]];
  else if ([action isEqual:@"apply"])
    result = [self nextspaceApplyDisplayLayout:[request objectForKey:@"layout"]
      revision:[[request objectForKey:@"revision"] unsignedIntegerValue]
      timeout:[[request objectForKey:@"timeout"] unsignedIntegerValue]];
  else if ([action isEqual:@"confirm"]) result = [self nextspaceConfirmDisplayLayout:[request objectForKey:@"token"]];
  else if ([action isEqual:@"cancel"]) result = [self nextspaceCancelDisplayLayout:[request objectForKey:@"token"]];
  else if ([action isEqual:@"status"]) result = [self nextspaceDisplayLayoutStatus:[request objectForKey:@"token"]];
  return result ? OSESessionSettingsEncode(result) : nil;
}
- (bycopy NSDictionary *)nextspaceDisplayState
{
  if (![self refreshOutputs]) return nil;
  return [NSDictionary dictionaryWithObjectsAndKeys:[NSNumber numberWithInt:1], @"schema",
    [NSNumber numberWithUnsignedInteger:[self outputRevision]], @"revision",
    [self outputs], @"heads", [NSNumber numberWithBool:
      [[[self outputResult] objectForKey:@"status"] intValue] == 1], @"pending", nil];
}
- (bycopy NSDictionary *)nextspaceTestDisplayLayout:(bycopy NSArray *)layout revision:(NSUInteger)revision
{
  if ([self hasPendingOutputLayout]) return [self failedOutputResult];
  [self clearOutputLease];
  return [self testOutputLayout:layout revision:revision] ?: [self failedOutputResult];
}
- (bycopy NSDictionary *)nextspaceApplyDisplayLayout:(bycopy NSArray *)layout
    revision:(NSUInteger)revision timeout:(NSUInteger)milliseconds
{
  if ([self hasPendingOutputLayout]) return [self failedOutputResult];
  NSDictionary *result = [self applyOutputLayout:layout revision:revision timeout:milliseconds];
  if (!result) return [self failedOutputResult];
  if ([[result objectForKey:@"status"] intValue] != 1) return result;
  /* A rejected stale request must not erase the preceding timeout result. */
  [self clearOutputLease];
  _outputToken = [[[NSProcessInfo processInfo] globallyUniqueString] copy];
  _outputLeaseResult = [_outputResult copy];
  NSMutableDictionary *reply = [[result mutableCopy] autorelease];
  [reply setObject:_outputToken forKey:@"token"];
  return reply;
}
- (bycopy NSDictionary *)nextspaceDisplayLayoutStatus:(bycopy NSString *)token
{
  if (![token isKindOfClass:[NSString class]] || ![_outputToken isEqual:token]) return [self failedOutputResult];
  NSMutableDictionary *result = [[_outputLeaseResult mutableCopy] autorelease];
  [result setObject:_outputToken forKey:@"token"];
  return result;
}
- (bycopy NSDictionary *)nextspaceConfirmDisplayLayout:(bycopy NSString *)token
{
  if (![token isKindOfClass:[NSString class]] || ![_outputToken isEqual:token] || ![self hasPendingOutputLayout])
    return [self failedOutputResult];
  if (![self confirmOutputLayout]) return [self failedOutputResult];
  return [self nextspaceDisplayLayoutStatus:token];
}
- (bycopy NSDictionary *)nextspaceCancelDisplayLayout:(bycopy NSString *)token
{
  if (![token isKindOfClass:[NSString class]] || ![_outputToken isEqual:token] || ![self hasPendingOutputLayout])
    return [self failedOutputResult];
  if (![self cancelOutputLayout]) return [self failedOutputResult];
  return [self nextspaceDisplayLayoutStatus:token];
}
- (BOOL)isConnected { return _display && _ready; }
- (NSArray *)windows { return orderedValues(_windows); }
- (NSDictionary *)windowForID:(NSNumber *)identifier
{
  /* Callers can dispatch nested loops while inspecting this immutable state. */
  return [[[_windows objectForKey:identifier] retain] autorelease];
}
- (void)bindRegistry:(struct wl_registry *)registry name:(uint32_t)name version:(uint32_t)version
{
  if (_shell || version < 7) return;
  _global = name;
  _shell = wl_registry_bind(registry, name, &nextspace_shell_v1_interface, MIN(version, 18));
  nextspace_shell_v1_add_listener(_shell, &shellListener, self);
}
- (void)removeGlobal:(uint32_t)name
{
  if (name == _global) [self invalidate];
}
- (NSNumber *)pointerWindow { return shellNumber(_pointerWindow); }
- (NSNumber *)movingWindow { return _movingWindow; }
- (void)cancelMove:(NSNumber *)identifier
{
  if (_shell && nextspace_shell_v1_get_version(_shell) >= 11) {
    nextspace_shell_v1_cancel_move(_shell, [identifier unsignedIntValue]); [self flush];
  }
}
- (void)recordMove:(NSDictionary *)event
{
  [_movingWindow release];
  _movingWindow = [[event objectForKey:@"phase"] unsignedIntValue] == 0 ? [[event objectForKey:@"id"] retain] : nil;
  [_moveEvents addObject:event];
}
- (void)recordPointerWindow:(uint32_t)identifier
{
  if (_pointerWindow != identifier) { _pointerWindow = identifier; _changed = YES; }
}
- (void)resetWindows
{ [_windows removeAllObjects]; [_movingWindow release]; _movingWindow = nil; [_moveEvents removeAllObjects]; }
- (void)recordWindow:(NSDictionary *)window
{ [_windows setObject:window forKey:[window objectForKey:@"id"]]; }
- (void)recordWindowInfo:(NSDictionary *)info identifier:(NSNumber *)identifier
{ mergeEntry(_windows, info, identifier); }
- (void)removeWindow:(NSNumber *)identifier
{
  [_windows removeObjectForKey:identifier];
  if ([_movingWindow isEqual:identifier]) { [_movingWindow release]; _movingWindow = nil; }
}
- (void)publishWindows
{
  _ready = YES; _changed = YES;
}
- (void)watchWrite:(BOOL)watch
{
  if (_watchingWrite == watch || !_display) return;
  _watchingWrite = watch;
  for (NSString *mode in _modes) {
    void *descriptor = (void *)(intptr_t)wl_display_get_fd(_display);
    if (watch) [_runLoop addEvent:descriptor type:ET_WDESC watcher:self forMode:mode];
    else [_runLoop removeEvent:descriptor type:ET_WDESC forMode:mode all:NO];
  }
}
- (void)flush
{
  if (!_display) return;
  if (wl_display_flush(_display) >= 0) [self watchWrite:NO];
  else if (errno == EAGAIN) [self watchWrite:YES];
  else [self invalidate];
}
- (void)receivedEvent:(void *)data type:(RunLoopEventType)type extra:(void *)extra forMode:(NSString *)mode
{
  if (!_display) return;
  [self retain];
  if (type == ET_RDESC) {
    _dispatching = YES;
    if (wl_display_dispatch(_display) < 0) _invalidated = YES;
    _dispatching = NO;
  }
  if (_invalidated) [self invalidate];
  else {
    [self flush];
    /* Preserve begin/end ordering even when one dispatch reads both events. */
    NSArray *moves = [[_moveEvents copy] autorelease];
    [_moveEvents removeAllObjects];
    for (NSDictionary *event in moves)
      [[NSNotificationCenter defaultCenter] postNotificationName:WSShellInteractiveMoveNotification
        object:self userInfo:event];
    if (_desktopsChanged && [self isConnected]) {
      _desktopsChanged = NO;
      [[NSNotificationCenter defaultCenter] postNotificationName:WSShellDesktopsDidChangeNotification object:self];
    }
    if (_inputsChanged && [self isConnected]) {
      _inputsChanged = NO;
      [[NSNotificationCenter defaultCenter] postNotificationName:WSShellInputSettingsDidChangeNotification object:self];
    }
    if (_outputsChanged && [self isConnected]) {
      _outputsChanged = NO;
      [[NSNotificationCenter defaultCenter] postNotificationName:WSShellOutputsDidChangeNotification object:self];
    }
    if (_outputResultChanged && [self isConnected]) {
      _outputResultChanged = NO;
      [[NSNotificationCenter defaultCenter] postNotificationName:WSShellOutputResultNotification object:self];
    }
    if (_changed && [self isConnected]) {
      _changed = NO;
      [[NSNotificationCenter defaultCenter]
        postNotificationName:WSShellWindowsDidChangeNotification object:self];
    }
  }
  [self release];
}
- (void)invalidate
{
  if (!_display) return;
  if (_dispatching) { _invalidated = YES; return; }
  BOOL notify = _ready;
  _ready = NO;
  void *descriptor = (void *)(intptr_t)wl_display_get_fd(_display);
  for (NSString *mode in _modes) {
    [_runLoop removeEvent:descriptor type:ET_RDESC forMode:mode all:NO];
    if (_watchingWrite) [_runLoop removeEvent:descriptor type:ET_WDESC forMode:mode all:NO];
  }
  _watchingWrite = NO;
  if (_configuration) { nextspace_output_configuration_v1_destroy(_configuration); _configuration = NULL; }
  if (_shell) { nextspace_shell_v1_destroy(_shell); _shell = NULL; }
  if (_registry) { wl_registry_destroy(_registry); _registry = NULL; }
  wl_display_disconnect(_display); _display = NULL;
  [_windows removeAllObjects];
  [_movingWindow release]; _movingWindow = nil; [_moveEvents removeAllObjects];
  [_outputs release]; _outputs = [NSDictionary new];
  [_pendingOutputs removeAllObjects];
  [_inputs release]; _inputs = nil;
  if (notify) [[NSNotificationCenter defaultCenter]
    postNotificationName:WSShellConnectionDidCloseNotification object:self];
}
- (void)resetOutputs:(uint32_t)revision
{ [_pendingOutputs removeAllObjects]; _pendingOutputRevision = revision; }
- (void)recordOutput:(NSDictionary *)output
{ [_pendingOutputs setObject:output forKey:[output objectForKey:@"id"]]; }
- (void)recordOutputInfo:(NSDictionary *)info identifier:(NSNumber *)identifier
{ mergeEntry(_pendingOutputs, info, identifier); }
- (void)recordOutputMode:(NSDictionary *)mode identifier:(NSNumber *)identifier
{
  NSArray *modes = [[_pendingOutputs objectForKey:identifier] objectForKey:@"modes"];
  if (modes) [self recordOutputInfo:[NSDictionary dictionaryWithObject:[modes arrayByAddingObject:mode]
    forKey:@"modes"] identifier:identifier];
}
- (void)publishOutputs
{
  _outputsChanged |= _outputRevision != _pendingOutputRevision || ![_outputs isEqualToDictionary:_pendingOutputs];
  [_outputs release]; _outputs = [_pendingOutputs copy];
  _outputRevision = _pendingOutputRevision; _outputBatchSequence++;
}
- (BOOL)waitForCounter:(NSUInteger *)counter after:(NSUInteger)sequence
{
  [self flush];
  int64_t deadline = monotonicMilliseconds() + 5000;
  while ([self isConnected] && *counter == sequence && monotonicMilliseconds() < deadline)
    [_runLoop runMode:NSConnectionReplyMode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.02]];
  return *counter != sequence;
}
- (BOOL)refreshOutputs
{
  if (!_shell || _dispatching) return NO;
  NSUInteger sequence = _outputBatchSequence;
  nextspace_shell_v1_output_snapshot(_shell);
  return [self waitForCounter:&_outputBatchSequence after:sequence];
}
- (NSArray *)outputs { return orderedValues(_outputs); }
- (NSUInteger)outputRevision { return _outputRevision; }
- (BOOL)setOutput:(NSNumber *)identifier insets:(NSArray *)insets
{
  if (!_shell || nextspace_shell_v1_get_version(_shell) < 13 || [insets count] != 4) return NO;
  for (id value in insets)
    if (![value respondsToSelector:@selector(integerValue)] || [value integerValue] < 0 || [value integerValue] > 4096)
      return NO;
  nextspace_shell_v1_set_output_insets(_shell, [identifier unsignedIntValue],
    [[insets objectAtIndex:0] intValue], [[insets objectAtIndex:1] intValue],
    [[insets objectAtIndex:2] intValue], [[insets objectAtIndex:3] intValue]);
  [self flush];
  return YES;
}
- (NSDictionary *)outputResult { return _outputResult; }
- (void)recordOutputResult:(NSDictionary *)result
{
  /* A dispatch can contain both apply and timeout. Keep the request's first
     reply separately from the latest state used by notifications and leases. */
  if (_waitingForOutputResult && !_outputReply) _outputReply = [result copy];
  if ([self hasPendingOutputLayout]) {
    [_outputLeaseResult release]; _outputLeaseResult = [result copy];
  }
  [_outputResult release]; _outputResult = [result copy];
  _outputResultSequence++; _outputResultChanged = YES;
}
- (NSDictionary *)waitForOutputResultAfter:(NSUInteger)sequence
{
  _waitingForOutputResult = YES;
  [self waitForCounter:&_outputResultSequence after:sequence];
  _waitingForOutputResult = NO;
  NSDictionary *reply = [_outputReply autorelease];
  _outputReply = nil;
  return reply;
}
- (BOOL)configureOutputLayout:(NSArray *)layout revision:(NSUInteger)revision
{
  if (!_shell || _dispatching || _waitingForOutputResult || ![layout isKindOfClass:[NSArray class]] || [layout count] > 64 ||
      revision > UINT32_MAX) return NO;
  /* Reject non-numbers and out-of-wire-range values before marshaling an RPC
     caller's property list. Detailed layout/mode validation belongs to the server. */
  NSArray *unsignedKeys = [NSArray arrayWithObjects:@"id", @"enabled", @"primary", @"scale", @"transform", nil];
  NSArray *signedKeys = [NSArray arrayWithObjects:@"width", @"height", @"refresh", @"x", @"y", nil];
  for (id head in layout) {
    if (![head isKindOfClass:[NSDictionary class]]) return NO;
    for (NSString *key in unsignedKeys) {
      id value = [head objectForKey:key];
      if (![value isKindOfClass:[NSNumber class]] || !isfinite([value doubleValue]) ||
          [value doubleValue] < 0 || [value doubleValue] > UINT32_MAX ||
          [value doubleValue] != [value longLongValue]) return NO;
    }
    for (NSString *key in signedKeys) {
      id value = [head objectForKey:key];
      if (![value isKindOfClass:[NSNumber class]] || !isfinite([value doubleValue]) ||
          [value doubleValue] < INT32_MIN || [value doubleValue] > INT32_MAX ||
          [value doubleValue] != [value longLongValue]) return NO;
    }
  }
  if (_configuration) {
    if ([[_outputResult objectForKey:@"status"] intValue] == 1) return NO;
    nextspace_output_configuration_v1_destroy(_configuration);
  }
  _configuration = nextspace_shell_v1_configure_outputs(_shell, revision);
  nextspace_output_configuration_v1_add_listener(_configuration, &outputListener, self);
  for (NSDictionary *head in layout)
    nextspace_output_configuration_v1_set_head(_configuration, [[head objectForKey:@"id"] unsignedIntValue],
      [[head objectForKey:@"enabled"] unsignedIntValue], [[head objectForKey:@"primary"] unsignedIntValue],
      [[head objectForKey:@"width"] intValue], [[head objectForKey:@"height"] intValue],
      [[head objectForKey:@"refresh"] intValue], [[head objectForKey:@"scale"] unsignedIntValue],
      [[head objectForKey:@"transform"] unsignedIntValue], [[head objectForKey:@"x"] intValue], [[head objectForKey:@"y"] intValue]);
  return YES;
}
- (NSDictionary *)testOutputLayout:(NSArray *)layout revision:(NSUInteger)revision
{
  if (![self configureOutputLayout:layout revision:revision]) return nil;
  NSUInteger sequence = _outputResultSequence;
  nextspace_output_configuration_v1_test(_configuration);
  return [self waitForOutputResultAfter:sequence];
}
- (NSDictionary *)applyOutputLayout:(NSArray *)layout revision:(NSUInteger)revision timeout:(NSUInteger)milliseconds
{
  if (milliseconds < 1000 || milliseconds > 30000 || ![self configureOutputLayout:layout revision:revision]) return nil;
  NSUInteger sequence = _outputResultSequence;
  nextspace_output_configuration_v1_apply(_configuration, milliseconds);
  return [self waitForOutputResultAfter:sequence];
}
- (void)discardOutputLayout
{
  if (_configuration) {
    nextspace_output_configuration_v1_destroy(_configuration); _configuration = NULL;
    [self flush];
  }
}
- (NSDictionary *)confirmOutputLayout
{
  if (!_configuration || _dispatching || _waitingForOutputResult || [[_outputResult objectForKey:@"status"] intValue] != 1) return nil;
  NSUInteger sequence = _outputResultSequence;
  nextspace_output_configuration_v1_confirm(_configuration);
  return [self waitForOutputResultAfter:sequence];
}
- (NSDictionary *)cancelOutputLayout
{
  if (!_configuration || _dispatching || _waitingForOutputResult || [[_outputResult objectForKey:@"status"] intValue] != 1) return nil;
  NSUInteger sequence = _outputResultSequence;
  nextspace_output_configuration_v1_cancel(_configuration);
  return [self waitForOutputResultAfter:sequence];
}
- (void)recordInputSettings:(NSDictionary *)settings
{
  _inputsChanged |= ![_inputs isEqualToDictionary:settings];
  [_inputs release]; _inputs = [settings copy]; _inputBatchSequence++;
}
- (void)recordInputResult:(NSDictionary *)result
{
  if ([[result objectForKey:@"serial"] unsignedIntValue] != _inputSerial) return;
  [_inputResult release]; _inputResult = [result copy]; _inputResultSequence++;
}
- (BOOL)refreshInputSettings
{
  if (!_shell || _dispatching || nextspace_shell_v1_get_version(_shell) < 8) return NO;
  NSUInteger sequence = _inputBatchSequence;
  nextspace_shell_v1_input_snapshot(_shell);
  return [self waitForCounter:&_inputBatchSequence after:sequence];
}
- (void)recordBackground:(NSDictionary *)color
{ [_background release]; _background = [color copy]; _backgroundSequence++; }
- (void)recordDesktop:(NSUInteger)index count:(NSUInteger)count
{
  _desktopsChanged |= index != _desktop || count != _desktopCount;
  _desktop = index; _desktopCount = count; _desktopSequence++;
}
- (NSUInteger)desktopIndex { return _desktop; }
- (NSUInteger)desktopCount { return _desktopCount ?: 1; }
- (BOOL)configureDesktops:(NSUInteger)count
{
  if (!_shell || _dispatching || nextspace_shell_v1_get_version(_shell) < 10 || !count || count > 32) return NO;
  NSUInteger sequence = _desktopSequence;
  nextspace_shell_v1_configure_desktops(_shell, count);
  return [self waitForCounter:&_desktopSequence after:sequence] && _desktopCount == count;
}
- (BOOL)switchDesktop:(NSUInteger)index
{
  if (!_shell || _dispatching || nextspace_shell_v1_get_version(_shell) < 10 || index >= _desktopCount) return NO;
  NSUInteger sequence = _desktopSequence;
  nextspace_shell_v1_switch_desktop(_shell, index);
  return [self waitForCounter:&_desktopSequence after:sequence] && _desktop == index;
}
- (void)setWindow:(NSNumber *)identifier desktop:(NSUInteger)index sticky:(BOOL)sticky
{
  if (!_shell || nextspace_shell_v1_get_version(_shell) < 10 || index >= _desktopCount) return;
  nextspace_shell_v1_move_to_desktop(_shell, [identifier unsignedIntValue], index, sticky);
  [self flush];
}
- (NSDictionary *)backgroundColor
{
  if (!_shell || _dispatching || nextspace_shell_v1_get_version(_shell) < 9) return nil;
  NSUInteger sequence = _backgroundSequence;
  nextspace_shell_v1_background_snapshot(_shell);
  return [self waitForCounter:&_backgroundSequence after:sequence] ? _background : nil;
}
- (NSDictionary *)setBackgroundColor:(NSDictionary *)color
{
  if (!_shell || _dispatching || nextspace_shell_v1_get_version(_shell) < 9 ||
      ![color isKindOfClass:[NSDictionary class]]) return nil;
  for (NSString *key in [NSArray arrayWithObjects:@"Red", @"Green", @"Blue", nil]) {
    id value = [color objectForKey:key];
    if (![value isKindOfClass:[NSNumber class]] || !isfinite([value doubleValue]) ||
        [value doubleValue] < 0 || [value doubleValue] > 1) return nil;
  }
  NSUInteger sequence = _backgroundSequence;
  nextspace_shell_v1_set_background(_shell, wl_fixed_from_double([[color objectForKey:@"Red"] doubleValue]),
    wl_fixed_from_double([[color objectForKey:@"Green"] doubleValue]), wl_fixed_from_double([[color objectForKey:@"Blue"] doubleValue]));
  return [self waitForCounter:&_backgroundSequence after:sequence] ? _background : nil;
}
- (NSDictionary *)inputSettings { return _inputs; }
- (void)recordGammaResult:(NSDictionary *)result
{
  if ([[result objectForKey:@"serial"] unsignedIntValue] != _gammaSerial) return;
  [_gammaResult release]; _gammaResult = [result copy]; _gammaResultSequence++;
}
- (NSDictionary *)setOutput:(NSNumber *)identifier gamma:(NSDictionary *)settings
{
  if (!_shell || _dispatching || nextspace_shell_v1_get_version(_shell) < 18 ||
      ![identifier isKindOfClass:[NSNumber class]] || !isfinite([identifier doubleValue]) ||
      [identifier doubleValue] < 1 || [identifier doubleValue] > UINT32_MAX ||
      [identifier doubleValue] != [identifier unsignedLongLongValue] ||
      ![settings isKindOfClass:[NSDictionary class]]) return nil;
  NSArray *keys = [NSArray arrayWithObjects:@"red", @"green", @"blue", @"brightness", nil];
  for (NSString *key in keys) {
    id value = [settings objectForKey:key];
    BOOL brightness = [key isEqual:@"brightness"];
    if (![value isKindOfClass:[NSNumber class]] || !isfinite([value doubleValue]) ||
        [value doubleValue] < (brightness ? 0 : 0.1) || [value doubleValue] > (brightness ? 2 : 10)) return nil;
  }
  NSUInteger sequence = _gammaResultSequence;
  if (++_gammaSerial == 0) ++_gammaSerial;
  nextspace_shell_v1_set_output_gamma(_shell, _gammaSerial, [identifier unsignedIntValue],
    wl_fixed_from_double([[settings objectForKey:@"red"] doubleValue]),
    wl_fixed_from_double([[settings objectForKey:@"green"] doubleValue]),
    wl_fixed_from_double([[settings objectForKey:@"blue"] doubleValue]),
    wl_fixed_from_double([[settings objectForKey:@"brightness"] doubleValue]));
  if (![self waitForCounter:&_gammaResultSequence after:sequence]) return nil;
  NSMutableDictionary *result = [[_gammaResult mutableCopy] autorelease];
  NSDictionary *gamma = [[_outputs objectForKey:identifier] objectForKey:@"gamma"];
  if (gamma) [result setObject:gamma forKey:@"gamma"];
  return result;
}
- (NSDictionary *)waitForInputResult:(NSUInteger)sequence
{
  return [self waitForCounter:&_inputResultSequence after:sequence] ? _inputResult : nil;
}
- (NSDictionary *)setKeyboardSettings:(NSDictionary *)settings
{
  if (!_shell || _dispatching || nextspace_shell_v1_get_version(_shell) < 8 ||
      ![settings isKindOfClass:[NSDictionary class]]) return nil;
  for (NSString *key in [NSArray arrayWithObjects:@"model", @"layout", @"variant", @"options", nil]) {
    id value = [settings objectForKey:key];
    if (![value isKindOfClass:[NSString class]] || [value lengthOfBytesUsingEncoding:NSUTF8StringEncoding] > 1024 ||
        [value rangeOfString:[NSString stringWithFormat:@"%C", (unichar)0]].location != NSNotFound) return nil;
  }
  for (NSString *key in [NSArray arrayWithObjects:@"delay", @"rate", @"numlock", nil]) {
    id value = [settings objectForKey:key];
    if (![value isKindOfClass:[NSNumber class]] || !isfinite([value doubleValue]) ||
        [value doubleValue] < 0 || [value doubleValue] > UINT32_MAX ||
        [value doubleValue] != [value longLongValue]) return nil;
  }
  NSUInteger sequence = _inputResultSequence;
  if (++_inputSerial == 0) ++_inputSerial;
  nextspace_shell_v1_set_keyboard(_shell, _inputSerial, [[settings objectForKey:@"model"] UTF8String],
    [[settings objectForKey:@"layout"] UTF8String], [[settings objectForKey:@"variant"] UTF8String],
    [[settings objectForKey:@"options"] UTF8String], [[settings objectForKey:@"delay"] unsignedIntValue],
    [[settings objectForKey:@"rate"] unsignedIntValue], [[settings objectForKey:@"numlock"] unsignedIntValue]);
  return [self waitForInputResult:sequence];
}
- (NSDictionary *)setPointerSettings:(NSDictionary *)settings
{
  if (!_shell || _dispatching || nextspace_shell_v1_get_version(_shell) < 8 ||
      ![settings isKindOfClass:[NSDictionary class]]) return nil;
  id speed = [settings objectForKey:@"speed"], profile = [settings objectForKey:@"profile"];
  if (![speed isKindOfClass:[NSNumber class]] || !isfinite([speed doubleValue]) ||
      [speed doubleValue] < -1 || [speed doubleValue] > 1 || ![profile isKindOfClass:[NSNumber class]] ||
      [profile doubleValue] < 0 || [profile doubleValue] > 1 || [profile doubleValue] != [profile intValue]) return nil;
  NSUInteger sequence = _inputResultSequence;
  if (++_inputSerial == 0) ++_inputSerial;
  nextspace_shell_v1_set_pointer(_shell, _inputSerial, wl_fixed_from_double([speed doubleValue]), [profile unsignedIntValue]);
  return [self waitForInputResult:sequence];
}
- (NSDictionary *)setShortcuts:(NSArray *)accelerators
{
  if (!_shell || _dispatching || nextspace_shell_v1_get_version(_shell) < 12 ||
      ![accelerators isKindOfClass:[NSArray class]] || [accelerators count] != 18) return nil;
  uint32_t values[18][2] = {{0}};
  NSUInteger index = 0;
  for (id accelerator in accelerators) {
    if (![accelerator isKindOfClass:[NSString class]] || [accelerator length] > 128) return nil;
    if ([accelerator caseInsensitiveCompare:@"None"] != NSOrderedSame && [accelerator length]) {
      NSArray *parts = [accelerator componentsSeparatedByString:@"+"];
      NSUInteger part;
      for (part = 0; part + 1 < [parts count]; part++) {
        NSString *modifier = [[parts objectAtIndex:part] lowercaseString];
        if ([modifier isEqual:@"shift"]) values[index][1] |= 1;
        else if ([modifier isEqual:@"control"] || [modifier isEqual:@"ctrl"]) values[index][1] |= 4;
        else if ([modifier isEqual:@"command"] || [modifier isEqual:@"alt"] || [modifier isEqual:@"mod1"]) values[index][1] |= 8;
        else if ([modifier isEqual:@"alternate"] || [modifier isEqual:@"super"] || [modifier isEqual:@"mod4"]) values[index][1] |= 64;
        else return nil;
      }
      values[index][0] = xkb_keysym_from_name([[parts lastObject] UTF8String], XKB_KEYSYM_CASE_INSENSITIVE);
      if (!values[index][0]) return nil;
    }
    index++;
  }
  struct wl_array wire = {.size = sizeof(values), .alloc = sizeof(values), .data = values};
  NSUInteger sequence = _inputResultSequence;
  if (++_inputSerial == 0) ++_inputSerial;
  nextspace_shell_v1_set_shortcuts(_shell, _inputSerial, &wire);
  return [self waitForInputResult:sequence];
}
- (BOOL)setMaximizedDragMode:(NSUInteger)mode
{
  if (!_shell || nextspace_shell_v1_get_version(_shell) < 14 || mode > 3) return NO;
  nextspace_shell_v1_set_maximized_drag_mode(_shell, (uint32_t)mode);
  [self flush]; return YES;
}
- (BOOL)setDoubleClickTime:(NSUInteger)milliseconds
{
  if (!_shell || nextspace_shell_v1_get_version(_shell) < 15 || milliseconds < 1 || milliseconds > 60000) return NO;
  nextspace_shell_v1_set_double_click_time(_shell, (uint32_t)milliseconds);
  [self flush]; return YES;
}
- (BOOL)setTitleAppearance:(NSDictionary *)appearance
{
  if (!_shell || nextspace_shell_v1_get_version(_shell) < 16 ||
      ![appearance isKindOfClass:[NSDictionary class]]) return NO;
  id font = [appearance objectForKey:@"font"], justify = [appearance objectForKey:@"justification"];
  id antialiased = [appearance objectForKey:@"antialiased"];
  if (![font isKindOfClass:[NSString class]] || ![justify isKindOfClass:[NSString class]] ||
      ![antialiased respondsToSelector:@selector(boolValue)]) return NO;
  const char *pattern = [font UTF8String];
  if (!pattern || !*pattern || strlen(pattern) > 4096) return NO;
  NSArray *names = [NSArray arrayWithObjects:@"center", @"left", @"right", nil];
  NSUInteger index = [names indexOfObject:[justify lowercaseString]];
  if (index == NSNotFound) return NO;
  nextspace_shell_v1_set_title_appearance(_shell, pattern, [antialiased boolValue], (uint32_t)index);
  [self flush]; return YES;
}
- (void)activateWindow:(NSNumber *)identifier
{
  if (_shell) { nextspace_shell_v1_activate(_shell, [identifier unsignedIntValue]); [self flush]; }
}
- (void)closeWindow:(NSNumber *)identifier
{
  if (_shell) { nextspace_shell_v1_close(_shell, [identifier unsignedIntValue]); [self flush]; }
}
- (void)moveWindow:(NSNumber *)identifier toPoint:(NSPoint)point
{
  if (!isfinite(point.x) || !isfinite(point.y) || point.x < INT_MIN || point.x > INT_MAX ||
      point.y < INT_MIN || point.y > INT_MAX) return;
  if (_shell) { nextspace_shell_v1_move(_shell, [identifier unsignedIntValue], point.x, point.y); [self flush]; }
}
- (void)setWindow:(NSNumber *)identifier minimized:(BOOL)minimized
{
  if (_shell) { nextspace_shell_v1_set_minimized(_shell, [identifier unsignedIntValue], minimized); [self flush]; }
}
- (void)setWindow:(NSNumber *)identifier shaded:(BOOL)shaded
{
  if (_shell) { nextspace_shell_v1_set_shaded(_shell, [identifier unsignedIntValue], shaded); [self flush]; }
}
- (void)setWindow:(NSNumber *)identifier presented:(BOOL)presented
{
  if (_shell) { nextspace_shell_v1_set_presented(_shell, [identifier unsignedIntValue], presented); [self flush]; }
}
- (void)setWindow:(NSNumber *)identifier level:(NSInteger)level
{
  if (_shell) { nextspace_shell_v1_set_level(_shell, [identifier unsignedIntValue],
    (int32_t)MAX(-1000, MIN(1000, level))); [self flush]; }
}
- (void)orderWindow:(NSNumber *)identifier above:(BOOL)above
{
  if (_shell) { nextspace_shell_v1_order(_shell, [identifier unsignedIntValue], above); [self flush]; }
}
@end
