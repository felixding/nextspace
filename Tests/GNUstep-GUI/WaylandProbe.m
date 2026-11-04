/* Native rendering and interaction fixture. LGPL-2.0-or-later. */
#import <AppKit/AppKit.h>
#import <AppKit/DPSOperators.h>
#import <objc/runtime.h>
#include <string.h>

static IMP originalIMETransaction;
static BOOL nestedIMEEntered;
static void nestedIMETransaction(id server, SEL selector, NSDictionary *transaction)
{
  ((void (*)(id, SEL, NSDictionary *))originalIMETransaction)(server, selector, transaction);
  if (nestedIMEEntered || ![[transaction objectForKey:@"preedit"] length]) return;
  nestedIMEEntered = YES;
  /* Model a synchronous AppKit/service reply while composition is applied.
     Incoming commits must still be drained after this nested loop returns. */
  NSDate *limit = [NSDate dateWithTimeIntervalSinceNow:0.5];
  while ([limit timeIntervalSinceNow] > 0)
    [[NSRunLoop currentRunLoop] runMode:NSConnectionReplyMode beforeDate:limit];
  printf("{\"event\":\"nested-ime\",\"queued\":%lu}\n",
    (unsigned long)[[server valueForKey:@"transactions"] count]); fflush(stdout);
}

@protocol ProbeZoomControl
- (void)toggleZoomVeto;
@end

static NSArray *rectValues(NSRect rect)
{
  return [NSArray arrayWithObjects:[NSNumber numberWithDouble:rect.origin.x], [NSNumber numberWithDouble:rect.origin.y],
    [NSNumber numberWithDouble:rect.size.width], [NSNumber numberWithDouble:rect.size.height], nil];
}

