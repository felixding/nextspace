/* Gecko select models and command binding. Existing NSPopUpButton/NSMenu own
 * all control drawing, menu geometry, hit testing and keyboard behavior. */
#include "pinned-popups.h"
struct GeckoPopupModel {
  struct NXSControlPopupRequest *packet;
  void **nodes;
};
struct GeckoPopup {
  struct GeckoPopup *next;
  void *frame,*node;
  uint64_t id;
  double width,height,actions;
  struct GeckoPopupModel model;
  uint32_t *pixels;
  int pixel_width,pixel_height,owned,visible;
};
struct PopupRectI {int x,y,width,height;};
static struct GeckoPopup *gecko_popups;
static void *popup_label_atom;
static __thread const void *popup_mouse_event;
static uint64_t popup_tracking_id;
static uint32_t (*original_popup_chrome_event)(void *,void *,const void *,int,int,int *);
static uint32_t (*original_popup_post)(void *,void *);
static struct GeckoPopup *popup_find(const void *frame) {
  for(struct GeckoPopup *p=gecko_popups;p;p=p->next)if(p->frame==frame)return p;
  return NULL;
}
static struct GeckoPopup *popup_find_id(uint64_t id) {
  for(struct GeckoPopup *p=gecko_popups;p;p=p->next)if(p->id==id)return p;
  return NULL;
}
static int native_popups_exist(void){return gecko_popups!=NULL;}
static int native_popup_frame(const void *frame) {
  if(!popups_requested||!native_web_process()||!frame||*(const uintptr_t *)frame!=base+NXS_GECKO_POPUP_FRAME_VTABLE+16)return 0;
  void *node=*(void **)((const char *)frame+24);
  if(!node||*(uintptr_t *)node!=base+NXS_GECKO_POPUP_SELECT_VTABLE+16||*(void **)((char *)node+96)!=frame)return 0;
  const void *style=*(void **)((const char *)frame+32),*display=*(void **)((const char *)style+80);
  /* Let Gecko resolve appearance:auto and its native-widget eligibility. */
  return fabsf(frame_scale(frame)-1)<0.000001f&&original_frontend_themed(frame,display,NULL);
}
static struct NXSResponse *popup_request(struct GeckoPopup *p,unsigned op,int value) {
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=op,.process=identity(),
    .kind=NXS_POPUP,.control=p->id,.width=p->width,.height=p->height,.enabled=!(*(uint64_t *)((char *)p->node+112)&16),.state=value};
  return exchange_bytes(&request,sizeof(request));
}
static void popup_model_free(struct GeckoPopupModel *model) {
  if(model->packet)for(unsigned i=0;i<model->packet->count;i++)
    ((unsigned (*)(void *))(base+NXS_GECKO_POPUP_NODE_RELEASE))(model->nodes[i]);
  free(model->nodes);free(model->packet);memset(model,0,sizeof(*model));
}
static int popup_snapshot(void *node,struct GeckoPopupModel *model) {
  memset(model,0,sizeof(*model));
  void *options=*(void **)((char *)node+264);if(!options)return 0;
  unsigned count=((unsigned (*)(void *))(base+NXS_GECKO_POPUP_LIST_LENGTH))(options);if(count>4096)return 0;
  model->packet=calloc(1,sizeof(*model->packet)+65536);model->nodes=calloc(count?count:1,sizeof(void *));
  if(!model->packet||!model->nodes){popup_model_free(model);return 0;}
  struct NXSControlPopupRequest *request=model->packet;
  *request=(struct NXSControlPopupRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=11,.process=identity(),.kind=NXS_POPUP,
    .selected=((int (*)(void *))(base+NXS_GECKO_POPUP_SELECTED_INDEX))(node)};
  if(!popup_label_atom)popup_label_atom=((void *(*)(const char *))(base+NXS_GECKO_POPUP_ATOMIZE))("label");
  if(!popup_label_atom){popup_model_free(model);return 0;}
  static const uint16_t empty;
  for(unsigned i=0;i<count;i++) {
    void *option=((void *(*)(void *,unsigned))(base+NXS_GECKO_POPUP_LIST_ITEM))(options,i);if(!option){popup_model_free(model);return 0;}
    struct GeckoString label={.data=&empty,.flags=1};
    ((int (*)(const void *,const void *,void *))(base+NXS_GECKO_POPUP_GET_ATTR))(option,popup_label_atom,&label);
    if(!label.length)((void (*)(void *,void *))(base+NXS_GECKO_POPUP_OPTION_TEXT))(option,&label);
    char *title=utf8_text(label.data,label.length);((void (*)(void *))(base+0x3826f2c))(&label);
    uint8_t disabled=0;uint32_t result=((uint32_t (*)(void *,int,void *))(base+NXS_GECKO_POPUP_OPTION_DISABLED))(node,i,&disabled);
    if(!title||result&0x80000000u){free(title);popup_model_free(model);return 0;}
    size_t length=strlen(title);
    if(length>65536||request->text_size+8+length>65536){free(title);popup_model_free(model);return 0;}
    uint32_t flags=!disabled,size=length;unsigned char *body=(unsigned char *)(request+1)+request->text_size;
    memcpy(body,&flags,4);memcpy(body+4,&size,4);memcpy(body+8,title,length);free(title);request->text_size+=8+length;
    ((unsigned (*)(void *))(base+NXS_GECKO_POPUP_NODE_ADDREF))(option);model->nodes[request->count++]=option;
  }
  return 1;
}
static int popup_model_same(const struct GeckoPopupModel *a,const struct GeckoPopupModel *b) {
  return a->packet&&b->packet&&a->packet->count==b->packet->count&&a->packet->selected==b->packet->selected&&
    a->packet->text_size==b->packet->text_size&&!memcmp(a->packet+1,b->packet+1,a->packet->text_size)&&
    !memcmp(a->nodes,b->nodes,a->packet->count*sizeof(void *));
}
/* Call the original WebIDL setter with a real engine JSContext and a native
 * boolean argument. It owns popup state, :open invalidation and notifications. */
