/* Consent dialog for xdg-desktop-portal-wlr's dmenu output chooser.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import <AppKit/AppKit.h>
#include <stdio.h>
#include <unistd.h>

@interface ScreenCastChooser : NSObject
@end
@implementation ScreenCastChooser
- (void)share:(id)sender { [NSApp stopModalWithCode:NSModalResponseOK]; }
- (void)cancel:(id)sender { [NSApp stopModalWithCode:NSModalResponseCancel]; }
@end

int main(void)
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  char bytes[8193]; size_t size = 0;
  while (size < sizeof(bytes)) {
    ssize_t count = read(STDIN_FILENO, bytes + size, sizeof(bytes) - size);
    if (count < 0) { [pool drain]; return 1; }
    if (!count) break;
    size += count;
  }
  if (!size || size > 8192) { [pool drain]; return 1; }
  NSString *input = [[[NSString alloc] initWithBytes:bytes length:size encoding:NSUTF8StringEncoding] autorelease];
  NSMutableArray *outputs = [NSMutableArray array];
  for (NSString *name in [input componentsSeparatedByString:@"\n"]) {
    if (![name length]) continue;
    if ([name length] > 128 || [name rangeOfCharacterFromSet:[NSCharacterSet controlCharacterSet]].location != NSNotFound) {
      [pool drain]; return 1;
    }
    if (![outputs containsObject:name]) [outputs addObject:name];
  }
  if (![outputs count] || [outputs count] > 32) { [pool drain]; return 1; }
  [NSApplication sharedApplication];
  ScreenCastChooser *delegate = [ScreenCastChooser new];
  NSPanel *panel = [[NSPanel alloc] initWithContentRect:NSMakeRect(0,0,400,170)
    styleMask:NSTitledWindowMask backing:NSBackingStoreBuffered defer:NO];
  [panel setTitle:@"Screen Sharing"];
  NSTextField *label = [[[NSTextField alloc] initWithFrame:NSMakeRect(20,115,360,35)] autorelease];
  [label setStringValue:@"Choose a display to share."];
  [label setEditable:NO]; [label setSelectable:NO]; [label setBezeled:NO]; [label setDrawsBackground:NO];
  [[panel contentView] addSubview:label];
  NSPopUpButton *choice = [[[NSPopUpButton alloc] initWithFrame:NSMakeRect(20,72,360,28) pullsDown:NO] autorelease];
  [choice addItemsWithTitles:outputs]; [[panel contentView] addSubview:choice];
  for (NSUInteger index = 0; index < 2; index++) {
    NSButton *button = [[[NSButton alloc] initWithFrame:NSMakeRect(192+index*96,20,88,30)] autorelease];
    [button setTitle:index ? @"Share" : @"Cancel"]; [button setTarget:delegate];
    [button setAction:index ? @selector(share:) : @selector(cancel:)];
    [button setKeyEquivalent:index ? @"\r" : @"\033"];
    [[panel contentView] addSubview:button];
  }
  [NSApp finishLaunching]; [panel center]; [panel makeKeyAndOrderFront:nil];
  [NSApp activateIgnoringOtherApps:YES];
  NSInteger response = [NSApp runModalForWindow:panel];
  if (response == NSModalResponseOK) {
    NSString *selected = [choice titleOfSelectedItem];
    if ([outputs containsObject:selected]) puts([selected UTF8String]);
  }
  [panel orderOut:nil]; [panel release]; [delegate release]; [pool drain];
  return 0;
}
