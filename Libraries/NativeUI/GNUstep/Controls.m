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
};
@interface NXSControlAction : NSObject { @public NXSControl *control; }
- (void)changed:(id)sender;
@end
@implementation NXSControlAction
- (void)changed:(id)sender
{
  if(!control->changed)return;
  NXSControlState state=nxs_gnustep_control_state(control);
  control->changed(control->context,control->kind==NXS_SLIDER?NXS_VALUE_CHANGED:NXS_ACTIVATE,&state);
}
@end

NXSControl *nxs_gnustep_control_create(int kind,NXSControlChanged changed,NXSPump pump,void *context)
{
  if(kind<NXS_BUTTON||kind>NXS_PROGRESS)return NULL;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  if(!nxs_host_initialize()){[pool drain];return NULL;}
  NXSControl *control=calloc(1,sizeof(*control));
  if(!control){[pool drain];return NULL;}
  NSView *view=nil;
  if(kind==NXS_SLIDER) {
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
  }
  [pool drain];return control;
}
int nxs_gnustep_control_destroy(NXSControl *control)
{
  if(!control)return 1;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  if(!nxs_host_destroy(control->host)){[pool drain];return 0;}
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
  } else {
    [(NSControl *)control->view setEnabled:control->enabled];
    if(control->kind==NXS_SLIDER) {
      NSSlider *view=(NSSlider *)control->view;
      [view setMinValue:config->minimum];[view setMaxValue:config->maximum];[view setDoubleValue:config->value];
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
    state.value=[(NSControl *)control->view doubleValue];
    if(control->kind!=NXS_SLIDER)state.state=[(NSButton *)control->view state];
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
