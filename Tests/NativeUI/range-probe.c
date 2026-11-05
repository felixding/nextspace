/* Native slider model configuration; no input or rendering rules are copied. */
#include "NativeUI.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
static unsigned actions;
static void changed(void *unused,int event,const NXSControlState *state)
{assert(event==NXS_VALUE_CHANGED);actions++;}
int main(int argc,char **argv)
{
  if(argc>1&&!strcmp(argv[1],"--expect-no-step")){
    assert(!nxs_control_range_capabilities());assert(!nxs_control_set_step(NULL,1));
    puts("{\"older_provider_without_step\":true}");return 0;
  }
  assert(nxs_control_range_capabilities()==NXS_RANGE_STEP);
  NXSControl *c=nxs_control_create(NXS_SLIDER,changed,NULL,NULL);assert(c);
  NXSControlConfig config={.size=sizeof(config),.width=240,.height=24,.minimum=0,.maximum=100,.value=40,.enabled=1};
  assert(nxs_control_sync(c,&config));assert(nxs_control_set_step(c,20));
  assert(nxs_control_focus(c,1));
  NXSKeyEvent key={.size=sizeof(key),.type=NXS_KEY_DOWN,.key=NXS_KEY_RIGHT};
  assert(nxs_control_key(c,&key)==NXS_INPUT_HANDLED);assert(nxs_control_state(c).value==60);
  key.key=NXS_KEY_HOME;assert(nxs_control_key(c,&key)==NXS_INPUT_HANDLED);assert(nxs_control_state(c).value==0);
  key.key=NXS_KEY_END;assert(nxs_control_key(c,&key)==NXS_INPUT_HANDLED);assert(nxs_control_state(c).value==100);
  config.maximum=200;config.value=60;assert(nxs_control_sync(c,&config));assert(nxs_control_state(c).value==60);
  assert(!nxs_control_set_step(c,NAN));assert(!nxs_control_set_step(c,-1));
  assert(nxs_control_set_step(c,1));
  config.maximum=100;config.value=50;assert(nxs_control_sync(c,&config));
  key.key=NXS_KEY_RIGHT;assert(nxs_control_key(c,&key)==NXS_INPUT_HANDLED);assert(nxs_control_state(c).value>50);
  assert(nxs_control_destroy(c));
  puts("{\"coarse_native_keys\":3,\"dense_native_keys\":1,\"range_update\":true,\"invalid_rejected\":true}");return 0;
}
