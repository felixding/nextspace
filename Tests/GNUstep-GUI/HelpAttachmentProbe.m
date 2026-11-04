/* Exercise GNUstep's real inline help attachment. LGPL-2.0-or-later. */
#import <AppKit/AppKit.h>
#import <GNUstepGUI/GSHelpAttachment.h>
#include <stdio.h>

@interface HelpAttachmentProbe : NSObject <NSApplicationDelegate>
{
  NSWindow *window;
  NSTextView *text;
  GSHelpLinkAttachment *attachment;
}
@end
@implementation HelpAttachmentProbe
- (void)emit:(NSTimer *)timer
{
  NSImage *image=[[attachment attachmentCell] image];
  NSMutableArray *sizes=[NSMutableArray array];
  for (NSImageRep *rep in [image representations])
    if ([rep isKindOfClass:[NSBitmapImageRep class]]) [sizes addObject:@[@([rep pixelsWide]),@([rep pixelsHigh])]];
  NSDictionary *row=@{@"event":@"frame",@"window":@([window windowNumber]),@"scale":@([window backingScaleFactor]),
    @"logical":@[@([image size].width),@([image size].height)],@"representations":sizes,
    @"target":[attachment fileName],@"marker":[attachment markerName]};
  NSData *data=[NSJSONSerialization dataWithJSONObject:row options:0 error:NULL];fwrite([data bytes],1,[data length],stdout);puts("");fflush(stdout);
}
- (void)applicationDidFinishLaunching:(NSNotification *)notification
{
  window=[[NSWindow alloc] initWithContentRect:NSMakeRect(100,100,400,160)
    styleMask:NSTitledWindowMask|NSClosableWindowMask backing:NSBackingStoreBuffered defer:NO];
  [window setTitle:@"Native Help Attachment"];
  text=[[NSTextView alloc] initWithFrame:[[window contentView] bounds]];
  [text setBackgroundColor:[NSColor whiteColor]];[text setEditable:NO];[text setSelectable:YES];
  attachment=[[GSHelpLinkAttachment alloc] initWithFileName:@"owned-guide.rtf" markerName:@"intro"];
  NSMutableAttributedString *content=[[NSMutableAttributedString alloc] initWithString:@"\n\n\t"];
  [content appendAttributedString:[NSAttributedString attributedStringWithAttachment:attachment]];
  [[text textStorage] setAttributedString:content];[content release];
  [[window contentView] addSubview:text];[window makeKeyAndOrderFront:nil];
  [NSTimer scheduledTimerWithTimeInterval:.1 target:self selector:@selector(emit:) userInfo:nil repeats:YES];
  [self emit:nil];
}
@end
int main(void)
{
  NSAutoreleasePool *pool=[NSAutoreleasePool new];[NSApplication sharedApplication];
  HelpAttachmentProbe *probe=[HelpAttachmentProbe new];[NSApp setDelegate:probe];[NSApp run];
  [probe release];[pool drain];return 0;
}
