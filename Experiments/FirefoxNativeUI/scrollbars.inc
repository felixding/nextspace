/* Original Gecko scroll models bound to the shared, original NSScroller.
 * No scrollbar drawing, hit-testing, tracking or repeat policy lives here. */
#include "pinned-scrollbars.h"
#include "pinned-scroller-policy.h"
static int document_scroller_policy_installed;
struct DocumentScroller {
  struct DocumentScroller *next;
  void *frame,*scroll;
  struct NXSScrollerBinding binding;
  struct NXSBitmapBinding bitmap;
  double minimum,length,total,page;
};
static struct DocumentScroller *document_scrollers,*document_scroller_active;
static int document_scrollbars_enabled;
static uint32_t document_layout_epoch;
static struct NXSRectD document_native_clip;
static double document_native_width;
static __thread void *document_scroller_event;
static int (*original_scrollbar_side)(const void *),(*original_scrollbar_side_thunk)(const void *);
static uint64_t (*original_scrollbar_size)(void *,void *,unsigned,void *);
static uint32_t (*original_scrollbar_event)(void *,void *,void *,int *);
static int (*original_scrollbar_overlay)(const void *);
static int (*original_scrollbar_thickness)(void *,const void *,unsigned,unsigned);

/* Built-in pages and their shared UI are hosted in the parent process.
 * Scrollbar ownership is a control policy, independent of retained toolbar
 * buttons/tabs. All enabled scrollbars reuse this same native binding. */
static int native_scroller_process(void)
{return native_web_process()||(frontend_requested&&getenv("NEXTSPACE_FIREFOX_WEBUI_PREFIX"));}

static void document_scroller_layout_echo(void)
{
  if(!native_scroller_process())return;
  int right=document_native_clip.x<128-document_native_clip.x-document_native_clip.width;
  /* Gecko also inlines its original side-pref branch in scroll reflow.
     Every enabled process takes that layout from the original NSScrollView. */
  atomic_store_explicit((_Atomic int *)(base+NXS_GECKO_SCROLLBAR_SIDE_CACHE),right?2:3,memory_order_relaxed);
  if(!document_scroller_policy_installed) {
    /* Gecko inlines its non-root direction shortcut in reflow as well. All
     * instances use the same provider policy; text direction stays untouched. */
    for(unsigned i=0;i<sizeof(gecko_scroller_policy_sites)/sizeof(*gecko_scroller_policy_sites);i++) {
      uintptr_t address=base+gecko_scroller_policy_sites[i].offset;
      uint32_t branch=0x14000000u|((gecko_scroller_policy_sites[i].target-gecko_scroller_policy_sites[i].offset)/4);
      writable((void *)address,4,PROT_READ|PROT_WRITE|PROT_EXEC);
      atomic_store_explicit((_Atomic uint32_t *)address,branch,memory_order_relaxed);
      __builtin___clear_cache((char *)address,(char *)address+4);
      writable((void *)address,4,PROT_READ|PROT_EXEC);
    }
    document_scroller_policy_installed=1;
  }
}

