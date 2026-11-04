/* Optional test-only NSImage draw tracing. GPL-2.0-or-later. */
#import <AppKit/AppKit.h>
#import <objc/runtime.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdlib.h>

static void (*originalDraw)(id,SEL,NSRect,NSRect,NSCompositingOperation,CGFloat,BOOL,NSDictionary*);
static NSImageRep *(*originalBest)(id,SEL,NSRect,NSGraphicsContext*,NSDictionary*);
static NSImageRep *(*originalDevice)(id,SEL,NSDictionary*);
static void (*originalPatternSet)(id,SEL);
static __thread unsigned patternDepth;
static __thread unsigned drawDepth;
static __thread BOOL recording;
static NSMutableSet *seen;
static int output=-1;
static NSString *executable;

static void recordImage(NSImage *image,NSImageRep *selected,NSRect destination,NSGraphicsContext *context)
{
  if (recording || !selected || output<0) return;
  recording=YES;
  @try {
    NSWindow *window=[[NSView focusView] window];
    NSMutableArray *reps=[NSMutableArray array];
    for (NSImageRep *rep in [image representations]) {
      [reps addObject:[NSDictionary dictionaryWithObjectsAndKeys:
        NSStringFromClass([rep class]),@"class",
        @([rep pixelsWide]),@"width",@([rep pixelsHigh]),@"height",
        @([rep size].width),@"logical_width",@([rep size].height),@"logical_height",nil]];
    }
    NSView *focused=[NSView focusView];
    NSRect base=focused ? [focused convertRect:destination toView:nil] : NSZeroRect;
    NSRect visible=focused ? [focused convertRect:[focused visibleRect] toView:nil] : NSZeroRect;
    NSString *action=[focused respondsToSelector:@selector(action)] ? NSStringFromSelector([(NSControl *)focused action]) : @"";
    NSDictionary *entry=[NSDictionary dictionaryWithObjectsAndKeys:
      executable,@"executable",@((int)getpid()),@"pid",
      focused ? NSStringFromClass([focused class]) : @"",@"focus_class",action ?: @"",@"focus_action",
      @[@(base.origin.x),@(base.origin.y),@(base.size.width),@(base.size.height)],@"image_base",
      @[@(visible.origin.x),@(visible.origin.y),@(visible.size.width),@(visible.size.height)],@"image_visible",
      [image valueForKey:@"fileName"] ?: @"",@"resource",[image name] ?: @"",@"name",
      @([image size].width),@"logical_width",@([image size].height),@"logical_height",
      reps,@"representations",NSStringFromClass([selected class]),@"selected_class",
      @([selected pixelsWide]),@"selected_width",@([selected pixelsHigh]),@"selected_height",
      @([context isDrawingToScreen]),@"screen_context",
      @(patternDepth>0),@"pattern_selection",
      @([window windowNumber]),@"window",[window title] ?: @"",@"window_title",
      @([window backingScaleFactor]),@"window_scale",
      @(destination.size.width),@"destination_width",@(destination.size.height),@"destination_height",nil];
    @synchronized(seen) {
      if (![seen containsObject:entry]) {
        [seen addObject:entry];
        NSData *json=[NSJSONSerialization dataWithJSONObject:entry options:0 error:NULL];
        if (json) { write(output,[json bytes],[json length]);write(output,"\n",1); }
      }
    }
  } @catch(NSException *error) {
    NSString *line=[NSString stringWithFormat:@"{\"trace_error\":\"%@\"}\n",[error name]];
    NSData *json=[line dataUsingEncoding:NSUTF8StringEncoding];write(output,[json bytes],[json length]);
  }
  recording=NO;
}

static NSImageRep *traceBest(id self,SEL selector,NSRect rect,NSGraphicsContext *context,NSDictionary *hints)
{
  NSImageRep *result=originalBest(self,selector,rect,context,hints);
  if (drawDepth) recordImage(self,result,rect,context);
  return result;
}
static NSImageRep *traceDevice(id self,SEL selector,NSDictionary *device)
{
  NSImageRep *result=originalDevice(self,selector,device);
  if (patternDepth && !recording) {
    NSSize size=[result size];
    recordImage(self,result,NSMakeRect(0,0,size.width,size.height),[NSGraphicsContext currentContext]);
  }
  return result;
}
static void tracePatternSet(id self,SEL selector)
{
  patternDepth++;
  @try { originalPatternSet(self,selector); }
  @finally { patternDepth--; }
}
static void traceDraw(id self,SEL selector,NSRect destination,NSRect source,
  NSCompositingOperation operation,CGFloat fraction,BOOL flipped,NSDictionary *hints)
{
  drawDepth++;
  @try { originalDraw(self,selector,destination,source,operation,fraction,flipped,hints); }
  @finally { drawDepth--; }
}

@interface ImageUsageTrace : NSObject @end
@implementation ImageUsageTrace
+ (void)load
{
  const char *directory=getenv("NEXTSPACE_IMAGE_USAGE_DIR");
  if (!directory) return;
  @autoreleasepool {
  char binary[4096];ssize_t length=readlink("/proc/self/exe",binary,sizeof(binary)-1);
  if (length<=0) return;binary[length]=0;
  executable=[[NSString alloc] initWithUTF8String:binary];
  NSArray *names=@[@"Workspace",@"Preferences",@"Terminal",@"TextEdit",@"Review",@"TimeMon",@"OpenUp",@"Login",@"ArtworkProbe",@"PrintingProbe",@"HelpAttachmentProbe"];
  if (![names containsObject:[executable lastPathComponent]]) return;
  NSString *path=[NSString stringWithFormat:@"%s/%d.jsonl",directory,(int)getpid()];
  output=open([path fileSystemRepresentation],O_WRONLY|O_CREAT|O_APPEND|O_CLOEXEC,0600);
  if (output<0) return;
  seen=[NSMutableSet new];
  Method draw=class_getInstanceMethod([NSImage class],@selector(drawInRect:fromRect:operation:fraction:respectFlipped:hints:));
  Method best=class_getInstanceMethod([NSImage class],@selector(bestRepresentationForRect:context:hints:));
  originalDraw=(void*)method_getImplementation(draw);originalBest=(void*)method_getImplementation(best);
  method_setImplementation(draw,(IMP)traceDraw);method_setImplementation(best,(IMP)traceBest);
  // Pattern colors select a representation without entering NSImage.drawInRect:.
  Method device=class_getInstanceMethod([NSImage class],@selector(bestRepresentationForDevice:));
  Method pattern=class_getInstanceMethod(objc_getClass("GSPatternColor"),@selector(set));
  if (device && pattern) {
    originalDevice=(void*)method_getImplementation(device);
    originalPatternSet=(void*)method_getImplementation(pattern);
    method_setImplementation(device,(IMP)traceDevice);
    method_setImplementation(pattern,(IMP)tracePatternSet);
  }
  }
}
@end
