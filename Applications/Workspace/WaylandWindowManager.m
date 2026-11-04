/* Native Workspace policy; compositor state arrives through a private capability.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import <AppKit/AppKit.h>
#import <GNUstepGUI/GSDisplayServer.h>
#import "WindowManager.h"
#import "WSShellConnection.h"
#import "Session.h"
#import "Recycler.h"
#import "RecyclerIcon.h"
#import "WSIconTileView.h"
#import "WSDockSettings.h"
#import <SystemKit/OSESessionSettings.h>
#import <SystemKit/OSEScreen.h>
#import <SystemKit/OSEKeyboard.h>
#import <SystemKit/OSEMouse.h>
#import <SystemKit/OSEDefaults.h>
#include <glib.h>
#import "Processes/ProcessManager+WindowManager.h"
#include <unistd.h>
#include <stdlib.h>
#include <math.h>

static NSArray *windowManagerRunLoopModes(void)
{
  return @[NSDefaultRunLoopMode, NSConnectionReplyMode,
    NSModalPanelRunLoopMode, NSEventTrackingRunLoopMode];
}

@interface GSDisplayServer (WorkspaceDisplay)
- (NSInteger)keyboardLayoutIndex;
- (NSRect)logicalDesktopBounds;
@end

@interface WSNativeIconWindow : NSWindow
@end
@implementation WSNativeIconWindow
- (BOOL)canBecomeKeyWindow { return NO; }
- (BOOL)canBecomeMainWindow { return NO; }
- (BOOL)worksWhenModal { return YES; }
@end

@interface WSWaylandWindowManager : NSObject <WSWindowManager, OSESessionSettings>
{
  WSShellConnection *_connection;
  NSNotificationCenter *_center;
  ProcessManager *_processManager;
  NSWindow *_recyclerIcon;
  WSDockSettings *_dockSettings;
  NSArray *_dockEntries;
  NSMutableDictionary *_dockIcons;
  NSMutableDictionary *_yardIcons, *_yardApplications;
  NSInteger _dockHeight;
  NSSet *_dockWindowIDs;
  NSNumber *_movingIcon;
  BOOL _dockHovering, _dockAutoRaised;
  NSMutableDictionary *_launchIcons;
  NSMutableDictionary *_launchedCommands;
  NSMutableDictionary *_foreignApplications;
  NSMutableDictionary *_pendingShades;
  BOOL _dockVisible, _dockCollapsed, _yardVisible, _focusEventsEnabled;
  BOOL _updating, _startupFinished, _stopping;
}
- (void)windowsChanged:(NSNotification *)notification;
- (void)mouseOptionsChanged:(NSNotification *)notification;
- (void)appearanceChanged:(NSNotification *)notification;
- (void)layoutIcons;
- (NSRect)primaryScreenFrame;
- (NSInteger)dockScreenHeight;
- (void)activateDockApplication:(NSString *)name;
- (NSDictionary *)desktopSettings:(NSDictionary *)changes;
@end

static NSDictionary *registeredApplication(ProcessManager *manager, NSNumber *pid)
{
  for (NSDictionary *info in [manager applications])
    if ([[info objectForKey:@"NSApplicationProcessIdentifier"] containsObject:pid]) return info;
  return nil;
}

static NSDictionary *desktopShortcuts(void)
{
  NSMutableDictionary *settings = [[WSDefaultDesktopShortcuts() mutableCopy] autorelease];
  NSDictionary *legacy = [NSDictionary dictionaryWithContentsOfFile:
    [[WSDockSettings legacyDirectory] stringByAppendingPathComponent:@"WM.plist"]];
  NSDictionary *saved = [[NSUserDefaults standardUserDefaults] dictionaryForKey:@"WaylandShortcuts"];
  for (NSString *key in WSDesktopShortcutNames()) {
    id value = [saved objectForKey:key] ?: [legacy objectForKey:key];
    if (!value && [key hasPrefix:@"Desktop"])
      value = [legacy objectForKey:[key stringByReplacingOccurrencesOfString:@"Desktop" withString:@"Workspace"]];
    if ([value isKindOfClass:[NSString class]]) [settings setObject:value forKey:key];
  }
  return settings;
}

static NSArray *shortcutValues(NSDictionary *settings)
{
  NSMutableArray *values = [NSMutableArray array];
  for (NSString *name in WSDesktopShortcutNames()) [values addObject:[settings objectForKey:name]];
  return values;
}

/* Views retain their name; the application owns the policy object. */
@interface WSNativeDockIconView : WSIconTileView
{
  WSWaylandWindowManager *_manager;
  NSString *_name;
}
- (id)initWithName:(NSString *)name manager:(WSWaylandWindowManager *)manager;
@end
@implementation WSNativeDockIconView
- (id)initWithName:(NSString *)name manager:(WSWaylandWindowManager *)manager
{
  if ((self = [super initWithFrame:NSMakeRect(0, 0, 64, 64)])) {
    _name = [name copy]; _manager = manager;
  }
  return self;
}
- (void)dealloc { [_name release]; [super dealloc]; }
- (BOOL)acceptsFirstMouse:(NSEvent *)event { return YES; }
- (void)mouseDown:(NSEvent *)event
{
  if ([event clickCount] == 2) [_manager activateDockApplication:_name];
  else [GSServerForWindow([self window]) dragIconWindow:[[self window] windowNumber] event:event];
}
@end

static NSArray *commandArguments(NSString *command)
{
  if (![command isKindOfClass:[NSString class]] || ![command length]) return [NSArray array];
  gchar **tokens = NULL;
  gint count = 0;
  GError *error = NULL;
  if (!g_shell_parse_argv([command UTF8String], &count, &tokens, &error)) {
    if (error) g_error_free(error);
    return [NSArray array];
  }
  NSMutableArray *arguments = [NSMutableArray array];
  for (int index = 0; index < count; index++) {
    NSString *value = [NSString stringWithUTF8String:tokens[index]];
    if (!value) { [arguments removeAllObjects]; break; }
    [arguments addObject:value];
  }
  g_strfreev(tokens);
  return arguments;
}

static NSInteger dockSlot(NSDictionary *entry)
{
  id position = [entry objectForKey:@"Position"];
  if (![position isKindOfClass:[NSString class]]) return -1;
  NSScanner *scanner = [NSScanner scannerWithString:position];
  int x, y;
  if (![scanner scanInt:&x] || ![scanner scanString:@"," intoString:NULL] ||
      ![scanner scanInt:&y] || ![scanner isAtEnd] || x != 0 || y < 0 || y > 1024) return -1;
  return y;
}

static NSString *windowApplicationName(NSDictionary *window)
{
  NSString *identifier = [window objectForKey:@"app_id"];
  if ([identifier hasPrefix:@"org.nextspace."]) return [identifier substringFromIndex:14];
  return [identifier length] ? identifier : [window objectForKey:@"title"];
}

static NSString *shellQuote(NSString *argument)
{
  return [NSString stringWithFormat:@"'%@'",
    [argument stringByReplacingOccurrencesOfString:@"'" withString:@"'\\''"]];
}

