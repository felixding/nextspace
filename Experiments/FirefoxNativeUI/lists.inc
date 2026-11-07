/* Gecko list model and DOM transactions only. Ordinary native NSBrowser owns
 * rows, scrolling, selection, focus, navigation, drawing and mouse tracking. */
#include "pinned-lists.h"
#include "pinned-list-geometry.h"
struct GeckoList {
  struct GeckoList *next;
  void *frame,*node;
  struct NXSListBinding binding;
  struct GeckoPopupModel model;
  int owned;
};
static struct GeckoList *gecko_lists;
static uint64_t list_tracking_id;
static __thread void *list_pointer_event_seen;
static int list_pointer_event(struct GeckoList *,void *);
static int native_lists_exist(void){return gecko_lists!=NULL;}
static void *list_multiple_atom;
static int list_layout_rows(struct GeckoList *);
_Static_assert(NXS_GECKO_LIST_DISPLAY==NXS_GECKO_TEXT_SCROLL_DISPLAY_OFFSET,"One shared scroll-container display boundary");
static struct GeckoList *list_find(const void *frame)
{for(struct GeckoList *list=gecko_lists;list;list=list->next)if(list->frame==frame)return list;return NULL;}
static struct GeckoList *list_find_id(uint64_t id)
{for(struct GeckoList *list=gecko_lists;list;list=list->next)if(list->binding.control==id)return list;return NULL;}
static int native_list_frame(const void *frame)
{
  if(!lists_requested||!native_web_process()||!frame||*(const uintptr_t *)frame!=base+NXS_GECKO_LIST_FRAME_VTABLE+16)return 0;
  void *node=*(void **)((const char *)frame+24);
  if(!node||*(uintptr_t *)node!=base+NXS_GECKO_POPUP_SELECT_VTABLE+16||*(void **)((char *)node+96)!=frame)return 0;
  const void *style=*(void **)((const char *)frame+32),*display=*(void **)((const char *)style+80);
  return fabsf(frame_scale(frame)-1)<.000001f&&original_frontend_themed(frame,display,NULL);
}
static int list_flags(void *node,unsigned *flags)
{
  if(!list_multiple_atom)list_multiple_atom=((void *(*)(const char *))(base+NXS_GECKO_POPUP_ATOMIZE))("multiple");
  if(!list_multiple_atom)return 0;
  static const uint16_t empty;struct GeckoString value={.data=&empty,.flags=1};
  int multiple=((int (*)(const void *,const void *,void *))(base+NXS_GECKO_POPUP_GET_ATTR))(node,list_multiple_atom,&value);
  ((void (*)(void *))(base+0x3826f2c))(&value);*flags=multiple?NXS_LIST_MULTIPLE:0;return 1;
}
static NXSListItem *list_items(const struct GeckoPopupModel *model)
{
  unsigned count=model->packet->count;if(count>4096)return NULL;
  NXSListItem *items=calloc(count?count:1,sizeof(*items));if(!items)return NULL;
  const unsigned char *row=(const unsigned char *)(model->packet+1);
  for(unsigned i=0;i<count;i++) {
    uint32_t flags,length;memcpy(&flags,row,4);memcpy(&length,row+4,4);row+=8;
    char *title=malloc((size_t)length+1);if(!title){native_list_binding_free_items(items,i);return NULL;}
    memcpy(title,row,length);title[length]=0;row+=length;
    items[i]=(NXSListItem){.size=sizeof(*items),.identifier=(uintptr_t)model->nodes[i],.title=title,
      .enabled=!!(flags&1),.selected=model->indices[i]>=0&&!!(*(uint64_t *)((char *)model->nodes[i]+112)&32)};
  }
  return items;
}
static int prepare_list_image(void *frame)
{
  if(!native_list_frame(frame)){native_list_forget(frame);return 0;}
  struct GeckoList *list=list_find(frame);
  if(!list) {
    if(!ensure_widget_lifetime())return 0;
    list=calloc(1,sizeof(*list));if(!list)return 0;
    list->frame=frame;list->node=*(void **)((char *)frame+24);list->binding.control=++next_widget;
    list->next=gecko_lists;gecko_lists=list;
  }
  int existing=list->binding.created&&list->binding.epoch==atomic_load(&native_host_epoch);
  list->owned=0;
  int rect[4]={0};engine_frame_rect((void *)(base+0x6daae5c),frame,rect);
  double width=rect[2]/60.,height=rect[3]/60.;
  if(width<1||height<1||width!=floor(width)||height!=floor(height)||width>8192||height>8192)return 0;
  struct GeckoPopupModel model;if(!popup_snapshot(list->node,&model))return 0;
  unsigned flags;NXSListItem *items=list_items(&model);
  void *manager=*(void **)(base+0xa439c38);int focused=manager&&*(void **)((char *)manager+128)==list->node;
  int okay=items&&list_flags(list->node,&flags)&&native_list_binding_sync(&list->binding,items,model.packet->count,flags,
    width,height,!(*(uint64_t *)((char *)list->node+112)&16),focused);
  if(okay&&!existing) {
    struct PointI position=viewport_engine_position(frame);
    okay=native_list_binding_scroll(&list->binding,position.x/60.,position.y/60.);
  }
  if(okay&&(list->binding.pixel_width!=lround(width)||list->binding.pixel_height!=lround(height)))okay=0;
  native_list_binding_free_items(items,items?model.packet->count:0);
  if(okay&&!list->binding.tracking) {popup_model_free(&list->model);list->model=model;memset(&model,0,sizeof(model));}
  popup_model_free(&model);list->owned=okay;
  uint64_t id=list->binding.control;if(okay)okay=list_layout_rows(list);
  list=list_find_id(id);if(list)list->owned=okay;return list&&okay;
}
static int native_list_owned(const void *frame)
{struct GeckoList *list=list_find(frame);return list&&list->owned;}
static int draw_list_image(void *target,void *frame,const struct RectF *area)
{
  struct GeckoList *list=list_find(frame);if(!list||!list->owned||!list->binding.pixels)return 0;
  if(list->binding.pixel_width!=lround(area->width)||list->binding.pixel_height!=lround(area->height))return 0;
  draw_bitmap(target,area,list->binding.pixels,list->binding.pixel_width,list->binding.pixel_height);
  if(log_fd>=0)dprintf(log_fd,"%d native-list id=%llu count=%u selected=%u rect=%.0f,%.0f %dx%d\n",getpid(),
    (unsigned long long)list->binding.control,list->binding.state.count,list->binding.state.selected_count,
    area->x,area->y,list->binding.pixel_width,list->binding.pixel_height);
  return 1;
}
static int native_list_display(void *frame,void *builder,const void *lists)
{
  if(prepare_list_image(frame)) {
    void *previous=frontend_background_frame;frontend_background_frame=frame;
    ((void (*)(void *,void *,const void *))(base+NXS_GECKO_TEXT_DISPLAY_BACKGROUND_OFFSET))(frame,builder,lists);
    frontend_background_frame=previous;return 1;
  }
  return 0;
}
static void native_list_forget(void *frame)
{
  struct GeckoList **link=&gecko_lists;
  while(*link) {
    struct GeckoList *list=*link;if(list->frame!=frame){link=&list->next;continue;}
    *link=list->next;if(list_tracking_id==list->binding.control)list_tracking_id=0;
    native_list_binding_destroy(&list->binding);popup_model_free(&list->model);free(list);
    release_idle_widget_notifier();break;
  }
}
static void native_list_release_context(void *context)
{
  for(;;) {
    struct GeckoList *list;for(list=gecko_lists;list;list=list->next)if(*(void **)((char *)list->frame+40)==context)break;
    if(!list)break;native_list_forget(list->frame);
  }
}
static void list_invalidate(struct GeckoList *list)
{((void (*)(void *,unsigned,int))(base+0x6e85c5c))(list->frame,0,1);}
static int list_viewport(const void *frame,struct FrameViewport *data,int refresh)
{
  struct GeckoList *list=list_find(frame);
  if(!list||!list->owned||!native_list_frame(frame))return 0;
  uint64_t id=list->binding.control;
  if(refresh&&!native_list_binding_refresh(&list->binding))return 0;
  list=list_find_id(id);
  if(!list||list->frame!=frame||!list->owned||!list->binding.geometry_ready||
     list->binding.epoch!=atomic_load(&native_host_epoch)||!native_list_frame(frame))return 0;
  struct NXSListWireState state=list->binding.state;
  *data=(struct FrameViewport){.frame=list->frame,.node=list->node,.id=id,
    .kind=NXS_LISTBOX,.epoch=list->binding.epoch,.geometry=list->binding.geometry,
    .native={.size=sizeof(NXSTextViewport),.visible={state.visible.x,state.visible.y,state.visible.width,state.visible.height},
      .content={state.content_width,state.content_height}}};return 1;
}
static int list_viewport_scroll(const struct FrameViewport *data,double x,double y)
{
  struct GeckoList *list=list_find_id(data->id);
  return list&&list->node==data->node&&list->frame==data->frame&&native_list_binding_scroll(&list->binding,x,y);
}
static int list_viewport_wheel(const struct FrameViewport *data,const NXSWheelEvent *wheel)
{
  struct GeckoList *list=list_find_id(data->id);
  return list&&list->node==data->node&&list->frame==data->frame&&native_list_binding_wheel(&list->binding,wheel);
}
/* Bind the original engine boxes to actual native row measurements. The
 * original SetRect preserves overflow bookkeeping; no row layout is copied. */
