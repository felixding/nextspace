/* Original label default action supplies association and filtering. The shared
 * provider performs the actual native action. GPL-2.0-or-later. */
#include "pinned-radio-labels.h"
static __thread const void *radio_label_event;
static void (*original_radio_label_default)(void *,void *);
static void (*original_radio_label_forward)(void *,const void *,int);
static void radio_label_default(void *label,void *event)
{
  const void *previous=radio_label_event;radio_label_event=event;
  original_radio_label_default(label,event);radio_label_event=previous;
}
static void radio_label_forward(void *node,const void *event,int scope)
{
  struct NativeForm *form=event&&event==radio_label_event&&(*(const unsigned short *)((const char *)event+32)&0x100)?find_form(node):NULL;
  if(!form||!form->painted||form->kind!=NXS_RADIO||input_form_kind(node)!=NXS_RADIO) {
    original_radio_label_forward(node,event,scope);return;
  }
  uint32_t origin=radio_node_id(node);uint64_t control=form->control;
  struct NativeRadioGroup *g=radio_sync(form);void *target=NULL;
  form=find_form(node);
  if(g&&form&&form->control==control) {
    g->busy++;
    if(native_radio_binding_activate(&g->native,form->radio_member))
      target=radio_action_target(g,origin,control,g->native.state.selected);
    g->busy--;
  }
  if(target)original_radio_label_forward(target,event,scope);
  radio_pointer_complete(origin,control);
}
static struct Detour radio_label_detours[]={
  {NXS_CHROMIUM_LABEL_DEFAULT_OFFSET,chromium_label_default_bytes,radio_label_default,(void **)&original_radio_label_default},
  {NXS_CHROMIUM_LABEL_FORWARD_OFFSET,chromium_label_forward_bytes,radio_label_forward,(void **)&original_radio_label_forward}
};
