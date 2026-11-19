/* Bind native document/clip geometry to Gecko's real scroll-container model.
 * NSScrollView supplies measurements and bounds; no layout or clamp algorithm. */
#include "pinned-viewport.h"
struct ViewportRect {int32_t x,y,width,height;};
struct ViewportPoint {float x,y;};
static __thread int viewport_syncing;
static void (*original_viewport_reflow)(void *,void *,void *,const void *,void *);
static void *original_viewport_compute_rect,*original_viewport_layout_range;
static void (*original_viewport_scroll_impl)(void *,struct PointI,const void *,int,int);
static uint32_t (*original_viewport_selection_scroll)(void *,short,uint64_t,uint64_t,unsigned,unsigned);
static struct Widget *viewport_widget(const void *frame) {
  if(!multiline_viewport_enabled)return NULL;
  struct Widget *w=widget_for_frame(frame);
  return w&&w->kind==NXS_TEXTAREA&&w->viewport_ready&&
    *(void **)((char *)w->node+96)==frame&&native_text_frame(frame)&&
    frame_scale_supported(frame)?w:NULL;
}
static struct PointI viewport_engine_position(const void *frame) {
  const void *child=*(void *const *)((const char *)frame+NXS_GECKO_VIEWPORT_SCROLLED_FRAME_BYTE);
  if(!child)return (struct PointI){0};
  struct PointI port,position;
  memcpy(&port,(const char *)frame+NXS_GECKO_VIEWPORT_SCROLL_PORT_BYTE,sizeof(port));
  memcpy(&position,(const char *)child+NXS_GECKO_VIEWPORT_CHILD_POSITION_BYTE,sizeof(position));
  return (struct PointI){port.x-position.x,port.y-position.y};
}
static int read_native_viewport(struct Widget *w) {
  struct NXSResponse *r=widget_request(w,34,0,0,0);
  if(!r||r->parts[3].x!=1||r->size!=sizeof(*r)+sizeof(NXSTextGeometry))return 0;
  NXSTextGeometry geometry;memcpy(&geometry,r+1,sizeof(geometry));
  r=widget_request(w,32,0,0,0);
  if(!r||r->parts[3].x!=1||geometry.size!=sizeof(geometry))return 0;
  w->text_geometry=geometry;
  w->text_viewport=(NXSTextViewport){.size=sizeof(NXSTextViewport),
    .visible={r->parts[5].x,r->parts[5].y,r->parts[5].width,r->parts[5].height},
    .content={r->parts[6].width,r->parts[6].height}};
  w->viewport_ready=1;return 1;
}
static int viewport_data(const void *frame,struct FrameViewport *data,int refresh) {
  struct Widget *w=viewport_widget(frame);
  if(!w)return list_viewport(frame,data,refresh);
  void *node=w->node;uint64_t id=w->id;
  if(refresh&&!read_native_viewport(w))return 0;
  w=widget_for_node(node);if(!w||w->id!=id||w->frame!=frame||!viewport_widget(frame))return 0;
  *data=(struct FrameViewport){.frame=w->frame,.node=node,.id=id,.epoch=w->text_epoch,
    .kind=NXS_TEXTAREA,.geometry=w->text_geometry,.native=w->text_viewport};return 1;
}
static int viewport_scroll_native(const struct FrameViewport *data,double x,double y) {
  if(data->kind==NXS_LISTBOX)return list_viewport_scroll(data,x,y);
  struct Widget *w=widget_for_node(data->node);if(!w||w->id!=data->id||w->frame!=data->frame)return 0;
  struct NXSResponse *r=widget_request(w,33,x,y,0);
  if(!r||r->parts[3].x!=1)return 0;
  w=widget_for_node(data->node);return w&&w->id==data->id&&w->frame==data->frame&&read_native_viewport(w);
}
static void viewport_invalidate(const struct FrameViewport *data) {
  struct FrameViewport live;
  if(viewport_data(data->frame,&live,0)&&live.node==data->node&&live.id==data->id)
    ((void (*)(void *,unsigned,int))(base+0x6e85c5c))(live.frame,0,1);
}
static void *viewport_frame(void *frame) {
  if(!frame)return NULL;struct FrameViewport data;
  if(viewport_data(frame,&data,0))return frame;
  void *root=((void *(*)(void *,unsigned))(base+NXS_GECKO_TEXT_NEAREST_SCROLL_OFFSET))(frame,3);
  return root&&viewport_data(root,&data,0)?root:NULL;
}
static int sync_viewport_widget(struct Widget *w) {
  int initialized=w->viewport_ready;
  if(!read_native_viewport(w))return 0;
  uint32_t epoch=atomic_load(&native_host_epoch);
  /* A tab can discard its native binding without replacing the host. Restore
   * the engine's retained position for that new binding as well as a new host. */
  if(!initialized||w->text_epoch!=epoch) {
    struct PointI position=viewport_engine_position(w->frame);
    struct NXSResponse *r=widget_request(w,33,position.x/frame_units(w->frame),position.y/frame_units(w->frame),0);
    if(!r||r->parts[3].x!=1||!read_native_viewport(w))return 0;
    w->text_epoch=epoch;
  }
  return 1;
}
static void echo_native_viewport(void *frame) {
  struct FrameViewport data;
  if(viewport_syncing||!viewport_data(frame,&data,1)||data.epoch!=atomic_load(&native_host_epoch))return;
  struct PointI current=viewport_engine_position(frame);
  struct ViewportPoint offset={data.native.visible.x,data.native.visible.y};
  if(fabs(current.x-offset.x*frame_units(frame))<.001&&fabs(current.y-offset.y*frame_units(frame))<.001)return;
  void *node=data.node;
  ((unsigned (*)(void *))(base+0x3b9f0e4))(node);
  offset.x*=frame_units(frame)/60.;offset.y*=frame_units(frame)/60.;
  viewport_syncing=1;
  ((void (*)(void *,const struct ViewportPoint *,unsigned))(base+NXS_GECKO_VIEWPORT_SCROLL_CSS_OFFSET))(frame,&offset,0);
  viewport_syncing=0;
  viewport_invalidate(&data);
  ((unsigned (*)(void *))(base+0x47ba6b8))(node);
}
static void echo_text_viewport(struct Widget *w) {echo_native_viewport(w->frame);}
static void viewport_reflow(void *frame,void *context,void *output,const void *input,void *status) {
  int list=native_list_frame(frame);
  int text=multiline_viewport_enabled&&frame_kind(frame)==NXS_TEXTAREA&&native_text_frame(frame);
  void *node=list||text?*(void **)((char *)frame+24):NULL;
  if(node)((unsigned (*)(void *))(base+0x3b9f0e4))(node);
  original_viewport_reflow(frame,context,output,input,status);
  if(!node)return;
  if(*(void **)((char *)node+96)!=frame)goto done;
  struct PointI previous=viewport_engine_position(frame);
  if(!(list?prepare_list_image(frame):prepare_text_image(frame)))goto done;
  struct FrameViewport data;if(!viewport_data(frame,&data,0))goto done;
  if(!text_transaction) {
    if(!viewport_scroll_native(&data,previous.x/frame_units(frame),previous.y/frame_units(frame))||!viewport_data(frame,&data,0))goto done;
  }
  NXSRect clip=data.geometry.clip;
  struct ViewportRect port={lround(clip.x*frame_units(frame)),lround(clip.y*frame_units(frame)),lround(clip.width*frame_units(frame)),lround(clip.height*frame_units(frame))};
  memcpy((char *)frame+NXS_GECKO_VIEWPORT_SCROLL_PORT_BYTE,&port,sizeof(port));
  static __thread unsigned logged;
  if(logged++<32&&log_fd>=0)dprintf(log_fd,"%d native-viewport-reflow id=%llu kind=%d previous=%d,%d clip=%d,%d,%d,%d native=%.2f,%.2f\n",getpid(),(unsigned long long)data.id,data.kind,previous.x,previous.y,port.x,port.y,port.width,port.height,data.native.visible.x,data.native.visible.y);
  if(!text_transaction)echo_native_viewport(frame);
 done:((unsigned (*)(void *))(base+0x47ba6b8))(node);
}
/* Gecko's nontrivial nsRect return uses x8, not the C aggregate ABI. */
__attribute__((naked)) static void call_viewport_rect(void *function,const void *frame,const void *reference,void *output) {
  __asm__("mov x16,x0\nmov x0,x1\nmov x1,x2\nmov x8,x3\nbr x16");
}
__attribute__((used,noinline)) static void viewport_compute_rect_impl(const void *frame,const void *reference,struct ViewportRect *output) {
  struct FrameViewport data;
  if(viewport_data(frame,&data,0)) {*output=(struct ViewportRect){0,0,lround(data.native.content.width*frame_units(frame)),lround(data.native.content.height*frame_units(frame))};return;}
  call_viewport_rect(original_viewport_compute_rect,frame,reference,output);
}
__attribute__((naked)) static void viewport_compute_rect(const void *frame,const void *reference) {
  __asm__("mov x2,x8\nb viewport_compute_rect_impl");
}
__attribute__((used,noinline)) static void viewport_layout_range_impl(const void *frame,struct ViewportRect *output) {
  struct FrameViewport data;
  if(viewport_data(frame,&data,0)) {NXSScrollGeometry g=data.geometry;*output=(struct ViewportRect){lround(g.minimum.x*frame_units(frame)),lround(g.minimum.y*frame_units(frame)),lround((g.maximum.x-g.minimum.x)*frame_units(frame)),lround((g.maximum.y-g.minimum.y)*frame_units(frame))};return;}
  call_viewport_rect(original_viewport_layout_range,frame,NULL,output);
}
__attribute__((naked)) static void viewport_layout_range(const void *frame) {
  __asm__("mov x1,x8\nb viewport_layout_range_impl");
}
static void viewport_scroll_impl(void *frame,struct PointI position,const void *range,int origin,int script) {
  struct FrameViewport data;int bound=viewport_data(frame,&data,0);
  struct PointI requested=position;
  void *node=bound?data.node:NULL;uint64_t id=bound?data.id:0;
  int native_position=!!(bound&&viewport_syncing);
  if(node)((unsigned (*)(void *))(base+0x3b9f0e4))(node);
  if(bound&&!viewport_syncing) {
    if(viewport_scroll_native(&data,position.x/frame_units(frame),position.y/frame_units(frame))&&viewport_data(frame,&data,0)){
      position=(struct PointI){lround(data.native.visible.x*frame_units(frame)),lround(data.native.visible.y*frame_units(frame))};native_position=1;
    }
  }
  if(node&&*(void **)((char *)node+96)!=frame)goto done;
  /* The provider has already applied native pixel rounding. Gecko's usual
   * half-pixel alignment tolerance can retain a former zoom's fractional
   * phase, so supply its existing setter with the exact native point. */
  struct ViewportRect exact={position.x,position.y,0,0};
  original_viewport_scroll_impl(frame,position,native_position?&exact:range,origin,script);
  bound=node&&viewport_data(frame,&data,0)&&data.node==node&&data.id==id;
  if(bound&&!viewport_syncing){viewport_data(frame,&data,1);viewport_invalidate(&data);}
  static __thread unsigned logged;
  if(bound&&logged++<64&&log_fd>=0){struct PointI actual=viewport_engine_position(frame);dprintf(log_fd,"%d native-viewport-scroll id=%llu requested=%d,%d native=%d,%d actual=%d,%d origin=%d script=%d echo=%d\n",getpid(),(unsigned long long)data.id,requested.x,requested.y,position.x,position.y,actual.x,actual.y,origin,script,viewport_syncing);}
 done:if(node)((unsigned (*)(void *))(base+0x47ba6b8))(node);
}
static uint32_t viewport_selection_scroll(void *selection,short region,uint64_t vertical,uint64_t horizontal,unsigned flags,unsigned mode) {
  if(multiline_viewport_enabled)reset_widget_process();
  if(multiline_viewport_enabled)for(struct Widget *w=widgets;w;w=w->next) {
    if(!viewport_widget(w->frame))continue;
    void *state=text_control_state(w->node);
    void *controller=state?((void *(*)(const void *))(base+NXS_GECKO_VIEWPORT_SELECTION_CONTROLLER_OFFSET))(state):NULL;
    void *nativeSelection=controller?((void *(*)(void *,short))(base+NXS_GECKO_VIEWPORT_SELECTION_GET_OFFSET))(controller,1):NULL;
    /* The hidden Gecko editor must not reveal its differently laid-out caret.
     * The real NSTextView owns selection scrolling. Keep the engine's queued
     * event lifetime/cleanup, suppress only this owned editor's second scroll. */
    if(nativeSelection==selection)return 0;
  }
  return original_viewport_selection_scroll(selection,region,vertical,horizontal,flags,mode);
}
static struct Detour viewport_detours[]={
  {NXS_GECKO_VIEWPORT_REFLOW_OFFSET,gecko_viewport_reflow_bytes,viewport_reflow,(void **)&original_viewport_reflow},
  {NXS_GECKO_VIEWPORT_COMPUTE_RECT_OFFSET,gecko_viewport_compute_rect_bytes,viewport_compute_rect,&original_viewport_compute_rect},
  {NXS_GECKO_VIEWPORT_LAYOUT_RANGE_OFFSET,gecko_viewport_layout_range_bytes,viewport_layout_range,&original_viewport_layout_range},
  {NXS_GECKO_VIEWPORT_SCROLL_IMPL_OFFSET,gecko_viewport_scroll_impl_bytes,viewport_scroll_impl,(void **)&original_viewport_scroll_impl},
  {NXS_GECKO_VIEWPORT_SELECTION_SCROLL_OFFSET,gecko_viewport_selection_scroll_bytes,viewport_selection_scroll,(void **)&original_viewport_selection_scroll}
};
