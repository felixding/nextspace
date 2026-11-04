/* Verify the public clock-defaults tracking switch. GPL-2.0-or-later. */
#import <AppKit/AppKit.h>
#import <DesktopKit/NXTClockView.h>

@interface TrackingClock : NXTClockView
{
  NSUInteger notifications;
}
- (NSUInteger)notifications;
@end
@implementation TrackingClock
- (void)loadClockbitsForLanguage:(NSString *)language {}
- (void)defaultsChanged:(NSNotification *)notification { notifications++; }
- (NSUInteger)notifications { return notifications; }
@end

int main(void)
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  TrackingClock *clock = [[TrackingClock alloc] initWithFrame:NSMakeRect(0,0,64,64)];
  NSNotificationCenter *center = [NSNotificationCenter defaultCenter];
  [clock setTracksDefaultsDatabase:NO];
  NSUInteger initial = [clock notifications];
  [center postNotificationName:NSUserDefaultsDidChangeNotification object:nil];
  NSCAssert([clock notifications] == initial, @"Disabled clock must ignore local defaults changes");
  [clock setTracksDefaultsDatabase:YES];
  [center postNotificationName:NSUserDefaultsDidChangeNotification object:nil];
  NSCAssert([clock notifications] == initial+1, @"Enabled clock must observe defaults changes");
  [clock setTracksDefaultsDatabase:NO];
  [center postNotificationName:NSUserDefaultsDidChangeNotification object:nil];
  NSCAssert([clock notifications] == initial+1, @"Disabling tracking must remove the observer again");
  [clock release];
  [center postNotificationName:NSUserDefaultsDidChangeNotification object:nil];
  puts("{\"tracking_toggles\":3,\"observed\":1,\"ignored\":2,\"deallocation_safe\":true}");
  [pool drain]; return 0;
}
