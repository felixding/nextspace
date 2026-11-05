/* Provider loading and ABI forwarding only; no UI implementation. GPL-2.0-or-later. */
#include "NativeUI.h"
#include <dlfcn.h>
#include <pthread.h>
#include <math.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>

static pthread_once_t once=PTHREAD_ONCE_INIT;
static const NXSNativeUIAPI *api;
static char error[512];
static void load_provider(void)
{
  const char *path=getenv("NEXTSPACE_NATIVE_UI_PROVIDER");
  if(!path||!*path)path="libnextspace-native-ui-gnustep.so.1";
  void *library=dlopen(path,RTLD_NOW|RTLD_LOCAL);
  if(!library){snprintf(error,sizeof(error),"%s",dlerror());return;}
  const NXSNativeUIAPI *(*provider)(uint32_t)=dlsym(library,"nxs_native_ui_provider");
  if(!provider){snprintf(error,sizeof(error),"Native UI provider has no ABI entry point");return;}
  const NXSNativeUIAPI *candidate=provider(NXS_NATIVE_UI_ABI);
  if(!candidate||candidate->version!=NXS_NATIVE_UI_ABI||candidate->size<NXS_NATIVE_UI_CORE_SIZE) {
    snprintf(error,sizeof(error),"Unsupported native UI provider ABI");return;
  }
  if(!candidate->scroller_create||!candidate->scroller_destroy||!candidate->scroller_width||
     !candidate->scroller_sync||!candidate->scroller_draw||!candidate->scroller_part||
     !candidate->scroller_track||!candidate->scroller_send||!candidate->scroller_tracking||
     !candidate->scroller_hit_part||!candidate->control_create||!candidate->control_destroy||
     !candidate->control_sync||!candidate->control_state||!candidate->control_size||
     !candidate->control_draw||!candidate->control_track||!candidate->control_send) {
    snprintf(error,sizeof(error),"Incomplete native UI provider ABI");return;
  }
  /* Objective-C classes and active controls can outlive a caller. Keep this
   * provider loaded for the process lifetime rather than unloading its code. */
  api=candidate;
}
const NXSNativeUIAPI *nxs_native_ui_api(void){pthread_once(&once,load_provider);return api;}
const char *nxs_native_ui_error(void){nxs_native_ui_api();return error;}
NXSControl *nxs_control_create(int kind,NXSControlChanged changed,NXSPump pump,void *context)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return p?p->control_create(kind,changed,pump,context):NULL;}
int nxs_control_destroy(NXSControl *c)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return p?p->control_destroy(c):0;}
int nxs_control_sync(NXSControl *c,const NXSControlConfig *config)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return p?p->control_sync(c,config):0;}
NXSControlState nxs_control_state(NXSControl *c)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return p?p->control_state(c):(NXSControlState){0};}
NXSSize nxs_control_size(NXSControl *c)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return p?p->control_size(c):(NXSSize){0};}
NXSBitmap nxs_control_draw(NXSControl *c,double scale)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return p?p->control_draw(c,scale):(NXSBitmap){0};}
void nxs_control_track(NXSControl *c,double x,double y,unsigned m)
{const NXSNativeUIAPI *p=nxs_native_ui_api();if(p)p->control_track(c,x,y,m);}
void nxs_control_send(NXSControl *c,int event,double x,double y,unsigned m)
{const NXSNativeUIAPI *p=nxs_native_ui_api();if(p)p->control_send(c,event,x,y,m);}
#define HAS_INPUT(p, field) ((p) && (p)->size >= offsetof(NXSNativeUIAPI, field)+sizeof((p)->field) && (p)->field)
unsigned nxs_control_pointer_capabilities(void)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,control_track_clicks)?NXS_POINTER_CLICK_COUNT:0;}
int nxs_control_track_clicks(NXSControl *c,double x,double y,unsigned m,unsigned clicks)
{
  if(!c||!clicks||clicks>INT_MAX||!isfinite(x)||!isfinite(y))return 0;
  const NXSNativeUIAPI *p=nxs_native_ui_api();
  if(HAS_INPUT(p,control_track_clicks))return p->control_track_clicks(c,x,y,m,clicks);
  if(p&&c&&clicks==1){p->control_track(c,x,y,m);return 1;}
  return 0;
}
unsigned nxs_control_input_capabilities(void)
{
  const NXSNativeUIAPI *p=nxs_native_ui_api();
  return (HAS_INPUT(p,control_focus)&&HAS_INPUT(p,control_focused)?NXS_INPUT_FOCUS:0) |
    (HAS_INPUT(p,control_key)?NXS_INPUT_KEYBOARD:0);
}
int nxs_control_focus(NXSControl *c,int focused)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,control_focus)?p->control_focus(c,focused):0;}
int nxs_control_focused(NXSControl *c)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,control_focused)?p->control_focused(c):0;}
int nxs_control_key(NXSControl *c,const NXSKeyEvent *event)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,control_key)?p->control_key(c,event):NXS_INPUT_UNHANDLED;}
unsigned nxs_native_ui_event_capabilities(void)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,dispatch_events)&&HAS_INPUT(p,control_needs_display)?NXS_EVENTS:0;}
double nxs_native_ui_dispatch_events(double maximum_wait)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,dispatch_events)?p->dispatch_events(maximum_wait):-1;}
int nxs_control_needs_display(NXSControl *c)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,control_needs_display)?p->control_needs_display(c):0;}
unsigned nxs_control_range_capabilities(void)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,control_set_step)?NXS_RANGE_STEP:0;}
int nxs_control_set_step(NXSControl *c,double step)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,control_set_step)?p->control_set_step(c,step):0;}
unsigned nxs_control_popup_capabilities(void)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,control_popup_items)&&HAS_INPUT(p,control_popup_state)&&HAS_INPUT(p,control_popup_item_rect)&&HAS_INPUT(p,control_set_screen_origin)?NXS_POPUP_ITEMS:0;}
int nxs_control_popup_items(NXSControl *c,const NXSPopupItem *items,uint32_t count,int selected)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,control_popup_items)?p->control_popup_items(c,items,count,selected):0;}
NXSPopupState nxs_control_popup_state(NXSControl *c)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,control_popup_state)?p->control_popup_state(c):(NXSPopupState){.size=sizeof(NXSPopupState),.highlighted=-1};}
NXSRect nxs_control_popup_item_rect(NXSControl *c,int index)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,control_popup_item_rect)?p->control_popup_item_rect(c,index):(NXSRect){0};}
int nxs_control_set_screen_origin(NXSControl *c,double x,double y)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,control_set_screen_origin)?p->control_set_screen_origin(c,x,y):0;}
unsigned nxs_native_ui_source_capabilities(void)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,event_source_create)&&HAS_INPUT(p,event_source_destroy)?1:0;}
NXSEventSource *nxs_native_ui_source_create(int descriptor)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,event_source_create)?p->event_source_create(descriptor):NULL;}
int nxs_native_ui_source_destroy(NXSEventSource *source)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,event_source_destroy)?p->event_source_destroy(source):0;}
unsigned nxs_control_popup_open_capabilities(void)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,control_popup_open)?1:0;}
int nxs_control_popup_open(NXSControl *c,int open)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,control_popup_open)?p->control_popup_open(c,open):0;}
unsigned nxs_control_text_capabilities(void)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,control_text_sync)&&HAS_INPUT(p,control_text_get)?
  NXS_TEXT_EDITING|(HAS_INPUT(p,control_text_filter)?NXS_TEXT_FILTER:0)|
  (HAS_INPUT(p,control_text_command)?NXS_TEXT_COMMAND:0):0;}
