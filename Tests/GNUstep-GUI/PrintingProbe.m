/* Screen density must not alter printing coordinates. LGPL-2.0-or-later. */
#import <AppKit/AppKit.h>

static NSButton *cancelButton(NSView *view)
{
  if ([view isKindOfClass:[NSButton class]] && [[(NSButton *)view title] isEqual:@"Cancel"]) return (NSButton *)view;
  for (NSView *child in [view subviews]) { NSButton *button = cancelButton(child); if (button) return button; }
  return nil;
}
static const short PrintingReadyEvent = 0x5052;

@interface PrintingApplication : NSApplication
@end
@implementation PrintingApplication
- (void)panelMetadata:(id)unused
{
  NSWindow *panel = [NSApp modalWindow]; NSButton *button = cancelButton([panel contentView]);
  if (!panel || !button) return;
  // Capture after key-window focus and its control outline have been painted.
  [panel display]; [panel flushWindow];
  NSView *content = [panel contentView];
  NSView *document = [content isKindOfClass:[NSScrollView class]] ? [(NSScrollView *)content documentView] : content;
  NSScroller *scroller = [content isKindOfClass:[NSScrollView class]] ? [(NSScrollView *)content verticalScroller] : nil;
  NSRect scroll = scroller ? [content convertRect:[scroller bounds] fromView:scroller] : NSZeroRect;
  NSRect bounds = [[panel contentView] convertRect:[button bounds] fromView:button];
  NSDictionary *value = @{ @"event":@"panel-control", @"metadata_request":@(unused != nil), @"window_number":@([panel windowNumber]),
    @"x":@(bounds.origin.x), @"y":@(bounds.origin.y), @"width":@(bounds.size.width),
    @"height":@(bounds.size.height), @"content_height":@([[panel contentView] bounds].size.height), @"content_class":NSStringFromClass([content class]), @"content_flipped":@([content isFlipped]),
    @"key_window":@([panel isKeyWindow]), @"first_responder":NSStringFromClass([[panel firstResponder] class]) ?: @"",
    @"document_width":@([document frame].size.width), @"document_height":@([document frame].size.height),
    @"scroll_x":@(scroll.origin.x), @"scroll_y":@(scroll.origin.y), @"scroll_width":@(scroll.size.width), @"scroll_height":@(scroll.size.height) };
  NSData *data = [NSJSONSerialization dataWithJSONObject:value options:0 error:NULL];
  fwrite([data bytes],1,[data length],stdout);putchar('\n');fflush(stdout);
}
- (void)sendEvent:(NSEvent *)event
{
  if ([event type] == NSApplicationDefined && [event subtype] == PrintingReadyEvent) {
    puts("{\"event\":\"ready\"}"); fflush(stdout); return;
  }
  if ([event type] == NSLeftMouseDown || [event type] == NSLeftMouseUp || [event type] == NSKeyDown) {
    NSWindow *window = [event window];
    printf("{\"event\":\"dispatch\",\"type\":%lu,\"window\":%ld,\"active\":%s,\"responder\":\"%s\"}\n",
      (unsigned long)[event type],(long)[window windowNumber], [self isActive] ? "true" : "false",
      [NSStringFromClass([[window firstResponder] class]) UTF8String]); fflush(stdout);
  }
  if ([event type] == NSKeyDown && [[event charactersIgnoringModifiers] isEqual:@"m"] && [NSApp modalWindow]) {
    [self panelMetadata:@YES];return;
  }
  [super sendEvent:event];
}
@end

