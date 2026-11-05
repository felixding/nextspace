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
#import "OSEMouse.h"
#import "OSEWaylandInput.h"
#import <AppKit/NSEvent.h>
#include <math.h>

#import <GNUstepGUI/GSDisplayServer.h>

NSString *OSEMouseAcceleration = @"MouseAcceleration";
NSString *OSEMouseWaylandAcceleration = @"WaylandPointerAcceleration";
NSString *OSEMouseWaylandProfile = @"WaylandPointerProfile";
NSString *OSEMouseThreshold = @"MouseThreshold";
NSString *OSEMouseDoubleClickTime = @"MouseDoubleClickTime";
NSString *OSEMouseWheelScroll = @"MouseWheelScroll";
NSString *OSEMouseWheelControlScroll = @"MouseWheelControlScroll";
NSString *OSEMouseMenuButtonEnabled = @"MenuButtonEnabled";
NSString *OSEMouseMenuButtonHand = @"MenuButtonHand";
NSString *OSEMouseCursorTheme = @"MouseCursorTheme";

@interface GSDisplayServer (NativeMouseGeometry)
- (NSRect)logicalDesktopBounds;
@end

@implementation OSEMouse

+ (void)configureWithDefaults:(OSEDefaults *)defaults
{
  OSEMouse *mouse = [self new];
  id speed = [defaults objectForKey:OSEMouseWaylandAcceleration];
  if (speed) [mouse setNormalizedAcceleration:[speed doubleValue]
    profile:[defaults integerForKey:OSEMouseWaylandProfile]];
  [mouse release];
}

+ (NSInteger)dragThreshold
{
  NSInteger value = [[NSUserDefaults standardUserDefaults] integerForKey:@"GSMouseMoveThreshold"];
  return value > 0 ? value : 3;
}
+ (NSTimeInterval)doubleClickInterval
{
  NSInteger value = [[NSUserDefaults standardUserDefaults] integerForKey:@"GSDoubleClickTime"];
  if (value <= 0) value = [[OSEDefaults globalUserDefaults] integerForKey:OSEMouseDoubleClickTime];
  return (value > 0 ? value : 300) / 1000.0;
}

- (id)init
{
  if (!(self = [super init])) return nil;
  gsDefaults = [NSUserDefaults standardUserDefaults];
  nxDefaults = [OSEDefaults globalUserDefaults];
  threshold = [self accelerationThreshold];
  doubleClickTime = [self doubleClickTime];
  wheelScrollLines = [self wheelScrollLines];
  isMenuButtonEnabled = [self isMenuButtonEnabled];
  menuButtonEvent = [self menuButton];
  [self saveToDefaults];
  return self;
}

- (BOOL)usesNativeInputSettings { return YES; }
- (double)normalizedAcceleration { return [[OSEWaylandInputSettings() objectForKey:@"speed"] doubleValue]; }
- (NSUInteger)accelerationProfile { return [[OSEWaylandInputSettings() objectForKey:@"profile"] unsignedIntegerValue]; }
- (BOOL)setNormalizedAcceleration:(double)speed profile:(NSUInteger)profile
{
  if (!isfinite(speed) || speed < -1 || speed > 1 || profile > 1) return NO;
  if (!OSEChangeWaylandInputSettings(@"pointer", [NSDictionary dictionaryWithObjectsAndKeys:
      [NSNumber numberWithDouble:speed], @"speed", [NSNumber numberWithUnsignedInteger:profile], @"profile", nil])) return NO;
  [nxDefaults setObject:[NSNumber numberWithDouble:speed] forKey:OSEMouseWaylandAcceleration];
  [nxDefaults setInteger:profile forKey:OSEMouseWaylandProfile];
  [nxDefaults synchronize];
  return YES;
}

// Acceleration
- (NSInteger)acceleration
{
  return 0; /* The native speed API uses libinput's normalized range. */
}
- (NSInteger)accelerationThreshold
{
  return [OSEMouse dragThreshold];
}
- (void)setAcceleration:(NSInteger)speed threshold:(NSInteger)pixels
{
  /* The ratio is a retained compatibility argument. Native pointer speed uses
     setNormalizedAcceleration:profile:; only the logical drag threshold changes. */
  if (pixels > 0) {
    threshold = pixels;
    [self _setGSDefaultsObject:[NSNumber numberWithInteger:pixels] forKey:@"GSMouseMoveThreshold"];
  }
}

// Double click
- (NSInteger)doubleClickTime
{
  NSInteger time;

  time = [gsDefaults integerForKey:@"GSDoubleClickTime"];
  if (time == 0)
    {
      time = [nxDefaults integerForKey:OSEMouseDoubleClickTime];
      if (time ==0 || time == -1)
        time = 300;
    }

  return time;
}
- (void)setDoubleClickTime:(NSUInteger)miliseconds
{
  doubleClickTime = miliseconds;
}

// Scroll wheel
- (NSInteger)wheelScrollLines
{
  NSInteger  lines;
  
  lines = [gsDefaults integerForKey:@"GSMouseScrollMultiplier"];
  if (lines == 0)
    {
      lines = [nxDefaults integerForKey:OSEMouseWheelScroll];
      if (lines == 0 || lines == -1)
        lines = 3;
    }
  
  return lines;
}
- (void)setWheelScrollLines:(NSInteger)lines
{
  wheelScrollLines = lines;
}
- (NSInteger)wheelControlScrollLines
{
  NSInteger  lines;
  
  lines = [nxDefaults integerForKey:OSEMouseWheelControlScroll];
  if (lines == 0 || lines == -1)
    lines = 1;
  
  return lines;
}
- (void)setWheelControlScrollLines:(NSInteger)lines
{
  wheelControlScrollLines = lines;
}

