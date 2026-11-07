/* Gecko owns label association, filtering and trusted click creation. The shared
 * provider supplies native semantic activation. GPL-2.0-or-later. */
#include "pinned-radio-labels.h"
static __thread void *radio_label_event;
static uint32_t (*original_radio_label_default)(void *,void *);
static uint32_t (*original_radio_label_forward)(void *,void *,void *,int,const void *,int *);
static uint32_t radio_label_default(void *label,void *visitor)
{
  void *previous=radio_label_event;radio_label_event=*(void **)((char *)visitor+8);
  uint32_t result=original_radio_label_default(label,visitor);radio_label_event=previous;return result;
}
static uint32_t radio_label_forward(void *context,void *event,void *node,int full,const void *flags,int *status)
{
  struct Widget *w=event&&event==radio_label_event&&(*(const uint8_t *)((const char *)event+48)&1)?widget_for_node(node):NULL;
  if(!w||!w->painted||w->kind!=NXS_RADIO||node_kind(node)!=NXS_RADIO)
    return original_radio_label_forward(context,event,node,full,flags,status);
  uint64_t id=w->id;struct GeckoRadioGroup *g=gecko_radio_sync(w);void *target=NULL;
  w=widget_for_node(node);
  if(g&&w&&w->id==id) {
    g->busy++;
    if(native_radio_binding_activate(&g->native,w->radio_member))
      target=gecko_radio_action_target(g,node,id,g->native.state.selected);
    g->busy--;
  }
  uint32_t result=target?original_radio_label_forward(context,event,target,full,flags,status):0;
  gecko_radio_pointer_complete(node,id);return result;
}
static struct Detour radio_label_detours[]={
  {NXS_FIREFOX_LABEL_DEFAULT_OFFSET,firefox_label_default_bytes,radio_label_default,(void **)&original_radio_label_default},
  {NXS_FIREFOX_LABEL_FORWARD_OFFSET,firefox_label_forward_bytes,radio_label_forward,(void **)&original_radio_label_forward}
};
