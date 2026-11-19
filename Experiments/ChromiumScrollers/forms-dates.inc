/* Native date view binding to original Blink temporal models and events.
 * NSDatePicker supplies the entire editor; no calendar/editor is copied here.
 * GPL-2.0-or-later. */
#include "pinned-dates.h"
#include "forms-months.inc"
static void (*original_date_field_default)(void *,void *);
static void (*original_date_edit_default)(void *,void *);
static void (*original_date_indicator_default)(void *,void *);
static void (*original_date_set_value)(void *,const void *,int);
static int (*original_date_field_focus)(const void *,int);
static int (*original_date_indicator_focus)(const void *,int);
static void (*original_date_focus_in)(void *,void *,int);
static void (*original_date_blur)(void *);
static void *date_type(void *node)
{
  if(!forms_dates_enabled||!node||*(uintptr_t *)node!=base+0x11dc01d8+16)return NULL;
  void *type=decode_member((char *)node+272);
  if(!type)return NULL;
  uintptr_t table=*(uintptr_t *)type;
  return table==base+NXS_DATE_TYPE_VTABLE+16||month_type(type)||(forms_weeks_enabled&&table==base+NXS_WEEK_TYPE_VTABLE+16)||(forms_times_enabled&&
    (table==base+NXS_TIME_TYPE_VTABLE+16||table==base+NXS_DATETIME_TYPE_VTABLE+16))?type:NULL;
}
static void *date_view(void *node)
{
  if(!date_type(node))return NULL;
  /* Original HasBadInput's guarded compressed member load is at +276. */
  void *view=decode_member((char *)node+276);
  return view&&*(uintptr_t *)view==base+NXS_DATE_VIEW_VTABLE+16?view:NULL;
}
static int date_enabled(void *node)
{
  void *view=date_view(node);
  return view&&!((int (*)(const void *))(base+NXS_DATE_READONLY))(view);
}
static int date_model(void *node,NXSDateModel *model)
{
  void *type=date_type(node);if(!type||!date_view(node))return 0;
  double milliseconds=((double (*)(const void *))(base+(month_type(type)?NXS_MONTH_VALUE:NXS_DATE_VALUE)))(type);
  *model=(NXSDateModel){.size=sizeof(*model),.flags=NXS_DATE_UTC|NXS_DATE_ALLOW_EMPTY,
    .elements=NXS_DATE_YEAR_MONTH_DAY,.style=NXS_DATE_TEXT_AND_STEPPER};
  if(forms_proleptic_enabled)model->flags|=NXS_DATE_PROLEPTIC_GREGORIAN;
  if(forms_weeks_enabled&&*(uintptr_t *)type==base+NXS_WEEK_TYPE_VTABLE+16) {
    model->elements=NXS_DATE_YEAR_WEEK;model->flags|=NXS_DATE_WEEK_START;
  } else if(month_type(type)) {
    model->elements=NXS_DATE_YEAR_MONTH;model->flags|=NXS_DATE_MONTH_START;
  } else if(*(uintptr_t *)type==base+NXS_TIME_TYPE_VTABLE+16) {
    model->elements=NXS_DATE_HOUR_MINUTE_SECOND;model->flags|=NXS_DATE_TIME_OF_DAY;
  } else if(*(uintptr_t *)type==base+NXS_DATETIME_TYPE_VTABLE+16)model->elements=NXS_DATE_DATE_AND_TIME;
  if(isnan(milliseconds))model->flags|=NXS_DATE_EMPTY;
  else if(isfinite(milliseconds))model->value=milliseconds/1000.;
  else return 0;
  return 1;
}
static struct NXSResponse *sync_date_image(struct NativeForm *form,struct NXSResponse *response)
{
  if(!response)return NULL;
  NXSDateModel model;if(!date_model(form->node,&model))return NULL;
  form->date.control=form->control;form->input_owned=1;
  if(!refresh_form_watch()||!native_date_binding_sync(&form->date,&model,active_form==form))return NULL;
  return form_request(form,5,0,0,0);
}
static void date_apply(struct NativeForm *form)
{
  uint32_t id=radio_node_id(form->node);uint64_t control=form->control;
  NXSDateModel domain=form->date.model;int rebound=0;
  struct NXSNativeActionBatch batch;
  int accepted=native_date_binding_actions(&form->date,&batch);
  if(accepted<0){note("native date action receipts unavailable");return;}
  if(!accepted||!batch.count)return;
  for(unsigned i=0;accepted&&i<batch.count;i++) {
    void *node=radio_node_for_id(id);form=node?find_form(node):NULL;
    if(!form||form->control!=control||form->kind!=NXS_DATEPICKER||!date_enabled(node))break;
    NXSDateModel current;
    if(!date_model(node,&current)||!native_date_model_domain_same(&domain,&current)){rebound=1;break;}
    void *view=date_view(node);if(!view)break;
    const struct NXSActionReceipt *action=&batch.actions[i];
    double chosen=action->state==-1?NAN:action->value*1000.;void *type=date_type(node);
    if(month_type(type)&&action->state==0&&!month_number(type,action->value,&chosen)){rebound=1;break;}
    native_date_binding_echo(&form->date,action);form->date_commit_pending=1;
    form->date_commit_domain=domain;
    NXSDateModel expected=form->date.model;
    ((void (*)(void *,double))(base+NXS_DATE_CHOOSE))(view,chosen);
    node=radio_node_for_id(id);form=node?find_form(node):NULL;
    if(!form||form->control!=control)break;
    if(!date_model(node,&current)||!native_date_model_same(&expected,&current)){rebound=1;break;}
  }
  void *node=radio_node_for_id(id);form=node?find_form(node):NULL;
  if(form&&form->control==control) {
    invalidate_form(form);
    if(active_form==form&&(!date_enabled(node)||rebound)) {
      form->date_discard_pending=1;finish_form(-10000,-10000,0);
    } else if(rebound)native_date_binding_discard(&form->date);
  }
}
static void date_commit(void *node,uint64_t control)
{
  struct NativeForm *form=find_form(node);void *view=date_view(node);
  if(!form||form->control!=control||!form->date_commit_pending||!view)return;
  form->date_commit_pending=0;
  NXSDateModel current;
  if(!date_model(node,&current)||!native_date_model_domain_same(&form->date_commit_domain,&current))return;
  ((void (*)(void *))(base+NXS_DATE_COMMIT))(view);
}
static int date_default_key(void *node,void *event)
{
  struct NativeForm *form=find_form(node);
  if(!form||form->kind!=NXS_DATEPICKER||!form->painted||!date_view(node))return 0;
  unsigned short *flags=(unsigned short *)((char *)event+32);
  if(!(*flags&0x100)||(*flags&0x60))return 0;
  uintptr_t atom=*(uintptr_t *)((char *)event+24);
  int down=same_atom(atom,0x123a55d8),up=same_atom(atom,0x123a55e8),press=same_atom(atom,0x123a55e0);
  if(!down&&!up&&!press)return 0;
  /* The disabled native picker has no first responder. Preserve the browser's
   * original readonly focus/navigation defaults without sending editor input. */
  if(!date_enabled(node))return 0;
  if(up||press){*flags|=0x40;return 1;}
  if(*(const unsigned char *)((char *)event+140))return 0;
  void *web=*(void **)((char *)event+112);if(!web)return 0;
  char *key=string_text(*(void **)((char *)event+128));if(!key)return 0;
  if(!strcmp(key,"Control")||!strcmp(key,"Alt")||!strcmp(key,"Shift")||!strcmp(key,"Meta")){free(key);return 0;}
  unsigned modifiers=event_modifiers(web),logical=logical_key(key);
  char *text=keyboard_text(web,102,key),*unmodified=keyboard_text(web,110,key);free(key);
  if(!text||!unmodified){free(text);free(unmodified);return 0;}
  uint32_t id=radio_node_id(node);uint64_t control=form->control;
  struct NXSResponse *response=sync_date_image(form,sync_form_focus(form,form_request(form,1,0,0,0)));
  if(response)response=form_input_request(form,8,0,NXS_KEY_DOWN,logical,text,unmodified,modifiers,!!(*(const unsigned *)((char *)event+108)&(1u<<5)));
  free(text);free(unmodified);
  int handled=response?response->parts[3].x:0;
  date_apply(form);node=radio_node_for_id(id);form=node?find_form(node):NULL;
  if(form&&form->control==control){date_commit(node,control);invalidate_form(form);}
  if(node&&(handled==NXS_INPUT_NEXT||handled==NXS_INPUT_PREVIOUS))advance_form_focus(node,event,handled);
  if(handled)*flags|=0x40;
  return 1;
}
static int date_source_default(void *node,void *event)
{
  struct NativeForm *form=form_ancestor(node);
  if(!form||form->kind!=NXS_DATEPICKER||!form->painted)return 0;
  if(date_default_key(form->node,event))return 1;
  uintptr_t atom=*(uintptr_t *)((char *)event+24);
  return same_atom(atom,0x123a55f8)||same_atom(atom,0x123a5608)||same_atom(atom,0x123a5590);
}
static void date_field_default(void *node,void *event)
{if(!date_source_default(node,event))original_date_field_default(node,event);}
static void date_edit_default(void *node,void *event)
{if(!date_source_default(node,event))original_date_edit_default(node,event);}
static void date_indicator_default(void *node,void *event)
{if(!date_source_default(node,event))original_date_indicator_default(node,event);}
static void date_set_value(void *view,const void *value,int changed)
{
  original_date_set_value(view,value,changed);
  /* Blink normally repaints its anonymous fields. Our complete native image
   * belongs to the input's border, which needs the original invalidation. */
  for(struct NativeForm *form=native_forms;form;form=form->next)
    if(form->kind==NXS_DATEPICKER&&date_view(form->node)==view)invalidate_form(form);
}
static int date_native_ancestor(const void *node)
{
  struct NativeForm *form=form_ancestor((void *)node);
  return form&&form->kind==NXS_DATEPICKER&&form->painted;
}
/* The native picker is one focusable widget. Original anonymous browser
 * segments and its replaced indicator no longer participate in traversal. */
