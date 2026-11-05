/* Instantiate native controls; drawing and interaction remain in AppKit.
 * GPL-2.0-or-later. */
#import "ViewHost.h"
#include "Provider.h"
#include <math.h>
#include <stdlib.h>
struct NXSControl {
  int kind,enabled;
  NSView *view;
  NXSViewHost *host;
  id target;
  NXSControlChanged changed;
  void *context;
  double step;
};
static void slider_model(NXSControl *control)
{
  NSSlider *view=(NSSlider *)control->view;
  double intervals=control->step>0?([view maxValue]-[view minValue])/control->step:0;
  /* Dense domains retain the native continuous presentation. Small domains
   * use the existing native tick/snap implementation, including its keys. */
  NSInteger ticks=isfinite(intervals)&&intervals>=1&&intervals<=63?(NSInteger)llround(intervals)+1:0;
  [view setNumberOfTickMarks:ticks];[view setAllowsTickMarkValuesOnly:ticks>1];
  [view setDoubleValue:[view doubleValue]];
}
@interface NXSControlAction : NSObject { @public NXSControl *control; }
- (void)changed:(id)sender;
- (void)willPopUp:(NSNotification *)notification;
@end
@implementation NXSControlAction
- (void)changed:(id)sender
{
  if(!control->changed)return;
  NXSControlState state=nxs_gnustep_control_state(control);
  control->changed(control->context,(control->kind==NXS_SLIDER||control->kind==NXS_POPUP)?NXS_VALUE_CHANGED:NXS_ACTIVATE,&state);
}
- (void)willPopUp:(NSNotification *)notification
{nxs_host_bind_input_window(control->host,[[(NSPopUpButton *)control->view menu] window]);}
@end

