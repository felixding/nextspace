/* Reuse NSScroller drawing, geometry and tracking; no second control.
 * GPL-2.0-or-later. */
#import <AppKit/AppKit.h>
#include "NativeScroller.h"
#include <math.h>
#include <stdlib.h>

struct NXSScroller {
  NSScroller *view;
  NSWindow *window;
  id target;
  NSBitmapImageRep *bitmap;
  unsigned char *pixels;
  double lower, upper, page, step, page_step, value;
  NXSChanged changed;
  NXSPump pump;
  void *context;
  BOOL tracking;
  BOOL horizontal;
  unsigned modifiers;
  NSPoint pointer;
  BOOL release_queued;
};

static NXSScroller *active;

/* NSScroller owns the tracking loop. While it waits, dispatch the embedding
 * toolkit so real pointer events and its other windows remain responsive. */
@interface NXSApplication : NSApplication
- (void)trackScroller:(NSScroller *)view event:(NSEvent *)event;
@end
@implementation NXSApplication
- (void)trackScroller:(NSScroller *)view event:(NSEvent *)event
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
    active->pump(active->context);
    NSDate *slice = [NSDate dateWithTimeIntervalSinceNow:.005];
    if ([limit compare:slice] == NSOrderedAscending) slice = limit;
    NSEvent *event = [super nextEventMatchingMask:mask untilDate:slice inMode:mode dequeue:dequeue];
    if (event) return event;
  } while (active && [limit timeIntervalSinceNow] > 0);
  return nil;
}
@end

@interface NXSBackingWindow : NSWindow { @public NXSScroller *control; }
@end
@implementation NXSBackingWindow
- (NSPoint)mouseLocationOutsideOfEventStream {return control->pointer;}
/* NSCell flushes its backing window during tracking. Its pixels belong to the
 * embedding widget; never submit this private window to the compositor. */
- (void)flushWindow {}
- (void)flushWindowIfNeeded {}
@end

@interface NXSAction : NSObject { @public NXSScroller *control; }
- (void)changed:(NSScroller *)sender;
@end
@implementation NXSAction
- (void)changed:(NSScroller *)sender
{
  double value = control->value;
  switch ([sender hitPart]) {
    case NSScrollerDecrementLine: value -= control->step; break;
    case NSScrollerIncrementLine: value += control->step; break;
    case NSScrollerDecrementPage: value -= control->page_step; break;
    case NSScrollerIncrementPage: value += control->page_step; break;
    default: value = control->lower + [sender doubleValue] *
      fmax(0, control->upper - control->lower - control->page); break;
  }
  control->value = fmax(control->lower, fmin(value, fmax(control->lower, control->upper - control->page)));
  control->changed(control->context, control->value);
}
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

static NSEvent *mouse(NXSScroller *control, NSEventType type, double x, double y, unsigned modifiers)
{
  NSPoint point = [control->view convertPoint:NSMakePoint(x, y) toView:nil];
  return [NSEvent mouseEventWithType:type location:point modifierFlags:flags(modifiers)
    timestamp:[NSDate timeIntervalSinceReferenceDate] windowNumber:[control->window windowNumber]
    context:nil eventNumber:0 clickCount:1 pressure:type == NSLeftMouseUp ? 0 : 1];
}

double nxs_scroller_width(void)
{
  return [NSScroller scrollerWidth];
}

