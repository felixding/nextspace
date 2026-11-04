/* Exercise the real DesktopKit alert layout and modal default action. MIT. */
#import <AppKit/AppKit.h>
#import <DesktopKit/NXTAlert.h>

@interface NXTAlert (ProbeLayout)
- (void)sizeToFitScreen;
@end

@interface AlertProbe : NSObject
@end
@implementation AlertProbe
- (void)applicationDidFinishLaunching:(NSNotification *)notification
{
  [self performSelector:@selector(runAlerts) withObject:nil afterDelay:0];
}
- (void)runAlerts
{
  if ([[[NSProcessInfo processInfo] arguments] containsObject:@"--power-layout"]) {
    NXTAlert *alert = [[NXTAlert alloc] initWithTitle:@"Log Out"
      message:@"Do you really want to log out?" defaultButton:@"Log out"
      alternateButton:@"Power off" otherButton:@"Cancel"];
    [alert sizeToFitScreen];
    NSMutableArray *buttons = [NSMutableArray array];
    for (NSView *view in [[[alert panel] contentView] subviews]) if ([view isKindOfClass:[NSButton class]]) {
      NSRect rect = [view convertRect:[view bounds] toView:nil];
      [buttons addObject:@{@"title": [(NSButton *)view title], @"x": @(NSMidX(rect)), @"y": @(NSMidY(rect)),
        @"width": @(rect.size.width), @"height": @(rect.size.height)}];
    }
    NSRect frame = [[alert panel] frame];
    NSData *data = [NSJSONSerialization dataWithJSONObject:@{@"buttons":buttons,
      @"width":@(frame.size.width), @"height":@(frame.size.height)} options:0 error:NULL];
    if (!data || [buttons count]!=3) exit(1);
    fwrite([data bytes],1,[data length],stdout); putchar('\n'); fflush(stdout);
    [alert release]; return;
  }
  for (NSUInteger index = 0; index < 2; index++) {
    NXTAlert *alert = [[NXTAlert alloc] initWithTitle:@"Alert keyboard test"
      message:@"Check cancellation and the default action." defaultButton:@"Continue"
      alternateButton:@"Cancel" otherButton:nil];
    NSButtonCell *cell = [[alert panel] defaultButtonCell];
    if (!cell || ![[cell title] isEqual:@"Continue"] || ![[cell keyEquivalent] isEqual:@"\r"] ||
        [cell keyEquivalentModifierMask] != 0) {
      fprintf(stderr, "AlertProbe: the loaded alert has no usable default action.\n");
      exit(1);
    }
    [alert sizeToFitScreen];
    NSPoint cancel = NSZeroPoint;
    for (NSView *view in [[[alert panel] contentView] subviews]) {
      if ([view isKindOfClass:[NSButton class]] && [[(NSButton *)view title] isEqual:@"Cancel"])
        cancel = [view convertPoint:NSMakePoint(NSMidX([view bounds]), NSMidY([view bounds])) toView:nil];
    }
    printf("{\"event\":\"alert\",\"index\":%lu,\"window\":%ld,\"cancel_x\":%.1f,\"cancel_y\":%.1f}\n",
      (unsigned long)index, (long)[[alert panel] windowNumber], cancel.x, cancel.y); fflush(stdout);
    NSInteger result = [alert runModal];
    if (result != (index == 0 ? NSAlertAlternateReturn : NSAlertDefaultReturn)) {
      fprintf(stderr, "AlertProbe: unexpected modal response %ld.\n", (long)result);
      exit(1);
    }
    [alert release];
  }
  puts("{\"event\":\"passed\",\"checks\":[\"loaded default action\",\"pointer cancellation\",\"Return after cancellation\"]}");
  fflush(stdout);
  [NSApp stop:self];
}
@end

int main(int argc, char **argv)
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  NSApplication *app = [NSApplication sharedApplication];
  AlertProbe *delegate = [AlertProbe new];
  [app setDelegate:delegate];
  if ([[[NSProcessInfo processInfo] arguments] containsObject:@"--power-layout"]) [delegate runAlerts];
  else [app run];
  [delegate release]; [pool drain]; return 0;
}
