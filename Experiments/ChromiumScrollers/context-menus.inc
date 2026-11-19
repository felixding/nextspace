/* Original MenuModelAdapter data and MenuRunner lifecycle, shared by page and
 * browser chrome context menus. NSMenu owns presentation and tracking. */
#include "pinned-context-menus.h"
struct ContextModelRoot {
  struct ContextModelRoot *next;void *adapter,*root,*model;pthread_t owner;
};
struct ContextMenuBinding {
  struct ContextMenuBinding *next;void *object,*adapter,*root;
  struct AppMenuBinding projection;uint64_t selected;
  int running,closing,release_pending;
};
static struct ContextModelRoot *context_roots;
static struct ContextMenuBinding *context_menus;
static int context_menu_owns_keys(void)
{
  for(struct ContextMenuBinding *m=context_menus;m;m=m->next)
    if(m->running&&pthread_equal(m->projection.owner,pthread_self()))return 1;
  return 0;
}
static uint64_t next_context_menu;
static void (*original_context_build)(void *,void *);
static void (*original_context_model_dtor)(void *);
static void (*original_context_dtor)(void *);
static void (*original_context_release)(void *);
static void (*original_context_cancel)(void *);
static void (*original_context_run)(void *,void *,void *,const struct Rect *,int,int,int,void *,void *,void *);
static struct ContextMenuBinding *context_find(void *object,uint64_t control)
{
  for(struct ContextMenuBinding *m=context_menus;m;m=m->next)
    if((object?m->object==object:m->projection.control==control)&&pthread_equal(m->projection.owner,pthread_self()))return m;
  return NULL;
}
static struct ContextModelRoot *context_root(void *root)
{
  for(struct ContextModelRoot *r=context_roots;r;r=r->next)
    if(r->root==root&&pthread_equal(r->owner,pthread_self()))return r;
  return NULL;
}
static int context_model_live(struct ContextMenuBinding *m)
{
  struct ContextModelRoot *r=context_root(m->root);
  return r&&r->adapter==m->adapter&&r->model==m->projection.model&&
    *(void **)((char *)r->adapter+16)==r->model;
}
static void context_build(void *adapter,void *root)
{
  original_context_build(adapter,root);
  struct ContextModelRoot *r=context_root(root);
  if(!r){r=calloc(1,sizeof(*r));if(!r)return;r->next=context_roots;context_roots=r;}
  r->adapter=adapter;r->root=root;r->model=*(void **)((char *)adapter+16);r->owner=pthread_self();
}
static void context_model_dtor(void *adapter)
{
  struct ContextModelRoot **link=&context_roots;
  while(*link) {
    struct ContextModelRoot *r=*link;
    if(r->adapter!=adapter){link=&r->next;continue;}
    *link=r->next;free(r);
  }
  for(struct ContextMenuBinding *m=context_menus;m;m=m->next)
    if(m->adapter==adapter&&m->running)native_menu_request(m->projection.control,30,0);
  original_context_model_dtor(adapter);
}
static void context_release(void *object)
{
  struct ContextMenuBinding *m=context_find(object,0);
  if(m&&m->running){m->release_pending=1;native_menu_request(m->projection.control,30,0);return;}
  original_context_release(object);
}
static void context_cancel(void *object)
{
  struct ContextMenuBinding *m=context_find(object,0);
  if(m&&m->running){native_menu_request(m->projection.control,30,0);return;}
  original_context_cancel(object);
}
static void context_running(struct ContextMenuBinding *m,int running)
{
  m->running=running;
  /* Keep the original runner's own IsRunning implementation and all its
   * callers coherent, including devirtualized reads in the adapter wrapper. */
  *((unsigned char *)m->object+56)=!!running;
}
static void context_run(void *object,void *parent,void *button,const struct Rect *bounds,
    int anchor,int source,int types,void *gestures,void *corners,void *histogram)
{
  if(!menus_enabled||!(types&8)||!bounds)goto original;
  struct ContextMenuBinding *m=context_find(object,0);
  if(m&&m->running)return;
  struct ContextModelRoot *r=context_root(*(void **)((char *)object+24));
  if(!r||!r->model)goto original;
  if(!refresh_form_watch()||form_watch.wake_fd<0||!native_menu_filter_register(app_menu_command)||!app_menu_ensure_watch())goto original;
  if(!m) {
    m=calloc(1,sizeof(*m));if(!m)goto original;
    m->object=object;m->projection.owner=pthread_self();m->projection.control=(1ull<<40)|++next_context_menu;
    m->next=context_menus;context_menus=m;
  }
  m->adapter=r->adapter;m->root=r->root;m->projection.model=r->model;
  uint64_t control=m->projection.control;void *model=m->projection.model;
  context_running(m,1);m->closing=0;m->selected=0;
  ((void (*)(void *))(*(uintptr_t **)model)[32])(model);
  m=context_find(NULL,control);if(!m)return;
  if(!context_model_live(m)){context_running(m,0);return;}
  app_menu_clear_model(&m->projection);
  int okay=app_menu_project(&m->projection,model,-1,0);
  if(okay)for(unsigned i=0;i<m->projection.count;i++)
    if(!(m->projection.items[i].flags&NXS_MENU_SEPARATOR)&&!app_menu_entry_enabled(m->projection.entries[i]))m->projection.items[i].flags|=NXS_MENU_DISABLED;
  if(okay)okay=native_context_menu_model(control,native_context_menu_title(),m->projection.items,m->projection.count);
  if(okay){m->projection.bound=1;okay=native_menu_popup_request(control,bounds->x,bounds->y);}
  if(okay) {
    if(log_fd>=0)dprintf(log_fd,"%d native-context-present id=%llu count=%u origin=%d,%d\n",getpid(),(unsigned long long)control,m->projection.count,bounds->x,bounds->y);
    return;
  }
  if(m->projection.bound){native_menu_request(control,29,0);m->projection.bound=0;}
  context_running(m,0);
  ((void (*)(void *))(*(uintptr_t **)model)[33])(model);
  if(!context_find(object,0))return;
  note("context menu binding unavailable; original retained");
original:
  original_context_run(object,parent,button,bounds,anchor,source,types,gestures,corners,histogram);
}
static void context_dtor(void *object)
{
  struct ContextMenuBinding **link=&context_menus;
  while(*link&&(*link)->object!=object)link=&(*link)->next;
  if(*link) {
    struct ContextMenuBinding *m=*link;*link=m->next;
    if(m->projection.bound)native_menu_request(m->projection.control,29,0);
    app_menu_clear_model(&m->projection);free(m);
  }
  original_context_dtor(object);
}
static int context_menu_command(const struct NXSNativeMenuCommand *request)
{
  struct ContextMenuBinding *m=context_find(NULL,request->control);if(!m)return -1;
  if(request->phase>1)return 0;
  if(!m->running||m->closing)return 0;
  if(!request->command) {
    if(request->phase!=NXS_COMMAND_EXECUTE)return 0;
    m->closing=1;return app_menu_post_task(native_edit_channel,native_callback_generation,request->control,0,0);
  }
  if(!context_model_live(m)||request->command>m->projection.count)return 0;
  int enabled=app_menu_entry_enabled(m->projection.entries[request->command-1]);
  if(enabled&&request->phase==NXS_COMMAND_EXECUTE)m->selected=request->command;
  return enabled;
}
static void context_menu_complete(uint64_t control)
{
  struct ContextMenuBinding *m=context_find(NULL,control);if(!m)return;
  context_running(m,0);
  if(m->projection.bound){native_menu_request(control,29,0);m->projection.bound=0;}
  if(m->release_pending){context_release(m->object);return;}
  if(context_model_live(m)) {
    void *model=m->projection.model;
    ((void (*)(void *))(*(uintptr_t **)model)[33])(model);
    m=context_find(NULL,control);if(!m)return;
    if(context_model_live(m)&&m->selected&&m->selected<=m->projection.count) {
      struct MenuEntry entry=m->projection.entries[m->selected-1];
      if(app_menu_entry_enabled(entry))((void (*)(void *,size_t,int))(*(uintptr_t **)entry.model)[31])(entry.model,entry.index,0);
    }
  }
  m=context_find(NULL,control);
  if(m&&context_model_live(m))((void (*)(void *,void *))(base+NXS_CONTEXT_CLOSED))(m->adapter,NULL);
}
static void context_menu_callback_lost(void)
{
  /* Complete the original runner after a failed endpoint, without replaying
   * a selection whose native transaction was abandoned. Source callbacks can
   * destroy the binding, so retain only its numeric identity across them. */
  for(;;) {
    struct ContextMenuBinding *m=context_menus;
    while(m&&(!m->running||!pthread_equal(m->projection.owner,pthread_self())))m=m->next;
    if(!m)break;
    uint64_t control=m->projection.control;m->selected=0;
    context_menu_complete(control);
  }
}
static struct Detour context_menu_detours[]={
  {NXS_CONTEXT_BUILD,nxs_context_build_bytes,context_build,(void **)&original_context_build},
  {NXS_CONTEXT_MODEL_DTOR,nxs_context_model_dtor_bytes,context_model_dtor,(void **)&original_context_model_dtor},
  {NXS_CONTEXT_RUN,nxs_context_run_bytes,context_run,(void **)&original_context_run},
  {NXS_CONTEXT_CANCEL,nxs_context_cancel_bytes,context_cancel,(void **)&original_context_cancel},
  {NXS_CONTEXT_RELEASE,nxs_context_release_bytes,context_release,(void **)&original_context_release},
  {NXS_CONTEXT_DTOR,nxs_context_dtor_bytes,context_dtor,(void **)&original_context_dtor}
};
static int prepare_context_menus(void)
{
  return !memcmp((void *)(base+NXS_CONTEXT_CLOSED),nxs_context_closed_bytes,20)&&
    prepare_detours(context_menu_detours,sizeof(context_menu_detours)/sizeof(*context_menu_detours));
}
