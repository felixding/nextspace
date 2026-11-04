/* Native display model and session display service adapter.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import "OSEWaylandDisplay.h"
#import "OSEPower.h"
#import <AppKit/AppKit.h>
#import <GNUstepGUI/GSDisplayServer.h>
#include <math.h>

extern NSString *GSDisplayBackendName(void) __attribute__((weak));
extern NSString *GSSessionServiceName(NSString *) __attribute__((weak));
static id<OSESessionSettings> localSessionSettings, remoteSessionSettings;
static NSConnection *settingsConnection;

void OSERegisterSessionSettings(id<OSESessionSettings> service) { localSessionSettings = service; }
NSDictionary *OSERequestSessionSettings(NSDictionary *request)
{
  if (localSessionSettings) return OSESessionSettingsRequest(localSessionSettings, request);
  @try {
    if (!remoteSessionSettings) {
      NSString *name = GSSessionServiceName ? GSSessionServiceName(@"Workspace") : @"Workspace";
      settingsConnection = [[NSConnection connectionWithRegisteredName:name host:@""] retain];
      [settingsConnection setRequestTimeout:5]; [settingsConnection setReplyTimeout:5];
      remoteSessionSettings = [[(id)[settingsConnection rootProxy] delegate] retain];
    }
    NSDictionary *result = OSESessionSettingsRequest(remoteSessionSettings, request);
    if (result) return result;
  } @catch (NSException *exception) {}
  [remoteSessionSettings release]; remoteSessionSettings = nil;
  [settingsConnection release]; settingsConnection = nil;
  return nil;
}
BOOL OSEUsesWaylandDisplay(void)
{
  NSString *name = GSDisplayBackendName ? GSDisplayBackendName() :
    [[NSUserDefaults standardUserDefaults] stringForKey:@"GSBackend"];
  if (![name length]) name = [[[NSProcessInfo processInfo] environment] objectForKey:@"NEXTSPACE_GS_BACKEND"];
  return [name length] && [[name lowercaseString] rangeOfString:@"wayland"].location != NSNotFound;
}

static NSDictionary *resolution(NSDictionary *mode)
{
  return [NSDictionary dictionaryWithObjectsAndKeys:
    NSStringFromSize(NSMakeSize([[mode objectForKey:@"width"] intValue], [[mode objectForKey:@"height"] intValue])),
    OSEDisplayResolutionSizeKey, [NSNumber numberWithDouble:[[mode objectForKey:@"refresh"] doubleValue] / 1000],
    OSEDisplayResolutionRateKey, [NSString stringWithFormat:@"%dx%d",
      [[mode objectForKey:@"width"] intValue], [[mode objectForKey:@"height"] intValue]],
    OSEDisplayResolutionNameKey, nil];
}
static NSSize logicalSize(NSDictionary *mode, NSUInteger scale, NSUInteger transform)
{
  NSSize size = NSSizeFromString([mode objectForKey:OSEDisplayResolutionSizeKey]);
  if (transform & 1) size = NSMakeSize(size.height, size.width);
  if (!scale) return NSZeroSize;
  return NSMakeSize(floor(size.width * 120 / scale), floor(size.height * 120 / scale));
}
static NSArray *hardwareIdentity(NSDictionary *head, BOOL connector)
{
  return [NSArray arrayWithObjects:[head objectForKey:@"make"] ?: @"", [head objectForKey:@"model"] ?: @"",
    [head objectForKey:@"serial"] ?: @"", connector ? ([head objectForKey:@"name"] ?: @"") : @"", nil];
}

static NSDictionary *nativeGammaSettings(NSDictionary *description)
{
  if (![description isKindOfClass:[NSDictionary class]]) return nil;
  NSArray *legacy = [NSArray arrayWithObjects:OSEDisplayGammaRedKey, OSEDisplayGammaGreenKey,
    OSEDisplayGammaBlueKey, OSEDisplayGammaBrightnessKey, nil];
  NSArray *keys = [NSArray arrayWithObjects:@"red", @"green", @"blue", @"brightness", nil];
  NSMutableDictionary *settings = [NSMutableDictionary dictionary];
  for (NSUInteger i = 0; i < [keys count]; i++) {
    id value = [description objectForKey:[legacy objectAtIndex:i]];
    double number;
    if ([value isKindOfClass:[NSNumber class]]) number = [value doubleValue];
    else if ([value isKindOfClass:[NSString class]]) {
      NSScanner *scanner = [NSScanner scannerWithString:value];
      if (![scanner scanDouble:&number] || ![scanner isAtEnd]) return nil;
    } else return nil;
    if (i < 3 && number == 0) number = 1; /* Existing SystemKit convention. */
    if (!isfinite(number) || number < (i == 3 ? 0 : 0.1) || number > (i == 3 ? 2 : 10)) return nil;
    [settings setObject:[NSNumber numberWithDouble:number] forKey:[keys objectAtIndex:i]];
  }
  return settings;
}