static NSImage *redImage(NSSize size)
{
  NSBitmapImageRep *bitmap = [[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL
    pixelsWide:4 pixelsHigh:4 bitsPerSample:8 samplesPerPixel:4 hasAlpha:YES
    isPlanar:NO colorSpaceName:NSDeviceRGBColorSpace bytesPerRow:16 bitsPerPixel:32];
  unsigned char *bytes = [bitmap bitmapData];
  NSUInteger i;
  for (i = 0; i < 16; i++) {
    bytes[4*i] = 255; bytes[4*i+1] = bytes[4*i+2] = 0; bytes[4*i+3] = 255;
  }
  NSImage *image = [[[NSImage alloc] initWithSize:size] autorelease];
  [image addRepresentation:bitmap]; [bitmap release];
  return image;
}

static void finePattern(void)
{
  [[NSColor blackColor] set]; NSRectFill(NSMakeRect(0, 0, 16, 16));
  [[NSColor whiteColor] set]; NSRectFill(NSMakeRect(4.5, 0, 1, 16));
}

static void pathRasterSample(NSUInteger kind, CGFloat x, CGFloat y, BOOL antialias)
{
  [NSGraphicsContext saveGraphicsState];
  [[NSGraphicsContext currentContext] setShouldAntialias:antialias];
  NSAffineTransform *transform = [NSAffineTransform transform];
  [transform translateXBy:x yBy:y]; [transform concat];
  [[NSColor blackColor] set];
  if (kind == 0)
    [[NSBezierPath bezierPathWithRect:NSMakeRect(0.25, 0.25, 39.5, 39.5)] fill];
  else if (kind == 1)
    [[NSBezierPath bezierPathWithOvalInRect:NSMakeRect(0.25, 0.25, 39.5, 39.5)] fill];
  else if (kind == 2) {
    transform = [NSAffineTransform transform];
    [transform translateXBy:15 yBy:10]; [transform rotateByDegrees:17]; [transform concat];
    NSRectFill(NSMakeRect(0, 0, 30, 30));
  } else if (kind == 3)
    NSRectFill(NSMakeRect(0.25, 0.25, 39.5, 39.5));
  else if (kind == 4) {
    transform = [NSAffineTransform transform]; [transform scaleBy:1.125]; [transform concat];
    NSRectFill(NSMakeRect(0, 0, 35, 35));
  } else if (kind == 5) {
    transform = [NSAffineTransform transform]; [transform translateXBy:0.25 yBy:0.25]; [transform concat];
    NSRectFill(NSMakeRect(0, 0, 39, 39));
  } else
    NSRectFill(NSMakeRect(0, 0, 39, 39));
  [NSGraphicsContext restoreGraphicsState];
}

@interface ProbeView : NSView
{
  NSImage *image;
  NSImage *vectorImage, *densityImage;
  NSCursor *customCursor;
  NSCursor *themedCursor;
  BOOL cursorActive;
  NSUInteger rasterGeneration;
}
@end
@implementation ProbeView
- (void)dealloc
{
  [customCursor release]; [image release]; [vectorImage release]; [densityImage release];
  [super dealloc];
}
- (BOOL)drawPattern:(NSCustomImageRep *)rep { finePattern(); return YES; }
- (BOOL)drawCursor:(NSCustomImageRep *)rep
{
  [[NSColor redColor] set]; NSRectFill(NSMakeRect(0, 0, 19, 8));
  [[NSColor greenColor] set]; NSRectFill(NSMakeRect(0, 8, 19, 9));
  return YES;
}
- (void)resetCursorRects
{
  [self addCursorRect:[self bounds] cursor:cursorActive ? customCursor :
    (themedCursor ? themedCursor : [NSCursor arrowCursor])];
}
- (BOOL)pixel:(NSPoint)point isRed:(BOOL)red
{
  NSBitmapImageRep *image = [[[NSBitmapImageRep alloc] initWithFocusedViewRect:
    NSMakeRect(point.x, point.y, 1, 1)] autorelease];
  NSColor *color = [[image colorAtX:0 y:0] colorUsingColorSpaceName:NSDeviceRGBColorSpace];
  return color && [color redComponent] == (red ? 1 : 0) &&
    [color greenComponent] == (red ? 0 : 1) && [color blueComponent] == 0;
}
- (void)drawRect:(NSRect)rect
{
  if ([[NSUserDefaults standardUserDefaults] boolForKey:@"PathRasterProbe"]) {
    [[NSColor whiteColor] set]; NSRectFill([self bounds]);
    for (NSUInteger kind = 0; kind < 7; kind++) {
      pathRasterSample(kind, 20 + 100 * kind, 60, YES);
      pathRasterSample(kind, 20 + 100 * kind, 160, NO);
    }
    [(rasterGeneration % 2 ? [NSColor redColor] : [NSColor greenColor]) set];
    NSRectFill(NSMakeRect(750, 60, 20, 20));
    return;
  }
  if ([[NSUserDefaults standardUserDefaults] boolForKey:@"TransparentWindow"]) {
    NSRectFillUsingOperation([self bounds], NSCompositeClear);
    [[NSColor colorWithDeviceRed:1 green:0 blue:0 alpha:0.5] set];
    NSRectFill(NSMakeRect(20, 220, 30, 20));
    return;
  }
  [[NSColor lightGrayColor] set]; NSRectFill([self bounds]);
  [@"NEXTSPACE native Wayland — text and logical geometry" drawAtPoint:NSMakePoint(20, [self bounds].size.height - 40)
    withAttributes:[NSDictionary dictionaryWithObject:[NSFont systemFontOfSize:18]
                                               forKey:NSFontAttributeName]];
  [[NSColor whiteColor] set]; NSRectFill(NSMakeRect(20, 530, 761, 1));
  [[NSColor blackColor] set]; NSRectFill(NSMakeRect(20, 529, 761, 1));
  [[NSColor redColor] set]; NSRectFill(NSMakeRect(20, 220, 30, 20));
  [[NSColor greenColor] set]; NSRectFill(NSMakeRect(50, 220, 30, 20));
  if (!image) image = [redImage(NSMakeSize(4, 4)) retain];
  [image drawInRect:NSMakeRect(160, 220, 20, 20) fromRect:NSZeroRect operation:NSCompositeSourceOver fraction:1];
  [image compositeToPoint:NSMakePoint(190, 220) operation:NSCompositeSourceOver];
  if (!vectorImage) {
    vectorImage = [[NSImage alloc] initWithSize:NSMakeSize(16, 16)];
    NSCustomImageRep *rep = [[NSCustomImageRep alloc] initWithDrawSelector:@selector(drawPattern:) delegate:self];
    [rep setSize:[vectorImage size]]; [vectorImage addRepresentation:rep]; [rep release];
    densityImage = [redImage(NSMakeSize(4, 4)) retain];
    NSBitmapImageRep *blue = [[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL
      pixelsWide:8 pixelsHigh:8 bitsPerSample:8 samplesPerPixel:4 hasAlpha:YES
      isPlanar:NO colorSpaceName:NSDeviceRGBColorSpace bytesPerRow:32 bitsPerPixel:32];
    [blue setSize:NSMakeSize(4, 4)];
    NSUInteger i;
    for (i = 0; i < 64; i++) {
      unsigned char *pixel = [blue bitmapData] + 4*i;
      pixel[0] = pixel[1] = 0; pixel[2] = pixel[3] = 255;
    }
    [densityImage addRepresentation:blue]; [blue release];
  }
  [vectorImage drawInRect:NSMakeRect(200, 270, 16, 16) fromRect:NSZeroRect operation:NSCompositeSourceOver fraction:1];
  [NSGraphicsContext saveGraphicsState];
  NSAffineTransform *transform = [NSAffineTransform transform];
  [transform translateXBy:240 yBy:270]; [transform concat]; finePattern();
  [NSGraphicsContext restoreGraphicsState];
  NSBitmapImageRep *pattern = [[[NSBitmapImageRep alloc] initWithFocusedViewRect:NSMakeRect(200, 270, 16, 16)] autorelease];
  NSBitmapImageRep *direct = [[[NSBitmapImageRep alloc] initWithFocusedViewRect:NSMakeRect(240, 270, 16, 16)] autorelease];
  /* Image clipping applies separate edge coverage at fractional boundaries.
     Compare the interior, including the fine line, without that outer pixel. */
  BOOL vectorOK = pattern && direct;
  NSInteger px, py;
  for (py = 1; vectorOK && py < [direct pixelsHigh] - 1; py++)
    for (px = 1; px < [direct pixelsWide] - 1; px++)
      if (![[pattern colorAtX:px y:py] isEqual:[direct colorAtX:px y:py]]) vectorOK = NO;
  [densityImage drawInRect:NSMakeRect(220, 270, 8, 8) fromRect:NSZeroRect operation:NSCompositeSourceOver fraction:1];
  [vectorImage drawInRect:NSMakeRect(280, 270, 16, 16) fromRect:NSMakeRect(4, 0, 8, 16)
    operation:NSCompositeSourceOver fraction:0.5];
  NSBitmapImageRep *sample = [[[NSBitmapImageRep alloc] initWithFocusedViewRect:NSMakeRect(224, 274, 1, 1)] autorelease];
  NSColor *color = [[sample colorAtX:0 y:0] colorUsingColorSpaceName:NSDeviceRGBColorSpace];
  BOOL high = [[self window] backingScaleFactor] > 1;
  BOOL densityOK = color && [color redComponent] == (high ? 0 : 1) &&
    [color blueComponent] == (high ? 1 : 0) && [color greenComponent] == 0;
  printf("{\"event\":\"vector-image\",\"scale\":%.8f,\"ok\":%s,\"density_rep\":%s}\n",
    [[self window] backingScaleFactor], vectorOK ? "true" : "false", densityOK ? "true" : "false");
  NSCopyBits(0, NSMakeRect(20, 220, 60, 20), NSMakePoint(90, 200));
  BOOL readback = [self pixel:NSMakePoint(30, 230) isRed:YES] &&
    [self pixel:NSMakePoint(60, 230) isRed:NO] &&
    [self pixel:NSMakePoint(100, 210) isRed:YES] && [self pixel:NSMakePoint(130, 210) isRed:NO] &&
    [self pixel:NSMakePoint(170, 230) isRed:YES] && [self pixel:NSMakePoint(191, 221) isRed:YES];
  printf("{\"event\":\"readback\",\"scale\":%.8f,\"ok\":%s}\n",
    [[self window] backingScaleFactor], readback ? "true" : "false");
  NSGraphicsContext *context = [NSGraphicsContext currentContext];
  [[NSFont systemFontOfSize:12] set];
  const NSGlyph glyphs[] = {'A', 'B'};
  const NSSize advances[] = {{20, 0}, {7, 0}};
  DPSmoveto(context, 20, 320);
  GSShowGlyphsWithAdvances(context, glyphs, advances, 2);
  CGFloat x, y;
  DPScurrentpoint(context, &x, &y);
  printf("{\"event\":\"glyph-advance\",\"x\":%.3f,\"y\":%.3f}\n", x, y);
  fflush(stdout);
}
- (BOOL)acceptsFirstResponder { return YES; }
- (BOOL)acceptsFirstMouse:(NSEvent *)event { return YES; }
- (void)mouseDown:(NSEvent *)event
{
  [[self window] makeFirstResponder:self];
  NSPoint p = [event locationInWindow];
  printf("{\"event\":\"click\",\"x\":%.3f,\"y\":%.3f}\n", p.x, p.y);
  fflush(stdout);
}
- (void)keyDown:(NSEvent *)event
{
  NSString *characters = [event characters];
  if ([[NSUserDefaults standardUserDefaults] boolForKey:@"PathRasterProbe"] && [characters isEqual:@"r"]) {
    rasterGeneration++;
    [self setNeedsDisplay:YES]; [self displayIfNeeded]; [[self window] flushWindow];
    printf("{\"event\":\"raster-redraw\",\"generation\":%lu}\n", (unsigned long)rasterGeneration); fflush(stdout);
    return;
  }
  NSString *plain = [event charactersIgnoringModifiers];
  if ([[NSUserDefaults standardUserDefaults] boolForKey:@"ZoomProbe"] &&
      [characters length] && [characters characterAtIndex:0] == NSF11FunctionKey)
    [(id<ProbeZoomControl>)[[self window] delegate] toggleZoomVeto];
  if ([[NSUserDefaults standardUserDefaults] boolForKey:@"ZoomProbe"] &&
      [characters length] && [characters characterAtIndex:0] == NSF12FunctionKey) {
    [[self window] zoom:nil];
    printf("{\"event\":\"zoom-request\",\"zoomed\":%s}\n", [[self window] isZoomed] ? "true" : "false");
  }
  if ([characters isEqual:@"9"]) {
    if (!customCursor) {
      NSImage *cursorImage = [[NSImage alloc] initWithSize:NSMakeSize(19, 17)];
      NSCustomImageRep *rep = [[NSCustomImageRep alloc] initWithDrawSelector:@selector(drawCursor:) delegate:self];
      [rep setSize:[cursorImage size]]; [cursorImage addRepresentation:rep]; [rep release];
      customCursor = [[NSCursor alloc] initWithImage:cursorImage hotSpot:NSMakePoint(3, 5)];
      [cursorImage release];
    }
    cursorActive = YES;
    [[self window] invalidateCursorRectsForView:self];
    [customCursor set];
  } else if ([characters isEqual:@"0"]) {
    cursorActive = NO;
    themedCursor = nil;
    [[self window] invalidateCursorRectsForView:self];
    [[NSCursor arrowCursor] set];
  }
  else if ([characters isEqual:@"7"]) [NSCursor hide];
  else if ([characters isEqual:@"8"]) [NSCursor unhide];
  if ([[NSUserDefaults standardUserDefaults] boolForKey:@"CursorProbe"]) {
    NSCursor *selected = nil;
    if ([characters isEqual:@"i"]) selected = [NSCursor IBeamCursor];
    else if ([characters isEqual:@"h"]) selected = [NSCursor pointingHandCursor];
    else if ([characters isEqual:@"r"]) selected = [NSCursor resizeLeftRightCursor];
    else if ([characters isEqual:@"c"]) selected = [NSCursor crosshairCursor];
    else if ([characters isEqual:@"o"]) selected = [NSCursor openHandCursor];
    else if ([characters isEqual:@"p"]) selected = [NSCursor closedHandCursor];
    else if ([characters isEqual:@"m"]) selected = [NSCursor contextualMenuCursor];
    if (selected) {
      cursorActive = NO; themedCursor = selected;
      [[self window] invalidateCursorRectsForView:self];
      [selected set];
    }
  }
  if ([characters isEqual:@"g"]) {
    [[self window] setMinSize:NSMakeSize(100, 110)];
    [[self window] setMaxSize:NSMakeSize(2000, 2000)];
    [[self window] setResizeIncrements:NSMakeSize(8, 16)];
    puts("{\"event\":\"grid-enabled\"}");
  } else if ([characters isEqual:@"n"]) {
    [[self window] setMinSize:NSMakeSize(1, 1)];
    [[self window] setMaxSize:NSMakeSize(10000, 10000)];
    [[self window] setResizeIncrements:NSMakeSize(1, 1)];
    puts("{\"event\":\"grid-disabled\"}");
  }
  if ([characters isEqual:@"c"] && !([event modifierFlags] & NSControlKeyMask)) {
    NSMutableString *text = [NSMutableString stringWithString:@"Native:日本語\n"];
    int i;
    for (i = 0; i < 6000; i++) [text appendString:@"clipboard:日本語\n"];
    NSPasteboard *pasteboard = [NSPasteboard generalPasteboard];
    [pasteboard declareTypes:[NSArray arrayWithObjects:NSStringPboardType, @"org.nextspace.test.binary", nil] owner:nil];
    [pasteboard setString:text forType:NSStringPboardType];
    const unsigned char bytes[] = {0, 1, 127, 128, 254, 255};
    [pasteboard setData:[NSData dataWithBytes:bytes length:sizeof(bytes)] forType:@"org.nextspace.test.binary"];
    puts("{\"event\":\"clipboard-copy\"}");
  }
  if ([characters isEqual:@"p"] && !([event modifierFlags] & NSControlKeyMask)) {
    NSMutableString *text = [NSMutableString stringWithString:@"Primary:日本語\n"];
    int i;
    for (i = 0; i < 6000; i++) [text appendString:@"selection:日本語\n"];
    NSPasteboard *pasteboard = [NSPasteboard pasteboardWithName:@"Selection"];
    [pasteboard declareTypes:[NSArray arrayWithObject:NSStringPboardType] owner:nil];
    [pasteboard setString:text forType:NSStringPboardType];
    puts("{\"event\":\"primary-copy\"}");
  }
  printf("{\"event\":\"key\",\"character\":%u,\"plain\":%u,\"modifiers\":%lu,\"repeat\":%s}\n",
    [characters length] ? [characters characterAtIndex:0] : 0,
    [plain length] ? [plain characterAtIndex:0] : 0,
    (unsigned long)[event modifierFlags], [event isARepeat] ? "true" : "false");
  fflush(stdout);
}
@end

@interface ProbeApplication : NSApplication
@end
@implementation ProbeApplication
- (NSEvent *)nextEventMatchingMask:(NSUInteger)mask untilDate:(NSDate *)limit inMode:(NSString *)mode dequeue:(BOOL)flag
{
  BOOL cursorProbe = [[NSUserDefaults standardUserDefaults] boolForKey:@"CursorProbe"];
  if (cursorProbe || [[NSUserDefaults standardUserDefaults] boolForKey:@"TextInputProbe"]) {
    NSArray *modes = [NSArray arrayWithObjects:NSDefaultRunLoopMode, NSModalPanelRunLoopMode,
      NSEventTrackingRunLoopMode, NSConnectionReplyMode, nil];
    NSUInteger index = [[NSUserDefaults standardUserDefaults] integerForKey:
      cursorProbe ? @"CursorRunLoopMode" : @"TextInputRunLoopMode"];
    if (index < [modes count]) mode = [modes objectAtIndex:index];
  }
  return [super nextEventMatchingMask:mask untilDate:limit inMode:mode dequeue:flag];
}
- (void)sendEvent:(NSEvent *)event
{
  NSEventType type = [event type];
  NSPoint point = [event locationInWindow];
  NSInteger number = [event windowNumber];
  NSInteger clicks = type == NSLeftMouseDown ? [event clickCount] : 0;
  unsigned keycode = type == NSKeyUp ? [event keyCode] : 0;
  [super sendEvent:event];
  if (type == NSLeftMouseDown) {
    printf("{\"event\":\"mouse-handled\",\"x\":%.0f,\"y\":%.0f,\"window\":%ld,\"clicks\":%ld}\n",
      point.x, point.y, (long)number, (long)clicks); fflush(stdout);
  }
  if (type == NSKeyUp) {
    printf("{\"event\":\"key-up-handled\",\"keycode\":%u}\n", keycode); fflush(stdout);
  }
}
@end

@interface Probe : NSObject <NSTextFieldDelegate, NSWindowDelegate, ProbeZoomControl>
{
  NSWindow *window;
  NSPanel *popup;
  NSMenu *detachedMenu;
  NSMenu *nestedMenu;
  NSTimer *nestedTimer;
  NSTimer *stateTimer;
  NSDictionary *lastInputState;
  NSPanel *modal;
  BOOL denyZoom;
}
- (void)closePopup:(id)sender;
@end
@implementation Probe
- (void)toggleZoomVeto
{
  denyZoom = !denyZoom;
  printf("{\"event\":\"zoom-veto\",\"denied\":%s}\n", denyZoom ? "true" : "false"); fflush(stdout);
}
- (BOOL)windowShouldZoom:(NSWindow *)sender toFrame:(NSRect)frame { return !denyZoom; }
- (void)menuAction:(id)sender
{
  [detachedMenu close];
  puts("{\"event\":\"menu-action\"}"); fflush(stdout);
}
- (void)nestedAction:(id)sender
{
  [nestedMenu close];
  puts("{\"event\":\"nested-menu-action\"}"); fflush(stdout);
}
- (void)reportNestedHighlight:(NSTimer *)timer
{
  NSMenu *leaf = [[[nestedMenu itemAtIndex:0] submenu] itemAtIndex:0].submenu;
  if ([[leaf window] isVisible] && [[leaf menuRepresentation] highlightedItemIndex] == 0) {
    puts("{\"event\":\"nested-leaf-highlight\"}"); fflush(stdout);
    [timer invalidate]; [nestedTimer release]; nestedTimer = nil;
  }
}
- (void)showNestedMenu:(id)sender
{
  if (!nestedMenu) {
    nestedMenu = [[NSMenu alloc] initWithTitle:@"Wayland nested menu"];
    NSMenu *parent = nestedMenu;
    NSUInteger i;
    for (i = 0; i < 2; i++) {
      NSMenuItem *item = [parent addItemWithTitle:@"More" action:NULL keyEquivalent:@""];
      NSMenu *child = [[NSMenu alloc] initWithTitle:i ? @"Leaf menu" : @"Child menu"];
      [parent setSubmenu:child forItem:item]; [child release]; parent = child;
    }
    NSMenuItem *item = [parent addItemWithTitle:@"Run nested action" action:@selector(nestedAction:) keyEquivalent:@""];
    [item setTarget:self]; [nestedMenu setTornOff:YES];
  }
  [nestedMenu display];
  [nestedTimer invalidate]; [nestedTimer release];
  nestedTimer = [[NSTimer timerWithTimeInterval:0.01 target:self
    selector:@selector(reportNestedHighlight:) userInfo:nil repeats:YES] retain];
  [[NSRunLoop currentRunLoop] addTimer:nestedTimer forMode:NSEventTrackingRunLoopMode];
  NSRect frame = [window frame];
  [[nestedMenu window] setTitle:@"Wayland nested menu"];
  [[nestedMenu window] setFrameOrigin:NSMakePoint(frame.origin.x + 400, frame.origin.y + 200)];
  NSMenu *menu = nestedMenu;
  NSUInteger depth;
  for (depth = 0; depth < 3; depth++) {
    [menu sizeToFit];
    NSMenuView *view = [menu menuRepresentation];
    NSRect item = [view rectOfItemAtIndex:0];
    NSPoint point = [view convertPoint:NSMakePoint(NSMidX(item), NSMidY(item)) toView:nil];
    printf("{\"event\":\"nested-item\",\"depth\":%lu,\"x\":%.0f,\"y\":%.0f}\n",
      (unsigned long)depth, point.x, point.y);
    menu = [[menu itemAtIndex:0] submenu];
  }
  fflush(stdout);
}
- (void)showMenu:(id)sender
{
  if (!detachedMenu) {
    detachedMenu = [[NSMenu alloc] initWithTitle:@"Wayland detached menu"];
    NSMenuItem *item = [detachedMenu addItemWithTitle:@"Run menu action"
      action:@selector(menuAction:) keyEquivalent:@""];
    [item setTarget:self];
    [detachedMenu setTornOff:YES];
  }
  NSRect frame = [window frame];
  [[detachedMenu window] setTitle:@"Wayland detached menu"];
  [detachedMenu display];
  [[detachedMenu window] setFrameOrigin:NSMakePoint(frame.origin.x + 400, frame.origin.y + 200)];
  NSMenuView *view = [detachedMenu menuRepresentation];
  NSRect item = [view rectOfItemAtIndex:0];
  NSPoint p = [view convertPoint:NSMakePoint(NSMidX(item), NSMidY(item)) toView:nil];
  printf("{\"event\":\"menu-item\",\"x\":%.0f,\"y\":%.0f}\n", p.x, p.y); fflush(stdout);
}
- (void)stopModal:(id)sender { [NSApp stopModal]; }
- (void)showModal:(id)sender
{
  NSRect frame = [window frame];
  modal = [[NSPanel alloc] initWithContentRect:NSMakeRect(frame.origin.x + 200,
    frame.origin.y + 200, 300, 160) styleMask:NSTitledWindowMask
    backing:NSBackingStoreBuffered defer:NO];
  [modal setReleasedWhenClosed:NO]; [modal setTitle:@"Wayland modal panel"];
  [modal setLevel:NSModalPanelWindowLevel];
  NSButton *button = [[NSButton alloc] initWithFrame:NSMakeRect(50, 50, 200, 40)];
  [button setTitle:@"Finish modal"]; [button setTarget:self]; [button setAction:@selector(stopModal:)];
  [[modal contentView] addSubview:button]; [button release];
  NSPoint p = [button convertPoint:NSMakePoint(100, 20) toView:nil];
  printf("{\"event\":\"modal-button\",\"x\":%.0f,\"y\":%.0f}\n", p.x, p.y); fflush(stdout);
  [NSApp runModalForWindow:modal];
  [modal close]; [modal release]; modal = nil;
  puts("{\"event\":\"modal-finished\"}"); fflush(stdout);
}
- (void)echo:(NSPasteboard *)pasteboard userData:(NSString *)userData error:(NSString **)error
{
  NSString *text = [pasteboard stringForType:NSStringPboardType];
  if (!text) { *error = @"Missing service input"; return; }
  NSData *binary = [pasteboard dataForType:@"org.nextspace.test.binary"];
  [pasteboard declareTypes:[NSArray arrayWithObjects:NSStringPboardType, @"org.nextspace.test.binary", nil] owner:nil];
  [pasteboard setString:[@"Services:" stringByAppendingString:text] forType:NSStringPboardType];
  [pasteboard setData:binary forType:@"org.nextspace.test.binary"];
  puts("{\"event\":\"service\"}"); fflush(stdout);
}
- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)app
{ return ![[NSUserDefaults standardUserDefaults] boolForKey:@"CloseOnScale"]; }
- (void)moved:(id)sender
{
  NSPoint origin = [window frame].origin;
  printf("{\"event\":\"move\",\"x\":%.0f,\"y\":%.0f}\n", origin.x, origin.y);
  fflush(stdout);
}
- (void)screenChanged:(id)sender
{
  NSRect frame = [[window screen] frame];
  printf("{\"event\":\"screen\",\"x\":%.0f,\"y\":%.0f}\n", frame.origin.x, frame.origin.y);
  fflush(stdout);
}
- (void)requestPlacement:(id)sender
{
  [window setFrameOrigin:NSMakePoint(100000, 100000)];
  puts("{\"event\":\"placement-request\"}"); fflush(stdout);
}
- (void)miniState:(id)sender
{
  if ([[NSUserDefaults standardUserDefaults] boolForKey:@"TextInputProbe"]) {
    id client = [window firstResponder];
    if ([client isKindOfClass:[NSTextView class]]) {
      NSRange marked = [client markedRange], selected = [client selectedRange];
      NSDictionary *state = [NSDictionary dictionaryWithObjectsAndKeys:@"input-state", @"event",
        [[[client string] copy] autorelease], @"text", [NSNumber numberWithBool:[client hasMarkedText]], @"marked",
        [NSNumber numberWithUnsignedInteger:marked.location], @"mark_location",
        [NSNumber numberWithUnsignedInteger:marked.length], @"mark_length",
        [NSNumber numberWithUnsignedInteger:selected.location], @"cursor",
        [NSNumber numberWithUnsignedInteger:selected.length], @"selection", nil];
      if (![state isEqual:lastInputState]) {
        NSData *json = [NSJSONSerialization dataWithJSONObject:state options:0 error:NULL];
        fwrite([json bytes], 1, [json length], stdout); putchar('\n'); fflush(stdout);
        [lastInputState release]; lastInputState = [state copy];
      }
    }
  }
  static BOOL previous = NO;
  BOOL current = [window isMiniaturized];
  if (previous == current) return;
  previous = current;
  printf("{\"event\":\"mini-state\",\"minimized\":%s}\n", current ? "true" : "false");
  fflush(stdout);
}
- (void)windowWillClose:(id)sender
{
  [stateTimer invalidate]; stateTimer = nil;
  if (popup) [self closePopup:nil];
  if ([[NSUserDefaults standardUserDefaults] boolForKey:@"CloseDelegateProbe"]) {
    puts("{\"event\":\"window-close\"}"); fflush(stdout);
  }
}
- (BOOL)windowShouldClose:(id)sender
{
  static unsigned attempts = 0;
  BOOL denied = [[NSUserDefaults standardUserDefaults] boolForKey:@"CloseDelegateProbe"] &&
    [sender isDocumentEdited] && attempts++ == 0;
  printf("{\"event\":\"close-request\",\"denied\":%s}\n", denied ? "true" : "false");
  fflush(stdout);
  return !denied;
}
- (void)miniNotification:(NSNotification *)notification
{
  printf("{\"event\":\"mini-notification\",\"minimized\":%s}\n",
    [[notification name] isEqualToString:NSWindowDidMiniaturizeNotification] ? "true" : "false");
  fflush(stdout);
}
- (void)minimize:(id)sender { [window miniaturize:sender]; }
- (void)controlTextDidChange:(NSNotification *)notification
{
  NSData *json = [NSJSONSerialization dataWithJSONObject:[NSDictionary dictionaryWithObjectsAndKeys:
    @"field-text", @"event", [[notification object] stringValue], @"text", nil] options:0 error:NULL];
  fwrite([json bytes], 1, [json length], stdout); putchar('\n'); fflush(stdout);
}
- (void)closePopup:(id)sender
{
  [[NSNotificationCenter defaultCenter] removeObserver:self name:NSWindowDidMoveNotification object:popup];
  [window removeChildWindow:popup];
  [popup close]; [popup autorelease]; popup = nil;
  puts("{\"event\":\"popup-closed\"}"); fflush(stdout);
}
- (void)popupMoved:(id)sender
{
  NSPoint origin = [popup frame].origin;
  printf("{\"event\":\"popup-move\",\"x\":%.0f,\"y\":%.0f}\n", origin.x, origin.y);
  fflush(stdout);
}
- (void)showPopup:(id)sender
{
  if (popup) return;
  NSRect parent = [window frame];
  popup = [[NSPanel alloc] initWithContentRect:NSMakeRect(parent.origin.x + 650,
    parent.origin.y + 450, 200, 120) styleMask:NSBorderlessWindowMask
    backing:NSBackingStoreBuffered defer:NO];
  [popup setReleasedWhenClosed:NO];
  [popup setLevel:NSPopUpMenuWindowLevel];
  [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(popupMoved:)
    name:NSWindowDidMoveNotification object:popup];
  NSButton *close = [[NSButton alloc] initWithFrame:NSMakeRect(20, 20, 150, 30)];
  [close setTitle:@"Close popup"]; [close setTarget:self]; [close setAction:@selector(closePopup:)];
  [[popup contentView] addSubview:close]; [close release];
  [window addChildWindow:popup ordered:NSWindowAbove];
  [popup orderFront:nil];
}
- (void)titleState:(NSNotification *)notification
{
  for (NSWindow *candidate in [NSApp windows]) {
    if (candidate != window && !([candidate styleMask] & NSTitledWindowMask)) continue;
    printf("{\"event\":\"title-state\",\"window\":%ld,\"state\":%d,\"key\":%s,\"main\":%s,\"active\":%s}\n",
      (long)[candidate windowNumber], [[[candidate valueForKey:@"_wv"] valueForKey:@"inputState"] intValue],
      [candidate isKeyWindow] ? "true" : "false", [candidate isMainWindow] ? "true" : "false",
      [NSApp isActive] ? "true" : "false");
  }
  fflush(stdout);
}
- (void)report:(id)sender
{
  CGFloat scale = [window backingScaleFactor];
  ProbeView *view = (ProbeView *)[window contentView];
  [view lockFocus];
  BOOL imageOK = [view pixel:NSMakePoint(580, 366) isRed:YES];
  [view unlockFocus];
  printf("{\"event\":\"image-subview\",\"scale\":%.8f,\"ok\":%s}\n", scale, imageOK ? "true" : "false");
  NSRect logical = NSMakeRect(-3, 5, 801, 601);
  NSRect roundtrip = [window convertRectFromBacking:[window convertRectToBacking:logical]];
  printf("{\"event\":\"scale\",\"scale\":%.8f,\"width\":%.0f,\"height\":%.0f,\"roundtrip\":%s}\n",
    scale, [window frame].size.width, [window frame].size.height,
    NSEqualRects(logical, roundtrip) ? "true" : "false");
  fflush(stdout);
  if (scale == 2 && [[NSUserDefaults standardUserDefaults] boolForKey:@"CloseOnScale"]) {
    [window close]; window = nil;
    puts("{\"event\":\"closed-during-scale\"}"); fflush(stdout);
    [NSApp performSelector:@selector(terminate:) withObject:nil afterDelay:0.1];
  }
}
- (void)applicationDidFinishLaunching:(NSNotification *)note
{
  if ([[NSUserDefaults standardUserDefaults] boolForKey:@"NestedIMEProbe"]) {
    Method method = class_getInstanceMethod(NSClassFromString(@"WaylandInputServer"),
      NSSelectorFromString(@"applyTransaction:"));
    NSCAssert(method != NULL, @"Native input server is required");
    originalIMETransaction = method_setImplementation(method, (IMP)nestedIMETransaction);
  }
  [NSApp setServicesProvider:self];
  NSUInteger style = NSTitledWindowMask | NSClosableWindowMask | NSResizableWindowMask | NSMiniaturizableWindowMask;
  id requestedStyle = [[NSUserDefaults standardUserDefaults] objectForKey:@"WindowStyleMask"];
  if (requestedStyle) style = [requestedStyle integerValue];
  NSRect content = [NSWindow contentRectForFrameRect:NSMakeRect(0, 0, 801, 601) styleMask:style];
  window = [[NSWindow alloc] initWithContentRect:content
    styleMask:style backing:NSBackingStoreBuffered
    defer:[[NSUserDefaults standardUserDefaults] boolForKey:@"DeferredWindow"]];
  [window setDocumentEdited:[[NSUserDefaults standardUserDefaults] boolForKey:@"DocumentEdited"]];
  if ([[NSUserDefaults standardUserDefaults] boolForKey:@"TransparentWindow"]) {
    [window setOpaque:NO];
    [window setBackgroundColor:[NSColor clearColor]];
  }
  NSString *requestedTitle = [[NSUserDefaults standardUserDefaults] stringForKey:@"WindowTitle"];
  [window setTitle:requestedTitle ? requestedTitle :
    [[NSUserDefaults standardUserDefaults] boolForKey:@"CloseOnScale"] ? @"WaylandCloseProbe" : @"WaylandProbe"];
  NSButton *closeButton = [window standardWindowButton:NSWindowCloseButton];
  NSPoint closePoint = NSZeroPoint;
  if (closeButton)
    closePoint = [closeButton convertPoint:NSMakePoint(NSMidX([closeButton bounds]), NSMidY([closeButton bounds])) toView:nil];
  printf("{\"event\":\"close-button\",\"x\":%.0f,\"y\":%.0f}\n", closePoint.x, closePoint.y);
  ProbeView *view = [[ProbeView alloc] initWithFrame:[[window contentView] bounds]];
  [view allocateGState];
  [window setContentView:view]; [view release];
  if ([[NSUserDefaults standardUserDefaults] boolForKey:@"PathRasterProbe"]) {
    [window makeFirstResponder:view]; [window makeKeyAndOrderFront:nil];
    return;
  }
  NSPoint patternPoint = [view convertPoint:NSMakePoint(200, 270) toView:nil];
  printf("{\"event\":\"pixel-pattern\",\"window\":%ld,\"x\":%.0f,\"y\":%.0f}\n",
    (long)[window windowNumber], patternPoint.x, patternPoint.y);
  NSButton *button = [[NSButton alloc] initWithFrame:NSMakeRect(20, 460, 140, 32)];
  [button setTitle:@"Redraw controls"]; [button setTarget:self]; [button setAction:@selector(report:)];
  [view addSubview:button]; [button release];
  button = [[NSButton alloc] initWithFrame:NSMakeRect(200, 460, 140, 32)];
  [button setTitle:@"Open popup"]; [button setTarget:self]; [button setAction:@selector(showPopup:)];
  [view addSubview:button]; [button release];
  NSPoint popupButton = [view convertPoint:NSMakePoint(270, 476) toView:nil];
  printf("{\"event\":\"popup-button\",\"x\":%.0f,\"y\":%.0f}\n", popupButton.x, popupButton.y);
  fflush(stdout);
  button = [[NSButton alloc] initWithFrame:NSMakeRect(380, 460, 140, 32)];
  [button setTitle:@"Test placement"]; [button setTarget:self]; [button setAction:@selector(requestPlacement:)];
  [view addSubview:button]; [button release];
  NSPoint placementButton = [view convertPoint:NSMakePoint(450, 476) toView:nil];
  printf("{\"event\":\"placement-button\",\"x\":%.0f,\"y\":%.0f}\n", placementButton.x, placementButton.y);
  fflush(stdout);
  Class fieldClass = [[NSUserDefaults standardUserDefaults] boolForKey:@"SecureTextInputProbe"] ?
    [NSSecureTextField class] : [NSTextField class];
  NSTextField *field = [[fieldClass alloc] initWithFrame:NSMakeRect(20, 400, 500, 28)];
  [field setStringValue:@"Selection, keyboard input and text metrics"]; [field setDelegate:self]; [view addSubview:field];
  NSPoint fieldStart = [field convertPoint:NSMakePoint(3, 14) toView:nil];
  NSPoint fieldEnd = [field convertPoint:NSMakePoint(497, 14) toView:nil];
  printf("{\"event\":\"text-field\",\"start_x\":%.0f,\"start_y\":%.0f,\"end_x\":%.0f,\"end_y\":%.0f}\n",
    fieldStart.x, fieldStart.y, fieldEnd.x, fieldEnd.y);
  [field release];
  button = [[NSButton alloc] initWithFrame:NSMakeRect(550, 350, 60, 32)];
  [button setBordered:NO]; [button setImage:redImage(NSMakeSize(20, 20))]; [button setImagePosition:NSImageOnly];
  [button allocateGState]; [view addSubview:button]; [button release];
  NSPoint imagePoint = [view convertPoint:NSMakePoint(580, 366) toView:nil];
  printf("{\"event\":\"image-point\",\"x\":%.0f,\"y\":%.0f}\n", imagePoint.x, imagePoint.y);
  NSArray *actions = [NSArray arrayWithObjects:@"showMenu:", @"showModal:", @"showNestedMenu:", @"minimize:", nil];
  NSArray *titles = [NSArray arrayWithObjects:@"Open detached menu", @"Run modal panel", @"Open nested menus", @"Miniaturize", nil];
  NSArray *events = [NSArray arrayWithObjects:@"show-menu", @"show-modal", @"show-nested", @"minimize", nil];
  NSUInteger i;
  for (i = 0; i < [actions count]; i++) {
    NSString *action = [actions objectAtIndex:i];
    button = [[NSButton alloc] initWithFrame:NSMakeRect(20 + (i % 2) * 200, 350 - (i / 2) * 50, 180, 32)];
    [button setTitle:[titles objectAtIndex:i]];
    [button setTarget:self]; [button setAction:NSSelectorFromString(action)];
    [view addSubview:button];
    NSPoint p = [button convertPoint:NSMakePoint(90, 16) toView:nil];
    printf("{\"event\":\"%s\",\"x\":%.0f,\"y\":%.0f}\n", [[events objectAtIndex:i] UTF8String], p.x, p.y);
    [button release];
  }
  fflush(stdout);
  stateTimer = [NSTimer scheduledTimerWithTimeInterval:0.05 target:self selector:@selector(miniState:) userInfo:nil repeats:YES];
  if ([[NSUserDefaults standardUserDefaults] boolForKey:@"TextInputProbe"])
    for (NSString *mode in [NSArray arrayWithObjects:NSModalPanelRunLoopMode, NSEventTrackingRunLoopMode, NSConnectionReplyMode, nil])
      [[NSRunLoop currentRunLoop] addTimer:stateTimer forMode:mode];
  if ([[NSUserDefaults standardUserDefaults] boolForKey:@"ZoomProbe"] ||
      [[NSUserDefaults standardUserDefaults] boolForKey:@"CloseDelegateProbe"])
    [window setDelegate:self];
  else
    [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(windowWillClose:)
      name:NSWindowWillCloseNotification object:window];
  for (NSString *name in [NSArray arrayWithObjects:NSWindowDidMiniaturizeNotification,
      NSWindowDidDeminiaturizeNotification, nil])
    [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(miniNotification:) name:name object:window];
  [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(report:)
    name:NSWindowDidChangeBackingPropertiesNotification object:window];
  [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(moved:)
    name:NSWindowDidMoveNotification object:window];
  [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(screenChanged:)
    name:NSWindowDidChangeScreenNotification object:window];
  for (NSString *name in [NSArray arrayWithObjects:NSWindowDidBecomeKeyNotification, NSWindowDidResignKeyNotification,
      NSWindowDidBecomeMainNotification, NSWindowDidResignMainNotification,
      NSApplicationDidBecomeActiveNotification, NSApplicationDidResignActiveNotification, nil])
    [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(titleState:) name:name object:nil];
  [window makeKeyAndOrderFront:nil];
  [self report:nil];
}
@end

static BOOL exportImageReference(NSBitmapImageRep *source, NSString *path)
{
  NSInteger width = [source pixelsWide], height = [source pixelsHigh];
  NSBitmapImageRep *rgba = [[[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL
    pixelsWide:width pixelsHigh:height bitsPerSample:8 samplesPerPixel:4
    hasAlpha:YES isPlanar:NO colorSpaceName:NSCalibratedRGBColorSpace
    bitmapFormat:NSAlphaNonpremultipliedBitmapFormat bytesPerRow:width*4 bitsPerPixel:32] autorelease];
  unsigned char *bytes = [rgba bitmapData];
  for (NSInteger y = 0; y < height; y++) for (NSInteger x = 0; x < width; x++) {
    NSColor *color = [[source colorAtX:x y:y] colorUsingColorSpaceName:NSCalibratedRGBColorSpace];
    if (!color) return NO;
    CGFloat red = 0, green = 0, blue = 0, alpha = 0;
    [color getRed:&red green:&green blue:&blue alpha:&alpha];
    NSUInteger offset = 4*(y*width+x);
    bytes[offset] = round(red*255); bytes[offset+1] = round(green*255);
    bytes[offset+2] = round(blue*255); bytes[offset+3] = round(alpha*255);
  }
  return [[rgba representationUsingType:NSPNGFileType properties:[NSDictionary dictionary]]
    writeToFile:path atomically:YES];
}

static int decodeImage(const char *path, BOOL density, NSString *referencePath)
{
  NSImage *image = [[[NSImage alloc] initWithContentsOfFile:
    [NSString stringWithUTF8String:path]] autorelease];
  NSMutableArray *representations = [NSMutableArray array];
  for (NSImageRep *candidate in [image representations]) {
    if (![candidate isKindOfClass:[NSBitmapImageRep class]]) continue;
    NSBitmapImageRep *rep = (NSBitmapImageRep *)candidate;
    if ([rep pixelsWide] <= 0 || [rep pixelsHigh] <= 0) continue;
    NSMutableArray *samples = [NSMutableArray array];
    for (NSUInteger y = 0; y < 2; y++) for (NSUInteger x = 0; x < 2; x++) {
      NSColor *color = [[rep colorAtX:(2*x+1)*[rep pixelsWide]/4
        y:(2*y+1)*[rep pixelsHigh]/4] colorUsingColorSpaceName:NSCalibratedRGBColorSpace];
      NSCAssert(color != nil, @"Decoded pixel must have an RGB representation");
      CGFloat red = 0, green = 0, blue = 0, alpha = 0;
      [color getRed:&red green:&green blue:&blue alpha:&alpha];
      [samples addObject:[NSArray arrayWithObjects:
        [NSNumber numberWithInt:round(red*255)], [NSNumber numberWithInt:round(green*255)],
        [NSNumber numberWithInt:round(blue*255)], [NSNumber numberWithInt:round(alpha*255)], nil]];
    }
    [representations addObject:[NSDictionary dictionaryWithObjectsAndKeys:
      [NSNumber numberWithInteger:[rep pixelsWide]], @"width",
      [NSNumber numberWithInteger:[rep pixelsHigh]], @"height",
      [NSNumber numberWithDouble:[rep size].width], @"logical_width",
      [NSNumber numberWithDouble:[rep size].height], @"logical_height",
      [rep colorSpaceName], @"color_space", samples, @"samples", nil]];
  }
  NSMutableArray *selections = [NSMutableArray array];
  if (density) {
    const CGFloat scales[] = {1, 1.25, 1.5, 1.75, 2, 3, 4, 5, 6, 7, 8};
    for (NSUInteger i = 0; i < sizeof(scales)/sizeof(scales[0]); i++) {
      NSDictionary *device = [NSDictionary dictionaryWithObjectsAndKeys:
        [NSValue valueWithSize:NSMakeSize(72*scales[i], 72*scales[i])], NSDeviceResolution,
        NSCalibratedRGBColorSpace, NSDeviceColorSpaceName,
        [NSNumber numberWithInt:8], NSDeviceBitsPerSample, nil];
      NSImageRep *rep = [image bestRepresentationForDevice:device];
      if (referencePath && i == 0 &&
          (![rep isKindOfClass:[NSBitmapImageRep class]] ||
           !exportImageReference((NSBitmapImageRep *)rep, referencePath))) return 1;
      [selections addObject:[NSDictionary dictionaryWithObjectsAndKeys:
        [NSNumber numberWithDouble:scales[i]], @"scale",
        [NSNumber numberWithUnsignedInteger:[[image representations] indexOfObjectIdenticalTo:rep]], @"representation_index",
        [NSNumber numberWithInteger:[rep pixelsWide]], @"width",
        [NSNumber numberWithInteger:[rep pixelsHigh]], @"height", nil]];
    }
  }
  NSMutableSet *libraries = [NSMutableSet set];
  NSString *maps = [NSString stringWithContentsOfFile:@"/proc/self/maps" encoding:NSUTF8StringEncoding error:NULL];
  for (NSString *line in [maps componentsSeparatedByString:@"\n"])
    if ([line rangeOfString:@".so"].location != NSNotFound ||
        [line rangeOfString:@"libgnustep-"].location != NSNotFound)
      [libraries addObject:[[line componentsSeparatedByString:@" "] lastObject]];
  BOOL valid = [representations count] > 0;
  NSDictionary *result = [NSDictionary dictionaryWithObjectsAndKeys:
    [NSNumber numberWithBool:valid], @"ok", representations, @"representations",
    [libraries allObjects], @"libraries", selections, @"density_selections", nil];
  NSData *json = [NSJSONSerialization dataWithJSONObject:result options:0 error:NULL];
  fwrite([json bytes], 1, [json length], stdout); puts("");
  return valid ? 0 : 1;
}

int main(int argc, char **argv)
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  if (argc == 3 && (strcmp(argv[1], "--decode-image") == 0 || strcmp(argv[1], "--image-density") == 0)) {
    int result = decodeImage(argv[2], strcmp(argv[1], "--image-density") == 0, nil);
    [pool drain]; return result;
  }
  if (argc == 4 && strcmp(argv[1], "--image-reference") == 0) {
    int result = decodeImage(argv[2], YES, [NSString stringWithUTF8String:argv[3]]);
    [pool drain]; return result;
  }
  [ProbeApplication sharedApplication];
  if ([[NSUserDefaults standardUserDefaults] boolForKey:@"WorkAreaProbe"]) {
    NSMutableArray *areas = [NSMutableArray array];
    for (NSScreen *screen in [NSScreen screens]) {
      NSRect frame = [screen frame], work = [screen visibleFrame];
      [areas addObject:[NSDictionary dictionaryWithObjectsAndKeys:rectValues(frame), @"frame", rectValues(work), @"work", nil]];
    }
    NSData *json = [NSJSONSerialization dataWithJSONObject:areas options:0 error:NULL];
    fwrite([json bytes], 1, [json length], stdout); puts("");
    int result = json ? 0 : 1;
    [pool drain]; return result;
  }
  Probe *probe = [Probe new];
  [NSApp setDelegate:probe];
  [NSApp run];
  [probe release]; [pool drain]; return 0;
}
