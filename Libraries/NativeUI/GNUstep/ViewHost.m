/* One native view host shared by every provider control. GPL-2.0-or-later. */
#import "ViewHost.h"
#include <math.h>
#include <stdlib.h>
#include <objc/runtime.h>
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
  BOOL injected_pointer;
  BOOL release_queued;
  unsigned dispatch_depth;
  int key_result;
  NSResponder *fallback;
};
static NXSViewHost *active,*focused;
/* Auxiliary native windows (menus) must read the same pointer stream as their
 * owner during embedded tracking. Only the event source is adapted; native
 * menu layout, hit testing and tracking remain untouched. */
struct NXSInputWindow {
  NSWindow *window;
  NXSViewHost *host;
  Class original,adapted;
  struct NXSInputWindow *next;
};
static struct NXSInputWindow *input_windows;
static NSPoint auxiliary_pointer(id window,SEL selector)
{
  for(struct NXSInputWindow *entry=input_windows;entry;entry=entry->next)
    if(entry->window==window) {
      if(active==entry->host&&(entry->host->tracking||entry->host->injected_pointer)) {
        NSPoint screen=[entry->host->window convertBaseToScreen:entry->host->pointer];
        return [window convertScreenToBase:screen];
      }
      IMP original=class_getMethodImplementation(entry->original,selector);
      return ((NSPoint (*)(id,SEL))original)(window,selector);
    }
  return NSZeroPoint;
}
void nxs_host_bind_input_window(NXSViewHost *host,NSWindow *window)
{
  if(!host||!window)return;
  for(struct NXSInputWindow *entry=input_windows;entry;entry=entry->next)
    if(entry->window==window)return;
  Class original=object_getClass(window);
  NSString *name=[@"NXSInputWindow_" stringByAppendingString:NSStringFromClass(original)];
  Class adapted=objc_getClass([name UTF8String]);
  if(!adapted) {
    adapted=objc_allocateClassPair(original,[name UTF8String],0);
    if(!adapted)return;
    SEL selector=@selector(mouseLocationOutsideOfEventStream);
    Method method=class_getInstanceMethod(original,selector);
    class_addMethod(adapted,selector,(IMP)auxiliary_pointer,method_getTypeEncoding(method));
    objc_registerClassPair(adapted);
  }
  struct NXSInputWindow *entry=calloc(1,sizeof(*entry));if(!entry)return;
  *entry=(struct NXSInputWindow){[window retain],host,original,adapted,input_windows};
  input_windows=entry;object_setClass(window,adapted);
}
void nxs_host_unbind_input_windows(NXSViewHost *host)
{
  struct NXSInputWindow **cursor=&input_windows;
  while(*cursor) {
    struct NXSInputWindow *entry=*cursor;
    if(entry->host!=host){cursor=&entry->next;continue;}
    if(object_getClass(entry->window)==entry->adapted)object_setClass(entry->window,entry->original);
    *cursor=entry->next;[entry->window release];free(entry);
  }
}
/* The native control owns the tracking loop. While it waits, dispatch the embedding
 * toolkit so real pointer events and its other windows remain responsive. */
