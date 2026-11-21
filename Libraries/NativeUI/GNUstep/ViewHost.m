/* One native view host shared by every provider control. GPL-2.0-or-later. */
#import "ViewHost.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include <objc/runtime.h>
#include <GNUstepGUI/GSDisplayServer.h>
@interface NSObject (NXSWindowActivation)
- (BOOL)activatewindow:(int)number withToken:(NSString *)token;
- (BOOL)setforeignparent:(NSString *)handle forwindow:(int)number;
@end
@interface NSGraphicsContext (NXSBackingReadback)
- (NSDictionary *)GSReadRectAtBackingScale:(NSRect)rect;
@end
struct NXSViewHost {
  NSView *view;
  NSWindow *window;
  NSBitmapImageRep *bitmap;
  unsigned char *pixels;
  NSSize drawn_size;
  double drawn_scale;
  NXSPump pump;
  void *context;
  BOOL tracking;
  unsigned modifiers;
  unsigned click_count;
  NSPoint pointer;
  NSPoint screen_origin;
  BOOL screen_origin_valid;
  NXSRect screen_bounds;
  BOOL screen_bounds_valid;
  BOOL injected_pointer;
  BOOL release_queued;
  BOOL pointer_events;
  NSResponder *pointer_target;
  NSWindow *tracking_popup_window;
  unsigned dispatch_depth;
  int key_result;
  NSResponder *fallback;
  id command_target;
  NXSCommandFilter command_filter;
  void *command_context;
  NSString *auxiliary_parent;
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
{return [view isKindOfClass:[NSTextField class]]||[view isKindOfClass:[NSScrollView class]]||[view isKindOfClass:[NSPopUpButton class]]||[view isKindOfClass:[NSMatrix class]]||[view isKindOfClass:[NSBrowser class]]||[view isKindOfClass:[NSStepper class]]||[view isKindOfClass:[NSColorWell class]]||[view isKindOfClass:[NSDatePicker class]]||[view isKindOfClass:NSClassFromString(@"GSToolbarView")];}
static NSView *focus_view(NXSViewHost *host)
{return [host->view isKindOfClass:[NSScrollView class]]?[(NSScrollView *)host->view documentView]:host->view;}
static NXSMenuLoop *menu_loop;
void nxs_host_menu_begin(NXSMenuLoop *scope)
{scope->previous=menu_loop;menu_loop=scope;}
void nxs_host_menu_end(NXSMenuLoop *scope)
{
  /* Activation can close a tracking menu while a model callback is pumping
   * another client. Unlink that scope even when the callback is above it. */
  NXSMenuLoop **link=&menu_loop;
  while(*link&&*link!=scope)link=&(*link)->previous;
  if(*link)*link=scope->previous;
  scope->previous=NULL;
}
static BOOL menu_tracks_input(void)
{
  for(NXSMenuLoop *scope=menu_loop;scope;scope=scope->previous)
    if(scope->tracking)return YES;
  return NO;
}
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
unsigned nxs_host_auxiliary_capabilities(void)
{id server=GSCurrentServer();return ([server respondsToSelector:@selector(activatewindow:withToken:)]?1:0)|
  ([server respondsToSelector:@selector(setforeignparent:forwindow:)]?2:0);}
int nxs_host_window_parent(NSWindow *window,const char *handle)
{
  if(!window||(handle&&(!*handle||strlen(handle)>4096))||!(nxs_host_auxiliary_capabilities()&2))return 0;
  return [(id)GSCurrentServer() setforeignparent:handle?[NSString stringWithUTF8String:handle]:nil
    forwindow:(int)[window windowNumber]];
}
int nxs_host_window_activate(NSWindow *window,const char *token)
{
  if(!window||!token||!*token||strlen(token)>4096||!(nxs_host_auxiliary_capabilities()&1))return 0;
  return [(id)GSCurrentServer() activatewindow:(int)[window windowNumber]
    withToken:[NSString stringWithUTF8String:token]];
}
static NSWindow *auxiliary_window(NXSViewHost *host)
{
  NSWindow *window=nil;
  for(struct NXSInputWindow *entry=input_windows;entry;entry=entry->next)
    if(entry->host==host&&[entry->window isVisible]) {
      if(window)return nil;
      window=entry->window;
    }
  return window;
}
int nxs_host_auxiliary_parent(NXSViewHost *host,const char *handle)
{
  if(!host||(handle&&(!*handle||strlen(handle)>4096))||!(nxs_host_auxiliary_capabilities()&2))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];NSWindow *window=auxiliary_window(host);
  int result=nxs_host_window_parent(window,handle);
  if(result) {
    [host->auxiliary_parent release];
    host->auxiliary_parent=handle?[[NSString alloc] initWithUTF8String:handle]:nil;
  }
  [pool drain];return result;
}
int nxs_host_auxiliary_activate(NXSViewHost *host,const char *token)
{
  if(!host||!token||!*token||strlen(token)>4096||!nxs_host_auxiliary_capabilities())return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];int accepted=0;
  NSWindow *window=auxiliary_window(host);
  /* AppKit remembers panels hidden on application deactivation. This host
     serves several foreign windows: their old panels must not reappear when
     another owner activates a component. orderOut also clears AppKit's own
     inactive-window bookkeeping, without replacing its panel lifecycle. */
  if(window&&host->auxiliary_parent)
    for(struct NXSInputWindow *entry=input_windows;entry;entry=entry->next)
      if(entry->host!=host&&entry->host->auxiliary_parent&&
         ![entry->host->auxiliary_parent isEqual:host->auxiliary_parent])
        [entry->window orderOut:nil];
  if(window)accepted=nxs_host_window_activate(window,token);
  [pool drain];return accepted;
}
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
    if(entry->window==window){entry->host=host;return;}
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
int nxs_host_owns_input_window(NXSViewHost *host,NSWindow *window)
{
  for(struct NXSInputWindow *entry=input_windows;entry;entry=entry->next)
    if(entry->window==window)return entry->host==host;
  return 0;
}
/* The native control owns the tracking loop. While it waits, dispatch the embedding
 * toolkit so real pointer events and its other windows remain responsive. */
