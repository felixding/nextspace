/* Gecko model/event adapter only. NSButton owns button/checkbox/radio rendering,
 * focus, tracking and key interpretation in the independent NativeUI host. */
#include "pinned-input.h"
#include "pinned-multiline.h"
#include "pinned-html-buttons.h"
struct GeckoError {uint32_t result,padding;uint64_t extra;};
_Static_assert(sizeof(struct GeckoError)==16,"Pinned release ErrorResult ABI");
static void clear_text_error(struct GeckoError *);
#include "../../Libraries/NativeUI/Bridge/ControlActions.inc"
struct Widget {
  struct Widget *next;
  void *frame,*node;
  uint64_t id;
  uint64_t radio_owner,radio_member;
  unsigned radio_clicks;
  struct NXSRectD radio_rect;
  int kind,painted;
  double width,height,actions;
  uint32_t *button_pixels;int button_width,button_height,button_label_owned,button_focused;
  double button_preferred_width,button_preferred_height;
  int button_reflow_pending;
  char *button_model_title;
  int button_model_changed;
  double range_step,range_x,range_y;int range_tracking,range_keypress;
  int text_owned,text_tracking;
  double text_width,text_height;
  NXSTextGeometry text_geometry;
  NXSTextViewport text_viewport;
  uint32_t text_epoch;
  int viewport_ready;
};
struct PointI {int x,y;};
struct RelativeTo {void *frame;int viewport;};
static int widgets_enabled,buttons_enabled,sliders_enabled,texts_enabled,widget_notifier=-1;
static int radio_groups_enabled,labels_enabled;
static int multiline_enabled;
static int multiline_viewport_enabled;
static int wheel_enabled;
static int frontend_requested;
static int text_command_reporting;
static int application_commands;
static int application_menu_keys;
static unsigned widget_pointer_capabilities;
static pid_t widget_pid;
static uint64_t next_widget;
static struct Widget *widgets,*active_widget;
static struct {void *event,*node;uint64_t control;int allowed,radio;struct NXSControlAction action;} click_gate;
static struct {void *node,*context;uint64_t control;int active;} radio_pointer_source;
static double preferred_width[4],preferred_height[4];
static __thread int metric_probe;
static void reset_widget_process(void);
static void gecko_radio_reset_process(void);
static struct NXSResponse *gecko_radio_request(struct Widget *,unsigned,double,double,unsigned);
static void *gecko_radio_pointer_target(void *,uint64_t);
static void gecko_radio_pointer_complete(void *,uint64_t);
static void gecko_radio_pointer_capture(void *);
static void gecko_radio_pointer_release_context(void *);
static uint32_t (*original_radio_pre_event)(void *,void *,void *,void *,void *,int *,void *);
static uint32_t gecko_radio_key(struct Widget *,void *,void *);
static char *utf8_text(const uint16_t *,uint32_t);
static int prepare_button_image(void *);
static struct Widget *bind_input_widget(void *);
static int native_button_frame(const void *);
static struct Widget *html_button_owner(const void *);
static int button_cache_update(struct Widget *,const struct NXSResponse *);
static int button_cache_available(const struct Widget *);
static char *button_title(const struct Widget *);
static int native_range_frame(const void *);
static int prepare_range_image(void *);
static void release_range_frame(void *);
static int range_config(struct Widget *,struct NXSControlRequest *);
static void range_key_action(void *,const struct NXSResponse *,int);
static struct NXSResponse *range_end(struct Widget *);
static void prepare_range_bindings(const struct NXSResponse *);
static int native_text_frame(const void *);
static int frontend_text_frame(const void *);
static int prepare_text_image(void *);
static struct NXSResponse *sync_text_widget(struct Widget *);
static int sync_viewport_widget(struct Widget *);
static void echo_text_viewport(struct Widget *);
static void remove_text_watch(void);
static int dispatch_text_key(void *,void *,void *);
static int text_modifier_event(const void *);
static int text_kind(int);
static int native_wheel_post(void *,void *,int *);
static void *text_pointer_frame(void *);
static uint32_t text_pointer_post(void *,void *,void *,void *,int *,void *,void *);
static int (*original_draw_target)(void *,void *,void *,unsigned,const void *,int);
static int (*original_default_size)(void *);
static int (*original_intrinsic)(void *,const void *,int);
static uint32_t (*original_input_post)(void *,void *);
static uint32_t (*original_post_event)(void *,void *,void *,void *,int *,void *);
static uint32_t (*original_click_events)(void *,void *,void *,int *,void *,void *);
static void (*original_frame_destroy)(void *,void *);
static void (*original_freeze)(void *,int);
static void (*original_active)(void *,int);

