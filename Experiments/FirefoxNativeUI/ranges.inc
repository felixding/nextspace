/* Gecko range data and gesture lifecycle; NSSlider owns the widget behavior. */
#include "pinned-ranges.h"
struct GeckoDecimal {uint64_t opaque[3];};
_Static_assert(sizeof(struct GeckoDecimal)==24,"Pinned Gecko Decimal return ABI");
static struct GeckoDecimal (*decimal_from_double)(double);
static double (*decimal_to_double)(const void *);
static struct GeckoDecimal (*original_range_point)(void *,void *);
static void (*original_range_cancel)(void *,int);
static double range_number(const void *node,uintptr_t function) {
  struct GeckoDecimal value=((struct GeckoDecimal (*)(const void *))(base+function))(node);
  return decimal_to_double(&value);
}
static int native_range_frame(const void *frame) {
  if(!sliders_enabled||!frame||*(const uintptr_t *)frame!=base+0xa10b448+16||frame_kind(frame)!=NXS_SLIDER)return 0;
  const void *style=*(void *const *)((const char *)frame+32),*display=*(void *const *)((const char *)style+80);
  return ((int (*)(const void *))(base+0x6ef91c4))(frame)&&
    ((int (*)(const void *,const void *,void *))(base+0x47c1bfc))(frame,display,NULL);
}
static int range_config(struct Widget *w,struct NXSControlRequest *request) {
  if(!native_range_frame(w->frame))return 0;
  request->minimum=range_number(w->node,0x5888ddc);
  request->maximum=range_number(w->node,0x5888f34);
  request->value=range_number(w->node,0x5887588);
  w->range_step=range_number(w->node,0x5889cf4);
  return isfinite(request->minimum)&&isfinite(request->maximum)&&isfinite(request->value)&&
    isfinite(w->range_step)&&w->range_step>=0&&request->minimum<=request->maximum;
}
static void release_range_frame(void *frame) {
  reset_widget_process();struct Widget **cursor=&widgets;
  while(*cursor&&(*cursor)->frame!=frame)cursor=&(*cursor)->next;
  if(*cursor&&(*cursor)->kind==NXS_SLIDER)forget_widget(cursor);
}
static int prepare_range_image(void *frame) {
  float scale=frame?frame_scale(frame):0;
  if(!native_range_frame(frame)||!isfinite(scale)||fabsf(scale-1)>0.000001f){release_range_frame(frame);return 0;}
  struct Widget *w=bind_widget(frame);if(!w)return 0;
  int rect[4]={0};engine_frame_rect((void *)(base+0x6daae5c),frame,rect);
  double width=rect[2]/60.,height=rect[3]/60.;
  int horizontal=((int (*)(const void *))(base+0x6ef8690))(frame);
  if(width<1||height<1||width>8192||height>8192||width!=floor(width)||height!=floor(height)||horizontal!=(width>=height)){release_range_frame(frame);return 0;}
  w->width=width;w->height=height;
  struct NXSResponse *response=widget_sync(w);
  w->painted=response&&response->width==width&&response->height==height;
  if(!w->painted){release_range_frame(frame);return 0;}
  return 1;
}
static void range_key_action(void *node,const struct NXSResponse *response,int commit) {
  if(!response||!isfinite(response->parts[0].x))return;
  struct GeckoDecimal value=decimal_from_double(response->parts[0].x);
  /* The actual setter serializes/sanitizes and dispatches trusted input. */
  ((void (*)(void *,const void *,int))(base+0x588da50))(node,&value,0);
  if(commit)((void (*)(void *))(base+0x588a9c4))(node);
}
static struct NXSResponse *range_settle(struct Widget *w,struct NXSResponse *response) {
  for(int i=0;response&&response->parts[0].y&&i<100;i++) {
    struct timespec pause={.tv_nsec=2000000};nanosleep(&pause,NULL);response=widget_request(w,5,0,0,0);
  }
  return response;
}
static struct NXSResponse *range_end(struct Widget *w) {
  struct NXSResponse *response=widget_request(w,4,w->range_x,w->range_y,0);
  w->range_tracking=0;return range_settle(w,response);
}
static struct GeckoDecimal range_point(void *frame,void *event) {
  unsigned message=*(const uint16_t *)((const char *)event+18);
  if(!(*(const uint8_t *)((const char *)event+48)&1)||
     (message!=13&&message!=14&&message!=15)||!prepare_range_image(frame))return original_range_point(frame,event);
  struct Widget *w=widget_for_frame(frame);if(!w)return original_range_point(frame,event);
  struct PointI point=widget_point(w,event);w->range_x=point.x/60.;w->range_y=point.y/60.;
  struct NXSResponse *response;
  if(message==15) {
    response=widget_request(w,2,w->range_x,w->range_y,widget_modifiers(event));w->range_tracking=!!response;
    if(response)response=widget_request(w,5,0,0,0);
  } else if(w->range_tracking) {
    response=widget_request(w,message==14?4:3,w->range_x,w->range_y,widget_modifiers(event));
    if(message==14){w->range_tracking=0;response=range_settle(w,response);}
    else if(response)response=widget_request(w,5,0,0,0);
  } else return original_range_point(frame,event);
  if(!response||!isfinite(response->parts[0].x))return original_range_point(frame,event);
  double value=response->parts[0].x;
  invalidate_widget(w);
  /* Original Start/FinishRangeThumbDrag retain capture, focus bookkeeping,
   * rollback and trusted input/change. Replace only their point-to-value
   * result with the actual native slider's value; no slider geometry copied. */
  return decimal_from_double(value);
}
static void range_cancel(void *node,int user) {
  struct Widget *w=widget_for_node(node);if(w&&w->range_tracking)range_end(w);
  original_range_cancel(node,user);
}
static void prepare_range_bindings(const struct NXSResponse *response) {
  const char *flag=getenv("NEXTSPACE_FIREFOX_SLIDERS");
  if(!flag||strcmp(flag,"1")||response->parts[5].width!=1)return;
  decimal_from_double=dlsym(RTLD_DEFAULT,"_ZN5blink7Decimal10fromDoubleEd");
  decimal_to_double=dlsym(RTLD_DEFAULT,"_ZNK5blink7Decimal8toDoubleEv");
  sliders_enabled=decimal_from_double&&decimal_to_double;
}
static struct Detour range_detours[]={
  {NXS_GECKO_RANGE_POINT_OFFSET,gecko_range_point_bytes,range_point,(void **)&original_range_point},
  {NXS_GECKO_RANGE_CANCEL_OFFSET,gecko_range_cancel_bytes,range_cancel,(void **)&original_range_cancel}
};
