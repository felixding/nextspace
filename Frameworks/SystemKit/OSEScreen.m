/* -*- mode: objc -*- */
//
// Project: NEXTSPACE - SystemKit framework
//
// Copyright (C) 2014-2019 Sergii Stoian
//
// This application is free software; you can redistribute it and/or
// modify it under the terms of the GNU General Public
// License as published by the Free Software Foundation; either
// version 2 of the License, or (at your option) any later version.
//
// This application is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
// Library General Public License for more details.
//
// You should have received a copy of the GNU General Public
// License along with this library; if not, write to the Free
// Software Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111 USA.
//

#import "OSEDefaults.h"
#import "OSEWaylandDisplay.h"
#import "OSEDisplayModel.h"
#import "OSEPower.h"
#import <AppKit/AppKit.h>
#import <GNUstepGUI/GSDisplayServer.h>
extern NSString *GSSessionServiceName(NSString *) __attribute__((weak));
@interface GSDisplayServer (NativeDisplayModel)
- (NSArray *)nativeOutputDescriptions;
@end

// NXGlobalDomain key
NSString *OSEDesktopBackgroundColor = @"DesktopBackgroundColor";

// Displays.config field keys
NSString *OSEDisplayIsActiveKey = @"Active";
NSString *OSEDisplayIsMainKey = @"Main";
NSString *OSEDisplayGammaKey = @"Gamma";
NSString *OSEDisplayGammaRedKey = @"Red";
NSString *OSEDisplayGammaGreenKey = @"Green";
NSString *OSEDisplayGammaBlueKey = @"Blue";
NSString *OSEDisplayGammaBrightnessKey = @"Brightness";
NSString *OSEDisplayIDKey = @"ID";
NSString *OSEDisplayNameKey = @"Name";
NSString *OSEDisplayFrameKey = @"Frame";
NSString *OSEDisplayHiddenFrameKey = @"FrameHidden";
NSString *OSEDisplayFrameRateKey = @"FrameRate";
NSString *OSEDisplayResolutionNameKey = @"ResolutionName";
NSString *OSEDisplayResolutionSizeKey = @"ResolutionSize";
NSString *OSEDisplayResolutionRateKey = @"ResolutionRate";
NSString *OSEDisplayPhSizeKey = @"PhysicalSize";
NSString *OSEDisplayPropertiesKey = @"Properties";
NSString *OSEDisplayModeKey = @"Mode";
NSString *OSEDisplayScaleKey = @"Scale120";
NSString *OSEDisplayTransformKey = @"Transform";

// Notifications
NSString *OSEScreenDidChangeNotification = @"OSEScreenDidChangeNotification";
NSString *OSEScreenDidUpdateNotification = @"OSEScreenDidUpdateNotification";

static OSEScreen *systemScreen = nil;

@implementation OSEScreen
+ (id)sharedScreen
{
  if (systemScreen == nil) {
    systemScreen = [[OSEScreen alloc] init];
  }

  return systemScreen;
}

- (NSRect)logicalBounds
{
  NSRect bounds = NSZeroRect;
  BOOL first = YES;
  for (OSEDisplay *display in [self activeDisplays]) {
    bounds = first ? [display frame] : NSUnionRect(bounds, [display frame]); first = NO;
  }
  return bounds;
}

- (void)setUseAutosave:(BOOL)yn
{
  useAutosave = yn;
}

- (BOOL)savedBackgroundColorRed:(CGFloat *)redComponent
                          green:(CGFloat *)greenComponent
                           blue:(CGFloat *)blueComponent
{
  NSDictionary	*dBack;
  BOOL		success = NO;
  
  dBack = [[OSEDefaults globalUserDefaults]
                               objectForKey:OSEDesktopBackgroundColor];
  if (dBack) {
    *redComponent = [dBack[@"Red"] floatValue];
    *greenComponent = [dBack[@"Green"] floatValue];
    *blueComponent = [dBack[@"Blue"] floatValue];
    success = YES;
  }
  else {
    *redComponent = 83.0/255.0;
    *greenComponent = 83.0/255.0;
    *blueComponent = 116.0/255.0;
    success = YES;
  }
  
  return success;
}

- (NSArray *)allDisplays
{
  return systemDisplays;
}

- (NSArray *)activeDisplays
{
  NSMutableArray *activeDisplays = [[NSMutableArray alloc] init];
  
  for (OSEDisplay *display in systemDisplays) {
    if ([display isActive]) {
      NSLog(@"Adding active display: %@", [display outputName]);
      [activeDisplays addObject:display];
    }
  }
  return [activeDisplays autorelease];
}

