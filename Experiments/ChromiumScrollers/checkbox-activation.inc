/* Bind the native checkbox result inside Blink's original activation journal.
 * Original setters, event construction and rollback stay engine-owned. GPL-2.0-or-later. */
#include "pinned-checkbox-activation.h"
static __thread struct {uint64_t node,control;int checked,mixed;} checkbox_pre;
static void *(*original_checkbox_pre)(void *,void *);
static void (*original_checkbox_set)(void *,int,int,int);
static int checkbox_pre_matches(void *node)
{
  if(!checkbox_pre.node||radio_node_for_id(checkbox_pre.node)!=node)return 0;
  struct NativeForm *form=find_form(node);
  return form&&form->control==checkbox_pre.control&&
    form->kind==NXS_CHECKBOX&&input_form_kind(node)==NXS_CHECKBOX;
}
static void *checkbox_pre_activation(void *node,void *event)
{
  struct NativeForm *form=find_form(node);
  __typeof__(checkbox_pre) previous=checkbox_pre;memset(&checkbox_pre,0,sizeof(checkbox_pre));
  if(event&&same_atom(*(const uintptr_t *)((char *)event+24),0x123a5590)&&
     (*(const unsigned short *)((char *)event+32)&0x100)&&native_checkbox_activation.armed&&
     radio_node_for_id(native_checkbox_activation.node)==node&&form&&form->control==native_checkbox_activation.control&&
     form->kind==NXS_CHECKBOX&&native_control_action_valid(&native_checkbox_activation.action)) {
    int state=native_checkbox_activation.action.state;native_checkbox_activation.armed=0;
    checkbox_pre.node=radio_node_id(node);checkbox_pre.control=form->control;checkbox_pre.mixed=state==-1;
    checkbox_pre.checked=state==-1?!!((int (*)(void *))(base+0xefaa720))(node):state>0;
  }
  void *journal=original_checkbox_pre(node,event);
  if(checkbox_pre.mixed&&checkbox_pre_matches(node))((void (*)(void *,int))(base+NXS_CHROMIUM_CHECK_MIXED_OFFSET))(node,1);
  checkbox_pre=previous;return journal;
}
static void checkbox_set(void *node,int checked,int behavior,int autofill)
{original_checkbox_set(node,checkbox_pre_matches(node)?checkbox_pre.checked:checked,behavior,autofill);}
static int guard_checkbox_calls(void)
{return !memcmp((void *)(base+NXS_CHROMIUM_CHECK_MIXED_OFFSET),chromium_check_mixed_bytes,20);}
static struct Detour checkbox_activation_detours[]={
 {NXS_CHROMIUM_CHECK_PRE_OFFSET,chromium_check_pre_bytes,checkbox_pre_activation,(void **)&original_checkbox_pre},
 {NXS_CHROMIUM_CHECK_SET_OFFSET,chromium_check_set_bytes,checkbox_set,(void **)&original_checkbox_set}
};
