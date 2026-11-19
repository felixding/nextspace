/* Gecko select models and command binding. Existing NSPopUpButton/NSMenu own
 * all control drawing, menu geometry, hit testing and keyboard behavior. */
#include "pinned-popups.h"
struct GeckoPopupModel {
  struct NXSControlPopupRequest *packet;
  void **nodes;
  int *indices,selected_index;
  void *selected_node;
  char *title;
};
struct GeckoPopup {
  struct GeckoPopup *next;
  void *frame,*node;
  uint64_t id;
  double width,height,actions;
  double preferred_width,preferred_height;
  uint32_t model_epoch;
  struct GeckoPopupModel model;
  uint32_t *pixels;
  int pixel_width,pixel_height,owned,visible;
};
struct PopupRectI {int x,y,width,height;};
static struct GeckoPopup *gecko_popups;
static void *popup_label_atom,*popup_hidden_atom;
static __thread const void *popup_mouse_event;
static uint64_t popup_tracking_id;
static uint64_t popup_pending_press;
static uint32_t (*original_popup_chrome_event)(void *,void *,const void *,int,int,int *);
static uint32_t (*original_popup_post)(void *,void *);
static int (*original_popup_longest)(void *,void *);
static int (*original_popup_has_button)(void *);
static void (*original_popup_attribute_changed)(void *,void *,int,void *,unsigned,void *);
static void (*original_popup_character_changed)(void *,void *,const void *);
static void (*original_popup_content_removed)(void *,void *,const void *);
static void (*original_popup_content_added)(void *,void *,int);
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
  if(!popups_requested||!native_form_process()||!frame||*(const uintptr_t *)frame!=base+NXS_GECKO_POPUP_FRAME_VTABLE+16)return 0;
  void *node=*(void **)((const char *)frame+24);
  if(!node||*(uintptr_t *)node!=base+NXS_GECKO_POPUP_SELECT_VTABLE+16||*(void **)((char *)node+96)!=frame)return 0;
  const void *style=*(void **)((const char *)frame+32),*display=*(void **)((const char *)style+80);
  /* Let Gecko resolve appearance:auto and its native-widget eligibility. */
  return frame_scale_supported(frame)&&original_frontend_themed(frame,display,NULL);
}
static struct NXSResponse *popup_request(struct GeckoPopup *p,unsigned op,int value) {
  if(op==1&&!native_control_presentation(NXS_POPUP,p->id,frame_scale(p->frame)))return NULL;
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=op,.process=identity(),
    .kind=NXS_POPUP,.control=p->id,.width=p->width,.height=p->height,.enabled=!(*(uint64_t *)((char *)p->node+112)&16),.state=value};
  return exchange_bytes(&request,sizeof(request));
}
static void popup_model_free(struct GeckoPopupModel *model) {
  if(model->packet)for(unsigned i=0;i<model->packet->count;i++)
    ((unsigned (*)(void *))(base+NXS_GECKO_POPUP_NODE_RELEASE))(model->nodes[i]);
  if(model->selected_node)((unsigned (*)(void *))(base+NXS_GECKO_POPUP_NODE_RELEASE))(model->selected_node);
  free(model->nodes);free(model->indices);free(model->title);free(model->packet);memset(model,0,sizeof(*model));
}
static char *popup_label(void *node,int option) {
  static const uint16_t empty;
  struct GeckoString label={.data=&empty,.flags=1};
  ((int (*)(const void *,const void *,void *))(base+NXS_GECKO_POPUP_GET_ATTR))(node,popup_label_atom,&label);
  if(option&&!label.length)((void (*)(void *,void *))(base+NXS_GECKO_POPUP_OPTION_TEXT))(node,&label);
  char *title=utf8_text(label.data,label.length);((void (*)(void *))(base+0x3826f2c))(&label);return title;
}
static int popup_visible(void *element,void *select) {
  /* Application data only: native DOM ancestry and original computed style
   * determine whether an option/group/separator belongs in the menu model.
   * Disabled entries remain visible. No menu layout or navigation is copied. */
  static const uint16_t empty;
  for(unsigned depth=0;element&&element!=select&&depth<4096;depth++) {
    if(depth&&*(uintptr_t *)element!=base+NXS_GECKO_POPUP_GROUP_VTABLE+16)return 0;
    struct GeckoString hidden={.data=&empty,.flags=1};
    int present=((int (*)(const void *,const void *,void *))(base+NXS_GECKO_POPUP_GET_ATTR))(element,popup_hidden_atom,&hidden);
    ((void (*)(void *))(base+0x3826f2c))(&hidden);if(present)return 0;
    /* The guarded engine's PseudoStyleRequest is 16 bytes; 95 is NotPseudo,
     * StyleType::All is 1. Its original style ownership/release stays native. */
    uint64_t pseudo[2]={95,0};
    void *style=((void *(*)(const void *,const void *,unsigned))(base+NXS_GECKO_POPUP_COMPUTED_STYLE))(element,pseudo,1);
    if(!style)return 0;
    int display=*(const uint16_t *)*(const void **)((const char *)style+80);
    ((void (*)(const void *))(base+NXS_GECKO_POPUP_STYLE_RELEASE))(style);if(!display)return 0;
    element=*(void **)((char *)element+48);
    if(element&&!(*(uint8_t *)((char *)element+28)&16))return 0;
  }
  return element==select;
}
static int popup_snapshot(void *node,struct GeckoPopupModel *model) {
  memset(model,0,sizeof(*model));
  if(!popup_label_atom)popup_label_atom=((void *(*)(const char *))(base+NXS_GECKO_POPUP_ATOMIZE))("label");
  if(!popup_hidden_atom)popup_hidden_atom=((void *(*)(const char *))(base+NXS_GECKO_POPUP_ATOMIZE))("hidden");
  if(!popup_label_atom||!popup_hidden_atom)return 0;
  static const uint16_t wildcard[]={'*',0};
  const struct GeckoString tag={.data=wildcard,.length=1,.flags=1};
  void *list=((void *(*)(void *,const void *))(base+NXS_GECKO_POPUP_GET_ELEMENTS))(node,&tag);if(!list)return 0;
  unsigned count=((unsigned (*)(void *))(base+NXS_GECKO_POPUP_LIST_LENGTH))(list);
  int okay=count<=4096;
  if(okay) {
    model->packet=native_popup_model_new(-1);model->nodes=calloc(count?count:1,sizeof(void *));model->indices=calloc(count?count:1,sizeof(int));
    okay=model->packet&&model->nodes&&model->indices;
  }
  if(okay) {
    model->selected_index=((int (*)(void *))(base+NXS_GECKO_POPUP_SELECTED_INDEX))(node);
    void *options=*(void **)((char *)node+264);
    if(model->selected_index>=0) {
      model->selected_node=((void *(*)(void *,unsigned))(base+NXS_GECKO_POPUP_LIST_ITEM))(options,model->selected_index);
      if(model->selected_node)((unsigned (*)(void *))(base+NXS_GECKO_POPUP_NODE_ADDREF))(model->selected_node);else okay=0;
    }
  }
  for(unsigned i=0;okay&&i<count;i++) {
    void *item=((void *(*)(void *,unsigned))(base+NXS_GECKO_POPUP_LIST_ITEM))(list,i);if(!item){okay=0;break;}
    uintptr_t table=*(uintptr_t *)item;
    int option=table==base+NXS_GECKO_POPUP_OPTION_VTABLE+16,group=table==base+NXS_GECKO_POPUP_GROUP_VTABLE+16,separator=table==base+NXS_GECKO_POPUP_HR_VTABLE+16;
    if((!option&&!group&&!separator)||!popup_visible(item,node))continue;
    unsigned row=model->packet->count;
    if(separator&&row) {
      void *previous=model->nodes[row-1];
      if(*(uintptr_t *)previous==base+NXS_GECKO_POPUP_HR_VTABLE+16&&*(void **)((char *)previous+48)==*(void **)((char *)item+48))continue;
    }
    int index=option?((int (*)(void *))(base+NXS_GECKO_POPUP_OPTION_INDEX))(item):-1;
    if(option&&index<0)continue;
    char *title=separator?strdup(""):popup_label(item,option);uint8_t disabled=1;
    if(option) {
      uint32_t result=((uint32_t (*)(void *,int,void *))(base+NXS_GECKO_POPUP_OPTION_DISABLED))(node,index,&disabled);
      if(result&0x80000000u){free(title);okay=0;break;}
    }
    if(!title||!native_popup_model_append(model->packet,title,!disabled,separator)){free(title);okay=0;break;}
    free(title);((unsigned (*)(void *))(base+NXS_GECKO_POPUP_NODE_ADDREF))(item);model->nodes[row]=item;model->indices[row]=index;
    if(option&&index==model->selected_index)model->packet->selected=row;
  }
  ((unsigned (*)(void *))(base+NXS_GECKO_POPUP_LIST_RELEASE))(list);
  if(okay&&model->selected_node&&model->packet->selected<0) {
    model->title=popup_label(model->selected_node,1);okay=model->title!=NULL;
  }
  if(!okay)popup_model_free(model);return okay;
}
static int popup_model_same(const struct GeckoPopupModel *a,const struct GeckoPopupModel *b) {
  return a->packet&&b->packet&&a->packet->count==b->packet->count&&a->packet->selected==b->packet->selected&&
    a->selected_index==b->selected_index&&a->selected_node==b->selected_node&&
    (a->title&&b->title?!strcmp(a->title,b->title):a->title==b->title)&&
    a->packet->text_size==b->packet->text_size&&!memcmp(a->packet+1,b->packet+1,a->packet->text_size)&&
    !memcmp(a->indices,b->indices,a->packet->count*sizeof(int))&&!memcmp(a->nodes,b->nodes,a->packet->count*sizeof(void *));
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
  uint32_t epoch=atomic_load(&native_host_epoch);
  if(p->model_epoch!=epoch)p->actions=r->parts[0].width;
  struct GeckoPopupModel model;if(!popup_snapshot(p->node,&model))return NULL;
  if(model.title&&r->parts[1].x!=1){popup_model_free(&model);return NULL;}
  if(r->parts[6].width<=0&&(p->model_epoch!=epoch||!popup_model_same(&p->model,&model))) {
    model.packet->control=p->id;r=exchange_bytes(model.packet,sizeof(*model.packet)+model.packet->text_size);
    if(r&&r->parts[3].x==1&&r->parts[1].x==1)r=native_popup_title(p->id,model.title);
    if(r&&r->parts[3].x==1){popup_model_free(&p->model);p->model=model;p->model_epoch=epoch;memset(&model,0,sizeof(model));}
    else r=NULL;
  }
  popup_model_free(&model);if(!r)return NULL;
  void *manager=*(void **)(base+0xa439c38);int focused=manager&&*(void **)((char *)manager+128)==p->node;
  /* Gecko's original select actor normally closes its window on blur. Forward
   * that lifecycle to the native menu; native tracking remains in AppKit. */
  if(!focused&&r->parts[6].width>0){r=popup_request(p,14,0);if(!r)return NULL;}
  if(!!r->parts[3].y!=focused) {
    struct NXSControlInputRequest focus={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=7,.process=identity(),.kind=NXS_POPUP,.control=p->id,.focused=focused};
    if(!exchange_bytes(&focus,sizeof(focus)))return NULL;r=popup_request(p,1,0);
  }
  if(!popup_cache(p,r))return NULL;
  return r;
}
static struct GeckoPopup *popup_bind(void *frame) {
  if(!native_popup_frame(frame))return NULL;
  struct GeckoPopup *p=popup_find(frame);
  if(!p) {
    if(!ensure_widget_lifetime()||!ensure_text_watch())return NULL;
    p=calloc(1,sizeof(*p));if(!p)return NULL;
    p->frame=frame;p->node=*(void **)((char *)frame+24);p->id=++next_widget;p->next=gecko_popups;gecko_popups=p;
  }
  return p;
}
static int popup_preferred(void *frame,struct LogicalSizeI *size) {
  struct GeckoPopup *p=popup_bind(frame);if(!p||(*((const unsigned char *)frame+108)&1))return 0;
  /* The one-unit probe hosts only the native model before first reflow.
   * NSPopUpButtonCell::cellSize supplies all title/arrow/border metrics. */
  if(p->width<1||p->height<1)p->width=p->height=frame_scale(frame);
  struct NXSResponse *r=popup_sync(p);if(!r)return 0;
  double width=r->parts[1].width,height=r->parts[1].height;
  if(!isfinite(width)||!isfinite(height)||width<1||height<1||width>8192||height>8192)return 0;
  p->preferred_width=width;p->preferred_height=height;
  *size=(struct LogicalSizeI){ceil(width)*frame_units(frame),ceil(height)*frame_units(frame)};return 1;
}
static int popup_longest(void *frame,void *rendering) {
  struct LogicalSizeI preferred;
  if(!popup_preferred(frame,&preferred))return original_popup_longest(frame,rendering);
  struct IntrinsicOffsetsI offsets=((struct IntrinsicOffsetsI (*)(void *,int))(base+0x6e83058))(frame,0x3fffffff);
  /* Gecko still owns contain/field-sizing, CSS min/max, flex/grid and box
   * sizing. The complete native control owns its arrow, so the separate
   * engine dropmarker allocation is suppressed below. */
  int content=preferred.inline_size-offsets.padding-offsets.border;
  return content>0?content:0;
}
static int popup_has_button(void *frame) {
  struct GeckoPopup *p=popup_find(frame);
  return p&&p->preferred_width>0&&channel>=0&&native_popup_frame(frame)?0:original_popup_has_button(frame);
}
static void popup_reflow(struct GeckoPopup *p) {
  if(!p||!native_popup_frame(p->frame))return;
  void *context=*(void **)((char *)p->frame+40),*shell=*(void **)((char *)context+32);
  if(shell)((void (*)(void *,void *,unsigned,uint64_t,unsigned))(base+NXS_GECKO_HTML_BUTTON_REFLOW_OFFSET))(shell,p->frame,2,0x400,2);
}
static uint64_t popup_mutation(void *node,void *changed) {
  for(struct GeckoPopup *p=gecko_popups;p;p=p->next)if(p->node==node) {
    /* Keep Gecko's existing mutation observer and anonymous-tree boundary.
     * Only schedule its ordinary intrinsic-size invalidation; the next layout
     * obtains the complete model and preferred size from the native cell. */
    return ((int (*)(const void *,const void *))(base+NXS_GECKO_POPUP_SAME_ANONYMOUS_TREE))(node,changed)?p->id:0;
  }
  return 0;
}
static void popup_attribute_changed(void *node,void *element,int ns,void *attribute,unsigned change,void *old) {
  uint64_t id=popup_mutation(node,element);
  original_popup_attribute_changed(node,element,ns,attribute,change,old);
  native_list_model_changed(node);
  if(id)popup_reflow(popup_find_id(id));
}
static void popup_character_changed(void *node,void *content,const void *info) {
  uint64_t id=popup_mutation(node,content);
  original_popup_character_changed(node,content,info);
  native_list_model_changed(node);
  if(id)popup_reflow(popup_find_id(id));
}
static void popup_content_removed(void *node,void *child,const void *info) {
  uint64_t id=popup_mutation(node,child);
  original_popup_content_removed(node,child,info);
  native_list_model_changed(node);
  if(id)popup_reflow(popup_find_id(id));
}
static void popup_content_added(void *node,void *child,int append) {
  uint64_t id=popup_mutation(node,child);
  original_popup_content_added(node,child,append);
  native_list_model_changed(node);
  if(id)popup_reflow(popup_find_id(id));
}
static int prepare_popup_image(void *frame) {
  struct GeckoPopup *p=popup_bind(frame);if(!p)return 0;
  p->owned=0;struct NXSRectD viewport;
  if(!native_frame_viewport(frame,&viewport))return 0;
  p->width=viewport.width;p->height=viewport.height;
  struct NXSResponse *r=popup_sync(p);p->owned=r!=NULL;
  if(r&&(p->preferred_width!=r->parts[1].width||p->preferred_height!=r->parts[1].height)) {
    p->preferred_width=r->parts[1].width;p->preferred_height=r->parts[1].height;
    popup_reflow(p);
  }
  return p->owned;
}
static int native_popup_owned(const void *frame) {struct GeckoPopup *p=popup_find(frame);return p&&p->owned;}
static int native_popup_display(void *frame,void *builder,const void *lists) {
  if(!native_popup_frame(frame)||!prepare_popup_image(frame))return 0;
  void *previous=frontend_background_frame;frontend_background_frame=frame;
  ((void (*)(void *,void *,const void *))(base+NXS_GECKO_TEXT_DISPLAY_BACKGROUND_OFFSET))(frame,builder,lists);
  frontend_background_frame=previous;return 1;
}
static int draw_popup_image(void *target,void *frame,const struct RectF *area) {
  struct GeckoPopup *p=popup_find(frame);if(!p||!p->owned||!p->pixels)return 0;
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
      int valid=popup_model_same(&p->model,&current),index=valid?p->model.indices[selected]:-1;popup_model_free(&current);
      if(valid&&index>=0) {
        ((void (*)(unsigned))(base+NXS_GECKO_POPUP_USER_START))(0);
        ((void (*)(void *,int,unsigned,int,int))(base+NXS_GECKO_POPUP_POST_KEY))(node,index,0,0,0);
        ((void (*)(unsigned))(base+NXS_GECKO_POPUP_USER_STOP))(0);
      } else note("native select stale model action discarded");
    }
  }
  ((unsigned (*)(void *))(base+NXS_GECKO_POPUP_NODE_RELEASE))(node);
  p=popup_find_id(id);if(p){popup_sync(p);popup_invalidate(p);}
}
static void native_popup_notification(const struct NXSInvalidations *invalidations) {
  /* A closed, unchanged select must not rebuild its display list whenever
   * another native control animates. The shared receipt identifies its owner. */
  unsigned count=0;for(struct GeckoPopup *p=gecko_popups;p;p=p->next)
    if(native_invalidation_contains(invalidations,NXS_POPUP,p->id))count++;
  uint64_t *ids=calloc(count?count:1,sizeof(*ids));if(!ids)return;
  unsigned i=0;for(struct GeckoPopup *p=gecko_popups;p;p=p->next)
    if(native_invalidation_contains(invalidations,NXS_POPUP,p->id))ids[i++]=p->id;
  for(i=0;i<count;i++){struct GeckoPopup *p=popup_find_id(ids[i]);if(p)popup_after_input(ids[i],popup_request(p,5,0));}
  free(ids);
}
static void native_popup_dismiss(void) {
  for(struct GeckoPopup *p=gecko_popups;p;p=p->next)if(p->visible) {
    uint64_t id=p->id;
    popup_after_input(id,popup_request(p,14,0));
    return;
  }
}
static int popup_event_name(const struct GeckoString *name,const char *text) {
  size_t size=strlen(text);if(name->length!=size)return 0;
  for(unsigned i=0;i<size;i++)if(name->data[i]!=(unsigned char)text[i])return 0;return 1;
}
static int popup_origin(struct GeckoPopup *p) {
  struct NXSRectD bounds;uint64_t id=p->id;
  if(!gecko_frame_screen_bounds(p->frame,&bounds))return 0;
  p=popup_find_id(id);
  return p&&native_popup_binding_bounds(NXS_POPUP,id,bounds);
}
static struct NXSResponse *popup_pointer_request(struct GeckoPopup *p,unsigned operation,const void *event) {
  struct PointI point=((struct PointI (*)(const void *,struct RelativeTo))(base+0x6da35a8))(event,(struct RelativeTo){p->frame,0});
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,.process=identity(),.kind=NXS_POPUP,
    .control=p->id,.x=point.x/frame_units(p->frame),.y=point.y/frame_units(p->frame),.modifiers=widget_modifiers(event)};
  return exchange_bytes(&request,sizeof(request));
}
static void native_popup_pointer_post(const void *event) {
  unsigned message=*(const uint16_t *)((const char *)event+18);
  if(message!=13&&(message!=14||*(const int16_t *)((const char *)event+152)!=0))return;
  if(message==14)popup_pending_press=0;
  struct GeckoPopup *p=popup_find_id(popup_tracking_id);if(!p)return;
  uint64_t id=p->id;struct NXSResponse *r=popup_pointer_request(p,message==13?3:4,event);
  if(r){if(!r->parts[0].y)popup_tracking_id=0;popup_after_input(id,r);}
}
static uint32_t popup_chrome_event(void *document,void *target,const void *name,int bubble,int cancel,int *result) {
  if(popups_requested&&target&&*(uintptr_t *)target==base+NXS_GECKO_POPUP_SELECT_VTABLE+16) {
    int show=popup_event_name(name,"mozshowdropdown"),hide=popup_event_name(name,"mozhidedropdown");
    void *frame=*(void **)((char *)target+96);
    if((show||hide)&&prepare_popup_image(frame)) {
      struct GeckoPopup *p=popup_find(frame);uint64_t id=p->id;
      if(hide&&popup_pending_press==id)popup_pending_press=0;
      /* A native empty model has no menu to open. Keep the original engine
       * lifecycle closed instead of creating a second, empty actor window. */
      if(show&&p->model.packet&&!p->model.packet->count){popup_engine_open(target,0);if(result)*result=1;return 0;}
      if(show&&paint_forms_only&&popup_mouse_event) {
        /* Finish Gecko's opening click before the native menu can receive it. */
        popup_pending_press=id;
        if(result)*result=1;
        return 0;
      }
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
  if(lists_requested&&native_list_post(node,visitor))return 0;
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
  int primary=(message==14||message==15)&&(*(const uint8_t *)((char *)event+48)&1)&&
      *(const int16_t *)((const char *)event+152)==0;
  if(primary&&message==15&&p&&p->owned) {
    popup_pending_press=0;
    popup_mouse_event=event;
  }
  uint64_t pending=primary&&message==14&&p&&p->id==popup_pending_press?p->id:0;
  uint32_t result=original_popup_post(node,visitor);popup_mouse_event=previous;
  if(pending) {
    popup_pending_press=0;
    p=popup_find_id(pending);
    if(p&&prepare_popup_image(p->frame)&&popup_origin(p))
      popup_after_input(pending,popup_request(p,14,1));
  }
  return result;
}
static void native_popup_forget(void *frame) {
  struct GeckoPopup **link=&gecko_popups;
  while(*link) {
    struct GeckoPopup *p=*link;if(p->frame!=frame){link=&p->next;continue;}
    *link=p->next;if(popup_tracking_id==p->id)popup_tracking_id=0;
    if(popup_pending_press==p->id)popup_pending_press=0;
    popup_request(p,14,0);popup_request(p,6,0);if(p->visible)popup_engine_open(p->node,0);
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
 {NXS_GECKO_POPUP_LONGEST,gecko_popup_longest_bytes,popup_longest,(void **)&original_popup_longest},
 {NXS_GECKO_POPUP_HAS_BUTTON,gecko_popup_has_button_bytes,popup_has_button,(void **)&original_popup_has_button},
 {NXS_GECKO_POPUP_ATTRIBUTE_CHANGED,gecko_popup_attribute_changed_bytes,popup_attribute_changed,(void **)&original_popup_attribute_changed},
 {NXS_GECKO_POPUP_CHARACTER_CHANGED,gecko_popup_character_changed_bytes,popup_character_changed,(void **)&original_popup_character_changed},
 {NXS_GECKO_POPUP_CONTENT_REMOVED,gecko_popup_content_removed_bytes,popup_content_removed,(void **)&original_popup_content_removed},
 {NXS_GECKO_POPUP_CONTENT_ADDED,gecko_popup_content_added_bytes,popup_content_added,(void **)&original_popup_content_added},
 {NXS_GECKO_POPUP_CHROME_EVENT,gecko_popup_chrome_event_bytes,popup_chrome_event,(void **)&original_popup_chrome_event},
 {NXS_GECKO_POPUP_POST_EVENT,gecko_popup_post_event_bytes,popup_post,(void **)&original_popup_post}
};