NXSScroller *nxs_scroller_create(int horizontal, NXSChanged changed, NXSPump pump, void *context)
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  if (NSApp && ![NSApp isKindOfClass:[NXSApplication class]]) { [pool drain]; return NULL; }
  if(!NSApp) {
    NSUserDefaults *defaults=[NSUserDefaults standardUserDefaults];
    NSMutableDictionary *arguments=[NSMutableDictionary dictionaryWithDictionary:
      [defaults volatileDomainForName:NSArgumentDomain] ?: @{}];
    [arguments setObject:@YES forKey:@"GSSuppressAppIcon"];
    [defaults removeVolatileDomainForName:NSArgumentDomain];
    [defaults setVolatileDomain:arguments forName:NSArgumentDomain];
  }
  [NXSApplication sharedApplication];
  NXSScroller *control = calloc(1, sizeof(*control));
  if (control) {
    double width = nxs_scroller_width();
    control->view = [[NSScroller alloc] initWithFrame:
      NSMakeRect(0, 0, horizontal ? 128 : width, horizontal ? width : 128)];
    NXSAction *target = [NXSAction new]; target->control = control;
    control->target = target;
    [control->view setTarget:target]; [control->view setAction:@selector(changed:)];
    control->changed = changed; control->pump = pump; control->context = context;
    control->horizontal=horizontal;
    /* NSCell pixel alignment uses the view-to-window transform, even when
     * rendering offscreen. Keep that contract stable before the first click. */
    NXSBackingWindow *window = [[NXSBackingWindow alloc] initWithContentRect:[control->view bounds]
      styleMask:NSBorderlessWindowMask backing:NSBackingStoreBuffered defer:NO];
    window->control=control;control->window=window;
    [window setReleasedWhenClosed:NO];
    [[window contentView] addSubview:control->view];
  }
  [pool drain];
  return control;
}

void nxs_scroller_destroy(NXSScroller *control)
{
  if (!control) return;
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  [control->view removeFromSuperview];
  [control->window close];[control->window release]; [control->view release]; [control->target release];
  [control->bitmap release]; free(control->pixels); free(control);
  [pool drain];
}

void nxs_scroller_sync(NXSScroller *control, double length, double lower, double upper,
                       double page, double step, double page_step, double value, int enabled)
{
  if (!control || !isfinite(length) || length < 1 || length > 32768) return;
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  double width=nxs_scroller_width();
  NSSize size=NSMakeSize(control->horizontal ? length : width,control->horizontal ? width : length);
  /* setFrameSize: resets NSScroller's hit part, even for an unchanged size. */
  if(!NSEqualSizes([control->view frame].size,size)) {
    [control->view setFrameSize:size];
    if (control->window) [control->window setContentSize:size];
  }
  control->lower = lower; control->upper = upper; control->page = page;
  control->step = step; control->page_step = page_step; control->value = value;
  double extent = fmax(0, upper - lower), range = fmax(0, extent - page);
  [control->view setEnabled:enabled && range > 0];
  [control->view setFloatValue:range > 0 ? (value - lower) / range : 0
              knobProportion:extent > 0 ? fmin(1, page / extent) : 1];
  [pool drain];
}

NXSBitmap nxs_scroller_draw(NXSScroller *control, double scale)
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

NXSRect nxs_scroller_part(NXSScroller *control, int part)
{
  NSRect rect = control ? [control->view rectForPart:(NSScrollerPart)part] : NSZeroRect;
  return (NXSRect){rect.origin.x, rect.origin.y, rect.size.width, rect.size.height};
}

void nxs_scroller_track(NXSScroller *control, double x, double y, unsigned modifiers)
{
  if (!control || active || ![control->view isEnabled]) return;
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  active = control; control->tracking = YES;control->modifiers=modifiers;control->release_queued=NO;
  NSEvent *event=mouse(control,NSLeftMouseDown,x,y,modifiers);control->pointer=[event locationInWindow];
  @try { [(NXSApplication *)NSApp trackScroller:control->view event:event]; }
  @finally { control->tracking = NO; active = NULL; }
  [pool drain];
}

void nxs_scroller_send(NXSScroller *control, int event, double x, double y, unsigned modifiers)
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

int nxs_scroller_tracking(NXSScroller *control) { return control && control->tracking; }
int nxs_scroller_hit_part(NXSScroller *control) { return control ? [control->view hitPart] : NSScrollerNoPart; }
