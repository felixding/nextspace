/* Exercise the production Workspace icon view. GPL-2.0-or-later. */
#import <AppKit/AppKit.h>
#import <GNUstepGUI/GSTheme.h>
#import "PatternArtwork.h"
#ifdef TERMINAL_ARTWORK
#import "TerminalIcon.h"
#else
#import "WSIconTileView.h"
#endif

#ifdef TERMINAL_ARTWORK
@interface TerminalArtworkView : TerminalIcon
@end
@implementation TerminalArtworkView
- (void)drawRect:(NSRect)rect
{
  if ([self scrollingImage]) {
    // Hold one animation frame while exercising the production crop/draw path.
    [self setIsAnimates:YES]; [self setValue:[NSNumber numberWithInt:7] forKey:@"yPosition"];
  }
  [super drawRect:rect];
}
@end
#endif

#ifndef TERMINAL_ARTWORK
@interface ArtworkCanvas : WSIconTileView
{
  NSImage *canvasImage;
}
@end
@implementation ArtworkCanvas
- (void)setImage:(NSImage *)image
{
  [image retain]; [canvasImage release]; canvasImage=image; [self setNeedsDisplay:YES];
}
- (void)drawRect:(NSRect)rect
{
  [super drawRect:rect];
  [canvasImage drawInRect:NSMakeRect(8,8,[canvasImage size].width,[canvasImage size].height)
    fromRect:NSZeroRect operation:NSCompositeSourceOver fraction:1];
}
- (void)dealloc { [canvasImage release]; [super dealloc]; }
@end
#endif

@interface ArtworkScroller : NSScroller
@end
@implementation ArtworkScroller
- (void)drawRect:(NSRect)rect
{
  [super drawRect:rect];
  if ([self tag]) {
    [self drawArrow:NSScrollerDecrementArrow highlight:YES];
    [self drawArrow:NSScrollerIncrementArrow highlight:YES];
  }
}
@end

@interface ArtworkProgress : NSProgressIndicator
{
  NSUInteger sequence;
}
@end
@implementation ArtworkProgress
- (void)animate:(id)sender
{
  sequence++;
  [super animate:sender];
}
- (void)drawRect:(NSRect)rect
{
  [super drawRect:rect];
  NSRect box = [self convertRect:[self bounds] toView:nil];
  NSData *json = [NSJSONSerialization dataWithJSONObject:@{@"event": @"progress",
    @"sequence": @(sequence), @"frame": @(sequence % ([self style] == NSProgressIndicatorSpinningStyle ? 8 : 6) + 1),
    @"scale": @([[self window] backingScaleFactor]),
    @"x": @(box.origin.x), @"y": @(box.origin.y),
    @"width": @(box.size.width), @"height": @(box.size.height),
    @"content_height": @([[[self window] contentView] frame].size.height)} options:0 error:NULL];
  fwrite([json bytes],1,[json length],stdout);puts("");fflush(stdout);
}
@end

@interface ArtworkDelegate : NSObject
{
  NSMutableArray *windows;
  NSMutableArray *tabViews;
  NSStepper *stepper;
  ArtworkProgress *progress;
  NSImage *artwork;
}
@end

