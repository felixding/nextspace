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

#import "OSEWaylandDisplay.h"
#import "OSEDisplayModel.h"
#import <AppKit/AppKit.h>

@implementation OSEDisplay
+ (NSDictionary *)zeroResolution
{
  NSString *zeroSizeString = NSStringFromSize(NSMakeSize(0, 0));
  NSNumber *zeroRate = [NSNumber numberWithFloat:0.0];

  return [NSDictionary dictionaryWithObjectsAndKeys:zeroSizeString, OSEDisplayResolutionSizeKey, zeroRate,
                                                    OSEDisplayResolutionRateKey, nil];
}
- (CGFloat)scaleFactor { return [self scaleNumerator] / 120.0; }
- (BOOL)isSupportedResolution:(NSDictionary *)mode
{
  NSSize size = NSSizeFromString([mode objectForKey:OSEDisplayResolutionSizeKey]);
  if (NSEqualSizes(size, NSZeroSize)) return YES;
  return [[self allResolutions] containsObject:[self resolutionWithWidth:size.width height:size.height
    rate:[[mode objectForKey:OSEDisplayResolutionRateKey] doubleValue]]];
}

- (NSDictionary *)resolutionWithWidth:(CGFloat)width height:(CGFloat)height rate:(CGFloat)refresh
{
  NSDictionary *best = nil;
  for (NSDictionary *mode in [self allResolutions]) {
    NSSize size = NSSizeFromString([mode objectForKey:OSEDisplayResolutionSizeKey]);
    double rate = [[mode objectForKey:OSEDisplayResolutionRateKey] doubleValue];
    if (size.width != width || size.height != height) continue;
    if (refresh && (float)refresh == (float)rate) return mode;
    if (!refresh && (!best || rate > [[best objectForKey:OSEDisplayResolutionRateKey] doubleValue])) best = mode;
  }
  return best ?: [NSDictionary dictionaryWithObjectsAndKeys:NSStringFromSize(NSMakeSize(width, height)),
    OSEDisplayResolutionSizeKey, [NSNumber numberWithDouble:refresh], OSEDisplayResolutionRateKey, nil];
}

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
{ [(OSEScreen *)screen setDisplay:self resolution:mode position:position]; }
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
