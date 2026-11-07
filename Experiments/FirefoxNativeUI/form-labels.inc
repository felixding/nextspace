/* Gecko owns label association, filtering and trusted click creation. The shared
 * provider supplies native semantic activation. GPL-2.0-or-later. */
#include "pinned-form-labels.h"
static __thread void *form_label_event;
static uint32_t (*original_form_label_default)(void *,void *);
static uint32_t (*original_form_label_forward)(void *,void *,void *,int,const void *,int *);
static uint32_t form_label_default(void *label,void *visitor)
{
  void *previous=form_label_event;form_label_event=*(void **)((char *)visitor+8);
  uint32_t result=original_form_label_default(label,visitor);form_label_event=previous;return result;
}
static uint32_t form_label_forward(void *context,void *event,void *node,int full,const void *flags,int *status)
{
  struct Widget *w=event&&event==form_label_event&&(*(const uint8_t *)((const char *)event+48)&1)?widget_for_node(node):NULL;
  if(!w||!w->painted||node_kind(node)!=w->kind)
    return original_form_label_forward(context,event,node,full,flags,status);
  uint64_t id=w->id;
  if(w->kind==NXS_CHECKBOX||w->kind==NXS_BUTTON) {
    int kind=w->kind;struct NXSResponse *response=widget_sync(w);double before=response?response->parts[0].width:0;
    struct NXSControlAction action={0};
    if(response)native_control_action_snapshot(native_control_perform_click(kind,id,0),before,&action);
    w=widget_for_node(node);uint32_t result=0;
    if(w&&w->id==id&&w->kind==kind&&native_control_action_valid(&action)) {
      struct NXSCheckboxActivation previous=native_checkbox_activation;
      if(kind==NXS_CHECKBOX)native_checkbox_enter((uintptr_t)node,id,action);
      result=original_form_label_forward(context,event,node,full,flags,status);native_checkbox_activation=previous;
    }
    w=widget_for_node(node);if(w&&w->id==id){widget_sync(w);invalidate_widget(w);}
    return result;
  }
  if(w->kind!=NXS_RADIO||!radio_groups_enabled)return original_form_label_forward(context,event,node,full,flags,status);
  struct GeckoRadioGroup *g=gecko_radio_sync(w);void *target=NULL;
  w=widget_for_node(node);
  if(g&&w&&w->id==id) {
    g->busy++;
    if(native_radio_binding_activate(&g->native,w->radio_member))
      target=gecko_radio_action_target(g,node,id,g->native.state.selected);
    g->busy--;
  }
  uint32_t result=target?original_form_label_forward(context,event,target,full,flags,status):0;
  gecko_radio_pointer_complete(node,id);return result;
}
static struct Detour form_label_detours[]={
  {NXS_FIREFOX_LABEL_DEFAULT_OFFSET,firefox_label_default_bytes,form_label_default,(void **)&original_form_label_default},
  {NXS_FIREFOX_LABEL_FORWARD_OFFSET,firefox_label_forward_bytes,form_label_forward,(void **)&original_form_label_forward}
};
