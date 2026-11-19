/* Exercise original NSMenu placement and tracking without a browser adapter. */
#import <AppKit/AppKit.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

@interface NSMenu (PlacementProbe)
- (void)setMain:(BOOL)flag;
- (void)shiftOnScreen;
@end

@interface MenuPlacementMenu : NSMenu
@end
@implementation MenuPlacementMenu
- (void)close
{
  if (getenv("NEXTSPACE_MENU_TRACE_CLOSE"))
    fprintf(stderr,"native menu close: %s\n",[[[NSThread callStackSymbols] description] UTF8String]);
  [super close];
}
- (void)shiftOnScreen
{
  NSWindow *window = [self window];
  NSPoint pointer = [window convertBaseToScreen:[window mouseLocationOutsideOfEventStream]];
  fprintf(stderr, "native shift before: pointer=%s frame=%s screen=%s work=%s\n",
    [NSStringFromPoint(pointer) UTF8String], [NSStringFromRect([window frame]) UTF8String],
    [NSStringFromRect([[window screen] frame]) UTF8String],
    [NSStringFromRect([[window screen] visibleFrame]) UTF8String]);
  [super shiftOnScreen];
  fprintf(stderr, "native shift after: frame=%s\n", [NSStringFromRect([window frame]) UTF8String]);
}
@end

@interface MenuPlacementTarget : NSObject
{
@public NSInteger actions, last;
}
- (void)invoke:(id)sender;
@end
@implementation MenuPlacementTarget
- (void)invoke:(id)sender { actions++; last = [sender tag]; }
@end

static NSArray *rectangle(NSRect r)
{ return @[@(r.origin.x), @(r.origin.y), @(r.size.width), @(r.size.height)]; }

static void report(NSMenu *menu, MenuPlacementTarget *target)
{
  NSWindow *window = [menu window];
  NSRect frame = [window frame];
  NSMenuView *view = [menu menuRepresentation];
  NSMutableArray *items = [NSMutableArray array], *screens = [NSMutableArray array];
  for (NSInteger index = 0; index < [menu numberOfItems]; index++) {
    NSRect item = [view convertRect:[view rectOfItemAtIndex:index] toView:nil];
    item = [window convertRectToScreen:item];
    item.origin = NSMakePoint(NSMinX(item) - NSMinX(frame), NSMaxY(frame) - NSMaxY(item));
    [items addObject:rectangle(item)];
  }
  for (NSScreen *screen in [NSScreen screens])
    [screens addObject:@{@"frame":rectangle([screen frame]), @"work":rectangle([screen visibleFrame])}];
  NSDictionary *state = @{@"event":@"state", @"window":@([window windowNumber]),
    @"visible":@([window isVisible]), @"transient":@([menu isTransient]),
    @"level":@([window level]), @"main":@(menu == [NSApp mainMenu]), @"active":@([NSApp isActive]),
    @"frame":rectangle(frame), @"screen":rectangle([[window screen] frame]),
    @"work":rectangle([[window screen] visibleFrame]), @"screens":screens,
    @"items":items, @"actions":@(target->actions), @"last":@(target->last)};
  NSData *data = [NSJSONSerialization dataWithJSONObject:state options:0 error:NULL];
  puts([[[[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] autorelease] UTF8String]);
}

int main(int argc, char **argv)
{
  setvbuf(stdout, NULL, _IOLBF, 0);
  setvbuf(stdin, NULL, _IONBF, 0);
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  [NSApplication sharedApplication];
  [NSApp finishLaunching];
  NSMenu *menu = [[MenuPlacementMenu alloc] initWithTitle:@"Native menu placement"];
  MenuPlacementTarget *target = [MenuPlacementTarget new];
  NSWindow *normal = nil;
  BOOL done = NO;
  puts("{\"event\":\"ready\"}");
  while (!done) {
    NSAutoreleasePool *iteration = [NSAutoreleasePool new];
    NSEvent *event = [NSApp nextEventMatchingMask:NSAnyEventMask
      untilDate:[NSDate dateWithTimeIntervalSinceNow:.005] inMode:NSDefaultRunLoopMode dequeue:YES];
    if (event) [NSApp sendEvent:event];
    [NSApp updateWindows];
    struct pollfd input = {0, POLLIN, 0};
    if (poll(&input, 1, 0) > 0) {
      char line[128];
      int count;
      double x, y;
      if (!fgets(line, sizeof(line), stdin) || !strncmp(line, "quit", 4)) done = YES;
      else if (sscanf(line, "items %d", &count) == 1) {
        while ([menu numberOfItems]) [menu removeItemAtIndex:0];
        for (int index = 0; index < count; index++) {
          NSMenuItem *item = [[NSMenuItem alloc] initWithTitle:
            [NSString stringWithFormat:@"Native command %d", index + 1]
            action:@selector(invoke:) keyEquivalent:@""];
          [item setTag:index + 1]; [item setTarget:target]; [menu addItem:item]; [item release];
        }
        [NSApp setMainMenu:menu]; [menu sizeToFit]; [menu display];
      } else if (sscanf(line, "move %lf %lf", &x, &y) == 2) {
        [[menu window] setFrameOrigin:NSMakePoint(x, y)];
      } else if (sscanf(line, "level %d", &count) == 1) {
        [[menu window] setLevel:count];
      } else if (!strncmp(line, "deactivate", 10)) [NSApp deactivate];
      else if (!strncmp(line, "adopt", 5)) {
        /* setMain: only displays when NSApp is active. Match the production
           native-menu show sequence after this pointer-only fixture loses
           activation; menu adoption alone does not promise visibility. */
        [menu setMain:YES]; [menu display];
      }
      else if (!strncmp(line, "show", 4)) [menu display];
      else if (!strncmp(line, "hide", 4)) [menu close];
      else if (!strncmp(line, "normal", 6)) {
        normal = [[NSWindow alloc] initWithContentRect:NSMakeRect(300, 300, 320, 180)
          styleMask:NSTitledWindowMask | NSClosableWindowMask | NSResizableWindowMask
          backing:NSBackingStoreBuffered defer:NO];
        [normal setReleasedWhenClosed:NO]; [normal setTitle:@"Native normal window"];
        [normal makeKeyAndOrderFront:nil];
      }
      else if (!strncmp(line, "state", 5)) report(menu, target);
    }
    [iteration drain];
  }
  [normal close]; [normal release];
  [menu close]; [NSApp setMainMenu:nil]; [menu release]; [target release]; [pool drain];
  return 0;
}
