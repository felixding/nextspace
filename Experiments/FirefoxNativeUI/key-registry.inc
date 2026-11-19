/* Extend Gecko's original exporter with its original non-menu XUL keys.
 * NSMenu and the existing D-Bus binding retain matching and dispatch. */
struct GeckoMenuRegistry {
  struct GeckoMenuRegistry *next;
  void *model,*root;
};
static struct GeckoMenuRegistry *gecko_menu_registries;
static void (*original_registry_create)(void *,void *);
static void (*original_registry_destroy)(void *);
static void (*original_registry_delete)(void *);
static void (*original_registry_recompute)(void *);
static void (*original_registry_insert)(void *,void *,void *);
static void (*original_registry_remove)(void *,void *,void *);
static void (*original_registry_attribute)(void *,void *,int,void *,int,const void *);
static struct GeckoMenuRegistry *registry_for(void *model)
{
  for(struct GeckoMenuRegistry *r=gecko_menu_registries;r;r=r->next)if(r->model==model)return r;
  return NULL;
}
static void registry_create(void *model,void *element)
{
  void *root=element,*parent;unsigned depth=0;
  /* nsINode::mParent, ending at the document element, not the Document. */
  while(root&&(parent=*(void **)((char *)root+48))&&*(void **)((char *)parent+48)) {
    if(++depth>64){root=element;break;}root=parent;
  }
  struct GeckoMenuRegistry *r=root!=element?calloc(1,sizeof(*r)):NULL;
  original_registry_create(model,r?root:element);
  if(!r)return;
  /* The original constructor owns/observes root. Keep Element() pointing at
   * the actual menubar for native visibility and original exporter methods. */
  ((unsigned (*)(void *))(base+0x3b9f0e4))(element);
  *(void **)((char *)model+40)=element;
  r->model=model;r->root=root;r->next=gecko_menu_registries;gecko_menu_registries=r;
}
static void registry_destroy_with(void *model,void (*destroy)(void *))
{
  struct GeckoMenuRegistry **link=&gecko_menu_registries,*r=NULL;
  while(*link&&(*link)->model!=model)link=&(*link)->next;
  void *element=NULL;
  if(*link) {
    r=*link;*link=r->next;element=*(void **)((char *)model+40);
    /* The original destructor removes its own observer and releases root. */
    *(void **)((char *)model+40)=r->root;
  }
  destroy(model);
  if(r){context_element_release(element);free(r);}
}
static void registry_destroy(void *model){registry_destroy_with(model,original_registry_destroy);}
static void registry_delete(void *model){registry_destroy_with(model,original_registry_delete);}
static int registry_boolean(void *element,const char *name)
{
  static const uint16_t empty;
  void *atom=((void *(*)(const char *))(base+NXS_GECKO_POPUP_ATOMIZE))(name);
  struct GeckoString value={.data=&empty,.flags=1};
  if(atom)((int (*)(void *,void *,void *))(base+NXS_GECKO_POPUP_GET_ATTR))(element,atom,&value);
  int result=value.length==4&&!memcmp(value.data,u"true",8);
  ((void (*)(void *))(base+0x3826f2c))(&value);return result;
}
static int registry_command_enabled(void *root,void *key)
{
  static void *command;static const uint16_t empty;
  if(!command)command=((void *(*)(const char *))(base+NXS_GECKO_POPUP_ATOMIZE))("command");
  struct GeckoString id={.data=&empty,.flags=1};
  ((int (*)(void *,void *,void *))(base+NXS_GECKO_POPUP_GET_ATTR))(key,command,&id);
  int enabled=1;
  if(id.length) {
    void *target=((void *(*)(void *,const void *))(base+0x4899594))(root,&id);
    enabled=target&&!registry_boolean(target,"disabled")&&!registry_boolean(target,"internal");
  }
  ((void (*)(void *))(base+0x3826f2c))(&id);return enabled;
}
static void registry_recompute(void *model)
{
  original_registry_recompute(model);
  struct GeckoMenuRegistry *r=registry_for(model);if(!r)return;
  static void *library;static void *(*children)(void *);static int (*property)(void *,const char *,int);
  static int (*string_property)(void *,const char *,const char *);static void *id_atom;
  if(!library)library=dlopen("libdbusmenu-glib.so.4",RTLD_LAZY|RTLD_NOLOAD);
  if(!library)return;
  if(!children)children=dlsym(library,"dbusmenu_menuitem_get_children");
  if(!property)property=dlsym(library,"dbusmenu_menuitem_property_set_bool");
  if(!string_property)string_property=dlsym(library,"dbusmenu_menuitem_property_set");
  if(!id_atom)id_atom=((void *(*)(const char *))(base+NXS_GECKO_POPUP_ATOMIZE))("id");
  if(!children||!property||!string_property||!id_atom)return;
  static const uint16_t name[]=u"key";
  const struct GeckoString tag={.data=name,.length=3,.flags=1};
  void *list=((void *(*)(void *,const void *))(base+NXS_GECKO_TABS_GET_TABS))(r->root,&tag);
  if(!list)return;
  unsigned count=((unsigned (*)(void *))(base+NXS_GECKO_TABS_LIST_LENGTH))(list),added=0;
  if(count<=2048)for(unsigned i=0;i<count;i++) {
    void *key=((void *(*)(void *,unsigned))(base+NXS_GECKO_TABS_LIST_ITEM))(list,i);
    if(!key||registry_boolean(key,"internal"))continue;
    void *parent=*(void **)((char *)key+48);
    if(!parent||registry_boolean(parent,"disabled"))continue;
    void *root=*(void **)((char *)model+56);
    /* AppendMenuItem already owns key parsing, modifier metadata, enabled
     * state and the original XUL command callback. Do not reproduce them. */
    ((void (*)(void *,void *))(base+0x6afac14))(root,key);
    struct GeckoRegistryList {void *data;struct GeckoRegistryList *next,*previous;};
    struct GeckoRegistryList *last=children(root);if(!last)continue;
    while(last->next)last=last->next;
    property(last->data,"x-nextspace-key-only",1);
    /* Distinct original keys can intentionally have identical shortcuts.
     * Preserve their original element IDs across exporter object rebuilds. */
    static const uint16_t empty;
    struct GeckoString id={.data=&empty,.flags=1};
    ((int (*)(void *,void *,void *))(base+NXS_GECKO_POPUP_GET_ATTR))(key,id_atom,&id);
    char *source=utf8_text(id.data,id.length);
    if(source&&*source)string_property(last->data,"x-nextspace-key-source",source);
    free(source);((void (*)(void *))(base+0x3826f2c))(&id);
    property(last->data,"enabled",!registry_boolean(key,"disabled")&&registry_command_enabled(r->root,key));added++;
  }
  ((unsigned (*)(void *))(base+NXS_GECKO_TABS_LIST_RELEASE))(list);
  if(log_fd>=0)dprintf(log_fd,"%d native-menu-key-registry count=%u\n",getpid(),added);
}
static int registry_source(void *node)
{
  if(!node)return 0;
  /* kNameSpaceID_XUL is 8 in this pinned Gecko build. */
  void *info=*(void **)((char *)node+40);if(!info||*(uint32_t *)((char *)info+32)!=8)return 0;
  static void *key,*set,*command;
  if(!key)key=((void *(*)(const char *))(base+NXS_GECKO_POPUP_ATOMIZE))("key");
  if(!set)set=((void *(*)(const char *))(base+NXS_GECKO_POPUP_ATOMIZE))("keyset");
  if(!command)command=((void *(*)(const char *))(base+NXS_GECKO_POPUP_ATOMIZE))("command");
  void *name=*(void **)((char *)info+16);return name==key||name==set||name==command;
}
static int registry_menu_source(void *model,void *node)
{
  void *menu=*(void **)((char *)model+40);
  for(unsigned depth=0;node&&depth<64;depth++,node=*(void **)((char *)node+48))
    if(node==menu)return 1;
  return 0;
}
static void registry_insert(void *model,void *child,void *info)
{
  if(!registry_for(model)||registry_menu_source(model,child))original_registry_insert(model,child,info);
  else if(registry_source(child))((void (*)(void *))(base+0x6af9a04))(model);
}
static void registry_remove(void *model,void *child,void *info)
{
  /* Reuse Gecko's own script-runner scheduling after removal completes. */
  if(!registry_for(model)||registry_menu_source(model,child))original_registry_remove(model,child,info);
  else if(registry_source(child))original_registry_remove(model,*(void **)((char *)model+40),info);
}
static void registry_attribute(void *model,void *element,int ns,void *attribute,int type,const void *old)
{
  if(!registry_for(model)||registry_menu_source(model,element))original_registry_attribute(model,element,ns,attribute,type,old);
  else if(registry_source(element))((void (*)(void *))(base+0x6af9a04))(model);
}
static const unsigned char registry_create_bytes[20]={0x3f,0x23,0x03,0xd5,0xfe,0x0f,0x1e,0xf8,0xf4,0x4f,0x01,0xa9,0x08,0x00,0x80,0x12,0xf3,0x03,0x00,0xaa};
static const unsigned char registry_destroy_bytes[20]={0x3f,0x23,0x03,0xd5,0xfe,0x4f,0xbf,0xa9,0xf3,0x03,0x00,0xaa,0x00,0x1c,0x40,0xf9,0x40,0x00,0x00,0xb4};
static const unsigned char registry_delete_bytes[20]={0x3f,0x23,0x03,0xd5,0xfe,0x4f,0xbf,0xa9,0xf3,0x03,0x00,0xaa,0x00,0x1c,0x40,0xf9,0x40,0x00,0x00,0xb4};
static const unsigned char registry_recompute_bytes[20]={0x3f,0x23,0x03,0xd5,0xfe,0x57,0xbe,0xa9,0xf4,0x4f,0x01,0xa9,0x34,0xcc,0x01,0x90,0xf3,0x03,0x00,0xaa};
static const unsigned char registry_insert_bytes[20]={0x5f,0x24,0x03,0xd5,0x28,0x70,0x40,0x39,0x08,0x05,0x20,0x36,0x28,0x14,0x40,0xf9,0x09,0x21,0x40,0xb9};
static const unsigned char registry_remove_bytes[20]={0x5f,0x24,0x03,0xd5,0x28,0x70,0x40,0x39,0x48,0x03,0x20,0x36,0x28,0x14,0x40,0xf9,0x09,0x21,0x40,0xb9};
static const unsigned char registry_attribute_bytes[20]={0x5f,0x24,0x03,0xd5,0x28,0x70,0x40,0x39,0x48,0x05,0x20,0x36,0x28,0x14,0x40,0xf9,0x09,0x21,0x40,0xb9};
static struct Detour registry_detours[]={
  {0x6b142b8,registry_create_bytes,registry_create,(void **)&original_registry_create},
  {0x6b107d0,registry_destroy_bytes,registry_destroy,(void **)&original_registry_destroy},
  {0x6b108a8,registry_delete_bytes,registry_delete,(void **)&original_registry_delete},
  {0x6afa9fc,registry_recompute_bytes,registry_recompute,(void **)&original_registry_recompute},
  {0x6af9a44,registry_insert_bytes,registry_insert,(void **)&original_registry_insert},
  {0x6af992c,registry_remove_bytes,registry_remove,(void **)&original_registry_remove},
  {0x6af9af0,registry_attribute_bytes,registry_attribute,(void **)&original_registry_attribute},
};
static int prepare_key_registry(void)
{
  static const unsigned char lookup[20]={0x3f,0x23,0x03,0xd5,0xff,0x43,0x01,0xd1,0xfe,0x13,0x00,0xf9,0xf6,0x57,0x03,0xa9,0xf4,0x4f,0x04,0xa9};
  static const unsigned char append[20]={0x3f,0x23,0x03,0xd5,0xfd,0x7b,0xba,0xa9,0xfc,0x6f,0x01,0xa9,0xfa,0x67,0x02,0xa9,0xf8,0x5f,0x03,0xa9};
  static const unsigned char dirty[20]={0x5f,0x24,0x03,0xd5,0x09,0xc4,0x40,0x39,0x28,0x00,0x80,0x52,0x08,0xc0,0x00,0x39,0x3f,0x05,0x00,0x71};
  static const unsigned char activation[20]={0x3f,0x23,0x03,0xd5,0xfe,0x4f,0xbf,0xa9,0xf3,0x03,0x02,0xaa,0x62,0x00,0x00,0xb4,0xe0,0x03,0x13,0xaa};
  return !memcmp((void *)(base+0x4899594),lookup,20)&&
    !memcmp((void *)(base+0x6afac14),append,20)&&!memcmp((void *)(base+0x6af9a04),dirty,20)&&
    !memcmp((void *)(base+0x6b12644),activation,20)&&
    !memcmp((void *)(base+NXS_GECKO_TABS_GET_TABS),gecko_tabs_get_tabs_bytes,20)&&
    !memcmp((void *)(base+NXS_GECKO_TABS_LIST_LENGTH),gecko_tabs_list_length_bytes,20)&&
    !memcmp((void *)(base+NXS_GECKO_TABS_LIST_ITEM),gecko_tabs_list_item_bytes,20)&&
    !memcmp((void *)(base+NXS_GECKO_TABS_LIST_RELEASE),gecko_tabs_list_release_bytes,20)&&
    prepare_detours(registry_detours,sizeof(registry_detours)/sizeof(*registry_detours));
}