static int html_button_node(const void *node) {
  return buttons_enabled&&node&&*(const uintptr_t *)node==base+0xa008c98+16;
}
static int node_kind(const void *node) {
  if(!native_web_process())return 0;
  if(html_button_node(node))return NXS_BUTTON;
  if(node&&multiline_enabled&&*(const uintptr_t *)node==base+NXS_GECKO_TEXTAREA_VTABLE_OFFSET+16)return NXS_TEXTAREA;
  if(!node||*(const uintptr_t *)node!=base+0xa00fc30+16)return 0;
  unsigned type=*((const unsigned char *)node+144);
  return type==130?NXS_CHECKBOX:type==141?NXS_RADIO:
    buttons_enabled&&(type==129||type==136||type==143)?NXS_BUTTON:
    sliders_enabled&&type==148?NXS_SLIDER:
    texts_enabled&&type==145?NXS_TEXTFIELD:texts_enabled&&type==140?NXS_PASSWORD:0;
}
static int frame_kind(const void *frame) {
  return frame?node_kind(*(void *const *)((const char *)frame+24)):0;
}
static struct Widget *widget_for_node(const void *node) {
  reset_widget_process();
  for(struct Widget *w=widgets;w;w=w->next)if(w->node==node)return w;
  return NULL;
}
static struct Widget *widget_for_frame(const void *frame) {
  reset_widget_process();
  for(struct Widget *w=widgets;w;w=w->next)if(w->frame==frame)return w;
  return NULL;
}
static int widget_focused(const struct Widget *w) {
  void *manager=*(void **)(base+0xa439c38);
  return manager&&*(void **)((char *)manager+128)==w->node;
}
static void invalidate_widget(struct Widget *w) {
  ((void (*)(void *,unsigned,int))(base+0x6e85c5c))(w->frame,0,1);
}
static struct NXSResponse *widget_request(struct Widget *w,unsigned operation,double x,double y,unsigned modifiers) {
  if(w->kind==NXS_RADIO&&radio_groups_enabled)return gecko_radio_request(w,operation,x,y,modifiers);
  uint64_t state=((uint64_t (*)(const void *,unsigned))(base+0x6a7dc9c))(w->frame,w->kind==NXS_BUTTON?10:w->kind==NXS_SLIDER?19:w->kind==NXS_CHECKBOX?4:5);
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,
    .process=identity(),.kind=w->kind,.control=w->id,.width=w->width,.height=w->height,
    .maximum=1,.state=(w->kind==NXS_CHECKBOX&&(state&64))?-1:!!(state&32),
    .enabled=!(state&16),.x=x,.y=y,.modifiers=modifiers};
  if(w->kind==NXS_SLIDER&&operation==1&&!range_config(w,&request))return NULL;
  char *title=w->kind==NXS_BUTTON&&operation==1?button_title(w):NULL;
  if(w->kind==NXS_BUTTON&&operation==1&&!title)return NULL;
  size_t length=title?strlen(title):0;
  request.text_size=length;
  size_t size=sizeof(request)+length;unsigned char *data=malloc(size);
  if(!data){free(title);return NULL;}
  memcpy(data,&request,sizeof(request));if(length)memcpy(data+sizeof(request),title,length);
  struct NXSResponse *response=exchange_bytes(data,size);free(data);
  if(response&&title&&(!w->button_model_title||strcmp(w->button_model_title,title))) {
    free(w->button_model_title);w->button_model_title=title;title=NULL;w->button_model_changed=1;
  }
  free(title);return response;
}
static struct NXSResponse *widget_sync(struct Widget *w) {
  if(w->kind==NXS_RADIO&&radio_groups_enabled)return widget_request(w,1,0,0,0);
  if(text_kind(w->kind))return sync_text_widget(w);
  if(w->button_reflow_pending)return widget_request(w,5,0,0,0);
  struct NXSResponse *response=widget_request(w,1,0,0,0);
  if(!response)return NULL;
  if(w->kind==NXS_SLIDER&&response->parts[5].x!=w->range_step) {
    struct NXSControlStepRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=10,
      .process=identity(),.kind=w->kind,.control=w->id,.step=w->range_step};
    response=exchange_bytes(&request,sizeof(request));
    if(!response||response->parts[5].x!=w->range_step)return NULL;
  }
  int focused=widget_focused(w);
  if(!!response->parts[3].y!=focused) {
    struct NXSControlInputRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=7,
      .process=identity(),.kind=w->kind,.control=w->id,.focused=focused};
    response=exchange_bytes(&request,sizeof(request));
    if(!response)return NULL;
    response=widget_request(w,1,0,0,0);
  }
  if(response&&w->kind==NXS_BUTTON&&!button_cache_update(w,response))return NULL;
  return response;
}
static void drain_widget_notifier(void) {
  if(widget_notifier>=0){uint64_t count;while(read(widget_notifier,&count,sizeof(count))==sizeof(count)){};}
}
static void reset_widget_process(void) {
  if(widget_pid!=getpid()) {
    gecko_radio_reset_process();
    remove_text_watch();
    while(widgets){struct Widget *next=widgets->next;free(widgets->button_pixels);free(widgets->button_model_title);free(widgets);widgets=next;}
    active_widget=NULL;memset(&click_gate,0,sizeof(click_gate));next_widget=0;
    if(widget_notifier>=0)close(widget_notifier);
    widget_notifier=-1;widget_pid=getpid();
  }
}
static int ensure_widget_lifetime(void) {
  reset_widget_process();
  if(widget_notifier>=0)return 1;
  int descriptor=eventfd(0,EFD_CLOEXEC|EFD_NONBLOCK);if(descriptor<0)return 0;
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=15,.process=identity()};
  struct NXSResponse *response=exchange_bytes_descriptor(&request,sizeof(request),descriptor);
  if(!response||response->parts[3].x!=1){close(descriptor);return 0;}
  widget_notifier=descriptor;note("Gecko native object lifetime descriptor registered");return 1;
}
static float frame_scale(const void *frame) {
  const void *context=*(void *const *)((const char *)frame+40),*style=*(void *const *)((const char *)frame+32);
  int units=*(const int *)((const char *)context+200);
  return units>0?(60.f/units)*(*(const float *)((const char *)style+228)):0;
}
/* nsRect is returned indirectly in x8 in this binary. Forward to Gecko's
 * existing frame-rectangle union; do not duplicate frame/transform geometry. */
