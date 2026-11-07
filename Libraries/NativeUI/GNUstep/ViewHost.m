/* One native view host shared by every provider control. GPL-2.0-or-later. */
#import "ViewHost.h"
#include <math.h>
#include <stdlib.h>
#include <limits.h>
#include <objc/runtime.h>
@interface NSGraphicsContext (NXSBackingReadback)
- (NSDictionary *)GSReadRectAtBackingScale:(NSRect)rect;
@end
struct NXSViewHost {
  NSView *view;
  NSWindow *window;
  NSBitmapImageRep *bitmap;
  unsigned char *pixels;
  NXSPump pump;
  void *context;
  BOOL tracking;
  unsigned modifiers;
  unsigned click_count;
  NSPoint pointer;
  BOOL injected_pointer;
  BOOL release_queued;
  unsigned dispatch_depth;
  int key_result;
  NSResponder *fallback;
  id command_target;
  NXSCommandFilter command_filter;
  void *command_context;
};
static NXSViewHost *active,*focused;
/* NSImage's temporary screen context has a 1x cache window. Supply the actual
 * embedding density while native views draw, so AppKit owns representation
 * selection and cache policy exactly as it does for an ordinary screen window.
 * No image/control drawing or selection algorithm is implemented here. */
struct NXSDrawDensity {
  NSWindow *window;
  Class original;
  double scale;
  struct NXSDrawDensity *previous;
};
static __thread struct NXSDrawDensity *draw_density;
static CGFloat drawing_backing_scale(id window,SEL selector)
{
  for(struct NXSDrawDensity *scope=draw_density;scope;scope=scope->previous)
    if(scope->window==window)return scope->scale;
  Class original=class_getSuperclass(object_getClass(window));
  return ((CGFloat (*)(id,SEL))class_getMethodImplementation(original,selector))(window,selector);
}
static BOOL begin_draw_density(NSGraphicsContext *context,double scale,struct NXSDrawDensity *scope)
{
  *scope=(struct NXSDrawDensity){0};
  if(scale==1)return YES;
  id window=[[context attributes] objectForKey:NSGraphicsContextDestinationAttributeName];
  if(![context isDrawingToScreen]||![window isKindOfClass:[NSWindow class]])return NO;
  if(fabs([window backingScaleFactor]-scale)<.000001)return YES;
  Class original=object_getClass(window);
  NSString *name=[@"NXSDrawDensity_" stringByAppendingString:NSStringFromClass(original)];
  Class adapted=objc_getClass([name UTF8String]);
  if(!adapted) {
    adapted=objc_allocateClassPair(original,[name UTF8String],0);if(!adapted)return NO;
    SEL selector=@selector(backingScaleFactor);
    Method method=class_getInstanceMethod(original,selector);
    class_addMethod(adapted,selector,(IMP)drawing_backing_scale,method_getTypeEncoding(method));
    objc_registerClassPair(adapted);
  }
  *scope=(struct NXSDrawDensity){[window retain],original,scale,draw_density};
  draw_density=scope;object_setClass(window,adapted);return YES;
}
static void end_draw_density(struct NXSDrawDensity *scope)
{
  if(scope->window){object_setClass(scope->window,scope->original);draw_density=scope->previous;[scope->window release];}
}
static BOOL native_backing(NSView *view)
{return [view isKindOfClass:[NSTextField class]]||[view isKindOfClass:[NSScrollView class]]||[view isKindOfClass:[NSPopUpButton class]]||[view isKindOfClass:[NSMatrix class]]||[view isKindOfClass:NSClassFromString(@"GSToolbarView")];}
static NSView *focus_view(NXSViewHost *host)
{return [host->view isKindOfClass:[NSScrollView class]]?[(NSScrollView *)host->view documentView]:host->view;}
static NXSMenuLoop *menu_loop;
void nxs_host_menu_begin(NXSMenuLoop *scope)
{scope->previous=menu_loop;menu_loop=scope;}
void nxs_host_menu_end(NXSMenuLoop *scope)
{if(menu_loop==scope)menu_loop=scope->previous;}
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
/* The native menu still resolves targets and validates its own items. This
 * proxy lets the embedding application's existing controller own selected
 * semantic actions, while all unclaimed native methods remain untouched. */
