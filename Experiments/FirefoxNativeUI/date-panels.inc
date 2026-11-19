/* Gecko permissions/model/lifetime to the shared original NSDatePicker panel.
 * No calendar, editing rules, window drawing or focus policy is copied here.
 * GPL-2.0-or-later. */
static struct {
  void *node,*focus,*window;
  struct NXSPopupBinding popup;
  NXSDateModel domain;
  unsigned timer;
} date_panel_session;
static void (*original_date_show_picker)(void *,struct GeckoError *);
static void (*original_date_open_picker)(void *,const void *);
static void (*original_date_close_picker)(void *);
static void *date_panel_focus_manager(void)
{
  void *manager=*(void **)(base+0xa439c38);
  /* Original nsIFocusManager interface, from the pinned IDL. In particular,
   * SetFocus/MoveFocus verify its interface address and method ordering. */
  uintptr_t *methods=manager?*(uintptr_t **)manager:NULL;
  return methods&&methods[11]==base+0x487316c&&methods[12]==base+0x4873490?manager:NULL;
}
static int date_panel_focus_owner(void *window,void **focus)
{
  void *manager=date_panel_focus_manager(),*focused_window=NULL;
  *focus=NULL;if(!manager||!window)return 0;
  uint32_t status=((uint32_t (*)(void *,void *,uint8_t,void **,void **))
    (*(uintptr_t **)manager)[14])(manager,window,1,&focused_window,focus);
  gecko_release_window(focused_window);
  return !(status&0x80000000u);
}
static int date_panel_origin(struct Widget *w)
{
  struct NXSRectD bounds;void *node=w->node;uint64_t id=w->id;
  if(!gecko_frame_screen_bounds(w->frame,&bounds))return 0;
  w=widget_for_node(node);
  return w&&w->id==id&&native_popup_binding_bounds(NXS_DATEPICKER,id,bounds);
}
static void date_panel_end(void)
{
  void *node=date_panel_session.node;
  void *focus=date_panel_session.focus,*window=date_panel_session.window;
  unsigned timer=date_panel_session.timer;
  struct NXSPopupBinding popup=date_panel_session.popup;
  memset(&date_panel_session,0,sizeof(date_panel_session));
  if(timer) {
    int (*remove)(unsigned)=dlsym(RTLD_DEFAULT,"g_source_remove");
    if(remove)remove(timer);
  }
  native_popup_binding_end(&popup);
  if(focus)((unsigned (*)(void *))(base+0x47ba6b8))(focus);
  gecko_release_window(window);
  if(node)((unsigned (*)(void *))(base+0x47ba6b8))(node);
}
static int date_panel_tick(void *unused)
{
  void *node=date_panel_session.node;
  uint64_t control=date_panel_session.popup.control;
  struct Widget *w=node?widget_for_node(node):NULL;
  NXSDateModel model;
  void *focus=NULL;
  int focus_valid=date_panel_focus_owner(date_panel_session.window,&focus);
  int same_focus=focus_valid&&focus==date_panel_session.focus;
  if(focus)((unsigned (*)(void *))(base+0x47ba6b8))(focus);
  if(!w||w->id!=control||!date_mutable(node)||!native_date_frame(w->frame)||
     !same_focus||!date_model(node,&model)||
     !native_date_model_domain_same(&model,&date_panel_session.domain)||
     !native_popup_binding_current(&date_panel_session.popup)) {
    if(log_fd>=0)dprintf(log_fd,"%d native calendar owner retired control=%llu node=%p widget=%p focus=%p expected=%p\n",
      getpid(),(unsigned long long)control,node,w,focus,date_panel_session.focus);
    date_panel_session.timer=0;date_panel_end();return 0;
  }
  /* The DOM owner is still valid. A temporary configuration/origin reply
   * failure must not abandon its original native panel and close receipt. */
  /* Keep the canonical model current without requesting inline bitmap
   * snapshots on every owner poll. Native invalidations own repainting. */
  if(!native_date_binding_sync(&w->date,&model,date_tracking(w))||!date_panel_origin(w)) {
    if(native_popup_binding_current(&date_panel_session.popup))return 1;
    date_panel_session.timer=0;date_panel_end();return 0;
  }
  int visible=native_popup_binding_poll(&date_panel_session.popup);
  /* Per-window DOM focus survives native auxiliary activation, unlike the
   * process-wide active-content pointer. It still detects real script blur
   * and owner changes. NSPanel retains its original window focus lifecycle. */
  if(visible>=0)date_apply(w);
  if(date_panel_session.node!=node||date_panel_session.popup.control!=control)return 0;
  if(visible<=0){note("native calendar window closed");date_panel_session.timer=0;date_panel_end();return 0;}
  return 1;
}
static int date_panel_begin(void *node)
{
  struct Widget *w=widget_for_node(node);
  NXSDateModel model;
  if(!w||!date_mutable(node)||!native_date_frame(w->frame)||
     !date_model(node,&model)) {
    if(log_fd>=0)dprintf(log_fd,"%d native calendar model unavailable widget=%d painted=%d\n",
      getpid(),!!w,w?!!w->painted:0);
    return 0;
  }
  /* Original ShowPicker already validated activation and the DOM owner.
   * A temporarily unavailable inline bitmap is not a lost picker owner.
   * The model and native configuration below remain required. */
  /* The source gesture can dismiss the native panel before ShowPicker runs.
   * A retained source session alone does not mean its native window is open. */
  if(date_panel_session.node==node&&date_panel_session.popup.control==w->id&&
     native_date_model_domain_same(&model,&date_panel_session.domain)&&
     native_popup_binding_poll(&date_panel_session.popup)>0)return 1;
  unsigned (*add)(unsigned,int (*)(void *),void *)=dlsym(RTLD_DEFAULT,"g_timeout_add");
  if(!add)return 0;
  date_panel_end();
  if(!widget_sync(w)) {
    if(log_fd>=0)dprintf(log_fd,"%d native calendar configuration unavailable control=%llu size=%.3f,%.3f errno=%d\n",getpid(),(unsigned long long)w->id,w->width,w->height,errno);
    return 0;
  }
  if(!date_panel_origin(w)) {
    note("native calendar origin unavailable");return 0;
  }
  void *manager=date_panel_focus_manager(),*window=gecko_node_owner_window(node),*focus=NULL;
  if(!manager){gecko_release_window(window);note("native calendar focus manager unavailable");return 0;}
  if(!window||!date_panel_focus_owner(window,&focus)) {
    if(log_fd>=0)dprintf(log_fd,"%d native calendar document window unavailable window=%d\n",
      getpid(),!!window);
    gecko_release_window(window);return 0;
  }
  if(!native_popup_binding_open(&date_panel_session.popup,NXS_DATEPICKER,w->id)) {
    if(focus)((unsigned (*)(void *))(base+0x47ba6b8))(focus);
    gecko_release_window(window);
    note("Gecko native calendar open reply unavailable");return 0;
  }
  ((unsigned (*)(void *))(base+0x3b9f0e4))(node);
  date_panel_session.node=node;date_panel_session.focus=focus;date_panel_session.window=window;
  date_panel_session.domain=model;date_panel_session.timer=add(40,date_panel_tick,NULL);
  if(!date_panel_session.timer){date_panel_end();return 0;}
  note("native calendar panel opened after original Gecko permission boundary");return 1;
}
static void date_show_picker(void *node,struct GeckoError *error)
{
  int native=date_node(node);
  if(native)((unsigned (*)(void *))(base+0x3b9f0e4))(node);
  /* Keep Gecko's mutability, same-origin, transient-activation consumption and
   * composed-document gates. Its replaced UA shadow editor is empty, so only
   * a successful original call is followed by native panel presentation. */
  original_date_show_picker(node,error);
  if(log_fd>=0)dprintf(log_fd,"%d original Gecko calendar request native=%d status=%08x\n",
    getpid(),native,error->result);
  if(native) {
    if(!error->result)date_panel_begin(node);
    ((unsigned (*)(void *))(base+0x47ba6b8))(node);
  }
}
static void date_open_picker(void *node,const void *value)
{if(!date_node(node)||!date_panel_begin(node))original_date_open_picker(node,value);}
static void date_close_picker(void *node)
{if(date_panel_session.node==node){note("original Gecko picker close");date_panel_end();}original_date_close_picker(node);}
static void date_panel_forget(struct Widget *w)
{if(date_panel_session.node==w->node&&date_panel_session.popup.control==w->id)date_panel_end();}