@interface NXSApplication : NSApplication
- (void)dispatchNativeEvent:(NSEvent *)event to:(NSResponder *)responder;
@end
@implementation NXSApplication
- (void)dispatchNativeEvent:(NSEvent *)event to:(NSResponder *)responder
{
  /* NSCell expects the initiating event to be NSApp.currentEvent, just as
   * when AppKit dispatches a real mouseDown. */
  NSEvent *previous=[_current_event retain];
  [_current_event release];_current_event=[event retain];
  [responder retain];
  @try {
    switch([event type]) {
      case NSLeftMouseDown:[responder mouseDown:event];break;
      case NSKeyDown:[responder keyDown:event];break;
      case NSKeyUp:[responder keyUp:event];break;
      case NSFlagsChanged:[responder flagsChanged:event];break;
      default:break;
    }
  }
  @finally {[responder release];[_current_event release];_current_event=previous;}
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

/* Unhandled keys return to the embedding application. Native responders and
 * NSWindow still interpret the key; the host supplies no key-binding rules. */
@interface NXSInputFallback : NSResponder { @public NXSViewHost *control; }
@end
@implementation NXSInputFallback
- (void)keyDown:(NSEvent *)event {control->key_result=NXS_INPUT_UNHANDLED;}
- (void)keyUp:(NSEvent *)event {control->key_result=NXS_INPUT_UNHANDLED;}
- (void)flagsChanged:(NSEvent *)event {control->key_result=NXS_INPUT_UNHANDLED;}
@end

@interface NXSBackingWindow : NSWindow { @public NXSViewHost *control; }
@end
@implementation NXSBackingWindow
- (NSPoint)mouseLocationOutsideOfEventStream {return control->pointer;}
/* NSCell flushes its backing window during tracking. Its pixels belong to the
 * embedding widget; never submit this private window to the compositor. */
- (void)flushWindow {}
- (void)flushWindowIfNeeded {}
/* The application owns its focus order. Export the native window's requests. */
- (void)selectNextKeyView:(id)sender {control->key_result=NXS_INPUT_NEXT;}
- (void)selectPreviousKeyView:(id)sender {control->key_result=NXS_INPUT_PREVIOUS;}
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
  NXSInputFallback *fallback=[NXSInputFallback new];fallback->control=host;
  host->fallback=fallback;[window setNextResponder:fallback];
  [[window contentView] addSubview:view];
  return host;
}
int nxs_host_destroy(NXSViewHost *host)
{
  if(!host)return 1;
  if(host->tracking||host->dispatch_depth)return 0;
  if(focused==host&&!nxs_host_focus(host,0))return 0;
  nxs_host_unbind_input_windows(host);
  [host->view removeFromSuperview];
  [host->window close];[host->window release];[host->view release];
  [host->fallback release];
  [host->bitmap release];free(host->pixels);free(host);
  return 1;
}
void nxs_host_resize(NXSViewHost *host,NSSize size)
{
  if(!host||NSEqualSizes([host->view frame].size,size))return;
  [host->view setFrameSize:size];[host->window setContentSize:size];
}
int nxs_host_set_screen_origin(NXSViewHost *host,double x,double y)
{
  if(!host||!isfinite(x)||!isfinite(y)||fabs(x)>1e7||fabs(y)>1e7||nxs_host_tracking(host))return 0;
  NSRect screen=[[NSScreen mainScreen] frame];
  [host->window setFrameOrigin:NSMakePoint(NSMinX(screen)+x,NSMaxY(screen)-y-[host->view frame].size.height)];
  return 1;
}
NXSRect nxs_host_rect_from_view(NXSViewHost *host,NSView *view,NSRect rect)
{
  if(!host||!view||![view window])return (NXSRect){0};
  rect=[view convertRect:rect toView:nil];
  rect.origin=[[view window] convertBaseToScreen:rect.origin];
  rect.origin=[host->window convertScreenToBase:rect.origin];
  rect=[host->view convertRect:rect fromView:nil];
  return (NXSRect){rect.origin.x,[host->view isFlipped]?rect.origin.y:[host->view bounds].size.height-NSMaxY(rect),rect.size.width,rect.size.height};
}
double nxs_host_dispatch_events(double maximum_wait)
{
  if(!NSApp||!isfinite(maximum_wait)||maximum_wait<0||maximum_wait>60)return -1;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSRunLoop *loop=[NSRunLoop currentRunLoop];
  NSString *mode=active?NSEventTrackingRunLoopMode:NSDefaultRunLoopMode;
  [loop runMode:mode beforeDate:[NSDate dateWithTimeIntervalSinceNow:maximum_wait]];
  /* Native menus own real auxiliary windows. Run their queued AppKit window
   * and input events as NSApplication normally does, unless a native tracking
   * loop already owns the queue. Never take events out of that loop. */
  unsigned dispatched=0;
  if(!active)while(dispatched<1024) {
    NSEvent *event=[NSApp nextEventMatchingMask:NSAnyEventMask untilDate:[NSDate distantPast]
      inMode:NSDefaultRunLoopMode dequeue:YES];
    if(!event)break;
    NXSViewHost *owner=NULL;
    for(struct NXSInputWindow *entry=input_windows;entry;entry=entry->next)
      if(entry->window==[event window]){owner=entry->host;break;}
    if(owner){owner->dispatch_depth++;owner->injected_pointer=NO;owner->release_queued=NO;active=owner;}
    @try {[NSApp sendEvent:event];}
    @finally {if(owner){owner->dispatch_depth--;active=NULL;}}
    dispatched++;
  }
  /* GNUstep services due timers and reports their own next deadline here.
   * No control interval, animation counter or frame selection lives in host. */
  NSDate *date=[loop limitDateForMode:mode];
  double next=date&&[date compare:[NSDate distantFuture]]==NSOrderedAscending?
    MAX(0,[date timeIntervalSinceNow]):-1;
  if(dispatched==1024)next=0;
  [pool drain];return next;
}
int nxs_host_needs_display(NXSViewHost *host)
{return host&&[host->view needsDisplay];}
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
  @try { [(NXSApplication *)NSApp dispatchNativeEvent:event to:control->view]; }
  @finally { control->tracking = NO; active = NULL; }
  [pool drain];
}

