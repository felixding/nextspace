/* One native view host shared by every provider control. GPL-2.0-or-later. */
#import "ViewHost.h"
#include <math.h>
#include <stdlib.h>
struct NXSViewHost {
  NSView *view;
  NSWindow *window;
  NSBitmapImageRep *bitmap;
  unsigned char *pixels;
  NXSPump pump;
  void *context;
  BOOL tracking;
  unsigned modifiers;
  NSPoint pointer;
  BOOL release_queued;
};
static NXSViewHost *active;
/* The native control owns the tracking loop. While it waits, dispatch the embedding
 * toolkit so real pointer events and its other windows remain responsive. */
@interface NXSApplication : NSApplication
- (void)trackView:(NSView *)view event:(NSEvent *)event;
@end
@implementation NXSApplication
- (void)trackView:(NSView *)view event:(NSEvent *)event
{
  /* NSCell expects the initiating event to be NSApp.currentEvent, just as
   * when AppKit dispatches a real mouseDown. */
  NSEvent *previous=[_current_event retain];
  [_current_event release];_current_event=[event retain];
  @try {[view mouseDown:event];}
  @finally {[_current_event release];_current_event=previous;}
}
- (NSEvent *)nextEventMatchingMask:(NSUInteger)mask untilDate:(NSDate *)limit
                           inMode:(NSString *)mode dequeue:(BOOL)dequeue
{
  if (!active) return [super nextEventMatchingMask:mask untilDate:limit inMode:mode dequeue:dequeue];
  do {
    if(active->pump)active->pump(active->context);
    NSDate *slice = [NSDate dateWithTimeIntervalSinceNow:.005];
    if ([limit compare:slice] == NSOrderedAscending) slice = limit;
    NSEvent *event = [super nextEventMatchingMask:mask untilDate:slice inMode:mode dequeue:dequeue];
    if (event) return event;
  } while (active && [limit timeIntervalSinceNow] > 0);
  return nil;
}
@end

@interface NXSBackingWindow : NSWindow { @public NXSViewHost *control; }
@end
@implementation NXSBackingWindow
- (NSPoint)mouseLocationOutsideOfEventStream {return control->pointer;}
/* NSCell flushes its backing window during tracking. Its pixels belong to the
 * embedding widget; never submit this private window to the compositor. */
- (void)flushWindow {}
- (void)flushWindowIfNeeded {}
@end

static NSUInteger flags(unsigned modifiers)
{
  NSUInteger result=(modifiers & NXS_SHIFT) ? NSShiftKeyMask : 0;
  NSUserDefaults *defaults=[NSUserDefaults standardUserDefaults];
  NSArray *keys=@[@"Control",@"Command",@"Alternate"];
  NSArray *fallback=@[@"Control_L",@"Alt_L",@"Super_L"];
  NSUInteger native[]={NSControlKeyMask,NSCommandKeyMask,NSAlternateKeyMask};
  for(NSUInteger i=0;i<3;i++) {
    NSString *name=[defaults stringForKey:[NSString stringWithFormat:@"GSFirst%@Key",keys[i]]] ?: fallback[i];
    unsigned family=[name hasPrefix:@"Control_"] ? NXS_CONTROL : [name hasPrefix:@"Alt_"] ? NXS_ALT :
      ([name hasPrefix:@"Super_"] || [name hasPrefix:@"Meta_"]) ? NXS_SUPER : 0;
    if(modifiers & family) result |= native[i];
  }
  return result;
}

static NSEvent *mouse(NXSViewHost *control, NSEventType type, double x, double y, unsigned modifiers)
{
  /* Consumers use bitmap coordinates, independent of a UI library's native
   * view orientation. Keep this conversion inside the provider. */
  double localY=[control->view isFlipped]?y:[control->view bounds].size.height-y;
  NSPoint point = [control->view convertPoint:NSMakePoint(x, localY) toView:nil];
  return [NSEvent mouseEventWithType:type location:point modifierFlags:flags(modifiers)
    timestamp:[NSDate timeIntervalSinceReferenceDate] windowNumber:[control->window windowNumber]
    context:nil eventNumber:0 clickCount:1 pressure:type == NSLeftMouseUp ? 0 : 1];
}

