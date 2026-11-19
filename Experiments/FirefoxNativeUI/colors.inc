/* Original Gecko color model/callback ownership. All picker UI remains in the
 * shared GNUstep provider. Exact guarded libxul build; GPL-2.0-or-later. */
#include "pinned-colors.h"
#include "../../Libraries/NativeUI/Bridge/ColorBinding.inc"
#include "../../Libraries/NativeUI/Bridge/ColorOwners.inc"
#include "color-callback.inc"
static struct {void *picker;struct NXSColorBinding binding;} color_session;
static __thread void *color_display_owner;
static uint32_t (*original_color_open)(void *);
static void (*original_color_update)(void *);
static uint32_t (*original_color_input_open)(void *);
static uint32_t (*original_color_proxy_open)(void *,void *);
static __thread void *color_input_node;
static void color_callback_completed(uint64_t control,uint32_t token)
{
  int accepted=native_color_owner(control,token,67,0);
  if(log_fd>=0)dprintf(log_fd,"%d original Gecko color model completed control=%llu acknowledged=%d\n",
    getpid(),(unsigned long long)control,accepted);
}
static int color_string_model(const void *string,NXSColorModel *model)
{
  /* Original ParseSimpleColor returns Maybe<nscolor>: the present byte is
   * at bit 32 in this guarded ABI. Unpack the application RGBA integer only;
   * parsing and validation remain in the original browser implementation. */
  uint64_t parsed=((uint64_t (*)(const void *))(base+NXS_GECKO_COLOR_PARSE))(string);
  if(!(parsed&0xff00000000ull))return 0;
  *model=(NXSColorModel){.size=sizeof(*model),.red=(parsed&255)/255.,
    .green=((parsed>>8)&255)/255.,.blue=((parsed>>16)&255)/255.,.alpha=((parsed>>24)&255)/255.};return 1;
}
static int color_node_model(void *node,NXSColorModel *model)
{
  static const uint16_t empty;struct GeckoString value={.data=&empty,.flags=1};
  ((void (*)(void *,void *,unsigned))(base+NXS_GECKO_TEXT_VALUE_OFFSET))(node,&value,0);
  int okay=color_string_model(&value,model);
  ((void (*)(void *))(base+0x3826f2c))(&value);return okay;
}
static int native_color_frame(const void *frame)
{
  if(!colors_enabled||!frame||frame_kind(frame)!=NXS_COLORWELL)return 0;
  void *node=*(void **)((const char *)frame+24);
  if(*(void **)((char *)node+96)!=frame)return 0;
  const void *style=*(void *const *)((const char *)frame+32),*display=*(void *const *)((const char *)style+80);
  return *((const unsigned char *)display+6)&&
    ((int (*)(const void *,const void *,void *))(base+NXS_GECKO_TEXT_IS_THEMED_OFFSET))(frame,display,NULL);
}
static struct NXSResponse *sync_color_widget(struct Widget *w,struct NXSResponse *response)
{
  NXSColorModel model;
  if(!response||!color_node_model(w->node,&model)||!native_color_sync(w->id,&model))return NULL;
  return widget_request(w,5,0,0,0);
}
static int prepare_color_image(void *frame)
{
  if(!native_color_frame(frame)||!frame_scale_supported(frame))return 0;
  struct Widget *w=bind_widget(frame);if(!w)return 0;
  int rectangle[4]={0};engine_frame_rect((void *)(base+0x6daae5c),frame,rectangle);
  w->width=rectangle[2]/frame_units(frame);w->height=rectangle[3]/frame_units(frame);
  struct NXSResponse *response=widget_sync(w);w->painted=!!response;
  return response&&button_cache_update(w,response);
}
static int color_display(void *frame,void *builder,const void *lists)
{
  if(color_display_owner&&frame!=color_display_owner)return 1;
  if(!prepare_color_image(frame))return 0;
  void *previous=color_display_owner;color_display_owner=frame;
  original_block_display(frame,builder,lists);color_display_owner=previous;return 1;
}
static void color_update(void *frame)
{
  original_color_update(frame);
  struct Widget *w=widget_for_frame(frame);if(w&&w->kind==NXS_COLORWELL)invalidate_widget(w);
}
static int color_watch_needed(void){return color_session.binding.open;}
static void color_end(void)
{
  void *picker=color_session.picker;if(!picker)return;
  struct NXSColorBinding binding=color_session.binding;memset(&color_session,0,sizeof(color_session));
  native_color_binding_return(&binding);
  /* Detach the original callback before invoking it, preserving XPCOM's
   * original ownership and reentrancy contract. No GTK dialog is constructed.
   * Offsets/virtual slots are guarded against original Open/Update/Done code. */
  void *callback=*(void **)((char *)picker+48);*(void **)((char *)picker+48)=NULL;
  if(callback) {
    ((uint32_t (*)(void *,const void *))(*(uintptr_t **)callback)[4])(callback,(char *)picker+72);
    ((unsigned (*)(void *))(*(uintptr_t **)callback)[2])(callback);
  }
  ((unsigned (*)(void *))(base+NXS_GECKO_COLOR_RELEASE))(picker);
  note("native Firefox color panel completed through original callback owner");
  release_idle_widget_notifier();
}
static void color_native_work(int failed)
{
  void *picker=color_session.picker;uint64_t control=color_session.binding.control;if(!picker)return;
  NXSColorModel model;int open=0;
  int changed=failed?-1:native_color_binding_poll(&color_session.binding,&model,&open);
  if(changed>=0) {
    struct {double red,green,blue,alpha;} rgba={model.red,model.green,model.blue,model.alpha};
    if(!changed)((void (*)(void *,const void *))(base+NXS_GECKO_COLOR_SET_COLOR))(picker,&rgba);
    else
    /* Original OnColorChanged ignores its GTK chooser argument and calls
     * original SetColor plus callback Update, including the IPC proxy. */
    ((void (*)(void *,void *,void *))(base+NXS_GECKO_COLOR_CHANGED))(NULL,&rgba,picker);
  }
  if(color_session.picker==picker&&color_session.binding.control==control&&(changed<0||!open))color_end();
}
static uint32_t color_open(void *picker)
{
  if(color_session.picker)color_end();
  void *callback=*(void **)((char *)picker+48);
  if(!callback||*(uintptr_t *)callback!=base+0xa0a6488||!ensure_widget_lifetime()||!ensure_text_watch())return original_color_open(picker);
  void *actor=*(void **)((char *)callback+16);
  uint32_t token=actor?*(uint32_t *)((char *)actor+8):0;
  if(!token){release_idle_widget_notifier();return original_color_open(picker);}
  uint64_t control=++next_widget;
  if(!native_color_binding_borrow(&color_session.binding,control,token)) {
    release_idle_widget_notifier();return original_color_open(picker);
  }
  ((unsigned (*)(void *))(base+NXS_GECKO_COLOR_ADDREF))(picker);
  color_session.picker=picker;
  /* Initialize the original canonical output string without firing Update. */
  NXSColorModel model=color_session.binding.color;
  struct {double red,green,blue,alpha;} rgba={model.red,model.green,model.blue,model.alpha};
  ((void (*)(void *,const void *))(base+NXS_GECKO_COLOR_SET_COLOR))(picker,&rgba);
  note("native Firefox color panel opened through original callback owner");return 0;
}
static uint32_t color_input_open(void *node)
{
  void *previous=color_input_node;
  if(node_kind(node)==NXS_COLORWELL) {
    void *frame=*(void **)((char *)node+96);
    if(native_color_frame(frame)&&frame_scale_supported(frame)) {
      /* Original InitColorPicker checks and consumes user activation first.
       * Do not wait for native drawing before that security boundary. */
      color_input_node=node;
    }
  }
  uint32_t result=original_color_input_open(node);
  if(result==0x80004005u&&color_input_node==node) {
    struct Widget *w=widget_for_node(node);
    if(w&&native_color_frame(w->frame)&&!(widget_content_state(w)&16)&&native_color_panel_reveal(w->id)) {
      /* InitColorPicker rejects a second session. Reveal its still-running
       * native panel through the shared owner without starting another one. */
      result=0;note("existing native Firefox color panel revealed");
    }
  }
  if(log_fd>=0)dprintf(log_fd,"%d original Gecko color input request status=%08x\n",getpid(),result);
  color_input_node=previous;return result;
}
static uint32_t color_proxy_open(void *proxy,void *callback)
{
  /* This original proxy boundary follows the activation check. Refresh the
   * existing native model here, including script changes before opening or
   * an owner not yet painted. Missing pixels are not an ownership failure. */
  if(color_input_node)prepare_color_image(*(void **)((char *)color_input_node+96));
  struct Widget *field=color_input_node?widget_for_node(color_input_node):NULL;
  uint64_t control=field?field->id:0;
  uint32_t token=control?*(uint32_t *)((char *)proxy+16):0;
  int eligible=token&&!*(void **)((char *)proxy+72);
  struct NXSGeckoColorCallback *owner=eligible?color_callback_create(callback,control,token):NULL;
  int offered=eligible&&native_color_owner(control,token,60,owner?2:1);
  if(!offered&&owner)offered=native_color_owner(control,token,60,1);
  uint32_t result=original_color_proxy_open(proxy,offered&&owner?(void *)owner:callback);
  if(owner)color_callback_release(owner);
  if(offered&&(result&0x80000000u))native_color_owner(control,token,60,0);
  return result;
}
static struct Detour color_detours[]={
 {NXS_GECKO_COLOR_OPEN_NATIVE,gecko_color_open_native_bytes,color_open,(void **)&original_color_open},
 {NXS_GECKO_COLOR_FRAME_UPDATE,gecko_color_frame_update_bytes,color_update,(void **)&original_color_update},
 {NXS_GECKO_COLOR_INPUT_OPEN,gecko_color_input_open_bytes,color_input_open,(void **)&original_color_input_open},
 {NXS_GECKO_COLOR_PROXY_OPEN,gecko_color_proxy_open_bytes,color_proxy_open,(void **)&original_color_proxy_open}
};
