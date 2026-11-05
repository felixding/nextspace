/* Real slider/scroller tracks and their shared theme pattern. GPL-2.0-or-later. */
#import <AppKit/AppKit.h>
#import <GNUstepGUI/GSTheme.h>
@interface GSTheme (TrackPatternProbe)
- (NSImage *)knobSlotPattern;
@end
@interface NSGraphicsContext (TrackPatternProbe)
- (void)GSSetPatterColor:(NSImage *)image;
@end
@interface TrackPreview : NSView @end
@implementation TrackPreview
- (void)drawRect:(NSRect)dirty
{
  [[NSColor windowBackgroundColor] set]; NSRectFill([self bounds]);
  NSGraphicsContext *context=[NSGraphicsContext currentContext];
  [context GSSetPatterColor:[[GSTheme theme] knobSlotPattern]];
  [context DPSrectfill:20 :40 :300 :96];
}
@end
@interface TrackPatternProbe : NSObject <NSApplicationDelegate> { NSWindow *window; } @end
@implementation TrackPatternProbe
- (void)emit:(NSTimer *)timer
{
  NSImage *image=[[GSTheme theme] knobSlotPattern]; NSMutableArray *reps=[NSMutableArray array];
  for (NSImageRep *rep in [image representations]) [reps addObject:@{@"class":NSStringFromClass([rep class]),@"width":@([rep pixelsWide]),@"height":@([rep pixelsHigh])}];
  NSDictionary *row=@{@"event":@"frame",@"window":@([window windowNumber]),@"scale":@([window backingScaleFactor]),@"representations":reps,@"pattern_logical":@[@([image size].width),@([image size].height)],@"preview":@[@20,@40,@300,@96]};
  NSData *data=[NSJSONSerialization dataWithJSONObject:row options:0 error:NULL];fwrite([data bytes],1,[data length],stdout);puts("");fflush(stdout);
}
- (void)applicationDidFinishLaunching:(NSNotification *)notification
{
  window=[[NSWindow alloc] initWithContentRect:NSMakeRect(10,10,480,300) styleMask:NSBorderlessWindowMask backing:NSBackingStoreBuffered defer:NO]; [window setTitle:@"Native Track Pattern"];
  TrackPreview *view=[[TrackPreview alloc] initWithFrame:NSMakeRect(0,0,480,300)];[window setContentView:view];
  NSSlider *horizontal=[[NSSlider alloc] initWithFrame:NSMakeRect(20,240,300,24)];[horizontal setDoubleValue:.37];[view addSubview:horizontal];[horizontal release];
  NSSlider *vertical=[[NSSlider alloc] initWithFrame:NSMakeRect(360,100,24,160)];[vertical setDoubleValue:.63];[view addSubview:vertical];[vertical release];
  NSScrollView *scroll=[[NSScrollView alloc] initWithFrame:NSMakeRect(20,165,300,50)];[scroll setHasHorizontalScroller:YES];[scroll setHasVerticalScroller:YES];
  NSView *document=[[NSView alloc] initWithFrame:NSMakeRect(0,0,600,200)];[scroll setDocumentView:document];[document release];[view addSubview:scroll];[scroll release];
  [view release];[window makeKeyAndOrderFront:nil];[NSTimer scheduledTimerWithTimeInterval:.1 target:self selector:@selector(emit:) userInfo:nil repeats:YES];[self emit:nil];
}
@end
int main(void)
{
  NSAutoreleasePool *pool=[NSAutoreleasePool new];[NSApplication sharedApplication];TrackPatternProbe *probe=[TrackPatternProbe new];[NSApp setDelegate:probe];[NSApp run];[probe release];[pool drain];return 0;
}
