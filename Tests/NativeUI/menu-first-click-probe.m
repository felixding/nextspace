/* Verify native menu lifetime and destination focus without a browser. */
#import <AppKit/AppKit.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

@interface MenuClickTarget : NSObject
{ @public NSInteger actions; }
- (void)invoke:(id)sender;
@end
@implementation MenuClickTarget
- (void)invoke:(id)sender { actions++; }
@end

static NSArray *rect(NSRect r)
{ return @[@(r.origin.x), @(r.origin.y), @(r.size.width), @(r.size.height)]; }
static NSArray *fieldRect(NSTextField *field)
{ return rect([[field window] convertRectToScreen:[field convertRect:[field bounds] toView:nil]]); }

int main(void)
{
  setvbuf(stdout, NULL, _IOLBF, 0);
  setvbuf(stdin, NULL, _IONBF, 0);
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  BOOL destination = getenv("NEXTSPACE_MENU_DESTINATION") != NULL;
  [NSApplication sharedApplication];
  MenuClickTarget *target = [MenuClickTarget new];
  NSMenu *root = [[NSMenu alloc] initWithTitle:@"Native menu first click"];
  NSMenu *edit = [[NSMenu alloc] initWithTitle:@"Edit"];
  NSMenuItem *command = [[NSMenuItem alloc] initWithTitle:@"Inspect"
    action:@selector(invoke:) keyEquivalent:@""];
  [command setTarget:target]; [edit addItem:command]; [command release];
  NSMenuItem *item = [[NSMenuItem alloc] initWithTitle:@"Edit" action:NULL keyEquivalent:@""];
  [item setSubmenu:edit]; [root addItem:item]; [item release];
  if (!destination) [NSApp setMainMenu:root];
  NSWindow *normal = [[NSWindow alloc] initWithContentRect:
    (destination ? NSMakeRect(450, 100, 360, 180) : NSMakeRect(280, 280, 360, 180))
    styleMask:NSTitledWindowMask | NSClosableWindowMask
    backing:NSBackingStoreBuffered defer:NO];
  [normal setReleasedWhenClosed:NO];
  [normal setTitle:destination ? @"Native foreign destination" : @"Native menu source"];
  NSTextField *first = [[[NSTextField alloc] initWithFrame:NSMakeRect(20, 110, 280, 24)] autorelease];
  NSTextField *second = [[[NSTextField alloc] initWithFrame:NSMakeRect(20, 60, 280, 24)] autorelease];
  [first setStringValue:@"First"]; [second setStringValue:@"Second"];
  [[normal contentView] addSubview:first]; [[normal contentView] addSubview:second];
  [NSApp finishLaunching]; [normal makeKeyAndOrderFront:nil];
  if (!destination) [root display];
  puts("{\"event\":\"ready\"}");
  BOOL done = NO;
  while (!done) {
    NSAutoreleasePool *iteration = [NSAutoreleasePool new];
    NSEvent *event = [NSApp nextEventMatchingMask:NSAnyEventMask
      untilDate:[NSDate dateWithTimeIntervalSinceNow:.005] inMode:NSDefaultRunLoopMode dequeue:YES];
    if (event) [NSApp sendEvent:event];
    [NSApp updateWindows];
    struct pollfd input = {0, POLLIN, 0};
    if (poll(&input, 1, 0) > 0) {
      char line[32];
      if (!fgets(line, sizeof(line), stdin) || !strncmp(line, "quit", 4)) done = YES;
      else if (!strncmp(line, "state", 5)) {
        NSMenuView *representation = [root menuRepresentation];
        NSRect itemRect = [representation convertRect:[representation rectOfItemAtIndex:0] toView:nil];
        itemRect = [[root window] convertRectToScreen:itemRect];
        NSMenuView *subview = [edit menuRepresentation];
        NSRect commandRect = [subview convertRect:[subview rectOfItemAtIndex:0] toView:nil];
        commandRect = [[edit window] convertRectToScreen:commandRect];
        NSDictionary *state = @{@"actions":@(target->actions), @"first_focused":@([first currentEditor] != nil),
          @"second_focused":@([second currentEditor] != nil), @"first": [first stringValue],
          @"second":[second stringValue], @"first_rect":fieldRect(first), @"second_rect":fieldRect(second),
          @"menu_item":rect(itemRect), @"command_item":rect(commandRect),
          @"submenu_visible":@([[edit window] isVisible]), @"submenu_transient":@([edit isTransient]),
          @"submenu_level":@([[edit window] level]), @"screen":rect([[normal screen] frame])};
        NSData *data = [NSJSONSerialization dataWithJSONObject:state options:0 error:NULL];
        puts([[[[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] autorelease] UTF8String]);
      }
    }
    [iteration drain];
  }
  [edit close]; [root close]; [normal close]; [normal release];
  [NSApp setMainMenu:nil]; [root release]; [edit release]; [target release]; [pool drain];
  return 0;
}
