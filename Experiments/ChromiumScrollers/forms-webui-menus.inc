/* Shared WebUI menu-model/lifecycle adapter. The existing NativeUI NSMenu
 * implementation owns rendering, checkmarks, placement, tracking and keys. */
static __thread int (*component_previous_menu)(const struct NXSNativeMenuCommand *);
static struct NativeForm *component_menu_find(uint64_t control)
{
 for(struct NativeForm *form=native_forms;form;form=form->next)
  if(form->kind==NXS_WEBUI_MENU&&form->menu_control==control)return form;
 return NULL;
}
static int component_menu_command(const struct NXSNativeMenuCommand *request)
{
 struct NativeForm *form=component_menu_find(request->control);
 if(!form)return component_previous_menu?component_previous_menu(request):0;
 if(!form->menu_bound||!form->popup_open||request->phase>NXS_COMMAND_EXECUTE)return 0;
 if(!request->command) {
  if(request->phase!=NXS_COMMAND_EXECUTE)return 0;
  form->menu_closed=1;return 1;
 }
 struct PopupSnapshot snapshot;if(!popup_snapshot(form->node,&snapshot))return 0;
 int valid=popup_same_model(form,&snapshot),found=0;
 if(valid)for(unsigned i=0;i<snapshot.request->count;i++)
  if(radio_node_id(snapshot.nodes[i])==request->command&&form_enabled(snapshot.nodes[i])){found=1;break;}
 popup_snapshot_free(&snapshot);
 if(found&&request->phase==NXS_COMMAND_EXECUTE)form->menu_selected=request->command;
 return found;
}
static struct NXSResponse *component_menu_request(struct NativeForm *form,int operation)
{
 if(operation==6) {
  if(form->menu_bound)native_menu_request(form->menu_control,29,0);
  form->menu_bound=0;return NULL;
 }
 return form->menu_bound?native_menu_request(form->menu_control,28,-1):NULL;
}
static struct NXSResponse *component_menu_key(struct NativeForm *form,const NXSKeyEvent *key)
{
 static __thread struct NXSResponse response;
 int accepted=form->menu_bound&&native_application_menu_key(key,1);
 response=(struct NXSResponse){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.size=sizeof(response)};
 response.parts[3].x=accepted?NXS_INPUT_HANDLED:NXS_INPUT_UNHANDLED;
 return &response;
}
static int component_menu_open(struct NativeForm *form,void *engine)
{
 uint32_t owner=radio_node_id(form->node);uint64_t control=form->control;
 form->popup_engine=engine;form->popup_open=1;form->input_owned=1;
 if(!refresh_form_watch())goto failed;
 if(native_menu_handler!=component_menu_command)component_previous_menu=native_menu_handler;
 if(!native_menu_filter_register(component_menu_command))goto failed;
 struct Rect screen;if(!form_screen_rectangle(form,&screen))goto failed;
 form=find_form(radio_node_for_id(owner));if(!form||form->control!=control)return 0;
 struct PopupSnapshot snapshot;if(!popup_snapshot(form->node,&snapshot))goto failed;
 unsigned count=snapshot.request->count;
 NXSMenuItem *items=calloc(count?count:1,sizeof(*items));if(!items){popup_snapshot_free(&snapshot);goto failed;}
 unsigned ready=0;
 for(;ready<count;ready++) {
  void *node=snapshot.nodes[ready];unsigned kind=*((unsigned char *)*(uintptr_t *)node-17);
  char *label=popup_item_label(form->node,node);if(!label)break;
  unsigned flags=0;char *text=label;
  if(kind!=0x38&&kind!=0x37)flags=NXS_MENU_SEPARATOR;
  else {
   char *end;unsigned long value=strtoul(label,&end,10);
   if(end==label||*end!='|'||value&~(NXS_MENU_DISABLED|NXS_MENU_CHECKED|NXS_MENU_MIXED)){free(label);break;}
   flags=value;text=end+1;if(!form_enabled(node))flags|=NXS_MENU_DISABLED;
  }
  items[ready]=(NXSMenuItem){.size=sizeof(NXSMenuItem),.parent=-1,
   .command=flags&NXS_MENU_SEPARATOR?0:radio_node_id(node),.title=strdup(text),.flags=flags};
  free(label);if(!items[ready].title)break;
 }
 if(ready==count) {
  popup_free_model(form);
  form->popup_size=snapshot.request->text_size;form->popup_count=count;
  form->popup_selected=snapshot.request->selected;form->popup_selected_list=snapshot.selected_list;
  form->popup_selected_node=snapshot.selected_node;
  form->popup_model=malloc(form->popup_size?form->popup_size:1);
  if(form->popup_model)memcpy(form->popup_model,snapshot.request+1,form->popup_size);
  form->popup_indices=snapshot.indices;snapshot.indices=NULL;
  form->popup_nodes=snapshot.nodes;snapshot.nodes=NULL;
  form->popup_title=snapshot.title;snapshot.title=NULL;
  form->menu_control=(UINT64_C(1)<<42)|control;form->menu_closed=0;form->menu_selected=0;
  form->menu_bound=!!form->popup_model;
  if(form->menu_bound&&!native_menu_model_kind(form->menu_control,"",items,count,3))form->menu_bound=0;
 }
 for(unsigned i=0;i<ready;i++)free((void *)items[i].title);free(items);popup_snapshot_free(&snapshot);
 form=find_form(radio_node_for_id(owner));if(!form||form->control!=control)return 0;
 if(form->menu_bound&&native_menu_popup_request(form->menu_control,screen.x,screen.y))return 1;
failed:
 form=find_form(radio_node_for_id(owner));if(form&&form->control==control){component_menu_request(form,6);form->popup_open=0;}
 return 0;
}
static void component_menus_native_work(int failed)
{
 /* Menu callbacks already signal the existing process invalidation source.
  * Drain on this renderer owner thread, never on the watcher or AppKit thread.
  * A close callback is acknowledged before application actions are dispatched. */
 native_callbacks_dispatch();
 for(;;) {
  struct NativeForm *form=native_forms;
  while(form&&!(form->kind==NXS_WEBUI_MENU&&form->popup_open&&(failed||form->menu_closed)))form=form->next;
  if(!form)break;
  uint32_t owner=radio_node_id(form->node);uint64_t control=form->control;
  if(!failed) {
   struct NXSResponse *state=component_menu_request(form,5);
   if(!state||state->parts[0].y)return; /* Await the helper's final close acknowledgement. */
  }
  uint64_t selected=failed?0:form->menu_selected;void *engine=form->popup_engine;
  component_menu_request(form,6);form->popup_open=0;form->menu_closed=0;popup_engine_closed(engine);
  form=find_form(radio_node_for_id(owner));if(!form||form->control!=control)continue;
  if(selected) {
   struct PopupSnapshot snapshot;
   if(popup_snapshot(form->node,&snapshot)) {
    int index=-1;
    if(popup_same_model(form,&snapshot))for(unsigned i=0;i<snapshot.request->count;i++)
     if(radio_node_id(snapshot.nodes[i])==selected){index=snapshot.indices[i];break;}
    popup_snapshot_free(&snapshot);
    if(index>=0)((void (*)(void *,int))(base+0xe1030e4))(form->node,index);
   }
  }
 }
}
