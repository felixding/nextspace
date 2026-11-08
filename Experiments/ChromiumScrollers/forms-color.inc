/* Original Blink chooser/model callbacks only. The shared provider owns the
 * NSColorWell and NSColorPanel. Exact guarded build; GPL-2.0-or-later. */
#include "pinned-colors.h"
#include "../../Libraries/NativeUI/Bridge/Specialized.inc"
#include "../../Libraries/NativeUI/Bridge/ColorBinding.inc"
static struct {void *controller,*node;struct NXSColorBinding binding;} color_session;
static void (*original_color_open)(void *);
static void (*original_color_end)(void *);
static int (*original_color_visible)(void *);
static void (*original_color_selected)(void *,const void *);
static void (*original_color_update)(void *);
static void *original_color_end_interface,*original_color_visible_interface,*original_color_selected_interface;
struct BlinkRGBA {float red,green,blue,alpha;};
/* Color is an opaque 20-byte C++ result in this build. Pass its return storage
 * in the original AArch64 x8 slot; conversion stays in Color::toSkColor4f(). */
__attribute__((naked)) static void call_color_current(void *function,void *self,void *output)
{__asm__("mov x16,x0\nmov x0,x1\nmov x8,x2\nbr x16");}
static int color_model(const void *color,NXSColorModel *model)
{
  struct BlinkRGBA rgba=((struct BlinkRGBA (*)(const void *))(base+NXS_COLOR_RGBA))(color);
  if(!isfinite(rgba.red)||!isfinite(rgba.green)||!isfinite(rgba.blue)||!isfinite(rgba.alpha)||
     rgba.red<0||rgba.red>1||rgba.green<0||rgba.green>1||rgba.blue<0||rgba.blue>1||rgba.alpha<0||rgba.alpha>1)return 0;
  *model=(NXSColorModel){.size=sizeof(*model),.red=rgba.red,.green=rgba.green,.blue=rgba.blue,.alpha=rgba.alpha};return 1;
}
static int color_node_model(void *node,NXSColorModel *model)
{
  if(input_form_kind(node)!=NXS_COLORWELL)return 0;
  void *type=decode_member((char *)node+272);if(!type)return 0;
  _Alignas(16) unsigned char color[32];
  call_color_current((void *)(base+NXS_COLOR_CURRENT),type,color);return color_model(color,model);
}
static struct NXSResponse *sync_color_image(struct NativeForm *form,struct NXSResponse *response)
{
  if(!response)return NULL;
  /* A panel selection is awaiting the original engine callback. A paint must
   * not overwrite it with the older DOM value before that callback runs. */
  if(color_session.node!=form->node||color_session.binding.control!=form->control) {
    NXSColorModel model;if(!color_node_model(form->node,&model)||!native_color_sync(form->control,&model))return NULL;
  }
  return form_request(form,5,0,0,0);
}
static int color_watch_needed(void){return color_session.binding.open;}
static void color_end(void *self)
{
  void *node=NULL;uint64_t control=0;
  if(color_session.controller==self) {
    node=color_session.node;control=color_session.binding.control;
    struct NXSColorBinding binding=color_session.binding;
    memset(&color_session,0,sizeof(color_session));native_color_binding_end(&binding);
  }
  /* Original DidEndChooser clears the owning member and emits the original
   * change notification. Clear our session before entering page callbacks. */
  original_color_end(self);
  struct NativeForm *form=node?find_form(node):NULL;
  if(form&&form->control==control)invalidate_form(form);
  refresh_form_watch();
}
static void color_forget(void *node)
{if(color_session.node==node)color_end(color_session.controller);}
static void color_open(void *self)
{
  if(color_session.controller)color_end(color_session.controller);
  void *node=((void *(*)(void *))(base+NXS_COLOR_OWNER))(self);
  struct NativeForm *form=node?bind_input_form(node):NULL;NXSColorModel model;
  if(!form||form->kind!=NXS_COLORWELL||!form_enabled(node)||!color_node_model(node,&model)){
    original_color_open(self);return;
  }
  form->enabled=1;
  if(!form_request(form,1,0,0,0)||!native_color_binding_open(&color_session.binding,form->control,&model)){
    original_color_open(self);return;
  }
  color_session.controller=self;color_session.node=node;form->input_owned=1;
  invalidate_form(form);
  if(!refresh_form_watch()){
    struct NXSColorBinding binding=color_session.binding;memset(&color_session,0,sizeof(color_session));
    native_color_binding_end(&binding);original_color_open(self);return;
  }
  note("native color chooser opened through original Blink lifecycle");
}
static int color_visible(void *self)
{return color_session.controller==self?color_session.binding.open:original_color_visible(self);}
static void color_selected(void *self,const void *color)
{
  if(color_session.controller!=self){original_color_selected(self,color);return;}
  NXSColorModel model;
  if(color_model(color,&model)&&native_color_sync(color_session.binding.control,&model)) {
    color_session.binding.color=model;
    struct NativeForm *form=find_form(color_session.node);if(form)invalidate_form(form);
  }
}
static void color_update(void *self)
{
  original_color_update(self);
  for(struct NativeForm *form=native_forms;form;form=form->next)
    if(form->kind==NXS_COLORWELL&&decode_member((char *)form->node+272)==self)invalidate_form(form);
}
/* The original ColorChooser interface is eight bytes into this controller.
 * These optimized virtual thunks contain their own bodies rather than branch
 * to the complete-object entry points; bind both original boundaries. */