__attribute__((naked)) static void engine_frame_rect(void *function,void *frame,void *output) {
  __asm__("mov x16,x0\nmov x0,x1\nmov x8,x2\nmov w2,wzr\nbr x16");
}
static struct Widget *bind_widget(void *frame) {
  struct Widget *existing=widget_for_frame(frame);if(existing)return existing;
  int kind=frame_kind(frame);if(!widgets_enabled||!kind)return NULL;
  float scale=frame_scale(frame);if(!isfinite(scale)||fabsf(scale-1)>0.000001f)return NULL;
  int native;
  if(kind==NXS_BUTTON)native=native_button_frame(frame);
  else if(kind==NXS_SLIDER)native=native_range_frame(frame);
  else if(text_kind(kind))native=native_text_frame(frame);
  else {metric_probe=1;native=original_intrinsic(frame,NULL,0);metric_probe=0;}
  if(!native||!ensure_widget_lifetime())return NULL;
  int rectangle[4]={0};engine_frame_rect((void *)(base+0x6daae5c),frame,rectangle);
  double width=rectangle[2]/60.,height=rectangle[3]/60.;
  /* A native button can be measured before its first reflow. This viewport
   * only hosts the model probe; the provider's cellSize supplies the metrics. */
  if(kind==NXS_BUTTON&&(width<1||height<1))width=height=1;
  if(!isfinite(width)||!isfinite(height)||width<1||height<1||width>8192||height>8192)return NULL;
  struct Widget *w=calloc(1,sizeof(*w));if(!w)return NULL;
  w->frame=frame;w->node=*(void **)((char *)frame+24);w->id=++next_widget;w->kind=kind;
  w->width=width;w->height=height;w->next=widgets;widgets=w;
  w->painted=widget_sync(w)!=NULL;
  if(kind==NXS_BUTTON||kind==NXS_SLIDER)w->painted=0;
  if(log_fd>=0)dprintf(log_fd,"%d native-widget bound before paint id=%llu kind=%d\n",getpid(),(unsigned long long)w->id,w->kind);
  return w;
}
static int draw_text_image(void *target,void *frame,const struct RectF *area) {
  struct Widget *w=widget_for_frame(frame);
  if(!w||!w->text_owned||!button_cache_available(w))return 0;
  /* Focus may change without rebuilding Gecko's retained display list. Refresh
   * native focus and pixels only; do not mutate engine scroll state in paint. */
  int focused=widget_focused(w);
  if(w->button_focused!=focused) {
    struct NXSControlInputRequest focus={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=7,
      .process=identity(),.kind=w->kind,.control=w->id,.focused=focused};
    if(!exchange_bytes(&focus,sizeof(focus))||!button_cache_update(w,widget_request(w,5,0,0,0)))return 0;
  }
  /* Parent frames may have fractional bounds. Native readback owns pixel
   * rounding; transport its actual bitmap without scaling or rounding it again. */
  if(!frontend_text_frame(frame)&&
     (w->button_width!=lround(area->width)||w->button_height!=lround(area->height)))return 0;
  draw_bitmap(target,area,w->button_pixels,w->button_width,w->button_height);w->painted=1;
  if(log_fd>=0)dprintf(log_fd,"%d native-text id=%llu kind=%d size=%dx%d\n",getpid(),(unsigned long long)w->id,w->kind,w->button_width,w->button_height);
  return 1;
}
static int draw_widget(void *self,void *target,void *frame,unsigned appearance,const void *rect,int overflow) {
  int kind=frame_kind(frame);
  int is_text=text_kind(kind);
  if(is_text&&(!native_text_frame(frame)||!widget_for_frame(frame)||!widget_for_frame(frame)->text_owned))
    return original_draw_target(self,target,frame,appearance,rect,overflow);
  if(kind==NXS_SLIDER&&!prepare_range_image(frame))
    return original_draw_target(self,target,frame,appearance,rect,overflow);
  if(!widgets_enabled||!kind||(!is_text&&appearance!=(unsigned)(kind==NXS_BUTTON?10:kind==NXS_SLIDER?19:kind==NXS_CHECKBOX?4:5))||fabsf(frame_scale(frame)-1)>0.000001f||
     (kind==NXS_SLIDER&&!native_range_frame(frame)))
    return original_draw_target(self,target,frame,appearance,rect,overflow);
  const void *context=*(void *const *)((const char *)frame+40);
  double units=*(const int *)((const char *)context+200);
  struct RectF area=((struct RectF (*)(const void *,double,const void *))(base+0x6db633c))(rect,units,target);
  if(!isfinite(area.width)||!isfinite(area.height)||area.width<1||area.height<1||area.width>8192||area.height>8192)
    return original_draw_target(self,target,frame,appearance,rect,overflow);
  struct Widget *w=widget_for_frame(frame);
  if(!w) {
    if(!ensure_widget_lifetime())return original_draw_target(self,target,frame,appearance,rect,overflow);
    w=calloc(1,sizeof(*w));if(!w)return original_draw_target(self,target,frame,appearance,rect,overflow);
    w->frame=frame;w->node=*(void **)((char *)frame+24);w->id=++next_widget;w->kind=kind;
    w->next=widgets;widgets=w;
  }
  w->width=area.width;w->height=area.height;
  if(is_text) {
    if(draw_text_image(target,frame,&area))return 1;
    return original_draw_target(self,target,frame,appearance,rect,overflow);
  }
  if(kind==NXS_BUTTON) {
    if(!w->button_label_owned)return original_draw_target(self,target,frame,appearance,rect,overflow);
    widget_sync(w);
    if(button_cache_available(w)&&w->button_width==lround(area.width)&&w->button_height==lround(area.height)) {
      draw_bitmap(target,&area,w->button_pixels,w->button_width,w->button_height);w->painted=1;
      if(log_fd>=0)dprintf(log_fd,"%d native-button id=%llu frame=%p size=%dx%d\n",getpid(),(unsigned long long)w->id,frame,w->button_width,w->button_height);
      return 1;
    }
    return original_draw_target(self,target,frame,appearance,rect,overflow);
  }
  struct NXSResponse *response=widget_sync(w);w->painted=0;
  if(!response||response->width!=lround(area.width)||response->height!=lround(area.height)||response->stride!=response->width*4||
     sizeof(*response)+(size_t)response->stride*response->height!=response->size)
    return original_draw_target(self,target,frame,appearance,rect,overflow);
  draw_bitmap(target,&area,(const uint32_t *)(response+1),response->width,response->height);w->painted=1;
  drain_widget_notifier();
  if(log_fd>=0)dprintf(log_fd,"%d native-widget id=%llu kind=%d frame=%p rect=%.0f,%.0f %.0fx%.0f\n",getpid(),(unsigned long long)w->id,w->kind,frame,area.x,area.y,area.width,area.height);
  return 1;
}
/* Preserve Gecko's CSS/style/zoom sizing path, substituting the provider's
 * preferred width or height. No square-control or artwork geometry is copied. */
