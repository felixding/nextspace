/* Browser tab model/controller adaptation. Ordinary NSTabView owns all tab
 * presentation and hit testing. GPL-2.0-or-later. */
#include "pinned-tabs.h"
struct ViewsTabIdentity {struct ViewsTabIdentity *next;void *tab;uint64_t identifier;};
struct ViewsTabs {
  struct ViewsTabs *next;
  void *view,*strip,*controller;
  uint64_t control,selected;
  NXSTabItem *items;
  struct ViewsTabIdentity *identities;
  unsigned count,busy;
  int owned,width,height;
};
static struct ViewsTabs *views_tabs;
static uint64_t next_tab_identity;
static void (*original_tabs_layout)(void *);
static void *(*original_tabs_target)(void *,void *,const void *);
static int (*original_tabs_content_area)(void *,const void *);
static void (*original_tabs_paint)(void *,void *),(*original_tabs_children)(void *,const void *);
static int (*original_tabs_press)(void *,const void *);
static void (*original_tabs_data)(void *,int,const void *);
static void (*original_tabs_model_changed)(void *,void *,const void *,const void *);
static struct ViewsTabs *tabs_find(void *view) {
  for(struct ViewsTabs *f=views_tabs;f;f=f->next)if(f->view==view)return f;
  return NULL;
}
static void tabs_free_items(NXSTabItem *items,unsigned count)
{for(unsigned i=0;i<count;i++)free((void *)items[i].title);free(items);}
static void tabs_release(struct ViewsTabs *f)
{
  if(!--f->busy&&!f->view) {
    tabs_free_items(f->items,f->count);
    while(f->identities){struct ViewsTabIdentity *item=f->identities;f->identities=item->next;free(item);}
    free(f);
  }
}
static void tabs_forget(void *view) {
  /* TabStrip::tab_at's guarded -24 adjustment identifies the existing View
   * base. Retire its opaque ID before the browser can reuse the allocation. */
  for(struct ViewsTabs *f=views_tabs;f;f=f->next) {
    struct ViewsTabIdentity **entry=&f->identities;
    while(*entry) {
      if((char *)(*entry)->tab+24!=(char *)view){entry=&(*entry)->next;continue;}
      struct ViewsTabIdentity *old=*entry;*entry=old->next;free(old);break;
    }
  }
  struct ViewsTabs **link=&views_tabs;
  while(*link) {
    struct ViewsTabs *f=*link;if(f->view!=view){link=&f->next;continue;}
    *link=f->next;f->view=NULL;f->busy++;
    native_tabs_request(f->control,6,0,0,1);tabs_release(f);break;
  }
}
static uint64_t tabs_identity(struct ViewsTabs *f,void *tab) {
  for(struct ViewsTabIdentity *item=f->identities;item;item=item->next)if(item->tab==tab)return item->identifier;
  if(next_tab_identity==UINT64_MAX)return 0;
  struct ViewsTabIdentity *item=calloc(1,sizeof(*item));if(!item)return 0;
  *item=(struct ViewsTabIdentity){f->identities,tab,++next_tab_identity};f->identities=item;return item->identifier;
}
static NXSTabItem *tabs_snapshot(struct ViewsTabs *f,unsigned *count,uint64_t *selected) {
  int size=((int (*)(void *))(base+NXS_VIEWS_TABS_COUNT))(f->view);
  if(size<0||size>4096)return NULL;
  NXSTabItem *items=calloc(size?size:1,sizeof(*items));if(!items)return NULL;
  *count=size;*selected=0;
  for(int i=0;i<size;i++) {
    void *tab=((void *(*)(void *,int))(base+NXS_VIEWS_TABS_AT))(f->strip,i);
    /* The guarded native OnTabDataChanged loads its existing title Label
     * at +1536. GetText supplies Chromium's displayed/localized title. */
    void *label=tab?*(void **)((char *)tab+1536):NULL;
    if(!label){tabs_free_items(items,i);return NULL;}
    struct ViewsString title=((struct ViewsString (*)(void *))(base+NXS_VIEWS_TABS_LABEL))(label);
    if(title.length>65536||(!title.data&&title.length)){tabs_free_items(items,i);return NULL;}
    char *text=encode_text(title.data,title.length,0);
    if(!text){tabs_free_items(items,i);return NULL;}
    uint64_t identifier=tabs_identity(f,tab);
    if(!identifier){free(text);tabs_free_items(items,i);return NULL;}
    items[i]=(NXSTabItem){sizeof(NXSTabItem),identifier,text,NULL};
    if(((int (*)(void *))(base+NXS_VIEWS_TABS_ACTIVE))(tab))*selected=identifier;
  }
  if(size&&!*selected){tabs_free_items(items,size);return NULL;}
  return items;
}
static int tabs_same(struct ViewsTabs *f,NXSTabItem *items,unsigned count,uint64_t selected) {
  if(f->count!=count||f->selected!=selected)return 0;
  for(unsigned i=0;i<count;i++)if(f->items[i].identifier!=items[i].identifier||strcmp(f->items[i].title,items[i].title))return 0;
  return 1;
}
static void tabs_repaint_model(struct ViewsTabs *f) {
  unsigned count;uint64_t selected;NXSTabItem *items=tabs_snapshot(f,&count,&selected);
  if(items) {
    if(!tabs_same(f,items,count,selected))views_schedule(f->view);
    tabs_free_items(items,count);
  }
}
static void tabs_data(void *tab,int change,const void *data) {
  original_tabs_data(tab,change,data);
  for(struct ViewsTabs *f=views_tabs;f;f=f->next)
    for(struct ViewsTabIdentity *item=f->identities;item;item=item->next)
      if(item->tab==tab){tabs_repaint_model(f);break;}
}
static void tabs_model_changed(void *controller,void *model,const void *change,const void *selection) {
  original_tabs_model_changed(controller,model,change,selection);
  for(struct ViewsTabs *f=views_tabs;f;f=f->next)if(f->controller==controller)tabs_repaint_model(f);
}
static struct NXSResponse *tabs_sync(struct ViewsTabs *f,int *changed) {
  unsigned count;uint64_t selected;NXSTabItem *items=tabs_snapshot(f,&count,&selected);if(!items)return NULL;
  const struct Rect bounds=*(struct Rect *)((char *)f->view+440);
  struct NXSResponse *r=native_tabs_request(f->control,1,bounds.width,bounds.height,1);
  if(r&&r->width>0&&f->view)r=native_tabs_model(f->control,items,count,selected,1);else r=NULL;
  if(r&&f->view) {
    if(changed)*changed=!tabs_same(f,items,count,selected)||bounds.width!=f->width||bounds.height!=f->height;
    tabs_free_items(f->items,f->count);f->items=items;f->count=count;f->selected=selected;
    f->width=bounds.width;f->height=bounds.height;return r;
  }
  tabs_free_items(items,count);return NULL;
}
static void tabs_trace(struct ViewsTabs *f) {
  if(!tabs_trace_enabled||log_fd<0)return;
  struct Rect rect={.width=f->width,.height=f->height};
  ((void (*)(void *,void *))(base+NXS_VIEWS_TABS_TO_WIDGET))(f->view,&rect);
  struct NXSTabWireState state;if(!native_tabs_state(f->control,&state))return;
  dprintf(log_fd,"tabs-state id=%llu count=%u selected=%d x=%d y=%d width=%d height=%d content=%.3f,%.3f,%.3f,%.3f\n",
    (unsigned long long)f->control,state.count,state.selected_index,rect.x,rect.y,rect.width,rect.height,
    state.content.x,state.content.y,state.content.width,state.content.height);
  for(unsigned i=0;i<f->count;i++) {
    struct NXSRectD item;if(native_tabs_item_rect(f->control,f->items[i].identifier,&item))
      dprintf(log_fd,"tabs-item id=%llu index=%u native_id=%llu x=%.3f y=%.3f width=%.3f height=%.3f\n",
        (unsigned long long)f->control,i,(unsigned long long)f->items[i].identifier,item.x,item.y,item.width,item.height);
  }
}
static void tabs_paint(void *view,void *canvas) {
  struct ViewsTabs *f=tabs_find(view);
  if(!f){original_tabs_paint(view,canvas);return;}
  f->busy++;f->owned=0;int changed=0;struct NXSResponse *r=tabs_sync(f,&changed);int painted=0;
  if(r&&f->view&&r->width==f->width&&r->height==f->height&&r->stride==r->width*4&&r->size==sizeof(*r)+(size_t)r->stride*r->height) {
    struct NXSResponse header=*r;uint32_t *pixels=malloc((size_t)header.stride*header.height);
    if(pixels) {
      memcpy(pixels,r+1,(size_t)header.stride*header.height);
      void *paint=*(void **)((char *)canvas+192);
      if(paint){draw_native_bitmap(paint,pixels,header.width,0,0,0,0,header.width,header.height);painted=f->owned=1;}
      free(pixels);
    }
  }
  if(f->view) {
    if(!painted)original_tabs_paint(view,canvas);
    else {
      refresh_form_watch();tabs_trace(f);
      /* Old child damage can cover a different area than the native tab
       * label. Repaint the complete native owner after its model changes. */
      if(changed&&f->view)views_schedule(f->view);
    }
  }
  tabs_release(f);
}
static void tabs_children(void *view,const void *info) {
  struct ViewsTabs *f=tabs_find(view);
  if(!f||!f->owned){original_tabs_children(view,info);return;}
  /* A model change can invalidate only an old engine child. Repaint the
   * owning native control instead of displaying those replaced child views. */
  unsigned count;uint64_t selected;NXSTabItem *items=tabs_snapshot(f,&count,&selected);
  if(items) {
    if(!tabs_same(f,items,count,selected))views_schedule(view);
    tabs_free_items(items,count);
  }
}
static void tabs_layout(void *strip) {
  original_tabs_layout(strip);
  void *view=*(void **)((char *)strip+864);
  if(view&&!tabs_find(view)) {
    struct ViewsTabs *f=calloc(1,sizeof(*f));if(!f)return;
    f->view=view;f->strip=strip;f->controller=*(void **)((char *)strip+840);
    f->control=++next_form_control;f->next=views_tabs;views_tabs=f;
    views_schedule(view);
  }
}
static void *tabs_target(void *view,void *root,const void *rect) {
  struct ViewsTabs *f=tabs_find(view);
  return f&&f->owned?view:original_tabs_target(view,root,rect);
}
/* Once the native container owns this rectangle it is client content, not
 * Chromium's empty drag handle. Native AppKit still owns internal hit testing. */
