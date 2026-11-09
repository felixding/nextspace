/* Gecko permissions/model/lifetime to the shared original NSDatePicker panel.
 * No calendar, editing rules, window drawing or focus policy is copied here.
 * GPL-2.0-or-later. */
static struct {
  void *node,*focus;
  struct NXSPopupBinding popup;
  NXSDateModel domain;
  unsigned timer;
} date_panel_session;
static void (*original_date_show_picker)(void *,struct GeckoError *);
static void (*original_date_open_picker)(void *,const void *);
static void (*original_date_close_picker)(void *);
static void *date_panel_focus_owner(void)
{
  void *manager=*(void **)(base+0xa439c38);
  return manager?*(void **)((char *)manager+128):NULL;
}
static int date_panel_origin(struct Widget *w)
{
  double x,y;
  return gecko_frame_screen_origin(w->frame,&x,&y)&&
    native_popup_binding_origin(NXS_DATEPICKER,w->id,x,y);
}
static void date_panel_end(void)
{
  void *node=date_panel_session.node;
  unsigned timer=date_panel_session.timer;
  struct NXSPopupBinding popup=date_panel_session.popup;
  memset(&date_panel_session,0,sizeof(date_panel_session));
  if(timer) {
    int (*remove)(unsigned)=dlsym(RTLD_DEFAULT,"g_source_remove");
    if(remove)remove(timer);
  }
  native_popup_binding_end(&popup);
  if(node)((unsigned (*)(void *))(base+0x47ba6b8))(node);
}
static int date_panel_tick(void *unused)
{
  void *node=date_panel_session.node;
  uint64_t control=date_panel_session.popup.control;
  struct Widget *w=node?widget_for_node(node):NULL;
  NXSDateModel model;
  if(!w||w->id!=control||!date_mutable(node)||!native_date_frame(w->frame)||
     date_panel_focus_owner()!=date_panel_session.focus||!date_model(node,&model)||
     !native_date_model_domain_same(&model,&date_panel_session.domain)||
     !widget_sync(w)||!date_panel_origin(w)) {
    date_panel_session.timer=0;date_panel_end();return 0;
  }
  int visible=native_popup_binding_poll(&date_panel_session.popup);
  if(visible>=0)date_apply(w);
  if(date_panel_session.node!=node||date_panel_session.popup.control!=control)return 0;
  if(visible<=0){date_panel_session.timer=0;date_panel_end();return 0;}
  return 1;
}
static int date_panel_begin(void *node)
{
  struct Widget *w=widget_for_node(node);
  NXSDateModel model;
  if(!w||!w->painted||!date_mutable(node)||!native_date_frame(w->frame)||
     !date_model(node,&model))return 0;
  if(date_panel_session.node==node&&date_panel_session.popup.control==w->id)return 1;
  unsigned (*add)(unsigned,int (*)(void *),void *)=dlsym(RTLD_DEFAULT,"g_timeout_add");
  if(!add)return 0;
  date_panel_end();
  if(!widget_sync(w)||!date_panel_origin(w))return 0;
  if(!native_popup_binding_open(&date_panel_session.popup,NXS_DATEPICKER,w->id)) {
    note("Gecko native calendar open reply unavailable");return 0;
  }
  ((unsigned (*)(void *))(base+0x3b9f0e4))(node);
  date_panel_session.node=node;date_panel_session.focus=date_panel_focus_owner();
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
  if(native) {
    if(!error->result)date_panel_begin(node);
    ((unsigned (*)(void *))(base+0x47ba6b8))(node);
  }
}
static void date_open_picker(void *node,const void *value)
{if(!date_node(node)||!date_panel_begin(node))original_date_open_picker(node,value);}
static void date_close_picker(void *node)
{if(date_panel_session.node==node)date_panel_end();original_date_close_picker(node);}
static void date_panel_forget(struct Widget *w)
{if(date_panel_session.node==w->node&&date_panel_session.popup.control==w->id)date_panel_end();}
