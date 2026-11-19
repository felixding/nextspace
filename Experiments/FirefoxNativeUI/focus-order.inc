/* Preserve focus/input order through Gecko's original IPC queue barriers.
 * Its input-priority queue can overtake normal-priority Activate/Deactivate
 * while native drawing occupies the content thread. SetInputPriorityEventEnabled
 * already supplies suspend/flush/resume barriers for the same ordering problem
 * in drag sessions. Bracket the original focus message with those barriers,
 * retaining the former priority mode. No focus or key behavior is implemented.
 * GPL-2.0-or-later. */
static void (*original_browser_activate)(void *,uint64_t);
static void (*original_browser_deactivate)(void *,int,uint64_t);
static void *native_focus_input_barrier(void *browser)
{
  if(!widgets_enabled)return NULL;
  void *parent=((void *(*)(void *))(base+0x34fcd1c))(browser);
  uint16_t flags=0;if(parent)memcpy(&flags,(char *)parent+0x319,sizeof(flags));
  if(!(flags&0x100))return NULL;
  ((void (*)(void *,int))(base+0x657ddcc))(parent,0);
  return parent;
}
static void native_focus_input_resume(void *parent)
{if(parent)((void (*)(void *,int))(base+0x657ddcc))(parent,1);}
static void native_browser_activate(void *browser,uint64_t action)
{
  void *parent=native_focus_input_barrier(browser);
  original_browser_activate(browser,action);native_focus_input_resume(parent);
}
static void native_browser_deactivate(void *browser,int lowering,uint64_t action)
{
  void *parent=native_focus_input_barrier(browser);
  original_browser_deactivate(browser,lowering,action);native_focus_input_resume(parent);
}
static const unsigned char focus_activate_bytes[]={0x3f,0x23,0x03,0xd5,0xff,0x43,0x01,0xd1,0xfe,0x13,0x00,0xf9,0xf6,0x57,0x03,0xa9,0xf4,0x4f,0x04,0xa9};
static const unsigned char focus_deactivate_bytes[]={0x3f,0x23,0x03,0xd5,0xff,0x03,0x01,0xd1,0xfe,0x0b,0x00,0xf9,0xf6,0x57,0x02,0xa9,0xf4,0x4f,0x03,0xa9};
static struct Detour focus_order_detours[]={
  {0x655fd6c,focus_activate_bytes,native_browser_activate,(void **)&original_browser_activate},
  {0x655ff14,focus_deactivate_bytes,native_browser_deactivate,(void **)&original_browser_deactivate}
};
static int prepare_focus_input_order(void)
{
  static const unsigned char manager[]={0x5f,0x24,0x03,0xd5,0x00,0x10,0x40,0xf9,0xc0,0x03,0x5f,0xd6};
  static const unsigned char toggle[]={0x5f,0x24,0x03,0xd5,0x08,0x64,0x0c,0x91,0x09,0x01,0x40,0x79,0xa9,0x00,0x38,0x36,0x3f,0x01,0x18,0x72};
  return !memcmp((void *)(base+0x34fcd1c),manager,sizeof(manager))&&!memcmp((void *)(base+0x657ddcc),toggle,sizeof(toggle))&&prepare_detours(focus_order_detours,2);
}