@interface NXSCommandTarget : NSObject {
 @public NXSViewHost *host; id target;
}
@end
@implementation NXSCommandTarget
- (void)dealloc {[target release];[super dealloc];}
- (BOOL)respondsToSelector:(SEL)selector
{return [super respondsToSelector:selector]||[target respondsToSelector:selector];}
- (NSMethodSignature *)methodSignatureForSelector:(SEL)selector
{return [super methodSignatureForSelector:selector]?:[target methodSignatureForSelector:selector];}
- (void)forwardInvocation:(NSInvocation *)invocation
{
  if(nxs_host_command(host,[invocation selector],NXS_COMMAND_EXECUTE)<0)
    [invocation invokeWithTarget:target];
}
- (BOOL)validateMenuItem:(NSMenuItem *)item
{
  int result=nxs_host_command(host,[item action],NXS_COMMAND_VALIDATE);
  if(result>=0)return result!=0;
  if([target respondsToSelector:_cmd])return [target validateMenuItem:item];
  if([target respondsToSelector:@selector(validateUserInterfaceItem:)])return [target validateUserInterfaceItem:item];
  return YES;
}
@end
int nxs_host_command(NXSViewHost *host,SEL selector,unsigned phase)
{
  if(!host||!host->command_filter||!selector||phase>NXS_COMMAND_EXECUTE)return -1;
  host->dispatch_depth++;
  int result;
  @try {result=host->command_filter(host->command_context,sel_getName(selector),phase);}
  @finally {host->dispatch_depth--;}
  return result>=-1&&result<=1?result:0;
}
int nxs_host_command_filter(NXSViewHost *host,NXSCommandFilter filter,void *context)
{
  if(!host||host->dispatch_depth)return 0;
  host->command_filter=filter;host->command_context=context;return 1;
}
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
- (BOOL)dispatchNativeEvent:(NSEvent *)event toMenu:(NSMenu *)menu;
@end
@implementation NXSApplication
/* AppKit resolves nil-target menu actions through the embedding application's
 * logical key window, without ordering a private backing window on screen. */