@implementation ArtworkDelegate
- (void)advanceProgress:(id)sender
{
  [progress animate:sender];
}
- (void)reportStepper:(id)sender
{
  NSMutableArray *buttons = [NSMutableArray array];
  for (NSInteger up = 0; up < 2; up++) {
    NSRect rect = up ? [[GSTheme theme] stepperUpButtonRectWithFrame:[stepper bounds]] :
      [[GSTheme theme] stepperDownButtonRectWithFrame:[stepper bounds]];
    rect = [stepper convertRect:rect toView:nil];
    [buttons addObject:@{@"up": @(up), @"x": @(rect.origin.x), @"y": @(rect.origin.y),
      @"width": @(rect.size.width), @"height": @(rect.size.height)}];
  }
  NSData *data = [NSJSONSerialization dataWithJSONObject:@{@"event": @"stepper",
    @"value": @([stepper integerValue]), @"buttons": buttons,
    @"content_height": @([[[windows firstObject] contentView] frame].size.height)} options:0 error:NULL];
  fwrite([data bytes],1,[data length],stdout);puts("");fflush(stdout);
}
- (void)reportTabs
{
  NSMutableArray *views = [NSMutableArray array];
  for (NSTabView *view in tabViews) {
    NSRect boxes[3] = {NSZeroRect, NSZeroRect, NSZeroRect};
    BOOL found[3] = {NO, NO, NO};
    NSRect bounds = [view bounds];
    // Use public hit testing to locate the actual headers after layout.
    for (NSInteger y = 0; y < NSHeight(bounds); y++)
      for (NSInteger x = 0; x < NSWidth(bounds); x++) {
        NSTabViewItem *item = [view tabViewItemAtPoint:NSMakePoint(x + .5, y + .5)];
        NSInteger index = item ? [view indexOfTabViewItem:item] : NSNotFound;
        if (index == NSNotFound) continue;
        NSRect point = NSMakeRect(x, y, 1, 1);
        boxes[index] = found[index] ? NSUnionRect(boxes[index], point) : point;
        found[index] = YES;
      }
    NSMutableArray *headers = [NSMutableArray array];
    for (NSInteger index = 0; index < 3; index++) {
      if (!found[index]) continue;
      NSRect rect = [view convertRect:boxes[index] toView:nil];
      [headers addObject:@{@"index": @(index), @"x": @(rect.origin.x), @"y": @(rect.origin.y),
        @"width": @(rect.size.width), @"height": @(rect.size.height)}];
    }
    [views addObject:@{@"orientation": [view tabViewType] == NSTopTabsBezelBorder ? @"top" : @"bottom",
      @"selected": @([view indexOfTabViewItem:[view selectedTabViewItem]]), @"headers": headers}];
  }
  NSWindow *window = [windows firstObject];
  NSData *json = [NSJSONSerialization dataWithJSONObject:@{@"event": @"tabs", @"views": views,
    @"content_height": @([[window contentView] frame].size.height)} options:0 error:NULL];
  fwrite([json bytes], 1, [json length], stdout); puts(""); fflush(stdout);
}
- (void)tabView:(NSTabView *)view didSelectTabViewItem:(NSTabViewItem *)item
{
  if ([tabViews count] == 2) [self performSelector:@selector(reportTabs) withObject:nil afterDelay:.05];
}
- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)application
{
  return [[NSUserDefaults standardUserDefaults] boolForKey:@"ArtworkTabs"] ||
    [[NSUserDefaults standardUserDefaults] boolForKey:@"ArtworkSteppers"] ||
    [[NSUserDefaults standardUserDefaults] boolForKey:@"ArtworkPatterns"] ||
    [[NSUserDefaults standardUserDefaults] boolForKey:@"ArtworkProgress"];
}
- (void)applicationDidFinishLaunching:(NSNotification *)notification
{
  NSUInteger artworkStyle = [[NSUserDefaults standardUserDefaults] boolForKey:@"ArtworkDecorations"] ?
    (NSTitledWindowMask | NSClosableWindowMask | NSMiniaturizableWindowMask | NSResizableWindowMask) : NSBorderlessWindowMask;
  if ([[NSUserDefaults standardUserDefaults] boolForKey:@"ArtworkProgress"]) {
    NSWindow *window = [[NSWindow alloc] initWithContentRect:NSMakeRect(20,20,256,112)
      styleMask:NSTitledWindowMask | NSClosableWindowMask backing:NSBackingStoreBuffered defer:NO];
    [window setTitle:@"ProgressArtwork"];
    windows = [[NSMutableArray alloc] initWithObjects:window,nil];
    BOOL spinning = [[NSUserDefaults standardUserDefaults] boolForKey:@"ArtworkSpinner"];
    progress = [[ArtworkProgress alloc] initWithFrame:NSMakeRect(16,64,spinning ? 32 : 224,spinning ? 32 : 24)];
    [progress setStyle:spinning ? NSProgressIndicatorSpinningStyle : NSProgressIndicatorBarStyle];
    [progress setIndeterminate:YES]; [progress setBezeled:!spinning]; [progress setDisplayedWhenStopped:YES];
    [[window contentView] addSubview:progress];[progress release];
    NSButton *next = [[NSButton alloc] initWithFrame:NSMakeRect(80,16,96,28)];
    [next setTitle:@"Next Frame"];[next setTarget:self];[next setAction:@selector(advanceProgress:)];
    [[window contentView] addSubview:next];[next release];
    [window makeKeyAndOrderFront:nil];[window release];
    return;
  }
  if ([[NSUserDefaults standardUserDefaults] boolForKey:@"ArtworkPatterns"]) {
    BOOL transforms = [[NSUserDefaults standardUserDefaults] boolForKey:@"ArtworkPatternTransforms"];
    NSSize size = transforms ? NSMakeSize(320,720) : NSMakeSize(128,216);
    NSWindow *window = [[NSWindow alloc] initWithContentRect:NSMakeRect(20,20,size.width,size.height)
      styleMask:NSTitledWindowMask | NSClosableWindowMask backing:NSBackingStoreBuffered defer:NO];
    [window setTitle:@"PatternArtwork"]; windows = [[NSMutableArray alloc] initWithObjects:window,nil];
    Class viewClass = transforms ? [PatternTransformView class] : [PatternArtworkView class];
    NSView *view = [[viewClass alloc] initWithFrame:NSMakeRect(0,0,size.width,size.height)];
    [window setContentView:view]; [view release]; [window makeKeyAndOrderFront:nil]; [window release];
    return;
  }
  if ([[NSUserDefaults standardUserDefaults] boolForKey:@"ArtworkSteppers"]) {
    NSWindow *window = [[NSWindow alloc] initWithContentRect:NSMakeRect(20,20,128,80)
      styleMask:NSTitledWindowMask | NSClosableWindowMask backing:NSBackingStoreBuffered defer:NO];
    [window setTitle:@"StepperArtwork"];
    windows = [[NSMutableArray alloc] initWithObjects:window,nil];
    stepper = [[NSStepper alloc] initWithFrame:NSMakeRect(54,25,19,27)];
    [stepper setMinValue:0];[stepper setMaxValue:100];[stepper setIncrement:1];
    [stepper setIntegerValue:50];[stepper setAutorepeat:NO];
    [stepper setTarget:self];[stepper setAction:@selector(reportStepper:)];
    [[window contentView] addSubview:stepper];[stepper release];
    [window makeKeyAndOrderFront:nil];[window release];
    [self performSelector:@selector(reportStepper:) withObject:nil afterDelay:.1];
    return;
  }
  if ([[NSUserDefaults standardUserDefaults] boolForKey:@"ArtworkTabs"]) {
    NSWindow *window = [[NSWindow alloc] initWithContentRect:NSMakeRect(20,20,360,190)
      styleMask:NSTitledWindowMask | NSClosableWindowMask backing:NSBackingStoreBuffered defer:NO];
    [window setTitle:@"TabArtwork"];
    windows = [[NSMutableArray alloc] initWithObjects:window,nil];
    tabViews = [NSMutableArray new];
    NSArray *labels = @[@"First", @"Second", @"Third"];
    for (NSInteger orientation = 0; orientation < 2; orientation++) {
      NSTabView *view = [[NSTabView alloc] initWithFrame:NSMakeRect(12,12 + orientation * 88,336,76)];
      [view setTabViewType:orientation ? NSTopTabsBezelBorder : NSBottomTabsBezelBorder];
      for (NSInteger index = 0; index < 3; index++) {
        NSTabViewItem *item = [[NSTabViewItem alloc] initWithIdentifier:@(index)];
        [item setLabel:[labels objectAtIndex:index]];
        [view addTabViewItem:item]; [item release];
      }
      [view setDelegate:self];
      [[window contentView] addSubview:view];
      [tabViews addObject:view]; [view release];
    }
    [window makeKeyAndOrderFront:nil]; [window release];
    [self performSelector:@selector(reportTabs) withObject:nil afterDelay:.1];
    return;
  }
  if ([[NSUserDefaults standardUserDefaults] boolForKey:@"ArtworkButtons"]) {
    NSWindow *window = [[NSWindow alloc] initWithContentRect:NSMakeRect(20,20,128,64)
      styleMask:artworkStyle backing:NSBackingStoreBuffered defer:NO];
    [window setTitle:@"ButtonArtwork"];
    NSMutableArray *records = [NSMutableArray array];
    for (NSUInteger index = 0; index < 4; index++) {
      NSButton *button = [[NSButton alloc] initWithFrame:NSMakeRect(8+index*28,24,20,20)];
      [button setButtonType:index < 2 ? NSRadioButton : NSSwitchButton];
      [button setTitle:@""]; [button setState:index%2];
      // Compare artwork without the keyboard-focus frame drawn over it.
      [button setRefusesFirstResponder:YES];
      [[button cell] setImagePosition:NSImageOnly];
      NSImage *image = index%2 ? [[button cell] alternateImage] : [[button cell] image];
      NSSize size = [image size]; [button setFrameSize:size];
      [[window contentView] addSubview:button];
      NSMutableArray *representations = [NSMutableArray array];
      for (NSImageRep *rep in [image representations])
        if ([rep isKindOfClass:[NSBitmapImageRep class]])
          [representations addObject:[NSArray arrayWithObjects:[NSNumber numberWithInteger:[rep pixelsWide]],
            [NSNumber numberWithInteger:[rep pixelsHigh]], nil]];
      NSRect rect = [button convertRect:[button bounds] toView:nil];
      NSString *name = [NSString stringWithFormat:@"common_%@%@", index < 2 ? @"Radio" : @"Switch", index%2 ? @"On" : @"Off"];
      [records addObject:[NSDictionary dictionaryWithObjectsAndKeys:name,@"name",representations,@"representations",
        [NSArray arrayWithObjects:[NSNumber numberWithDouble:rect.origin.x],[NSNumber numberWithDouble:rect.origin.y],
          [NSNumber numberWithDouble:rect.size.width],[NSNumber numberWithDouble:rect.size.height],nil],@"base",nil]];
      [button release];
    }
    [window orderFront:nil]; windows = [[NSMutableArray alloc] initWithObjects:window,nil]; [window release];
    NSData *json = [NSJSONSerialization dataWithJSONObject:records options:0 error:NULL];
    fwrite([json bytes],1,[json length],stdout); puts(""); fflush(stdout); return;
  }
  BOOL dimples = [[NSUserDefaults standardUserDefaults] boolForKey:@"ArtworkDimples"];
  if (dimples || [[NSUserDefaults standardUserDefaults] boolForKey:@"ArtworkScrollers"]) {
    NSWindow *window = [[NSWindow alloc] initWithContentRect:NSMakeRect(20,20,260,150)
      styleMask:artworkStyle backing:NSBackingStoreBuffered defer:NO];
    [window setTitle:dimples ? @"DimpleArtwork" : @"ScrollerArtwork"];
    NSMutableArray *arrows = [NSMutableArray array];
    for (NSUInteger index = 0; index < (dimples ? 2 : 4); index++) {
      BOOL horizontal = index >= (dimples ? 1 : 2), highlighted = dimples ? NO : index % 2;
      ArtworkScroller *scroller = [[ArtworkScroller alloc] initWithFrame:horizontal ?
        NSMakeRect(100,20+index%2*50,140,18) : NSMakeRect(20+index*40,20,18,120)];
      [scroller setTag:highlighted];
      [scroller setArrowsPosition:NSScrollerArrowsMaxEnd];
      [scroller setDoubleValue:.4]; [scroller setKnobProportion:.3];
      [[window contentView] addSubview:scroller];
      for (NSUInteger part = 0; part < (dimples ? 1 : 2); part++) {
        NSString *direction = horizontal ? (part ? @"Right" : @"Left") : (part ? @"Down" : @"Up");
        NSString *name = dimples ? (horizontal ? @"common_DimpleHoriz" : @"common_Dimple") :
          [NSString stringWithFormat:@"common_Arrow%@%@", direction, highlighted ? @"H" : @""];
        NSImage *image = [NSImage imageNamed:name];
        NSMutableArray *sizes = [NSMutableArray array];
        for (NSImageRep *rep in [image representations])
          if ([rep isKindOfClass:[NSBitmapImageRep class]])
            [sizes addObject:[NSArray arrayWithObjects:[NSNumber numberWithInteger:[rep pixelsWide]],
              [NSNumber numberWithInteger:[rep pixelsHigh]], nil]];
        NSRect partRect = [scroller rectForPart:dimples ? NSScrollerKnob : part ? NSScrollerIncrementLine : NSScrollerDecrementLine];
        NSRect rect = [scroller convertRect:partRect toView:nil];
        GSTheme *theme = [GSTheme theme];
        NSButtonCell *cell = dimples ? (NSButtonCell *)[theme cellForScrollerKnob:horizontal] :
          [theme cellForScrollerArrow:part ? NSScrollerIncrementArrow : NSScrollerDecrementArrow horizontal:horizontal];
        NSRect drawingRect = partRect;
        if ([cell isBordered]) {
          GSThemeMargins margins = [theme buttonMarginsForCell:cell style:[cell bezelStyle]
            state:highlighted ? GSThemeHighlightedState : GSThemeNormalState];
          drawingRect.origin.x += margins.left;
          drawingRect.origin.y += [scroller isFlipped] ? margins.top : margins.bottom;
          drawingRect.size.width -= margins.left + margins.right;
          drawingRect.size.height -= margins.top + margins.bottom;
        }
        NSRect drawingBase = [scroller convertRect:drawingRect toView:nil];
        [arrows addObject:[NSDictionary dictionaryWithObjectsAndKeys:name, @"name", sizes, @"representations",
          [NSArray arrayWithObjects:[NSNumber numberWithDouble:rect.origin.x], [NSNumber numberWithDouble:rect.origin.y],
            [NSNumber numberWithDouble:rect.size.width], [NSNumber numberWithDouble:rect.size.height], nil], @"base",
          [NSArray arrayWithObjects:@(drawingBase.origin.x), @(drawingBase.origin.y),
            @(drawingBase.size.width), @(drawingBase.size.height), nil], @"drawing_base", nil]];
      }
      [scroller release];
    }
    [window orderFront:nil]; windows = [[NSMutableArray alloc] initWithObjects:window, nil]; [window release];
    NSData *json = [NSJSONSerialization dataWithJSONObject:arrows options:0 error:NULL];
    fwrite([json bytes], 1, [json length], stdout); puts(""); fflush(stdout); return;
  }
  NSString *path = [[NSUserDefaults standardUserDefaults] stringForKey:@"ArtworkImage"];
  NSString *name = [[NSUserDefaults standardUserDefaults] stringForKey:@"ArtworkImageName"];
  NSImage *image = artwork = name ? [[NSImage imageNamed:name] retain] :
    [[NSImage alloc] initWithContentsOfFile:path];
  if (!image) { NSLog(@"Cannot load artwork: %@", name ?: path); exit(1); }
  NSRect canvasFrame = NSMakeRect(0,0,64,64);
  if ([[NSUserDefaults standardUserDefaults] boolForKey:@"ArtworkCanvas"])
    canvasFrame.size = NSMakeSize(MAX(64,[image size].width+16), MAX(64,[image size].height+16));
  windows = [NSMutableArray new];
  for (int index = 0; index < 2; index++) {
    NSWindow *window = [[NSWindow alloc] initWithContentRect:NSMakeRect(20+index*80,20,canvasFrame.size.width,canvasFrame.size.height)
      styleMask:NSBorderlessWindowMask backing:NSBackingStoreBuffered defer:NO];
    [window setTitle:index ? @"ArtworkBackground" : @"ArtworkProbe"];
    NSView *view;
#ifdef TERMINAL_ARTWORK
    if (index) view = [[NSView alloc] initWithFrame:canvasFrame];
    else {
      TerminalIcon *icon = [[TerminalArtworkView alloc] initWithFrame:canvasFrame
        scrollingFrame:NSMakeRect(13,17,27,23)];
      [icon setIconImage:image]; view = icon;
      NSString *strip = [[NSUserDefaults standardUserDefaults] stringForKey:@"ArtworkStrip"];
      if (strip) [icon setScrollingImage:[[NSImage alloc] initWithContentsOfFile:strip]];
    }
#else
    Class imageView = [[NSUserDefaults standardUserDefaults] boolForKey:@"ArtworkCanvas"] ? [ArtworkCanvas class] : [WSIconTileView class];
    view = [[imageView alloc] initWithFrame:canvasFrame];
    if (!index) [(WSIconTileView *)view setImage:image];
#endif
    [window setContentView:view]; [view release];
    [window orderFront:nil]; [windows addObject:window]; [window release];
  }
  NSMutableDictionary *report = [NSMutableDictionary dictionaryWithObjectsAndKeys:
    [NSNumber numberWithDouble:[image size].width], @"logical_width",
    [NSNumber numberWithDouble:[image size].height], @"logical_height", nil];
  if (name) {
    [report setObject:name forKey:@"requested_name"];
    [report setObject:[image valueForKey:@"fileName"] ?: @"" forKey:@"resource"];
  }
  NSData *json = [NSJSONSerialization dataWithJSONObject:report options:0 error:NULL];
  fwrite([json bytes], 1, [json length], stdout); puts("");
  fflush(stdout);
}
- (void)dealloc { [windows release]; [tabViews release]; [artwork release]; [super dealloc]; }
@end

int main(int argc, char **argv)
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  [NSApplication sharedApplication];
  ArtworkDelegate *delegate = [ArtworkDelegate new];
  [NSApp setDelegate:delegate]; [NSApp run];
  [delegate release]; [pool drain];
  return 0;
}
