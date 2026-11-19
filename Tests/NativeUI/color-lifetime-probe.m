/* Exercise original NSColorPanel lifetime through shared control ownership. */
#import <AppKit/AppKit.h>
#include "../../Libraries/NativeUI/NativeUI.h"
#include <assert.h>
#include <stdio.h>
#include <objc/runtime.h>
static unsigned drag_requests;
static BOOL drag_witness(id target,SEL command,NSColor *color,NSEvent *event,NSView *view)
{drag_requests++;return NO;}
static void collect(NSView *view,NSMutableSet *result)
{
  if([view isKindOfClass:[NSColorWell class]])[result addObject:view];
  for(NSView *child in [view subviews])collect(child,result);
}
static NSMutableSet *wells(void)
{
  NSMutableSet *result=[NSMutableSet set];
  for(NSWindow *window in [NSApp windows])collect([window contentView],result);
  return result;
}
static NXSControl *create(NSColorWell **view)
{
  NSMutableSet *before=[[wells() mutableCopy] autorelease];
  NXSControl *control=nxs_control_create(NXS_COLORWELL,NULL,NULL,NULL);assert(control);
  NXSControlConfig config={.size=sizeof(config),.width=80,.height=24,.enabled=1};
  assert(nxs_control_sync(control,&config));
  NSMutableSet *after=wells();[after minusSet:before];assert([after count]==1);
  *view=[after anyObject];return control;
}
int main(void)
{
  NSAutoreleasePool *pool=[NSAutoreleasePool new];NSColorWell *a,*b;
  NXSControl *first=create(&a);assert(nxs_control_color_open(first,1));
  NSColorPanel *panel=[NSColorPanel sharedColorPanel];assert([panel isVisible]&&[a isActive]);
  NSMutableSet *swatches=[NSMutableSet set];collect([panel contentView],swatches);
  NSColorWell *black=nil;
  for(NSColorWell *swatch in swatches)
    if(![swatch isBordered]&&[[swatch color] isEqual:[NSColor blackColor]])black=swatch;
  assert(black);
  [panel display];
  NSPoint point=[black convertPoint:NSMakePoint(NSMidX([black bounds]),NSMidY([black bounds])) toView:nil];
  NSEvent *press=[NSEvent mouseEventWithType:NSLeftMouseDown location:point modifierFlags:0
    timestamp:0 windowNumber:[panel windowNumber] context:nil eventNumber:0 clickCount:1 pressure:1];
  NSEvent *release=[NSEvent mouseEventWithType:NSLeftMouseUp location:point modifierFlags:0
    timestamp:0 windowNumber:[panel windowNumber] context:nil eventNumber:0 clickCount:1 pressure:0];
  Method drag=class_getClassMethod([NSColorPanel class],@selector(dragColor:withEvent:fromView:));
  IMP original_drag=method_setImplementation(drag,(IMP)drag_witness);
  [black mouseDown:press];assert(drag_requests==0);
  [black mouseUp:release];
  assert([a isActive]&&[panel isVisible]&&[[a color] isEqual:[NSColor blackColor]]);
  [black mouseDown:press];
  NSEvent *move=[NSEvent mouseEventWithType:NSLeftMouseDragged location:NSMakePoint(point.x+20,point.y)
    modifierFlags:0 timestamp:0 windowNumber:[panel windowNumber] context:nil eventNumber:0 clickCount:1 pressure:1];
  [black mouseDragged:move];assert(drag_requests==1);
  NSColorWell *plain=[[[NSColorWell alloc] initWithFrame:NSMakeRect(0,0,20,20)] autorelease];
  [plain setBordered:NO];[plain setAction:NULL];[plain mouseDown:press];assert(drag_requests==2);
  method_setImplementation(drag,original_drag);
  NXSControl *second=create(&b);assert(nxs_control_color_open(second,1));
  assert(nxs_control_color_open(first,0)&&[panel isVisible]&&[b isActive]);
  [b deactivate];assert([panel isVisible]&&![b isActive]);
  assert(nxs_control_color_open(second,0)&&![panel isVisible]);
  assert(nxs_control_color_open(first,1)&&[panel isVisible]);
  assert(nxs_control_destroy(first)&&![panel isVisible]);
  /* The original well can present before the queued protocol enter activates
   * NSApplication. A superseding leave must still hide that presentation. */
  [NSApp deactivate];assert(![NSApp isActive]);
  first=create(&a);assert(nxs_control_color_open(first,1)&&[panel isVisible]);
  assert(![NSApp isActive]);
  [NSApp deactivate];assert(![panel isVisible]);
  assert(![panel isKeyWindow]);
  [NSApp activateIgnoringOtherApps:YES];assert(![panel isVisible]);
  assert(nxs_control_destroy(first));
  first=create(&a);assert(nxs_control_color_open(second,1));
  assert(nxs_control_destroy(first)&&[panel isVisible]&&[b isActive]);
  assert(nxs_control_destroy(second)&&![panel isVisible]);
  first=create(&a);second=create(&b);
  assert(nxs_control_color_panel_capabilities()&NXS_COLOR_PANEL_CLOSE_ACK);
  assert(nxs_control_color_lifecycle(first,NXS_COLOR_CLOSE_REQUIRE_ACK));
  assert(nxs_control_color_open(first,1));
  assert(![NSApp isRunning]);[panel makeKeyWindow];assert([panel isKeyWindow]);
  [panel performClose:nil];
  assert([panel isVisible]&&![a isActive]);
  assert(nxs_control_color_lifecycle(first,NXS_COLOR_CLOSE_COMPLETE)&&![panel isVisible]);
  assert(![panel isKeyWindow]);
  assert(nxs_control_color_lifecycle(first,NXS_COLOR_CLOSE_COMPLETE)&&![panel isVisible]);
  assert(nxs_control_color_open(first,1));[panel performClose:nil];
  assert(nxs_control_color_open(second,1)&&[panel isVisible]&&[b isActive]);
  assert(nxs_control_color_lifecycle(first,NXS_COLOR_CLOSE_COMPLETE)&&[panel isVisible]&&[b isActive]);
  assert(nxs_control_destroy(first)&&[panel isVisible]);
  assert(nxs_control_destroy(second)&&![panel isVisible]);
  first=create(&a);assert(nxs_control_color_lifecycle(first,NXS_COLOR_CLOSE_REQUIRE_ACK));
  assert(nxs_control_color_open(first,1));[panel performClose:nil];
  assert([panel isVisible]&&nxs_control_destroy(first)&&![panel isVisible]);
  first=create(&a);assert(nxs_control_color_open(first,1));
  [NSApp activateIgnoringOtherApps:YES];assert([NSApp isActive]&&[panel hidesOnDeactivate]);
  [NSApp deactivate];assert(![panel isVisible]);
  [NSApp activateIgnoringOtherApps:YES];assert(![panel isVisible]);
  assert(nxs_control_color_open(first,1)&&[panel isVisible]&&[a isActive]);
  assert(nxs_control_destroy(first)&&![panel isVisible]);
  puts("{\"palette_selection_preserves_owner\":true,\"native_palette_click_and_drag\":true,\"plain_unbordered_drag_preserved\":true,\"inactive_owner_close\":true,\"destroy_closes_owned_panel\":true,\"other_owner_preserved\":true,\"close_waits_for_original_model_ack\":true,\"stale_owner_ack_preserves_new_panel\":true,\"destroy_pending_close\":true,\"acknowledged_close_resigns_native_key_window\":true,\"inactive_presentation_is_hidden\":true,\"reactivation_does_not_revive_old_panel\":true,\"original_owner_can_reopen_after_deactivation\":true}");
  [pool drain];return 0;
}
