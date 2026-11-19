/* Reject native drags from an unmapped embedding window without poisoning the
 * display connection. Exercises original AppKit/Wayland code; no drag UI.
 * SPDX-License-Identifier: GPL-2.0-or-later */
#import <AppKit/AppKit.h>
#import <GNUstepGUI/GSDragView.h>
#import <GNUstepGUI/GSDisplayServer.h>
#include <assert.h>
#include <stdio.h>
#include <sys/select.h>
#include <unistd.h>
static BOOL began,ended;
static NSDragOperation result;
@interface OriginSource : NSObject
@end
@implementation OriginSource
- (NSDragOperation)draggingSourceOperationMaskForLocal:(BOOL)local {return NSDragOperationCopy;}
- (void)draggedImage:(NSImage *)image beganAt:(NSPoint)point {began=YES;}
- (void)draggedImage:(NSImage *)image endedAt:(NSPoint)point operation:(NSDragOperation)operation
{ended=YES;result=operation;}
@end
int main(void)
{
 NSAutoreleasePool *pool=[NSAutoreleasePool new];[NSApplication sharedApplication];
 NSWindow *hidden=[[NSWindow alloc] initWithContentRect:NSMakeRect(0,0,160,30)
   styleMask:NSBorderlessWindowMask backing:NSBackingStoreBuffered defer:NO];
 assert([hidden windowNumber]>0&&![hidden isVisible]);
 NSPasteboard *pasteboard=[NSPasteboard pasteboardWithName:NSDragPboard];
 [pasteboard declareTypes:@[NSStringPboardType] owner:nil];
 assert([pasteboard setString:@"native drag origin probe" forType:NSStringPboardType]);
 NSImage *image=[[NSImage alloc] initWithSize:NSMakeSize(16,16)];
 [image lockFocus];[[NSColor blackColor] set];NSRectFill(NSMakeRect(0,0,16,16));[image unlockFocus];
 OriginSource *source=[OriginSource new];
 NSEvent *event=[NSEvent mouseEventWithType:NSLeftMouseDown location:NSMakePoint(8,8)
   modifierFlags:0 timestamp:0 windowNumber:[hidden windowNumber] context:nil
   eventNumber:1 clickCount:1 pressure:1];
 puts("{\"event\":\"unmapped-native-drag-start\"}");fflush(stdout);
 [(GSDragView *)[GSCurrentServer() dragInfo] dragImage:image at:NSMakePoint(8,8) offset:NSZeroSize
   event:event pasteboard:pasteboard source:source slideBack:NO];
 printf("{\"event\":\"unmapped-native-drag\",\"began\":%s,\"ended\":%s,\"operation\":%lu}\n",began?"true":"false",ended?"true":"false",(unsigned long)result);fflush(stdout);
 assert(!began&&ended&&result==NSDragOperationNone);
 NSWindow *visible=[[NSWindow alloc] initWithContentRect:NSMakeRect(80,80,240,120)
   styleMask:NSTitledWindowMask backing:NSBackingStoreBuffered defer:NO];
 [visible setTitle:@"Native drag origin guard"];[visible makeKeyAndOrderFront:nil];[NSApp finishLaunching];
 puts("{\"event\":\"native-window-ready\"}");fflush(stdout);
 for(;;) {
  fd_set read;FD_ZERO(&read);FD_SET(0,&read);struct timeval wait={0};
  if(select(1,&read,NULL,NULL,&wait)>0)break;
  NSEvent *next=[NSApp nextEventMatchingMask:NSAnyEventMask untilDate:[NSDate dateWithTimeIntervalSinceNow:.01] inMode:NSDefaultRunLoopMode dequeue:YES];
  if(next)[NSApp sendEvent:next];[NSApp updateWindows];
 }
 [visible close];[hidden close];[source release];[image release];[pool drain];return 0;
}