NXSControl *nxs_gnustep_control_create(int kind,NXSControlChanged changed,NXSPump pump,void *context)
{
  if(kind<NXS_BUTTON||kind>NXS_POPUP)return NULL;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  if(!nxs_host_initialize()){[pool drain];return NULL;}
  NXSControl *control=calloc(1,sizeof(*control));
  if(!control){[pool drain];return NULL;}
  NSView *view=nil;
  if(kind==NXS_POPUP) {
    view=[[NSPopUpButton alloc] initWithFrame:NSMakeRect(0,0,120,24) pullsDown:NO];
    [(NSPopUpButton *)view setAutoenablesItems:NO];
  } else if(kind==NXS_SLIDER) {
    NSSlider *slider=[[NSSlider alloc] initWithFrame:NSMakeRect(0,0,120,24)];
    [slider setContinuous:YES];view=slider;
  } else if(kind==NXS_PROGRESS) {
    NSProgressIndicator *progress=[[NSProgressIndicator alloc] initWithFrame:NSMakeRect(0,0,120,20)];
    [progress setStyle:NSProgressIndicatorBarStyle];[progress setIndeterminate:NO];
    [progress setDisplayedWhenStopped:YES];view=progress;
  } else {
    NSButton *button=[[NSButton alloc] initWithFrame:NSMakeRect(0,0,120,24)];
    [button setButtonType:kind==NXS_CHECKBOX?NSSwitchButton:kind==NXS_RADIO?NSRadioButton:NSMomentaryPushInButton];
    if(kind!=NXS_BUTTON)[button setBordered:NO];
    view=button;
  }
  control->host=nxs_host_create(view,pump,context);control->view=view;[view release];
  if(!control->host){free(control);[pool drain];return NULL;}
  control->kind=kind;control->enabled=1;control->changed=changed;control->context=context;
  if(kind!=NXS_PROGRESS) {
    NXSControlAction *target=[NXSControlAction new];target->control=control;control->target=target;
    [(NSControl *)view setTarget:target];[(NSControl *)view setAction:@selector(changed:)];
    if(kind==NXS_POPUP)[[NSNotificationCenter defaultCenter] addObserver:target
      selector:@selector(willPopUp:) name:NSPopUpButtonWillPopUpNotification object:view];
  }
  [pool drain];return control;
}
int nxs_gnustep_control_destroy(NXSControl *control)
{
  if(!control)return 1;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  if(control->kind==NXS_POPUP) {
    if(nxs_host_tracking(control->host)){[pool drain];return 0;}
    [(NSPopUpButtonCell *)[(NSPopUpButton *)control->view cell] dismissPopUp];
  }
  NSView *view=[control->view retain];
  if(!nxs_host_destroy(control->host)){[view release];[pool drain];return 0;}
  if(control->kind==NXS_POPUP)[[NSNotificationCenter defaultCenter] removeObserver:control->target];
  if(control->kind==NXS_PROGRESS)[(NSProgressIndicator *)view stopAnimation:nil];
  [view release];
  [control->target release];free(control);[pool drain];return 1;
}
int nxs_gnustep_control_sync(NXSControl *control,const NXSControlConfig *config)
{
  if(!control||!config||config->size<sizeof(*config)||!isfinite(config->width)||!isfinite(config->height)||
     config->width<1||config->height<1||config->width>32768||config->height>32768||
     !isfinite(config->minimum)||!isfinite(config->maximum)||!isfinite(config->value)||config->minimum>config->maximum||
     config->state<-1||config->state>1)return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSString *title=nil;
  if(control->kind==NXS_BUTTON||control->kind==NXS_CHECKBOX||control->kind==NXS_RADIO) {
    title=config->title?[NSString stringWithUTF8String:config->title]:@"";
    if(!title){[pool drain];return 0;}
  }
  nxs_host_resize(control->host,NSMakeSize(config->width,config->height));control->enabled=!!config->enabled;
  if(control->kind==NXS_PROGRESS) {
    NSProgressIndicator *view=(NSProgressIndicator *)control->view;
    [view setMinValue:config->minimum];[view setMaxValue:config->maximum];[view setDoubleValue:config->value];
    [view setIndeterminate:!!config->indeterminate];
    if(config->indeterminate&&control->enabled)[view startAnimation:nil];
    else [view stopAnimation:nil];
  } else {
    [(NSControl *)control->view setEnabled:control->enabled];
    if(control->kind==NXS_SLIDER) {
      NSSlider *view=(NSSlider *)control->view;
      [view setAllowsTickMarkValuesOnly:NO];
      [view setMinValue:config->minimum];[view setMaxValue:config->maximum];[view setDoubleValue:config->value];
      slider_model(control);
    } else if(control->kind==NXS_POPUP) {
      NSPopUpButton *view=(NSPopUpButton *)control->view;
      /* Selecting even the same item synchronizes the native highlighted item
       * into selection. Leave live menu input entirely with the native menu. */
      if(![[[view menu] window] isVisible]&&config->value!=[view indexOfSelectedItem]&&
         config->value>=-1&&config->value<[view numberOfItems]&&floor(config->value)==config->value)
        [view selectItemAtIndex:(NSInteger)config->value];
    } else {
      NSButton *view=(NSButton *)control->view;
      [view setTitle:title];[view setAllowsMixedState:control->kind==NXS_CHECKBOX&&config->state==-1];
      [view setState:config->state];
    }
  }
  [pool drain];return 1;
}
NXSControlState nxs_gnustep_control_state(NXSControl *control)
{
  NXSControlState state={.size=sizeof(state)};
  if(!control)return state;
  state.enabled=control->enabled;state.tracking=nxs_host_tracking(control->host);
  if(control->kind==NXS_PROGRESS)state.value=[(NSProgressIndicator *)control->view doubleValue];
  else {
    state.value=control->kind==NXS_POPUP?[(NSPopUpButton *)control->view indexOfSelectedItem]:[(NSControl *)control->view doubleValue];
    if(control->kind!=NXS_SLIDER&&control->kind!=NXS_POPUP)state.state=[(NSButton *)control->view state];
  }
  return state;
}
NXSSize nxs_gnustep_control_size(NXSControl *control)
{
  if(!control)return (NXSSize){0};
  NSSize size=control->kind==NXS_PROGRESS?[control->view frame].size:[[(NSControl *)control->view cell] cellSize];
  return (NXSSize){size.width,size.height};
}
NXSBitmap nxs_gnustep_control_draw(NXSControl *control,double scale)
{return control?nxs_host_draw(control->host,scale):(NXSBitmap){0};}
void nxs_gnustep_control_track(NXSControl *control,double x,double y,unsigned modifiers)
{if(control&&control->enabled&&control->kind!=NXS_PROGRESS)nxs_host_track(control->host,x,y,modifiers);}
void nxs_gnustep_control_send(NXSControl *control,int event,double x,double y,unsigned modifiers)
{if(control)nxs_host_send(control->host,event,x,y,modifiers);}
int nxs_gnustep_control_focus(NXSControl *control,int focused)
{return control&&(!focused||(control->enabled&&control->kind!=NXS_PROGRESS))?nxs_host_focus(control->host,focused):0;}
int nxs_gnustep_control_focused(NXSControl *control)
{return control?nxs_host_focused(control->host):0;}
int nxs_gnustep_control_key(NXSControl *control,const NXSKeyEvent *event)
{return control&&control->enabled&&control->kind!=NXS_PROGRESS?nxs_host_key(control->host,event):NXS_INPUT_UNHANDLED;}
int nxs_gnustep_control_needs_display(NXSControl *control)
{return control?nxs_host_needs_display(control->host):0;}
int nxs_gnustep_control_set_step(NXSControl *control,double step)
{
  if(!control||control->kind!=NXS_SLIDER||!isfinite(step)||step<0)return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  control->step=step;slider_model(control);[pool drain];return 1;
}
int nxs_gnustep_control_popup_items(NXSControl *control,const NXSPopupItem *items,uint32_t count,int selected)
{
  if(!control||control->kind!=NXS_POPUP||count>65536||(!items&&count)||selected<-1||
     (selected>=0&&(uint32_t)selected>=count)||nxs_host_tracking(control->host))return 0;
  NSPopUpButton *view=(NSPopUpButton *)control->view;
  if([[[view menu] window] isVisible])return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSMutableArray *titles=[NSMutableArray arrayWithCapacity:count];
  for(uint32_t i=0;i<count;i++) {
    if(items[i].size<sizeof(items[i])){[pool drain];return 0;}
    NSString *title=items[i].title?[NSString stringWithUTF8String:items[i].title]:@"";
    if(!title||(items[i].separator&&selected==(int)i)){
      [pool drain];return 0;
    }
    [titles addObject:title];
  }
  /* NSMenu preserves ordered duplicate labels. Its native popup ownership
   * already supplies selection and action dispatch for items with no custom
   * action; no private popup selector or selection implementation is needed. */
  NSMenu *menu=[[NSMenu alloc] initWithTitle:@""];[menu setAutoenablesItems:NO];
  for(uint32_t i=0;i<count;i++) {
    if(items[i].separator)[menu addItem:[NSMenuItem separatorItem]];
    else {
      id item=[menu addItemWithTitle:[titles objectAtIndex:i] action:NULL keyEquivalent:@""];
      [item setEnabled:!!items[i].enabled];
    }
  }
  nxs_host_unbind_input_windows(control->host);
  [view setMenu:menu];[menu release];
  [view selectItemAtIndex:selected];[view synchronizeTitleAndSelectedItem];
  [view setEnabled:control->enabled];
  [pool drain];return 1;
}
NXSPopupState nxs_gnustep_control_popup_state(NXSControl *control)
{
  NXSPopupState result={.size=sizeof(result),.highlighted=-1};
  if(!control||control->kind!=NXS_POPUP)return result;
  NSMenuView *view=[[(NSPopUpButton *)control->view menu] menuRepresentation];
  result.visible=[[view window] isVisible];
  if(result.visible){nxs_host_bind_input_window(control->host,[view window]);result.highlighted=[view highlightedItemIndex];result.frame=nxs_host_rect_from_view(control->host,view,[view bounds]);}
  return result;
}
NXSRect nxs_gnustep_control_popup_item_rect(NXSControl *control,int index)
{
  if(!control||control->kind!=NXS_POPUP||index<0||index>=[(NSPopUpButton *)control->view numberOfItems])return (NXSRect){0};
  NSMenuView *view=[[(NSPopUpButton *)control->view menu] menuRepresentation];
  return [[view window] isVisible]?nxs_host_rect_from_view(control->host,view,[view rectOfItemAtIndex:index]):(NXSRect){0};
}
int nxs_gnustep_control_set_screen_origin(NXSControl *control,double x,double y)
{
  if(!control)return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  int result=nxs_host_set_screen_origin(control->host,x,y);[pool drain];return result;
}
int nxs_gnustep_control_popup_open(NXSControl *control,int open)
{
  if(!control||control->kind!=NXS_POPUP||nxs_host_tracking(control->host)||(open&&!control->enabled))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSPopUpButton *view=(NSPopUpButton *)control->view;
  NSPopUpButtonCell *cell=(NSPopUpButtonCell *)[view cell];
  if(open) {
    if(![view numberOfItems]){[pool drain];return 0;}
    if(![[[view menu] window] isVisible])[cell attachPopUpWithFrame:[view bounds] inView:view];
  } else [cell dismissPopUp];
  [pool drain];return 1;
}
