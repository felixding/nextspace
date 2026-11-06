/* Complete the application's external-menu lifecycle with Gecko's own event
 * dispatcher. NativeUI still owns every menu control and tracking behavior. */
static int menu_lifecycle_requested;
static int (*original_dbus_menu_event)(void *,const char *,void *,unsigned,void *);
static int dbus_menu_event(void *item,const char *name,void *value,unsigned timestamp,void *element)
{
  /* Popup handlers can remove the target from the document. Retain it across
   * the unmodified exporter callback, as Gecko's callback itself does. */
  if(element)((unsigned (*)(void *))(base+0x3b9f0e4))(element);
  int result=original_dbus_menu_event(item,name,value,timestamp,element);
  if(element&&(!strcmp(name,"opened")||!strcmp(name,"closed"))) {
    static const uint16_t inactive[]=u"DOMMenuBarInactive";
    const struct GeckoString type={.data=inactive,.length=sizeof(inactive)/sizeof(*inactive)-1,.flags=1};
    /* The exported popup events bubble to AutoHideMenubar, although the XUL
     * menubar itself is inactive and hidden by Firefox's native attribute.
     * Keep that internal bar inactive through its existing trusted event;
     * otherwise it leaves an empty toolbar after an external menu opens.
     * CanBubble::eYes=0, ChromeOnlyDispatch::eNo=1, Composed::eDefault=2. */
    ((void (*)(void *,const void *,unsigned,unsigned,unsigned))(base+0x56d6a70))(element,&type,0,1,2);
    note("native external menu retained inactive internal menubar");
  }
  if(element)((unsigned (*)(void *))(base+0x570faf0))(element);
  return result;
}
static const unsigned char dbus_menu_event_bytes[]={0x3f,0x23,0x03,0xd5,0xfe,0x0f,0x1e,0xf8,0xf4,0x4f,0x01,0xa9,0xf3,0x03,0x04,0xaa,0xf4,0x03,0x01,0xaa};
static struct Detour menu_lifecycle_detours[]={
  {0x6b12674,dbus_menu_event_bytes,dbus_menu_event,(void **)&original_dbus_menu_event}
};
static int prepare_menu_lifecycle(void)
{
  static const unsigned char safe_event[]={0x3f,0x23,0x03,0xd5,0xfe,0x67,0xbc,0xa9,0xf8,0x5f,0x01,0xa9,0xf6,0x57,0x02,0xa9,0xf4,0x4f,0x03,0xa9};
  return !menu_lifecycle_requested||(!memcmp((void *)(base+0x56d6a70),safe_event,sizeof(safe_event))&&
    prepare_detours(menu_lifecycle_detours,sizeof(menu_lifecycle_detours)/sizeof(*menu_lifecycle_detours)));
}
