/* Exercise native tracking/model behavior through the provider ABI.
 * The probe contains no control drawing or tracking implementation. GPL-2.0-or-later. */
#include "NativeUI.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
struct Probe {NXSControl *control;int actions,pumps,cancel;double x,y;const char *pressed;NXSControlState last;};
static void changed(void *context,int event,const NXSControlState *state)
{struct Probe *p=context;assert(event==NXS_ACTIVATE||event==NXS_VALUE_CHANGED);p->actions++;p->last=*state;}
static void bitmap(NXSControl *control,const char *path,double scale)
{
  NXSBitmap b=nxs_control_draw(control,scale);assert(b.pixels&&b.width>0&&b.height>0);
  FILE *f=fopen(path,"wb");assert(f);assert(fwrite(b.pixels,b.stride,b.height,f)==(size_t)b.height);fclose(f);
}
static void pump(void *context)
{
  struct Probe *p=context;
  assert(nxs_control_state(p->control).tracking);
  assert(!nxs_control_destroy(p->control)); /* Destruction must defer while NSCell owns its stack. */
  if(p->pumps++==0) {
    if(p->pressed)bitmap(p->control,p->pressed,1);
    nxs_control_send(p->control,NXS_MOVE,p->cancel?180:p->x,p->cancel?80:p->y,0);
  } else nxs_control_send(p->control,NXS_RELEASE,p->cancel?180:p->x,p->cancel?80:p->y,0);
}
int main(int argc,char **argv)
{
  assert(argc>1);const char *directory=argv[1];
  const NXSNativeUIAPI *api=nxs_native_ui_api();
  if(!api){fprintf(stderr,"%s\n",nxs_native_ui_error());return 1;}
  assert(api->version==NXS_NATIVE_UI_ABI&&api->size>=NXS_NATIVE_UI_CORE_SIZE);
  assert(!nxs_control_create(100,changed,pump,NULL));
  for(int kind=NXS_BUTTON;kind<=NXS_PROGRESS;kind++) {
    struct Probe p={0};p.control=nxs_control_create(kind,changed,pump,&p);assert(p.control);
    NXSControlConfig config={.size=sizeof(config),.width=128,.height=24,.minimum=0,.maximum=100,.value=50,.enabled=1,.state=0,.title="Native control"};
    assert(nxs_control_sync(p.control,&config));
    char path[1024],pressed[1024];snprintf(path,sizeof(path),"%s/kind-%d-normal.argb",directory,kind);bitmap(p.control,path,1);
    snprintf(path,sizeof(path),"%s/kind-%d-150.argb",directory,kind);bitmap(p.control,path,1.5);
    NXSSize size=nxs_control_size(p.control);assert(size.width>0&&size.height>0);
    if(kind==NXS_BUTTON&&getenv("NXS_NATIVE_UI_PROBE_HOLD")) {
      printf("{\"event\":\"host-live\"}\n");fflush(stdout);
      assert(getchar()=='\n');
    }
    int click_actions=0,cancel_actions=0;
    if(kind!=NXS_PROGRESS) {
      snprintf(pressed,sizeof(pressed),"%s/kind-%d-pressed.argb",directory,kind);p.pressed=pressed;
      p.x=kind==NXS_SLIDER?100:64;p.y=12;
      nxs_control_track(p.control,64,12,0);
      assert(!nxs_control_state(p.control).tracking);assert(p.pumps>0);assert(p.actions>0);
      if(kind==NXS_CHECKBOX||kind==NXS_RADIO)assert(p.last.state==1);
      if(kind==NXS_SLIDER)assert(p.last.value>50&&p.last.value<=100);
      click_actions=p.actions;
      if(kind!=NXS_SLIDER) {
        assert(nxs_control_sync(p.control,&config));p.pumps=0;p.actions=0;p.cancel=1;p.pressed=NULL;
        nxs_control_track(p.control,64,12,0);assert(p.pumps>0);assert(p.actions==0);cancel_actions=p.actions;
      }
    }
    if(kind==NXS_SLIDER) {
      config.width=24;config.height=128;config.value=50;assert(nxs_control_sync(p.control,&config));
      p.actions=0;p.pumps=0;p.x=12;p.y=20;p.pressed=NULL;
      nxs_control_track(p.control,12,64,0);
      assert(p.actions>0&&p.last.value>50&&p.last.value<=100);
      config.width=128;config.height=24;
    }
    config.enabled=0;assert(nxs_control_sync(p.control,&config));p.pumps=0;p.actions=0;p.pressed=NULL;
    nxs_control_track(p.control,64,12,0);assert(p.pumps==0&&p.actions==0);
    snprintf(path,sizeof(path),"%s/kind-%d-disabled.argb",directory,kind);bitmap(p.control,path,1);
    NXSControlState disabled=nxs_control_state(p.control);assert(!disabled.enabled);
    if(kind<=NXS_RADIO) {
      config.title="\xc0";config.width=256;config.enabled=1;
      assert(!nxs_control_sync(p.control,&config));
      assert(!nxs_control_state(p.control).enabled);
      assert(nxs_control_draw(p.control,1).width==128);
    }
    config.width=NAN;assert(!nxs_control_sync(p.control,&config));
    assert(!nxs_control_draw(p.control,0).pixels);
    assert(nxs_control_destroy(p.control));
    printf("{\"kind\":%d,\"preferred\":[%g,%g],\"native_actions\":%d,\"cancel_actions\":%d,\"disabled_actions\":0}\n",kind,size.width,size.height,click_actions,cancel_actions);
  }
  return 0;
}
