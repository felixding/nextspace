/* Input format and lifetime binding only. NSScrollView owns wheel behavior. */
#include "pinned-wheel.h"
static void native_wheel_binding(struct NativeForm *form,int enabled) {
  if(!forms_wheel_enabled||(form->kind!=NXS_TEXTAREA&&form->kind!=NXS_LISTBOX))return;
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
/* Keep native delivery inside the original trusted DOM default dispatch.
 * Returning a handled result after DispatchEvent has already completed leaves
 * the engine's targeting/default-action lifecycle out of sync. */
static __thread const void *native_wheel_event;
static __thread int native_wheel_delivered;
static int native_wheel_supported(const void *event) {
  if(!forms_wheel_enabled||!event)return 0;
  unsigned phase=*(const uint32_t *)((const char *)event+NXS_WHEEL_PHASE_BYTE);
  unsigned momentum=*(const uint32_t *)((const char *)event+NXS_WHEEL_PHASE_BYTE+4);
  int action=*(const int *)((const char *)event+NXS_WHEEL_ACTION_BYTE);
  unsigned units=*((const unsigned char *)event+NXS_WHEEL_UNITS_BYTE);
  return !((phase|momentum)&(8|16|32))&&action>=1&&action<=3&&units<=1;
}
static int native_wheel_dispatch(void *dispatcher) {
  void *node=*(void **)dispatcher,*event=*((void **)dispatcher+1);
  unsigned short *flags=(unsigned short *)((char *)event+32);
  struct NativeForm *form=NULL;
  if(native_wheel_supported(native_wheel_event)&&
     *(uintptr_t *)event==base+NXS_WHEEL_DOM_VTABLE_OFFSET+16&&(*flags&0x100)&&!(*flags&0x60))
    form=form_ancestor(node);
  uint32_t origin=0;uint64_t control=0;
  if(form&&form->painted&&(form->kind==NXS_TEXTAREA||form->kind==NXS_LISTBOX)) {
    origin=radio_node_id(form->node);control=form->control;
  }
  int result=original_dom_dispatch(dispatcher);
  if(origin&&!result&&!(*flags&0x60)) {
    node=radio_node_for_id(origin);form=node?find_form(node):NULL;
    if(!form||form->control!=control) {
      /* A page listener retired the native target. Complete its default
       * without asking the compositor to scroll that removed widget later. */
      native_wheel_delivered=1;*flags|=0x40;
      result=2; /* Original DispatchEventResult::kCanceledByDefaultEventHandler. */
      note("retired native wheel target consumed");
    }
  }
  return result;
}
static int (*original_wheel_manager)(void *,const void *);
static int wheel_manager(void *self,const void *event) {
  const void *previous=native_wheel_event;int delivered=native_wheel_delivered;
  native_wheel_event=event;native_wheel_delivered=0;
  int result=original_wheel_manager(self,event);
  native_wheel_event=previous;native_wheel_delivered=delivered;
  return result;
}
static int native_wheel_default(void *node,void *dom_event) {
  const void *event=native_wheel_event;
  if(!forms_wheel_enabled||!event||native_wheel_delivered||
     *(uintptr_t *)dom_event!=base+NXS_WHEEL_DOM_VTABLE_OFFSET+16)return 0;
  unsigned short *flags=(unsigned short *)((char *)dom_event+32);
  if(!(*flags&0x100)||(*flags&0x60))return 0;
  if(!native_wheel_supported(event))return 0;
  struct NativeForm *form=find_form(node);
  if(!form||(form->kind!=NXS_TEXTAREA&&form->kind!=NXS_LISTBOX)||!form->painted)return 0;
  unsigned units=*((const unsigned char *)event+NXS_WHEEL_UNITS_BYTE);
  const float *delta=(const float *)((const char *)event+(units?NXS_WHEEL_TICKS_BYTE:NXS_WHEEL_DELTA_BYTE));
  /* Undo Ozone's axis-to-wheel normalization. Precise axes retain their
   * surface distance; ordinary wheel ticks represent ten surface units. */
  double dx=-delta[0]*(units?10:1),dy=-delta[1]*(units?10:1);
  if(!isfinite(dx)||!isfinite(dy))return 0;
  uint64_t control=form->control;
  struct FloatPoint point=form_point(form,event);
  if(form->kind==NXS_LISTBOX) {
    if(!list_sync(form)||!form->list.geometry_ready)return 0;
    NXSWheelEvent wheel={.size=sizeof(wheel),.x=point.x,.y=point.y,.delta_x=dx,.delta_y=dy,.modifiers=event_modifiers(event)};
    if(!native_list_binding_wheel(&form->list,&wheel))return 0;
    native_wheel_delivered=1;*flags|=0x40;
    echo_text_viewport(form);schedule_form_paint(form);return 1;
  }
  form=find_form(node);if(!form||form->control!=control||!sync_text_image(form))return 0;
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=35,
    .process=identity(),.kind=NXS_TEXTAREA,.control=control,.x=point.x,.y=point.y,
    .minimum=dx,.maximum=dy,.modifiers=event_modifiers(event)};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  if(!response)return 0;
  int accepted=response->parts[3].x==1;
  if(accepted){
    native_wheel_delivered=1;*flags|=0x40;
    if(read_text_viewport(form))echo_text_viewport(form);
    schedule_form_paint(form);
  }
  static __thread unsigned logged;
  if(logged++<48&&log_fd>=0)dprintf(log_fd,"%d native-wheel id=%llu axes=%.3f,%.3f units=%u accepted=%d offset=%.3f,%.3f\n",getpid(),(unsigned long long)control,dx,dy,units,accepted,form->text_viewport.visible.x,form->text_viewport.visible.y);
  return accepted; /* Original DispatchEvent supplies the engine acknowledgement. */
}
static struct Detour wheel_detours[]={
  {NXS_WHEEL_MANAGER_OFFSET,nxs_wheel_manager_bytes,wheel_manager,(void **)&original_wheel_manager}
};