static NSString *commandForPID(pid_t pid)
{
  if (pid <= 1) return nil;
  NSData *data = [NSData dataWithContentsOfFile:[NSString stringWithFormat:@"/proc/%d/cmdline", pid]];
  if (![data length] || [data length] > 1024 * 1024) return nil;
  NSMutableArray *arguments = [NSMutableArray array];
  const char *bytes = [data bytes];
  NSUInteger start = 0;
  for (NSUInteger index = 0; index < [data length]; index++) {
    if (bytes[index]) continue;
    NSString *argument = [[[NSString alloc] initWithBytes:bytes + start length:index - start
      encoding:NSUTF8StringEncoding] autorelease];
    if (!argument) return nil;
    [arguments addObject:shellQuote(argument)]; start = index + 1;
  }
  return [arguments count] ? [arguments componentsJoinedByString:@" "] : nil;
}

@implementation WSWaylandWindowManager
- (NSRect)primaryScreenFrame
{
  CGFloat bottom = MAX(0, NSMaxY([GSCurrentServer() logicalDesktopBounds]));
  for (NSDictionary *head in [_connection outputs])
    if ([[head objectForKey:@"enabled"] boolValue] && [[head objectForKey:@"primary"] boolValue])
      return NSMakeRect([[head objectForKey:@"x"] doubleValue],
        bottom - [[head objectForKey:@"y"] doubleValue] - [[head objectForKey:@"logical_height"] doubleValue],
        [[head objectForKey:@"logical_width"] doubleValue], [[head objectForKey:@"logical_height"] doubleValue]);
  NSArray *screens = [NSScreen screens];
  return [screens count] ? [[screens objectAtIndex:0] frame] : NSZeroRect;
}
- (NSInteger)dockScreenHeight { return (NSInteger)[self primaryScreenFrame].size.height; }
- (id)init
{
  if (!(self = [super init])) return nil;
  int descriptor = ws_shell_descriptor;
  ws_shell_descriptor = -1;
  _connection = [[WSShellConnection alloc] initWithFileDescriptor:descriptor];
  if (!_connection) {
    [self release];
    [NSException raise:NSInternalInconsistencyException format:@"Cannot connect to the session compositor shell interface"];
    return nil;
  }
  OSERegisterSessionSettings(self);
  _center = [[[NSWorkspace sharedWorkspace] notificationCenter] retain];
  _foreignApplications = [NSMutableDictionary new];
  _pendingShades = [NSMutableDictionary new];
  _launchIcons = [NSMutableDictionary new];
  _launchedCommands = [NSMutableDictionary new];
  _dockVisible = _yardVisible = _focusEventsEnabled = YES;
  _dockSettings = [[WSDockSettings alloc] initWithDefaults:[NSUserDefaults standardUserDefaults]
    domain:@"Workspace" legacyDirectory:[WSDockSettings legacyDirectory]];
  [_connection setMaximizedDragMode:[_dockSettings maximizedDragMode]];
  _dockIcons = [NSMutableDictionary new];
  _yardIcons = [NSMutableDictionary new]; _yardApplications = [NSMutableDictionary new];
  _dockCollapsed = [[[_dockSettings dock] objectForKey:@"Collapsed"] boolValue];
  NSNotificationCenter *local = [NSNotificationCenter defaultCenter];
  [local addObserver:self selector:@selector(commandDidExit:)
    name:NSTaskDidTerminateNotification object:nil];
  [local addObserver:self selector:@selector(windowsChanged:)
    name:WSShellWindowsDidChangeNotification object:_connection];
  [local addObserver:self selector:@selector(outputsChanged:)
    name:WSShellOutputsDidChangeNotification object:_connection];
  [local addObserver:self selector:@selector(outputResultChanged:)
    name:WSShellOutputResultNotification object:_connection];
  [local addObserver:self selector:@selector(desktopChanged:)
    name:WSShellDesktopsDidChangeNotification object:_connection];
  [local addObserver:self selector:@selector(iconMoved:)
    name:WSShellInteractiveMoveNotification object:_connection];
  [local addObserver:self selector:@selector(connectionClosed:)
    name:WSShellConnectionDidCloseNotification object:_connection];
  [local addObserver:self selector:@selector(keyboardChanged:)
    name:@"GSKeyboardLayoutDidChangeNotification" object:nil];
  [[NSDistributedNotificationCenter defaultCenter] addObserver:self selector:@selector(mouseOptionsChanged:)
    name:@"GSMouseOptionsDidChangeNotification" object:nil];
  [[NSDistributedNotificationCenter defaultCenter] addObserver:self selector:@selector(appearanceChanged:)
    name:@"WMDidChangeAppearanceSettingsNotification" object:nil];
  [self mouseOptionsChanged:nil];
  [self appearanceChanged:nil];
  return self;
}
- (void)mouseOptionsChanged:(NSNotification *)notification
{
  [[NSUserDefaults standardUserDefaults] synchronize];
  [_connection setDoubleClickTime:(NSUInteger)lround([OSEMouse doubleClickInterval] * 1000)];
}
- (void)appearanceChanged:(NSNotification *)notification
{ [_connection setTitleAppearance:[_dockSettings titleAppearance]]; }
- (void)dealloc
{
  [NSObject cancelPreviousPerformRequestsWithTarget:self];
  [[NSNotificationCenter defaultCenter] removeObserver:self];
  [[NSDistributedNotificationCenter defaultCenter] removeObserver:self];
  [_connection release]; [_center release]; [_recyclerIcon release]; [_dockSettings release];
  [_dockEntries release]; [_dockIcons release]; [_dockWindowIDs release];
  [_yardIcons release]; [_yardApplications release];
  [_foreignApplications release]; [_pendingShades release]; [_launchIcons release];
  [_launchedCommands release];
  [_movingIcon release];
  [super dealloc];
}
- (void)prepareForTermination
{
  _stopping = YES;
  [NSObject cancelPreviousPerformRequestsWithTarget:self];
  [[NSNotificationCenter defaultCenter] removeObserver:self];
  [[NSDistributedNotificationCenter defaultCenter] removeObserver:self];
  _processManager = nil;
}
- (void)outputsChanged:(NSNotification *)notification
{
  if (_stopping) return;
  /* The private inventory and AppKit's wl_output notifications may arrive in
     either order. Always lay out against the complete authoritative batch. */
  [NSObject cancelPreviousPerformRequestsWithTarget:self selector:@selector(layoutIcons) object:nil];
  [self performSelector:@selector(layoutIcons) withObject:nil afterDelay:0
    inModes:windowManagerRunLoopModes()];
  [[NSDistributedNotificationCenter defaultCenter] postNotificationName:OSEScreenDidChangeNotification
    object:WSSessionServiceName(@"OSEScreen") userInfo:nil deliverImmediately:YES];
}
- (void)desktopChanged:(NSNotification *)notification
{
  [_center postNotificationName:[self desktopChangeNotification] object:self userInfo:
    [NSDictionary dictionaryWithObject:[NSNumber numberWithUnsignedInteger:[_connection desktopIndex]] forKey:@"workspace"]];
}
- (void)outputResultChanged:(NSNotification *)notification
{
  [self outputsChanged:notification];
}
- (bycopy NSData *)nextspaceSettingsRequest:(bycopy NSData *)bytes
{
  NSDictionary *request = OSESessionSettingsDecode(bytes);
  if ([[request objectForKey:@"schema"] integerValue] != 1) return nil;
  NSString *action = [request objectForKey:@"action"];
  if ([action isEqual:@"desktop-state"]) return OSESessionSettingsEncode(
    [NSDictionary dictionaryWithObjectsAndKeys:[NSNumber numberWithUnsignedInteger:[_connection desktopIndex]], @"current",
      [NSNumber numberWithUnsignedInteger:[_connection desktopCount]], @"count", nil]);
  if ([action isEqual:@"desktop-settings"]) return OSESessionSettingsEncode([self desktopSettings:request]);
  return [_connection nextspaceSettingsRequest:bytes];
}
- (void)connectionClosed:(NSNotification *)notification
{
  /* The supervisor can restart Workspace on a new capability. */
  ws_quit_code = (WorkspaceExitCode)1;
  [NSApp stop:self];
  [NSApp postEvent:[NSEvent otherEventWithType:NSApplicationDefined location:NSZeroPoint
    modifierFlags:0 timestamp:0 windowNumber:0 context:nil subtype:0 data1:0 data2:0] atStart:YES];
}
- (NSString *)serverVersion { return @"NEXTSPACE Wayland compositor (shell v11)"; }
- (NSDictionary *)metadataForWindow:(NSWindow *)window
{
  for (NSDictionary *entry in [_connection windows]) {
    if ([[entry objectForKey:@"pid"] intValue] == getpid() &&
        !([[entry objectForKey:@"flags"] unsignedIntValue] & 2) &&
        [[entry objectForKey:@"client_id"] integerValue] == [window windowNumber]) return entry;
  }
  return nil;
}
- (NSString *)stateForWindow:(NSWindow *)window
{
  NSDictionary *entry = [self metadataForWindow:window];
  if (!entry) return nil;
  unsigned flags = [[entry objectForKey:@"flags"] unsignedIntValue];
  return flags & 8 ? @"Miniaturized" : flags & 16 ? @"Shaded" : flags & 32 ? @"Hidden" : @"Normal";
}
- (void)setWindow:(NSWindow *)window shaded:(BOOL)shaded
{
  NSDictionary *entry = [self metadataForWindow:window];
  if (entry) [_connection setWindow:[entry objectForKey:@"id"] shaded:shaded];
  else if (window) [_pendingShades setObject:@(shaded) forKey:@([window windowNumber])];
}
- (NSArray *)undockedApplications
{
  NSMutableArray *applications = [NSMutableArray array];
  NSMutableSet *pids = [NSMutableSet set];
  for (NSDictionary *window in [_connection windows]) {
    NSNumber *pid = [window objectForKey:@"pid"];
    if ([pid intValue] <= 1 || [pid intValue] == getpid() || [pids containsObject:pid] ||
        ([[window objectForKey:@"flags"] unsignedIntValue] & 2)) continue;
    [pids addObject:pid];
    BOOL docked = NO;
    for (NSDictionary *entry in _dockEntries)
      if ([self window:window belongsToDockApplication:[entry objectForKey:@"Name"]]) { docked = YES; break; }
    if (docked) continue;
    NSString *command = commandForPID([pid intValue]);
    if (command) [applications addObject:@{@"Name": [windowApplicationName(window) stringByAppendingString:@".GNUstep"],
                                         @"Command": command}];
  }
  return applications;
}
- (BOOL)isApplicationRunning:(NSString *)name
{
  if ([name hasSuffix:@".GNUstep"]) name = [name substringToIndex:[name length] - 8];
  for (NSDictionary *window in [_connection windows])
    if ([windowApplicationName(window) isEqualToString:name]) return YES;
  return NO;
}
- (pid_t)executeCommand:(NSString *)command
{
  if (![command length]) return 0;
  @try {
    NSArray *arguments = commandArguments(command);
    if (![arguments count]) return 0;
    NSTask *task = [NSTask launchedTaskWithLaunchPath:[arguments objectAtIndex:0]
      arguments:[arguments subarrayWithRange:NSMakeRange(1, [arguments count] - 1)]];
    [_launchedCommands setObject:[task launchPath] forKey:@([task processIdentifier])];
    return [task processIdentifier];
  } @catch (NSException *exception) { NSLog(@"Cannot launch %@: %@", command, [exception reason]); return 0; }
}
- (void)commandDidExit:(NSNotification *)notification
{
  NSTask *task = [notification object];
  NSNumber *pid = @([task processIdentifier]);
  NSString *path = [_launchedCommands objectForKey:pid];
  if (!path) return;
  /* Keep metadata only; observing a launch must not change child lifetime. */
  int status = [task terminationStatus];
  if (status || getenv("NEXTSPACE_WAYLAND_CAPTURE_DIR"))
    NSLog(@"Dock process %@ (%@) exited: status=%d reason=%ld", pid,
      [path lastPathComponent], status, (long)[task terminationReason]);
  [_launchedCommands removeObjectForKey:pid];
}
- (void)unhideWorkspace
{
  [NSApp unhide:self];
  for (NSDictionary *entry in [_connection windows])
    if ([[entry objectForKey:@"pid"] intValue] == getpid())
      [_connection setWindow:[entry objectForKey:@"id"] presented:YES];
  [self layoutIcons];
}
- (void)hideOtherApplications
{
  NSMutableSet *native = [NSMutableSet set];
  for (NSDictionary *application in [[NSWorkspace sharedWorkspace] launchedApplications]) {
    if ([[application objectForKey:@"NSApplicationProcessIdentifier"] intValue] == getpid()) continue;
    @try {
      NSConnection *connection = [NSConnection connectionWithRegisteredName:
        WSSessionServiceName([application objectForKey:@"NSApplicationName"]) host:@""];
      [connection setRequestTimeout:1]; [connection setReplyTimeout:1];
      id proxy = [connection rootProxy];
      if (proxy) {
        [proxy hide:NSApp];
        [native addObject:[NSNumber numberWithInt:[[application objectForKey:@"NSApplicationProcessIdentifier"] intValue]]];
      }
    } @catch (NSException *exception) { NSLog(@"Cannot hide application: %@", [exception reason]); }
  }
  for (NSDictionary *window in [_connection windows]) {
    if ([[window objectForKey:@"pid"] intValue] != getpid() &&
        ![native containsObject:[window objectForKey:@"pid"]] &&
        !([[window objectForKey:@"style"] unsignedIntValue] & (NSIconWindowMask | NSMiniWindowMask)))
      [_connection setWindow:[window objectForKey:@"id"] presented:NO];
  }
}
- (void)beginApplicationLaunch:(NSDictionary *)info fromPoint:(NSPoint)point
{
  NSString *path = [info objectForKey:@"LaunchPath"];
  if (!path || [_launchIcons objectForKey:path]) return;
  NSWindow *window = [[WSNativeIconWindow alloc] initWithContentRect:NSMakeRect(point.x, point.y, 64, 64)
    styleMask:NSIconWindowMask backing:NSBackingStoreBuffered defer:NO];
  WSIconTileView *icon = [[WSIconTileView alloc] initWithFrame:NSMakeRect(0, 0, 64, 64)];
  [icon setImage:[[[NSImage alloc] initWithContentsOfFile:[info objectForKey:@"IconPath"]] autorelease]];
  [window setContentView:icon]; [icon release];
  [window setLevel:NSDockWindowLevel]; [window setReleasedWhenClosed:NO];
  [_launchIcons setObject:window forKey:path]; [window release];
  [window orderFrontRegardless];
}
- (void)endApplicationLaunch:(NSString *)command
{
  NSWindow *window = [_launchIcons objectForKey:command];
  [window orderOut:self]; [_launchIcons removeObjectForKey:command];
}
- (void)observeApplicationEventsFor:(ProcessManager *)manager
{
  _processManager = manager;
  [self windowsChanged:nil];
}
- (BOOL)terminateApplication:(NSDictionary *)info
{
  NSSet *pids = [info objectForKey:@"NSApplicationProcessIdentifier"];
  for (NSDictionary *window in [_connection windows])
    if ([pids containsObject:[window objectForKey:@"pid"]]) [_connection closeWindow:[window objectForKey:@"id"]];
  NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:2];
  while ([deadline timeIntervalSinceNow] > 0) {
    BOOL running = NO;
    for (NSDictionary *window in [_connection windows])
      if ([pids containsObject:[window objectForKey:@"pid"]]) { running = YES; break; }
    if (!running) return YES;
    [[NSRunLoop currentRunLoop] runMode:NSDefaultRunLoopMode
      beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.02]];
  }
  return NO;
}
- (NSString *)keyboardLayoutBadgeForNotification:(NSNotification *)notification
{
  GSDisplayServer *server = GSCurrentServer();
  [_connection refreshInputSettings];
  NSArray *names = [[[_connection inputSettings] objectForKey:@"layout"] componentsSeparatedByString:@","];
  NSInteger index = [server keyboardLayoutIndex];
  return [names count] > 1 && index >= 0 && index < [names count] ? [names objectAtIndex:index] : @"";
}
- (void)keyboardChanged:(NSNotification *)notification
{ [_center postNotificationName:[self keyboardLayoutChangeNotification] object:self]; }
- (BOOL)isDockVisible { return _dockVisible; }
- (void)setDockVisible:(BOOL)visible { _dockVisible = visible; [self layoutIcons]; }
- (BOOL)isDockCollapsed { return _dockCollapsed; }
- (void)setDockCollapsed:(BOOL)collapsed
{
  if ([_dockSettings setDockValue:collapsed ? @"Yes" : @"No" forKey:@"Collapsed"]) {
    _dockCollapsed = collapsed; [self layoutIcons];
  }
}
- (BOOL)isIconYardVisible { return _yardVisible; }
- (void)setIconYardVisible:(BOOL)visible { _yardVisible = visible; [self layoutIcons]; }
- (NSInteger)desktopIndex { return [_connection desktopIndex]; }
- (NSDictionary *)desktopSettings:(NSDictionary *)changes
{
  NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
  NSArray *names = [changes objectForKey:@"names"];
  id requested = [changes objectForKey:@"shortcuts"];
  if (names) {
    if (![names isKindOfClass:[NSArray class]] || ![names count] || [names count] > 32) return nil;
    for (id name in names)
      if (![name isKindOfClass:[NSString class]] || ![name length] || [name length] > 128) return nil;
  }
  NSMutableDictionary *shortcuts = [[desktopShortcuts() mutableCopy] autorelease];
  if (requested) {
    if (![requested isKindOfClass:[NSDictionary class]]) return nil;
    for (id key in requested) {
      id value = [requested objectForKey:key];
      if (![WSDesktopShortcutNames() containsObject:key] || ![value isKindOfClass:[NSString class]] || [value length] > 128) return nil;
      [shortcuts setObject:value forKey:key];
    }
    if (![[[_connection setShortcuts:shortcutValues(shortcuts)] objectForKey:@"success"] boolValue]) return nil;
  }
  if (names && ![_connection configureDesktops:[names count]]) return nil;
  if (requested) [defaults setObject:shortcuts forKey:@"WaylandShortcuts"];
  if (names) [defaults setObject:names forKey:@"WaylandDesktops"];
  if (names || requested) [defaults synchronize];
  return [NSDictionary dictionaryWithObjectsAndKeys:[defaults arrayForKey:@"WaylandDesktops"] ?: [NSArray array], @"names",
    shortcuts, @"shortcuts", [NSNumber numberWithUnsignedInteger:[_connection desktopIndex]], @"current", nil];
}
- (BOOL)shouldRestoreWorkspaceWindows
{
  for (id entry in [_dockSettings applicationsForHeight:[self dockScreenHeight]])
    if ([entry isKindOfClass:[NSDictionary class]] && [[entry objectForKey:@"Name"] isEqualToString:@"Workspace.GNUstep"])
      return [[entry objectForKey:@"AutoLaunch"] boolValue];
  return YES;
}
- (NSWindow *)newRecyclerIconForRecycler:(Recycler *)recycler
{
  NSWindow *window = [[WSNativeIconWindow alloc] initWithContentRect:NSMakeRect(0, 0, 64, 64)
    styleMask:NSIconWindowMask backing:NSBackingStoreBuffered defer:NO];
  [window setTitle:@"Recycler"]; [window setReleasedWhenClosed:NO];
  [window setLevel:NSDockWindowLevel]; [window setExcludedFromWindowsMenu:YES];
  _recyclerIcon = [window retain];
  return window;
}
- (void)finishStartup
{
  NSUserDefaults *preferences = [NSUserDefaults standardUserDefaults];
  NSArray *names = [preferences arrayForKey:@"WaylandDesktops"];
  if (![names count]) {
    NSString *stateFile = [@"~/Library/Preferences/.NextSpace/WMState.plist" stringByExpandingTildeInPath];
    NSDictionary *state = [NSDictionary dictionaryWithContentsOfFile:stateFile];
    if (!state) state = [NSDictionary dictionaryWithContentsOfFile:[[NSBundle mainBundle] pathForResource:@"WMState" ofType:@"plist"]];
    NSMutableArray *imported = [NSMutableArray array];
    for (id entry in ([state objectForKey:@"Desktops"] ?: [state objectForKey:@"Workspaces"])) {
      id name = [entry isKindOfClass:[NSDictionary class]] ? [entry objectForKey:@"Name"] : entry;
      if ([name isKindOfClass:[NSString class]] && [name length] && [imported count] < 32) [imported addObject:name];
    }
    if (![imported count]) for (NSUInteger index = 1; index <= 4; index++)
      [imported addObject:[NSString stringWithFormat:@"Workspace %lu", (unsigned long)index]];
    [preferences setObject:imported forKey:@"WaylandDesktops"]; [preferences synchronize]; names = imported;
  }
  [_connection configureDesktops:MIN(32, [names count])];
  if (![[[_connection setShortcuts:shortcutValues(desktopShortcuts())] objectForKey:@"success"] boolValue])
    NSLog(@"Saved desktop shortcuts were rejected; keeping the compositor bindings.");
  /* Only the supervisor's first shell restores durable settings. Restarting
     Workspace must preserve the live compositor and unrelated clients. */
  if ([[[NSProcessInfo processInfo] arguments] containsObject:@"--nextspace-restore-settings"]) {
    OSEScreen *screen = [OSEScreen sharedScreen];
    if ([screen savedDisplayLayout] && ![screen applySavedDisplayLayout])
      NSLog(@"Saved Wayland display layout was rejected; keeping the usable startup layout.");
    OSEDefaults *defaults = [OSEDefaults globalUserDefaults];
    [OSEKeyboard configureWithDefaults:defaults];
    [OSEMouse configureWithDefaults:defaults];
    CGFloat red, green, blue;
    if ([screen savedBackgroundColorRed:&red green:&green blue:&blue])
      [screen setBackgroundColorRed:red green:green blue:blue];
  }
  _startupFinished = YES;
  for (id entry in [_dockSettings applicationsForHeight:[self dockScreenHeight]])
    if ([entry isKindOfClass:[NSDictionary class]] && [[entry objectForKey:@"AutoLaunch"] boolValue] &&
        ![[entry objectForKey:@"Name"] isEqualToString:@"Workspace.GNUstep"] &&
        ![[entry objectForKey:@"Name"] isEqualToString:@"Recycler.GNUstep"])
      [self executeCommand:[entry objectForKey:@"Command"]];
  [self layoutIcons];
}
- (void)setFocusEventsEnabled:(BOOL)enabled { _focusEventsEnabled = enabled; }
- (void)updateScreenParameters { [self layoutIcons]; }
- (void)updateUsableArea { [self layoutIcons]; }
- (NSNotificationCenter *)notificationCenter { return _center; }
- (NSString *)desktopChangeNotification { return @"WSWaylandDesktopDidChange"; }
- (NSString *)keyboardLayoutChangeNotification { return @"WSWaylandKeyboardLayoutDidChange"; }
- (NSInteger)dockLevel
{
  NSDictionary *dock = [_dockSettings dock];
  return [[dock objectForKey:@"Lowered"] boolValue] ?
    ([[dock objectForKey:@"AutoRaiseLower"] boolValue] ? -1000 : 0) : 5;
}
- (NSArray *)supportedDockLevels { return @[@0, @5, @(-1000)]; }
- (void)setDockLevel:(NSInteger)level
{
  if ([[self supportedDockLevels] containsObject:@(level)] && [_dockSettings setDockLevel:level]) {
    [NSObject cancelPreviousPerformRequestsWithTarget:self selector:@selector(raiseDock) object:nil];
    [NSObject cancelPreviousPerformRequestsWithTarget:self selector:@selector(lowerDock) object:nil];
    _dockHovering = _dockAutoRaised = NO;
    [self layoutIcons];
    [self applyDockOrder];
  }
}
- (NSInteger)dockSlotCount
{ return MAX(2, [self dockScreenHeight] / 64); }
- (NSDictionary *)dockApplicationAtSlot:(NSInteger)slot
{
  if (slot < 0 || slot >= [self dockSlotCount]) return nil;
  if (slot == [self dockSlotCount] - 1)
    return @{ @"Name": @"Recycler.GNUstep", @"Command": @"", @"Lock": @"Yes" };
  for (id entry in [_dockSettings applicationsForHeight:[self dockScreenHeight]])
    if ([entry isKindOfClass:[NSDictionary class]] && dockSlot(entry) == slot &&
        [[entry objectForKey:@"Name"] isKindOfClass:[NSString class]]) return entry;
  return slot == 0 ? @{ @"Name": @"Workspace.GNUstep", @"Command": @"", @"Lock": @"Yes" } : nil;
}
- (NSImage *)imageForDockApplication:(NSDictionary *)entry
{
  NSString *name = [entry objectForKey:@"Name"];
  if ([name isEqualToString:@"Workspace.GNUstep"]) return [NSApp applicationIconImage];
  if ([name isEqualToString:@"Recycler.GNUstep"]) return [NSImage imageNamed:@"RecyclerEmpty"];
  NSString *path = [_dockSettings iconPathForApplication:name];
  NSImage *image = path ? [[[NSImage alloc] initWithContentsOfFile:path] autorelease] : nil;
  if (!image && path) image = [NSImage imageNamed:path];
  if (!image) {
    NSString *application = [[NSApp delegate] fullPathForApplication:[name stringByDeletingPathExtension]];
    if (!application) {
      NSArray *arguments = commandArguments([entry objectForKey:@"Command"]);
      if ([arguments count]) {
        application = [arguments objectAtIndex:0];
        NSString *parent = [application stringByDeletingLastPathComponent];
        if ([[parent pathExtension] isEqualToString:@"app"]) application = parent;
      }
    }
    if (application) image = [[NSApp delegate] iconForFile:application];
  }
  return image ?: [NSImage imageNamed:@"NXUnknownApplication"];
}
- (NSImage *)dockImageAtSlot:(NSInteger)slot
{
  NSDictionary *entry = [self dockApplicationAtSlot:slot];
  return entry ? [self imageForDockApplication:entry] : nil;
}
- (NSString *)dockChangeNotification { return @"WSWaylandDockDidChange"; }
- (void)dockSettingsChanged
{
  _dockHeight = 0;
  [self layoutIcons];
  [_center postNotificationName:[self dockChangeNotification] object:self];
}
- (void)setDockValue:(NSString *)value forKey:(NSString *)key atSlot:(NSInteger)slot
{
  NSString *name = [[self dockApplicationAtSlot:slot] objectForKey:@"Name"];
  if (name && [_dockSettings setValue:value forKey:key application:name
      height:[self dockScreenHeight]]) [self dockSettingsChanged];
}
- (void)setDockImageAtPath:(NSString *)path atSlot:(NSInteger)slot
{
  NSString *name = [[self dockApplicationAtSlot:slot] objectForKey:@"Name"];
  if (name && [_dockSettings setIconPath:path forApplication:name]) [self dockSettingsChanged];
}
- (BOOL)window:(NSDictionary *)window belongsToDockApplication:(NSString *)name
{
  NSString *identifier = windowApplicationName(window);
  NSString *instance = [name stringByDeletingPathExtension];
  if ([identifier isEqualToString:instance] || [identifier isEqualToString:[name pathExtension]]) return YES;
  /* A GTK application without a session bus can advertise its executable name
     instead of its application ID. Match the actual native peer executable. */
  if ([[window objectForKey:@"flags"] unsignedIntValue] & 2) return NO;
  for (NSDictionary *entry in _dockEntries) {
    if (![[entry objectForKey:@"Name"] isEqualToString:name]) continue;
    NSArray *arguments = commandArguments([entry objectForKey:@"Command"]);
    NSString *path = [arguments count] ? [arguments objectAtIndex:0] : nil;
    if (![path isAbsolutePath]) return NO;
    NSString *executable = [[NSFileManager defaultManager] pathContentOfSymbolicLinkAtPath:
      [NSString stringWithFormat:@"/proc/%d/exe", [[window objectForKey:@"pid"] intValue]]];
    return [[path stringByResolvingSymlinksInPath] isEqualToString:executable];
  }
  return NO;
}
- (void)activateDockApplication:(NSString *)name
{
  BOOL found = NO;
  NSDictionary *candidate = nil;
  for (NSDictionary *window in [_connection windows]) {
    if (!([[window objectForKey:@"style"] unsignedIntValue] & (NSIconWindowMask | NSMiniWindowMask)) &&
        [self window:window belongsToDockApplication:name]) {
      found = YES;
      [_connection setWindow:[window objectForKey:@"id"] presented:YES];
      if (!candidate && ([[window objectForKey:@"flags"] unsignedIntValue] & 4) &&
          !([[window objectForKey:@"flags"] unsignedIntValue] & 8)) candidate = window;
    }
  }
  if (found) {
    if (candidate) {
      [_connection activateWindow:[candidate objectForKey:@"id"]];
      if ([[candidate objectForKey:@"flags"] unsignedIntValue] & 16)
        [_connection setWindow:[candidate objectForKey:@"id"] shaded:YES];
    }
    return;
  }
  for (NSDictionary *entry in _dockEntries)
    if ([[entry objectForKey:@"Name"] isEqualToString:name]) {
      [self executeCommand:[entry objectForKey:@"Command"]]; break;
    }
}
- (NSWindow *)iconForApplication:(NSString *)name inDictionary:(NSMutableDictionary *)icons
{
  NSWindow *window = [icons objectForKey:name];
  if (!window) {
    window = [[[WSNativeIconWindow alloc] initWithContentRect:NSMakeRect(0, 0, 64, 64)
      styleMask:NSIconWindowMask backing:NSBackingStoreBuffered defer:NO] autorelease];
    WSNativeDockIconView *icon = [[WSNativeDockIconView alloc] initWithName:name manager:self];
    [window setContentView:icon]; [icon release];
    [window setReleasedWhenClosed:NO]; [window setLevel:NSDockWindowLevel];
    [window setTitle:[name stringByDeletingPathExtension]]; [window setExcludedFromWindowsMenu:YES];
    [icons setObject:window forKey:name];
  }
  return window;
}
- (void)refreshDockForHeight:(NSInteger)height
{
  if (!_startupFinished || _dockHeight == height) return;
  _dockHeight = height;
  [_dockEntries release]; _dockEntries = nil;
  NSMutableArray *entries = [NSMutableArray array];
  NSMutableSet *names = [NSMutableSet set], *slots = [NSMutableSet set];
  for (id entry in [_dockSettings applicationsForHeight:height]) {
    if (![entry isKindOfClass:[NSDictionary class]]) continue;
    NSString *name = [entry objectForKey:@"Name"];
    NSInteger slot = dockSlot(entry);
    if (![name isKindOfClass:[NSString class]] || ![name length] || slot <= 0 ||
        [name isEqualToString:@"Recycler.GNUstep"] || [name isEqualToString:@"Workspace.GNUstep"] ||
        [names containsObject:name] || [slots containsObject:@(slot)]) continue;
    [names addObject:name]; [slots addObject:@(slot)]; [entries addObject:entry];
    NSWindow *window = [self iconForApplication:name inDictionary:_dockIcons];
    [(WSIconTileView *)[window contentView] setImage:[self imageForDockApplication:entry]];
    [window orderFrontRegardless];
  }
  _dockEntries = [entries copy];
  for (NSString *name in [_dockIcons allKeys])
    if (![names containsObject:name]) {
      [[_dockIcons objectForKey:name] orderOut:self]; [_dockIcons removeObjectForKey:name];
    }
}
- (void)refreshYardApplications
{
  if (!_startupFinished) return;
  NSArray *windows = [_connection windows];
  NSMutableDictionary *applications = [NSMutableDictionary dictionary];
  for (NSDictionary *window in windows) {
    if ([[window objectForKey:@"pid"] intValue] == getpid() ||
        ([[window objectForKey:@"style"] unsignedIntValue] & (NSIconWindowMask | NSMiniWindowMask))) continue;
    NSString *name = [windowApplicationName(window) stringByAppendingString:@".GNUstep"];
    if (![name length] || [applications objectForKey:name]) continue;
    BOOL represented = NO;
    for (NSDictionary *entry in _dockEntries)
      if ([self window:window belongsToDockApplication:[entry objectForKey:@"Name"]]) { represented = YES; break; }
    if (!represented) for (NSDictionary *icon in windows)
      if (([[icon objectForKey:@"style"] unsignedIntValue] & NSIconWindowMask) &&
          [[icon objectForKey:@"pid"] intValue] != getpid() &&
          [self window:icon belongsToDockApplication:name]) { represented = YES; break; }
    if (represented) continue;
    [applications setObject:window forKey:name];
    NSWindow *icon = [self iconForApplication:name inDictionary:_yardIcons];
    [(WSIconTileView *)[icon contentView] setImage:[self imageForDockApplication:@{@"Name": name}]];
    [icon orderFrontRegardless];
  }
  [_yardApplications setDictionary:applications];
  for (NSString *name in [_yardIcons allKeys])
    if (![applications objectForKey:name]) {
      [[_yardIcons objectForKey:name] orderOut:self]; [_yardIcons removeObjectForKey:name];
    }
}
- (void)applyDockOrder
{
  if ([self dockLevel] == 5) return;
  for (NSNumber *identifier in _dockWindowIDs) [_connection orderWindow:identifier above:_dockAutoRaised];
}
- (void)raiseDock
{
  if ([self dockLevel] == -1000 && _dockVisible && _dockHovering) {
    _dockAutoRaised = YES; [self applyDockOrder];
  }
}
- (void)lowerDock
{
  if ([self dockLevel] == -1000 && !_dockHovering) {
    _dockAutoRaised = NO; [self applyDockOrder];
  }
}
- (void)updateDockHover
{
  BOOL hovering = [self dockLevel] == -1000 && _dockVisible &&
    [_dockWindowIDs containsObject:[_connection pointerWindow]];
  if (hovering == _dockHovering) return;
  _dockHovering = hovering;
  [NSObject cancelPreviousPerformRequestsWithTarget:self selector:@selector(raiseDock) object:nil];
  [NSObject cancelPreviousPerformRequestsWithTarget:self selector:@selector(lowerDock) object:nil];
  [self performSelector:hovering ? @selector(raiseDock) : @selector(lowerDock) withObject:nil
    afterDelay:[_dockSettings delayForRaising:hovering] inModes:windowManagerRunLoopModes()];
}
- (NSDictionary *)pinForIcon:(NSDictionary *)window height:(NSInteger)height
{
  if (!([[window objectForKey:@"style"] unsignedIntValue] & NSIconWindowMask)) return nil;
  for (NSDictionary *entry in [_dockSettings applicationsForHeight:height]) {
    if (![entry isKindOfClass:[NSDictionary class]]) continue;
    NSString *name = [entry objectForKey:@"Name"];
    BOOL own = [[window objectForKey:@"pid"] intValue] == getpid();
    if ((own && [[window objectForKey:@"client_id"] integerValue] ==
        [[_dockIcons objectForKey:name] windowNumber]) ||
        (!own && [self window:window belongsToDockApplication:name])) return entry;
  }
  return nil;
}
- (NSString *)yardKeyForIcon:(NSDictionary *)window
{
  if ([[window objectForKey:@"pid"] intValue] == getpid())
    for (NSDictionary *icons in @[_yardIcons, _dockIcons])
      for (NSString *name in icons)
        if ([[window objectForKey:@"client_id"] integerValue] == [[icons objectForKey:name] windowNumber]) {
          NSDictionary *application = [_yardApplications objectForKey:name];
          if (!application) for (NSDictionary *candidate in [_connection windows])
            if ([[candidate objectForKey:@"pid"] intValue] != getpid() &&
                [self window:candidate belongsToDockApplication:name]) { application = candidate; break; }
          return application ? windowApplicationName(application) : [name stringByDeletingPathExtension];
        }
  NSString *name = windowApplicationName(window);
  if ([[window objectForKey:@"style"] unsignedIntValue] & NSMiniWindowMask)
    return [NSString stringWithFormat:@"%@/Mini/%@", name, [window objectForKey:@"title"]];
  return name;
}
- (void)iconMoved:(NSNotification *)notification
{
  NSDictionary *event = [notification userInfo];
  NSNumber *identifier = [event objectForKey:@"id"];
  NSDictionary *window = [_connection windowForID:identifier];
  NSInteger height = [[event objectForKey:@"screen_height"] integerValue];
  NSUInteger phase = [[event objectForKey:@"phase"] unsignedIntegerValue];
  if (phase == 0) {
    [_movingIcon release]; _movingIcon = [identifier retain];
    BOOL own = [[window objectForKey:@"pid"] intValue] == getpid();
    NSInteger clientID = [[window objectForKey:@"client_id"] integerValue];
    if ((own && (clientID == [[NSApp iconWindow] windowNumber] || clientID == [_recyclerIcon windowNumber])) ||
        [[[self pinForIcon:window height:height] objectForKey:@"Lock"] boolValue]) [_connection cancelMove:identifier];
    return;
  }
  if ([_movingIcon isEqual:identifier]) { [_movingIcon release]; _movingIcon = nil; }
  if (phase == 1 && window && [[NSScreen screens] count]) {
    NSRect screen = NSMakeRect([[event objectForKey:@"screen_x"] doubleValue],
      [[event objectForKey:@"screen_y"] doubleValue], [[event objectForKey:@"screen_width"] doubleValue], height);
    NSPoint point = NSMakePoint([[event objectForKey:@"x"] doubleValue], [[event objectForKey:@"y"] doubleValue]);
    NSPoint center = NSMakePoint(point.x + 32, point.y + 32);
    NSDictionary *pin = [self pinForIcon:window height:height];
    BOOL dockColumn = center.x >= NSMaxX(screen) - 64 && center.x < NSMaxX(screen) &&
      center.y >= NSMinY(screen) && center.y < NSMaxY(screen);
    if (dockColumn && !([[window objectForKey:@"style"] unsignedIntValue] & NSMiniWindowMask)) {
      NSInteger slot = (center.y - NSMinY(screen)) / 64;
      if (slot > 0 && slot < MAX(2, height / 64) - 1) {
        if (pin) [_dockSettings moveApplication:[pin objectForKey:@"Name"] toSlot:slot height:height];
        else {
          NSDictionary *application = window;
          if ([[window objectForKey:@"pid"] intValue] == getpid())
            application = [_yardApplications objectForKey:[[self yardKeyForIcon:window] stringByAppendingString:@".GNUstep"]];
          NSString *command = ([[application objectForKey:@"flags"] unsignedIntValue] & 2) ? nil :
            commandForPID([[application objectForKey:@"pid"] intValue]);
          if (command) [_dockSettings addApplication:@{@"Name": [windowApplicationName(application)
            stringByAppendingString:@".GNUstep"], @"Command": command, @"Lock": @"No", @"AutoLaunch": @"No"}
            atSlot:slot height:height];
        }
      }
    } else if (!pin || [_dockSettings removeApplication:[pin objectForKey:@"Name"] height:height]) {
      [_dockSettings setIconYardPosition:NSMakePoint(point.x - NSMinX(screen), point.y - NSMinY(screen))
        forApplication:[self yardKeyForIcon:window]];
    }
    [self dockSettingsChanged];
  } else [self layoutIcons];
}
- (void)layoutIcons
{
  if (_stopping) return;
  NSRect screen = [self primaryScreenFrame];
  if (NSIsEmptyRect(screen)) return;
  for (NSDictionary *head in [_connection outputs]) {
    BOOL primary = [[head objectForKey:@"enabled"] boolValue] && [[head objectForKey:@"primary"] boolValue];
    [_connection setOutput:[head objectForKey:@"id"]
      insets:[_dockSettings windowInsetsWithDock:primary && _dockVisible iconYard:_yardVisible]];
  }
  [self refreshDockForHeight:(NSInteger)screen.size.height];
  [self refreshYardApplications];
  CGFloat bottom = MAX(0, NSMaxY([GSCurrentServer() logicalDesktopBounds]));
  NSArray *windows = [_connection windows];
  for (NSDictionary *window in windows) {
    if ([[window objectForKey:@"pid"] intValue] == getpid() &&
        [[window objectForKey:@"level"] integerValue] == NSMainMenuWindowLevel &&
        ![[window objectForKey:@"sticky"] boolValue])
      [_connection setWindow:[window objectForKey:@"id"] desktop:[_connection desktopIndex] sticky:YES];
  }
  NSMutableDictionary *runningIcons = [NSMutableDictionary dictionary];
  for (NSDictionary *window in windows) {
    if ([[window objectForKey:@"pid"] intValue] == getpid() ||
        !([[window objectForKey:@"style"] unsignedIntValue] & NSIconWindowMask)) continue;
    for (NSDictionary *entry in _dockEntries) {
      NSString *name = [entry objectForKey:@"Name"];
      if (![runningIcons objectForKey:name] && [self window:window belongsToDockApplication:name])
        [runningIcons setObject:[window objectForKey:@"id"] forKey:name];
    }
  }
  NSMutableSet *dockIDs = [NSMutableSet set];
  NSInteger yardSlot = 0, maxSlot = [self dockSlotCount] - 1;
  NSInteger dockLevel = [self dockLevel] == 5 ? NSDockWindowLevel : NSNormalWindowLevel;
  for (NSDictionary *window in windows) {
    unsigned style = [[window objectForKey:@"style"] unsignedIntValue];
    if (!(style & (NSIconWindowMask | NSMiniWindowMask))) continue;
    BOOL own = [[window objectForKey:@"pid"] intValue] == getpid();
    NSInteger clientID = [[window objectForKey:@"client_id"] integerValue];
    BOOL workspace = own && clientID == [[NSApp iconWindow] windowNumber];
    BOOL recycler = own && clientID == [_recyclerIcon windowNumber];
    NSDictionary *pin = nil;
    BOOL placeholder = NO;
    for (NSDictionary *entry in _dockEntries) {
      NSString *name = [entry objectForKey:@"Name"];
      placeholder = own && clientID == [[_dockIcons objectForKey:name] windowNumber];
      if (placeholder || [[window objectForKey:@"id"] isEqual:[runningIcons objectForKey:name]]) { pin = entry; break; }
    }
    BOOL replaced = placeholder && [runningIcons objectForKey:[pin objectForKey:@"Name"]];
    NSInteger slot = recycler ? maxSlot : pin ? dockSlot(pin) : 0;
    BOOL docked = workspace || recycler || (pin && slot < maxSlot);
    BOOL visible = !replaced && (docked ? _dockVisible && (workspace || !_dockCollapsed) : _yardVisible);
    NSNumber *identifier = [window objectForKey:@"id"];
    if (docked && visible) [dockIDs addObject:identifier];
    BOOL presented = !([[window objectForKey:@"flags"] unsignedIntValue] & 32);
    if (presented != visible) [_connection setWindow:identifier presented:visible];
    NSInteger level = docked ? dockLevel : NSNormalWindowLevel;
    if (level != [[window objectForKey:@"level"] integerValue]) [_connection setWindow:identifier level:level];
    NSInteger columns = MAX(1, (NSInteger)(screen.size.width / 64) - 1);
    NSInteger yard = docked || replaced ? 0 : yardSlot++;
    NSPoint point = docked ? NSMakePoint(NSMaxX(screen) - 64, NSMaxY(screen) - 64 * (slot + 1)) :
      NSMakePoint(NSMinX(screen) + (yard % columns) * 64, NSMinY(screen) + (yard / columns) * 64);
    /* Keep Recycler flush with the lower edge when the height is not a multiple of 64. */
    if (recycler) point.y = NSMinY(screen);
    point.y = bottom - point.y - 64;
    if (!docked && !replaced) {
      NSDictionary *saved = [_dockSettings iconYardPositionForApplication:[self yardKeyForIcon:window]];
      if (saved) {
        point.x = NSMinX(screen) + MAX(0, MIN(screen.size.width - 128, [[saved objectForKey:@"X"] doubleValue]));
        point.y = bottom - NSMaxY(screen) + MAX(0, MIN(screen.size.height - 64, [[saved objectForKey:@"Y"] doubleValue]));
      }
    }
    if ([identifier isEqual:_movingIcon] || [identifier isEqual:[_connection movingWindow]]) continue;
    if (point.x != [[window objectForKey:@"x"] intValue] || point.y != [[window objectForKey:@"y"] intValue])
      [_connection moveWindow:identifier toPoint:point];
  }
  if (![_dockWindowIDs isEqual:dockIDs]) {
    [_dockWindowIDs release]; _dockWindowIDs = [dockIDs copy];
    [self applyDockOrder];
  }
  [self updateDockHover];
}
- (void)windowsChanged:(NSNotification *)notification
{
  if (_updating || _stopping) return;
  if (_movingIcon && ![_connection windowForID:_movingIcon]) { [_movingIcon release]; _movingIcon = nil; }
  _updating = YES;
  @try {
  for (NSDictionary *window in [_connection windows]) {
    if ([[window objectForKey:@"pid"] intValue] != getpid()) continue;
    NSNumber *clientID = [window objectForKey:@"client_id"];
    NSNumber *shade = [_pendingShades objectForKey:clientID];
    if (shade) {
      [_connection setWindow:[window objectForKey:@"id"] shaded:[shade boolValue]];
      [_pendingShades removeObjectForKey:clientID];
    }
  }
  [self layoutIcons];
  if (_processManager && ![_processManager workspaceIsQuitting]) {
    NSMutableDictionary *present = [NSMutableDictionary dictionary];
    NSDictionary *active = nil;
    for (NSDictionary *window in [_connection windows]) {
      NSNumber *pid = [window objectForKey:@"pid"];
      /* Xwayland's client-supplied PID is not a native peer credential. */
      if ([pid intValue] <= 1 || ([[window objectForKey:@"flags"] unsignedIntValue] & 2)) continue;
      if ([pid intValue] != getpid() && [_launchIcons count]) {
        NSString *executable = [[NSFileManager defaultManager] pathContentOfSymbolicLinkAtPath:
          [NSString stringWithFormat:@"/proc/%d/exe", [pid intValue]]];
        for (NSString *path in [_launchIcons allKeys])
          if ([[path stringByResolvingSymlinksInPath] isEqualToString:executable]) [self endApplicationLaunch:path];
      }
      NSDictionary *info = registeredApplication(_processManager, pid);
      if (!info || [[info objectForKey:@"NSApplicationUsesDistributedObjects"] isEqual:@NO]) {
        info = [_foreignApplications objectForKey:pid];
        if (!info) {
          NSString *path = [[NSFileManager defaultManager] pathContentOfSymbolicLinkAtPath:
            [NSString stringWithFormat:@"/proc/%d/exe", [pid intValue]]];
          info = @{@"NSApplicationName": windowApplicationName(window),
            @"NSApplicationPath": path ?: @"--", @"NSApplicationProcessIdentifier": pid,
            @"IsXWindowApplication": @"NO", @"NSApplicationUsesDistributedObjects": @NO};
          [_processManager applicationDidLaunch:[NSNotification
            notificationWithName:NSWorkspaceDidLaunchApplicationNotification object:self userInfo:info]];
        }
        [present setObject:info forKey:pid];
      }
      if (_focusEventsEnabled && ([[window objectForKey:@"flags"] unsignedIntValue] & 1)) active = info;
    }
    for (NSNumber *pid in _foreignApplications) {
      NSDictionary *info = registeredApplication(_processManager, pid);
      BOOL native = info && ![[info objectForKey:@"NSApplicationUsesDistributedObjects"] isEqual:@NO];
      if (![present objectForKey:pid] && !native) [_processManager applicationDidTerminate:[NSNotification
        notificationWithName:NSWorkspaceDidTerminateApplicationNotification object:self
        userInfo:[_foreignApplications objectForKey:pid]]];
    }
    [_foreignApplications setDictionary:present];
    if (_focusEventsEnabled) [_processManager setActiveApplicationInfo:active];
  }
  } @finally { _updating = NO; }
}
@end