int nxs_host_initialize(void)
{
  if (NSApp && ![NSApp isKindOfClass:[NXSApplication class]]) return 0;
  if(!NSApp) {
    NSUserDefaults *defaults=[NSUserDefaults standardUserDefaults];
    NSMutableDictionary *arguments=[NSMutableDictionary dictionaryWithDictionary:
      [defaults volatileDomainForName:NSArgumentDomain] ?: @{}];
    [arguments setObject:@YES forKey:@"GSSuppressAppIcon"];
    [defaults removeVolatileDomainForName:NSArgumentDomain];
    [defaults setVolatileDomain:arguments forName:NSArgumentDomain];
  }
  [NXSApplication sharedApplication];
  return 1;
}
NXSViewHost *nxs_host_create(NSView *view,NXSPump pump,void *context)
{
  if(!view||!nxs_host_initialize())return NULL;
  NXSViewHost *host=calloc(1,sizeof(*host));
  if(!host)return NULL;
  host->view=[view retain];host->pump=pump;host->context=context;
  NXSBackingWindow *window=[[NXSBackingWindow alloc] initWithContentRect:[view bounds]
    styleMask:NSBorderlessWindowMask backing:NSBackingStoreBuffered defer:NO];
  window->control=host;host->window=window;
  [window setReleasedWhenClosed:NO];
  [[window contentView] addSubview:view];
  return host;
}
int nxs_host_destroy(NXSViewHost *host)
{
  if(!host)return 1;
  if(host->tracking)return 0;
  [host->view removeFromSuperview];
  [host->window close];[host->window release];[host->view release];
  [host->bitmap release];free(host->pixels);free(host);
  return 1;
}
void nxs_host_resize(NXSViewHost *host,NSSize size)
{
  if(!host||NSEqualSizes([host->view frame].size,size))return;
  [host->view setFrameSize:size];[host->window setContentSize:size];
}
NXSBitmap nxs_host_draw(NXSViewHost *control, double scale)
{
  NXSBitmap result = {0};
  if (!control || !isfinite(scale) || scale < 1 || scale > 8) return result;
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  NSSize size = [control->view frame].size;
  int width = (int)floor(size.width * scale + .5), height = (int)floor(size.height * scale + .5);
  if (width < 1 || height < 1 || (size_t)width * height > 8 * 1024 * 1024) { [pool drain]; return result; }
  NSImage *image = [[NSImage alloc] initWithSize:NSMakeSize(width, height)];
  [image lockFocus];
  NSAffineTransform *transform = [NSAffineTransform transform];
  [transform translateXBy:0 yBy:height]; [transform scaleXBy:scale yBy:-scale]; [transform concat];
  NSGraphicsContext *context = [NSGraphicsContext currentContext];
  [context lockFocusView:control->view inRect:[control->view bounds]];
  [context GSWSetViewIsFlipped:[control->view isFlipped]];
  [[NSColor controlBackgroundColor] set]; NSRectFill(NSMakeRect(0,0,size.width,size.height));
  [control->view drawRect:[control->view bounds]];
  [context unlockFocusView:control->view needsFlush:NO];
  [control->view setNeedsDisplay:NO];
  [NSGraphicsContext saveGraphicsState];
  [transform invert]; [transform concat];
  NSBitmapImageRep *bitmap = [[NSBitmapImageRep alloc] initWithFocusedViewRect:NSMakeRect(0,0,width,height)];
  [NSGraphicsContext restoreGraphicsState]; [image unlockFocus]; [image release];
  [control->bitmap release]; control->bitmap = bitmap;
  unsigned char *pixels = realloc(control->pixels, (size_t)width * height * 4);
  if (pixels) {
    control->pixels = pixels;
    /* AppKit readback is RGBA; the two embedding toolkits accept native ARGB32. */
    const unsigned char *source = [bitmap bitmapData];
    for (int y = 0; y < height; y++) for (int x = 0; x < width; x++) {
      const unsigned char *p = source + y * [bitmap bytesPerRow] + 4 * x;
      ((uint32_t *)pixels)[y * width + x] = ((uint32_t)p[3] << 24) |
        ((uint32_t)p[0] << 16) | ((uint32_t)p[1] << 8) | p[2];
    }
    result = (NXSBitmap){width, height, width * 4, pixels};
  }
  [pool drain];
  return result;
}

void nxs_host_track(NXSViewHost *control, double x, double y, unsigned modifiers)
{
  if (!control || active) return;
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  /* Native cells may prepare their track/knob geometry while drawing. An
   * offscreen host has no automatic display pass between resize and input;
   * let the native view finish that pass instead of reproducing its layout. */
  if([control->view needsDisplay])nxs_host_draw(control,1);
  active = control; control->tracking = YES;control->modifiers=modifiers;control->release_queued=NO;
  NSEvent *event=mouse(control,NSLeftMouseDown,x,y,modifiers);control->pointer=[event locationInWindow];
  @try { [(NXSApplication *)NSApp trackView:control->view event:event]; }
  @finally { control->tracking = NO; active = NULL; }
  [pool drain];
}

void nxs_host_send(NXSViewHost *control, int event, double x, double y, unsigned modifiers)
{
  if (!control || !control->tracking || control->release_queued) return;
  if(event==NXS_RELEASE) control->release_queued=YES;
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  if(control->modifiers!=modifiers) {
    [NSApp postEvent:[NSEvent keyEventWithType:NSFlagsChanged location:NSZeroPoint modifierFlags:flags(modifiers)
      timestamp:[NSDate timeIntervalSinceReferenceDate] windowNumber:[control->window windowNumber]
      context:nil characters:@"" charactersIgnoringModifiers:@"" isARepeat:NO keyCode:0] atStart:NO];
    control->modifiers=modifiers;
  }
  NSEvent *mouseEvent=mouse(control,event == NXS_RELEASE ? NSLeftMouseUp : NSLeftMouseDragged,x,y,modifiers);
  control->pointer=[mouseEvent locationInWindow];
  [NSApp postEvent:mouseEvent atStart:NO];
  [pool drain];
}

int nxs_host_tracking(NXSViewHost *host){return host&&host->tracking;}
