/* Native click metadata, with no word/line selection implementation. GPL-2.0-or-later. */
#include "NativeUI.h"
#include <assert.h>
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
struct Probe {NXSControl *control;int pumps;};
static void release(void *context) {
  struct Probe *p=context;p->pumps++;
  assert(nxs_control_state(p->control).tracking);
  assert(!nxs_control_destroy(p->control));
  assert(!nxs_control_track_clicks(p->control,25,12,0,2));
  nxs_control_send(p->control,NXS_RELEASE,25,12,0);
}
int main(int argc,char **argv) {
  int previous=argc>1&&!strcmp(argv[1],"--expect-no-clicks");
  assert(nxs_control_input_capabilities()==(NXS_INPUT_FOCUS|NXS_INPUT_KEYBOARD));
  assert(nxs_control_pointer_capabilities()==(previous?0:NXS_POINTER_CLICK_COUNT));
  struct Probe p={0};p.control=nxs_control_create(NXS_TEXTFIELD,NULL,release,&p);assert(p.control);
  NXSControlConfig config={.size=sizeof(config),.width=180,.height=24,.enabled=1};
  assert(nxs_control_sync(p.control,&config)&&nxs_control_focus(p.control,1));
  assert(!nxs_control_track_clicks(NULL,25,12,0,1));
  assert(!nxs_control_track_clicks(p.control,NAN,12,0,1));
  assert(!nxs_control_track_clicks(p.control,25,INFINITY,0,1));
  assert(!nxs_control_track_clicks(p.control,25,12,0,0));
  assert(!nxs_control_track_clicks(p.control,25,12,0,UINT_MAX));
  unsigned starts[]={3,0,0},lengths[]={0,5,10};
  for(unsigned clicks=1;clicks<=(previous?1:3);clicks++) {
    NXSTextModel model={.size=sizeof(model),.text="Alpha beta",.editable=1};
    assert(nxs_control_text_sync(p.control,&model));p.pumps=0;
    assert(nxs_control_track_clicks(p.control,25,12,0,clicks));assert(p.pumps);
    NXSTextState state={.size=sizeof(state)};
    assert(nxs_control_text_get(p.control,NULL,0,&state));
    if(state.selection_start!=starts[clicks-1]||state.selection_length!=lengths[clicks-1])
      fprintf(stderr,"clicks=%u native range=%llu,%llu\n",clicks,(unsigned long long)state.selection_start,(unsigned long long)state.selection_length);
    assert(state.selection_start==starts[clicks-1]&&state.selection_length==lengths[clicks-1]);
    assert(!nxs_control_state(p.control).tracking);
  }
  if(previous)assert(!nxs_control_track_clicks(p.control,25,12,0,2));
  config.enabled=0;assert(nxs_control_sync(p.control,&config));
  if(!previous)assert(!nxs_control_track_clicks(p.control,25,12,0,2));
  assert(nxs_control_destroy(p.control));
  printf("{\"native_click_metadata\":%s,\"legacy_single_click\":true,\"focus_keyboard_capabilities_unchanged\":true,\"invalid_input_rejected\":true}\n",previous?"false":"true");
  return 0;
}
