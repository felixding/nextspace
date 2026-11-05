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

/*
  Class:		OSEMouse
  Inherits from:	NSObject
  Class descritopn:	Mouse configuration manipulation (speed, 
			double click time, cursor themes)
*/

#import <Foundation/Foundation.h>

@class OSEDefaults;

@interface OSEMouse : NSObject
{
  NSUserDefaults *gsDefaults;
  OSEDefaults *nxDefaults;

  NSInteger	threshold;
  NSInteger	doubleClickTime;
  NSInteger	wheelScrollLines;
  NSInteger	wheelControlScrollLines;
  BOOL		isMenuButtonEnabled;
  NSInteger	menuButtonEvent;
}

// Logical interaction settings for toolkit views; no native input mutation.
+ (NSInteger)dragThreshold;
+ (NSTimeInterval)doubleClickInterval;
+ (void)configureWithDefaults:(OSEDefaults *)defaults;

/* Native pointer speed uses libinput's normalized -1..1 range. The retained
   ratio argument affects no device; setAcceleration:threshold: changes only
   the logical toolkit drag threshold. */
- (BOOL)usesNativeInputSettings;
- (double)normalizedAcceleration;
- (NSUInteger)accelerationProfile;
- (BOOL)setNormalizedAcceleration:(double)speed profile:(NSUInteger)profile;
- (NSInteger)acceleration;
- (NSInteger)accelerationThreshold;
- (void)setAcceleration:(NSInteger)speed threshold:(NSInteger)pixels;

- (NSInteger)doubleClickTime;
- (void)setDoubleClickTime:(NSUInteger)miliseconds;

- (NSInteger)wheelScrollLines;
- (void)setWheelScrollLines:(NSInteger)lines;
- (NSInteger)wheelControlScrollLines;
- (void)setWheelControlScrollLines:(NSInteger)lines;

- (BOOL)isMenuButtonEnabled;
- (NSUInteger)menuButton;
- (void)setMenuButtonEnabled:(BOOL)enabled
                  menuButton:(NSUInteger)eventType;

- (NSPoint)locationOnScreen;
  
- (NSArray *)availableCursorThemes;
- (NSString *)cursorTheme;

- (void)saveToDefaults;

@end

extern NSString *OSEMouseAcceleration;
extern NSString *OSEMouseWaylandAcceleration;
extern NSString *OSEMouseWaylandProfile;
extern NSString *OSEMouseThreshold;
extern NSString *OSEMouseDoubleClickTime;
extern NSString *OSEMouseWheelScroll;
extern NSString *OSEMouseWheelControlScroll;
extern NSString *OSEMouseMenuButtonEnabled;
extern NSString *OSEMouseMenuButtonHand;
extern NSString *OSEMouseCursorTheme;