// Menu button
- (BOOL)isMenuButtonEnabled
{
  BOOL     enabled = YES;
  NSString *s;

  s = [gsDefaults objectForKey:@"GSMenuButtonEnabled"];
  if (s != nil)
    {
      enabled = [s isEqualToString:@"YES"];
    }
  else
    {
      s = [nxDefaults objectForKey:OSEMouseMenuButtonEnabled];
      if (s != nil)
        enabled = [s isEqualToString:@"YES"];
    }
 
  return enabled;
}
- (NSUInteger)menuButton
{
  NSInteger event = [gsDefaults integerForKey:@"GSMenuButtonEvent"];
  if (!event) event = [nxDefaults integerForKey:OSEMouseMenuButtonHand];
  return event == NSLeftMouseDown ? NSLeftMouseDown : NSRightMouseDown;
}
- (void)setMenuButtonEnabled:(BOOL)enabled
                  menuButton:(NSUInteger)eventType
{
  isMenuButtonEnabled = enabled;
  menuButtonEvent = eventType;
}

- (NSPoint)locationOnScreen
{
  NSPoint point = [NSEvent mouseLocation];
  NSRect bounds = [GSCurrentServer() respondsToSelector:@selector(logicalDesktopBounds)] ?
    [GSCurrentServer() logicalDesktopBounds] : NSZeroRect;
  point.y = NSMaxY(bounds) - point.y;
  return point;
}

// TODO
- (NSArray *)availableCursorThemes
{
  // NSArray 		*themePaths;
  // NSFileManager		*fm = [NSFileManager defaultManager];
  // NSEnumerator		*e;
  // NSMutableArray	*themes;

  // themePaths = [NSArray arrayWithObjects:@"/usr/share/icons", @"~/.icons"];

  return [NSArray arrayWithObjects:@"default", @"Adwaita", @"Bluecurve",
                  @"Bluecurve-inverse", @"LBluecurve", @"LBluecurve-inverse",
                  nil];
}

// TODO
- (NSString *)cursorTheme
{
  return [[[NSProcessInfo processInfo] environment] objectForKey:@"XCURSOR_THEME"] ?: @"default";
}

- (void)_setGSDefaultsObject:(id)object forKey:(NSString *)key
{
  NSMutableDictionary *globalDomain;
  
  globalDomain = [[gsDefaults persistentDomainForName:NSGlobalDomain] mutableCopy];
  if (!globalDomain) globalDomain = [NSMutableDictionary new];

  [globalDomain setObject:object forKey:key];
  [gsDefaults setPersistentDomain:globalDomain forName:NSGlobalDomain];
  [gsDefaults synchronize];
  
  [globalDomain release];
}

- (void)saveToDefaults
{
  BOOL sendNotification = NO;
  
  if (threshold != [gsDefaults integerForKey:@"GSMouseMoveThreshold"])
    {
      [self _setGSDefaultsObject:[NSNumber numberWithInteger:threshold]
                          forKey:@"GSMouseMoveThreshold"];
      sendNotification = YES;
    }
  
  // Double-Click Delay
  if (doubleClickTime != [gsDefaults integerForKey:@"GSDoubleClickTime"])
    {
      [self _setGSDefaultsObject:[NSNumber numberWithInteger:doubleClickTime]
                          forKey:@"GSDoubleClickTime"];
      sendNotification = YES;
    }
  if (doubleClickTime != [nxDefaults integerForKey:OSEMouseDoubleClickTime])
    {
      [nxDefaults setInteger:doubleClickTime forKey:OSEMouseDoubleClickTime];
    }

  // Mouse Wheel Scrolls
  if (wheelScrollLines != [gsDefaults integerForKey:@"GSMouseScrollMultiplier"])
    {
      [self _setGSDefaultsObject:[NSNumber numberWithInteger:wheelScrollLines]
                          forKey:@"GSMouseScrollMultiplier"];
      sendNotification = YES;
    }
  if (wheelScrollLines != [nxDefaults integerForKey:OSEMouseWheelScroll])
    {
      [nxDefaults setInteger:wheelScrollLines forKey:OSEMouseWheelScroll];
    }
  if (wheelControlScrollLines != [nxDefaults integerForKey:OSEMouseWheelControlScroll])
    {
      [nxDefaults setInteger:wheelControlScrollLines forKey:OSEMouseWheelControlScroll];
    }

  // Menu Button
  NSString *s = isMenuButtonEnabled ? @"YES" : @"NO";
  if (![[gsDefaults objectForKey:@"GSMenuButtonEnabled"] isEqualToString:s])
    {
      [self _setGSDefaultsObject:s forKey:@"GSMenuButtonEnabled"];
      sendNotification = YES;
    }
  if (menuButtonEvent != [gsDefaults integerForKey:@"GSMenuButtonEvent"])
    {
      [self _setGSDefaultsObject:[NSNumber numberWithInteger:menuButtonEvent]
                          forKey:@"GSMenuButtonEvent"];
      sendNotification = YES;
    }
  if (menuButtonEvent != [nxDefaults integerForKey:OSEMouseMenuButtonHand])
    {
      [nxDefaults setInteger:menuButtonEvent forKey:OSEMouseMenuButtonHand];
    }
  if (isMenuButtonEnabled != [nxDefaults boolForKey:OSEMouseMenuButtonEnabled])
    {
      [nxDefaults setBool:isMenuButtonEnabled forKey:OSEMouseMenuButtonEnabled];
    }

  // Notify GNUstep backend about mouse preferences change
  if (sendNotification == YES)
    {
      [[NSDistributedNotificationCenter defaultCenter]
               postNotificationName:@"GSMouseOptionsDidChangeNotification"
                             object:nil];
    }
}

@end
