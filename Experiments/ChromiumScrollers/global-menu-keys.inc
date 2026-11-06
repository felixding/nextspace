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
static __thread struct MenuBrowser *creating_menu_browser;
static __thread unsigned menu_key_preflight;
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
    if(b->active)menu_browser_schedule(b);
  }
}
static int app_menu_browser_visible(uint64_t identity) {
  if(!menu_keys_enabled)return 1;
  struct MenuBrowser *b=menu_browser_find(NULL,identity);
  if(!b||!b->active)return 0;
  menu_browser_hide_others(identity);return 1;
}
static void app_menu_browser_task(uint64_t identity) {
  struct MenuBrowser *b=menu_browser_find(NULL,identity);if(!b)return;
  b->pending=0;
  if(!b->active) {
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
static void app_menus_native_work(int failed) {
  if(!menu_keys_enabled||failed)return;
  uint32_t epoch=atomic_load(&native_host_epoch);
  for(struct MenuBrowser *b=menu_browsers;b;b=b->next) {
    if(!pthread_equal(b->owner,pthread_self()))continue;
    struct AppMenuBinding *menu=menu_browser_model(b);
    /* Host invalidation wakes the existing engine work loop. Re-project on
     * its actual UI task queue before the next key, even without a focus or
     * tab change. Reuse the live application model; never replay commands. */
    if(menu&&menu->epoch!=epoch)menu_browser_schedule(b);
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
  b->next=menu_browsers;menu_browsers=b;
  if(log_fd>=0)dprintf(log_fd,"%d app-menu-browser-added id=%llu active=%d\n",getpid(),(unsigned long long)b->identity,b->active);
  menu_browser_schedule(b);
}
static void browser_menu_active(void *view,void *widget,int active) {
  original_browser_active(view,widget,active);
  struct MenuBrowser *b=menu_browser_find(view,0);
  if(b){b->active=!!active;menu_browser_schedule(b);}
}
static void browser_menu_destroying(void *view,void *widget) {
  struct MenuBrowser **cursor=&menu_browsers;
  while(*cursor&&(*cursor)->view!=view)cursor=&(*cursor)->next;
  if(*cursor) {
    struct MenuBrowser *b=*cursor;*cursor=b->next;
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
  uint16_t text_unit=((uint16_t (*)(const void *))(base+NXS_KEY_TEXT_OFFSET))(event);
  uint16_t plain_unit=((uint16_t (*)(const void *))(base+NXS_KEY_UNMODIFIED_OFFSET))(event);
  char *text=encode_text(&text_unit,text_unit?1:0,0),*plain=encode_text(&plain_unit,plain_unit?1:0,0);
  int handled=0;
  if(text&&plain) {
    NXSKeyEvent key={.size=sizeof(key),.type=NXS_KEY_DOWN,.modifiers=views_modifiers(event),
      .key=views_logical(*(const uint16_t *)((const char *)event+136)),
      .repeat=!!(*(const unsigned *)((const char *)event+80)&(1u<<17)),.text=text,.unmodified_text=plain};
    handled=native_model_menu_key(menu->control,&key,execute);
  }
  free(text);free(plain);
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
    {NXS_KEY_TEXT_OFFSET,nxs_key_text_bytes},{NXS_KEY_UNMODIFIED_OFFSET,nxs_key_unmodified_bytes}};
  for(unsigned i=0;i<sizeof(calls)/sizeof(*calls);i++)if(memcmp((void *)(base+calls[i].offset),calls[i].bytes,20))return 0;
  return prepare_detours(browser_menu_detours,sizeof(browser_menu_detours)/sizeof(*browser_menu_detours));
}