static void color_end_interface(void *self){color_end((char *)self-8);}
static int color_visible_interface(void *self){return color_visible((char *)self-8);}
static void color_selected_interface(void *self,const void *color){color_selected((char *)self-8,color);}
static void color_native_work(int failed)
{
  void *controller=color_session.controller,*node=color_session.node;
  uint64_t control=color_session.binding.control;if(!controller)return;
  NXSColorModel model;int open=0;
  int changed=failed?-1:native_color_binding_poll(&color_session.binding,&model,&open);
  if(changed>0) {
    /* Transport only. The original CSS parser and DidChooseColor perform
     * canonicalization, validation, trusted input and page event dispatch. */
    char value[192];int count=snprintf(value,sizeof(value),"color(srgb %.9g %.9g %.9g / %.9g)",model.red,model.green,model.blue,model.alpha);
    if(count>0&&(size_t)count<sizeof(value)) {
      void *string=((void *(*)(const char *,size_t))(base+NXS_CHROMIUM_TEXT_FROM_UTF8_OFFSET))(value,count);
      ((void (*)(void *,const void *))(base+NXS_COLOR_SET_VALUE))(controller,&string);
      ((void (*)(void *))(base+NXS_CHROMIUM_TEXT_STRING_DESTROY_OFFSET))(&string);
    }
  }
  /* Original page listeners can remove/retype the input or open another
   * picker. Never use the old session after those engine callbacks. */
  if(color_session.controller!=controller||color_session.node!=node||color_session.binding.control!=control)return;
  if(changed<0||!open){color_end(controller);return;}
  struct NativeForm *form=find_form(node);if(form&&form->control==control)invalidate_form(form);
}
static struct Detour color_detours[]={
 {NXS_COLOR_OPEN,color_open_bytes,color_open,(void **)&original_color_open},
 {NXS_COLOR_END,color_end_bytes,color_end,(void **)&original_color_end},
 {NXS_COLOR_VISIBLE,color_visible_bytes,color_visible,(void **)&original_color_visible},
 {NXS_COLOR_SET_SELECTED,color_set_selected_bytes,color_selected,(void **)&original_color_selected},
 {NXS_COLOR_UPDATE,color_update_bytes,color_update,(void **)&original_color_update},
 {NXS_COLOR_END_INTERFACE,color_end_interface_bytes,color_end_interface,&original_color_end_interface},
 {NXS_COLOR_VISIBLE_INTERFACE,color_visible_interface_bytes,color_visible_interface,&original_color_visible_interface},
 {NXS_COLOR_SELECTED_INTERFACE,color_selected_interface_bytes,color_selected_interface,&original_color_selected_interface}
};