@implementation OSEWaylandDisplay
- (id)initWithDescriptor:(NSDictionary *)descriptor screen:(OSEScreen *)owner duplicateIdentity:(BOOL)duplicate
{
  if (!(self = [super init])) return nil;
  screen = owner;
  _descriptor = [descriptor copy];
  BOOL connector = duplicate || ![[descriptor objectForKey:@"serial"] length];
  _identity = [[NSPropertyListSerialization dataWithPropertyList:hardwareIdentity(descriptor, connector)
    format:NSPropertyListBinaryFormat_v1_0 options:0 error:NULL] retain];
  _logicalFrame = NSMakeRect([[descriptor objectForKey:@"x"] intValue], [[descriptor objectForKey:@"y"] intValue],
    [[descriptor objectForKey:@"logical_width"] intValue], [[descriptor objectForKey:@"logical_height"] intValue]);
  _hiddenLogicalFrame = _logicalFrame;
  if (![self isActive]) {
    NSDictionary *mode = [self modePixelSize].width > 0 ? resolution(_descriptor) : [self bestResolution];
    _hiddenLogicalFrame.size = logicalSize(mode, [self scaleNumerator] ?: 120, [self transform]);
    _logicalFrame = NSZeroRect;
  }
  return self;
}
- (void)dealloc { [_descriptor release]; [_identity release]; [super dealloc]; }
- (NSDictionary *)descriptor { return _descriptor; }
- (NSString *)outputName { return [_descriptor objectForKey:@"name"]; }
- (NSSize)physicalSize
{ return NSMakeSize([[_descriptor objectForKey:@"width_mm"] intValue], [[_descriptor objectForKey:@"height_mm"] intValue]); }
- (BOOL)isBuiltin
{
  NSString *name = [self outputName];
  return [name hasPrefix:@"eDP"] || [name hasPrefix:@"LVDS"] || [name hasPrefix:@"DSI"];
}
- (NSArray *)allResolutions
{
  NSMutableArray *result = [NSMutableArray array];
  for (NSDictionary *mode in [_descriptor objectForKey:@"modes"]) [result addObject:resolution(mode)];
  return result;
}
- (NSDictionary *)bestResolution
{
  for (NSDictionary *mode in [_descriptor objectForKey:@"modes"])
    if ([[mode objectForKey:@"preferred"] boolValue]) return resolution(mode);
  NSArray *modes = [self allResolutions];
  return [modes count] ? [modes objectAtIndex:0] : [OSEDisplay zeroResolution];
}
- (NSDictionary *)activeResolution
{ return [self isActive] ? resolution(_descriptor) : [OSEDisplay zeroResolution]; }
- (CGFloat)activeRate { return [[_descriptor objectForKey:@"refresh"] doubleValue] / 1000; }
- (NSPoint)activePosition { return _logicalFrame.origin; }
- (NSRect)frame { return _logicalFrame; }
- (void)setFrame:(NSRect)frame { _logicalFrame = frame; }
- (NSRect)hiddenFrame { return _hiddenLogicalFrame; }
- (void)setHiddenFrame:(NSRect)frame { _hiddenLogicalFrame = frame; }
- (BOOL)isConnected { return YES; }
- (BOOL)isActive { return [[_descriptor objectForKey:@"enabled"] boolValue]; }
- (BOOL)isMain { return [[_descriptor objectForKey:@"primary"] boolValue]; }
- (void)setActive:(BOOL)enabled
{ if (enabled) [screen activateDisplay:self]; else [screen deactivateDisplay:self]; }
- (void)setMain:(BOOL)primary { if (primary) [screen setMainDisplay:self]; }
- (void)setResolution:(NSDictionary *)mode position:(NSPoint)position
{ [(OSEWaylandScreen *)screen setDisplay:self resolution:mode position:position]; }
- (NSSize)modePixelSize
{ return NSMakeSize([[_descriptor objectForKey:@"width"] intValue], [[_descriptor objectForKey:@"height"] intValue]); }
- (NSUInteger)scaleNumerator { return [[_descriptor objectForKey:@"scale"] unsignedIntegerValue]; }
- (NSUInteger)transform { return [[_descriptor objectForKey:@"transform"] unsignedIntegerValue]; }
- (CGFloat)dpi
{ return [self physicalSize].width > 0 ? [self modePixelSize].width * 25.4 / [self physicalSize].width : 0; }
- (id)uniqueID { return _identity; }
- (NSDictionary *)properties { return _descriptor; }
- (void)parseProperties {}
- (BOOL)isGammaSupported { return [self isActive] && [[_descriptor objectForKey:@"gamma_size"] unsignedIntegerValue] >= 2; }
- (void)_getGamma
{
  NSDictionary *gamma = [_descriptor objectForKey:@"gamma"];
  gammaValue.red = gamma ? [[gamma objectForKey:@"red"] doubleValue] : 1;
  gammaValue.green = gamma ? [[gamma objectForKey:@"green"] doubleValue] : 1;
  gammaValue.blue = gamma ? [[gamma objectForKey:@"blue"] doubleValue] : 1;
  gammaBrightness = gamma ? [[gamma objectForKey:@"brightness"] doubleValue] : 1;
}
- (CGFloat)gamma { [self _getGamma]; return (gammaValue.red + gammaValue.green + gammaValue.blue) / 3; }
- (CGFloat)gammaBrightness { [self _getGamma]; return gammaBrightness; }
- (NSDictionary *)gammaDescription
{
  [self _getGamma];
  return [NSDictionary dictionaryWithObjectsAndKeys:
    [NSString stringWithFormat:@"%.9g", gammaValue.red], OSEDisplayGammaRedKey,
    [NSString stringWithFormat:@"%.9g", gammaValue.green], OSEDisplayGammaGreenKey,
    [NSString stringWithFormat:@"%.9g", gammaValue.blue], OSEDisplayGammaBlueKey,
    [NSString stringWithFormat:@"%.9g", gammaBrightness], OSEDisplayGammaBrightnessKey, nil];
}
- (BOOL)applyGammaDescription:(NSDictionary *)description
{
  NSDictionary *settings = nativeGammaSettings(description);
  if (![NSThread isMainThread] || ![self isGammaSupported] || !settings) return NO;
  NSDictionary *result = OSERequestSessionSettings([NSDictionary dictionaryWithObjectsAndKeys:
    @"gamma", @"action", [_descriptor objectForKey:@"id"], @"id", settings, @"settings", nil]);
  if (![[result objectForKey:@"success"] boolValue] || ![result objectForKey:@"gamma"]) return NO;
  NSMutableDictionary *descriptor = [[_descriptor mutableCopy] autorelease];
  [descriptor setObject:[result objectForKey:@"gamma"] forKey:@"gamma"];
  [_descriptor release]; _descriptor = [descriptor copy];
  [self _getGamma];
  return YES;
}
- (void)setGammaFromDescription:(NSDictionary *)description
{
  if (![NSThread isMainThread]) {
    [self performSelectorOnMainThread:@selector(setGammaFromDescription:) withObject:description waitUntilDone:YES];
    return;
  }
  [self applyGammaDescription:description];
}
- (void)changeGamma:(NSDictionary *)change
{
  if (![NSThread isMainThread]) {
    [self performSelectorOnMainThread:@selector(changeGamma:) withObject:change waitUntilDone:YES]; return;
  }
  NSMutableDictionary *description = [[[self gammaDescription] mutableCopy] autorelease];
  [description addEntriesFromDictionary:change];
  [self applyGammaDescription:description];
}
- (void)setGammaRed:(CGFloat)r green:(CGFloat)g blue:(CGFloat)b brightness:(CGFloat)brightness
{
  [self changeGamma:[NSDictionary dictionaryWithObjectsAndKeys:
    [NSNumber numberWithDouble:r], OSEDisplayGammaRedKey, [NSNumber numberWithDouble:g], OSEDisplayGammaGreenKey,
    [NSNumber numberWithDouble:b], OSEDisplayGammaBlueKey,
    [NSNumber numberWithDouble:brightness], OSEDisplayGammaBrightnessKey, nil]];
}
- (void)setGamma:(CGFloat)value brightness:(CGFloat)brightness
{ [self setGammaRed:value green:value blue:value brightness:brightness]; }
- (void)setGamma:(CGFloat)value
{
  NSNumber *number = [NSNumber numberWithDouble:value];
  [self changeGamma:[NSDictionary dictionaryWithObjectsAndKeys:number, OSEDisplayGammaRedKey,
    number, OSEDisplayGammaGreenKey, number, OSEDisplayGammaBlueKey, nil]];
}
- (void)setGammaBrightness:(CGFloat)value
{ [self changeGamma:[NSDictionary dictionaryWithObject:[NSNumber numberWithDouble:value] forKey:OSEDisplayGammaBrightnessKey]]; }
- (void)fadeWithSettings:(NSDictionary *)settings
{
  if (![NSThread isMainThread]) {
    [self performSelectorOnMainThread:@selector(fadeWithSettings:) withObject:settings waitUntilDone:YES]; return;
  }
  double seconds = [[settings objectForKey:@"seconds"] doubleValue];
  double brightness = [[settings objectForKey:@"brightness"] doubleValue];
  BOOL normal = [[settings objectForKey:@"normal"] boolValue];
  if (![self isGammaSupported] || !isfinite(seconds) || seconds < 0 || seconds > 60 ||
      !isfinite(brightness) || brightness < 0 || brightness > 2) return;
  NSUInteger steps = MAX(1, ceil(seconds / 0.03));
  NSDate *start = [NSDate date];
  for (NSUInteger i = 0; i <= steps; i++) {
    [self setGammaBrightness:brightness * (normal ? (double)i / steps : 1 - (double)i / steps)];
    if (i < steps) [[NSRunLoop currentRunLoop] runUntilDate:[start dateByAddingTimeInterval:seconds * (i + 1) / steps]];
  }
}
- (void)fadeToBlack:(CGFloat)value { [self fadeTo:0 interval:0.3 brightness:value]; }
- (void)fadeToNormal:(CGFloat)value { [self fadeTo:1 interval:0.5 brightness:value]; }
- (void)fadeTo:(NSInteger)mode interval:(CGFloat)seconds brightness:(CGFloat)brightness
{
  [self fadeWithSettings:[NSDictionary dictionaryWithObjectsAndKeys:[NSNumber numberWithBool:mode != 0], @"normal",
    [NSNumber numberWithDouble:seconds], @"seconds", [NSNumber numberWithDouble:brightness], @"brightness", nil]];
}
@end

@interface OSEScreen (ModelInitialization)
- (id)initDisplayModel;
@end
@interface GSDisplayServer (NativeDisplayModel)
- (NSArray *)nativeOutputDescriptions;
@end

@implementation OSEWaylandScreen
- (id)init
{
  if (!(self = [super initDisplayModel])) return nil;
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
  [_state release]; [_transaction release];
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
    OSEWaylandDisplay *display = [[OSEWaylandDisplay alloc] initWithDescriptor:head screen:self
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
      resolution([(OSEWaylandDisplay *)display descriptor]) : [display bestResolution];
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
    OSEWaylandDisplay *display = (OSEWaylandDisplay *)[self displayWithID:identity];
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
    for (OSEWaylandDisplay *display in gammaDisplays)
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