static int default_size(void *frame) {
  int original=original_default_size(frame),kind=frame_kind(frame);
  if(metric_probe||!kind)return original;
  metric_probe=1;int native=original_intrinsic(frame,NULL,0);metric_probe=0;
  if(!native)return original;
  float engine_pref=((float (*)(void *))(base+0x6a60be0))(NULL);
  return engine_pref>0?lround(original*preferred_height[kind]/engine_pref):original;
}
static int intrinsic_size(void *frame,const void *input,int type) {
  if(metric_probe)return original_intrinsic(frame,input,type);
  metric_probe=1;int original=original_intrinsic(frame,input,type);metric_probe=0;
  int kind=frame_kind(frame);if(!original||!kind)return original;
  float engine_pref=((float (*)(void *))(base+0x6a60be0))(NULL);
  return engine_pref>0?lround(original*preferred_width[kind]/engine_pref):original;
}
static unsigned widget_modifiers(const void *event) {
  unsigned flags=*(const uint16_t *)((const char *)event+144);
  return ((flags&0x200)?NXS_SHIFT:0)|((flags&1)?NXS_ALT:0)|((flags&8)?NXS_CONTROL:0)|((flags&0x40)?NXS_SUPER:0);
}
static struct PointI widget_point(struct Widget *w,const void *event) {
  return ((struct PointI (*)(const void *,struct RelativeTo))(base+0x6da35a8))(event,(struct RelativeTo){w->frame,0});
}
static struct NXSResponse *pointer_request(struct Widget *w,unsigned operation,const void *event) {
  struct PointI point=widget_point(w,event);
  if(operation==2&&w->kind==NXS_RADIO)w->radio_clicks=*(const uint32_t *)((const char *)event+236);
  if(operation==2&&(text_kind(w->kind))) {
    /* AssignMouseEventDataOnly copies the source's uint32_t mClickCount at
     * +236 in this exact libxul. No local click aggregation or word rules. */
    unsigned clicks=*(const uint32_t *)((const char *)event+236);
    if(clicks>1&&(widget_pointer_capabilities&NXS_POINTER_CLICK_COUNT))
      return native_pointer_press(w->kind,w->id,point.x/60.,point.y/60.,widget_modifiers(event),clicks);
  }
  return widget_request(w,operation,point.x/60.,point.y/60.,widget_modifiers(event));
}
static uint32_t radio_pre_event(void *self,void *context,void *event,void *frame,void *content,int *status,void *override) {
  if(radio_groups_enabled&&context&&event&&status&&*(const uint16_t *)((const char *)event+18)==15&&
     (*(const uint8_t *)((const char *)event+48)&1)&&*(const int16_t *)((const char *)event+152)==0)
    gecko_radio_pointer_capture(frame);
  return original_radio_pre_event(self,context,event,frame,content,status,override);
}
static uint32_t post_event(void *self,void *context,void *event,void *frame,int *status,void *override) {
  uint64_t tab_target=tabs_pointer_target(frame,event);
  unsigned message=*(const uint16_t *)((const char *)event+18);
  int trusted=*(const uint8_t *)((const char *)event+48)&1;
  if(trusted){native_popup_pointer_post(event);native_list_pointer_post(event);}
  if(native_wheel_post(event,frame,status))return original_post_event(self,context,event,frame,status,override);
  if(texts_enabled&&trusted&&(message==13||message==14||message==15)) {
    void *text_frame=text_pointer_frame(frame);
    if(text_frame||(active_widget&&(text_kind(active_widget->kind))))
      return text_pointer_post(self,context,event,frame,status,override,text_frame);
  }
  void *down_node=NULL,*radio_origin=NULL;uint64_t radio_control=0;
  if(trusted&&message==14&&*(const int16_t *)((const char *)event+152)==0&&radio_pointer_source.active) {
    /* Transfer the gesture's semantic reference across the original dispatch,
     * even if a page callback already retired its frame or changed its type. */
    radio_origin=radio_pointer_source.node;radio_control=radio_pointer_source.control;
    click_gate.event=event;click_gate.node=radio_origin;click_gate.control=radio_control;click_gate.radio=1;click_gate.allowed=0;
    memset(&radio_pointer_source,0,sizeof(radio_pointer_source));
  }
  void *target_frame=frame;
  struct Widget *button_owner=frame?html_button_owner(*(void **)((char *)frame+24)):NULL;
  if(button_owner)target_frame=button_owner->frame;
  if(trusted&&message==15&&*(const int16_t *)((const char *)event+152)==0&&frame_kind(target_frame)&&frame_kind(target_frame)!=NXS_SLIDER) {
    down_node=*(void **)((char *)target_frame+24);
    ((unsigned (*)(void *))(base+0x3b9f0e4))(down_node);
  }
  if(trusted&&active_widget&&(message==13||message==14)) {
    struct Widget *w=active_widget;
    if(message==13) {pointer_request(w,3,event);invalidate_widget(w);}
    else if(*(const int16_t *)((const char *)event+152)==0) {
      active_widget=NULL;
      struct NXSResponse *response=pointer_request(w,4,event);
      /* Wait for native tracking completion, not a guessed widget interval. */
      for(int i=0;response&&response->parts[0].y&&i<100;i++) {
        struct timespec pause={.tv_nsec=2000000};nanosleep(&pause,NULL);response=widget_request(w,5,0,0,0);
      }
      if(!click_gate.radio) {
        click_gate.event=event;click_gate.node=w->node;click_gate.control=w->id;
        click_gate.radio=w->kind==NXS_RADIO&&radio_groups_enabled;
        click_gate.allowed=response&&!response->parts[0].y&&response->parts[0].width>w->actions;
        native_control_action_snapshot(response,w->actions,&click_gate.action);
      }
      if(w->kind==NXS_RADIO&&radio_groups_enabled&&!radio_origin) {
        radio_origin=w->node;radio_control=w->id;
        ((unsigned (*)(void *))(base+0x3b9f0e4))(radio_origin);
      }
      invalidate_widget(w);
    }
  }
  uint32_t result=original_post_event(self,context,event,frame,status,override);
  if(radio_origin) {
    /* A native matrix can act even when Gecko has no ordinary click target. */
    void *chosen=gecko_radio_pointer_target(radio_origin,radio_control);
    if(chosen) {
      int native_status=0;void *shell=*(void **)((char *)context+32);
      if(shell)original_click_events(self,shell,event,&native_status,chosen,NULL);
    }
    gecko_radio_pointer_complete(radio_origin,radio_control);
    ((unsigned (*)(void *))(base+0x47ba6b8))(radio_origin);
  }
  tabs_pointer_post(tab_target,event,*status);
  struct Widget *radio_original=radio_pointer_source.node?widget_for_node(radio_pointer_source.node):NULL;
  int radio_current=!radio_pointer_source.active||(radio_original&&radio_original->id==radio_pointer_source.control&&
    radio_pointer_source.node==down_node&&node_kind(down_node)==NXS_RADIO);
  if(down_node&&*status!=1&&radio_current) {
    /* Focus handlers may destroy/reconstruct the original frame. Retain only
     * the semantic node across Gecko's dispatch, then obtain its live frame. */
    struct Widget *w=bind_input_widget(*(void **)((char *)down_node+96));
    if(w&&w->painted&&!active_widget) {
      struct NXSResponse *response=widget_sync(w);
      if(response&&response->parts[2].x) {
        w->actions=response->parts[0].width;
        response=pointer_request(w,2,event);
        if(response){active_widget=w;invalidate_widget(w);}
      }
    }
  }
  if(down_node)((unsigned (*)(void *))(base+0x47ba6b8))(down_node);
  if(click_gate.event==event)memset(&click_gate,0,sizeof(click_gate));
  return result;
}
static uint32_t click_events(void *self,void *shell,void *event,int *status,void *target,void *override) {
  if(click_gate.event==event&&click_gate.radio) {
    void *chosen=gecko_radio_pointer_target(click_gate.node,click_gate.control);
    return chosen?original_click_events(self,shell,event,status,chosen,NULL):0;
  }
  if(click_gate.event==event&&!click_gate.allowed&&(click_gate.node==target||
     (html_button_node(click_gate.node)&&target&&((int (*)(const void *,const void *))(base+NXS_GECKO_HTML_BUTTON_DESCENDANT_OFFSET))(target,click_gate.node)))) {
    note("native Gecko gesture cancelled activation");return 0;
  }
  struct Widget *w=click_gate.event==event?widget_for_node(click_gate.node):NULL;
  if(w&&w->id==click_gate.control&&w->kind==NXS_CHECKBOX&&target==w->node&&click_gate.allowed) {
    struct NXSCheckboxActivation previous=native_checkbox_enter((uintptr_t)w->node,w->id,click_gate.action);
    uint32_t result=original_click_events(self,shell,event,status,target,override);native_checkbox_activation=previous;return result;
  }
  return original_click_events(self,shell,event,status,target,override);
}
static unsigned logical_key(unsigned code) {
  switch(code) {
    case 13:return NXS_KEY_ENTER;case 9:return NXS_KEY_TAB;case 8:return NXS_KEY_BACKSPACE;
    case 46:return NXS_KEY_DELETE;case 27:return NXS_KEY_ESCAPE;
    case 37:return NXS_KEY_LEFT;case 39:return NXS_KEY_RIGHT;case 38:return NXS_KEY_UP_ARROW;case 40:return NXS_KEY_DOWN_ARROW;
    case 36:return NXS_KEY_HOME;case 35:return NXS_KEY_END;case 33:return NXS_KEY_PAGE_UP;case 34:return NXS_KEY_PAGE_DOWN;case 45:return NXS_KEY_INSERT;
  }
  return code>=112&&code<=135?NXS_KEY_F1+code-112:NXS_KEY_TEXT;
}
static char *utf8_text(const uint16_t *text,uint32_t length) {
  if(length>16384||(!text&&length))return NULL;
  char *result=malloc(length*3+1);if(!result)return NULL;size_t used=0;
  for(uint32_t i=0;i<length;i++) {
    uint32_t c=text[i];
    if(c>=0xd800&&c<=0xdbff&&i+1<length&&text[i+1]>=0xdc00&&text[i+1]<=0xdfff){c=0x10000+((c-0xd800)<<10)+(text[++i]-0xdc00);}
    else if(c>=0xd800&&c<=0xdfff)c=0xfffd;
    if(!c){free(result);return NULL;}
    if(c<0x80)result[used++]=c;
    else if(c<0x800){result[used++]=0xc0|(c>>6);result[used++]=0x80|(c&63);}
    else if(c<0x10000){result[used++]=0xe0|(c>>12);result[used++]=0x80|((c>>6)&63);result[used++]=0x80|(c&63);}
    else {result[used++]=0xf0|(c>>18);result[used++]=0x80|((c>>12)&63);result[used++]=0x80|((c>>6)&63);result[used++]=0x80|(c&63);}
  }
  result[used]=0;return result;
}
static char *key_text(const void *event) {
  const uint16_t *text=*(const uint16_t *const *)((const char *)event+160);
  uint32_t length=*(const uint32_t *)((const char *)event+168);
  if(!length&&*(const uint32_t *)((const char *)event+200)==32)return strdup(" ");
  return utf8_text(text,length);
}
static int advance_focus(void *node,int result) {
  void *manager=*(void **)(base+0xa439c38),*focused=NULL;if(!manager)return 0;
  uint32_t status=((uint32_t (*)(void *,void *,void *,unsigned,unsigned,void **))(base+0x4873490))
    (manager,NULL,node,result==NXS_INPUT_NEXT?1:2,1u<<13,&focused);
  if(focused)((unsigned (*)(void *))(base+0x47ba6b8))(focused);
  return !(status&0x80000000u);
}
static void text_post_keyboard(void *node,void *visitor) {
    void *event=*(void **)((char *)visitor+8);int *status=(int *)((char *)visitor+24);
    unsigned message=*(const uint16_t *)((char *)event+18);
    /* Accelerators and navigation may never produce keypress. Take their
     * default action after DOM keydown listeners, before engine commands. */
    if((message==3||message==4)&&*status!=1&&text_modifier_event(event)) {
      /* Flags changes are not empty text insertions. Preserve Gecko's own
       * modifier default action after informing the native responder. */
      dispatch_text_key(node,event,NULL);
    } else if(message==4&&*status!=1) {
      unsigned code=*(uint32_t *)((char *)event+200),modifiers=widget_modifiers(event);
      if((modifiers&(NXS_CONTROL|NXS_ALT|NXS_SUPER))||code==8||code==9||code==46||(code>=33&&code<=40))
        if(dispatch_text_key(node,event,NULL))*status=1;
    }
}
static uint32_t widget_post(void *node,void *visitor,uint32_t (*original)(void *,void *)) {
  if(text_kind(node_kind(node))) {
    text_post_keyboard(node,visitor);return original(node,visitor);
  }
  void *event=*(void **)((char *)visitor+8);
  unsigned message=*(const uint16_t *)((char *)event+18);
  struct Widget *w=widget_for_node(node);
  if(w&&w->kind==NXS_SLIDER&&w->range_tracking&&message==66) {
    struct NXSResponse *response=range_end(w);range_key_action(node,response,0);w=widget_for_node(node);
  }
  if(!w&&node_kind(node))w=bind_widget(*(void **)((char *)node+96));
  if((node_kind(node)==NXS_BUTTON||node_kind(node)==NXS_SLIDER)&&message>=2&&message<=4)
    w=bind_input_widget(*(void **)((char *)node+96));
  int *status=(int *)((char *)visitor+24);
  if(!w||!w->painted||message<2||message>4||!(*(uint8_t *)((char *)event+48)&1)||*status==1||!widget_focused(w))
    return original(node,visitor);
  if(message==2)return w->kind==NXS_SLIDER&&w->range_keypress?original(node,visitor):0;
  if(w->kind==NXS_RADIO&&radio_groups_enabled)return gecko_radio_key(w,event,visitor);
  struct NXSResponse *response=widget_sync(w);
  if(!response||!response->parts[2].x)return original(node,visitor);
  double actions=response->parts[0].width;
  char *text=key_text(event);if(!text)return original(node,visitor);
  size_t length=strlen(text),size=sizeof(struct NXSControlInputRequest)+2*length;
  struct NXSControlInputRequest *request=calloc(1,size);if(!request){free(text);return original(node,visitor);}
  *request=(struct NXSControlInputRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=8,.process=identity(),
    .kind=w->kind,.control=w->id,.type=message==4?NXS_KEY_DOWN:NXS_KEY_UP,
    .modifiers=widget_modifiers(event),.key=logical_key(*(uint32_t *)((char *)event+200)),
    .repeat=!!*((uint8_t *)event+223),.text_size=length,.unmodified_size=length};
  memcpy(request+1,text,length);memcpy((char *)(request+1)+length,text,length);
  response=exchange_bytes(request,size);free(request);free(text);
  if(!response)return original(node,visitor);
  int handled=response->parts[3].x,activate=response->parts[0].width>actions;
  struct NXSControlAction checkbox_action;native_control_action_snapshot(response,actions,&checkbox_action);
  if(w->kind==NXS_SLIDER)w->range_keypress=handled==NXS_INPUT_UNHANDLED;
  invalidate_widget(w);drain_widget_notifier();
  if(handled==NXS_INPUT_NEXT||handled==NXS_INPUT_PREVIOUS) {
    if(advance_focus(node,handled))*status=1;
  } else if(handled==NXS_INPUT_HANDLED)*status=1;
  if(activate) {
    if(w->kind==NXS_SLIDER){range_key_action(node,response,1);return 0;}
    note("native Gecko keyboard action invokes real engine click");
    struct NXSCheckboxActivation previous=native_checkbox_activation;
    if(w->kind==NXS_CHECKBOX)native_checkbox_enter((uintptr_t)node,w->id,checkbox_action);
    ((uint32_t (*)(void *,int,void *))(base+0x58ce09c))(node,1,*(void **)visitor);
    native_checkbox_activation=previous;
  }
  return 0;
}
static uint32_t input_post(void *node,void *visitor) {
  return widget_post(node,visitor,original_input_post);
}
static void release_idle_widget_notifier(void) {
  if(!widgets&&!native_popups_exist()&&!native_lists_exist()&&widget_notifier>=0) {
    remove_text_watch();
    struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=16,.process=identity()};
    exchange_bytes(&request,sizeof(request));close(widget_notifier);widget_notifier=-1;
  }
}
static void forget_widget(struct Widget **cursor) {
  struct Widget *w=*cursor;
  if(active_widget==w)active_widget=NULL;
  widget_request(w,6,0,0,0);*cursor=w->next;free(w->button_pixels);free(w->button_model_title);free(w);
  release_idle_widget_notifier();
}
static void frame_destroy(void *frame,void *context) {
  tabs_forget(frame);native_popup_forget(frame);native_list_forget(frame);
  reset_widget_process();
  struct Widget **cursor=&widgets;while(*cursor&&(*cursor)->frame!=frame)cursor=&(*cursor)->next;
  if(*cursor)forget_widget(cursor);
  original_frame_destroy(frame,context);
}
static void release_shell_widgets(void *shell) {
  reset_widget_process();void *context=*(void **)((char *)shell+120);
  gecko_radio_pointer_release_context(context);
  native_popup_release_context(context);native_list_release_context(context);
  struct Widget **cursor=&widgets;
  while(*cursor) {
    if(*(void **)((char *)(*cursor)->frame+40)==context)forget_widget(cursor);
    else cursor=&(*cursor)->next;
  }
}
static void freeze_shell(void *shell,int children) {
  release_shell_widgets(shell);original_freeze(shell,children);
}
static void active_shell(void *shell,int active) {
  if(!active)release_shell_widgets(shell);
  original_active(shell,active);
}
#include "buttons.inc"
#include "radios.inc"
#include "checkbox-activation.inc"
#include "form-labels.inc"
#include "ranges.inc"
#include "text.inc"
#include "viewport.inc"
#include "wheel.inc"
static struct Detour widget_detours[]={
  {NXS_GECKO_DRAW_TARGET_OFFSET,gecko_draw_target_bytes,draw_widget,(void **)&original_draw_target},
  {NXS_GECKO_DEFAULT_SIZE_OFFSET,gecko_default_size_bytes,default_size,(void **)&original_default_size},
  {NXS_GECKO_INTRINSIC_OFFSET,gecko_intrinsic_bytes,intrinsic_size,(void **)&original_intrinsic},
  {NXS_GECKO_INPUT_POST_OFFSET,gecko_input_post_bytes,input_post,(void **)&original_input_post},
  {NXS_GECKO_POST_EVENT_OFFSET,gecko_post_event_bytes,post_event,(void **)&original_post_event},
  {NXS_GECKO_CLICK_EVENTS_OFFSET,gecko_click_events_bytes,click_events,(void **)&original_click_events},
  {NXS_GECKO_FRAME_DESTROY_OFFSET,gecko_frame_destroy_bytes,frame_destroy,(void **)&original_frame_destroy},
  {NXS_GECKO_FREEZE_OFFSET,gecko_freeze_bytes,freeze_shell,(void **)&original_freeze},
  {NXS_GECKO_ACTIVE_OFFSET,gecko_active_bytes,active_shell,(void **)&original_active}
};
static void prepare_widget_metrics(void) {
  struct NXSResponse *response=exchange((struct NXSRequest){.magic=NXS_CHROMIUM_MAGIC,.operation=7,.process=identity()});
  if(!response||response->parts[4].width!=3||response->parts[6].x!=1)return;
  for(int kind=2;kind<=3;kind++) {
    double width=response->parts[kind-1].width,height=response->parts[kind-1].height;
    if(!isfinite(width)||!isfinite(height)||width<1||height<1||width>256||height>256)return;
    preferred_width[kind]=ceil(width);preferred_height[kind]=ceil(height);
  }
  widgets_enabled=1;
  const char *radio_groups=getenv("NEXTSPACE_FIREFOX_RADIO_GROUPS");
  widget_pointer_capabilities=response->parts[5].x==1?NXS_POINTER_CLICK_COUNT:0;
  radio_groups_enabled=radio_groups&&!strcmp(radio_groups,"1")&&((unsigned)response->parts[4].y&3)==3&&(widget_pointer_capabilities&NXS_POINTER_CLICK_COUNT);
  labels_enabled=widgets_enabled&&((unsigned)response->parts[4].y&4);
  prepare_range_bindings(response);
  const char *popups=getenv("NEXTSPACE_FIREFOX_POPUPS");popups_requested=popups&&!strcmp(popups,"1")&&response->parts[6].width&&response->parts[6].height;
  const char *lists=getenv("NEXTSPACE_FIREFOX_LISTS");lists_requested=popups_requested&&lists&&!strcmp(lists,"1")&&((unsigned)response->parts[3].x&1);
  const char *buttons=getenv("NEXTSPACE_FIREFOX_BUTTONS");buttons_enabled=buttons&&!strcmp(buttons,"1");
  const char *text=getenv("NEXTSPACE_FIREFOX_TEXT");texts_enabled=text&&!strcmp(text,"1")&&((unsigned)response->parts[6].y&3)==3;
  const char *multiline=getenv("NEXTSPACE_FIREFOX_MULTILINE");
  multiline_enabled=texts_enabled&&multiline&&!strcmp(multiline,"1")&&((unsigned)response->parts[6].y&NXS_TEXT_MULTILINE);
  const char *viewport=getenv("NEXTSPACE_FIREFOX_MULTILINE_VIEWPORT");
  multiline_viewport_enabled=multiline_enabled&&viewport&&!strcmp(viewport,"1")&&
    ((unsigned)response->parts[6].y&(NXS_TEXT_VIEWPORT|NXS_TEXT_GEOMETRY))==(NXS_TEXT_VIEWPORT|NXS_TEXT_GEOMETRY);
  const char *wheel=getenv("NEXTSPACE_FIREFOX_WHEEL");
  wheel_enabled=multiline_viewport_enabled&&wheel&&!strcmp(wheel,"1")&&response->parts[0].x==NXS_WHEEL_EVENTS;
  text_command_reporting=!!((unsigned)response->parts[6].y&NXS_TEXT_COMMAND);
  application_commands=response->parts[5].y==1;
  application_menu_keys=!!((unsigned)response->parts[5].height&2);
  const char *frontend=getenv("NEXTSPACE_FIREFOX_FRONTEND");frontend_requested=NXS_BROWSER_UI_PATCH&&texts_enabled&&frontend&&!strcmp(frontend,"1");
}