- (NSArray *)connectedDisplays
{
  NSMutableArray *connectedDisplays = [[NSMutableArray alloc] init];

  for (OSEDisplay *display in systemDisplays) {
      if ([display isConnected]) {
        [connectedDisplays addObject:display];
      }
  }
  return [connectedDisplays autorelease];
}

- (OSEDisplay *)mainDisplay
{
  OSEDisplay *display = nil;
  
  for (OSEDisplay *d in systemDisplays) {
    if ([d isActive] && [d isMain]) {
      display = d;
      break;
    }
  }
  
  return display;
}

- (OSEDisplay *)displayAtPoint:(NSPoint)point
{
  for (OSEDisplay *display in systemDisplays) {
    if (NSPointInRect(point, [display frame]) == YES) {
      return display;
    }
  }
  
  return nil;
}

- (OSEDisplay *)displayWithName:(NSString *)name
{
  for (OSEDisplay *display in systemDisplays) {
    if ([[display outputName] isEqualToString:name]) {
      return display;
    }
  }
  return nil;
}

- (NSDictionary *)descriptionOfDisplay:(OSEDisplay *)display
                              inLayout:(NSArray *)layout
{
  for (NSDictionary *dDesc in layout)
    {
      if ([[dDesc objectForKey:@"Name"] isEqualToString:display.outputName] &&
          [[dDesc objectForKey:@"ID"] isEqual:[display uniqueID]])
        {
          return dDesc;
        }
    }

  return nil;
}

- (id)objectForKey:(NSString *)key
        forDisplay:(OSEDisplay *)display
          inLayout:(NSArray *)layout
{
  return [[self descriptionOfDisplay:display inLayout:layout] objectForKey:key];
}

- (id)init
{
  if (!(self = [super init])) return nil;
  [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(displayChanged:)
    name:NSApplicationDidChangeScreenParametersNotification object:nil];
  NSString *object = GSSessionServiceName ? GSSessionServiceName(@"OSEScreen") : @"OSEScreen";
  [[NSDistributedNotificationCenter defaultCenter] addObserver:self selector:@selector(displayChanged:)
    name:OSEScreenDidChangeNotification object:object];
  [self refreshDisplays];
  return self;
}
- (void)dealloc
{
  [[NSNotificationCenter defaultCenter] removeObserver:self];
  [[NSDistributedNotificationCenter defaultCenter] removeObserver:self];
  [_state release]; [_transaction release];
  [systemDisplays release];
  [_systemPower stopEventsMonitor]; [_systemPower release];
  if (systemScreen == self) systemScreen = nil;
  [super dealloc];
}
- (NSDictionary *)request:(NSDictionary *)request { return OSERequestSessionSettings(request); }
- (void)displayChanged:(NSNotification *)notification { [self refreshDisplays]; }
- (void)refreshDisplays
{
  if (_refreshing) return;
  _refreshing = YES;
  NSDictionary *state = [self request:[NSDictionary dictionaryWithObject:@"state" forKey:@"action"]];
  NSArray *heads = [state objectForKey:@"heads"];
  if (![heads isKindOfClass:[NSArray class]] || [[state objectForKey:@"schema"] intValue] != 1) {
    state = nil;
    GSDisplayServer *server = GSCurrentServer();
    heads = [server respondsToSelector:@selector(nativeOutputDescriptions)] ? [server nativeOutputDescriptions] : nil;
  }
  [_state release]; _state = [state copy];
  NSMutableArray *displays = [NSMutableArray array];
  for (NSDictionary *head in heads) {
    NSUInteger matches = 0;
    for (NSDictionary *candidate in heads)
      if ([hardwareIdentity(head, NO) isEqual:hardwareIdentity(candidate, NO)]) matches++;
    OSEDisplay *display = [[OSEDisplay alloc] initWithDescriptor:head screen:self
      duplicateIdentity:matches > 1];
    [displays addObject:display]; [display release];
  }
  [systemDisplays release]; systemDisplays = [displays mutableCopy];
  _refreshing = NO;
  [[NSNotificationCenter defaultCenter] postNotificationName:OSEScreenDidUpdateNotification object:self];
}
- (BOOL)isNativeDisplay { return YES; }
- (BOOL)supportsDisplayConfiguration { return _state && [systemDisplays count] > 0; }
- (BOOL)supportsDisplayTransactions { return [self supportsDisplayConfiguration]; }
- (NSSize)sizeInPixels { return [self logicalBounds].size; } /* Legacy virtual-screen geometry. */
- (NSSize)sizeInMilimeters { return [[self mainDisplay] physicalSize]; }
- (NSUInteger)colorDepth { return 24; }
- (OSEPower *)systemPower
{
  if (!_systemPower) _systemPower = [[OSEPower sharedPower] retain];
  return _systemPower;
}
- (BOOL)isLidClosed { return [[self systemPower] isLidClosed]; }
- (OSEDisplay *)displayWithID:(id)identifier
{
  for (OSEDisplay *display in systemDisplays) if ([[display uniqueID] isEqual:identifier]) return display;
  return nil;
}
- (OSEDisplay *)displayWithMouseCursor
{
  NSPoint point = [NSEvent mouseLocation];
  point.y = NSMaxY([self logicalBounds]) - point.y;
  return [self displayAtPoint:point];
}
- (BOOL)backgroundColorRed:(CGFloat *)r green:(CGFloat *)g blue:(CGFloat *)b
{
  NSDictionary *color = [self request:[NSDictionary dictionaryWithObject:@"background" forKey:@"action"]];
  if (!color) return NO;
  *r = [[color objectForKey:@"Red"] doubleValue]; *g = [[color objectForKey:@"Green"] doubleValue];
  *b = [[color objectForKey:@"Blue"] doubleValue]; return YES;
}
- (BOOL)setBackgroundColorRed:(CGFloat)r green:(CGFloat)g blue:(CGFloat)b
{
  if (!isfinite(r) || !isfinite(g) || !isfinite(b) || r < 0 || r > 1 || g < 0 || g > 1 || b < 0 || b > 1) return NO;
  NSDictionary *color = [NSDictionary dictionaryWithObjectsAndKeys:[NSNumber numberWithDouble:r], @"Red",
    [NSNumber numberWithDouble:g], @"Green", [NSNumber numberWithDouble:b], @"Blue", nil];
  return [self request:[NSDictionary dictionaryWithObjectsAndKeys:@"background", @"action", color, @"color", nil]] != nil;
}

