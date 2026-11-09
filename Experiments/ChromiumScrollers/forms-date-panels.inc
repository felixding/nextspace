/* Original Blink popup lifecycle to the shared native calendar panel. The
 * existing DateBinding owns data/actions; no picker or permission logic here. */
static struct {void *view;uint32_t node;struct NXSPopupBinding popup;NXSDateModel domain;} date_panel_session;
static void (*original_date_panel_open)(void *),(*original_date_panel_close)(void *);
static int (*original_date_panel_opened)(const void *),(*original_date_panel_visible)(const void *);
static void date_panel_end(void)
{
  struct NXSPopupBinding popup=date_panel_session.popup;
  memset(&date_panel_session,0,sizeof(date_panel_session));native_popup_binding_end(&popup);
}
static void date_panel_open(void *view)
{
  struct NativeForm *form=native_forms;
  while(form&&!(form->kind==NXS_DATEPICKER&&form->painted&&date_view(form->node)==view))form=form->next;
  if(!form||!date_enabled(form->node)){original_date_panel_open(view);return;}
  if(date_panel_session.view&&date_panel_session.view!=view)date_panel_end();
  NXSDateModel model;
  if(!date_model(form->node,&model)||!sync_date_image(form,form_request(form,1,0,0,0))||
     !form_sync_screen_origin(form)||!native_popup_binding_open(&date_panel_session.popup,NXS_DATEPICKER,form->control)) {
    original_date_panel_open(view);return;
  }
  date_panel_session.view=view;date_panel_session.node=radio_node_id(form->node);date_panel_session.domain=model;
  form->input_owned=1;
  if(!refresh_form_watch()){date_panel_end();original_date_panel_open(view);return;}
  note("native calendar panel opened through original Blink popup boundary");
}
static void date_panel_close(void *view)
{if(date_panel_session.view==view)date_panel_end();original_date_panel_close(view);}
static int date_panel_opened(const void *view)
{return date_panel_session.view==view?native_popup_binding_poll(&date_panel_session.popup)>0:original_date_panel_opened(view);}
static int date_panel_visible(const void *view)
{return date_panel_session.view==view?native_popup_binding_poll(&date_panel_session.popup)>0:original_date_panel_visible(view);}
static void date_panel_forget(void *node)
{if(date_panel_session.view&&date_panel_session.node==radio_node_id(node))date_panel_end();}
static int date_panel_watch_needed(void){return date_panel_session.popup.open;}
static void date_panel_geometry_work(void)
{
  if(!date_panel_session.view)return;
  void *node=radio_node_for_id(date_panel_session.node);
  struct NativeForm *form=node?find_form(node):NULL;
  if(!form||form->kind!=NXS_DATEPICKER||form->control!=date_panel_session.popup.control||
     !date_enabled(node)||!form_sync_screen_origin(form))date_panel_end();
}
static void date_panel_native_work(int failed)
{
  if(!date_panel_session.view)return;
  uint32_t id=date_panel_session.node;uint64_t control=date_panel_session.popup.control;
  int visible=failed?-1:native_popup_binding_poll(&date_panel_session.popup);
  void *node=radio_node_for_id(id);struct NativeForm *form=node?find_form(node):NULL;
  NXSDateModel model;
  if(visible<0||!form||form->control!=control||!date_enabled(node)||!date_model(node,&model)||
     !native_date_model_domain_same(&model,&date_panel_session.domain)||!form_sync_screen_origin(form)){date_panel_end();return;}
  date_apply(form);
  if(date_panel_session.node!=id||date_panel_session.popup.control!=control)return;
  node=radio_node_for_id(id);form=node?find_form(node):NULL;
  if(!form||form->control!=control){date_panel_end();return;}
  date_commit(node,control);
  if(date_panel_session.node!=id||date_panel_session.popup.control!=control)return;
  if(!visible||!date_enabled(node)||!date_model(node,&model)||
     !native_date_model_domain_same(&model,&date_panel_session.domain))date_panel_end();
}
static struct Detour date_panel_detours[]={
 {NXS_DATE_PANEL_OPEN,date_panel_open_bytes,date_panel_open,(void **)&original_date_panel_open},
 {NXS_DATE_PANEL_CLOSE,date_panel_close_bytes,date_panel_close,(void **)&original_date_panel_close},
 {NXS_DATE_PANEL_OPENED,date_panel_opened_bytes,date_panel_opened,(void **)&original_date_panel_opened},
 {NXS_DATE_PANEL_VISIBLE,date_panel_visible_bytes,date_panel_visible,(void **)&original_date_panel_visible}
};
