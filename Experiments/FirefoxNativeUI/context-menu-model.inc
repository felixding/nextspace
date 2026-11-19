/* Complete the original GTK exporter's container visibility. Its recursive
 * projection skips hidden leaves, but otherwise recurses into hidden groups.
 * No commands, menu controls or state/toggle implementation are copied. */
static void (*original_context_model_children)(void *,void *,void *);
static void context_element_release(void *element)
{if(element)((unsigned (*)(void *))(base+0x570faf0))(element);}
static void context_model_source(void *object,void *element)
{
  static void *(*get)(void *,const char *);
  static void (*set)(void *,const char *,void *,void (*)(void *));
  if(!get)get=dlsym(RTLD_NEXT,"g_object_get_data");
  if(!set)set=dlsym(RTLD_NEXT,"g_object_set_data_full");
  if(get&&set&&get(object,"nextspace-native-menu-source")!=element) {
    ((unsigned (*)(void *))(base+0x3b9f0e4))(element);
    set(object,"nextspace-native-menu-source",element,context_element_release);
  }
}
static void context_submenu_state(void *action,void *value,void *element)
{
  static int (*boolean)(void *);static void (*set_state)(void *,void *);
  if(!boolean)boolean=dlsym(RTLD_NEXT,"g_variant_get_boolean");
  if(!set_state)set_state=dlsym(RTLD_NEXT,"g_simple_action_set_state");
  if(!boolean||!set_state||!original_dbus_menu_event)return;
  /* Reuse Gecko's existing native submenu event dispatcher. The GTK
   * exporter's own change-state callback is disabled in this browser build. */
  original_dbus_menu_event(NULL,boolean(value)?"opened":"closed",value,0,element);
  set_state(action,value);
}
unsigned long g_signal_connect_data(void *object,const char *signal,void *callback,void *data,void *destroy,int flags)
{
  static unsigned long (*original)(void *,const char *,void *,void *,void *,int);
  if(!original)original=dlsym(RTLD_NEXT,"g_signal_connect_data");
  if(installed&&menu_lifecycle_requested&&data&&
      callback==(void *)(base+0x6b12644)&&!strcmp(signal,"item-activated"))
    context_model_source(object,data);
  if(installed&&menu_lifecycle_requested&&data&&
      ((callback==(void *)(base+0x6af97c0)&&!strcmp(signal,"activate"))||
       (callback==(void *)(base+0x6af97b8)&&!strcmp(signal,"change-state")))) {
    /* GMenu rebuilds replace action objects. Holding the original GAction
     * must also retain its source element until the native menu releases it. */
    context_model_source(object,data);
    if(callback==(void *)(base+0x6af97b8))callback=context_submenu_state;
  }
  return original?original(object,signal,callback,data,destroy,flags):0;
}
static void context_model_children(void *menu,void *actions,void *element)
{
  static void *hidden,*collapsed;
  if(!hidden)hidden=((void *(*)(const char *))(base+NXS_GECKO_POPUP_ATOMIZE))("hidden");
  if(!collapsed)collapsed=((void *(*)(const char *))(base+NXS_GECKO_POPUP_ATOMIZE))("collapsed");
  void *attributes[]={hidden,collapsed};static const uint16_t empty;
  for(unsigned i=0;i<2;i++)if(attributes[i]) {
    struct GeckoString value={.data=&empty,.flags=1};
    int present=((int (*)(void *,void *,void *))(base+NXS_GECKO_POPUP_GET_ATTR))(element,attributes[i],&value);
    int excluded=present&&!(value.length==5&&!memcmp(value.data,u"false",10));
    ((void (*)(void *))(base+0x3826f2c))(&value);
    if(excluded)return;
  }
  context_model_source(menu,element);
  original_context_model_children(menu,actions,element);
}
static const unsigned char context_model_children_bytes[20]={0x3f,0x23,0x03,0xd5,0xff,0x83,0x06,0xd1,0xfd,0x7b,0x14,0xa9,0xfc,0x6f,0x15,0xa9,0xfa,0x67,0x16,0xa9};
static void (*original_context_show)(void *,void *,const void *,int);
static void context_show(void *menu,void *frame,const void *point,int context)
{
  original_context_show(menu,frame,point,context);
  void *model=*(void **)((char *)menu+32);
  if(!model||!*((unsigned char *)model+49))return;
  /* The GTK exporter omits the normal command-state update. Its popupshown
   * handlers have now finished, while GTK presentation remains queued. Reuse
   * Gecko's own updater before projecting that live GMenuModel. No command
   * resolution, enablement or password policy is copied into the bridge. */
  void *element=*(void **)((char *)model+40),*manager=*(void **)(base+0xa482060);
  if(element&&manager)((void (*)(void *,void *))(base+0x6f7190c))(manager,element);
  if(!*((unsigned char *)model+49))return;
  /* NativeMenuGtk also omits its opening observer notification. Mirror its
   * existing closing notification's snapshot boundary; the original observer
   * clears source :active, capture and drag state through Gecko itself. */
  void *header=*(void **)((char *)menu+40);unsigned count=header?*(uint32_t *)header:0;
  if(count>4096)return;
  void **observers=count?malloc(count*sizeof(void *)):NULL;if(count&&!observers)return;
  if(count)memcpy(observers,(char *)header+8,count*sizeof(void *));
  for(unsigned i=0;i<count;i++)if(observers[i])((void (*)(void *))(*(uintptr_t **)observers[i])[0])(observers[i]);
  free(observers);
}
static const unsigned char context_show_bytes[20]={0x3f,0x23,0x03,0xd5,0xff,0xc3,0x01,0xd1,0xe9,0x23,0x02,0x6d,0xfe,0x1b,0x00,0xf9,0xf8,0x5f,0x04,0xa9};
static const unsigned char context_update_bytes[20]={0x3f,0x23,0x03,0xd5,0xff,0xc3,0x06,0xd1,0xfd,0x7b,0x15,0xa9,0xfc,0x6f,0x16,0xa9,0xfa,0x67,0x17,0xa9};
static const unsigned char context_element_bytes[20]={0x5f,0x24,0x03,0xd5,0x09,0x10,0x40,0xf9,0x20,0x15,0x40,0xf9,0x00,0x01,0x00,0xf9,0x40,0x00,0x00,0xb4};
static const unsigned char context_observer_bytes[16]={0x74,0x16,0x40,0xf9,0xf5,0x03,0x00,0xf9,0xa8,0x06,0x40,0xb9,0x93,0x86,0x40,0xb8};
static const unsigned char context_showing_bytes[8]={0x08,0x10,0x40,0xf9,0x08,0xc5,0x40,0x39};
static const unsigned char context_activate_bytes[20]={0x3f,0x23,0x03,0xd5,0xfe,0x4f,0xbf,0xa9,0xf3,0x03,0x02,0xaa,0x62,0x00,0x00,0xb4,0xe0,0x03,0x13,0xaa};
static const unsigned char context_change_state_bytes[8]={0x5f,0x24,0x03,0xd5,0xc0,0x03,0x5f,0xd6};
static struct Detour context_model_detours[]={
  {0x6af9be0,context_model_children_bytes,context_model_children,(void **)&original_context_model_children},
  {0x6afa5ac,context_show_bytes,context_show,(void **)&original_context_show}
};
static int prepare_context_menu_model(void)
{
  return !menu_lifecycle_requested||(!memcmp((void *)(base+NXS_GECKO_POPUP_GET_ATTR),gecko_popup_get_attr_bytes,20)&&
    !memcmp((void *)(base+NXS_GECKO_POPUP_ATOMIZE),gecko_popup_atomize_bytes,20)&&
    !memcmp((void *)(base+0x6f7190c),context_update_bytes,20)&&
    !memcmp((void *)(base+0x6afa590),context_element_bytes,20)&&
    !memcmp((void *)(base+0x6afa8cc),context_observer_bytes,16)&&
    !memcmp((void *)(base+0x6afa5d8),context_showing_bytes,8)&&
    !memcmp((void *)(base+0x6af97c0),context_activate_bytes,20)&&
    !memcmp((void *)(base+0x6af97b8),context_change_state_bytes,8)&&
    prepare_detours(context_model_detours,sizeof(context_model_detours)/sizeof(*context_model_detours)));
}
