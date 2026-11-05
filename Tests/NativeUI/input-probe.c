/* Exercise native responders through the independent provider ABI. GPL-2.0-or-later. */
#include "NativeUI.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
struct Probe {NXSControl *control;int actions;NXSControlState last;};
static void changed(void *context,int event,const NXSControlState *state)
{
  struct Probe *p=context;p->actions++;p->last=*state;
  assert(event==NXS_ACTIVATE||event==NXS_VALUE_CHANGED);
  assert(state->tracking); /* Native input still owns the control's stack. */
  assert(!nxs_control_destroy(p->control));
}
static int key(struct Probe *p,int type,int logical,const char *text,unsigned modifiers)
{
  NXSKeyEvent event={.size=sizeof(event),.type=type,.key=logical,.text=text,.unmodified_text=text,.modifiers=modifiers};
  return nxs_control_key(p->control,&event);
}
static NXSControlConfig config(void)
{return (NXSControlConfig){.size=sizeof(NXSControlConfig),.width=128,.height=24,.minimum=0,.maximum=100,.value=50,.enabled=1,.title="Native input"};}
static void bitmap(const char *directory,int kind,const char *state,NXSBitmap b)
{
  if(!directory)return;
  char path[1024];snprintf(path,sizeof(path),"%s/input-kind-%d-%s.argb",directory,kind,state);
  FILE *file=fopen(path,"wb");assert(file);
  assert(fwrite(b.pixels,b.stride,b.height,file)==(size_t)b.height);fclose(file);
}
int main(int argc,char **argv)
{
  const NXSNativeUIAPI *api=nxs_native_ui_api();assert(api&&api->size>=NXS_NATIVE_UI_CORE_SIZE);
  if(argc>1&&!strcmp(argv[1],"--expect-no-input")) {
    assert(nxs_control_input_capabilities()==0);
    assert(!nxs_control_focus(NULL,1)&&!nxs_control_focused(NULL));
    assert(nxs_control_key(NULL,NULL)==NXS_INPUT_UNHANDLED);
    puts("{\"previous_provider_input_extension_absent\":true}");return 0;
  }
  assert(nxs_control_input_capabilities()==(NXS_INPUT_FOCUS|NXS_INPUT_KEYBOARD));
  const char *directory=argc>1&&argv[1][0]!='-'?argv[1]:NULL;
  int total=0;
  for(int kind=NXS_BUTTON;kind<=NXS_SLIDER;kind++) {
    struct Probe p={0};p.control=nxs_control_create(kind,changed,NULL,&p);assert(p.control);
    NXSControlConfig c=config();assert(nxs_control_sync(p.control,&c));
    assert(!nxs_control_focused(p.control));
    assert(key(&p,NXS_KEY_DOWN,NXS_KEY_TEXT," ",0)==NXS_INPUT_UNHANDLED);
    assert(!p.actions);
    NXSBitmap normal=nxs_control_draw(p.control,1);assert(normal.pixels);
    size_t bytes=(size_t)normal.stride*normal.height;
    unsigned char *pixels=malloc(bytes);assert(pixels);memcpy(pixels,normal.pixels,bytes);
    bitmap(directory,kind,"normal",normal);
    assert(nxs_control_focus(p.control,1)&&nxs_control_focused(p.control));
    NXSBitmap focused=nxs_control_draw(p.control,1);assert(focused.pixels);
    if(kind!=NXS_SLIDER)assert(memcmp(pixels,focused.pixels,bytes));
    bitmap(directory,kind,"focused",focused);free(pixels);
    if(kind!=NXS_SLIDER) {
      assert(key(&p,NXS_KEY_DOWN,NXS_KEY_TEXT," ",0)==NXS_INPUT_HANDLED);
      assert(p.actions==1);
      if(kind==NXS_CHECKBOX||kind==NXS_RADIO)assert(p.last.state==1);
      assert(key(&p,NXS_KEY_UP,NXS_KEY_TEXT," ",0)==NXS_INPUT_UNHANDLED&&p.actions==1);
    } else {
      assert(key(&p,NXS_KEY_DOWN,NXS_KEY_RIGHT,NULL,0)==NXS_INPUT_HANDLED);
      assert(p.actions==1&&p.last.value>50&&p.last.value<=100);
      assert(key(&p,NXS_KEY_DOWN,NXS_KEY_HOME,NULL,0)==NXS_INPUT_HANDLED&&p.last.value==0);
      assert(key(&p,NXS_KEY_DOWN,NXS_KEY_END,NULL,0)==NXS_INPUT_HANDLED&&p.last.value==100);
    }
    int before=p.actions;
    assert(key(&p,NXS_KEY_DOWN,NXS_KEY_TEXT,"x",0)==NXS_INPUT_UNHANDLED);
    assert(key(&p,NXS_KEY_DOWN,999,NULL,0)==NXS_INPUT_UNHANDLED);
    assert(key(&p,NXS_KEY_DOWN,NXS_KEY_TEXT,"\xc0",0)==NXS_INPUT_UNHANDLED);
    assert(key(&p,NXS_KEY_DOWN,NXS_KEY_TAB,NULL,0)==NXS_INPUT_NEXT);
    assert(key(&p,NXS_KEY_DOWN,NXS_KEY_TAB,NULL,NXS_SHIFT)==NXS_INPUT_PREVIOUS);
    assert(p.actions==before);
    c.enabled=0;assert(nxs_control_sync(p.control,&c));
    assert(key(&p,NXS_KEY_DOWN,NXS_KEY_TEXT," ",0)==NXS_INPUT_UNHANDLED);
    assert(!nxs_control_focus(p.control,1)&&p.actions==before);
    assert(nxs_control_focus(p.control,0)&&!nxs_control_focused(p.control));
    assert(nxs_control_destroy(p.control));total+=before;
  }
  struct Probe first={0},second={0};
  first.control=nxs_control_create(NXS_BUTTON,changed,NULL,&first);
  second.control=nxs_control_create(NXS_BUTTON,changed,NULL,&second);
  assert(first.control&&second.control);NXSControlConfig c=config();
  assert(nxs_control_sync(first.control,&c)&&nxs_control_sync(second.control,&c));
  assert(nxs_control_focus(first.control,1)&&nxs_control_focused(first.control));
  assert(nxs_control_focus(second.control,1)&&!nxs_control_focused(first.control)&&nxs_control_focused(second.control));
  if(getenv("NXS_NATIVE_UI_INPUT_HOLD")) {
    puts("{\"event\":\"host-live\"}");fflush(stdout);assert(getchar()=='\n');
  }
  assert(nxs_control_destroy(second.control));
  assert(nxs_control_focus(first.control,1));assert(nxs_control_destroy(first.control));
  printf("{\"native_keyboard_actions\":%d,\"controls\":4,\"focus_transfer\":true,\"navigation_requests\":8,\"disabled_actions\":0,\"deferred_destruction\":true}\n",total);
  return 0;
}