void nxs_host_send(NXSViewHost *control, int event, double x, double y, unsigned modifiers)
{
  if (!control || (!control->tracking&&!control->dispatch_depth) || active!=control || control->release_queued) return;
  control->injected_pointer=YES;
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

int nxs_host_tracking(NXSViewHost *host){return host&&(host->tracking||host->dispatch_depth);}

int nxs_host_focused(NXSViewHost *host)
{return host&&focused==host&&[host->window firstResponder]==host->view;}
int nxs_host_focus(NXSViewHost *host,int focus)
{
  if(!host)return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  int accepted=1;
  if(focus) {
    if(![host->view acceptsFirstResponder])accepted=0;
    else {
      NXSViewHost *previous=focused;
      if(previous&&previous!=host&&![previous->window makeFirstResponder:nil])accepted=0;
      else if(![host->window makeFirstResponder:host->view]) {
        accepted=0;
        if(previous)[previous->window makeFirstResponder:previous->view];
      } else focused=host;
    }
  } else if(focused==host) {
    accepted=[host->window makeFirstResponder:nil];
    if(accepted)focused=NULL;
  }
  [pool drain];return accepted;
}

static NSString *key_characters(const NXSKeyEvent *event,BOOL unmodified)
{
  unichar key=0;
  switch(event->key) {
    case NXS_KEY_TEXT: {
      const char *text=unmodified&&event->unmodified_text?event->unmodified_text:event->text;
      return text?[NSString stringWithUTF8String:text]:@"";
    }
    case NXS_KEY_ENTER:key=NSCarriageReturnCharacter;break;
    case NXS_KEY_TAB:key=NSTabCharacter;break;
    case NXS_KEY_BACKSPACE:key=NSDeleteCharacter;break;
    case NXS_KEY_DELETE:key=NSDeleteFunctionKey;break;
    case NXS_KEY_ESCAPE:key=0x1b;break;
    case NXS_KEY_LEFT:key=NSLeftArrowFunctionKey;break;
    case NXS_KEY_RIGHT:key=NSRightArrowFunctionKey;break;
    case NXS_KEY_UP_ARROW:key=NSUpArrowFunctionKey;break;
    case NXS_KEY_DOWN_ARROW:key=NSDownArrowFunctionKey;break;
    case NXS_KEY_HOME:key=NSHomeFunctionKey;break;
    case NXS_KEY_END:key=NSEndFunctionKey;break;
    case NXS_KEY_PAGE_UP:key=NSPageUpFunctionKey;break;
    case NXS_KEY_PAGE_DOWN:key=NSPageDownFunctionKey;break;
    case NXS_KEY_INSERT:key=NSInsertFunctionKey;break;
    default:if(event->key>=NXS_KEY_F1&&event->key<=NXS_KEY_F24)key=NSF1FunctionKey+event->key-NXS_KEY_F1;
  }
  return key?[NSString stringWithCharacters:&key length:1]:nil;
}
int nxs_host_key(NXSViewHost *host,const NXSKeyEvent *input)
{
  if(!host||!input||input->size<sizeof(*input)||input->type>NXS_KEY_MODIFIERS||
     active||!nxs_host_focused(host))return NXS_INPUT_UNHANDLED;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSString *text=key_characters(input,NO),*unmodified=key_characters(input,YES);
  if(!text||!unmodified){[pool drain];return NXS_INPUT_UNHANDLED;}
  if([host->view needsDisplay])nxs_host_draw(host,1);
  NSUInteger modifiers=flags(input->modifiers);
  if(input->key>=NXS_KEY_LEFT)modifiers|=NSFunctionKeyMask;
  NSEvent *event=[NSEvent keyEventWithType:input->type==NXS_KEY_DOWN?NSKeyDown:input->type==NXS_KEY_UP?NSKeyUp:NSFlagsChanged
    location:NSZeroPoint modifierFlags:modifiers timestamp:[NSDate timeIntervalSinceReferenceDate]
    windowNumber:[host->window windowNumber] context:nil characters:text
    charactersIgnoringModifiers:unmodified isARepeat:!!input->repeat keyCode:0];
  host->key_result=NXS_INPUT_HANDLED;host->dispatch_depth++;active=host;
  @try {[(NXSApplication *)NSApp dispatchNativeEvent:event to:[host->window firstResponder]];}
  @finally {host->dispatch_depth--;active=NULL;}
  int result=host->key_result;[pool drain];return result;
}