static int document_scroller_layout(void)
{
  uint32_t epoch=atomic_load(&native_host_epoch);
  if(document_layout_epoch==epoch&&document_native_width>0){document_scroller_layout_echo();return 1;}
  struct NXSRectD clip;
  if(!native_scroller_layout(128,128,&clip))return 0;
  struct NXSRequest request={.magic=NXS_CHROMIUM_MAGIC,.operation=7,.process=identity()};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  if(!response||response->parts[0].width<=0)return 0;
  document_native_clip=clip;document_native_width=response->parts[0].width;
  document_layout_epoch=atomic_load(&native_host_epoch);document_scroller_layout_echo();return 1;
}
static void *document_scrollbar_frame(void *frame)
{
  if(!document_scrollbars_enabled||!native_scroller_process())return NULL;
  for(unsigned n=0;frame&&n<64;n++,frame=*(void **)((char *)frame+48))
    if(*(uintptr_t *)frame==base+0xa118910+16)return frame;
  return NULL;
}
static struct DocumentScroller *document_scroller_find(void *frame)
{
  for(struct DocumentScroller *bar=document_scrollers;bar;bar=bar->next)
    if(bar->frame==frame)return bar;
  return NULL;
}
static void *document_scrollbar_container(void *frame)
{
  void *mediator=((void *(*)(void *))(base+NXS_GECKO_SCROLLBAR_MEDIATOR))(frame);
  if(!mediator)return NULL;
  /* Gecko's scroll-container query accepts derived frames. Cross-check the
     actual scrollbar mediator so a different ancestor can't receive input. */
  void *scroll=((void *(*)(void *,unsigned))(base+NXS_GECKO_TEXT_NEAREST_SCROLL_OFFSET))(frame,3);
  return scroll&&(char *)scroll+168==mediator?scroll:NULL;
}
static struct NXSResponse *document_scroller_sync(struct DocumentScroller *bar,int pixels)
{
  struct ViewportRect range={0},port={0};int rect[4]={0};
  call_viewport_rect((void *)(base+NXS_GECKO_VIEWPORT_LAYOUT_RANGE_OFFSET),bar->scroll,NULL,&range);
  memcpy(&port,(char *)bar->scroll+NXS_GECKO_VIEWPORT_SCROLL_PORT_BYTE,sizeof(port));
  engine_frame_rect((void *)(base+0x6daae5c),bar->frame,rect);
  double units=frame_units(bar->scroll);int horizontal=bar->binding.horizontal;
  struct PointI position=viewport_engine_position(bar->scroll);
  bar->minimum=(horizontal?range.x:range.y)/units;
  bar->page=(horizontal?port.width:port.height)/units;
  bar->total=bar->page+(horizontal?range.width:range.height)/units;
  bar->length=(horizontal?rect[2]:rect[3])/frame_units(bar->frame);
  double value=(horizontal?position.x:position.y)/units-bar->minimum;
  if(!native_scroller_prepare(&bar->binding,frame_scale(bar->frame)))return NULL;
  return native_scroller_model(&bar->binding,bar->length,bar->total,bar->page,value,pixels);
}
static struct DocumentScroller *document_scroller_bind(void *frame,unsigned appearance)
{
  void *bar_frame=document_scrollbar_frame(frame);
  if(!bar_frame)return NULL;
  struct DocumentScroller *bar=document_scroller_find(bar_frame);
  if(!bar) {
    void *scroll=document_scrollbar_container(bar_frame);
    if(!scroll||!ensure_widget_lifetime()||!ensure_text_watch())return NULL;
    bar=calloc(1,sizeof(*bar));if(!bar)return NULL;
    bar->frame=bar_frame;bar->scroll=scroll;
    bar->binding=(struct NXSScrollerBinding){.control=++next_widget,
      .horizontal=appearance==20||appearance==26||appearance==28};
    bar->next=document_scrollers;document_scrollers=bar;
  }
  struct NXSResponse *response=document_scroller_sync(bar,1);
  if(response)native_bitmap_store(&bar->bitmap,response);
  return native_bitmap_available(&bar->bitmap)?bar:NULL;
}
static int document_scroller_owned(void *frame,unsigned appearance)
{
  return appearance>=20&&appearance<=30&&document_scroller_bind(frame,appearance)!=NULL;
}
static int document_scroller_draw(void *target,void *frame,unsigned appearance,const struct RectF *area)
{
  struct DocumentScroller *bar=document_scroller_bind(frame,appearance);if(!bar)return 0;
  /* The complete native bar includes its thumb and arrows. Original anonymous
     Gecko children remain layout/event targets but do not paint a second bar. */
  if(frame!=bar->frame)return 1;
  double length=bar->binding.horizontal?area->width:area->height;
  if(lround(length)!=lround(bar->length)) {
    bar->length=length;
    struct PointI position=viewport_engine_position(bar->scroll);
    double value=(bar->binding.horizontal?position.x:position.y)/frame_units(bar->scroll)-bar->minimum;
    if(!native_bitmap_store(&bar->bitmap,native_scroller_model(&bar->binding,length,bar->total,bar->page,value,1)))return 0;
  }
  if(bar->bitmap.width!=lround(area->width)||bar->bitmap.height!=lround(area->height))return 0;
  draw_bitmap(target,area,bar->bitmap.pixels,bar->bitmap.width,bar->bitmap.height);
  if(log_fd>=0&&getenv("NEXTSPACE_FIREFOX_TRACE_SCALE"))
    dprintf(log_fd,"%d native-document-scroller id=%llu horizontal=%d rect=%.9g,%.9g %.9gx%.9g total=%.9g page=%.9g\n",
      getpid(),(unsigned long long)bar->binding.control,bar->binding.horizontal,area->x,area->y,area->width,area->height,bar->total,bar->page);
  return 1;
}
static int document_scrollbar_side(const void *frame)
{
  if(document_scrollbars_enabled&&native_scroller_process()&&document_scroller_layout())
    return document_native_clip.x<128-document_native_clip.x-document_native_clip.width;
  return original_scrollbar_side(frame);
}
static int document_scrollbar_side_thunk(const void *mediator)
{
  if(document_scrollbars_enabled&&native_scroller_process())return document_scrollbar_side((const char *)mediator-168);
  return original_scrollbar_side_thunk(mediator);
}
static uint64_t document_scrollbar_size(void *self,void *context,unsigned appearance,void *frame)
{
  uint64_t size=original_scrollbar_size(self,context,appearance,frame);
  if(document_scrollbars_enabled&&native_scroller_process()&&document_scroller_layout()&&frame) {
    uint32_t thickness=lround(document_native_width*frame_scale(frame));
    if(appearance==21||appearance==27||appearance==29)size=(size&0xffffffff00000000ull)|thickness;
    if(appearance==20||appearance==26||appearance==28)size=(size&0xffffffffull)|((uint64_t)thickness<<32);
  }
  return size;
}
static int document_scrollbar_overlay(const void *context)
{
  if(document_scrollbars_enabled&&native_scroller_process()&&document_scroller_layout())
    return document_native_clip.width>=128&&document_native_clip.height>=128;
  return original_scrollbar_overlay(context);
}
static int document_scrollbar_thickness(void *self,const void *context,unsigned style,unsigned overlay)
{
  if(document_scrollbars_enabled&&native_scroller_process()&&document_scroller_layout()) {
    int units=*(const int *)((const char *)context+200);
    if(units>0)return lround(document_native_width*60./units);
  }
  return original_scrollbar_thickness(self,context,style,overlay);
}
static void document_scroller_apply(struct DocumentScroller *bar)
{
  uint64_t id=bar->binding.control;void *frame=bar->frame,*scroll=bar->scroll;
  struct NXSResponse *response=native_scroller_input(&bar->binding,5,0,0,0);
  if(!response||!isfinite(response->parts[0].x))return;
  struct PointI position=viewport_engine_position(scroll);double units=frame_units(scroll);
  struct ViewportPoint css={position.x/60.f,position.y/60.f};
  if(bar->binding.horizontal)css.x=(response->parts[0].x+bar->minimum)*units/60.;
  else css.y=(response->parts[0].x+bar->minimum)*units/60.;
  ((void (*)(void *,const struct ViewportPoint *,unsigned))(base+NXS_GECKO_VIEWPORT_SCROLL_CSS_OFFSET))(scroll,&css,0);
  bar=document_scroller_find(frame);
  if(bar&&bar->binding.control==id)((void (*)(void *,unsigned,int))(base+0x6e85c5c))(frame,0,1);
}
static int document_scroller_pointer(void *frame,void *event,int *status)
{
  if(!document_scrollbars_enabled||!(*(const uint8_t *)((char *)event+48)&1))return 0;
  unsigned message=*(const uint16_t *)((char *)event+18);
  if(message!=13&&message!=14&&message!=15)return 0;
  if(message!=13&&*(const int16_t *)((char *)event+152)!=0)return 0;
  struct DocumentScroller *bar=document_scroller_active;
  if(message==15) {
    void *bar_frame=document_scrollbar_frame(frame);if(!bar_frame)return 0;
    int horizontal=((int (*)(const void *))(base+NXS_GECKO_SCROLLBAR_ORIENTATION))(bar_frame);
    bar=document_scroller_bind(bar_frame,horizontal?20:21);if(!bar)return 0;
    document_scroller_active=bar;
    ((void (*)(void *,unsigned,void *))(base+NXS_GECKO_TEXT_CAPTURE_OFFSET))(*(void **)((char *)bar->frame+24),1,NULL);
  }
  if(!bar)return 0;
  struct PointI point=((struct PointI (*)(const void *,struct RelativeTo))(base+0x6da35a8))(event,(struct RelativeTo){bar->frame,0});
  struct NXSResponse *response=native_scroller_input(&bar->binding,message==15?2:message==14?4:3,
    point.x/frame_units(bar->frame),point.y/frame_units(bar->frame),widget_modifiers(event));
  if(message==14)for(unsigned i=0;response&&response->parts[0].y&&i<100;i++) {
    struct timespec pause={.tv_nsec=2000000};nanosleep(&pause,NULL);
    response=native_scroller_input(&bar->binding,5,0,0,0);
  }
  document_scroller_apply(bar);
  if(message==14) {
    document_scroller_active=NULL;
    ((void (*)(void *,unsigned,void *))(base+NXS_GECKO_TEXT_CAPTURE_OFFSET))(NULL,1,NULL);
  }
  ((void (*)(void *,int,void *))(base+NXS_GECKO_TEXT_PREVENT_DEFAULT_OFFSET))(event,1,NULL);
  *status=1;return 1;
}
static uint32_t document_scrollbar_event(void *frame,void *context,void *event,int *status)
{
  if(document_scroller_event==event){*status=1;return 0;}
  if(document_scroller_pointer(frame,event,status)){document_scroller_event=event;return 0;}
  return original_scrollbar_event(frame,context,event,status);
}
static int document_scroller_pointer_pre(void *frame,void *event,int *status)
{
  /* Original anonymous thumb/button frames can consume their event before
     nsSliderFrame sees it. Use the shared original pre-dispatch hook, after
     its bookkeeping, so NSScroller receives every part of the gesture. */
  if(!document_scroller_pointer(frame,event,status))return 0;
  document_scroller_event=event;return 1;
}
static int document_scroller_pointer_post(void *frame,void *event,int *status)
{
  int handled=document_scroller_event==event;
  document_scroller_event=NULL;
  if(handled){*status=1;return 1;}
  return document_scroller_active&&document_scroller_pointer(frame,event,status);
}
static void document_scroller_notification(void)
{if(document_scroller_active)document_scroller_apply(document_scroller_active);}
static int document_scrollers_exist(void){return document_scrollers!=NULL;}
static void document_scroller_forget(void *frame)
{
  struct DocumentScroller **cursor=&document_scrollers;
  while(*cursor) {
    struct DocumentScroller *bar=*cursor;
    if(bar->frame!=frame&&bar->scroll!=frame){cursor=&bar->next;continue;}
    if(document_scroller_active==bar) {
      native_scroller_input(&bar->binding,4,0,0,0);document_scroller_active=NULL;
      ((void (*)(void *,unsigned,void *))(base+NXS_GECKO_TEXT_CAPTURE_OFFSET))(NULL,1,NULL);
    }
    native_scroller_retire(&bar->binding);native_bitmap_retire(&bar->bitmap);
    *cursor=bar->next;free(bar);
  }
}
static void document_scroller_release_context(void *context)
{
  struct DocumentScroller *bar=document_scrollers;
  while(bar) {struct DocumentScroller *next=bar->next;
    if(*(void **)((char *)bar->frame+40)==context)document_scroller_forget(bar->frame);
    bar=next;
  }
}
static struct Detour document_scroller_detours[]={
  {NXS_GECKO_SCROLLBAR_SIDE,gecko_scrollbar_side_bytes,document_scrollbar_side,(void **)&original_scrollbar_side},
  {NXS_GECKO_SCROLLBAR_SIDE_THUNK,gecko_scrollbar_side_thunk_bytes,document_scrollbar_side_thunk,(void **)&original_scrollbar_side_thunk},
  {NXS_GECKO_SCROLLBAR_SIZE,gecko_scrollbar_size_bytes,document_scrollbar_size,(void **)&original_scrollbar_size},
  {NXS_GECKO_SCROLLBAR_EVENT,gecko_scrollbar_event_bytes,document_scrollbar_event,(void **)&original_scrollbar_event},
  {NXS_GECKO_SCROLLBAR_OVERLAY,gecko_scrollbar_overlay_bytes,document_scrollbar_overlay,(void **)&original_scrollbar_overlay},
  {NXS_GECKO_SCROLLBAR_THICKNESS,gecko_scrollbar_thickness_bytes,document_scrollbar_thickness,(void **)&original_scrollbar_thickness}
};
static int prepare_document_scrollers(void)
{
  const char *enabled=getenv("NEXTSPACE_FIREFOX_SCROLLERS");
  if(!enabled||strcmp(enabled,"1"))return 1;
  for(unsigned i=0;i<sizeof(gecko_scroller_policy_sites)/sizeof(*gecko_scroller_policy_sites);i++)
    if(*(const uint32_t *)(base+gecko_scroller_policy_sites[i].offset)!=gecko_scroller_policy_sites[i].original)return 0;
  if(memcmp((void *)(base+NXS_GECKO_SCROLLBAR_MEDIATOR),gecko_scrollbar_mediator_bytes,20)||
     memcmp((void *)(base+NXS_GECKO_TEXT_NEAREST_SCROLL_OFFSET),gecko_text_nearest_scroll_bytes,20)||
     memcmp((void *)(base+NXS_GECKO_SCROLLBAR_ORIENTATION),gecko_scrollbar_orientation_bytes,20)||
     memcmp((void *)(base+NXS_GECKO_SCROLLBAR_SIDE_CACHE_LOAD),gecko_scrollbar_side_cache_load_bytes,20)||
     !guard_viewport_calls()||
     (!radio_groups_enabled&&!prepare_detours(radio_pointer_detours,sizeof(radio_pointer_detours)/sizeof(*radio_pointer_detours)))||
     !prepare_detours(document_scroller_detours,sizeof(document_scroller_detours)/sizeof(*document_scroller_detours)))return 0;
  /* Layout already queries the native measurement when it is needed. A
   * transient bootstrap RPC failure must not disable every browser binding. */
  document_scrollbars_enabled=1;return 1;
}
