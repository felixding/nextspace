/* Browser lifecycle and key-event adaptation only. GNUstep owns key matching
 * and controls; Chromium owns models, commands and its task queue.
 * GPL-2.0-or-later. */
#include "pinned-global-menu.h"
struct MenuBrowser {
  struct MenuBrowser *next;
  void *view,*browser,*manager;
  pthread_t owner;
  uint64_t identity,menu;
  int active,pending;
};
static struct MenuBrowser *menu_browsers;
static void menu_browser_schedule(struct MenuBrowser *);
static uint64_t next_menu_browser;
static __thread uint64_t selected_menu_browser;
/* Physical deactivation can transfer focus to this application's native
 * auxiliary window. Retain the last selected original window model; the
 * shared desktop broker alone decides whether its menu is presented. */
static __thread struct MenuBrowser *creating_menu_browser;
static __thread unsigned menu_key_preflight;
static NXSKeyEvent chromium_key_event(const void *event)
{
  uint16_t unit=((uint16_t (*)(const void *))(base+NXS_KEY_TEXT_OFFSET))(event);
  char *plain=views_layout_character(event);
  if(!plain) {
    uint16_t fallback=((uint16_t (*)(const void *))(base+NXS_KEY_UNMODIFIED_OFFSET))(event);
    plain=encode_text(&fallback,fallback?1:0,0);
  }
  return (NXSKeyEvent){.size=sizeof(NXSKeyEvent),.type=NXS_KEY_DOWN,.modifiers=views_modifiers(event),
    .key=views_logical(*(const uint16_t *)((const char *)event+136)),
    .repeat=!!(*(const unsigned *)((const char *)event+80)&(1u<<17)),
    .text=encode_text(&unit,unit?1:0,0),.unmodified_text=plain};
}
static void chromium_key_event_free(NXSKeyEvent key)
{
  free((void *)key.text);
  free((void *)key.unmodified_text);
}
static void (*original_browser_added)(void *);
static void (*original_browser_destroying)(void *,void *);
static void (*original_browser_active)(void *,void *,int);
static int (*original_browser_pre_key)(void *,const void *);
static int (*original_browser_key)(void *,const void *);
static struct MenuBrowser *menu_browser_find(void *view,uint64_t identity) {
  for(struct MenuBrowser *b=menu_browsers;b;b=b->next)
    if((view?b->view==view:b->identity==identity)&&pthread_equal(b->owner,pthread_self()))return b;
  return NULL;
}
static int app_menu_registry(struct AppMenuBinding *menu) {
  struct MenuBrowser *browser=menu_browser_find(NULL,menu->browser);
  if(!browser){note("command registry has no live browser owner");return 0;}
  /* Read the application's live, fully initialized registry. Its original
   * GetAccelerator method walks precisely these same std::map nodes. Keep no
   * parallel shortcut policy and no copied browser command table. */
  void *end=(char *)browser->view+NXS_BROWSER_ACCELERATOR_TABLE_END;
  void *node=*(void **)((char *)browser->view+NXS_BROWSER_ACCELERATOR_TABLE_BEGIN);
  unsigned count=0,imported=0,missing=0;
  while(node!=end) {
    if(!node||++count>4096){note("command registry node bound rejected");return 0;}
    const unsigned char *accelerator=(unsigned char *)node+NXS_BROWSER_ACCELERATOR_KEY;
    int command=*(const int *)((char *)node+NXS_BROWSER_ACCELERATOR_COMMAND);
    /* Native menus match key-down equivalents. Original key-up registrations
     * and non-command input continue through their original event paths. */
    if(*(const int *)(accelerator+4)==0&&(*(const int *)(accelerator+8)&(4|16))) {
      char label[64];snprintf(label,sizeof(label),"Command %d",command);
      int at=menu_entry_add(menu,-1,menu->model,0,2,command,NXS_MENU_KEY_ONLY,strdup(label),accelerator);
      if(at<0)return 0;
      if(!*menu->items[at].key_equivalent) {
        if(log_fd>=0)dprintf(log_fd,"%d command-registry-key-unavailable code=%u flags=%u command=%d\n",getpid(),
          *(const uint16_t *)accelerator,*(const unsigned *)(accelerator+8),command);
        free((void *)menu->items[at].title);free((void *)menu->items[at].key_equivalent);menu->count--;missing++;
      } else {
        menu->entries[at].browser_view=browser->view;
        memcpy(menu->entries[at].accelerator,accelerator,32);imported++;
      }
    }
    if(*(void **)((char *)node+8)) {
      node=*(void **)((char *)node+8);
      while(*(void **)node)node=*(void **)node;
    } else {
      void *parent=*(void **)((char *)node+16);
      while(node!=*(void **)parent){node=parent;parent=*(void **)((char *)node+16);}
      node=parent;
    }
  }
  if(log_fd>=0)dprintf(log_fd,"%d app-command-registry browser=%llu entries=%u native=%u missing=%u\n",getpid(),
    (unsigned long long)browser->identity,count,imported,missing);
  /* Some hardware-only commands have no Unicode key equivalent. Leave them
   * on the application's original hardware-event path rather than inventing
   * a native shortcut or disabling the ordinary command registry. */
  return 1;
}
static struct AppMenuBinding *menu_browser_model(struct MenuBrowser *browser) {
  for(struct AppMenuBinding *menu=app_menus;menu;menu=menu->next)
    if(menu->control==browser->menu&&menu->browser==browser->identity&&menu->bound)return menu;
  return NULL;
}
static void menu_browser_hide_others(uint64_t identity) {
  for(struct AppMenuBinding *menu=app_menus;menu;menu=menu->next)
    if(menu->bound&&menu->browser!=identity&&pthread_equal(menu->owner,pthread_self()))native_menu_request(menu->control,30,0);
}
static uint64_t app_menu_browser_created(void *browser,uint64_t control) {
  if(!menu_keys_enabled)return 0;
  struct MenuBrowser *b=creating_menu_browser;
  if(!b)for(b=menu_browsers;b;b=b->next)if(b->browser==browser&&pthread_equal(b->owner,pthread_self()))break;
  if(!b)return 0;
  b->browser=browser;b->menu=control;return b->identity;
}
static void app_menu_browser_removed(uint64_t identity,uint64_t control) {
  struct MenuBrowser *b=menu_browser_find(NULL,identity);
  if(b&&b->menu==control) {
    b->menu=0;
    /* Chromium can retire its temporary AppMenu when tab input cancels the
     * old runner. Recreate its real model on the existing UI queue while the
     * browser stays active, without waiting for a key or focus transition. */
    if(b->identity==selected_menu_browser)menu_browser_schedule(b);
  }
}
static int app_menu_browser_visible(uint64_t identity) {
  if(!menu_keys_enabled)return 1;
  struct MenuBrowser *b=menu_browser_find(NULL,identity);
  if(!b||b->identity!=selected_menu_browser)return 0;
  menu_browser_hide_others(identity);return 1;
}
static void app_menu_browser_task(uint64_t identity) {
  struct MenuBrowser *b=menu_browser_find(NULL,identity);if(!b)return;
  b->pending=0;
  if(b->identity!=selected_menu_browser) {
    struct AppMenuBinding *menu=menu_browser_model(b);if(menu)native_menu_request(menu->control,30,0);
    if(log_fd>=0)dprintf(log_fd,"%d app-menu-browser-selected id=%llu active=0\n",getpid(),(unsigned long long)identity);
    return;
  }
  menu_browser_hide_others(identity);
  struct AppMenuBinding *menu=menu_browser_model(b);
  if(menu){
    struct NXSResponse *response=native_menu_request(menu->control,26,1);
    if(response&&response->parts[3].x!=1)app_menu_bind(menu);
    if(log_fd>=0)dprintf(log_fd,"%d app-menu-browser-selected id=%llu active=1\n",getpid(),(unsigned long long)identity);
    return;}
  /* The real method creates and initializes the real AppMenuModel. Its
   * RunMenu reaches our existing native binding; no Views popup is opened. */
  struct MenuBrowser *previous=creating_menu_browser;creating_menu_browser=b;
  ((void (*)(void *))(base+NXS_BROWSER_SHOW_MENU_OFFSET))(b->view);
  creating_menu_browser=previous;
}
static void menu_browser_schedule(struct MenuBrowser *b) {
  if(b&&!b->pending) {
    b->pending=1;
    if(!app_menu_post_task(-1,0,0,0,b->identity)){b->pending=0;note("browser menu UI task rejected");}
  }
}
static void app_menu_callback_lost(void) {
  context_menu_callback_lost();
  for(struct MenuBrowser *b=menu_browsers;b;b=b->next)
    if(pthread_equal(b->owner,pthread_self())&&b->identity==selected_menu_browser)menu_browser_schedule(b);
}
static void app_menus_native_work(int failed) {
  if(!menu_keys_enabled||failed)return;
  uint32_t epoch=atomic_load(&native_host_epoch);
  for(struct MenuBrowser *b=menu_browsers;b;b=b->next) {
    if(!pthread_equal(b->owner,pthread_self()))continue;
    struct AppMenuBinding *menu=menu_browser_model(b);
    /* Host invalidation wakes the existing engine work loop. Re-project on
     * its actual UI task queue before the next key, even without a focus or
     * tab change. Reuse the live application model; never replay commands. */
    if(menu&&(menu->epoch!=epoch||menu->callback_generation!=native_callback_generation))menu_browser_schedule(b);
  }
}
static void browser_menu_added(void *view) {
  original_browser_added(view);
  if(menu_browser_find(view,0))return;
  void *widget=((void *(*)(void *))(base+NXS_BROWSER_WIDGET_OFFSET))(view);
  if(!widget)return;
  struct MenuBrowser *b=calloc(1,sizeof(*b));if(!b)return;
  b->view=view;b->owner=pthread_self();b->identity=++next_menu_browser;
  b->manager=((void *(*)(void *))(base+NXS_WIDGET_FOCUS_MANAGER_OFFSET))(widget);
  b->active=((int (*)(void *))(base+NXS_WIDGET_ACTIVE_OFFSET))(widget);
  if(b->active)selected_menu_browser=b->identity;
  b->next=menu_browsers;menu_browsers=b;
  if(log_fd>=0)dprintf(log_fd,"%d app-menu-browser-added id=%llu active=%d\n",getpid(),(unsigned long long)b->identity,b->active);
  menu_browser_schedule(b);
}
static void browser_menu_active(void *view,void *widget,int active) {
  original_browser_active(view,widget,active);
  struct MenuBrowser *b=menu_browser_find(view,0);
  if(b){b->active=!!active;if(active)selected_menu_browser=b->identity;menu_browser_schedule(b);}
}
static void browser_menu_destroying(void *view,void *widget) {
  struct MenuBrowser **cursor=&menu_browsers;
  while(*cursor&&(*cursor)->view!=view)cursor=&(*cursor)->next;
  if(*cursor) {
    struct MenuBrowser *b=*cursor;*cursor=b->next;
    if(selected_menu_browser==b->identity)selected_menu_browser=0;
    struct AppMenuBinding *menu=menu_browser_model(b);if(menu)native_menu_request(menu->control,30,0);
    if(log_fd>=0)dprintf(log_fd,"%d app-menu-browser-removed id=%llu\n",getpid(),(unsigned long long)b->identity);
    free(b); /* Queued tasks retain only the never-reused identity. */
  }
  original_browser_destroying(view,widget);
}
static int menu_browser_key(struct MenuBrowser *b,const void *event,int execute) {
  if(!b||!b->active||!b->manager||*(const unsigned char *)((char *)b->manager+72)||
      *(const int *)((const char *)event+8)!=7)return 0;
  struct AppMenuBinding *menu=menu_browser_model(b);if(!menu)return 0;
  /* The session can retain this connection while replacing the native host.
   * Re-project the actual engine model if its native object was lost. Never
   * replay a command or keep a second implementation of menu behavior. */
  struct NXSResponse *state=native_menu_request(menu->control,28,-1);
  if(!state||state->parts[3].x!=1) {
    if(!state||!app_menu_bind(menu))return 0;
  }
  NXSKeyEvent key=chromium_key_event(event);
  int handled=key.text&&key.unmodified_text&&native_model_menu_key(menu->control,&key,execute);
  chromium_key_event_free(key);
  if(log_fd>=0&&handled)dprintf(log_fd,"%d app-menu-global-key browser=%llu execute=%d handled=1\n",getpid(),(unsigned long long)b->identity,execute);
  return handled;
}
static const void *menu_browser_web_event(const void *event) {
  /* Source and binary agree: kRawKeyDown=7, os_event at 120,
   * skip_if_unhandled at 128. Never route composition/character events. */
  return *(const int *)((const char *)event+40)==7&&!*(const unsigned char *)((const char *)event+128)?
    *(void *const *)((const char *)event+120):NULL;
}
static int browser_menu_pre_key(void *view,const void *event) {
  const void *native=menu_browser_web_event(event);
  /* A tracking native menu owns keyboard input. Dispatch before Chromium's
   * renderer can consume it, including keys the menu leaves unmatched. */
  if(native&&context_menu_owns_keys()) {
    menu_browser_key(menu_browser_find(view,0),native,1);
    return 0; /* HANDLED. */
  }
  if(native&&menu_browser_key(menu_browser_find(view,0),native,0))return 3; /* NOT_HANDLED_IS_SHORTCUT, USE_AURA. */
  menu_key_preflight++;
  int result=original_browser_pre_key(view,event);
  menu_key_preflight--;return result;
}
static int browser_menu_key(void *view,const void *event) {
  /* Chromium reaches this hook only after the renderer declines the event.
   * A page's preventDefault therefore prevents the native action as well. */
  const void *native=menu_browser_web_event(event);
  if(native&&menu_browser_key(menu_browser_find(view,0),native,1))return 1;
  return original_browser_key(view,event);
}
static int app_menu_views_key(void *manager,const void *event) {
  if(menu_key_preflight)return 0;
  if(context_menu_owns_keys()) {
    for(struct MenuBrowser *b=menu_browsers;b;b=b->next)
      if(b->manager==manager&&pthread_equal(b->owner,pthread_self())) {
        menu_browser_key(b,event,1);return 1;
      }
    return 0;
  }
  /* Respect the real focused View's event contract before global matching.
   * WebView requests first delivery to its renderer here; BrowserView's
   * before/after-renderer hooks perform native lookup and execution later. */
  void *focused=*(void **)((char *)manager+24);
  if(focused&&((int (*)(void *,const void *))(*(uintptr_t **)focused)[71])(focused,event))return 0;
  for(struct MenuBrowser *b=menu_browsers;b;b=b->next)
    if(b->manager==manager&&pthread_equal(b->owner,pthread_self())&&menu_browser_key(b,event,1))return 1;
  return 0;
}
static struct Detour browser_menu_detours[]={
 {NXS_BROWSER_ADDED_OFFSET,nxs_browser_added_bytes,browser_menu_added,(void **)&original_browser_added},
 {NXS_BROWSER_DESTROYING_OFFSET,nxs_browser_destroying_bytes,browser_menu_destroying,(void **)&original_browser_destroying},
 {NXS_BROWSER_ACTIVE_OFFSET,nxs_browser_active_bytes,browser_menu_active,(void **)&original_browser_active},
 {NXS_BROWSER_PRE_KEY_OFFSET,nxs_browser_pre_key_bytes,browser_menu_pre_key,(void **)&original_browser_pre_key},
 {NXS_BROWSER_KEY_OFFSET,nxs_browser_key_bytes,browser_menu_key,(void **)&original_browser_key}
};
static int prepare_global_menu_keys(void) {
  const struct {uintptr_t offset;const unsigned char *bytes;} calls[]={
    {NXS_BROWSER_SHOW_MENU_OFFSET,nxs_browser_show_menu_bytes},{NXS_BROWSER_WIDGET_OFFSET,nxs_browser_widget_bytes},
    {NXS_WIDGET_FOCUS_MANAGER_OFFSET,nxs_widget_focus_manager_bytes},{NXS_WIDGET_ACTIVE_OFFSET,nxs_widget_active_bytes},
    {NXS_KEY_TEXT_OFFSET,nxs_key_text_bytes},{NXS_KEY_UNMODIFIED_OFFSET,nxs_key_unmodified_bytes},
    {NXS_BROWSER_ACCELERATOR_EXECUTE,nxs_browser_accelerator_execute_bytes},
    {NXS_APP_COMMAND_ENABLED,nxs_app_command_enabled_bytes}};
  for(unsigned i=0;i<sizeof(calls)/sizeof(*calls);i++)if(memcmp((void *)(base+calls[i].offset),calls[i].bytes,20))return 0;
  if(memcmp((void *)(base+NXS_BROWSER_ACCELERATOR_TABLE_GUARD),nxs_browser_accelerator_table_bytes,12)||
     memcmp((void *)(base+NXS_BROWSER_ACCELERATOR_VALUE_GUARD),nxs_browser_accelerator_value_bytes,12))return 0;
  return prepare_detours(browser_menu_detours,sizeof(browser_menu_detours)/sizeof(*browser_menu_detours));
}
