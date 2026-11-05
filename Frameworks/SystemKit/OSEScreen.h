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

/* Display modes are physical pixels. Frames and desktop bounds are logical
   coordinates. Backend handles are private to the selected implementation. */
#import <Foundation/Foundation.h>
@class OSEDisplay, OSEPower;

@interface OSEScreen : NSObject
{
 @protected
  BOOL useAutosave;
  NSMutableArray *systemDisplays;
  NSSize sizeInPixels, sizeInMilimeters;
  OSEPower *_systemPower;
 @private
  NSDictionary *_state;
  NSString *_transaction;
  BOOL _refreshing;
}

@property (readonly) OSEPower *systemPower;

+ (id)sharedScreen;
- (void)setUseAutosave:(BOOL)yn;

- (BOOL)isLidClosed;

- (void)refreshDisplays;
- (NSRect)logicalBounds;
- (BOOL)isNativeDisplay;
- (BOOL)supportsDisplayConfiguration;
- (BOOL)supportsDisplayTransactions;
/* Native preview/confirmation. The returned result uses OSESessionSettings's
   status values; timeout and settings-process failure are compositor owned. */
- (NSDictionary *)testDisplayLayout:(NSArray *)layout;
- (NSDictionary *)beginDisplayLayout:(NSArray *)layout timeout:(NSUInteger)milliseconds;
- (NSDictionary *)displayLayoutStatus;
- (BOOL)confirmDisplayLayout;
- (BOOL)cancelDisplayLayout;

/* Compatibility virtual-screen extent; native callers use logicalBounds.
   Per-display physical dimensions are OSEDisplay.modePixelSize. */
- (NSSize)sizeInPixels;
- (NSSize)sizeInMilimeters;
- (NSUInteger)colorDepth;

/** Returns color saved in defaults with key NXDesktopBackgroundBolor */
- (BOOL)savedBackgroundColorRed:(CGFloat *)redComponent
                          green:(CGFloat *)greenComponent
                           blue:(CGFloat *)blueComponent;
/** Returns current color of root window. On failure returns saved color. */
- (BOOL)backgroundColorRed:(CGFloat *)redComponent
                     green:(CGFloat *)greenComponent
                      blue:(CGFloat *)blueComponent;
- (BOOL)setBackgroundColorRed:(CGFloat)redComponent
                        green:(CGFloat)greenComponent
                         blue:(CGFloat)blueComponent;
 
- (NSArray *)allDisplays;
- (NSArray *)activeDisplays;
- (NSArray *)connectedDisplays;

- (OSEDisplay *)mainDisplay;
- (void)setMainDisplay:(OSEDisplay *)display;

- (OSEDisplay *)displayAtPoint:(NSPoint)point;
- (OSEDisplay *)displayWithMouseCursor;
- (OSEDisplay *)displayWithName:(NSString *)name;
- (OSEDisplay *)displayWithID:(id)uniqueID;

- (void)activateDisplay:(OSEDisplay *)display;
- (void)deactivateDisplay:(OSEDisplay *)display;
- (void)setDisplay:(OSEDisplay *)display resolution:(NSDictionary *)resolution;

- (NSArray *)defaultLayout:(BOOL)arrange;
- (NSArray *)currentLayout;
- (BOOL)validateLayout:(NSArray *)layout;
- (BOOL)applyDisplayLayout:(NSArray *)layout;
- (BOOL)saveCurrentDisplayLayout;
- (NSArray *)savedDisplayLayout;
- (BOOL)applySavedDisplayLayout;
- (NSDictionary *)descriptionOfDisplay:(OSEDisplay *)display
                              inLayout:(NSArray *)layout;
- (id)objectForKey:(NSString *)key
        forDisplay:(OSEDisplay *)display
          inLayout:(NSArray *)layout;

- (NSArray *)arrangedDisplayLayout;

@end

// NXGlobalDefaults desktop background key
extern NSString *OSEDesktopBackgroundColor;

// Displays.config user path
#define DISPLAYS_CONFIG @"~/Library/Preferences/Displays.config"
#define LAYOUTS_DIR     @"~/Library/Preferences/.NextSpace"

// Displays.config field keys
extern NSString *OSEDisplayIsActiveKey;
extern NSString *OSEDisplayIsMainKey;
extern NSString *OSEDisplayGammaKey;
extern NSString *OSEDisplayGammaRedKey;
extern NSString *OSEDisplayGammaGreenKey;
extern NSString *OSEDisplayGammaBlueKey;
extern NSString *OSEDisplayGammaBrightnessKey;
extern NSString *OSEDisplayIDKey;
extern NSString *OSEDisplayNameKey;
extern NSString *OSEDisplayFrameKey;
extern NSString *OSEDisplayHiddenFrameKey;
extern NSString *OSEDisplayFrameRateKey;
extern NSString *OSEDisplayResolutionNameKey;
extern NSString *OSEDisplayResolutionSizeKey;
extern NSString *OSEDisplayResolutionRateKey;
extern NSString *OSEDisplayPhSizeKey;
extern NSString *OSEDisplayPropertiesKey;
extern NSString *OSEDisplayModeKey;
extern NSString *OSEDisplayScaleKey;
extern NSString *OSEDisplayTransformKey;

// Notifications
extern NSString *OSEScreenDidChangeNotification;
extern NSString *OSEScreenDidUpdateNotification;