static int popup_engine_open(void *node,int open) {
  /* Original AutoJSContext owns JSAPI entry/exit when physical input has no
   * current script context. Its member AutoJSAPI starts at +8 in this build.
   * Use aligned opaque storage; no JSContext or JSAPI implementation is copied. */
  _Alignas(16) unsigned char scope[128];
  ((void (*)(void *))(base+NXS_GECKO_POPUP_AUTO_CONTEXT))(scope);
  void *context=((void *(*)(const void *))(base+NXS_GECKO_POPUP_AUTO_CONTEXT_GET))(scope);
  uint64_t value=UINT64_C(0xfff9000000000000)|!!open;
  int result=context&&((int (*)(void *,void *,void *,const void *))(base+NXS_GECKO_POPUP_OPEN_SETTER))(context,NULL,node,&value);
  ((void (*)(void *))(base+NXS_GECKO_POPUP_AUTO_API_DESTROY))(scope+8);return result;
}
static int popup_cache(struct GeckoPopup *p,const struct NXSResponse *response) {
  if(!response||response->width<1||response->height<1||response->stride!=response->width*4||
    response->size!=sizeof(*response)+(size_t)response->stride*response->height)return 0;
  uint32_t *pixels=malloc((size_t)response->stride*response->height);if(!pixels)return 0;
  memcpy(pixels,response+1,(size_t)response->stride*response->height);free(p->pixels);p->pixels=pixels;
  p->pixel_width=response->width;p->pixel_height=response->height;return 1;
}
static void popup_invalidate(struct GeckoPopup *p) {
  ((void (*)(void *,unsigned,int))(base+0x6e85c5c))(p->frame,0,1);
}
static struct NXSResponse *popup_sync(struct GeckoPopup *p) {
  struct NXSResponse *r=popup_request(p,1,0);if(!r)return NULL;
  struct GeckoPopupModel model;if(!popup_snapshot(p->node,&model))return NULL;
  if(r->parts[6].width<=0&&!popup_model_same(&p->model,&model)) {
    model.packet->control=p->id;r=exchange_bytes(model.packet,sizeof(*model.packet)+model.packet->text_size);
    if(r&&r->parts[3].x==1){popup_model_free(&p->model);p->model=model;memset(&model,0,sizeof(model));}
    else r=NULL;
  }
  popup_model_free(&model);if(!r)return NULL;
  void *manager=*(void **)(base+0xa439c38);int focused=manager&&*(void **)((char *)manager+128)==p->node;
  /* Gecko's original select actor normally closes its window on blur. Forward
   * that lifecycle to the native menu; native tracking remains in AppKit. */
  if(!focused&&r->parts[6].width>0){r=popup_request(p,14,0);if(!r)return NULL;}
  if(!!r->parts[3].y!=focused) {
    struct NXSControlInputRequest focus={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=7,.process=identity(),.kind=NXS_POPUP,.control=p->id,.focused=focused};
    if(!exchange_bytes(&focus,sizeof(focus)))return NULL;r=popup_request(p,5,0);
  }
  if(!popup_cache(p,r))return NULL;
  return r;
}
static int prepare_popup_image(void *frame) {
  if(!native_popup_frame(frame))return 0;
  struct GeckoPopup *p=popup_find(frame);
  if(!p) {
    if(!ensure_widget_lifetime()||!ensure_text_watch())return 0;
    p=calloc(1,sizeof(*p));if(!p)return 0;
    p->frame=frame;p->node=*(void **)((char *)frame+24);p->id=++next_widget;p->next=gecko_popups;gecko_popups=p;
  }
  int rect[4]={0};engine_frame_rect((void *)(base+0x6daae5c),frame,rect);p->width=rect[2]/60.;p->height=rect[3]/60.;p->owned=0;
  if(p->width<1||p->height<1||p->width!=floor(p->width)||p->height!=floor(p->height)||p->width>8192||p->height>8192)return 0;
  p->owned=popup_sync(p)!=NULL;return p->owned;
}
static int native_popup_owned(const void *frame) {struct GeckoPopup *p=popup_find(frame);return p&&p->owned;}
static int native_popup_display(void *frame,void *builder,const void *lists) {
  if(!native_popup_frame(frame)||!prepare_popup_image(frame))return 0;
  void *previous=frontend_background_frame;frontend_background_frame=frame;
  ((void (*)(void *,void *,const void *))(base+NXS_GECKO_TEXT_DISPLAY_BACKGROUND_OFFSET))(frame,builder,lists);
  frontend_background_frame=previous;return 1;
}
static int draw_popup_image(void *target,void *frame,const struct RectF *area) {
  struct GeckoPopup *p=popup_find(frame);if(!p||!p->owned||!p->pixels||p->pixel_width!=lround(area->width)||p->pixel_height!=lround(area->height))return 0;
  draw_bitmap(target,area,p->pixels,p->pixel_width,p->pixel_height);
  if(log_fd>=0)dprintf(log_fd,"%d native-select id=%llu count=%u selected=%d rect=%.0f,%.0f %dx%d\n",getpid(),(unsigned long long)p->id,p->model.packet->count,p->model.packet->selected,area->x,area->y,p->pixel_width,p->pixel_height);
  return 1;
}
static void popup_after_input(uint64_t id,const struct NXSResponse *response) {
  struct GeckoPopup *p=popup_find_id(id);if(!p||!response)return;
  int visible=response->parts[6].width>0,action=response->parts[0].width>p->actions,selected=response->parts[0].x;
  p->actions=response->parts[0].width;
  if(popup_tracking_id==id&&!response->parts[0].y)popup_tracking_id=0;
  void *node=p->node;
  ((unsigned (*)(void *))(base+NXS_GECKO_POPUP_NODE_ADDREF))(node);
  if(visible!=p->visible){p->visible=visible;popup_engine_open(node,visible);}
  p=popup_find_id(id);
  if(!p){((unsigned (*)(void *))(base+NXS_GECKO_POPUP_NODE_RELEASE))(node);return;}
  if(action&&selected>=0&&p->model.packet&&(unsigned)selected<p->model.packet->count&&!(*(uint64_t *)((char *)node+112)&16)) {
    struct GeckoPopupModel current;
    if(popup_snapshot(node,&current)) {
      int valid=popup_model_same(&p->model,&current);popup_model_free(&current);
      if(valid) {
        ((void (*)(unsigned))(base+NXS_GECKO_POPUP_USER_START))(0);
        ((void (*)(void *,int,unsigned,int,int))(base+NXS_GECKO_POPUP_POST_KEY))(node,selected,0,0,0);
        ((void (*)(unsigned))(base+NXS_GECKO_POPUP_USER_STOP))(0);
      } else note("native select stale model action discarded");
    }
  }
  ((unsigned (*)(void *))(base+NXS_GECKO_POPUP_NODE_RELEASE))(node);
  p=popup_find_id(id);if(p){popup_sync(p);popup_invalidate(p);}
}
static void native_popup_notification(void) {
  unsigned count=0;for(struct GeckoPopup *p=gecko_popups;p;p=p->next)count++;
  uint64_t *ids=calloc(count?count:1,sizeof(*ids));if(!ids)return;
  unsigned i=0;for(struct GeckoPopup *p=gecko_popups;p;p=p->next)ids[i++]=p->id;
  for(i=0;i<count;i++){struct GeckoPopup *p=popup_find_id(ids[i]);if(p)popup_after_input(ids[i],popup_request(p,5,0));}
  free(ids);
}
static int popup_event_name(const struct GeckoString *name,const char *text) {
  size_t size=strlen(text);if(name->length!=size)return 0;
  for(unsigned i=0;i<size;i++)if(name->data[i]!=(unsigned char)text[i])return 0;return 1;
}
static int popup_origin(struct GeckoPopup *p) {
  struct PopupRectI rect=((struct PopupRectI (*)(const void *))(base+NXS_GECKO_POPUP_SCREEN_RECT))(p->frame);
  struct NXSControlRequest origin={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=13,.process=identity(),.kind=NXS_POPUP,.control=p->id,.x=rect.x,.y=rect.y};
  struct NXSResponse *r=exchange_bytes(&origin,sizeof(origin));return r&&r->parts[3].x==1;
}
static struct NXSResponse *popup_pointer_request(struct GeckoPopup *p,unsigned operation,const void *event) {
  struct PointI point=((struct PointI (*)(const void *,struct RelativeTo))(base+0x6da35a8))(event,(struct RelativeTo){p->frame,0});
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,.process=identity(),.kind=NXS_POPUP,
    .control=p->id,.x=point.x/60.,.y=point.y/60.,.modifiers=widget_modifiers(event)};
  return exchange_bytes(&request,sizeof(request));
}
static void native_popup_pointer_post(const void *event) {
  struct GeckoPopup *p=popup_find_id(popup_tracking_id);if(!p)return;
  unsigned message=*(const uint16_t *)((const char *)event+18);
  if(message!=13&&(message!=14||*(const int16_t *)((const char *)event+152)!=0))return;
  uint64_t id=p->id;struct NXSResponse *r=popup_pointer_request(p,message==13?3:4,event);
  if(r){if(!r->parts[0].y)popup_tracking_id=0;popup_after_input(id,r);}
}
static uint32_t popup_chrome_event(void *document,void *target,const void *name,int bubble,int cancel,int *result) {
  if(popups_requested&&target&&*(uintptr_t *)target==base+NXS_GECKO_POPUP_SELECT_VTABLE+16) {
    int show=popup_event_name(name,"mozshowdropdown"),hide=popup_event_name(name,"mozhidedropdown");
    void *frame=*(void **)((char *)target+96);
    if((show||hide)&&prepare_popup_image(frame)) {
      struct GeckoPopup *p=popup_find(frame);uint64_t id=p->id;
      if(popup_origin(p)) {
        struct NXSResponse *r=show&&popup_mouse_event?popup_pointer_request(p,2,popup_mouse_event):popup_request(p,14,show);
        if(r&&(r->parts[3].x==1||(show&&popup_mouse_event&&r->parts[0].y))) {
          if(show&&popup_mouse_event)popup_tracking_id=id;
          popup_after_input(id,r);if(result)*result=1;return 0;
        }
      }
    }
  }
  return original_popup_chrome_event(document,target,name,bubble,cancel,result);
}
static uint32_t popup_post(void *node,void *visitor) {
  struct GeckoPopup *p=popup_find(*(void **)((char *)node+96));
  void *event=*(void **)((char *)visitor+8);int *status=(int *)((char *)visitor+24);unsigned message=*(const uint16_t *)((char *)event+18);
  if(p&&p->owned&&*status!=1&&(*(const uint8_t *)((char *)event+48)&1)&&!(*((const uint8_t *)event+49)&2)&&
      (message==2||message==4)&&prepare_popup_image(p->frame)) {
    void *manager=*(void **)(base+0xa439c38);
    if(manager&&*(void **)((char *)manager+128)==node) {
      uint64_t id=p->id;char *text=key_text(event);
      if(text&&popup_origin(p)) {
        size_t length=strlen(text),size=sizeof(struct NXSControlInputRequest)+length*2;struct NXSControlInputRequest *key=calloc(1,size);
        if(key) {
          *key=(struct NXSControlInputRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=8,.process=identity(),.kind=NXS_POPUP,.control=id,
            .type=message==4?NXS_KEY_DOWN:NXS_KEY_UP,.key=logical_key(*(uint32_t *)((char *)event+200)),.modifiers=widget_modifiers(event),.text_size=length,.unmodified_size=length};
          memcpy(key+1,text,length);memcpy((char *)(key+1)+length,text,length);struct NXSResponse *r=exchange_bytes(key,size);free(key);
          if(r){int handled=r->parts[3].x;popup_after_input(id,r);if(handled==NXS_INPUT_HANDLED)*status=1;else if(handled==NXS_INPUT_NEXT||handled==NXS_INPUT_PREVIOUS){if(advance_focus(node,handled))*status=1;}if(handled!=NXS_INPUT_UNHANDLED){free(text);return 0;}}
        }
      }
      free(text);
    }
  }
  const void *previous=popup_mouse_event;
  if(p&&p->owned&&message==15&&(*(const uint8_t *)((char *)event+48)&1)&&
      *(const int16_t *)((const char *)event+152)==0)popup_mouse_event=event;
  uint32_t result=original_popup_post(node,visitor);popup_mouse_event=previous;return result;
}
static void native_popup_forget(void *frame) {
  struct GeckoPopup **link=&gecko_popups;
  while(*link) {
    struct GeckoPopup *p=*link;if(p->frame!=frame){link=&p->next;continue;}
    *link=p->next;if(popup_tracking_id==p->id)popup_tracking_id=0;popup_request(p,14,0);popup_request(p,6,0);if(p->visible)popup_engine_open(p->node,0);
    popup_model_free(&p->model);free(p->pixels);free(p);release_idle_widget_notifier();break;
  }
}
static void native_popup_release_context(void *context) {
  struct GeckoPopup *p;
  while(1) {
    for(p=gecko_popups;p;p=p->next)if(*(void **)((char *)p->frame+40)==context)break;
    if(!p)break;native_popup_forget(p->frame);
  }
}
static struct Detour popup_detours[]={
 {NXS_GECKO_POPUP_CHROME_EVENT,gecko_popup_chrome_event_bytes,popup_chrome_event,(void **)&original_popup_chrome_event},
 {NXS_GECKO_POPUP_POST_EVENT,gecko_popup_post_event_bytes,popup_post,(void **)&original_popup_post}
};