static NSBitmapImageRep *solidImage(NSInteger pixels, BOOL red)
{
  NSBitmapImageRep *rep = [[[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL
    pixelsWide:pixels pixelsHigh:pixels bitsPerSample:8 samplesPerPixel:3 hasAlpha:NO
    isPlanar:NO colorSpaceName:NSDeviceRGBColorSpace bytesPerRow:pixels*3 bitsPerPixel:24] autorelease];
  [rep setSize:NSMakeSize(16,16)];
  for (NSInteger i=0; i<pixels*pixels; i++) {
    unsigned char *pixel = [rep bitmapData]+i*3;
    pixel[0] = red ? 255 : 0; pixel[1] = 0; pixel[2] = red ? 0 : 255;
  }
  return rep;
}

@interface PrintingView : NSView
{
  NSImage *image;
  NSInteger panelResult;
}
@end
@implementation PrintingView
- (void)dealloc { [image release]; [super dealloc]; }
- (BOOL)isFlipped { return ![[NSUserDefaults standardUserDefaults] boolForKey:@"UnflippedView"]; }
- (BOOL)acceptsFirstResponder { return YES; }
- (BOOL)acceptsFirstMouse:(NSEvent *)event { return YES; }
- (void)mouseDown:(NSEvent *)event
{
  id responder = [[self superview] isKindOfClass:[PrintingView class]] ? [self superview] : self;
  [[self window] makeFirstResponder:responder];
  puts("{\"event\":\"mouse-input\"}"); fflush(stdout);
}
- (void)drawRect:(NSRect)dirty
{
  [[NSColor whiteColor] set]; NSRectFill([self bounds]);
  if ([[self subviews] count]) return;
  [[NSColor redColor] set]; NSRectFill(NSMakeRect(10, 10, 40, 20));
  [[NSColor greenColor] set]; NSRectFill(NSMakeRect(100, 10, 40, 20));
  [[NSColor blueColor] set]; NSRectFill(NSMakeRect(10, 140, 40, 20));
  if (!image) {
    image = [[NSImage alloc] initWithSize:NSMakeSize(16,16)];
    [image addRepresentation:solidImage(16,YES)];
    [image addRepresentation:solidImage(32,NO)];
  }
  [image drawInRect:NSMakeRect(160,140,40,20) fromRect:NSZeroRect
    operation:NSCompositeSourceOver fraction:1];
  [[NSColor blackColor] set]; NSRectFill(NSMakeRect(10, 110, 200, 1));
  [@"NEXTSPACE print geometry" drawAtPoint:NSMakePoint(10, 60)
    withAttributes:[NSDictionary dictionaryWithObjectsAndKeys:
      [NSFont systemFontOfSize:12], NSFontAttributeName,
      [NSColor blackColor], NSForegroundColorAttributeName, nil]];
}
- (void)pageLayoutDidEnd:(NSPageLayout *)panel returnCode:(NSInteger)value contextInfo:(void *)context
{ panelResult = value; }
- (void)keyDown:(NSEvent *)event
{
  NSString *characters = [event charactersIgnoringModifiers];
  printf("{\"event\":\"key-input\",\"character\":%u}\n",
    (unsigned)([characters length] ? [characters characterAtIndex:0] : 0)); fflush(stdout);
  if ([characters isEqual:@"l"] || [characters isEqual:@"p"] || [characters isEqual:@"s"]) {
    [NSApp performSelector:@selector(panelMetadata:) withObject:nil afterDelay:0 inModes:@[NSModalPanelRunLoopMode]];
    NSInteger result = NSCancelButton;
    if ([characters isEqual:@"s"]) {
      panelResult = NSRunContinuesResponse;
      [[NSPageLayout pageLayout] beginSheetWithPrintInfo:[NSPrintInfo sharedPrintInfo]
        modalForWindow:[self window] delegate:self
        didEndSelector:@selector(pageLayoutDidEnd:returnCode:contextInfo:) contextInfo:NULL];
      result = panelResult;
    } else result = [characters isEqual:@"l"] ?
      [[NSPageLayout pageLayout] runModalWithPrintInfo:[NSPrintInfo sharedPrintInfo]] :
      [[NSPrintPanel printPanel] runModalWithPrintInfo:[NSPrintInfo sharedPrintInfo]];
    if (![characters isEqual:@"p"]) {
      NSPageLayout *panel = [NSPageLayout pageLayout];
      NSDictionary *state = @{ @"event":@"page-layout-restored",
        @"content_class":NSStringFromClass([[panel contentView] class]),
        @"width":@([panel frame].size.width), @"height":@([panel frame].size.height),
        @"document_width":@([[panel contentView] frame].size.width),
        @"document_height":@([[panel contentView] frame].size.height),
        @"minimum_width":@([panel minSize].width), @"minimum_height":@([panel minSize].height) };
      NSData *data = [NSJSONSerialization dataWithJSONObject:state options:0 error:NULL];
      fwrite([data bytes],1,[data length],stdout);putchar('\n');fflush(stdout);
    }
    printf("{\"event\":\"panel\",\"kind\":\"%s\",\"result\":%ld}\n",
      [characters UTF8String], (long)result); fflush(stdout); return;
  }
  if (![[event charactersIgnoringModifiers] isEqual:@"e"]) return;
  NSString *directory = [[NSUserDefaults standardUserDefaults] stringForKey:@"ExportDirectory"];
  NSInteger scale = (NSInteger)([[self window] backingScaleFactor] * 120 + 0.5);
  NSRect bounds = [self bounds];
  NSString *profile = [[NSUserDefaults standardUserDefaults] stringForKey:@"ExportCase"];
  NSRect rect = [profile isEqual:@"crop"] ? NSMakeRect(7,5,203,251) : bounds;
  printf("{\"event\":\"export-begin\",\"scale\":%ld}\n", (long)scale); fflush(stdout);
  NSPrintInfo *info = [[[NSPrintInfo sharedPrintInfo] copy] autorelease];
  [info setPaperSize:bounds.size];
  [info setLeftMargin:0]; [info setRightMargin:0];
  [info setTopMargin:0]; [info setBottomMargin:0];
  [info setHorizontallyCentered:NO]; [info setVerticallyCentered:NO];
  NSPrintInfo *exportInfo = [[info copy] autorelease];
  [exportInfo setPaperSize:rect.size];
  NSMutableData *pdf = [NSMutableData data], *eps = [NSMutableData data];
  BOOL printed = [[NSPrintOperation PDFOperationWithView:self insideRect:rect
    toData:pdf printInfo:exportInfo] runOperation];
  printf("{\"event\":\"export-format\",\"format\":\"pdf\",\"ok\":%s}\n", printed ? "true" : "false"); fflush(stdout);
  printed = [[NSPrintOperation EPSOperationWithView:self insideRect:rect toData:eps printInfo:exportInfo] runOperation] && printed;
  printf("{\"event\":\"export-format\",\"format\":\"eps\",\"ok\":%s}\n", printed ? "true" : "false"); fflush(stdout);
  NSString *postscript = [directory stringByAppendingPathComponent:
    [NSString stringWithFormat:@"print-%ld.ps", (long)scale]];
  [[info dictionary] setObject:NSPrintSaveJob forKey:NSPrintJobDisposition];
  [[info dictionary] setObject:postscript forKey:NSPrintSavePath];
  NSPrintOperation *operation = [NSPrintOperation printOperationWithView:self printInfo:info];
  [operation setShowsPrintPanel:NO]; [operation setShowsProgressPanel:NO];
  printed = [operation runOperation] && printed &&
    [[NSData dataWithContentsOfFile:postscript] length] > 0;
  BOOL ok = printed && [pdf length] && [eps length] &&
    [pdf writeToFile:[directory stringByAppendingPathComponent:
      [NSString stringWithFormat:@"print-%ld.pdf", (long)scale]] atomically:YES] &&
    [eps writeToFile:[directory stringByAppendingPathComponent:
      [NSString stringWithFormat:@"print-%ld.eps", (long)scale]] atomically:YES];
  printf("{\"event\":\"export\",\"scale\":%ld,\"ok\":%s,\"width\":%.0f,\"height\":%.0f,\"printer_class\":\"%s\"}\n",
    (long)scale, ok ? "true" : "false", bounds.size.width, bounds.size.height,
    [NSStringFromClass([operation class]) UTF8String]);
  fflush(stdout);
}
@end

@interface PrintingDelegate : NSObject
{
  NSWindow *window;
}
@end
@implementation PrintingDelegate
- (void)applicationDidFinishLaunching:(NSNotification *)notification
{
  BOOL landscape = [[[NSUserDefaults standardUserDefaults] stringForKey:@"ExportCase"] isEqual:@"landscape"];
  NSSize size = landscape ? NSMakeSize(313,257) : NSMakeSize(257,313);
  window = [[NSWindow alloc] initWithContentRect:NSMakeRect(20, 20, size.width, size.height)
    styleMask:NSTitledWindowMask | NSClosableWindowMask
    backing:NSBackingStoreBuffered defer:NO];
  [window setTitle:@"PrintingProbe"];
  PrintingView *view = [[PrintingView alloc] initWithFrame:NSMakeRect(0, 0, size.width, size.height)];
  if ([[NSUserDefaults standardUserDefaults] boolForKey:@"NestedPrintView"]) {
    PrintingView *child = [[PrintingView alloc] initWithFrame:NSInsetRect([view bounds],7,5)];
    [child setBoundsOrigin:NSMakePoint(7,5)];
    [view addSubview:child]; [child release];
  }
  [window setContentView:view]; [window makeFirstResponder:view]; [view release];
  [window makeKeyAndOrderFront:nil];
  /* A mapped buffer precedes completion of launch notifications and Services.
     A dispatched event confirms AppKit has entered its actual event loop. */
  [NSApp postEvent:[NSEvent otherEventWithType:NSApplicationDefined location:NSZeroPoint
    modifierFlags:0 timestamp:0 windowNumber:0 context:nil subtype:PrintingReadyEvent
    data1:0 data2:0] atStart:NO];
}
@end

int main(int argc, char **argv)
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  [PrintingApplication sharedApplication];
  PrintingDelegate *delegate = [PrintingDelegate new];
  [NSApp setDelegate:delegate]; [NSApp run];
  [delegate release]; [pool drain];
  return 0;
}