int nxs_control_text_sync(NXSControl *c,const NXSTextModel *model)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,control_text_sync)?p->control_text_sync(c,model):0;}
size_t nxs_control_text_get(NXSControl *c,char *buffer,size_t capacity,NXSTextState *state)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,control_text_get)?p->control_text_get(c,buffer,capacity,state):0;}
int nxs_control_text_filter(NXSControl *c,NXSTextShouldChange filter,void *context)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,control_text_filter)?p->control_text_filter(c,filter,context):0;}
const char *nxs_control_text_command(NXSControl *c)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,control_text_command)?p->control_text_command(c):NULL;}
unsigned nxs_control_command_capabilities(void)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,control_command_filter)?1:0;}
int nxs_control_command_filter(NXSControl *c,NXSCommandFilter filter,void *context)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,control_command_filter)?p->control_command_filter(c,filter,context):0;}
unsigned nxs_native_ui_menu_capabilities(void)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,menu_create)&&HAS_INPUT(p,menu_destroy)&&HAS_INPUT(p,menu_items)&&HAS_INPUT(p,menu_show)&&HAS_INPUT(p,menu_key)&&HAS_INPUT(p,menu_state)?1:0;}
NXSMenu *nxs_menu_create(const char *title,NXSMenuCommand command,NXSPump pump,void *context)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return nxs_native_ui_menu_capabilities()?p->menu_create(title,command,pump,context):NULL;}
int nxs_menu_destroy(NXSMenu *menu)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,menu_destroy)?p->menu_destroy(menu):0;}
int nxs_menu_items(NXSMenu *menu,const NXSMenuItem *items,uint32_t count)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,menu_items)?p->menu_items(menu,items,count):0;}
int nxs_menu_show(NXSMenu *menu,int visible)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,menu_show)?p->menu_show(menu,visible):0;}
int nxs_menu_key(NXSMenu *menu,const NXSKeyEvent *event)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,menu_key)?p->menu_key(menu,event):0;}
NXSMenuState nxs_menu_state(NXSMenu *menu,int index)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return HAS_INPUT(p,menu_state)?p->menu_state(menu,index):(NXSMenuState){.size=sizeof(NXSMenuState),.highlighted=-1};}