@interface NXSApplication : NSApplication
- (void)dispatchNativeEvent:(NSEvent *)event to:(NSResponder *)responder;
- (BOOL)dispatchNativeEvent:(NSEvent *)event toMenu:(NSMenu *)menu;
@end
@implementation NXSApplication
- (void)deactivate
{
  [super deactivate];
  /* This component host serves foreign owners, rather than one application.
   * Forget AppKit's hidden auxiliary presentations when it deactivates, so a
   * later native field or menu cannot revive another owner's old panel.
   * A well can also show its panel before the queued protocol enter activates
   * NSApplication. Hide that presentation on a superseding leave as well.
   * NSWindow owns the inactive-window bookkeeping and the next explicit open. */
  for(struct NXSInputWindow *entry=input_windows;entry;entry=entry->next)
    if([entry->window hidesOnDeactivate])
      [entry->window orderOut:nil];
}
/* AppKit resolves nil-target menu actions through the embedding application's
 * logical key window, without ordering a private backing window on screen. */
- (NSWindow *)keyWindow
{
  NSWindow *native=[super keyWindow];
  /* This component host does not run a separate application's launch/services
   * lifecycle. Resolve the original AppKit modal key window directly, just
   * as embedded controls below resolve their logical key window. AppKit still
   * owns modal ordering, key equivalents and responder dispatch. */
  NSWindow *modal=[self modalWindow];
  if(nxs_gnustep_file_panel_active()&&[modal isVisible]&&[modal isKeyWindow])return modal;
  for(struct NXSInputWindow *entry=input_windows;entry;entry=entry->next)
    if([entry->window isVisible]&&[entry->window isKeyWindow])return entry->window;
  return focused&&!nxs_gnustep_file_panel_active()?focused->window:native;
}
- (id)targetForAction:(SEL)action to:(id)recipient from:(id)sender
{
  id native=[super targetForAction:action to:recipient from:sender];
  /* Editing commands can belong to either the field editor (selection and
   * clipboard) or its native window (undo/redo). Preserve that responder
   * lookup, then offer the semantic action to the application's transaction
   * binding. Auxiliary windows retain their own native responder chain. */
  if(native&&focused&&focused->command_filter&&[self keyWindow]==focused->window&&
     (native==[focused->window firstResponder]||native==focused->window)) {
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
      case NSLeftMouseDragged:[responder mouseDragged:event];break;
      case NSLeftMouseUp:[responder mouseUp:event];break;
      case NSScrollWheel:[responder scrollWheel:event];break;
      case NSKeyDown: {
        /* Menu matching already ran for this model. Let its native responder
         * interpret only unmatched input; the transported application-menu
         * fallback runs after tracking closes. Consulting mainMenu here
         * would also execute it during a context-menu reservation query. */
        if([responder isKindOfClass:[NSMenuView class]]) {
          [responder keyDown:event];break;
        }
        /* Reuse the editor's native command menu, including its key equivalents
         * and validation. Do not maintain an embedding-specific shortcut table. */
        /* An embedded editor with an application transaction binding owns
         * native editing actions. An imported application menu has opaque
         * command IDs, not this editor's real responder chain; letting it
         * intercept editing first can defer Copy until a subsequent edit.
         * Resolve the native editor menu in its bound responder context,
         * then offer all unclaimed commands to the application menu. */
        NSMenu *editor=[responder isKindOfClass:[NSView class]]?[(NSView *)responder menu]:nil;
        BOOL bound=focused&&focused->command_filter&&[self keyWindow]==focused->window;
        if(bound) {
          if([editor performKeyEquivalent:event])break;
          /* Ordinary text input and native editing modifiers belong to the
           * native responder. Updating an opaque remote application menu here
           * would synchronously validate another process during text input. */
          if(!([event modifierFlags]&NSCommandKeyMask)){[responder keyDown:event];break;}
        }
        if(![[self mainMenu] performKeyEquivalent:event]&&
           !(!bound&&[editor performKeyEquivalent:event]))
          [responder keyDown:event];
        break;
      }
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
  /* NSMenu owns key matching and validates its match. A blanket update first
   * queries every foreign command even when this key belongs to an editor. */
  @try {return [menu performKeyEquivalent:event];}
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
    /* Wayland can unmap the menu during its initial mouse-down. The release
     * then goes to the window underneath. Unwind AppKit's original tracking
     * loop without activating a row in the dismissed menu. */
    if ((mask&NSLeftMouseUpMask) && active && active->tracking_popup_window &&
        ![active->tracking_popup_window isVisible])
      nxs_host_send(active,NXS_RELEASE,-10000,-10000,0);
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
- (NSAffineTransform *)screenProjection
{
  if(!control||!control->screen_bounds_valid)return nil;
  NSRect local=[control->view convertRect:[control->view bounds] toView:nil];
  if(NSWidth(local)<=0||NSHeight(local)<=0)return nil;
  NXSRect bounds=control->screen_bounds;
  NSRect screen=[[NSScreen mainScreen] frame];
  NSAffineTransform *transform=[NSAffineTransform transform];
  [transform translateXBy:NSMinX(screen)+bounds.x yBy:NSMaxY(screen)-bounds.y-bounds.height];
  [transform scaleXBy:bounds.width/NSWidth(local) yBy:bounds.height/NSHeight(local)];
  [transform translateXBy:-NSMinX(local) yBy:-NSMinY(local)];
  return transform;
}
- (NSPoint)convertBaseToScreen:(NSPoint)point
{
  NSAffineTransform *transform=[self screenProjection];
  return transform?[transform transformPoint:point]:[super convertBaseToScreen:point];
}
- (NSPoint)convertScreenToBase:(NSPoint)point
{
  NSAffineTransform *transform=[self screenProjection];
  if(!transform)return [super convertScreenToBase:point];
  [transform invert];return [transform transformPoint:point];
}
- (NSRect)convertRectToScreen:(NSRect)rect
{
  NSAffineTransform *transform=[self screenProjection];
  if(!transform)return [super convertRectToScreen:rect];
  return (NSRect){[transform transformPoint:rect.origin],[transform transformSize:rect.size]};
}
- (NSRect)convertRectFromScreen:(NSRect)rect
{
  NSAffineTransform *transform=[self screenProjection];
  if(!transform)return [super convertRectFromScreen:rect];
  [transform invert];return (NSRect){[transform transformPoint:rect.origin],[transform transformSize:rect.size]};
}
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

static unsigned physical_modifier(unsigned modifier)
{
  NSString *key, *fallback;
  switch (modifier) {
    case NXS_MENU_COMMAND: key=@"GSFirstCommandKey"; fallback=@"Alt_L"; break;
    case NXS_MENU_CONTROL: key=@"GSFirstControlKey"; fallback=@"Control_L"; break;
    case NXS_MENU_ALTERNATE: key=@"GSFirstAlternateKey"; fallback=@"Super_L"; break;
    case NXS_MENU_SHIFT: return NXS_SHIFT;
    default: return 0;
  }
  NSString *name=[[NSUserDefaults standardUserDefaults] stringForKey:key] ?: fallback;
  return [name hasPrefix:@"Control_"] ? NXS_CONTROL : [name hasPrefix:@"Alt_"] ? NXS_ALT :
    ([name hasPrefix:@"Super_"] || [name hasPrefix:@"Meta_"]) ? NXS_SUPER : 0;
}

unsigned nxs_host_physical_modifier(unsigned modifier)
{
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  unsigned family=physical_modifier(modifier);
  [pool drain];
  return family;
}

static NSUInteger flags(unsigned modifiers)
{
  NSUInteger result=(modifiers & NXS_SHIFT) ? NSShiftKeyMask : 0;
  unsigned control=physical_modifier(NXS_MENU_CONTROL);
  unsigned command=physical_modifier(NXS_MENU_COMMAND) & ~control;
  unsigned alternate=physical_modifier(NXS_MENU_ALTERNATE) & ~(control | command);
  if(modifiers & control) result |= NSControlKeyMask;
  if(modifiers & command) result |= NSCommandKeyMask;
  if(modifiers & alternate) result |= NSAlternateKeyMask;
  return result;
}

static NSPoint mouse_location(NXSViewHost *control,double x,double y)
{
  /* Consumers use bitmap coordinates, independent of a UI library's native
   * view orientation. Keep this conversion inside the provider. */
  double localY=[control->view isFlipped]?y:[control->view bounds].size.height-y;
  return [control->view convertPoint:NSMakePoint(x, localY) toView:nil];
}
NSPoint nxs_host_point_to_view(NXSViewHost *host,NSView *view,double x,double y)
{return [view convertPoint:mouse_location(host,x,y) fromView:nil];}
NSView *nxs_host_hit_view(NXSViewHost *host,double x,double y)
{
  NSPoint point=mouse_location(host,x,y);
  return [host->view hitTest:[[host->view superview] convertPoint:point fromView:nil]];
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
  [host->auxiliary_parent release];
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
static void document_positions(NSView *view,NSMutableArray *positions)
{
  if([view isKindOfClass:[NSClipView class]]) {
    NSView *document=[(NSClipView *)view documentView];
    if(document)[positions addObject:@{ @"clip":view,@"document":document,
      @"visible":[NSValue valueWithRect:[(NSClipView *)view documentVisibleRect]] }];
  }
  for(NSView *child in [view subviews])document_positions(child,positions);
}
NSArray *nxs_host_document_positions(NXSViewHost *host)
{
  NSMutableArray *positions=[NSMutableArray array];
  if(host&&!nxs_host_tracking(host))document_positions(host->view,positions);
  return positions;
}
void nxs_host_restore_document_positions(NXSViewHost *host,NSArray *positions)
{
  if(!host||nxs_host_tracking(host))return;
  for(NSDictionary *position in positions) {
    NSClipView *clip=[position objectForKey:@"clip"];NSView *document=[position objectForKey:@"document"];
    if([clip documentView]!=document||[clip window]!=host->window)continue;
    [[clip enclosingScrollView] reflectScrolledClipView:clip];
    NSRect visible=[[position objectForKey:@"visible"] rectValue];NSPoint point=visible.origin;
    if(![document isFlipped])point.y=NSMaxY(visible)-[clip documentVisibleRect].size.height;
    [document scrollPoint:point];
  }
}
void nxs_host_resize(NXSViewHost *host,NSSize size)
{
  if(!host)return;
  /* The backing covers complete device pixels; the actual native view keeps
   * its logical fractional bounds. Its parent must cover the antialiased edge. */
  NSSize backing=NSMakeSize(ceil(size.width),ceil(size.height));
  if(!NSEqualSizes([[host->window contentView] frame].size,backing))[host->window setContentSize:backing];
  if(!NSEqualSizes([host->view frame].size,size))[host->view setFrame:NSMakeRect(0,0,size.width,size.height)];
  /* The embedding API supplies a top-left screen anchor. NSWindow resizing
   * keeps its bottom-left origin, so restore the same anchor after the view
   * acquires its real size (including an origin supplied before first sync). */
  if(host->screen_origin_valid)nxs_host_set_screen_origin(host,host->screen_origin.x,host->screen_origin.y);
}
int nxs_host_set_screen_origin(NXSViewHost *host,double x,double y)
{
  if(!host||!isfinite(x)||!isfinite(y)||fabs(x)>1e7||fabs(y)>1e7||nxs_host_tracking(host))return 0;
  host->screen_origin=NSMakePoint(x,y);host->screen_origin_valid=YES;
  NSRect screen=[[NSScreen mainScreen] frame];
  [host->window setFrameOrigin:NSMakePoint(NSMinX(screen)+x,NSMaxY(screen)-y-[host->view frame].size.height)];
  return 1;
}
int nxs_host_set_screen_bounds(NXSViewHost *host,NXSRect bounds)
{
  BOOL reset=bounds.width==0&&bounds.height==0;
  if(!host||!isfinite(bounds.width)||!isfinite(bounds.height)||
     (!reset&&(bounds.width<=0||bounds.height<=0||bounds.width>1e7||bounds.height>1e7))||
     !nxs_host_set_screen_origin(host,bounds.x,bounds.y))return 0;
  /* Only global conversion changes. The same view, field editor, local input
   * and raster backing retain their original model and native coordinates. */
  host->screen_bounds=bounds;host->screen_bounds_valid=!reset;return 1;
}
NXSRect nxs_host_rect_from_view(NXSViewHost *host,NSView *view,NSRect rect)
{
  if(!host||!view||![view window])return (NXSRect){0};
  rect=[view convertRect:rect toView:nil];
  rect=[[view window] convertRectToScreen:rect];
  rect=[host->window convertRectFromScreen:rect];
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
    if(owner&&[event type]==NSLeftMouseDown&&[owner->view isKindOfClass:[NSPopUpButton class]])
      owner->tracking_popup_window=[event window];
    @try {[NSApp sendEvent:event];}
    @finally {if(owner){owner->tracking_popup_window=nil;owner->dispatch_depth--;active=NULL;}}
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
  if (!control || !isfinite(scale) || scale < .125 || scale > 8) return result;
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  NSSize size = [control->view frame].size;
  if(control->bitmap&&control->pixels&&control->drawn_scale==scale&&
     NSEqualSizes(control->drawn_size,size)&&!nxs_host_needs_display(control)) {
    result=(NXSBitmap){[control->bitmap pixelsWide],[control->bitmap pixelsHigh],
      [control->bitmap pixelsWide]*4,control->pixels};
    [pool drain];return result;
  }
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
    double backingScale=[control->window backingScaleFactor];
    int requestedWidth=width,requestedHeight=height;
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
    if(fabs(scale-backingScale)>0.000001) {
      /* Browser zoom can differ from the screen density. Keep the original
       * view hierarchy/editor drawing, then let AppKit compose its native
       * image at the requested presentation density. No control drawing,
       * font metrics, caret or selection implementation is reproduced. */
      NSImage *source=[[NSImage alloc] initWithSize:size];
      [bitmap setSize:size];[source addRepresentation:bitmap];
      NSImage *target=[[NSImage alloc] initWithSize:NSMakeSize(requestedWidth,requestedHeight)];
      [target lockFocus];
      [source drawInRect:NSMakeRect(0,0,requestedWidth,requestedHeight)
        fromRect:NSZeroRect operation:NSCompositeCopy fraction:1];
      NSBitmapImageRep *scaled=[[NSBitmapImageRep alloc]
        initWithFocusedViewRect:NSMakeRect(0,0,requestedWidth,requestedHeight)];
      [target unlockFocus];[target release];[source release];[bitmap release];bitmap=scaled;
      width=[bitmap pixelsWide];height=[bitmap pixelsHigh];
      if(width!=requestedWidth||height!=requestedHeight){[bitmap release];[pool drain];return result;}
    }
  } else {
  NSImage *image = [[NSImage alloc] initWithSize:NSMakeSize(width, height)];
  [image lockFocus];
  [NSGraphicsContext saveGraphicsState];
  NSAffineTransform *transform = [NSAffineTransform transform];
  [transform translateXBy:0 yBy:height]; [transform scaleXBy:scale yBy:-scale]; [transform concat];
  NSGraphicsContext *context = [NSGraphicsContext currentContext];
  [context lockFocusView:control->view inRect:[control->view bounds]];
  [context GSWSetViewIsFlipped:[control->view isFlipped]];
  struct NXSDrawDensity density;
  if(!begin_draw_density(context,scale,&density)) {
    [context unlockFocusView:control->view needsFlush:NO];[NSGraphicsContext restoreGraphicsState];[image unlockFocus];[image release];[pool drain];return result;
  }
  @try {
    [[NSColor controlBackgroundColor] set]; NSRectFill(NSMakeRect(0,0,size.width,size.height));
    [control->view drawRect:[control->view bounds]];
  } @finally {end_draw_density(&density);}
  [context unlockFocusView:control->view needsFlush:NO];
  [control->view setNeedsDisplay:NO];
  if(popup)[control->window setViewsNeedDisplay:NO];
  acknowledge_empty_panes(control->view);
  /* Restore the exact image CTM. Multiplying by an inverse can leave an
   * integral edge infinitesimally short; native readback then floors it. */
  [NSGraphicsContext restoreGraphicsState];
  bitmap = [[NSBitmapImageRep alloc] initWithFocusedViewRect:NSMakeRect(0,0,width,height)];
  [image unlockFocus]; [image release];
  }
  /* Never expose dimensions different from the native allocation. Both the
   * copy below and a later cached read must describe the same complete image. */
  if(!bitmap||[bitmap pixelsWide]!=width||[bitmap pixelsHigh]!=height||[bitmap bytesPerRow]<width*4) {
    control->drawn_scale=0;[bitmap release];[pool drain];return result;
  }
  [control->bitmap release]; control->bitmap = bitmap;
  unsigned char *pixels = realloc(control->pixels, (size_t)width * height * 4);
  if (pixels) {
    control->pixels = pixels;
    control->drawn_size=size;control->drawn_scale=scale;
    /* AppKit readback is RGBA; the two embedding toolkits accept native ARGB32. */
    const unsigned char *source = [bitmap bitmapData];
    for (int y = 0; y < height; y++) for (int x = 0; x < width; x++) {
      const unsigned char *p = source + y * [bitmap bytesPerRow] + 4 * x;
      ((uint32_t *)pixels)[y * width + x] = ((uint32_t)p[3] << 24) |
        ((uint32_t)p[0] << 16) | ((uint32_t)p[1] << 8) | p[2];
    }
    result = (NXSBitmap){width, height, width * 4, pixels};
  } else control->drawn_scale=0;
  [pool drain];
  return result;
}

void nxs_host_track(NXSViewHost *control, double x, double y, unsigned modifiers)
{nxs_host_track_clicks(control,x,y,modifiers,1);}
void nxs_host_pointer_events(NXSViewHost *host,int enabled)
{if(host&&!nxs_host_tracking(host))host->pointer_events=!!enabled;}
static void finish_pointer(NXSViewHost *host)
{
  host->tracking=NO;if(active==host)active=NULL;
  [host->pointer_target release];host->pointer_target=nil;
}
int nxs_host_track_clicks(NXSViewHost *control,double x,double y,unsigned modifiers,unsigned clicks)
{
  if (!control || active || menu_tracks_input() || !clicks || clicks>INT_MAX || !isfinite(x) || !isfinite(y)) return 0;
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  /* Native cells may prepare their track/knob geometry while drawing. An
   * offscreen host has no automatic display pass between resize and input;
   * let the native view finish that pass instead of reproducing its layout. */
  if([control->view needsDisplay])nxs_host_draw(control,[control->window backingScaleFactor]);
  active = control; control->tracking = YES;control->modifiers=modifiers;control->release_queued=NO;control->click_count=clicks;
  NSEvent *event=mouse(control,NSLeftMouseDown,x,y,modifiers);control->pointer=[event locationInWindow];
  NSView *target=control->view;
  if([target isKindOfClass:[NSScrollView class]]||[target isKindOfClass:[NSBrowser class]]||[target isKindOfClass:NSClassFromString(@"GSToolbarView")])
    target=[target hitTest:[[target superview] convertPoint:[event locationInWindow] fromView:nil]];
  BOOL completed=NO;
  if(control->pointer_events){control->pointer_target=[target retain];control->dispatch_depth++;}
  @try { [(NXSApplication *)NSApp dispatchNativeEvent:event to:target];completed=YES; }
  @finally {
    if(control->pointer_events)control->dispatch_depth--;
    if(!control->pointer_events||!completed||control->release_queued)finish_pointer(control);
  }
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
  if(control->pointer_events&&!control->dispatch_depth) {
    BOOL completed=NO;control->dispatch_depth++;
    @try {[(NXSApplication *)NSApp dispatchNativeEvent:mouseEvent to:control->pointer_target];completed=YES;}
    @finally {control->dispatch_depth--;if(!completed||control->release_queued)finish_pointer(control);}
  } else [NSApp postEvent:mouseEvent atStart:NO];
  [pool drain];
}

int nxs_host_tracking(NXSViewHost *host){return host&&(host->tracking||host->dispatch_depth);}
int nxs_host_action(NXSViewHost *host,void (*action)(NSView *,void *),void *context)
{
  /* A model callback may pump an unrelated client's activation while waiting
   * for its owner. Only real NSMenu tracking owns the pointer at that point. */
  if(!host||!action||active||menu_tracks_input()||nxs_host_tracking(host))return 0;
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
  return responder==focus_view(host)||([responder isKindOfClass:[NSView class]]&&[(NSView *)responder isDescendantOf:host->view])||([host->view isKindOfClass:[NSControl class]]&&
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

@interface NXSEditInputManager : NSInputManager
- (BOOL)awaitingKey;
@end
@implementation NXSEditInputManager
- (BOOL)awaitingKey
{return [_pendingKeyEvents count]!=0||_interpretNextKeyStrokeLiterally;}
@end

@interface NXSEditReceiver : NSResponder {
 @public NSMutableArray *commands;
}
@end
@implementation NXSEditReceiver
- (void)doCommandBySelector:(SEL)selector
{if(selector)[commands addObject:NSStringFromSelector(selector)];}
- (void)insertText:(id)text
{(void)text;} /* Literal input remains with the original editor and its IME. */
- (void)receiveMenuCommand:(NSMenuItem *)item
{[self doCommandBySelector:NSSelectorFromString([item representedObject])];}
@end

struct NXSEditBindings {
  NXSEditInputManager *manager;
  NXSEditReceiver *receiver;
  NSMenu *menu;
};

NXSEditBindings *nxs_host_edit_bindings_create(void)
{
  if(![NSThread isMainThread])return NULL;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NXSEditBindings *bindings=nxs_host_initialize()?calloc(1,sizeof(*bindings)):NULL;
  if(bindings) {
    bindings->manager=[[NXSEditInputManager alloc] initWithName:nil host:nil];
    bindings->receiver=[NXSEditReceiver new];
    /* Use the installed NSTextView edit menu's real actions and equivalents.
       Project a private command target, without creating a field editor. */
    bindings->menu=[[NSTextView defaultMenu] copy];
    [bindings->menu setAutoenablesItems:NO];
    for(NSMenuItem *item in [bindings->menu itemArray]) {
      SEL action=[item action];
      if(!action)continue;
      [item setRepresentedObject:NSStringFromSelector(action)];
      [item setTarget:bindings->receiver];
      [item setAction:@selector(receiveMenuCommand:)];
      [item setEnabled:YES];
    }
    if(!bindings->manager||!bindings->receiver||!bindings->menu) {
      nxs_host_edit_bindings_destroy(bindings);
      bindings=NULL;
    }
  }
  [pool drain];return bindings;
}

void nxs_host_edit_bindings_destroy(NXSEditBindings *bindings)
{
  if(!bindings)return;
  [bindings->menu release];
  [bindings->manager release];
  [bindings->receiver release];
  free(bindings);
}

void nxs_host_edit_bindings_reset(NXSEditBindings *bindings)
{
  if(!bindings)return;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  [bindings->manager resetInternalState];
  [pool drain];
}

int nxs_host_edit_bindings_resolve(NXSEditBindings *bindings,const NXSKeyEvent *input,NXSEditCommand receive,void *context)
{
  if(!bindings||!receive||!input||input->size<sizeof(*input)||input->type!=NXS_KEY_DOWN)
    return NXS_EDIT_UNBOUND;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  int result=NXS_EDIT_UNBOUND;
  @try {
    NSEvent *event=key_event(input,nil);
    if(event) {
      NSMutableArray *commands=[NSMutableArray array];
      bindings->receiver->commands=commands;
      @try {
        if([(NXSApplication *)NSApp dispatchNativeEvent:event toMenu:bindings->menu])
          [bindings->manager resetInternalState];
        else [bindings->manager handleKeyboardEvents:@[event] client:bindings->receiver];
        result=[commands count]?NXS_EDIT_COMMANDS:
          [bindings->manager awaitingKey]?NXS_EDIT_SEQUENCE:NXS_EDIT_UNBOUND;
      }
      @finally {bindings->receiver->commands=nil;}
      for(NSString *command in commands)receive(context,[command UTF8String]);
    }
  }
  @finally {[pool drain];}
  return result;
}

int nxs_host_responder_key(NSResponder *responder,NSWindow *window,const NXSKeyEvent *input)
{
  NSEvent *event=key_event(input,window);if(!event)return 0;
  [(NXSApplication *)NSApp dispatchNativeEvent:event to:responder];return 1;
}
int nxs_host_key(NXSViewHost *host,const NXSKeyEvent *input)
{
  if(!host||active||menu_loop||!nxs_host_focused(host))return NXS_INPUT_UNHANDLED;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSWindow *destination=host->window,*native=[NSApp keyWindow];
  for(struct NXSInputWindow *entry=input_windows;entry;entry=entry->next)
    if(entry->host==host&&entry->window==native&&[native isVisible]){destination=native;break;}
  NSEvent *event=key_event(input,destination);
  if(!event){[pool drain];return NXS_INPUT_UNHANDLED;}
  if([host->view needsDisplay])nxs_host_draw(host,1);
  host->key_result=NXS_INPUT_HANDLED;host->dispatch_depth++;active=host;
  @try {[(NXSApplication *)NSApp dispatchNativeEvent:event to:[destination firstResponder]];}
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
  NSView *target=nxs_host_hit_view(host,input->x,input->y);
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

void nxs_host_popup_pointer(NXSViewHost *host,NSWindow *window,BOOL enabled)
{
  if(!host)return;
  if(enabled){host->pointer=NSMakePoint(0,[host->view frame].size.height);nxs_host_bind_input_window(host,window);}
  host->injected_pointer=enabled;
}
