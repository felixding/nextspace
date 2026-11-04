/* Native pattern color, format, phase and clipping fixtures. GPL-2.0-or-later. */
static NSBitmapImageRep *patternRep(NSInteger factor, BOOL alpha, BOOL stripes)
{
  NSInteger width=8*factor,height=8*factor;
  NSBitmapImageRep *rep = [[[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL
    pixelsWide:width pixelsHigh:height bitsPerSample:8 samplesPerPixel:4 hasAlpha:YES
    isPlanar:NO colorSpaceName:NSDeviceRGBColorSpace bitmapFormat:NSAlphaNonpremultipliedBitmapFormat
    bytesPerRow:width*4 bitsPerPixel:32] autorelease];
  [rep setSize:NSMakeSize(8,8)];
  for (NSInteger y=0;y<height;y++) for (NSInteger x=0;x<width;x++) {
    unsigned char *p=[rep bitmapData]+y*[rep bytesPerRow]+x*4;
    if (stripes) p[0]=p[1]=p[2]=(x%2) ? 255 : 0;
    else {p[0]=factor==1 ? 255 : 0;p[1]=0;p[2]=factor==1 ? 0 : 255;}
    if (alpha) {p[0]=factor==1 ? 200 : 40;p[1]=factor==1 ? 80 : 160;p[2]=factor==1 ? 40 : 220;}
    p[3]=alpha ? 128 : 255;
  }
  return rep;
}
static NSBitmapImageRep *formatPatternRep(NSInteger factor, NSInteger profile)
{
  if (profile<3 || profile==6) return patternRep(factor,profile==1,profile==2);
  NSInteger width=8*factor,height=8*factor;
  BOOL gray=profile==4,planar=profile==5;
  NSBitmapImageRep *rep=[[[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL
    pixelsWide:width pixelsHigh:height bitsPerSample:8 samplesPerPixel:gray ? 1 : 3 hasAlpha:NO
    isPlanar:planar colorSpaceName:gray ? NSCalibratedWhiteColorSpace : NSDeviceRGBColorSpace
    bytesPerRow:width*(gray || planar ? 1 : 3) bitsPerPixel:gray || planar ? 8 : 24] autorelease];
  [rep setSize:NSMakeSize(8,8)];unsigned char *planes[5];[rep getBitmapDataPlanes:planes];
  for (NSInteger y=0;y<height;y++) for (NSInteger x=0;x<width;x++) {
    if (gray) planes[0][y*[rep bytesPerRow]+x]=170;
    else if (planar) {planes[0][y*[rep bytesPerRow]+x]=64;planes[1][y*[rep bytesPerRow]+x]=192;planes[2][y*[rep bytesPerRow]+x]=32;}
    else {unsigned char *p=planes[0]+y*[rep bytesPerRow]+x*3;p[0]=p[2]=0;p[1]=255;}
  }
  return rep;
}
@interface PatternArtworkView : NSView @end
@implementation PatternArtworkView
- (BOOL)drawPatternVector:(NSCustomImageRep *)unused
{
  [[NSColor greenColor] set];NSRectFill(NSMakeRect(0,0,8,8));
  [[NSColor blackColor] set];NSRectFill(NSMakeRect(3,3,2,2));return YES;
}
- (void)drawRect:(NSRect)dirty
{
  [[NSColor whiteColor] set];NSRectFill([self bounds]);
  NSMutableArray *samples=[NSMutableArray array];
  for (NSInteger i=0;i<8;i++) {
    NSImage *image=[[[NSImage alloc] initWithSize:NSMakeSize(8,8)] autorelease];
    if (i==7) {
      NSCustomImageRep *rep=[[[NSCustomImageRep alloc] initWithDrawSelector:@selector(drawPatternVector:) delegate:self] autorelease];
      [rep setSize:NSMakeSize(8,8)];[image addRepresentation:rep];
    } else {
      [image addRepresentation:formatPatternRep(1,i)];
      [image addRepresentation:formatPatternRep(2,i)];
    }
    [[NSColor colorWithPatternImage:image] set];
    NSRect rect=NSMakeRect(8,8+24*i,96,16);
    if (i==6) [[NSBezierPath bezierPathWithOvalInRect:rect] fill];
    else NSRectFill(rect);
    NSBitmapImageRep *read=[[[NSBitmapImageRep alloc] initWithFocusedViewRect:rect] autorelease];
    NSColor *color=[[read colorAtX:3 y:3] colorUsingColorSpaceName:NSDeviceRGBColorSpace];
    [samples addObject:@{@"index":@(i),@"red":@([color redComponent]),
      @"green":@([color greenComponent]),@"blue":@([color blueComponent])}];
  }
  NSData *json=[NSJSONSerialization dataWithJSONObject:@{@"event":@"pattern",
    @"scale":@([[self window] backingScaleFactor]),@"samples":samples} options:0 error:NULL];
  fwrite([json bytes],1,[json length],stdout);puts("");fflush(stdout);
}
@end

@interface PatternTransformView : NSView @end
@implementation PatternTransformView
- (void)drawRect:(NSRect)dirty
{
  [[NSColor whiteColor] set];NSRectFill([self bounds]);
  NSImage *image=[[[NSImage alloc] initWithSize:NSMakeSize(8,6)] autorelease];
  for (NSInteger factor=1;factor<=2;factor++) {
    NSInteger width=8*factor,height=6*factor;
    NSBitmapImageRep *rep=[[[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL
      pixelsWide:width pixelsHigh:height bitsPerSample:8 samplesPerPixel:4 hasAlpha:YES
      isPlanar:NO colorSpaceName:NSDeviceRGBColorSpace bytesPerRow:width*4 bitsPerPixel:32] autorelease];
    [rep setSize:NSMakeSize(8,6)];
    for (NSInteger y=0;y<height;y++) for (NSInteger x=0;x<width;x++) {
      unsigned char *p=[rep bitmapData]+y*[rep bytesPerRow]+x*4;
      BOOL right=x>=width/2,bottom=y>=height/2;
      p[0]=(!right&&!bottom)||(right&&bottom) ? 255 : 0;
      p[1]=right ? 255 : 0;p[2]=(!right&&bottom) ? 255 : 0;p[3]=255;
    }
    [image addRepresentation:rep];
  }
  NSMutableArray *cases=[NSMutableArray array];
  for (NSInteger profile=0;profile<9;profile++) {
    NSPoint phase=(profile==0 || profile>=7) ? NSZeroPoint : NSMakePoint(3,2);
    NSMutableArray *pairs=[NSMutableArray array];NSAffineTransform *transforms[2];
    for (NSInteger reference=0;reference<2;reference++) {
      [NSGraphicsContext saveGraphicsState];
      NSAffineTransformStruct m={1,0,0,1,8+160*reference,24+80*profile};
      if (profile==2) {m.m11=1.5;m.m22=1.25;}
      else if (profile==3) {m.m11=m.m22=0;m.m12=1;m.m21=-1;m.tX+=46;m.tY-=26;}
      else if (profile==4) {m.m22=-1;m.tY+=20;}
      NSAffineTransform *t=[NSAffineTransform transform];[t setTransformStruct:m];[t concat];transforms[reference]=t;
      NSRect rect=NSMakeRect(0,0,72,20);
      NSBezierPath *shape=[NSBezierPath bezierPathWithRect:rect];
      if (profile==6) {[shape appendBezierPathWithRect:NSMakeRect(20,4,32,12)];[shape setWindingRule:NSEvenOddWindingRule];}
      if (profile==8) {
        NSRectClip(NSZeroRect);
        [NSGraphicsContext saveGraphicsState];
        [[NSColor redColor] set];NSRectFill(rect);
        [NSGraphicsContext restoreGraphicsState];
      } else if (reference) {
        [shape addClip];
        for (NSInteger y=-1;y<5;y++) for (NSInteger x=-1;x<10;x++)
          [image drawInRect:NSMakeRect(phase.x+x*8,phase.y+y*6,8,6) fromRect:NSZeroRect
            operation:NSCompositeSourceOver fraction:1];
      } else {
        if (profile!=5) [[NSGraphicsContext currentContext] setPatternPhase:phase];
        [[NSColor colorWithPatternImage:image] set];
        if (profile==5) [[NSGraphicsContext currentContext] setPatternPhase:phase];
        if (profile==7) {
          [NSGraphicsContext saveGraphicsState];
          [[NSGraphicsContext currentContext] setPatternPhase:NSMakePoint(3,2)];
          [NSGraphicsContext restoreGraphicsState];
        }
        [shape fill];
      }
      [NSGraphicsContext restoreGraphicsState];
    }
    for (NSInteger row=0;row<3;row++) for (NSInteger col=0;col<8;col++) {
      NSPoint local=NSMakePoint(phase.x+col*8+2,phase.y+row*6+1.5);
      if (local.x>=71 || local.y>=19) continue;
      NSPoint a=[transforms[0] transformPoint:local],b=[transforms[1] transformPoint:local];
      [pairs addObject:@{@"x":@(a.x),@"y":@(a.y),@"reference_x":@(b.x),@"reference_y":@(b.y)}];
    }
    [cases addObject:@{@"profile":@(profile),@"pairs":pairs}];
  }
  NSData *data=[NSJSONSerialization dataWithJSONObject:@{@"event":@"pattern-transform",
    @"scale":@([[self window] backingScaleFactor]),@"content_height":@([self bounds].size.height),@"cases":cases} options:0 error:NULL];
  fwrite([data bytes],1,[data length],stdout);puts("");fflush(stdout);
}
@end

