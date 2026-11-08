/* Native NSStepper binding to original Blink number actions. No copied
 * parsing, decimal arithmetic, hit testing or repeat timer. GPL-2.0-or-later. */
#include "pinned-numbers.h"
static int (*original_number_paint)(void *,const void *,const void *,const void *,const struct Rect *);
static void (*original_number_default)(void *,void *);
static struct SizeI number_native_size(void)
{
  static struct SizeI metrics;
  if(metrics.width&&metrics.height)return metrics;
  uint64_t control=++next_form_control;
  struct NXSResponse *response=native_stepper_request(control,1,24,26,1,0,0,0);
  if(response&&response->parts[1].width>=1&&response->parts[1].width<=256&&
     response->parts[1].height>=1&&response->parts[1].height<=256)
    metrics=(struct SizeI){ceil(response->parts[1].width),ceil(response->parts[1].height)};
  native_stepper_request(control,6,24,26,1,0,0,0);
  return metrics;
}
static void *number_type(void *node)
{
  if(!forms_numbers_enabled||!node||*(uintptr_t *)node!=base+0x11dc01d8+16)return NULL;
  void *type=decode_member((char *)node+272);
  return type&&*(uintptr_t *)type==base+NXS_NUMBER_INPUT_VTABLE+16?type:NULL;
}
static void *number_owner(void *node)
{
  if(!forms_numbers_enabled||!node||*(uintptr_t *)node!=base+NXS_NUMBER_SPIN_VTABLE+16)return NULL;
  for(unsigned depth=0;node&&depth<256;depth++) {
    if(number_type(node))return node;
    node=((void *(*)(void *))(base+0xdd0e0ac))(node);
  }
  return NULL;
}
static int number_enabled(void *node)
{
  void *type=number_type(number_owner(node));
  return type&&((int (*)(void *))(base+NXS_NUMBER_RESPONDS))(type);
}
static double number_text_width(void *node)
{
  if(!number_type(node))return 0;
  struct FloatRect input=((struct FloatRect (*)(const void *))(base+NXS_COORDINATE_CLIENT_BOX_OFFSET))(node);
  for(struct NativeForm *form=native_forms;form;form=form->next) {
    if(form->kind!=NXS_STEPPER||number_owner(form->node)!=node)continue;
    struct FloatRect spin=((struct FloatRect (*)(const void *))(base+NXS_COORDINATE_CLIENT_BOX_OFFSET))(form->node);
    /* These are original engine boxes, not native widget layout rules. */
    double width=spin.x-input.x;
    if(isfinite(width)&&width>=1&&width<=input.width)return width;
  }
  return input.width;
}
static int number_text_children(void *input,void *node)
{
  void *type=number_type(input);if(!type)return -1;
  void *container=((void *(*)(const void *))(base+NXS_NUMBER_CONTAINER))(type);
  /* Preserve the original anonymous decoration container/spin traversal and
   * suppress only its editor subtree, whose pixels the native field owns. */
  return node!=input&&node!=container;
}
static struct NativeForm *number_pointer_form(void *input,const void *event)
{
  if(!number_type(input))return NULL;
  for(struct NativeForm *form=native_forms;form;form=form->next) {
    if(form->kind!=NXS_STEPPER||number_owner(form->node)!=input)continue;
    struct FloatPoint point=form_point(form,event);
    /* Blink can retarget its anonymous child to the input before this hook.
     * Route by the original child's box; NSStepper still owns arrow hit tests. */
    if(point.x>=0&&point.y>=0&&point.x<form->rect.width&&point.y<form->rect.height)return form;
  }
  return NULL;
}
static void apply_number_actions(struct NativeForm *form)
{
  uint32_t id=radio_node_id(form->node);uint64_t control=form->control;
  struct NXSStepperBatch batch;
  int accepted=native_stepper_actions(&form->stepper,0,&batch);
  if(accepted<0){note("native number action receipts unavailable; gesture retired");return;}
  for(unsigned i=0;accepted&&i<batch.count;i++) {
    void *node=radio_node_for_id(id);form=node?find_form(node):NULL;
    if(!form||form->kind!=NXS_STEPPER||form->control!=control||!number_enabled(node))break;
    void *type=number_type(number_owner(node));if(!type)break;
    ((void (*)(void *))(base+(batch.directions[i]>0?NXS_NUMBER_STEP_UP:NXS_NUMBER_STEP_DOWN)))(type);
  }
  void *node=radio_node_for_id(id);form=node?find_form(node):NULL;
  if(form&&form->control==control)invalidate_form(form);
}
static int paint_number_stepper(void *self,const void *element,const void *style,const void *info,const struct Rect *rect)
{
  void *owner=number_owner((void *)element);
  if(owner) {
    if(!paint_form(NXS_STEPPER,self,element,NULL,style,info,rect)) {
      struct NativeForm *field=find_form(owner);
      if(field&&fabs(field->rect.width-number_text_width(owner))>=1)invalidate_form(field);
      return 0;
    }
  }
  return original_number_paint(self,element,style,info,rect);
}
static void number_default(void *node,void *event)
{
  struct NativeForm *form=find_form(node);
  if(form&&form->kind==NXS_STEPPER&&form->painted&&form->stepper.ready&&number_owner(node)) {
    uintptr_t atom=*(uintptr_t *)((char *)event+24);
    if(same_atom(atom,0x123a55f8)||same_atom(atom,0x123a5600)||same_atom(atom,0x123a5608)) {
      *(unsigned short *)((char *)event+32)|=0x40;return;
    }
  }
  original_number_default(node,event);
}
static int number_mouse_dispatch(void *manager,void *target,const void *type,const void *event,const void *last,
    void *related,int check,const void *pointer_id,const void *pointer_type,void *down,void *up,struct MouseDispatchResult *result)
{
  if(!forms_numbers_enabled)return 0;
  uintptr_t atom=*(const uintptr_t *)type;
  int press=same_atom(atom,0x123a55f8)&&*(const int *)((const char *)event+120)==0;
  int release=same_atom(atom,0x123a5608)&&*(const int *)((const char *)event+120)==0;
  int move=same_atom(atom,0x123a5600);
  struct NativeForm *form=active_form&&active_form->kind==NXS_STEPPER?active_form:NULL;
  if(!form&&press) {
    void *node=target?((void *(*)(void *))(*(uintptr_t **)target)[9])(target):NULL;
    form=form_ancestor(node);
    if(form&&number_type(form->node))form=number_pointer_form(form->node,event);
  }
  int held=form&&form==active_form&&form->kind==NXS_STEPPER;
  if(!form||form->kind!=NXS_STEPPER||(!held&&(!form->painted||!form->stepper.ready))||(!press&&!release&&!move))return 0;
  void *input=number_owner(form->node);
  uint32_t id=radio_node_id(form->node),owner=input?radio_node_id(input):0;uint64_t control=form->control;
  struct FloatPoint point=form_point(form,event);
  unsigned modifiers=event_modifiers(event);
  if(release&&form==active_form)finish_form(point.x,point.y,modifiers);
  *result=original_mouse_dispatch(manager,target,type,event,last,related,check,pointer_id,pointer_type,down,up);
  void *node=radio_node_for_id(id);form=node?find_form(node):NULL;
  if(!form||form->control!=control)return 1;
  unsigned flags=result->event?*(unsigned short *)((char *)result->event+32):0;
  if(release) {
    void *input=radio_node_for_id(owner),*model=number_type(input);
    if(model)((void (*)(void *,int))(base+NXS_NUMBER_RELEASE))(model,0);
  } else if((flags&0x100)&&!(flags&0x20)&&number_enabled(node)) {
    point=form_point(form,event);
    if(press) {
      if(active_form)finish_form(-10000,-10000,0);
      node=radio_node_for_id(id);form=node?find_form(node):NULL;
      if(!form||form->control!=control||!number_enabled(node))return 1;
      void *model=number_type(number_owner(node));
      ((void (*)(void *))(base+NXS_NUMBER_FOCUS))(model);
      node=radio_node_for_id(id);form=node?find_form(node):NULL;
      if(!form||form->control!=control||!number_enabled(node))return 1;
      form->enabled=1;struct NXSStepperBatch baseline;
      if(form_request(form,1,0,0,0)&&native_stepper_actions(&form->stepper,1,&baseline)>0) {
        struct NXSResponse *response=form_request(form,2,point.x,point.y,modifiers);
        if(response&&response->parts[0].y){active_form=form;refresh_form_watch();invalidate_form(form);}
      }
    } else if(move&&form==active_form){form_request(form,3,point.x,point.y,modifiers);apply_number_actions(form);}
  }
  return 1;
}
static int guard_number_calls(void)
{
  return !memcmp((void *)(base+NXS_NUMBER_INNER_VALUE),number_inner_value_bytes,20)&&
    !memcmp((void *)(base+NXS_NUMBER_CONTAINER),number_container_bytes,20)&&
    !memcmp((void *)(base+NXS_RADIO_NODE_ID_OFFSET),nxs_radio_node_id_bytes,20)&&
    !memcmp((void *)(base+NXS_RADIO_NODE_FOR_ID_OFFSET),nxs_radio_node_for_id_bytes,20)&&
    !memcmp((void *)(base+NXS_NUMBER_STEP_UP),number_step_up_bytes,20)&&
    !memcmp((void *)(base+NXS_NUMBER_STEP_DOWN),number_step_down_bytes,20)&&
    !memcmp((void *)(base+NXS_NUMBER_FOCUS),number_focus_bytes,20)&&
    !memcmp((void *)(base+NXS_NUMBER_RESPONDS),number_responds_bytes,20)&&
    !memcmp((void *)(base+NXS_NUMBER_RELEASE),number_release_bytes,20);
}
static struct Detour number_detours[]={
 {NXS_NUMBER_PAINT,number_paint_bytes,paint_number_stepper,(void **)&original_number_paint},
 {NXS_NUMBER_DEFAULT,number_default_bytes,number_default,(void **)&original_number_default}
};