- (NSWindow *)keyWindow {return focused?focused->window:[super keyWindow];}
- (id)targetForAction:(SEL)action to:(id)recipient from:(id)sender
{
  id native=[super targetForAction:action to:recipient from:sender];
  if(native&&focused&&focused->command_filter&&native==[focused->window firstResponder]) {
    NXSCommandTarget *proxy=focused->command_target;
    if(proxy->target!=native){[native retain];[proxy->target release];proxy->target=native;}
    return proxy;
  }
  return native;
}
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
      case NSScrollWheel:[responder scrollWheel:event];break;
      case NSKeyDown:
        /* Reuse the editor's native command menu, including its key equivalents
         * and validation. Do not maintain an embedding-specific shortcut table. */
        [[self mainMenu] update];
        if(![[self mainMenu] performKeyEquivalent:event]&&
           !([responder isKindOfClass:[NSView class]]&&
             [[(NSView *)responder menu] performKeyEquivalent:event]))
          [responder keyDown:event];
        break;
      case NSKeyUp:[responder keyUp:event];break;
      case NSFlagsChanged:[responder flagsChanged:event];break;
      default:break;
    }
  }
  @finally {[responder release];[_current_event release];_current_event=previous;}
}
- (BOOL)dispatchNativeEvent:(NSEvent *)event toMenu:(NSMenu *)menu
{
  NSEvent *previous=[_current_event retain];
  [_current_event release];_current_event=[event retain];
  @try {[menu update];return [menu performKeyEquivalent:event];}
  @finally {[_current_event release];_current_event=previous;}
}
- (NSEvent *)nextEventMatchingMask:(NSUInteger)mask untilDate:(NSDate *)limit
                           inMode:(NSString *)mode dequeue:(BOOL)dequeue
{
  if (!active&&!menu_loop) return [super nextEventMatchingMask:mask untilDate:limit inMode:mode dequeue:dequeue];
  do {
    if(menu_loop&&menu_loop->pump)menu_loop->pump(menu_loop->context);
    else if(active&&active->pump)active->pump(active->context);
    NSDate *slice = [NSDate dateWithTimeIntervalSinceNow:.005];
    if ([limit compare:slice] == NSOrderedAscending) slice = limit;
    NSEvent *event = [super nextEventMatchingMask:mask untilDate:slice inMode:mode dequeue:dequeue];
    if (event) return event;
  } while ((active||menu_loop) && [limit timeIntervalSinceNow] > 0);
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
/* The embedding application supplies activation; a private backing window
 * must never acquire OS focus merely to activate its native field editor. */
- (BOOL)isKeyWindow {return control&&focused==control;}
/* Native menus restore their logical key window after an action. This window
 * is only an editor backing, so that restoration must not map a second widget
 * window beside the embedding application's real control. */
- (void)orderWindow:(NSWindowOrderingMode)place relativeTo:(NSInteger)other
{if(place==NSWindowOut)[super orderWindow:place relativeTo:other];}
/* NSCell flushes its backing window during tracking. Its pixels belong to the
 * embedding widget; never submit this private window to the compositor. */
- (void)flushWindow {[control->view setNeedsDisplay:YES];}
- (void)flushWindowIfNeeded {[control->view setNeedsDisplay:YES];}
/* The application owns its focus order. Export the native window's requests. */
- (void)selectNextKeyView:(id)sender {control->key_result=NXS_INPUT_NEXT;}
- (void)selectPreviousKeyView:(id)sender {control->key_result=NXS_INPUT_PREVIOUS;}
- (void)selectKeyViewFollowingView:(NSView *)view {control->key_result=NXS_INPUT_NEXT;}
- (void)selectKeyViewPrecedingView:(NSView *)view {control->key_result=NXS_INPUT_PREVIOUS;}
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

static NSPoint mouse_location(NXSViewHost *control,double x,double y)
{
  /* Consumers use bitmap coordinates, independent of a UI library's native
   * view orientation. Keep this conversion inside the provider. */
  double localY=[control->view isFlipped]?y:[control->view bounds].size.height-y;
  return [control->view convertPoint:NSMakePoint(x, localY) toView:nil];
}
static NSEvent *mouse(NXSViewHost *control, NSEventType type, double x, double y, unsigned modifiers)
{
  return [NSEvent mouseEventWithType:type location:mouse_location(control,x,y) modifierFlags:flags(modifiers)
    timestamp:[NSDate timeIntervalSinceReferenceDate] windowNumber:[control->window windowNumber]
    context:nil eventNumber:0 clickCount:control->click_count pressure:type == NSLeftMouseUp ? 0 : 1];
}

int nxs_host_initialize(void)
{
  if (NSApp && ![NSApp isKindOfClass:[NXSApplication class]]) return 0;
  if(!NSApp) {
    NSUserDefaults *defaults=[NSUserDefaults standardUserDefaults];
    NSMutableDictionary *arguments=[NSMutableDictionary dictionaryWithDictionary:
      [defaults volatileDomainForName:NSArgumentDomain] ?: @{}];
    [arguments setObject:@YES forKey:@"GSSuppressAppIcon"];
    [arguments setObject:@YES forKey:@"GSSuppressMenuActivation"];
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
  host->click_count=1;
  NXSCommandTarget *proxy=[NXSCommandTarget new];proxy->host=host;host->command_target=proxy;
  host->view=[view retain];host->pump=pump;host->context=context;
  /* Keep geometry in NSWindow until a native auxiliary window is shown. An
   * unmapped backend window cannot acknowledge moves; its stale frame would
   * otherwise anchor native menus at the old screen position. */
  NXSBackingWindow *window=[[NXSBackingWindow alloc] initWithContentRect:[view bounds]
    styleMask:NSBorderlessWindowMask backing:NSBackingStoreBuffered
    defer:!native_backing(view)];
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
  [host->command_target release];
  [host->view removeFromSuperview];
  [host->window close];[host->window release];[host->view release];
  [host->fallback release];
  [host->bitmap release];free(host->pixels);free(host);
  return 1;
}
int nxs_host_replace_view(NXSViewHost *host,NSView *view)
{
  if(!host||!view||nxs_host_tracking(host))return 0;
  BOOL had_focus=nxs_host_focused(host);
  if(had_focus&&!nxs_host_focus(host,0))return 0;
  NSView *previous=host->view;
  host->view=[view retain];[previous removeFromSuperview];
  [view setFrameOrigin:NSZeroPoint];[[host->window contentView] addSubview:view];
  NSSize size=[view frame].size;
  [host->window setContentSize:NSMakeSize(MAX(1,ceil(size.width)),MAX(1,ceil(size.height)))];
  [view setNeedsDisplay:YES];
  if(had_focus&&!nxs_host_focus(host,1)) {
    [view removeFromSuperview];[view release];host->view=previous;
    [[host->window contentView] addSubview:previous];
    size=[previous frame].size;
    [host->window setContentSize:NSMakeSize(MAX(1,ceil(size.width)),MAX(1,ceil(size.height)))];
    nxs_host_focus(host,1);return 0;
  }
  [previous release];return 1;
}
void nxs_host_resize(NXSViewHost *host,NSSize size)
{
  if(!host)return;
  /* The backing covers complete device pixels; the actual native view keeps
   * its logical fractional bounds. Its parent must cover the antialiased edge. */
  NSSize backing=NSMakeSize(ceil(size.width),ceil(size.height));
  if(!NSEqualSizes([[host->window contentView] frame].size,backing))[host->window setContentSize:backing];
  if(!NSEqualSizes([host->view frame].size,size))[host->view setFrame:NSMakeRect(0,0,size.width,size.height)];
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
  NSString *mode=active||menu_loop?NSEventTrackingRunLoopMode:NSDefaultRunLoopMode;
  [loop runMode:mode beforeDate:[NSDate dateWithTimeIntervalSinceNow:maximum_wait]];
  /* Native menus own real auxiliary windows. Run their queued AppKit window
   * and input events as NSApplication normally does, unless a native tracking
   * loop already owns the queue. Never take events out of that loop. */
  unsigned dispatched=0;
  if(!active&&!menu_loop)while(dispatched<1024) {
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
static int view_needs_display(NSView *view)
{
  if([view needsDisplay])return 1;
  for(NSView *child in [view subviews])if(view_needs_display(child))return 1;
  return 0;
}
static void acknowledge_empty_panes(NSView *view)
{
  /* Plain NSView's drawRect: is guaranteed empty. Native tab items
   * create these panes; their application content belongs to the embedding.
   * Consume only that no-op display after drawing the native parent. Actual
   * control subclasses keep their own invalidation and rendering behavior. */
  if([view class]==[NSView class])[view setNeedsDisplay:NO];
  for(NSView *child in [view subviews])acknowledge_empty_panes(child);
}
int nxs_host_needs_display(NXSViewHost *host)
{
  if(!host)return 0;
  /* Native windows track visible display work separately from clipped child
   * dirty flags. Hidden toolbar/scroll content keeps its invalidation until
   * visible; it must not create an embedding repaint loop. */
  return native_backing(host->view)?([host->window viewsNeedDisplay]||[host->view needsDisplay]):view_needs_display(host->view);
}
NXSBitmap nxs_host_draw(NXSViewHost *control, double scale)
{
  NXSBitmap result = {0};
  if (!control || !isfinite(scale) || scale < 1 || scale > 8) return result;
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  NSSize size = [control->view frame].size;
  int width = (int)floor(size.width * scale + .5), height = (int)floor(size.height * scale + .5);
  if (width < 1 || height < 1 || (size_t)width * height > 8 * 1024 * 1024) { [pool drain]; return result; }
  NSBitmapImageRep *bitmap;
  /* Popup raster images must use the ordinary native device coordinates at
   * the actual screen density. The legacy arbitrary-scale image path remains
   * available when callers request a different density. */
  BOOL popup=[control->view isKindOfClass:[NSPopUpButton class]];
  if(native_backing(control->view)&&(!popup||fabs(scale-[control->window backingScaleFactor])<0.000001)) {
    /* AppKit's recursive display restores the window's gstate even with an
     * explicit image context. Render/read the real native backing instead.
     * Its field editor, selection and caret remain wholly native. */
    if(fabs(scale-[control->window backingScaleFactor])>0.000001){[pool drain];return result;}
    NSView *backing=[control->window contentView];
    [backing lockFocus];
    [[NSColor controlBackgroundColor] set];
    NSRectFill(NSIntegralRect([control->view frame]));
    [backing unlockFocus];
    [control->view displayRectIgnoringOpacity:[control->view bounds]];
    [control->view lockFocus];
    NSGraphicsContext *context=[NSGraphicsContext currentContext];
    if([context respondsToSelector:@selector(GSReadRectAtBackingScale:)]) {
      NSDictionary *readback=[context GSReadRectAtBackingScale:[control->view bounds]];
      NSSize dimensions=[[readback objectForKey:@"Size"] sizeValue];
      NSData *data=[readback objectForKey:@"Data"];
      bitmap=[[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL pixelsWide:dimensions.width pixelsHigh:dimensions.height
        bitsPerSample:8 samplesPerPixel:4 hasAlpha:YES isPlanar:NO colorSpaceName:NSDeviceRGBColorSpace
        bytesPerRow:dimensions.width*4 bitsPerPixel:32];
      if(bitmap&&[data length]==[bitmap bytesPerRow]*[bitmap pixelsHigh])memcpy([bitmap bitmapData],[data bytes],[data length]);
      else { [bitmap release];bitmap=nil; }
    } else bitmap=[[NSBitmapImageRep alloc] initWithFocusedViewRect:[control->view bounds]];
    [control->view unlockFocus];[control->view setNeedsDisplay:NO];
    /* These private windows remain unmapped, so NSWindow::displayIfNeeded
     * cannot acknowledge the completed native display for us. */
    [control->window setViewsNeedDisplay:NO];
    /* Native readback defines pixel rounding, including exact half units. */
    width=[bitmap pixelsWide];height=[bitmap pixelsHigh];
    if(width<1||height<1||(size_t)width*height>8*1024*1024){[bitmap release];[pool drain];return result;}
  } else {
  NSImage *image = [[NSImage alloc] initWithSize:NSMakeSize(width, height)];
  [image lockFocus];
  NSAffineTransform *transform = [NSAffineTransform transform];
  [transform translateXBy:0 yBy:height]; [transform scaleXBy:scale yBy:-scale]; [transform concat];
  NSGraphicsContext *context = [NSGraphicsContext currentContext];
  [context lockFocusView:control->view inRect:[control->view bounds]];
  [context GSWSetViewIsFlipped:[control->view isFlipped]];
  struct NXSDrawDensity density;
  if(!begin_draw_density(context,scale,&density)) {
    [context unlockFocusView:control->view needsFlush:NO];[image unlockFocus];[image release];[pool drain];return result;
  }
  @try {
    [[NSColor controlBackgroundColor] set]; NSRectFill(NSMakeRect(0,0,size.width,size.height));
    [control->view drawRect:[control->view bounds]];
  } @finally {end_draw_density(&density);}
  [context unlockFocusView:control->view needsFlush:NO];
  [control->view setNeedsDisplay:NO];
  if(popup)[control->window setViewsNeedDisplay:NO];
  acknowledge_empty_panes(control->view);
  [NSGraphicsContext saveGraphicsState];
  [transform invert]; [transform concat];
  bitmap = [[NSBitmapImageRep alloc] initWithFocusedViewRect:NSMakeRect(0,0,width,height)];
  [NSGraphicsContext restoreGraphicsState]; [image unlockFocus]; [image release];
  }
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
{nxs_host_track_clicks(control,x,y,modifiers,1);}
int nxs_host_track_clicks(NXSViewHost *control,double x,double y,unsigned modifiers,unsigned clicks)
{
  if (!control || active || menu_loop || !clicks || clicks>INT_MAX || !isfinite(x) || !isfinite(y)) return 0;
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  /* Native cells may prepare their track/knob geometry while drawing. An
   * offscreen host has no automatic display pass between resize and input;
   * let the native view finish that pass instead of reproducing its layout. */
  if([control->view needsDisplay])nxs_host_draw(control,1);
  active = control; control->tracking = YES;control->modifiers=modifiers;control->release_queued=NO;control->click_count=clicks;
  NSEvent *event=mouse(control,NSLeftMouseDown,x,y,modifiers);control->pointer=[event locationInWindow];
  NSView *target=control->view;
  if([target isKindOfClass:[NSScrollView class]]||[target isKindOfClass:NSClassFromString(@"GSToolbarView")])
    target=[target hitTest:[[target superview] convertPoint:[event locationInWindow] fromView:nil]];
  @try { [(NXSApplication *)NSApp dispatchNativeEvent:event to:target]; }
  @finally { control->tracking = NO; active = NULL; }
  [pool drain];
  return 1;
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
int nxs_host_action(NXSViewHost *host,void (*action)(NSView *,void *),void *context)
{
  if(!host||!action||active||menu_loop||nxs_host_tracking(host))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  host->dispatch_depth++;active=host;
  @try {action(host->view,context);}
  @finally {host->dispatch_depth--;active=NULL;}
  [pool drain];return 1;
}

int nxs_host_focused(NXSViewHost *host)
{
  if(!host||focused!=host)return 0;
  NSResponder *responder=[host->window firstResponder];
  return responder==focus_view(host)||([host->view isKindOfClass:[NSControl class]]&&
    [(NSControl *)host->view currentEditor]==responder);
}
int nxs_host_focus(NXSViewHost *host,int focus)
{
  if(!host)return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  int accepted=1;
  NXSViewHost *previous=focused;
  host->dispatch_depth++;
  if(previous&&previous!=host)previous->dispatch_depth++;
  if(focus) {
    if(![focus_view(host) acceptsFirstResponder])accepted=0;
    else {
      if(previous&&previous!=host&&![previous->window makeFirstResponder:nil])accepted=0;
      else if(![host->window makeFirstResponder:focus_view(host)]) {
        accepted=0;
        if(previous)[previous->window makeFirstResponder:focus_view(previous)];
      } else {
        focused=host;
        NSResponder *responder=[host->window firstResponder];
        if([responder respondsToSelector:@selector(becomeKeyWindow)])[(id)responder becomeKeyWindow];
      }
    }
  } else if(focused==host) {
    accepted=[host->window makeFirstResponder:nil];
    if(accepted)focused=NULL;
  }
  if(previous&&previous!=host)previous->dispatch_depth--;
  host->dispatch_depth--;
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
static NSEvent *key_event(const NXSKeyEvent *input,NSWindow *window)
{
  if(!input||input->size<sizeof(*input)||input->type>NXS_KEY_MODIFIERS)return nil;
  NSString *text=key_characters(input,NO),*unmodified=key_characters(input,YES);
  if(!text||!unmodified)return nil;
  NSUInteger modifiers=flags(input->modifiers);
  if(input->key>=NXS_KEY_LEFT)modifiers|=NSFunctionKeyMask;
  return [NSEvent keyEventWithType:input->type==NXS_KEY_DOWN?NSKeyDown:input->type==NXS_KEY_UP?NSKeyUp:NSFlagsChanged
    location:NSZeroPoint modifierFlags:modifiers timestamp:[NSDate timeIntervalSinceReferenceDate]
    windowNumber:[window windowNumber] context:nil characters:text
    charactersIgnoringModifiers:unmodified isARepeat:!!input->repeat keyCode:0];
}
int nxs_host_menu_key(NSMenu *menu,const NXSKeyEvent *input)
{
  if(!menu||!input||input->size<sizeof(*input)||input->type!=NXS_KEY_DOWN)return 0;
  NSEvent *event=key_event(input,[menu window]);
  return event&&[(NXSApplication *)NSApp dispatchNativeEvent:event toMenu:menu];
}
int nxs_host_key(NXSViewHost *host,const NXSKeyEvent *input)
{
  if(!host||active||menu_loop||!nxs_host_focused(host))return NXS_INPUT_UNHANDLED;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSEvent *event=key_event(input,host->window);
  if(!event){[pool drain];return NXS_INPUT_UNHANDLED;}
  if([host->view needsDisplay])nxs_host_draw(host,1);
  host->key_result=NXS_INPUT_HANDLED;host->dispatch_depth++;active=host;
  @try {[(NXSApplication *)NSApp dispatchNativeEvent:event to:[host->window firstResponder]];}
  @finally {host->dispatch_depth--;active=NULL;}
  int result=host->key_result;[pool drain];return result;
}
int nxs_host_wheel(NXSViewHost *host,const NXSWheelEvent *input)
{
  if(!host||active||menu_loop||!input||input->size<sizeof(*input)||
     !isfinite(input->x)||!isfinite(input->y)||!isfinite(input->delta_x)||!isfinite(input->delta_y))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  if([host->view needsDisplay])nxs_host_draw(host,1);
  NSPoint point=mouse_location(host,input->x,input->y);
  NSView *target=[host->view hitTest:[[host->view superview] convertPoint:point fromView:nil]];
  if(!target){[pool drain];return 0;}
  double multiplier=[[NSUserDefaults standardUserDefaults] integerForKey:@"GSMouseScrollMultiplier"];
  if(multiplier<.0001)multiplier=1;
  NSEvent *event=[NSEvent mouseEventWithType:NSScrollWheel location:point modifierFlags:flags(input->modifiers)
    timestamp:[NSDate timeIntervalSinceReferenceDate] windowNumber:[host->window windowNumber]
    context:nil eventNumber:0 clickCount:1 pressure:1 buttonNumber:0
    deltaX:input->delta_x*multiplier deltaY:-input->delta_y*multiplier deltaZ:0];
  host->dispatch_depth++;active=host;
  @try {[(NXSApplication *)NSApp dispatchNativeEvent:event to:target];[host->view setNeedsDisplay:YES];}
  @finally {host->dispatch_depth--;active=NULL;}
  [pool drain];return 1;
}
