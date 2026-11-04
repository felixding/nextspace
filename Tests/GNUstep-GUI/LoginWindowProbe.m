/* Exercise the production Login window with public AppKit operations.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import <AppKit/AppKit.h>
#import "LoginWindow.h"

static NSArray *rectValues(NSRect r)
{
  return [NSArray arrayWithObjects:[NSNumber numberWithDouble:r.origin.x],
    [NSNumber numberWithDouble:r.origin.y], [NSNumber numberWithDouble:r.size.width],
    [NSNumber numberWithDouble:r.size.height], nil];
}

@interface LoginWindowProbe : NSObject
{
  LoginWindow *window;
  NSView *content;
  NSTextField *field;
  NSString *commands;
  NSInteger lastSequence;
  BOOL performing;
}
- (void)report:(NSString *)event sequence:(NSInteger)sequence before:(NSDictionary *)before;
- (void)command:(NSTimer *)timer;
@end

@implementation LoginWindowProbe
- (void)applicationDidFinishLaunching:(NSNotification *)notification
{
  commands = [[[[NSProcessInfo processInfo] environment] objectForKey:@"LOGIN_WINDOW_COMMANDS"] copy];
  window = [[LoginWindow alloc] initWithContentRect:NSMakeRect(100, 100, 400, 240)
    styleMask:NSTitledWindowMask backing:NSBackingStoreBuffered defer:NO];
  [window setTitle:@"LoginWindowProbe"];
  [window setReleasedWhenClosed:NO];
  content = [window contentView];
  [content setAutoresizesSubviews:YES];
  NSString *imagePath = [[[NSProcessInfo processInfo] environment] objectForKey:@"LOGIN_WINDOW_IMAGE"];
  NSImage *image = [[NSImage alloc] initWithContentsOfFile:imagePath];
  NSImageView *background = [[NSImageView alloc] initWithFrame:[content bounds]];
  [background setImage:image];
  [background setImageScaling:NSScaleNone];
  [content addSubview:background];
  [image release]; [background release];
  field = [[NSTextField alloc] initWithFrame:NSMakeRect(100, 80, 200, 24)];
  [field setStringValue:@"Synthetic Login panel"];
  [field setAutoresizingMask:NSViewMinXMargin | NSViewMaxXMargin];
  [content addSubview:field];
  [window center];
  [window makeKeyAndOrderFront:nil];
  [NSTimer scheduledTimerWithTimeInterval:0.02 target:self selector:@selector(command:)
    userInfo:nil repeats:YES];
  [self report:@"ready" sequence:0 before:nil];
}
- (void)report:(NSString *)event sequence:(NSInteger)sequence before:(NSDictionary *)before
{
  NSMutableDictionary *row = [NSMutableDictionary dictionaryWithObjectsAndKeys:
    event, @"event", [NSNumber numberWithInteger:sequence], @"sequence", rectValues([window frame]), @"frame",
    rectValues([content bounds]), @"bounds", rectValues([field frame]), @"field",
    rectValues([[window screen] frame]), @"screen", [NSNumber numberWithDouble:[window backingScaleFactor]], @"scale",
    [NSNumber numberWithBool:[content autoresizesSubviews]], @"autoresizes",
    [NSNumber numberWithUnsignedInteger:[window styleMask]], @"style",
    [NSNumber numberWithInteger:[window windowNumber]], @"number", nil];
  if (before) [row setObject:before forKey:@"before"];
  NSData *json = [NSJSONSerialization dataWithJSONObject:row options:0 error:NULL];
  fwrite([json bytes], 1, [json length], stdout); putchar('\n'); fflush(stdout);
}
- (void)command:(NSTimer *)timer
{
  if (performing) return;
  NSData *data = [NSData dataWithContentsOfFile:commands];
  if (!data) return;
  NSDictionary *command = [NSJSONSerialization JSONObjectWithData:data options:0 error:NULL];
  NSInteger sequence = [[command objectForKey:@"sequence"] integerValue];
  if (sequence <= lastSequence) {
    [self report:@"state" sequence:lastSequence before:nil];
    return;
  }
  lastSequence = sequence;
  performing = YES;
  NSString *action = [command objectForKey:@"action"];
  NSDictionary *before = [NSDictionary dictionaryWithObjectsAndKeys:rectValues([window frame]), @"frame",
    rectValues([content bounds]), @"bounds", rectValues([field frame]), @"field", nil];
  if ([action isEqual:@"center"]) [window center];
  else if ([action isEqual:@"shake"]) [window shakePanel];
  else if ([action isEqual:@"shrink"]) [window shrinkPanel];
  else if ([action isEqual:@"quit"]) { [NSApp stop:nil]; return; }
  [window displayIfNeeded];
  [self report:action sequence:sequence before:before];
  performing = NO;
}
@end

int main(void)
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  [NSApplication sharedApplication];
  LoginWindowProbe *probe = [LoginWindowProbe new];
  [NSApp setDelegate:probe]; [NSApp run];
  [probe release]; [pool drain]; return 0;
}
