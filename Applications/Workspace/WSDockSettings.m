/* SPDX-License-Identifier: GPL-2.0-or-later */
#import "WSDockSettings.h"
#include <math.h>

static id propertyListCopy(id value, NSPropertyListReadOptions options)
{
  if (!value || ![NSPropertyListSerialization propertyList:value isValidForFormat:NSPropertyListBinaryFormat_v1_0]) return nil;
  NSData *data = [NSPropertyListSerialization dataWithPropertyList:value
    format:NSPropertyListBinaryFormat_v1_0 options:0 error:NULL];
  return data ? [NSPropertyListSerialization propertyListWithData:data options:options format:NULL error:NULL] : nil;
}
static NSString *applicationName(id entry)
{
  id name = [entry isKindOfClass:[NSDictionary class]] ? [entry objectForKey:@"Name"] : nil;
  return [name isKindOfClass:[NSString class]] ? name : nil;
}

@implementation WSDockSettings
+ (NSString *)legacyDirectory
{ return [GSDefaultsRootForUser(NSUserName()) stringByAppendingPathComponent:@".NextSpace"]; }
- (id)initWithDefaults:(NSUserDefaults *)defaults domain:(NSString *)domain legacyDirectory:(NSString *)directory
{
  if (!(self = [super init])) return nil;
  _defaults = [defaults retain]; _domain = [domain copy]; _legacyDirectory = [directory copy];
  return self;
}
- (void)dealloc
{
  [_defaults release]; [_domain release]; [_legacyDirectory release];
  [super dealloc];
}
- (id)storedValue:(NSString *)key
{ return [[_defaults persistentDomainForName:_domain] objectForKey:key]; }
- (BOOL)store:(id)value forKey:(NSString *)key
{
  NSDictionary *previous = [[[_defaults persistentDomainForName:_domain] copy] autorelease];
  id snapshot = propertyListCopy(value, NSPropertyListImmutable);
  if (!snapshot) return NO;
  NSMutableDictionary *domain = previous ? [[previous mutableCopy] autorelease] : [NSMutableDictionary dictionary];
  [domain setObject:snapshot forKey:key];
  [_defaults setPersistentDomain:domain forName:_domain];
  if ([_defaults synchronize]) return YES;
  if (previous) [_defaults setPersistentDomain:previous forName:_domain];
  else [_defaults removePersistentDomainForName:_domain];
  return NO;
}
- (NSDictionary *)dock
{
  id dock = [self storedValue:@"WaylandDock"];
  if (![dock isKindOfClass:[NSDictionary class]]) {
    NSString *path = [_legacyDirectory stringByAppendingPathComponent:@"WMState.plist"];
    if (![[NSFileManager defaultManager] fileExistsAtPath:path])
      path = [[NSBundle mainBundle] pathForResource:@"WMState" ofType:@"plist"];
    dock = [[NSDictionary dictionaryWithContentsOfFile:path] objectForKey:@"Dock"];
  }
  if ([dock isKindOfClass:[NSDictionary class]]) return propertyListCopy(dock, NSPropertyListImmutable);
  NSDictionary *workspace = [NSDictionary dictionaryWithObjectsAndKeys:@"Workspace.GNUstep", @"Name",
    @"0,0", @"Position", @"Yes", @"Lock", @"Yes", @"AutoLaunch",
    @"NEXTSPACE internal: don't edit it!", @"Command", nil];
  return [NSDictionary dictionaryWithObject:[NSArray arrayWithObject:workspace] forKey:@"Applications"];
}
- (NSDictionary *)legacyPreferences
{ return [NSDictionary dictionaryWithContentsOfFile:[_legacyDirectory stringByAppendingPathComponent:@"WM.plist"]]; }
- (NSTimeInterval)delayForRaising:(BOOL)raising
{
  NSDictionary *preferences = [self legacyPreferences];
  id value = [preferences objectForKey:raising ? @"ClipAutoraiseDelay" : @"ClipAutolowerDelay"];
  NSInteger delay = [value respondsToSelector:@selector(integerValue)] ? [value integerValue] : (raising ? 600 : 1000);
  return MAX(0, MIN(60000, delay)) / 1000.0;
}
- (NSArray *)windowInsetsWithDock:(BOOL)dockVisible iconYard:(BOOL)yardVisible
{
  NSDictionary *preferences = [self legacyPreferences];
  id dock = [preferences objectForKey:@"NoWindowOverDock"];
  id yard = [preferences objectForKey:@"NoWindowOverIcons"];
  /* Match the existing 64-point icons and three-point Dock clearance. */
  return [NSArray arrayWithObjects:[NSNumber numberWithInt:0], [NSNumber numberWithInt:0],
    [NSNumber numberWithInt:dockVisible && (![dock respondsToSelector:@selector(boolValue)] || [dock boolValue]) ? 67 : 0],
    [NSNumber numberWithInt:yardVisible && (![yard respondsToSelector:@selector(boolValue)] || [yard boolValue]) ? 64 : 0], nil];
}
- (NSUInteger)maximizedDragMode
{
  NSDictionary *preferences = [self legacyPreferences];
  id value = [preferences objectForKey:@"DragMaximizedWindow"];
  if (![value isKindOfClass:[NSString class]]) return 0;
  NSArray *names = [NSArray arrayWithObjects:@"Move", @"RestoreGeometry", @"Unmaximize", @"NoMove", nil];
  for (NSUInteger mode = 0; mode < [names count]; mode++)
    if ([value caseInsensitiveCompare:[names objectAtIndex:mode]] == NSOrderedSame) return mode;
  return 0;
}
- (NSDictionary *)titleAppearance
{
  NSDictionary *preferences = [self legacyPreferences];
  id font = [preferences objectForKey:@"WindowTitleFont"];
  if (![font isKindOfClass:[NSString class]] || ![font length]) font = @"Helvetica:bold:pixelsize=12";
  id antialiased = [preferences objectForKey:@"UseAntialiasedText"];
  id justification = [preferences objectForKey:@"TitleJustify"];
  NSArray *names = [NSArray arrayWithObjects:@"center", @"left", @"right", nil];
  justification = [justification isKindOfClass:[NSString class]] ? [justification lowercaseString] : @"center";
  if (![names containsObject:justification]) justification = @"center";
  return [NSDictionary dictionaryWithObjectsAndKeys:font, @"font", justification, @"justification",
    [NSNumber numberWithBool:[antialiased respondsToSelector:@selector(boolValue)] && [antialiased boolValue]], @"antialiased", nil];
}
- (NSArray *)applicationsInDock:(NSDictionary *)dock height:(NSInteger)height
{
  id applications = [dock objectForKey:[NSString stringWithFormat:@"Applications%ld", (long)height]];
  if (![applications isKindOfClass:[NSArray class]]) applications = [dock objectForKey:@"Applications"];
  return [applications isKindOfClass:[NSArray class]] ? applications : [NSArray array];
}
- (NSArray *)applicationsForHeight:(NSInteger)height
{ return [self applicationsInDock:[self dock] height:height]; }
- (BOOL)storeApplications:(NSArray *)applications inDock:(NSMutableDictionary *)dock height:(NSInteger)height
{
  [dock setObject:applications forKey:@"Applications"];
  [dock setObject:applications forKey:[NSString stringWithFormat:@"Applications%ld", (long)height]];
  return [self store:dock forKey:@"WaylandDock"];
}
- (BOOL)setDockLevel:(NSInteger)level
{
  if (level != -1000 && level != 0 && level != 5) return NO;
  NSMutableDictionary *dock = propertyListCopy([self dock], NSPropertyListMutableContainers);
  [dock setObject:level == 5 ? @"No" : @"Yes" forKey:@"Lowered"];
  [dock setObject:level == -1000 ? @"Yes" : @"No" forKey:@"AutoRaiseLower"];
  return [self store:dock forKey:@"WaylandDock"];
}
- (BOOL)setDockValue:(NSString *)value forKey:(NSString *)key
{
  if (![value isKindOfClass:[NSString class]] || ![[NSArray arrayWithObjects:@"Collapsed", @"Lowered",
      @"Position", nil] containsObject:key]) return NO;
  NSMutableDictionary *dock = propertyListCopy([self dock], NSPropertyListMutableContainers);
  [dock setObject:value forKey:key];
  return [self store:dock forKey:@"WaylandDock"];
}
- (BOOL)setValue:(NSString *)value forKey:(NSString *)key application:(NSString *)name height:(NSInteger)height
{
  if (![value isKindOfClass:[NSString class]] || ![[NSArray arrayWithObjects:@"Command", @"PasteCommand",
      @"DropCommand", @"AutoLaunch", @"Lock", nil] containsObject:key]) return NO;
  NSMutableDictionary *dock = propertyListCopy([self dock], NSPropertyListMutableContainers);
  NSMutableArray *applications = [NSMutableArray arrayWithArray:[self applicationsInDock:dock height:height]];
  for (NSMutableDictionary *application in applications) {
    if (![name isEqual:applicationName(application)]) continue;
    [application setObject:value forKey:key];
    return [self storeApplications:applications inDock:dock height:height];
  }
  return NO;
}
- (BOOL)addApplication:(NSDictionary *)application atSlot:(NSInteger)slot height:(NSInteger)height
{
  if (![application isKindOfClass:[NSDictionary class]]) return NO;
  NSString *name = [application objectForKey:@"Name"], *command = [application objectForKey:@"Command"];
  if (slot < 1 || slot > 1024 || ![name isKindOfClass:[NSString class]] || ![name length] ||
      ![command isKindOfClass:[NSString class]] || ![command length] ||
      [name isEqualToString:@"Workspace.GNUstep"] || [name isEqualToString:@"Recycler.GNUstep"]) return NO;
  NSMutableDictionary *dock = propertyListCopy([self dock], NSPropertyListMutableContainers);
  NSMutableArray *applications = [NSMutableArray arrayWithArray:[self applicationsInDock:dock height:height]];
  NSString *position = [NSString stringWithFormat:@"0,%ld", (long)slot];
  for (NSDictionary *entry in applications)
    if ([name isEqual:applicationName(entry)] || ([entry isKindOfClass:[NSDictionary class]] &&
        [position isEqual:[entry objectForKey:@"Position"]])) return NO;
  NSMutableDictionary *entry = [[application mutableCopy] autorelease];
  [entry setObject:position forKey:@"Position"];
  [applications addObject:entry];
  return [self storeApplications:applications inDock:dock height:height];
}
- (BOOL)removeApplication:(NSString *)name height:(NSInteger)height
{
  if (![name isKindOfClass:[NSString class]] || ![name length]) return NO;
  if ([name isEqualToString:@"Workspace.GNUstep"] || [name isEqualToString:@"Recycler.GNUstep"]) return NO;
  NSMutableDictionary *dock = propertyListCopy([self dock], NSPropertyListMutableContainers);
  NSMutableArray *applications = [NSMutableArray arrayWithArray:[self applicationsInDock:dock height:height]];
  NSUInteger index = 0;
  for (NSDictionary *entry in applications) {
    if ([name isEqual:applicationName(entry)]) {
      if ([[entry objectForKey:@"Lock"] boolValue]) return NO;
      [applications removeObjectAtIndex:index];
      return [self storeApplications:applications inDock:dock height:height];
    }
    index++;
  }
  return NO;
}
- (BOOL)moveApplication:(NSString *)name toSlot:(NSInteger)slot height:(NSInteger)height
{
  if (slot < 1 || slot > 1024 || ![name isKindOfClass:[NSString class]] ||
      [name isEqualToString:@"Workspace.GNUstep"] || [name isEqualToString:@"Recycler.GNUstep"]) return NO;
  NSMutableDictionary *dock = propertyListCopy([self dock], NSPropertyListMutableContainers);
  NSArray *applications = [self applicationsInDock:dock height:height];
  NSMutableDictionary *source = nil, *destination = nil;
  NSString *position = [NSString stringWithFormat:@"0,%ld", (long)slot];
  for (NSMutableDictionary *entry in applications) {
    if (![entry isKindOfClass:[NSDictionary class]]) continue;
    if ([name isEqual:applicationName(entry)]) source = entry;
    if ([position isEqual:[entry objectForKey:@"Position"]]) destination = entry;
  }
  if (!source || ![[source objectForKey:@"Position"] isKindOfClass:[NSString class]] ||
      [[source objectForKey:@"Lock"] boolValue] ||
      [[destination objectForKey:@"Lock"] boolValue]) return NO;
  NSString *previous = [[source objectForKey:@"Position"] copy];
  if (destination) [destination setObject:previous forKey:@"Position"];
  [source setObject:position forKey:@"Position"];
  [previous release];
  return [self storeApplications:applications inDock:dock height:height];
}
- (NSDictionary *)iconYardPositionForApplication:(NSString *)name
{
  if (![name isKindOfClass:[NSString class]] || ![name length]) return nil;
  id positions = [self storedValue:@"WaylandIconYardPositions"];
  id point = [positions isKindOfClass:[NSDictionary class]] ? [positions objectForKey:name] : nil;
  if (![point isKindOfClass:[NSDictionary class]]) return nil;
  for (NSString *key in [NSArray arrayWithObjects:@"X", @"Y", nil]) {
    id value = [point objectForKey:key];
    if (![value isKindOfClass:[NSNumber class]] || !isfinite([value doubleValue]) ||
        fabs([value doubleValue]) > 1000000) return nil;
  }
  return point;
}
- (BOOL)setIconYardPosition:(NSPoint)point forApplication:(NSString *)name
{
  if (![name isKindOfClass:[NSString class]] || ![name length] || !isfinite(point.x) ||
      !isfinite(point.y) || fabs(point.x) > 1000000 || fabs(point.y) > 1000000) return NO;
  id stored = [self storedValue:@"WaylandIconYardPositions"];
  NSMutableDictionary *positions = [stored isKindOfClass:[NSDictionary class]] ?
    [[stored mutableCopy] autorelease] : [NSMutableDictionary dictionary];
  [positions setObject:[NSDictionary dictionaryWithObjectsAndKeys:[NSNumber numberWithDouble:point.x], @"X",
    [NSNumber numberWithDouble:point.y], @"Y", nil] forKey:name];
  return [self store:positions forKey:@"WaylandIconYardPositions"];
}
- (NSString *)iconPathForApplication:(NSString *)name
{
  if (![name isKindOfClass:[NSString class]] || ![name length]) return nil;
  id icons = [self storedValue:@"WaylandDockIcons"];
  id path = [icons isKindOfClass:[NSDictionary class]] ? [icons objectForKey:name] : nil;
  if (!path) {
    id attributes = [[NSDictionary dictionaryWithContentsOfFile:
      [_legacyDirectory stringByAppendingPathComponent:@"WMWindowAttributes.plist"]] objectForKey:name];
    if ([attributes isKindOfClass:[NSDictionary class]]) path = [attributes objectForKey:@"Icon"];
  }
  return [path isKindOfClass:[NSString class]] && [path length] ? path : nil;
}
- (BOOL)setIconPath:(NSString *)path forApplication:(NSString *)name
{
  if (![name isKindOfClass:[NSString class]] || ![name length] || (path && ![path isKindOfClass:[NSString class]])) return NO;
  id stored = [self storedValue:@"WaylandDockIcons"];
  NSMutableDictionary *icons = [stored isKindOfClass:[NSDictionary class]] ?
    [[stored mutableCopy] autorelease] : [NSMutableDictionary dictionary];
  [icons setObject:path ?: @"" forKey:name];
  return [self store:icons forKey:@"WaylandDockIcons"];
}
@end
