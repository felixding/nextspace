/* Native wheel ownership at Gecko's real post-DOM/default boundary. */
#include "pinned-wheel.h"
static uint32_t (*original_wheel_hit_info)(void *,void *);
static uint32_t wheel_hit_info(void *frame,void *builder) {
  uint32_t result=original_wheel_hit_info(frame,builder);
  /* The engine uses the same flag for its built-in range handlers. APZ must
   * wait for this real native widget, including pages without DOM listeners. */
  struct FrameViewport data;void *owner=wheel_enabled?viewport_frame(frame):NULL;
  if(wheel_enabled&&(result&1)&&owner&&viewport_data(owner,&data,0))result|=4;
  return result;
}
static int native_wheel_post(void *event,void *frame,int *status) {
  if(!wheel_enabled||*(const uint16_t *)((const char *)event+18)!=220||*status==1||
     !(*(const uint8_t *)((const char *)event+48)&1)||(*((const uint8_t *)event+49)&2))return 0;
  /* Reuse Gecko's current wheel action preferences, preserving app zoom and
   * history commands. Exact-build Maybe<APZWheelAction>::Some(Scroll)=0x100. */
  if(((uint16_t (*)(const void *))(base+NXS_GECKO_WHEEL_APZ_ACTION_OFFSET))(event)!=0x100)return 0;
  void *native_frame=viewport_frame(frame);struct FrameViewport data;
  if(!native_frame||!viewport_data(native_frame,&data,0))return 0;
  unsigned mode=*(const uint32_t *)((const char *)event+NXS_GECKO_WHEEL_MODE_BYTE);
  if(mode>1)return 0;
  const double *delta=(const double *)((const char *)event+(mode?NXS_GECKO_WHEEL_TICKS_BYTE:NXS_GECKO_WHEEL_DELTA_BYTE));
  double dx=delta[0]*(mode?10:1),dy=delta[1]*(mode?10:1);
  if(!isfinite(dx)||!isfinite(dy))return 0;
  void *node=data.node;uint64_t id=data.id;
  ((unsigned (*)(void *))(base+0x3b9f0e4))(node);
  struct Widget *text=data.kind==NXS_TEXTAREA?widget_for_node(node):NULL;
  int ready=data.kind==NXS_LISTBOX?prepare_list_image(native_frame):
    text&&text->id==id&&text->frame==native_frame&&text->text_owned&&sync_text_widget(text)!=NULL;
  if(!ready||!viewport_data(native_frame,&data,0)||data.id!=id||data.node!=node){((unsigned (*)(void *))(base+0x47ba6b8))(node);return 0;}
  struct PointI point=((struct PointI (*)(const void *,struct RelativeTo))(base+0x6da35a8))(event,(struct RelativeTo){native_frame,0});
  NXSWheelEvent wheel={.size=sizeof(wheel),.x=point.x/frame_units(native_frame),.y=point.y/frame_units(native_frame),.delta_x=dx,.delta_y=dy,.modifiers=widget_modifiers(event)};
  int received,accepted;
  if(data.kind==NXS_LISTBOX)received=accepted=list_viewport_wheel(&data,&wheel);
  else {
    struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=35,
      .process=identity(),.kind=data.kind,.control=id,.x=wheel.x,.y=wheel.y,
      .minimum=dx,.maximum=dy,.modifiers=wheel.modifiers};
    struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
    received=!!response;accepted=response&&response->parts[3].x==1;
  }
  if(accepted)echo_native_viewport(native_frame);
  if(received) {
    /* Default-handler cancellation is hidden from content's defaultPrevented
     * getter, but tells APZ that the native control consumed this wheel block. */
    ((void (*)(void *,int,void *))(base+NXS_GECKO_TEXT_PREVENT_DEFAULT_OFFSET))(event,1,NULL);
    *status=1;
  }
  static __thread unsigned logged;
  if(logged++<48&&log_fd>=0)dprintf(log_fd,"%d native-wheel id=%llu axes=%.3f,%.3f mode=%u accepted=%d\n",getpid(),(unsigned long long)id,dx,dy,mode,accepted);
  ((unsigned (*)(void *))(base+0x47ba6b8))(node);
  return received;
}
static struct Detour wheel_detours[]={
  {NXS_GECKO_WHEEL_HIT_INFO_OFFSET,gecko_wheel_hit_info_bytes,wheel_hit_info,(void **)&original_wheel_hit_info}
};
