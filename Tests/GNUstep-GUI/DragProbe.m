/* Exercise the actual AppKit dragging API. SPDX-License-Identifier: MIT */
#import <AppKit/AppKit.h>

static void report(NSDictionary *event)
{
  NSData *bytes = [NSJSONSerialization dataWithJSONObject:event options:0 error:NULL];
  fwrite([bytes bytes], 1, [bytes length], stdout); putchar('\n'); fflush(stdout);
}
static void reportDragBegan(void)
{
  report([NSDictionary dictionaryWithObject:@"drag-begin" forKey:@"event"]);
  NSTimeInterval delay = [[NSUserDefaults standardUserDefaults] doubleForKey:@"DragBeginDelay"];
  if (delay > 0) [NSThread sleepForTimeInterval:MIN(delay, 1.0)];
}
static NSColor *dragColor(void)
{ return [NSColor colorWithCalibratedRed:.2 green:.4 blue:.6 alpha:.5]; }
@interface DragProbeLegacySource : NSObject
@end
@implementation DragProbeLegacySource
- (NSDragOperation)draggingSourceOperationMaskForLocal:(BOOL)local { return NSDragOperationCopy; }
- (void)draggedImage:(NSImage *)image beganAt:(NSPoint)point
{ reportDragBegan(); }
- (void)draggedImage:(NSImage *)image endedAt:(NSPoint)point deposited:(BOOL)deposited
{
  report([NSDictionary dictionaryWithObjectsAndKeys:@"drag-end", @"event",
    [NSNumber numberWithBool:deposited], @"action", [NSNumber numberWithDouble:point.x], @"x",
    [NSNumber numberWithDouble:point.y], @"y", [NSNumber numberWithBool:YES], @"legacy", nil]);
}
@end
@interface DragProbeView : NSView
@end
@implementation DragProbeView
- (BOOL)acceptsFirstMouse:(NSEvent *)event { return YES; }
- (void)drawRect:(NSRect)rect
{
  [[NSColor lightGrayColor] set]; NSRectFill([self bounds]);
  [@"Native AppKit drag and drop" drawAtPoint:NSMakePoint(20, 40) withAttributes:nil];
}
- (NSDragOperation)draggingSourceOperationMaskForLocal:(BOOL)local
{
  NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
  if ([defaults boolForKey:@"GenericDrag"]) return NSDragOperationGeneric;
  if (!local && [defaults boolForKey:@"ReentrantMove"]) {
    NSPoint origin = [[self window] frame].origin;
    [[self window] setFrameOrigin:NSMakePoint(origin.x + 37, origin.y + 29)];
  }
  return [defaults boolForKey:@"MoveDrag"] || (local && [defaults boolForKey:@"LocalMove"]) ?
    NSDragOperationMove : NSDragOperationCopy;
}
- (void)drawDragImage:(NSCustomImageRep *)representation
{
  [([[NSUserDefaults standardUserDefaults] boolForKey:@"ColorDrag"] ? dragColor() : [NSColor redColor]) set];
  NSRectFill(NSMakeRect(0, 0, 33, 31));
}
- (void)mouseDown:(NSEvent *)event
{
  NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
  if (![[[self window] title] isEqual:@"NativeDragSource"]) return;
  NSPasteboard *pasteboard = [NSPasteboard pasteboardWithName:NSDragPboard];
  if ([defaults boolForKey:@"ColorDrag"]) {
    [pasteboard declareTypes:@[NSColorPboardType] owner:nil];
    [dragColor() writeToPasteboard:pasteboard];
    NSData *colorData = [pasteboard dataForType:NSColorPboardType];
    NSAssert([colorData length]>0, @"The color source must publish encoded color data");
    report(@{@"event":@"color-offer",@"bytes":@([colorData length]),
      @"base64":[colorData base64EncodedStringWithOptions:0]});
  } else {
    NSString *file = [defaults stringForKey:@"DragFile"];
    NSString *type = file ? NSFilenamesPboardType : NSStringPboardType;
    BOOL mixed = [defaults boolForKey:@"TextWithFile"];
    [pasteboard declareTypes:mixed ? [NSArray arrayWithObjects:NSFilenamesPboardType, NSStringPboardType, nil] :
      [NSArray arrayWithObject:type] owner:nil];
    if (file) [pasteboard setPropertyList:[NSArray arrayWithObject:file] forType:type];
    if (!file || mixed) {
      NSUInteger repeat = MAX(1, MIN(1048576, [defaults integerForKey:@"DragRepeat"]));
      NSUInteger index;
      NSMutableString *text = [NSMutableString string];
      for (index = 0; index < repeat; index++) [text appendString:@"NextSpace日本語"];
      [pasteboard setString:text forType:NSStringPboardType];
    }
  }
  NSImage *image = [[[NSImage alloc] initWithSize:NSMakeSize(33, 31)] autorelease];
  NSCustomImageRep *representation = [[[NSCustomImageRep alloc]
    initWithDrawSelector:@selector(drawDragImage:) delegate:self] autorelease];
  [representation setSize:[image size]]; [image addRepresentation:representation];
  NSPoint point = [self convertPoint:[event locationInWindow] fromView:nil];
  id source = [defaults boolForKey:@"LegacySource"] ? [[[DragProbeLegacySource alloc] init] autorelease] : self;
  [self dragImage:image at:NSMakePoint(point.x - 8, point.y - 8) offset:NSZeroSize
    event:event pasteboard:pasteboard source:source slideBack:YES];
}
- (void)draggedImage:(NSImage *)image beganAt:(NSPoint)point
{ reportDragBegan(); }
- (void)draggedImage:(NSImage *)image endedAt:(NSPoint)point operation:(NSDragOperation)operation
{
  report([NSDictionary dictionaryWithObjectsAndKeys:@"drag-end", @"event",
    [NSNumber numberWithUnsignedInteger:operation], @"action",
    [NSNumber numberWithDouble:point.x], @"x", [NSNumber numberWithDouble:point.y], @"y", nil]);
}
- (NSDragOperation)draggingEntered:(id<NSDraggingInfo>)info
{
  report([NSDictionary dictionaryWithObjectsAndKeys:@"drag-enter", @"event", [[self window] title], @"window",
    [NSNumber numberWithInteger:[info draggingSequenceNumber]], @"sequence", nil]);
  return [info draggingSourceOperationMask] & (NSDragOperationCopy | NSDragOperationMove);
}
- (NSDragOperation)draggingUpdated:(id<NSDraggingInfo>)info
{ return [info draggingSourceOperationMask] & (NSDragOperationCopy | NSDragOperationMove); }
- (BOOL)prepareForDragOperation:(id<NSDraggingInfo>)info
{ return ![[NSUserDefaults standardUserDefaults] boolForKey:@"RejectDrop"]; }
- (BOOL)performDragOperation:(id<NSDraggingInfo>)info
{
  NSPasteboard *pasteboard = [info draggingPasteboard];
  NSMutableDictionary *event = [NSMutableDictionary dictionaryWithObject:@"drop" forKey:@"event"];
  if ([[pasteboard types] containsObject:NSColorPboardType]) {
    NSColor *color = [[NSColor colorFromPasteboard:pasteboard] colorUsingColorSpaceName:NSCalibratedRGBColorSpace];
    if (!color) return NO;
    CGFloat r,g,b,a; [color getRed:&r green:&g blue:&b alpha:&a];
    [event setObject:@[@(r),@(g),@(b),@(a)] forKey:@"rgba"];
  } else if ([[pasteboard types] containsObject:NSFilenamesPboardType]) {
    id paths = [pasteboard propertyListForType:NSFilenamesPboardType];
    if (![paths isKindOfClass:[NSArray class]] || ![paths count]) return NO;
    [event setObject:paths forKey:@"files"];
    if ([[NSUserDefaults standardUserDefaults] boolForKey:@"TextWithFile"]) {
      NSString *text = [pasteboard stringForType:NSStringPboardType];
      if (!text) return NO;
      [event setObject:[[text dataUsingEncoding:NSUTF8StringEncoding] base64EncodedStringWithOptions:0] forKey:@"base64"];
    }
  } else {
    NSString *text = [pasteboard stringForType:NSStringPboardType];
    if (!text) return NO;
    [event setObject:[[text dataUsingEncoding:NSUTF8StringEncoding] base64EncodedStringWithOptions:0] forKey:@"base64"];
  }
  [event setObject:[NSNumber numberWithDouble:[info draggingLocation].x] forKey:@"x"];
  [event setObject:[NSNumber numberWithDouble:[info draggingLocation].y] forKey:@"y"];
  [event setObject:[NSNumber numberWithBool:[info draggingSource] != nil] forKey:@"local"];
  [event setObject:[NSNumber numberWithInteger:[info draggingSequenceNumber]] forKey:@"sequence"];
  if ([info draggingSource]) {
    NSPoint image = [info draggedImageLocation];
    [event setObject:[NSNumber numberWithDouble:image.x] forKey:@"image_x"];
    [event setObject:[NSNumber numberWithDouble:image.y] forKey:@"image_y"];
  }
  report(event); return YES;
}
@end
@interface DragProbeWindow : NSWindow
@end
@implementation DragProbeWindow
- (BOOL)canBecomeKeyWindow { return YES; }
- (BOOL)canBecomeMainWindow { return YES; }
- (void)performClose:(id)sender { [self close]; }
@end
@interface DragProbe : NSObject
@end
@implementation DragProbe
- (void)openWindow:(BOOL)source
{
  NSUInteger style = [[NSUserDefaults standardUserDefaults] boolForKey:@"FramedDrag"] ?
    NSTitledWindowMask | NSClosableWindowMask | NSMiniaturizableWindowMask | NSResizableWindowMask : NSBorderlessWindowMask;
  NSRect content = [NSWindow contentRectForFrameRect:NSMakeRect(0, 0, 401, 301) styleMask:style];
  NSWindow *window = [[DragProbeWindow alloc] initWithContentRect:content
    styleMask:style backing:NSBackingStoreBuffered defer:NO];
  [window setReleasedWhenClosed:NO];
  [window setTitle:source ? @"NativeDragSource" : @"NativeDragTarget"];
  DragProbeView *view = [[DragProbeView alloc] initWithFrame:[[window contentView] bounds]];
  [view registerForDraggedTypes:[[NSUserDefaults standardUserDefaults] boolForKey:@"ColorDrag"] ?
    @[NSColorPboardType,NSStringPboardType,NSFilenamesPboardType] : @[NSStringPboardType,NSFilenamesPboardType]];
  [window setContentView:view]; [view release]; [window makeKeyAndOrderFront:nil];
}
- (void)applicationDidFinishLaunching:(NSNotification *)notification
{
  NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
  [self openWindow:[defaults boolForKey:@"DragSource"]];
  if ([defaults boolForKey:@"SameClient"]) [self openWindow:NO];
}
@end
int main(int argc, char **argv)
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  [NSApplication sharedApplication];
  DragProbe *probe = [DragProbe new]; [NSApp setDelegate:probe]; [NSApp run];
  [probe release]; [pool drain]; return 0;
}
