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
    fabsf(frame_scale(frame)-1)<.000001f?w:NULL;
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
static int sync_viewport_widget(struct Widget *w) {
  if(!read_native_viewport(w))return 0;
  uint32_t epoch=atomic_load(&native_host_epoch);
  if(w->text_epoch!=epoch) {
    struct PointI position=viewport_engine_position(w->frame);
    struct NXSResponse *r=widget_request(w,33,position.x/60.,position.y/60.,0);
    if(!r||r->parts[3].x!=1||!read_native_viewport(w))return 0;
    w->text_epoch=epoch;
  }
  return 1;
}
static void echo_text_viewport(struct Widget *w) {
  if(viewport_syncing||!w->viewport_ready||!read_native_viewport(w)||w->text_epoch!=atomic_load(&native_host_epoch))return;
  struct PointI current=viewport_engine_position(w->frame);
  struct ViewportPoint offset={w->text_viewport.visible.x,w->text_viewport.visible.y};
  if(fabs(current.x-offset.x*60)<.001&&fabs(current.y-offset.y*60)<.001)return;
  void *node=w->node,*frame=w->frame;uint64_t id=w->id;
  ((unsigned (*)(void *))(base+0x3b9f0e4))(node);
  viewport_syncing=1;
  ((void (*)(void *,const struct ViewportPoint *,unsigned))(base+NXS_GECKO_VIEWPORT_SCROLL_CSS_OFFSET))(frame,&offset,0);
  viewport_syncing=0;
  w=widget_for_node(node);
  if(w&&w->id==id&&w->frame==frame&&*(void **)((char *)node+96)==frame)invalidate_widget(w);
  ((unsigned (*)(void *))(base+0x47ba6b8))(node);
}
static void viewport_reflow(void *frame,void *context,void *output,const void *input,void *status) {
  original_viewport_reflow(frame,context,output,input,status);
  if(!multiline_viewport_enabled||frame_kind(frame)!=NXS_TEXTAREA||!native_text_frame(frame))return;
  struct PointI previous=viewport_engine_position(frame);
  if(!prepare_text_image(frame))return;
  struct Widget *w=viewport_widget(frame);if(!w)return;
  struct NXSResponse *r=widget_request(w,33,previous.x/60.,previous.y/60.,0);
  if(!r||r->parts[3].x!=1||!read_native_viewport(w))return;
  NXSRect clip=w->text_geometry.clip;
  struct ViewportRect port={lround(clip.x*60),lround(clip.y*60),lround(clip.width*60),lround(clip.height*60)};
  memcpy((char *)frame+NXS_GECKO_VIEWPORT_SCROLL_PORT_BYTE,&port,sizeof(port));
  static __thread unsigned logged;
  if(logged++<32&&log_fd>=0)dprintf(log_fd,"%d native-viewport-reflow id=%llu previous=%d,%d clip=%d,%d,%d,%d native=%.2f,%.2f\n",getpid(),(unsigned long long)w->id,previous.x,previous.y,port.x,port.y,port.width,port.height,w->text_viewport.visible.x,w->text_viewport.visible.y);
  echo_text_viewport(w);
}
/* Gecko's nontrivial nsRect return uses x8, not the C aggregate ABI. */
__attribute__((naked)) static void call_viewport_rect(void *function,const void *frame,const void *reference,void *output) {
  __asm__("mov x16,x0\nmov x0,x1\nmov x1,x2\nmov x8,x3\nbr x16");
}
__attribute__((used,noinline)) static void viewport_compute_rect_impl(const void *frame,const void *reference,struct ViewportRect *output) {
  struct Widget *w=viewport_widget(frame);
  if(w) {*output=(struct ViewportRect){0,0,lround(w->text_viewport.content.width*60),lround(w->text_viewport.content.height*60)};return;}
  call_viewport_rect(original_viewport_compute_rect,frame,reference,output);
}
__attribute__((naked)) static void viewport_compute_rect(const void *frame,const void *reference) {
  __asm__("mov x2,x8\nb viewport_compute_rect_impl");
}
__attribute__((used,noinline)) static void viewport_layout_range_impl(const void *frame,struct ViewportRect *output) {
  struct Widget *w=viewport_widget(frame);
  if(w) {NXSTextGeometry g=w->text_geometry;*output=(struct ViewportRect){lround(g.minimum.x*60),lround(g.minimum.y*60),lround((g.maximum.x-g.minimum.x)*60),lround((g.maximum.y-g.minimum.y)*60)};return;}
  call_viewport_rect(original_viewport_layout_range,frame,NULL,output);
}
__attribute__((naked)) static void viewport_layout_range(const void *frame) {
  __asm__("mov x1,x8\nb viewport_layout_range_impl");
}
static void viewport_scroll_impl(void *frame,struct PointI position,const void *range,int origin,int script) {
  struct Widget *w=viewport_widget(frame);
  struct PointI requested=position;
  void *node=w?w->node:NULL;uint64_t id=w?w->id:0;
  int native_position=!!(w&&viewport_syncing);
  if(node)((unsigned (*)(void *))(base+0x3b9f0e4))(node);
  if(w&&!viewport_syncing) {
    struct NXSResponse *r=widget_request(w,33,position.x/60.,position.y/60.,0);
    if(r&&r->parts[3].x==1){position=(struct PointI){lround(r->parts[5].x*60),lround(r->parts[5].y*60)};native_position=1;}
  }
  /* The provider has already applied native pixel rounding. Gecko's usual
   * half-pixel alignment tolerance can retain a former zoom's fractional
   * phase, so supply its existing setter with the exact native point. */
  struct ViewportRect exact={position.x,position.y,0,0};
  original_viewport_scroll_impl(frame,position,native_position?&exact:range,origin,script);
  w=node?widget_for_node(node):NULL;
  if(w&&(w->id!=id||w->frame!=frame||*(void **)((char *)node+96)!=frame))w=NULL;
  if(w&&!viewport_syncing){read_native_viewport(w);invalidate_widget(w);}
  static __thread unsigned logged;
  if(w&&logged++<64&&log_fd>=0){struct PointI actual=viewport_engine_position(frame);dprintf(log_fd,"%d native-viewport-scroll id=%llu requested=%d,%d native=%d,%d actual=%d,%d origin=%d script=%d echo=%d\n",getpid(),(unsigned long long)w->id,requested.x,requested.y,position.x,position.y,actual.x,actual.y,origin,script,viewport_syncing);}
  if(node)((unsigned (*)(void *))(base+0x47ba6b8))(node);
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
