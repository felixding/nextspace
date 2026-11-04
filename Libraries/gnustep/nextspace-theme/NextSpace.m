#import <AppKit/AppKit.h>

#import "NextSpace.h"
#import "NXTScrollerKnobSlotCell.h"

@implementation NextSpace

@synthesize knobSlotPattern;

#pragma mark - Init & dealloc

- (void)dealloc
{
  [knobSlotPattern release];
  [super dealloc];
}

+ (BOOL)drawKnobSlotPattern:(NSCustomImageRep *)representation
{
  [[NSColor colorWithDeviceWhite:2.0/3.0 alpha:1.0] set];
  NSRectFill(NSMakeRect(0,0,12,12));
  NSBezierPath *checks=[NSBezierPath bezierPath];
  for (NSInteger y=0;y<12;y++)
    for (NSInteger x=1-y%2;x<12;x+=2)
      [checks appendBezierPathWithRect:NSMakeRect(x,y,1,1)];
  [[NSColor colorWithDeviceWhite:1.0/3.0 alpha:1.0] set];
  [checks fill];
  return YES;
}

- (NSImage *)knobSlotPattern
{
  if (knobSlotPattern == nil) {
    knobSlotPattern=[[NSImage alloc] initWithSize:NSMakeSize(12,12)];
    NSCustomImageRep *representation=[[NSCustomImageRep alloc]
      initWithDrawSelector:@selector(drawKnobSlotPattern:) delegate:[self class]];
    [representation setSize:NSMakeSize(12,12)];
    [knobSlotPattern addRepresentation:representation];
    [representation release];
  }
  return knobSlotPattern;
}

#pragma mark - NSScroller

- (NSCell *)cellForScrollerKnobSlot:(BOOL)horizontal
{
  NXTScrollerKnobSlotCell *cell;

  cell = [NXTScrollerKnobSlotCell new];
  [cell setBordered:NO];
  [cell setTitle:nil];

  return cell;
}

#pragma mark - NSSlider

- (void)drawSliderBorderAndBackground:(NSBorderType)aType
                                frame:(NSRect)cellFrame
                               inCell:(NSCell *)cell
                         isHorizontal:(BOOL)horizontal
{
  if (NSIsEmptyRect(cellFrame)) {
    return;
  }

  if (aType == NSBezelBorder) {
    [self drawGrayBezel:cellFrame withClip:NSZeroRect];
  } else {
    [[GSTheme theme] drawBorderType:aType frame:cellFrame view:[cell controlView]];
  }
}

- (void)drawBarInside:(NSRect)rect inCell:(NSCell *)cell flipped:(BOOL)flipped
{
  if (NSIsEmptyRect(rect)) {
    return;
  }

  NSGraphicsContext *ctxt = GSCurrentContext();
  if ([[ctxt className] isEqualToString:@"CairoContext"]) {
    [ctxt GSSetPatterColor:self.knobSlotPattern];
    [ctxt DPSrectfill:rect.origin.x :rect.origin.y :rect.size.width :rect.size.height];
  }
}

// - (void)drawKnobInCell:(NSCell *)cell
// {
//   NSLog(@"%s", __func__);

//   NSView *controlView = [cell controlView];
//   NSSliderCell *sliderCell = (NSSliderCell *)cell;
//   NSRect knobRect = [sliderCell knobRectFlipped:[controlView isFlipped]];

//   [sliderCell drawKnob:knobRect];
// }

@end

