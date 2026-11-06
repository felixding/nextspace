/* Chromium application models bound to the independent native menu provider.
 * No native menu implementation, artwork, geometry or shortcut table.
 * GPL-2.0-or-later. */
#include "pinned-app-menu.h"
#include "../../Libraries/NativeUI/Bridge/Menu.inc"
struct MenuString {unsigned char bytes[24];};
struct MenuEntry {void *model;size_t index;int button,command_id;};
struct MenuLabel {struct MenuLabel *next;void *model;size_t index;char *label;};
struct AppMenuBinding {
  struct AppMenuBinding *next;
  void *object,*model;
  pthread_t owner;
  uint64_t control;
  struct MenuLabel *labels;
  NXSMenuItem *items;
  struct MenuEntry *entries;
  unsigned count;
  int bound;
};
static struct AppMenuBinding *app_menus;
static __thread struct AppMenuBinding *collecting_menu;
static uint64_t next_app_menu;
static unsigned app_menu_watch;
static int app_menu_watch_fd=-1;
static uint64_t app_menu_watch_generation;
static void *app_menu_task_runner; /* One engine-owned reference for this process. */
struct MenuTaskLocation {const char *function,*file;int line,padding;const void *pc;};
struct MenuTask {unsigned char state[32];int descriptor,padding;uint64_t generation,control,command;};
static int app_menu_ensure_watch(void);
static int app_menu_post_task(int,uint64_t,uint64_t,uint64_t);
static void (*original_app_menu_ctor)(void *,void *,void *,int,void *);
static void (*original_app_menu_dtor)(void *);
static void (*original_app_menu_run)(void *,void *,int);
static void (*original_app_menu_run_anchor)(void *,void *,const void *,int);
static struct MenuString (*original_app_menu_accessible_name)(void *,size_t,int,int);
static struct AppMenuBinding *app_menu_find(void *object) {
  for(struct AppMenuBinding *menu=app_menus;menu;menu=menu->next)if(menu->object==object)return menu;
  return NULL;
}
static char *menu_string(const void *value,int mnemonic) {
  const unsigned char *s=value;
  size_t length=(s[0]&1)?*(const size_t *)(s+8):s[0]>>1;
  const uint16_t *data=(s[0]&1)?*(const uint16_t *const *)(s+16):(const void *)(s+2);
  if(length>65536||(!data&&length))return NULL;
  if(!mnemonic)return encode_text(data,length,0);
  /* Chromium owns mnemonic removal, including escaped ampersands and CJK
   * resource suffixes. Native menus receive the resulting application label. */
  struct MenuString clean=((struct MenuString (*)(int,struct ViewsString,int *,int *))
    (base+NXS_APP_MENU_REMOVE_MNEMONIC_OFFSET))(1,(struct ViewsString){data,length},NULL,NULL);
  char *text=menu_string(&clean,0);
  ((void (*)(void *))(base+NXS_CHROMIUM_VIEWS_STRING_DESTROY_OFFSET))(&clean);return text;
}
static char *menu_model_label(void *model,size_t index) {
  struct MenuString label=((struct MenuString (*)(void *,size_t))(*(uintptr_t **)model)[7])(model,index);
  char *text=menu_string(&label,1);
  ((void (*)(void *))(base+NXS_CHROMIUM_VIEWS_STRING_DESTROY_OFFSET))(&label);return text;
}
static struct MenuString app_menu_accessible_name(void *model,size_t index,int resource,int accelerator) {
  struct MenuString result=original_app_menu_accessible_name(model,index,resource,accelerator);
  if(collecting_menu) {
    struct MenuString label=original_app_menu_accessible_name(model,index,resource,0);
    char *text=menu_string(&label,0);
    ((void (*)(void *))(base+NXS_CHROMIUM_VIEWS_STRING_DESTROY_OFFSET))(&label);
    if(text) {
      struct MenuLabel *entry=calloc(1,sizeof(*entry));
      if(entry){*entry=(struct MenuLabel){collecting_menu->labels,model,index,text};collecting_menu->labels=entry;}
      else free(text);
    }
  }
  return result;
}
static void app_menu_clear_model(struct AppMenuBinding *menu) {
  for(unsigned i=0;i<menu->count;i++){free((void *)menu->items[i].title);free((void *)menu->items[i].key_equivalent);}
  free(menu->items);free(menu->entries);menu->items=NULL;menu->entries=NULL;menu->count=0;
}
static int menu_entry_add(struct AppMenuBinding *menu,int parent,void *model,size_t index,int button,
    int command,unsigned flags,char *title,const unsigned char *accelerator) {
  if(!title||menu->count>=4096){free(title);return -1;}
  unsigned at=menu->count;
  NXSMenuItem *items=realloc(menu->items,(at+1)*sizeof(*items));
  if(!items){free(title);return -1;}menu->items=items;
  struct MenuEntry *entries=realloc(menu->entries,(at+1)*sizeof(*entries));
  if(!entries){free(title);return -1;}menu->entries=entries;
  char *key=strdup("");unsigned modifiers=0;
  if(accelerator) {
    int code=*(const int *)accelerator,flags=*(const int *)(accelerator+8);uint16_t unit=0;
    if(code>='A'&&code<='Z')unit=(flags&2)?code:code+32;
    else if(code>='0'&&code<='9')unit=code;
    else if(code>=112&&code<=135)unit=0xf704+code-112; /* Native function-key Unicode metadata. */
    else if(code==187)unit=(flags&2)?'+':'=';
    else if(code==189)unit=(flags&2)?'_':'-';
    if(unit){free(key);key=encode_text(&unit,1,0);}
    /* The application's primary Ctrl accelerator becomes the native Command
     * role. GNUstep owns its user's physical Command-key preference. */
    modifiers=((flags&(4|16))?NXS_MENU_COMMAND:0)|((flags&2)?NXS_MENU_SHIFT:0)|((flags&8)?NXS_MENU_ALTERNATE:0);
  }
  if(!key){free(title);return -1;}
  menu->items[at]=(NXSMenuItem){.size=sizeof(NXSMenuItem),.parent=parent,.command=flags&(NXS_MENU_SUBMENU|NXS_MENU_SEPARATOR)?0:at+1,
    .title=title,.key_equivalent=key,.modifiers=modifiers,.flags=flags};
  menu->entries[at]=(struct MenuEntry){model,index,button,command};menu->count++;return at;
}
static int app_menu_buttons(struct AppMenuBinding *menu,void *model,int parent) {
  if(!model)return 0;
  const unsigned char *begin=*(void **)((char *)model+24),*end=*(void **)((char *)model+32);
  if(!begin||end<begin||(end-begin)%40||(end-begin)/40>256)return 0;
  void *delegate=*(void **)((char *)model+48);
  for(size_t index=0;index<(size_t)(end-begin)/40;index++) {
    const unsigned char *item=begin+index*40;int command=*(const int *)item,type=*(const int *)(item+4);
    if(!type)continue; /* The native menu lays out its own separation. */
    char *label=NULL;
    for(struct MenuLabel *entry=menu->labels;entry;entry=entry->next)
      if(entry->model==model&&entry->index==index){label=strdup(entry->label);break;}
    if(!label)label=menu_string(item+8,1);
    if(!label||!*label){free(label);return 0;}
    unsigned char accelerator[32] __attribute__((aligned(8)))={0};
    int has_accelerator=delegate&&((int (*)(void *,int,void *))(*(uintptr_t **)delegate)[0])(delegate,command,accelerator);
    if(menu_entry_add(menu,parent,model,index,1,command,type==2?NXS_MENU_DISABLED:0,label,has_accelerator?accelerator:NULL)<0)return 0;
  }
  return 1;
}
static int app_menu_project(struct AppMenuBinding *menu,void *model,int parent,unsigned depth) {
  if(!model||depth>16)return 0;
  uintptr_t *methods=*(uintptr_t **)model;
  size_t count=((size_t (*)(void *))methods[3])(model);if(count>4096)return 0;
  for(size_t index=0;index<count;index++) {
    if(!((int (*)(void *,size_t))methods[24])(model,index))continue;
    int type=((int (*)(void *,size_t))methods[4])(model,index),command=((int (*)(void *,size_t))methods[6])(model,index);
    char *label=type==3?strdup(""):menu_model_label(model,index);unsigned flags=0;
    if(type==3)flags=NXS_MENU_SEPARATOR;
    else if(type==4||type==5)flags=NXS_MENU_SUBMENU;
    else if(type==8)flags=NXS_MENU_DISABLED;
    else if(type!=0&&type!=1&&type!=2&&type!=7){free(label);return 0;}
    if((type==1||type==2)&&((int (*)(void *,size_t))methods[19])(model,index))flags|=NXS_MENU_CHECKED;
    void *buttons=type==4?((void *(*)(void *,size_t))methods[22])(model,index):NULL;
    if(buttons){free(label);label=menu_string(buttons,1);}
    unsigned char accelerator[32] __attribute__((aligned(8)))={0};
    int has_accelerator=!(flags&(NXS_MENU_SUBMENU|NXS_MENU_SEPARATOR))&&
      ((int (*)(void *,size_t,void *))methods[17])(model,index,accelerator);
    int at=menu_entry_add(menu,parent,model,index,0,command,flags,label,has_accelerator?accelerator:NULL);
    if(at<0)return 0;
    if(type==4&&!app_menu_buttons(menu,buttons,at))return 0;
    if(type==5&&!app_menu_project(menu,((void *(*)(void *,size_t))methods[29])(model,index),at,depth+1))return 0;
  }
  return 1;
}
static struct AppMenuBinding *app_menu_for_command(uint64_t control,uint64_t command) {
  struct AppMenuBinding *menu=app_menus;
  while(menu&&menu->control!=control)menu=menu->next;
  return menu&&menu->bound&&pthread_equal(menu->owner,pthread_self())&&command&&command<=menu->count?menu:NULL;
}
static int app_menu_entry_enabled(struct MenuEntry entry) {
  if(entry.button) {
    void *delegate=*(void **)((char *)entry.model+48);
    return !delegate||((int (*)(void *,int))(*(uintptr_t **)delegate)[6])(delegate,entry.command_id);
  }
  return ((int (*)(void *,size_t))(*(uintptr_t **)entry.model)[23])(entry.model,entry.index);
}
static void app_menu_execute(uint64_t control,uint64_t command) {
  struct AppMenuBinding *menu=app_menu_for_command(control,command);if(!menu)return;
  struct MenuEntry entry=menu->entries[command-1];int enabled=app_menu_entry_enabled(entry);
  if(enabled) {
    if(entry.button) {
      void *delegate=*(void **)((char *)entry.model+48);
      if(delegate)((void (*)(void *,int,int))(*(uintptr_t **)delegate)[5])(delegate,entry.command_id,0);
    } else ((void (*)(void *,size_t,int))(*(uintptr_t **)entry.model)[31])(entry.model,entry.index,0);
  }
  /* Activation can delete its AppMenu. Only copied command data is used now. */
  if(log_fd>=0)dprintf(log_fd,"%d app-menu-execute id=%llu command=%d enabled=%d\n",getpid(),(unsigned long long)control,entry.command_id,!!enabled);
}
static int app_menu_command(const struct NXSNativeMenuCommand *request) {
  if(request->process!=identity())return 0;
  struct AppMenuBinding *menu=app_menu_for_command(request->control,request->command);if(!menu)return 0;
  struct MenuEntry entry=menu->entries[request->command-1];int enabled=app_menu_entry_enabled(entry);
  /* Synchronous native RPCs may dispatch this callback during a Chromium
   * paint/layout stack. Accept the native action here, then revalidate and
   * activate the application model in a separate real Chromium UI task. */
  if(enabled&&request->phase==NXS_COMMAND_EXECUTE)
    enabled=app_menu_post_task(native_edit_channel,native_callback_generation,request->control,request->command);
  if(log_fd>=0)dprintf(log_fd,"%d app-menu-command id=%llu command=%d phase=%u enabled=%d\n",getpid(),
    (unsigned long long)request->control,entry.command_id,request->phase,!!enabled);
  return !!enabled;
}
static void app_menu_task(void *state) {
  struct MenuTask *task=state;
  if(log_fd>=0)dprintf(log_fd,"%d app-menu-task owner=%d\n",getpid(),native_callback_owner());
  int current=native_callback_owner()&&task->descriptor==native_edit_channel&&task->generation==native_callback_generation;
  if(task->command){if(current)app_menu_execute(task->control,task->command);}
  else {
    app_menu_watch=0;
    if(current)native_callbacks_dispatch();
    if(native_edit_channel>=0)app_menu_ensure_watch();
  }
}
static void app_menu_task_destroy(const void *state) {free((void *)state);}
static int app_menu_post_task(int descriptor,uint64_t generation,uint64_t control,uint64_t command) {
  if(!app_menu_task_runner)return 0;
  struct MenuTask *state=calloc(1,sizeof(*state));if(!state)return 0;
  ((void (*)(void *,void (*)(void *),void (*)(const void *)))(base+NXS_TASK_BIND_STATE_CTOR_OFFSET))
    (state,app_menu_task,app_menu_task_destroy);
  state->descriptor=descriptor;state->generation=generation;
  state->control=control;state->command=command;
  struct MenuTaskLocation location=((struct MenuTaskLocation (*)(const char *,const char *,int))
    (base+NXS_TASK_LOCATION_OFFSET))("app_menu_task","../../NEXTSPACE-native-menu",1);
  /* OnceClosure is the pinned trivial-ABI, one-pointer BindStateHolder. The
   * real PostTask takes ownership even if the scheduler rejects the task. */
  return ((int (*)(void *,const void *,void *))(base+NXS_TASK_POST_OFFSET))(app_menu_task_runner,&location,state);
}
static int app_menu_ready(int descriptor,unsigned condition,void *unused) {
  if(log_fd>=0)dprintf(log_fd,"%d app-menu-source-wake condition=%u owner=%d\n",getpid(),condition,native_callback_owner());
  /* A GLib source can run inside Chromium's nested native dispatch while its
   * compositor is midway through a frame. Use its actual UI task queue for
   * application mutations. Remove this readable source until the task drains
   * the callback socket, rather than repeatedly posting the same wake. */
  if(!app_menu_post_task(descriptor,(uintptr_t)unused,0,0))note("application menu UI task rejected");
  return 0;
}
static int app_menu_ensure_watch(void) {
  if(app_menu_watch&&app_menu_watch_fd==native_edit_channel&&app_menu_watch_generation==native_callback_generation)return 1;
  unsigned (*add)(int,unsigned,int (*)(int,unsigned,void *),void *)=dlsym(RTLD_DEFAULT,"g_unix_fd_add");
  int (*remove)(unsigned)=dlsym(RTLD_DEFAULT,"g_source_remove");
  if(!add||!remove||!native_callback_owner())return 0;
  if(!app_menu_task_runner) {
    /* Actual default BrowserTaskTraits: kDefault, USER_BLOCKING. Chromium
     * constructs/retains the runner, the closure state and the task itself. */
    unsigned char traits[8]={0,0,0,0,2,0,0,0};
    app_menu_task_runner=((void *(*)(const void *))(base+NXS_TASK_UI_RUNNER_OFFSET))(traits);
    if(!app_menu_task_runner)return 0;
  }
  if(app_menu_watch)remove(app_menu_watch);
  app_menu_watch_fd=native_edit_channel;app_menu_watch_generation=native_callback_generation;
  app_menu_watch=add(native_edit_channel,1,app_menu_ready,(void *)(uintptr_t)native_callback_generation);return app_menu_watch!=0;
}
static void menu_trace_hex(const char *text) {
  for(const unsigned char *p=(const void *)text;*p;p++)dprintf(log_fd,"%02x",*p);
}
static int app_menu_bind(struct AppMenuBinding *menu) {
  if(!menu||!pthread_equal(menu->owner,pthread_self())||*(uintptr_t *)menu->model!=base+0x11b63b38+16)return 0;
  if(menu->bound){native_menu_request(menu->control,29,0);menu->bound=0;}
  app_menu_clear_model(menu);
  if(!app_menu_project(menu,menu->model,-1,0)||!refresh_form_watch()||form_watch.wake_fd<0||
     !native_menu_filter_register(app_menu_command)||!app_menu_ensure_watch())return 0;
  menu->bound=1;
  if(!native_menu_model(menu->control,"Chromium",menu->items,menu->count)){menu->bound=0;return 0;}
  struct NXSResponse *response=native_menu_request(menu->control,26,1);
  if(!response||response->parts[3].x!=1){native_menu_request(menu->control,29,0);menu->bound=0;return 0;}
  if(log_fd>=0) {
    struct NXSRectD frame=response->parts[1];
    dprintf(log_fd,"%d app-menu-native id=%llu count=%u frame=%.0f,%.0f,%.0f,%.0f\n",getpid(),(unsigned long long)menu->control,menu->count,frame.x,frame.y,frame.width,frame.height);
    if(menus_trace_enabled)for(unsigned i=0;i<menu->count;i++) {
      NXSMenuItem *item=&menu->items[i];
      dprintf(log_fd,"%d app-menu-item id=%llu index=%u command=%d parent=%d flags=%u modifiers=%u title_hex=",getpid(),(unsigned long long)menu->control,i,menu->entries[i].command_id,item->parent,item->flags,item->modifiers);
      menu_trace_hex(item->title);dprintf(log_fd," key_hex=");menu_trace_hex(item->key_equivalent);dprintf(log_fd,"\n");
    }
  }
  return 1;
}
static void app_menu_ctor(void *object,void *browser,void *model,int run_types,void *closed) {
  struct AppMenuBinding *menu=calloc(1,sizeof(*menu)),*previous=collecting_menu;
  if(menu){menu->object=object;menu->model=model;menu->owner=pthread_self();menu->control=++next_app_menu;collecting_menu=menu;}
  original_app_menu_ctor(object,browser,model,run_types,closed);collecting_menu=previous;
  if(menu){menu->next=app_menus;app_menus=menu;}
}
static void app_menu_dtor(void *object) {
  struct AppMenuBinding **cursor=&app_menus;
  while(*cursor&&(*cursor)->object!=object)cursor=&(*cursor)->next;
  if(*cursor) {
    struct AppMenuBinding *menu=*cursor;*cursor=menu->next;
    if(menu->bound)native_menu_request(menu->control,29,0);
    app_menu_clear_model(menu);
    while(menu->labels){struct MenuLabel *entry=menu->labels;menu->labels=entry->next;free(entry->label);free(entry);}
    free(menu);refresh_form_watch();
  }
  original_app_menu_dtor(object);
}
static void app_menu_run(void *object,void *button,int source) {
  if(!app_menu_bind(app_menu_find(object))){note("application menu binding unavailable; original menu retained");original_app_menu_run(object,button,source);}
}
static void app_menu_run_anchor(void *object,void *widget,const void *anchor,int source) {
  if(!app_menu_bind(app_menu_find(object)))original_app_menu_run_anchor(object,widget,anchor,source);
}
static int app_menus_watch_needed(void) {return menus_enabled&&app_menus!=NULL;}
static struct Detour app_menu_detours[]={
 {NXS_APP_MENU_CTOR_OFFSET,nxs_app_menu_ctor_bytes,app_menu_ctor,(void **)&original_app_menu_ctor},
 {NXS_APP_MENU_DTOR_OFFSET,nxs_app_menu_dtor_bytes,app_menu_dtor,(void **)&original_app_menu_dtor},
 {NXS_APP_MENU_RUN_OFFSET,nxs_app_menu_run_bytes,app_menu_run,(void **)&original_app_menu_run},
 {NXS_APP_MENU_RUN_ANCHOR_OFFSET,nxs_app_menu_run_anchor_bytes,app_menu_run_anchor,(void **)&original_app_menu_run_anchor},
 {NXS_APP_MENU_ACCESSIBLE_NAME_OFFSET,nxs_app_menu_accessible_name_bytes,app_menu_accessible_name,(void **)&original_app_menu_accessible_name}
};
static int prepare_app_menus(void) {
  return !memcmp((void *)(base+NXS_APP_MENU_REMOVE_MNEMONIC_OFFSET),nxs_app_menu_remove_mnemonic_bytes,20)&&
    !memcmp((void *)(base+NXS_TASK_BIND_STATE_CTOR_OFFSET),nxs_task_bind_state_ctor_bytes,20)&&
    !memcmp((void *)(base+NXS_TASK_POST_OFFSET),nxs_task_post_bytes,20)&&
    !memcmp((void *)(base+NXS_TASK_UI_RUNNER_OFFSET),nxs_task_ui_runner_bytes,20)&&
    !memcmp((void *)(base+NXS_TASK_LOCATION_OFFSET),nxs_task_location_bytes,20)&&
    prepare_detours(app_menu_detours,sizeof(app_menu_detours)/sizeof(*app_menu_detours));
}
