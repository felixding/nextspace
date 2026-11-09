/* Gecko temporal models/lifetime bound to the shared NSDatePicker. All editor,
 * calendar, drawing and input rules stay in GNUstep. GPL-2.0-or-later. */
#include "pinned-dates.h"
static void *date_active_node;
static uint64_t date_active_control;
static void (*original_date_shadow)(void *,int,int,int,int);
static void (*original_date_notify)(void *);
static void (*original_date_display)(void *,void *,const void *);
static int (*original_date_focus)(void *,unsigned,uint8_t *,int *);
static int (*original_date_intrinsic)(void *,const void *,int);
static void date_end(const void *);
static void date_finish(const void *,int);
static int date_node(const void *node)
{
  if(!dates_enabled||!native_web_process()||!node||*(const uintptr_t *)node!=base+0xa00fc30+16)return 0;
  unsigned type=*((const unsigned char *)node+144);
  return type==132||(times_enabled&&(type==146||type==150));
}
static int date_mutable(const void *node)
{return date_node(node)&&!(*(const uint64_t *)((const char *)node+112)&0x800010u);}
static int date_tracking(const struct Widget *w)
{return date_active_node==w->node&&date_active_control==w->id;}
static int native_date_frame(const void *frame)
{
  return frame&&date_node(*(void *const *)((const char *)frame+24))&&
    *(const uintptr_t *)frame==base+0xa109c60+16&&
    *(void **)((char *)*(void *const *)((const char *)frame+24)+96)==frame;
}
static void date_shadow(void *node,int widget,int delegate,int slots,int notify)
{
  /* SetupShadowTree is also inlined at its callers. Bind the original shared
   * attachment boundary so every date path omits the replaced JS editor. */
  if(date_node(node)) {
    widget=0;delegate=0;
    note("native Gecko date attaches empty native-widget shadow boundary");
  }
  original_date_shadow(node,widget,delegate,slots,notify);
}
static void date_notify(void *node)
{
  /* Temporal-to-temporal type changes reuse the shadow root and notify the UA
   * widget directly. Keep that replaced editor retired on this path too. */
  if(!date_node(node))original_date_notify(node);
}
static int date_focus(void *node,unsigned flags,uint8_t *focusable,int *tab_index)
{
  if(!date_node(node))return original_date_focus(node,flags,focusable,tab_index);
  /* Let the original form-control base retain tabindex/document policy. The
   * date override normally delegates to anonymous fields that were replaced. */
  int result=((int (*)(void *,unsigned,uint8_t *,int *))(base+NXS_GECKO_DATE_BASE_FOCUS))(node,flags,focusable,tab_index);
  if(!result)*focusable=!(*(const uint64_t *)((const char *)node+112)&0x10u);
  return result;
}
static int date_model(void *node,NXSDateModel *model)
{
  if(!date_node(node))return 0;
  double milliseconds=range_number(node,NXS_GECKO_DATE_VALUE);
  *model=(NXSDateModel){.size=sizeof(*model),.flags=NXS_DATE_UTC|NXS_DATE_ALLOW_EMPTY,
    .elements=NXS_DATE_YEAR_MONTH_DAY,.style=NXS_DATE_TEXT_AND_STEPPER};
  unsigned type=*((const unsigned char *)node+144);
  if(type==146){model->elements=NXS_DATE_HOUR_MINUTE_SECOND;model->flags|=NXS_DATE_TIME_OF_DAY;}
  else if(type==150)model->elements=NXS_DATE_DATE_AND_TIME;
  if(isnan(milliseconds))model->flags|=NXS_DATE_EMPTY;
  else if(isfinite(milliseconds))model->value=milliseconds/1000.;
  else return 0;
  return 1;
}
static struct NXSResponse *sync_date_widget(struct Widget *w,struct NXSResponse *response)
{
  NXSDateModel model;if(!response||!date_model(w->node,&model)||!ensure_text_watch())return NULL;
  w->date.control=w->id;
  if(!native_date_binding_sync(&w->date,&model,date_tracking(w)))return NULL;
  return widget_request(w,5,0,0,0);
}
static int prepare_date_image(void *frame)
{
  if(!native_date_frame(frame)||fabsf(frame_scale(frame)-1)>.000001f)return 0;
  struct Widget *w=bind_widget(frame);if(!w)return 0;
  int rectangle[4]={0};engine_frame_rect((void *)(base+0x6daae5c),frame,rectangle);
  w->width=rectangle[2]/60.;w->height=rectangle[3]/60.;
  if(w->width<1||w->height<1)return 0;
  struct NXSResponse *response=widget_sync(w);
  w->painted=response&&button_cache_update(w,response);w->text_owned=w->painted;return w->painted;
}
static int date_intrinsic(void *frame,const void *input,int type)
{
  if(!native_date_frame(frame))return original_date_intrinsic(frame,input,type);
  struct Widget *w=bind_widget(frame);if(!w)return original_date_intrinsic(frame,input,type);
  struct NXSResponse *response=widget_sync(w);
  double width=response?response->parts[1].width:0;
  return isfinite(width)&&width>0&&width<8192?lround(width*60):original_date_intrinsic(frame,input,type);
}
static void date_display(void *frame,void *builder,const void *lists)
{
  if(!prepare_date_image(frame)){original_date_display(frame,builder,lists);return;}
  void *previous=frontend_background_frame;frontend_background_frame=frame;
  ((void (*)(void *,void *,const void *))(base+NXS_GECKO_TEXT_DISPLAY_BACKGROUND_OFFSET))(frame,builder,lists);
  frontend_background_frame=previous;
}
static int draw_date_image(void *target,void *frame,const struct RectF *area)
{
  struct Widget *w=widget_for_frame(frame);
  if(!w||w->kind!=NXS_DATEPICKER||!w->painted||!button_cache_available(w)||
     w->button_width!=lround(area->width)||w->button_height!=lround(area->height))return 0;
  draw_bitmap(target,area,w->button_pixels,w->button_width,w->button_height);return 1;
}
static void date_apply(struct Widget *w)
{
  struct NXSNativeActionBatch batch;uint64_t control=w->id;void *node=w->node;
  NXSDateModel domain=w->date.model;int rebound=0;
  int accepted=native_date_binding_actions(&w->date,&batch);
  if(accepted<0){note("native Gecko date receipts unavailable");return;}
  ((unsigned (*)(void *))(base+0x3b9f0e4))(node);
  for(unsigned i=0;accepted&&i<batch.count;i++) {
    w=widget_for_node(node);if(!w||w->id!=control||!date_mutable(node))break;
    NXSDateModel current;
    if(!date_model(node,&current)||!native_date_model_domain_same(&domain,&current)){rebound=1;break;}
    const struct NXSActionReceipt *action=&batch.actions[i];
    static const uint16_t empty;struct GeckoString value={.data=&empty,.flags=1};
    if(action->state==0) {
      struct GeckoDecimal decimal=decimal_from_double(action->value*1000.);
      void *type=*(void **)((char *)node+424);
      /* Original SetValue(Decimal)'s input type and virtual serializer slot.
       * Decimal/date serialization and validation remain in Gecko. */
      if(!type||!((int (*)(void *,const void *,int,void *))(*(uintptr_t **)type)[19])(type,&decimal,0,&value)) {
        ((void (*)(void *))(base+0x3826f2c))(&value);break;
      }
    }
    void *info=*(void **)((char *)node+40),*manager=info?*(void **)((char *)info+72):NULL;
    void *principal=manager?*(void **)((char *)manager+56):NULL;
    if(!principal){((void (*)(void *))(base+0x3826f2c))(&value);break;}
    native_date_binding_echo(&w->date,action);
    NXSDateModel expected=w->date.model;
    /* Exact original NodePrincipal load and SetUserInput, as in color input.
     * This retains original user-edit bookkeeping and trusted input/change. */
    ((void (*)(void *,const void *,void *))(base+NXS_GECKO_DATE_SET_USER))(node,&value,principal);
    ((void (*)(void *))(base+0x3826f2c))(&value);
    w=widget_for_node(node);if(!w||w->id!=control)break;
    if(!date_model(node,&current)||!native_date_model_same(&expected,&current)){rebound=1;break;}
  }
  w=widget_for_node(node);
  if(w&&w->id==control) {
    invalidate_widget(w);
    if(date_tracking(w)&&(!date_mutable(node)||rebound))date_finish(NULL,1);
    else if(rebound)native_date_binding_discard(&w->date);
  }
  ((unsigned (*)(void *))(base+0x47ba6b8))(node);
}
static uint32_t date_widget_post(void *node,void *visitor,uint32_t (*original)(void *,void *))
{
  void *event=*(void **)((char *)visitor+8);int *status=(int *)((char *)visitor+24);
  unsigned message=*(const uint16_t *)((char *)event+18);
  struct Widget *w=widget_for_node(node);
  if(log_fd>=0&&message>=2&&message<=4)dprintf(log_fd,"%d native-date-key candidate id=%llu message=%u painted=%d focused=%d mutable=%d status=%d flags=%u\n",getpid(),(unsigned long long)(w?w->id:0),message,w?w->painted:0,w?widget_focused(w):0,date_mutable(node),*status,*((const uint8_t *)event+49));
  if(!w||!w->painted||!widget_focused(w)||message<2||message>4||*status==1||
     !(*(const uint8_t *)((char *)event+48)&1)||(*((const uint8_t *)event+49)&2)||!date_mutable(node))return original(node,visitor);
  if(message==2)return w->date_keypress?0:original(node,visitor);
  uint64_t control=w->id;((unsigned (*)(void *))(base+0x3b9f0e4))(node);
  struct NXSResponse *response=widget_sync(w);
  if(response)response=widget_key_request(w,event,message==4?NXS_KEY_DOWN:NXS_KEY_UP);
  int handled=response?response->parts[3].x:0;
  if(log_fd>=0)dprintf(log_fd,"%d native-date-key result id=%llu handled=%d response=%p\n",getpid(),(unsigned long long)control,handled,(void *)response);
  if(message==4)w->date_keypress=handled!=0;
  date_apply(w);w=widget_for_node(node);
  if(w&&w->id==control) {
    if(handled==NXS_INPUT_NEXT||handled==NXS_INPUT_PREVIOUS) {
      if(advance_focus(node,handled))*status=1;
    } else if(handled)*status=1;
    invalidate_widget(w);
  }
  ((unsigned (*)(void *))(base+0x47ba6b8))(node);
  return handled?0:original(node,visitor);
}
static void date_finish(const void *event,int discard)
{
  void *node=date_active_node;uint64_t control=date_active_control;
  date_active_node=NULL;date_active_control=0;if(!node)return;
  struct Widget *w=widget_for_node(node);
  if(w&&w->id==control) {
    struct PointI point=event?widget_point(w,event):(struct PointI){-600000,-600000};
    struct NXSResponse *response=widget_request(w,4,point.x/60.,point.y/60.,event?widget_modifiers(event):0);
    for(unsigned n=0;response&&response->parts[0].y&&n<100;n++) {
      struct timespec pause={.tv_nsec=2000000};nanosleep(&pause,NULL);response=widget_request(w,5,0,0,0);
    }
    if(discard)native_date_binding_discard(&w->date);
    else date_apply(w);
  }
  ((unsigned (*)(void *))(base+0x47ba6b8))(node);
}
static void date_end(const void *event){date_finish(event,0);}
static int date_pointer_post(void *self,void *context,void *event,void *frame,int *status,void *override,uint32_t *result)
{
  if(!dates_enabled||!(*(const uint8_t *)((char *)event+48)&1))return 0;
  unsigned message=*(const uint16_t *)((char *)event+18);
  if(message!=13&&message!=14&&message!=15)return 0;
  if(message!=13&&*(const int16_t *)((char *)event+152)!=0)return 0;
  struct Widget *w=date_active_node?widget_for_node(date_active_node):NULL;
  if(!w&&message==15&&native_date_frame(frame))w=widget_for_frame(frame);
  /* A page mutation may decline a repaint during tracking. Release still
   * belongs to the held native gesture and must reach the original picker. */
  if(!w||w->kind!=NXS_DATEPICKER||(!date_tracking(w)&&!w->painted))return 0;
  void *node=w->node;uint64_t control=w->id;int allowed=*status!=1&&!(*((const uint8_t *)event+49)&2);
  ((unsigned (*)(void *))(base+0x3b9f0e4))(node);
  if(message==14)date_end(event);
  *result=original_post_event(self,context,event,frame,status,override);
  w=widget_for_node(node);
  if(w&&w->id==control&&message!=14&&allowed&&date_mutable(node)) {
    if(message==15) {
      if(date_active_node)date_end(NULL);
      w=widget_for_node(node);
      if(w&&w->id==control&&widget_sync(w)) {
        struct PointI point=widget_point(w,event);
        if(widget_request(w,2,point.x/60.,point.y/60.,widget_modifiers(event))) {
          ((unsigned (*)(void *))(base+0x3b9f0e4))(node);date_active_node=node;date_active_control=control;
          ((void (*)(void *,unsigned,void *))(base+NXS_GECKO_TEXT_CAPTURE_OFFSET))(node,1,NULL);
          date_apply(w);
        }
      }
    } else if(date_tracking(w)) {
      struct PointI point=widget_point(w,event);
      widget_request(w,3,point.x/60.,point.y/60.,widget_modifiers(event));date_apply(w);
    }
  }
  ((unsigned (*)(void *))(base+0x47ba6b8))(node);return 1;
}
static void date_native_work(void)
{
  struct Widget *w=date_active_node?widget_for_node(date_active_node):NULL;
  if(w&&w->id==date_active_control)date_apply(w);
}
static void date_forget(struct Widget *w)
{
  if(date_tracking(w)) {
    void *node=date_active_node;date_active_node=NULL;date_active_control=0;
    widget_request(w,4,-10000,-10000,0);((unsigned (*)(void *))(base+0x47ba6b8))(node);
  }
}
static void date_reset(void){date_active_node=NULL;date_active_control=0;}
static struct Detour date_detours[]={
 {NXS_GECKO_DATE_ATTACH_SHADOW,gecko_date_attach_shadow_bytes,date_shadow,(void **)&original_date_shadow},
 {NXS_GECKO_DATE_NOTIFY_SHADOW,gecko_date_notify_shadow_bytes,date_notify,(void **)&original_date_notify},
 {NXS_GECKO_DATE_CONTAINER_DISPLAY,gecko_date_container_display_bytes,date_display,(void **)&original_date_display},
 {NXS_GECKO_DATE_FOCUS,gecko_date_focus_bytes,date_focus,(void **)&original_date_focus},
 {NXS_GECKO_DATE_INTRINSIC,gecko_date_intrinsic_bytes,date_intrinsic,(void **)&original_date_intrinsic}
};