- (NSArray *)currentLayout
{
  NSMutableArray *layout = [NSMutableArray array];
  for (OSEDisplay *display in systemDisplays) {
    NSDictionary *mode = [display modePixelSize].width > 0 ?
      resolution([(OSEDisplay *)display descriptor]) : [display bestResolution];
    [layout addObject:[NSDictionary dictionaryWithObjectsAndKeys:
      [display uniqueID], OSEDisplayIDKey, [display outputName], OSEDisplayNameKey,
      [display isActive] ? @"YES" : @"NO", OSEDisplayIsActiveKey,
      [display isMain] ? @"YES" : @"NO", OSEDisplayIsMainKey,
      NSStringFromRect([display frame]), OSEDisplayFrameKey,
      NSStringFromRect([display hiddenFrame]), OSEDisplayHiddenFrameKey,
      NSStringFromSize([display physicalSize]), OSEDisplayPhSizeKey,
      [mode objectForKey:OSEDisplayResolutionRateKey], OSEDisplayFrameRateKey,
      mode, OSEDisplayModeKey, [NSNumber numberWithUnsignedInteger:[display scaleNumerator]], OSEDisplayScaleKey,
      [NSNumber numberWithUnsignedInteger:[display transform]], OSEDisplayTransformKey,
      [display gammaDescription], OSEDisplayGammaKey, [display properties], OSEDisplayPropertiesKey, nil]];
  }
  return layout;
}
- (NSArray *)headsForLayout:(NSArray *)layout
{
  if (![layout isKindOfClass:[NSArray class]] || [layout count] != [systemDisplays count]) return nil;
  NSMutableArray *heads = [NSMutableArray array];
  NSMutableSet *used = [NSMutableSet set];
  for (id entry in layout) {
    if (![entry isKindOfClass:[NSDictionary class]]) return nil;
    id identity = [entry objectForKey:OSEDisplayIDKey];
    OSEDisplay *display = (OSEDisplay *)[self displayWithID:identity];
    if (!display || [used containsObject:identity]) return nil;
    [used addObject:identity];
    NSDictionary *mode = [entry objectForKey:OSEDisplayModeKey];
    if (![mode isKindOfClass:[NSDictionary class]]) return nil;
    NSString *size = [mode objectForKey:OSEDisplayResolutionSizeKey];
    NSString *frameString = [entry objectForKey:[[entry objectForKey:OSEDisplayIsActiveKey] boolValue] ?
      OSEDisplayFrameKey : OSEDisplayHiddenFrameKey];
    id scale = [entry objectForKey:OSEDisplayScaleKey], transform = [entry objectForKey:OSEDisplayTransformKey];
    id rate = [mode objectForKey:OSEDisplayResolutionRateKey];
    if (![size isKindOfClass:[NSString class]] || ![frameString isKindOfClass:[NSString class]] ||
        ![scale isKindOfClass:[NSNumber class]] || ![transform isKindOfClass:[NSNumber class]] ||
        ![rate isKindOfClass:[NSNumber class]]) return nil;
    NSSize pixels = NSSizeFromString(size);
    NSRect frame = NSRectFromString(frameString);
    id gamma = [entry objectForKey:OSEDisplayGammaKey];
    if (gamma && !nativeGammaSettings(gamma)) return nil;
    if (!isfinite(pixels.width) || !isfinite(pixels.height) || !isfinite([rate doubleValue]) ||
        !isfinite(frame.origin.x) || !isfinite(frame.origin.y)) return nil;
    NSMutableDictionary *head = [[[display descriptor] mutableCopy] autorelease];
    [head addEntriesFromDictionary:[NSDictionary dictionaryWithObjectsAndKeys:
      [NSNumber numberWithBool:[[entry objectForKey:OSEDisplayIsActiveKey] boolValue]], @"enabled",
      [NSNumber numberWithBool:[[entry objectForKey:OSEDisplayIsMainKey] boolValue]], @"primary",
      [NSNumber numberWithDouble:pixels.width], @"width", [NSNumber numberWithDouble:pixels.height], @"height",
      [NSNumber numberWithDouble:round([rate doubleValue] * 1000)], @"refresh", scale, @"scale", transform, @"transform",
      [NSNumber numberWithDouble:frame.origin.x], @"x", [NSNumber numberWithDouble:frame.origin.y], @"y", nil]];
    [heads addObject:head];
  }
  return heads;
}
- (NSDictionary *)layoutRequest:(NSString *)action layout:(NSArray *)layout timeout:(NSUInteger)milliseconds
{
  if (![self supportsDisplayConfiguration]) return nil;
  NSArray *heads = [self headsForLayout:layout];
  if (!heads) return nil;
  return [self request:[NSDictionary dictionaryWithObjectsAndKeys:action, @"action", heads, @"layout",
    [_state objectForKey:@"revision"], @"revision", [NSNumber numberWithUnsignedInteger:milliseconds], @"timeout", nil]];
}
- (NSDictionary *)testDisplayLayout:(NSArray *)layout { return [self layoutRequest:@"test" layout:layout timeout:0]; }
- (NSDictionary *)beginDisplayLayout:(NSArray *)layout timeout:(NSUInteger)milliseconds
{
  NSDictionary *result = [self layoutRequest:@"apply" layout:layout timeout:milliseconds];
  if ([[result objectForKey:@"status"] intValue] == 1 && [result objectForKey:@"token"]) {
    [_transaction release]; _transaction = [[result objectForKey:@"token"] copy];
  }
  [self refreshDisplays];
  return result;
}
- (NSDictionary *)transactionRequest:(NSString *)action
{
  if (!_transaction) return nil;
  return [self request:[NSDictionary dictionaryWithObjectsAndKeys:action, @"action", _transaction, @"token", nil]];
}
- (NSDictionary *)displayLayoutStatus { return [self transactionRequest:@"status"]; }
- (BOOL)confirmDisplayLayout
{
  NSDictionary *result = [self transactionRequest:@"confirm"];
  [self refreshDisplays];
  return result && [[result objectForKey:@"status"] intValue] == 2;
}
- (BOOL)cancelDisplayLayout
{
  NSDictionary *result = [self transactionRequest:@"cancel"];
  [self refreshDisplays];
  return result && [[result objectForKey:@"status"] intValue] == 3;
}
- (BOOL)validateLayout:(NSArray *)layout
{
  NSDictionary *result = [self testDisplayLayout:layout];
  return result && [[result objectForKey:@"status"] intValue] == 0;
}
- (BOOL)applyDisplayLayout:(NSArray *)layout
{
  NSDictionary *result = [self beginDisplayLayout:layout timeout:15000];
  BOOL applied = result && [[result objectForKey:@"status"] intValue] == 1 && [self confirmDisplayLayout];
  NSArray *gammaDisplays = [[systemDisplays copy] autorelease];
  if (applied) for (NSDictionary *entry in layout) {
    NSDictionary *gamma = [entry objectForKey:OSEDisplayGammaKey];
    for (OSEDisplay *display in gammaDisplays)
      if (gamma && [[display uniqueID] isEqual:[entry objectForKey:OSEDisplayIDKey]] && [display isGammaSupported])
        applied &= [display applyGammaDescription:gamma];
  }
  if (applied && useAutosave) [self saveCurrentDisplayLayout];
  return applied;
}
- (void)changeDisplay:(OSEDisplay *)display values:(NSDictionary *)values
{
  NSMutableArray *layout = [NSMutableArray array];
  for (NSDictionary *entry in [self currentLayout]) {
    NSMutableDictionary *changed = [[entry mutableCopy] autorelease];
    if ([[entry objectForKey:OSEDisplayIDKey] isEqual:[display uniqueID]]) [changed addEntriesFromDictionary:values];
    [layout addObject:changed];
  }
  BOOL primary = NO;
  for (NSDictionary *entry in layout)
    primary |= [[entry objectForKey:OSEDisplayIsMainKey] boolValue] && [[entry objectForKey:OSEDisplayIsActiveKey] boolValue];
  for (NSMutableDictionary *entry in layout) {
    BOOL active = [[entry objectForKey:OSEDisplayIsActiveKey] boolValue];
    if (!active) [entry setObject:@"NO" forKey:OSEDisplayIsMainKey];
    else if (!primary) { [entry setObject:@"YES" forKey:OSEDisplayIsMainKey]; primary = YES; }
  }
  [self applyDisplayLayout:layout];
}
- (void)activateDisplay:(OSEDisplay *)display
{
  [self changeDisplay:display values:[NSDictionary dictionaryWithObjectsAndKeys:@"YES", OSEDisplayIsActiveKey,
    NSStringFromRect([display hiddenFrame]), OSEDisplayFrameKey, nil]];
}
- (void)deactivateDisplay:(OSEDisplay *)display
{ [self changeDisplay:display values:[NSDictionary dictionaryWithObject:@"NO" forKey:OSEDisplayIsActiveKey]]; }
- (void)setMainDisplay:(OSEDisplay *)display
{
  if (!display || ![display isActive]) return;
  NSMutableArray *layout = [NSMutableArray array];
  for (NSDictionary *entry in [self currentLayout]) {
    NSMutableDictionary *changed = [[entry mutableCopy] autorelease];
    [changed setObject:[[entry objectForKey:OSEDisplayIDKey] isEqual:[display uniqueID]] ? @"YES" : @"NO"
      forKey:OSEDisplayIsMainKey];
    [layout addObject:changed];
  }
  [self applyDisplayLayout:layout];
}
- (void)setDisplay:(OSEDisplay *)display resolution:(NSDictionary *)mode
{
  NSRect frame = [display isActive] ? [display frame] : [display hiddenFrame];
  [self setDisplay:display resolution:mode position:frame.origin];
}
- (void)setDisplay:(OSEDisplay *)display resolution:(NSDictionary *)mode position:(NSPoint)position
{
  if (!display || !mode) return;
  NSRect frame = NSMakeRect(position.x, position.y, 0, 0);
  frame.size = logicalSize(mode, [display scaleNumerator], [display transform]);
  [self changeDisplay:display values:[NSDictionary dictionaryWithObjectsAndKeys:
    mode, OSEDisplayModeKey, NSStringFromRect(frame), OSEDisplayFrameKey, @"YES", OSEDisplayIsActiveKey, nil]];
}
- (NSArray *)arrangedDisplayLayout
{
  NSMutableArray *layout = [NSMutableArray array];
  CGFloat x = 0;
  for (NSDictionary *entry in [self currentLayout]) {
    NSMutableDictionary *changed = [[entry mutableCopy] autorelease];
    if ([[entry objectForKey:OSEDisplayIsActiveKey] boolValue]) {
      NSRect frame = NSRectFromString([entry objectForKey:OSEDisplayFrameKey]);
      frame.origin = NSMakePoint(x, 0); x += frame.size.width;
      [changed setObject:NSStringFromRect(frame) forKey:OSEDisplayFrameKey];
    }
    [layout addObject:changed];
  }
  return layout;
}
- (NSArray *)defaultLayout:(BOOL)arrange
{
  NSMutableArray *layout = [NSMutableArray array];
  CGFloat x = 0;
  for (OSEDisplay *display in systemDisplays) {
    NSDictionary *entry = [self descriptionOfDisplay:display inLayout:[self currentLayout]];
    NSMutableDictionary *changed = [[entry mutableCopy] autorelease];
    NSDictionary *mode = [display bestResolution];
    NSRect frame = [display isActive] ? [display frame] : [display hiddenFrame];
    frame.size = logicalSize(mode, 120, 0);
    if (arrange) { frame.origin = NSMakePoint(x, 0); x += frame.size.width; }
    [changed setObject:mode forKey:OSEDisplayModeKey];
    [changed setObject:[NSNumber numberWithInt:120] forKey:OSEDisplayScaleKey];
    [changed setObject:[NSNumber numberWithInt:0] forKey:OSEDisplayTransformKey];
    [changed setObject:@"YES" forKey:OSEDisplayIsActiveKey];
    [changed setObject:[layout count] ? @"NO" : @"YES" forKey:OSEDisplayIsMainKey];
    [changed setObject:NSStringFromRect(frame) forKey:OSEDisplayFrameKey];
    [layout addObject:changed];
  }
  return layout;
}
- (NSString *)layoutPath
{ return [@"~/Library/Preferences/.NextSpace/WaylandDisplays.plist" stringByExpandingTildeInPath]; }
- (BOOL)saveCurrentDisplayLayout
{
  [self refreshDisplays];
  if (![self supportsDisplayConfiguration] || [[_state objectForKey:@"pending"] boolValue]) return NO;
  NSString *path = [self layoutPath];
  if (![[NSFileManager defaultManager] createDirectoryAtPath:[path stringByDeletingLastPathComponent]
      withIntermediateDirectories:YES attributes:nil error:NULL]) return NO;
  NSMutableArray *layout = [NSMutableArray array];
  for (NSDictionary *entry in [self currentLayout]) {
    NSMutableDictionary *saved = [[entry mutableCopy] autorelease];
    [saved removeObjectForKey:OSEDisplayPropertiesKey]; /* No compositor-local IDs in durable profiles. */
    [layout addObject:saved];
  }
  return [[NSDictionary dictionaryWithObjectsAndKeys:[NSNumber numberWithInt:2], @"Schema",
    layout, @"Layout", nil] writeToFile:path atomically:YES];
}
- (NSArray *)savedDisplayLayout
{
  NSDictionary *profile = [NSDictionary dictionaryWithContentsOfFile:[self layoutPath]];
  id layout = [profile objectForKey:@"Layout"];
  return [[profile objectForKey:@"Schema"] intValue] == 2 && [layout isKindOfClass:[NSArray class]] ? layout : nil;
}
- (BOOL)applySavedDisplayLayout
{
  NSArray *saved = [self savedDisplayLayout];
  if (![saved count]) return NO;
  NSMutableDictionary *byID = [NSMutableDictionary dictionary];
  for (id entry in saved) {
    if (![entry isKindOfClass:[NSDictionary class]]) return NO;
    id identity = [entry objectForKey:OSEDisplayIDKey];
    if (![identity isKindOfClass:[NSData class]] || [byID objectForKey:identity]) return NO;
    [byID setObject:entry forKey:identity];
  }
  NSMutableArray *layout = [NSMutableArray array];
  BOOL matched = NO;
  id primaryID = nil;
  for (NSDictionary *current in [self currentLayout]) {
    id identity = [current objectForKey:OSEDisplayIDKey];
    NSDictionary *profile = [byID objectForKey:identity];
    NSMutableDictionary *head = [[(profile ?: current) mutableCopy] autorelease];
    matched |= profile != nil;
    if (profile && [[profile objectForKey:OSEDisplayIsActiveKey] boolValue] &&
        [[profile objectForKey:OSEDisplayIsMainKey] boolValue]) primaryID = identity;
    [layout addObject:head];
  }
  if (!matched) return NO;
  if (!primaryID) for (NSDictionary *head in layout)
    if ([[head objectForKey:OSEDisplayIsActiveKey] boolValue]) { primaryID = [head objectForKey:OSEDisplayIDKey]; break; }
  for (NSMutableDictionary *head in layout) [head setObject:
    [[head objectForKey:OSEDisplayIDKey] isEqual:primaryID] ? @"YES" : @"NO" forKey:OSEDisplayIsMainKey];
  /* Disconnected heads are ignored; newly connected heads retain their safe
     current settings. Invalid modes or an all-disabled profile fail atomically. */
  return [self applyDisplayLayout:layout];
}
@end