static int list_layout_rows(struct GeckoList *list)
{
  uint64_t id=list->binding.control;void *owner=list->frame,*root=list->node;
  unsigned count=list->model.packet?list->model.packet->count:0;
  for(unsigned i=0;i<count;i++) {
    void *node=list->model.nodes[i];
    if(list->model.indices[i]<0)continue;
    ((unsigned (*)(void *))(base+NXS_GECKO_POPUP_NODE_ADDREF))(node);
    struct NXSRectD row;struct NXSListWireState state;
    int okay=native_list_item_geometry(id,(uintptr_t)node,&row,&state);
    list=list_find_id(id);
    if(!okay||!list||list->frame!=owner||list->node!=root||state.count!=count||
       !list->binding.geometry_ready||!native_list_frame(owner)) {
      ((unsigned (*)(void *))(base+NXS_GECKO_POPUP_NODE_RELEASE))(node);return 0;
    }
    void *frame=*(void **)((char *)node+96);
    if(frame&&((void *(*)(void *,unsigned))(base+NXS_GECKO_TEXT_NEAREST_SCROLL_OFFSET))(frame,3)==owner) {
      void *parent=*(void **)((char *)frame+48);
      void *document=*(void **)((char *)owner+NXS_GECKO_VIEWPORT_SCROLLED_FRAME_BYTE);
      if(parent&&document) {
        struct PointI offset=((struct PointI (*)(const void *,const void *))(base+NXS_GECKO_LIST_GEOMETRY_FRAME_OFFSET))(parent,document);
        NXSRect clip=list->binding.geometry.clip;
        struct ViewportRect rect={lround((row.x-clip.x+state.visible.x)*60)-offset.x,
          lround((row.y-clip.y+state.visible.y)*60)-offset.y,lround(row.width*60),lround(row.height*60)};
        ((void (*)(void *,const struct ViewportRect *,int))(base+NXS_GECKO_LIST_GEOMETRY_SET_RECT))(frame,&rect,0);
      }
    }
    ((unsigned (*)(void *))(base+NXS_GECKO_POPUP_NODE_RELEASE))(node);
  }
  return 1;
}
static void native_list_model_changed(void *node)
{for(struct GeckoList *list=gecko_lists;list;list=list->next)if(list->node==node)list_invalidate(list);}
static void list_after_input(uint64_t id,uint64_t actions)
{
  struct GeckoList *list=list_find_id(id);if(!list||!native_list_binding_refresh(&list->binding))return;
  if(list_tracking_id==id&&!list->binding.tracking)list_tracking_id=0;
  if(list->binding.state.actions!=actions) {
    struct GeckoPopupModel current;
    if(popup_snapshot(list->node,&current)) {
      unsigned flags;NXSListItem *items=list_items(&current);
      int valid=items&&list_flags(list->node,&flags)&&native_list_binding_same(&list->binding,items,current.packet->count,flags)&&
        !(*(uint64_t *)((char *)list->node+112)&16);
      int changed=0;void *node=list->node;
      ((unsigned (*)(void *))(base+NXS_GECKO_POPUP_NODE_ADDREF))(node);
      /* Native selection is authoritative. These are original DOM setters,
       * not an implementation of range/toggle/navigation rules. NoReselect
       * prevents an intermediate deselection from inventing another choice. */
      for(unsigned i=0;valid&&i<current.packet->count;i++) {
        if(current.indices[i]<0)continue;
        int selected=0;for(unsigned j=0;j<list->binding.state.selected_count;j++)
          if(list->binding.selection[j]==items[i].identifier)selected=1;
        if(selected==items[i].selected)continue;
        unsigned mask=(1u<<2)|(1u<<3)|(1u<<4)|(selected?1:0);
        changed|=((int (*)(void *,int,int,unsigned))(base+NXS_GECKO_LIST_SET_SELECTION))(node,current.indices[i],current.indices[i],mask);
        list->binding.items[i].selected=selected;
      }
      native_list_binding_free_items(items,items?current.packet->count:0);popup_model_free(&current);
      if(valid&&changed)((void (*)(void *,int))(base+NXS_GECKO_LIST_FINISH))(node,1);
      else if(!valid)note("native list stale model action discarded");
      ((unsigned (*)(void *))(base+NXS_GECKO_POPUP_NODE_RELEASE))(node);
    }
  }
  list=list_find_id(id);
  if(list&&prepare_list_image(list->frame)) {
    echo_native_viewport(list->frame);list=list_find_id(id);if(list)list_invalidate(list);
  }
}
static int native_list_post(void *node,void *visitor)
{
  void *frame=*(void **)((char *)node+96);
  struct GeckoList *list=list_find(frame);if(!list||!list->owned)return 0;
  void *event=*(void **)((char *)visitor+8);int *status=(int *)((char *)visitor+24);
  unsigned message=*(const uint16_t *)((char *)event+18);
  if(!(*(const uint8_t *)((char *)event+48)&1)||*status==1)return 0;
  if(message>=2&&message<=4) {
    void *manager=*(void **)(base+0xa439c38);
    if(!manager||*(void **)((char *)manager+128)!=node||!prepare_list_image(frame))return 0;
    if(message==2)return 1; /* keypress follows the native keydown decision. */
    uint64_t id=list->binding.control,actions=list->binding.state.actions;char *text=key_text(event);if(!text)return 0;
    NXSKeyEvent key={.size=sizeof(key),.type=text_modifier_event(event)?NXS_KEY_MODIFIERS:message==4?NXS_KEY_DOWN:NXS_KEY_UP,
      .modifiers=widget_modifiers(event),.key=logical_key(*(uint32_t *)((char *)event+200)),
      .repeat=!!*((uint8_t *)event+223),.text=text,.unmodified_text=text};
    struct NXSResponse *response=native_list_input(id,0,&key);free(text);if(!response)return 0;
    int handled=response->parts[3].x;list_after_input(id,actions);
    if(handled==NXS_INPUT_HANDLED)*status=1;
    else if(handled==NXS_INPUT_NEXT||handled==NXS_INPUT_PREVIOUS){if(advance_focus(node,handled))*status=1;}
    return handled!=NXS_INPUT_UNHANDLED;
  }
  int handled=list_pointer_event(list,event);if(handled)list_pointer_event_seen=event;return handled;
}
static int list_pointer_event(struct GeckoList *list,void *event)
{
  void *frame=list->frame;unsigned message=*(const uint16_t *)((char *)event+18);
  if(message!=13&&message!=14&&message!=15)return 0;
  if((message==14||message==15)&&*(const int16_t *)((char *)event+152)!=0)return 0;
  if(message==15&&!prepare_list_image(frame))return 0;
  uint64_t id=list->binding.control,actions=list->binding.state.actions;
  struct PointI point=((struct PointI (*)(const void *,struct RelativeTo))(base+0x6da35a8))(event,(struct RelativeTo){frame,0});
  unsigned operation=message==15?2:message==14?4:3;
  if(message!=15&&list_tracking_id!=id)return 1;
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,.process=identity(),
    .kind=NXS_LISTBOX,.control=id,.x=point.x/60.,.y=point.y/60.,.modifiers=widget_modifiers(event)};
  unsigned clicks=message==15?*(const uint32_t *)((const char *)event+236):0;
  struct NXSResponse *response=message==15&&clicks>1?native_pointer_press(NXS_LISTBOX,id,request.x,request.y,request.modifiers,clicks):exchange_bytes(&request,sizeof(request));
  if(!response)return 0;
  if(message==15){list_tracking_id=id;list->binding.tracking=!!response->parts[0].y;}
  if(message==14)for(unsigned i=0;response&&response->parts[0].y&&i<100;i++) {
    struct timespec pause={.tv_nsec=2000000};nanosleep(&pause,NULL);response=native_list_request(id,5,0,0,1);
  }
  list_after_input(id,actions);return 1;
}
/* The select's DOM post handler receives inside events. The existing engine
 * post-event boundary also forwards move/release outside the original target.
 * Retain one native tracker and avoid sending the same dispatch twice. */
static void native_list_pointer_post(void *event)
{
  int seen=list_pointer_event_seen==event;list_pointer_event_seen=NULL;
  if(seen||!list_tracking_id||!(*(const uint8_t *)((char *)event+48)&1))return;
  unsigned message=*(const uint16_t *)((char *)event+18);
  if(message!=13&&message!=14)return;
  struct GeckoList *list=list_find_id(list_tracking_id);if(list)list_pointer_event(list,event);
}

#include "list-hits.inc"
static struct Detour list_detours[]={
  /* Installed only when text did not already install this same boundary. */
  {NXS_GECKO_LIST_DISPLAY,gecko_list_display_bytes,text_scroll_display,(void **)&original_text_scroll_display}
};