static int tabs_content_area(void *view,const void *rect) {
  struct ViewsTabs *f=tabs_find(view);
  return f&&f->owned?1:original_tabs_content_area(view,rect);
}
static int tabs_press(void *view,const void *event) {
  struct ViewsTabs *f=tabs_find(view);unsigned flags=*(const unsigned *)((const char *)event+80);
  if(!f||!f->owned||(flags&0xf800)!=0x800)return original_tabs_press(view,event);
  f->busy++;int accepted=0;
  if(tabs_sync(f,NULL)&&f->view) {
    const float *point=(const float *)((const char *)event+136);
    unsigned clicks=(flags&(1u<<17))?3:(flags&(1u<<16))?2:1;
    struct NXSResponse *r=native_pointer_press(NXS_TABVIEW,f->control,point[0],point[1],views_modifiers(event),clicks);
    if(r) {
      struct NXSTabWireState state={0};int ready=0;
      for(unsigned i=0;i<100&&f->view;i++) {
        r=native_tabs_request(f->control,37,0,0,1);
        if(!r||r->parts[3].x!=1||r->size!=sizeof(*r)+sizeof(state))break;
        if(!r->parts[0].y){memcpy(&state,r+1,sizeof(state));ready=1;break;}
        struct timespec pause={.tv_nsec=2000000};nanosleep(&pause,NULL);
      }
      if(ready&&f->view) {
        accepted=1;
        if(state.selected!=f->selected) {
          struct ViewsTabIdentity *identity=f->identities;
          while(identity&&identity->identifier!=state.selected)identity=identity->next;
          /* Owner callbacks can change the application model during RPC.
           * Resolve against the current live list, never a cached index. */
          int count=((int (*)(void *))(base+NXS_VIEWS_TABS_COUNT))(f->view);
          for(int i=0;identity&&i<count&&count<=4096;i++) {
            void *tab=((void *(*)(void *,int))(base+NXS_VIEWS_TABS_AT))(f->strip,i);
            if(identity->tab!=tab)continue;
            if(log_fd>=0)dprintf(log_fd,"tabs-select id=%llu index=%d\n",(unsigned long long)f->control,i);
            ((void (*)(void *,void *,const void *))(base+NXS_VIEWS_TABS_SELECT))(f->strip,tab,event);break;
          }
        }
        if(f->view)views_schedule(view);
      }
    }
  }
  tabs_release(f);return accepted;
}
static int tabs_watch_needed(void) {return tabs_enabled&&views_tabs!=NULL;}
static void tabs_native_work(int failed) {
  if(tabs_enabled)for(struct ViewsTabs *f=views_tabs;f;f=f->next){if(failed)f->owned=0;views_schedule(f->view);}
}
static struct Detour tabs_detours[]={
  {NXS_VIEWS_TABS_LAYOUT,tabs_layout_bytes,tabs_layout,(void **)&original_tabs_layout},
  {NXS_VIEWS_TABS_TARGET,tabs_target_bytes,tabs_target,(void **)&original_tabs_target},
  {NXS_VIEWS_TABS_CONTENT_AREA,tabs_content_area_bytes,tabs_content_area,(void **)&original_tabs_content_area},
  {NXS_VIEWS_TABS_DATA,tabs_data_bytes,tabs_data,(void **)&original_tabs_data},
  {NXS_VIEWS_TABS_MODEL_CHANGED,tabs_model_changed_bytes,tabs_model_changed,(void **)&original_tabs_model_changed}
};
static int prepare_tabs(void) {
  uintptr_t *table=(uintptr_t *)(base+0x11fd9440);
  return guard_tabs_calls()&&table[109]==base+0xc71669c&&table[108]==base+0x9948830&&table[39]==base+0x2f20364&&
    prepare_detours(tabs_detours,sizeof(tabs_detours)/sizeof(*tabs_detours));
}
static void activate_tabs(void) {
  /* Native tabs own their complete rectangle. Remove only the guarded
   * legacy bottom-corner-overlap terms in Chromium's parent layout;
   * keep its original neighboring-button layout and sizing implementation. */
  const struct {uintptr_t offset;uint32_t instruction;} embedding[]={
    {0x11135c00,0x2a0903f5}, /* sub w21,w9,#12 -> mov w21,w9 */
    {0x11134c80,0x2a0803f5}, /* sub w21,w8,#12 -> mov w21,w8 */
    {0x111359bc,0x52800016}, /* Leading radius -> zero */
    {0x11135a30,0x2a0903f5}, /* add w21,w9,#12 -> mov w21,w9 */
    {0x11135aa4,0x52800008}, /* Combo leading radius -> zero */
    /* CanPaintThrobberToLayer is inlined in callers. Override the original
     * UpdateThrobber layer-eligibility load; its existing lifecycle destroys
     * old icon layers and keeps replaced children inside our paint boundary. */
    {NXS_VIEWS_TABS_THROBBER_LAYER,0x2a1f03e8} /* ldrb w8 -> mov w8,wzr */
  };
  for(unsigned i=0;i<sizeof(embedding)/sizeof(*embedding);i++) {
    uint32_t *address=(void *)(base+embedding[i].offset);
    writable(address,4,PROT_READ|PROT_WRITE|PROT_EXEC);*address=embedding[i].instruction;
    __builtin___clear_cache((void *)address,(char *)address+4);writable(address,4,PROT_READ|PROT_EXEC);
  }
  uintptr_t *table=(uintptr_t *)(base+0x11fd9440);
  original_tabs_paint=(void *)table[109];original_tabs_children=(void *)table[108];original_tabs_press=(void *)table[39];
  writable(table,112*sizeof(*table),PROT_READ|PROT_WRITE);
  table[109]=(uintptr_t)tabs_paint;table[108]=(uintptr_t)tabs_children;table[39]=(uintptr_t)tabs_press;
  writable(table,112*sizeof(*table),PROT_READ);
  activate_detours(tabs_detours,sizeof(tabs_detours)/sizeof(*tabs_detours));
}
