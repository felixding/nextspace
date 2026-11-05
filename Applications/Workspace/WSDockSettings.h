/* Native Dock preferences, importing the existing user configuration.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import <Foundation/Foundation.h>

@interface WSDockSettings : NSObject
{
  NSUserDefaults *_defaults;
  NSString *_domain;
  NSString *_legacyDirectory;
}
+ (NSString *)legacyDirectory;
- (id)initWithDefaults:(NSUserDefaults *)defaults domain:(NSString *)domain
      legacyDirectory:(NSString *)directory;
- (NSDictionary *)dock;
- (NSTimeInterval)delayForRaising:(BOOL)raising;
- (NSArray *)windowInsetsWithDock:(BOOL)dockVisible iconYard:(BOOL)yardVisible;
- (NSUInteger)maximizedDragMode;
- (NSDictionary *)titleAppearance;
- (NSArray *)applicationsForHeight:(NSInteger)height;
- (BOOL)setDockLevel:(NSInteger)level;
- (BOOL)setDockValue:(NSString *)value forKey:(NSString *)key;
- (BOOL)setValue:(NSString *)value forKey:(NSString *)key application:(NSString *)name height:(NSInteger)height;
- (BOOL)addApplication:(NSDictionary *)application atSlot:(NSInteger)slot height:(NSInteger)height;
- (BOOL)removeApplication:(NSString *)name height:(NSInteger)height;
- (BOOL)moveApplication:(NSString *)name toSlot:(NSInteger)slot height:(NSInteger)height;
- (NSDictionary *)iconYardPositionForApplication:(NSString *)name;
- (BOOL)setIconYardPosition:(NSPoint)point forApplication:(NSString *)name;
- (NSString *)iconPathForApplication:(NSString *)name;
- (BOOL)setIconPath:(NSString *)path forApplication:(NSString *)name;
@end
