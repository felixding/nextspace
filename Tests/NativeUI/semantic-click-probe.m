/* Native semantic activation compared with ordinary AppKit buttons.
 * No button state or interaction implementation is supplied. GPL-2.0-or-later. */
#import <AppKit/AppKit.h>
#include "NativeUI.h"
#include <assert.h>
#include <stdio.h>
@interface ReferenceAction : NSObject { @public unsigned actions; }
- (void)changed:(id)sender;
@end
@implementation ReferenceAction
- (void)changed:(id)sender {actions++;}
@end
struct Probe {NXSControl *control;unsigned actions;NXSControlState last;};
static void changed(void *context,int action,const NXSControlState *state)
{
  struct Probe *p=context;p->actions++;p->last=*state;
  assert(action==NXS_ACTIVATE&&state->tracking);
  assert(!nxs_control_destroy(p->control)&&!nxs_control_perform_click(p->control,0));
}
int main(void)
{
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  assert(nxs_control_activation_capabilities()==1&&nxs_native_ui_api()->size>=528);
  unsigned comparisons=0,actions=0;
  for(int kind=NXS_BUTTON;kind<=NXS_RADIO;kind++)for(int initial=-1;initial<=1;initial++) {
    struct Probe p={0};p.control=nxs_control_create(kind,changed,NULL,&p);assert(p.control);
    NXSControlConfig config={.size=sizeof(config),.width=128,.height=24,.enabled=1,.state=initial,.title="Native semantic action"};
    assert(nxs_control_sync(p.control,&config));
    NSButton *button=[[NSButton alloc] initWithFrame:NSMakeRect(0,0,128,24)];
    [button setButtonType:kind==NXS_CHECKBOX?NSSwitchButton:kind==NXS_RADIO?NSRadioButton:NSMomentaryPushInButton];
    [button setTitle:@"Native semantic action"];if(kind!=NXS_BUTTON)[button setBordered:NO];
    [button setAllowsMixedState:kind==NXS_CHECKBOX&&initial==-1];[button setState:initial];
    ReferenceAction *target=[ReferenceAction new];[button setTarget:target];[button setAction:@selector(changed:)];
    assert(!nxs_control_perform_click(p.control,1)&&!p.actions);
    for(unsigned i=1;i<=3;i++) {
      [button performClick:nil];assert(nxs_control_perform_click(p.control,0));
      NXSControlState state=nxs_control_state(p.control);
      assert(p.actions==target->actions&&p.actions==i&&state.state==[button state]&&state.value==[button doubleValue]);
      assert(p.last.state==state.state&&p.last.value==state.value&&!nxs_control_focused(p.control));
      printf("{\"kind\":%d,\"initial\":%d,\"click\":%u,\"native_state\":%ld,\"native_value\":%g}\n",kind,initial,i,(long)[button state],[button doubleValue]);comparisons++;
    }
    config.enabled=0;assert(nxs_control_sync(p.control,&config));[button setEnabled:NO];
    [button performClick:nil];assert(!nxs_control_perform_click(p.control,0)&&p.actions==target->actions&&p.actions==3);
    actions+=p.actions;assert(nxs_control_destroy(p.control));[button release];[target release];
  }
  NXSControl *slider=nxs_control_create(NXS_SLIDER,NULL,NULL,NULL);assert(slider);
  assert(!nxs_control_perform_click(slider,0)&&nxs_control_destroy(slider));
  assert(!nxs_control_perform_click(NULL,0));
  printf("{\"native_button_comparisons\":%u,\"native_actions\":%u,\"disabled_rejected\":true,\"focus_unchanged\":true,\"reentry_and_destruction_guarded\":true}\n",comparisons,actions);
  [pool drain];return 0;
}
