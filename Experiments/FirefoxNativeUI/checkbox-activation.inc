/* Native checkbox result inside Gecko's original preactivation transaction.
 * Original journal flags, setters and cancellation remain intact. GPL-2.0-or-later. */
#include "pinned-checkbox-activation.h"
static __thread struct {void *node;uint64_t control;int checked,mixed;} checkbox_pre;
static void (*original_checkbox_pre)(void *,void *);
static void (*original_checkbox_set)(void *,int,int,int,int);
static int checkbox_pre_matches(void *node)
{
  if(!node||checkbox_pre.node!=node)return 0;
  struct Widget *w=widget_for_node(node);
  return w&&w->id==checkbox_pre.control&&w->kind==NXS_CHECKBOX&&node_kind(node)==NXS_CHECKBOX;
}
static void checkbox_pre_activation(void *node,void *visitor)
{
  void *event=*(void **)((char *)visitor+8);struct Widget *w=widget_for_node(node);
  __typeof__(checkbox_pre) previous=checkbox_pre;memset(&checkbox_pre,0,sizeof(checkbox_pre));
  if((*(const uint8_t *)((const char *)event+48)&1)&&native_checkbox_activation.armed&&
     (void *)(uintptr_t)native_checkbox_activation.node==node&&w&&w->id==native_checkbox_activation.control&&
     w->kind==NXS_CHECKBOX&&native_control_action_valid(&native_checkbox_activation.action)) {
    int state=native_checkbox_activation.action.state;native_checkbox_activation.armed=0;
    checkbox_pre.node=node;checkbox_pre.control=w->id;checkbox_pre.mixed=state==-1;
    checkbox_pre.checked=state==-1?!!(*(const uint8_t *)((char *)node+458)&32):state>0;
  }
  original_checkbox_pre(node,visitor);
  if(checkbox_pre.mixed&&checkbox_pre_matches(node))((void (*)(void *,int))(base+NXS_FIREFOX_CHECK_MIXED_OFFSET))(node,1);
  checkbox_pre=previous;
}
static void checkbox_set(void *node,int checked,int notify,int changed,int update)
{original_checkbox_set(node,checkbox_pre_matches(node)?checkbox_pre.checked:checked,notify,changed,update);}
static int guard_checkbox_calls(void)
{return !memcmp((void *)(base+NXS_FIREFOX_CHECK_MIXED_OFFSET),firefox_check_mixed_bytes,20);}
static struct Detour checkbox_activation_detours[]={
 {NXS_FIREFOX_CHECK_PRE_OFFSET,firefox_check_pre_bytes,checkbox_pre_activation,(void **)&original_checkbox_pre},
 {NXS_FIREFOX_CHECK_SET_OFFSET,firefox_check_set_bytes,checkbox_set,(void **)&original_checkbox_set}
};
