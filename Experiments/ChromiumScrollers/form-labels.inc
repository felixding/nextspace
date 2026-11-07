/* Original label default action supplies association and filtering. The shared
 * provider performs the actual native action. GPL-2.0-or-later. */
#include "pinned-form-labels.h"
static __thread const void *form_label_event;
static void (*original_form_label_default)(void *,void *);
static void (*original_form_label_forward)(void *,const void *,int);
static void form_label_default(void *label,void *event)
{
  const void *previous=form_label_event;form_label_event=event;
  original_form_label_default(label,event);form_label_event=previous;
}
static void form_label_forward(void *node,const void *event,int scope)
{
  struct NativeForm *form=event&&event==form_label_event&&(*(const unsigned short *)((const char *)event+32)&0x100)?find_form(node):NULL;
  if(!form||!form->painted||input_form_kind(node)!=form->kind) {
    original_form_label_forward(node,event,scope);return;
  }
  uint32_t origin=radio_node_id(node);uint64_t control=form->control;
  if(form->kind==NXS_CHECKBOX||form->kind==NXS_BUTTON) {
    int kind=form->kind;form->enabled=form_enabled(node);form->state=form_state(node,kind);
    struct NXSResponse *response=form_request(form,1,0,0,0);double before=response?response->parts[0].width:0;
    struct NXSControlAction action={0};
    if(response)native_control_action_snapshot(native_control_perform_click(kind,control,0),before,&action);
    form=find_form(node);
    if(form&&form->control==control&&form->kind==kind&&native_control_action_valid(&action)) {
      struct NXSCheckboxActivation previous=native_checkbox_activation;
      if(kind==NXS_CHECKBOX)native_checkbox_enter(origin,control,action);
      original_form_label_forward(node,event,scope);native_checkbox_activation=previous;
    }
    node=radio_node_for_id(origin);form=node?find_form(node):NULL;
    if(form&&form->control==control) {
      form->enabled=form_enabled(node);form->state=form_state(node,form->kind);
      form_request(form,1,0,0,0);invalidate_form(form);
    }
    return;
  }
  if(form->kind!=NXS_RADIO||!forms_radio_groups_enabled){original_form_label_forward(node,event,scope);return;}

  struct NativeRadioGroup *g=radio_sync(form);void *target=NULL;
  form=find_form(node);
  if(g&&form&&form->control==control) {
    g->busy++;
    if(native_radio_binding_activate(&g->native,form->radio_member))
      target=radio_action_target(g,origin,control,g->native.state.selected);
    g->busy--;
  }
  if(target)original_form_label_forward(target,event,scope);
  radio_pointer_complete(origin,control);
}
static struct Detour form_label_detours[]={
  {NXS_CHROMIUM_LABEL_DEFAULT_OFFSET,chromium_label_default_bytes,form_label_default,(void **)&original_form_label_default},
  {NXS_CHROMIUM_LABEL_FORWARD_OFFSET,chromium_label_forward_bytes,form_label_forward,(void **)&original_form_label_forward}
};
