/* Gecko tab model/controller adaptation. Ordinary NSTabView supplies the
 * presentation, item geometry and pointer behavior. GPL-2.0-or-later. */
#include "pinned-tabs.h"
#include "../../Libraries/NativeUI/Bridge/Tabs.inc"
struct GeckoTab {void *node;NXSTabItem item;};
struct GeckoTabs {
  struct GeckoTabs *next;
  void *frame;
  uint64_t control,selected;
  struct GeckoTab *tabs;
  unsigned count,busy;
  int repaint_pending;
  uint32_t *pixels;
  int width,height,owned;
};
static struct GeckoTabs *gecko_tabs;
static uint64_t next_tab_identity;
static void *tabs_id_atom,*tabs_label_atom,*tabs_selected_atom;
static void (*original_tabs_display)(void *,void *,const void *);
static unsigned (*tabs_add_idle)(int,int (*)(void *),void *,void (*)(void *));
static int tabs_repaint_idle(void *identity) {
  for(struct GeckoTabs *f=gecko_tabs;f;f=f->next)if(f->control==(uintptr_t)identity) {
    f->repaint_pending=0;
    ((void (*)(void *,unsigned,int))(base+0x6e85c5c))(f->frame,0,1);break;
  }
  return 0;
}
static void tabs_repaint(struct GeckoTabs *f) {
  if(!f->repaint_pending)f->repaint_pending=tabs_add_idle(0,tabs_repaint_idle,(void *)(uintptr_t)f->control,NULL)!=0;
}
static struct GeckoTabs *tabs_find(const void *frame) {
  for(struct GeckoTabs *f=gecko_tabs;f;f=f->next)if(f->frame==frame)return f;
  return NULL;
}
static char *tabs_attr(void *node,void *atom) {
  static const uint16_t empty;
  struct GeckoString value={.data=&empty,.flags=1};
  ((int (*)(const void *,const void *,void *))(base+NXS_GECKO_TABS_GET_ATTR))(node,atom,&value);
  char *result=utf8_text(value.data,value.length);
  ((void (*)(void *))(base+0x3826f2c))(&value);return result;
}
static int tabs_owner(void *frame) {
  if(!tabs_requested||!frontend_text_frame(frame))return 0;
  void *node=*(void **)((char *)frame+24);
  if(!node||*(uintptr_t *)node!=base+0xa0c34f8+16)return 0;
  if(!tabs_id_atom) {
    tabs_id_atom=((void *(*)(const char *))(base+NXS_GECKO_TABS_ATOMIZE))("id");
    tabs_label_atom=((void *(*)(const char *))(base+NXS_GECKO_TABS_ATOMIZE))("label");
    tabs_selected_atom=((void *(*)(const char *))(base+NXS_GECKO_TABS_ATOMIZE))("selected");
  }
  if(!tabs_id_atom||!tabs_label_atom||!tabs_selected_atom)return 0;
  char *id=tabs_attr(node,tabs_id_atom);int match=id&&!strcmp(id,"tabbrowser-tabs");free(id);return match;
}
static void tabs_free_model(struct GeckoTab *tabs,unsigned count) {
  for(unsigned i=0;i<count;i++) {
    free((void *)tabs[i].item.title);
    ((unsigned (*)(void *))(base+NXS_GECKO_TABS_NODE_RELEASE))(tabs[i].node);
  }
  free(tabs);
}
static void tabs_release(struct GeckoTabs *f) {
  if(!--f->busy&&!f->frame){tabs_free_model(f->tabs,f->count);free(f->pixels);free(f);}
}
static void tabs_forget(void *frame) {
  struct GeckoTabs **link=&gecko_tabs;
  while(*link) {
    struct GeckoTabs *f=*link;if(f->frame!=frame){link=&f->next;continue;}
    *link=f->next;f->frame=NULL;f->busy++;
    native_tabs_request(f->control,6,0,0,1);tabs_release(f);break;
  }
}
static struct GeckoTab *tabs_snapshot(struct GeckoTabs *f,unsigned *count,uint64_t *selected) {
  static const uint16_t name[]={'t','a','b',0};
  const struct GeckoString tag={.data=name,.length=3,.flags=1};
  void *node=*(void **)((char *)f->frame+24);
  void *list=((void *(*)(void *,const void *))(base+NXS_GECKO_TABS_GET_TABS))(node,&tag);
  if(!list)return NULL;
  unsigned size=((unsigned (*)(void *))(base+NXS_GECKO_TABS_LIST_LENGTH))(list);
  struct GeckoTab *tabs=size<=4096?calloc(size?size:1,sizeof(*tabs)):NULL;unsigned done=0;*selected=0;
  if(tabs)for(;done<size;done++) {
    void *tab=((void *(*)(void *,unsigned))(base+NXS_GECKO_TABS_LIST_ITEM))(list,done);
    if(!tab||*(uintptr_t *)tab!=base+0xa0c34f8+16)break;
    char *title=tabs_attr(tab,tabs_label_atom),*active=tabs_attr(tab,tabs_selected_atom);
    uint64_t id=0;
    for(unsigned i=0;i<f->count;i++)if(f->tabs[i].node==tab){id=f->tabs[i].item.identifier;break;}
    if(!id&&next_tab_identity<UINT64_MAX)id=++next_tab_identity;
    if(!title||!active||!id){free(title);free(active);break;}
    ((unsigned (*)(void *))(base+NXS_GECKO_TABS_NODE_ADDREF))(tab);
    tabs[done]=(struct GeckoTab){tab,{sizeof(NXSTabItem),id,title,NULL}};
    if(!strcmp(active,"true"))*selected=id;free(active);
  }
  ((unsigned (*)(void *))(base+NXS_GECKO_TABS_LIST_RELEASE))(list);
  if(!tabs||done!=size||(size&&!*selected)){tabs_free_model(tabs,done);return NULL;}
  *count=size;return tabs;
}
static int tabs_sync(struct GeckoTabs *f) {
  unsigned count;uint64_t selected;
  struct GeckoTab *tabs=tabs_snapshot(f,&count,&selected);if(!tabs)return 0;
  int rectangle[4]={0};engine_frame_rect((void *)(base+0x6daae5c),f->frame,rectangle);
  int width=lround(rectangle[2]/60.),height=lround(rectangle[3]/60.);
  int okay=width>0&&height>0&&width<=8192&&height<=8192;
  NXSTabItem *items=okay?calloc(count?count:1,sizeof(*items)):NULL;
  if(items)for(unsigned i=0;i<count;i++)items[i]=tabs[i].item;
  struct NXSResponse *r=items?native_tabs_request(f->control,1,width,height,1):NULL;
  if(r&&f->frame)r=native_tabs_model(f->control,items,count,selected,1);else r=NULL;
  free(items);
  uint32_t *pixels=NULL;
  if(r&&f->frame&&r->width==width&&r->height==height&&r->stride==width*4&&r->size==sizeof(*r)+(size_t)r->stride*height) {
    pixels=malloc((size_t)r->stride*height);if(pixels)memcpy(pixels,r+1,(size_t)r->stride*height);
  }
  if(!pixels){tabs_free_model(tabs,count);return 0;}
  int changed=f->count!=count||f->selected!=selected||f->width!=width||f->height!=height;
  for(unsigned i=0;!changed&&i<count;i++)changed=f->tabs[i].item.identifier!=tabs[i].item.identifier||strcmp(f->tabs[i].item.title,tabs[i].item.title);
  tabs_free_model(f->tabs,f->count);free(f->pixels);
  f->tabs=tabs;f->count=count;f->selected=selected;f->pixels=pixels;f->width=width;f->height=height;f->owned=1;
  /* Gecko may damage only the former child label. Repaint the whole owner
   * through the real UI queue after this display-list transaction commits. */
  if(changed&&f->frame)tabs_repaint(f);
  if(tabs_trace_enabled&&log_fd>=0) {
    struct NXSTabWireState state;
    if(native_tabs_state(f->control,&state)) {
      dprintf(log_fd,"tabs-state id=%llu count=%u selected=%d width=%d height=%d\n",(unsigned long long)f->control,state.count,state.selected_index,width,height);
      for(unsigned i=0;i<count;i++) {
        struct NXSRectD rect;
        if(native_tabs_item_rect(f->control,tabs[i].item.identifier,&rect))dprintf(log_fd,"tabs-item id=%llu index=%u native_id=%llu x=%.3f y=%.3f width=%.3f height=%.3f\n",(unsigned long long)f->control,i,(unsigned long long)tabs[i].item.identifier,rect.x,rect.y,rect.width,rect.height);
      }
    }
  }
  return 1;
}
static int tabs_frame_owned(const void *frame) {
  struct GeckoTabs *f=tabs_requested?tabs_find(frame):NULL;return f&&f->owned;
}
static int tabs_draw(void *target,void *frame,const struct RectF *area) {
  struct GeckoTabs *f=tabs_find(frame);
  if(!f||!f->owned||!f->pixels||fabsf(frame_scale(frame)-1)>0.000001f)return 0;
  draw_bitmap(target,area,f->pixels,f->width,f->height);return 1;
}
static void tabs_display(void *frame,void *builder,const void *lists) {
  if(!tabs_owner(frame)||fabsf(frame_scale(frame)-1)>0.000001f||!ensure_widget_lifetime()||!ensure_text_watch())goto fallback;
  struct GeckoTabs *f=tabs_find(frame);
  if(!f) {
    f=calloc(1,sizeof(*f));if(!f)goto fallback;
    f->frame=frame;f->control=++next_widget;f->next=gecko_tabs;gecko_tabs=f;
  }
  f->busy++;f->owned=0;int okay=tabs_sync(f);
  if(okay&&f->frame) {
    void *previous=frontend_background_frame;frontend_background_frame=frame;
    ((void (*)(void *,void *,const void *))(base+NXS_GECKO_TEXT_DISPLAY_BACKGROUND_OFFSET))(frame,builder,lists);
    frontend_background_frame=previous;
  }
  int live=f->frame!=NULL;tabs_release(f);
  if(okay||!live)return;
 fallback:original_tabs_display(frame,builder,lists);
}
static void tabs_native_notification(void) {
  for(struct GeckoTabs *f=gecko_tabs;f;f=f->next)
    ((void (*)(void *,unsigned,int))(base+0x6e85c5c))(f->frame,0,1);
}
static uint64_t tabs_pointer_target(void *frame,void *event) {
  struct GeckoTabs *f=tabs_requested?tabs_find(frame):NULL;
  return f&&f->owned&&*(const uint16_t *)((char *)event+18)==15?f->control:0;
}
static void tabs_pointer_post(uint64_t target,void *event,int status) {
  /* The original dispatch may destroy/recreate a frame at the same address.
   * Preserve the exact binding identity across it, not a borrowed frame. */
  struct GeckoTabs *f=NULL;
  for(struct GeckoTabs *candidate=gecko_tabs;target&&candidate;candidate=candidate->next)if(candidate->control==target){f=candidate;break;}
  if(!f||!f->owned||status==1||*(const uint16_t *)((char *)event+18)!=15||
     !(*(const uint8_t *)((char *)event+48)&1)||*(const int16_t *)((char *)event+152)!=0)return;
  f->busy++;
  struct Widget owner={.frame=f->frame};struct PointI point=widget_point(&owner,event);
  unsigned clicks=*(const uint32_t *)((char *)event+236);
  struct NXSResponse *r=tabs_sync(f)&&f->frame?native_pointer_press(NXS_TABVIEW,f->control,point.x/60.,point.y/60.,widget_modifiers(event),clicks?clicks:1):NULL;
  struct NXSTabWireState state={0};int ready=0;
  for(unsigned i=0;r&&f->frame&&i<100;i++) {
    r=native_tabs_request(f->control,37,0,0,1);
    if(!r||r->parts[3].x!=1||r->size!=sizeof(*r)+sizeof(state))break;
    if(!r->parts[0].y){memcpy(&state,r+1,sizeof(state));ready=1;break;}
    struct timespec pause={.tv_nsec=2000000};nanosleep(&pause,NULL);
  }
  if(ready&&f->frame&&state.selected!=f->selected) {
    void *node=NULL;
    for(unsigned i=0;i<f->count;i++)if(f->tabs[i].item.identifier==state.selected){node=f->tabs[i].node;break;}
    if(node&&*(void **)((char *)node+96)) {
      ((unsigned (*)(void *))(base+NXS_GECKO_TABS_NODE_ADDREF))(node);
      if(log_fd>=0)dprintf(log_fd,"tabs-select id=%llu selected=%llu\n",(unsigned long long)f->control,(unsigned long long)state.selected);
      /* The original XUL activation dispatches down/up/click and invokes the
       * real browser listeners/controller. No gBrowser state is duplicated. */
      ((void (*)(void *,unsigned,int))(base+NXS_GECKO_TABS_XUL_CLICK))(node,1,1);
      ((unsigned (*)(void *))(base+NXS_GECKO_TABS_NODE_RELEASE))(node);
    }
  }
  if(f->frame)((void (*)(void *,unsigned,int))(base+0x6e85c5c))(f->frame,0,1);
  tabs_release(f);
}
static struct Detour tabs_detours[]={
  {NXS_GECKO_TABS_FLEX_DISPLAY,gecko_tabs_flex_display_bytes,tabs_display,(void **)&original_tabs_display}
};
static int prepare_tabs(void) {
  tabs_add_idle=dlsym(RTLD_DEFAULT,"g_idle_add_full");
  struct NXSResponse *r=exchange((struct NXSRequest){.magic=NXS_CHROMIUM_MAGIC,.operation=7,.process=identity()});
  return tabs_add_idle&&r&&((unsigned)r->parts[4].x&NXS_TAB_ITEMS)&&guard_tabs_calls()&&
    prepare_detours(tabs_detours,sizeof(tabs_detours)/sizeof(*tabs_detours));
}
