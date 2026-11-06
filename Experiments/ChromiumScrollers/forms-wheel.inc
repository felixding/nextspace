/* Input format and lifetime binding only. NSScrollView owns wheel behavior. */
#include "pinned-wheel.h"
static void native_wheel_binding(struct NativeForm *form,int enabled) {
  if(!forms_wheel_enabled||form->kind!=NXS_TEXTAREA)return;
  void *frame=text_frame(form->node);
  void *handler=frame?decode_member((char *)frame+592):NULL;
  void *registry=handler?decode_member((char *)handler+NXS_WHEEL_REGISTRY_BYTE):NULL;
  if(!enabled){
    if(registry&&registry==form->wheel_registry)
      ((void (*)(void *,void *,int))(base+NXS_WHEEL_REGISTRY_REMOVE_OFFSET))(registry,form->node,1);
    form->wheel_registry=NULL;return;
  }
  if(registry&&form->wheel_registry!=registry){
    /* The engine uses this registry for native widget handlers too. Register
     * a blocking wheel region without adding page JavaScript or a dummy DOM
     * listener. Pair it with layout-detach cleanup. */
    ((void (*)(void *,void *,int))(base+NXS_WHEEL_REGISTRY_ADD_OFFSET))(registry,form->node,1);
    form->wheel_registry=registry;
  }
}
static int (*original_wheel_manager)(void *,const void *);
static int wheel_manager(void *self,const void *event) {
  /* Real targeting, subframe forwarding, trusted DOM dispatch and cancellation
   * run first. The native control supplies only the uncancelled default action. */
  int result=original_wheel_manager(self,event);
  if(result||!forms_wheel_enabled)return result;
  unsigned phase=*(const uint32_t *)((const char *)event+NXS_WHEEL_PHASE_BYTE);
  unsigned momentum=*(const uint32_t *)((const char *)event+NXS_WHEEL_PHASE_BYTE+4);
  int action=*(const int *)((const char *)event+NXS_WHEEL_ACTION_BYTE);
  if((phase|momentum)&(8|16|32)||action<1||action>3)return result;
  struct NativeForm *form=form_ancestor(decode_member((char *)self+NXS_WHEEL_TARGET_BYTE));
  if(!form||form->kind!=NXS_TEXTAREA||!form->painted)return result;
  unsigned units=*((const unsigned char *)event+NXS_WHEEL_UNITS_BYTE);
  if(units>1)return result; /* Page/document input needs its own native binding. */
  const float *delta=(const float *)((const char *)event+(units?NXS_WHEEL_TICKS_BYTE:NXS_WHEEL_DELTA_BYTE));
  /* Undo Ozone's axis-to-wheel normalization. Precise axes retain their
   * surface distance; ordinary wheel ticks represent ten surface units. */
  double dx=-delta[0]*(units?10:1),dy=-delta[1]*(units?10:1);
  if(!isfinite(dx)||!isfinite(dy))return result;
  void *node=form->node;uint64_t control=form->control;
  struct FloatPoint point=form_point(form,event);
  form=find_form(node);if(!form||form->control!=control||!sync_text_image(form))return result;
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=35,
    .process=identity(),.kind=NXS_TEXTAREA,.control=control,.x=point.x,.y=point.y,
    .minimum=dx,.maximum=dy,.modifiers=event_modifiers(event)};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  if(!response)return result;
  int accepted=response->parts[3].x==1;
  if(accepted){
    if(read_text_viewport(form))echo_text_viewport(form);
    schedule_form_paint(form);
  }
  static __thread unsigned logged;
  if(logged++<48&&log_fd>=0)dprintf(log_fd,"%d native-wheel id=%llu axes=%.3f,%.3f units=%u accepted=%d offset=%.3f,%.3f\n",getpid(),(unsigned long long)control,dx,dy,units,accepted,form->text_viewport.visible.x,form->text_viewport.visible.y);
  return 3; /* Chromium kHandledSystem: no second browser default action. */
}
static struct Detour wheel_detours[]={
  {NXS_WHEEL_MANAGER_OFFSET,nxs_wheel_manager_bytes,wheel_manager,(void **)&original_wheel_manager}
};