static int date_field_focus(const void *node,int update)
{return date_native_ancestor(node)?0:original_date_field_focus(node,update);}
static int date_indicator_focus(const void *node,int update)
{return date_native_ancestor(node)?0:original_date_indicator_focus(node,update);}
static void date_focus_in(void *view,void *previous,int type)
{
  /* Original focus-in redirects into browser segments (or advances again on
   * backward entry). The native widget retains focus on its owning input. */
  for(struct NativeForm *form=native_forms;form;form=form->next)
    if(form->kind==NXS_DATEPICKER&&form->painted&&date_view(form->node)==view)return;
  original_date_focus_in(view,previous,type);
}
static void date_blur(void *view)
{
  uint32_t id=0;uint64_t control=0;
  for(struct NativeForm *form=native_forms;form;form=form->next)
    if(form->kind==NXS_DATEPICKER&&form->painted&&date_view(form->node)==view) {
      id=radio_node_id(form->node);control=form->control;break;
    }
  /* Retain original popup cleanup. Its anonymous-field blur no longer owns
   * native focus; the original base view blurs the owning application input. */
  original_date_blur(view);
  void *node=id?radio_node_for_id(id):NULL;struct NativeForm *form=node?find_form(node):NULL;
  if(form&&form->control==control&&date_view(node)==view&&form_focused(node))
    ((void (*)(void *))(base+NXS_DATE_BASE_BLUR))(view);
}
static int date_mouse_dispatch(void *manager,void *target,const void *type,const void *event,const void *last,
    void *related,int check,const void *pointer_id,const void *pointer_type,void *down,void *up,struct MouseDispatchResult *result)
{
  if(!forms_dates_enabled)return 0;
  uintptr_t atom=*(const uintptr_t *)type;
  int press=same_atom(atom,0x123a55f8)&&*(const int *)((const char *)event+120)==0;
  int release=same_atom(atom,0x123a5608)&&*(const int *)((const char *)event+120)==0;
  int move=same_atom(atom,0x123a5600);
  struct NativeForm *form=active_form&&active_form->kind==NXS_DATEPICKER?active_form:NULL;
  if(!form&&press) {
    void *node=target?((void *(*)(void *))(*(uintptr_t **)target)[9])(target):NULL;
    form=form_ancestor(node);
  }
  int held=form&&form==active_form;
  if(!form||form->kind!=NXS_DATEPICKER||(!held&&(!form->painted||!form->date.ready))||(!press&&!release&&!move))return 0;
  uint32_t id=radio_node_id(form->node);uint64_t control=form->control;
  struct FloatPoint point=form_point(form,event);unsigned modifiers=event_modifiers(event);
  if(release&&held)finish_form(point.x,point.y,modifiers);
  *result=original_mouse_dispatch(manager,target,type,event,last,related,check,pointer_id,pointer_type,down,up);
  void *node=radio_node_for_id(id);form=node?find_form(node):NULL;
  if(!form||form->control!=control)return 1;
  unsigned flags=result->event?*(unsigned short *)((char *)result->event+32):0;
  if((flags&0x100)&&!(flags&0x20)&&date_enabled(node)) {
    point=form_point(form,event);
    if(press) {
      if(active_form)finish_form(-10000,-10000,0);
      node=radio_node_for_id(id);form=node?find_form(node):NULL;
      if(!form||form->control!=control||!date_enabled(node))return 1;
      struct NXSResponse *response=sync_date_image(form,sync_form_focus(form,form_request(form,1,0,0,0)));
      if(response)response=form_request(form,2,point.x,point.y,modifiers);
      if(response){active_form=form;refresh_form_watch();date_apply(form);}
    } else if(move&&held) {form_request(form,3,point.x,point.y,modifiers);date_apply(form);}
  }
  return 1;
}
static struct Detour date_detours[]={
 {NXS_DATE_BLUR,date_blur_bytes,date_blur,(void **)&original_date_blur},
 {NXS_DATE_FOCUS_IN,date_focus_in_bytes,date_focus_in,(void **)&original_date_focus_in},
 {NXS_DATE_FIELD_FOCUS,date_field_focus_bytes,date_field_focus,(void **)&original_date_field_focus},
 {NXS_DATE_INDICATOR_FOCUS,date_indicator_focus_bytes,date_indicator_focus,(void **)&original_date_indicator_focus},
 {NXS_DATE_SET_VALUE,date_set_value_bytes,date_set_value,(void **)&original_date_set_value},
 {NXS_DATE_FIELD_DEFAULT,date_field_default_bytes,date_field_default,(void **)&original_date_field_default},
 {NXS_DATE_EDIT_DEFAULT,date_edit_default_bytes,date_edit_default,(void **)&original_date_edit_default},
 {NXS_DATE_INDICATOR_DEFAULT,date_indicator_default_bytes,date_indicator_default,(void **)&original_date_indicator_default}
};
