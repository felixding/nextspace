/* Shared WebUI model ownership. A hidden first list item carries metadata;
 * application values, identities and trusted change events remain in Blink.
 * Existing NativeUI providers supply controls and their input policy. */
static int component_native_kind(void *node)
{
  const char *prefix=getenv("NEXTSPACE_CHROMIUM_WEBUI_RADIO_PREFIX");
  if(!prefix||!popup_element(node))return 0;
  ((int (*)(const void *))(base+0xe0ff7b8))(node); /* Original GetListItems refresh. */
  unsigned count=*(unsigned *)((char *)node+588);
  void *items=*(void **)((char *)node+576);
  if(!count||count>4096||!items)return 0;
  void *first=decode_member(items);if(!first)return 0;
  char *label=popup_item_label(node,first);if(!label)return 0;
  size_t length=strlen(prefix);
  int result=0;
  if(!strncmp(label,prefix,length))result=!strcmp(label+length,"tabs")?NXS_TABVIEW:!strcmp(label+length,"tree")?NXS_OUTLINE:!strcmp(label+length,"menu")?NXS_WEBUI_MENU:!strcmp(label+length,"popup")?NXS_POPUP:0;
  free(label);return result;
}
static struct NXSResponse *component_tabs_sync(struct NativeForm *form,struct NXSResponse *response)
{
  if(!response)return NULL;
  struct PopupSnapshot snapshot;if(!popup_snapshot(form->node,&snapshot))return NULL;
  unsigned count=snapshot.request->count;
  NXSTabItem *items=calloc(count?count:1,sizeof(*items));uint64_t selected=0;
  if(!items){popup_snapshot_free(&snapshot);return NULL;}
  unsigned ready=0;
  for(;ready<count;ready++) {
    char *label=popup_item_label(form->node,snapshot.nodes[ready]);
    uint64_t identifier=radio_node_id(snapshot.nodes[ready]);
    if(!label||!identifier){free(label);break;}
    items[ready]=(NXSTabItem){sizeof(NXSTabItem),identifier,label,NULL};
    if(snapshot.nodes[ready]==snapshot.selected_node)selected=identifier;
  }
  if(ready==count)response=native_tabs_model(form->control,items,count,selected,
    native_layout_scale(form->node,decode_member((char *)form->node+48)));
  else response=NULL;
  for(unsigned i=0;i<ready;i++)free((void *)items[i].title);free(items);
  if(response) {
    popup_free_model(form);
    form->popup_model=(char *)snapshot.request;form->popup_size=snapshot.request->text_size;
    form->popup_count=count;form->popup_selected=snapshot.request->selected;
    form->popup_selected_list=snapshot.selected_list;form->popup_selected_node=snapshot.selected_node;
    form->popup_indices=snapshot.indices;form->popup_nodes=snapshot.nodes;form->popup_title=snapshot.title;
    /* popup_model stores only the original wire body, matching the common
     * snapshot comparator. Keep the same ownership convention as popups. */
    memmove(form->popup_model,snapshot.request+1,form->popup_size);
    snapshot.request=NULL;snapshot.indices=NULL;snapshot.nodes=NULL;snapshot.title=NULL;
  }
  popup_snapshot_free(&snapshot);return response;
}
static void component_tabs_after_input(struct NativeForm *form)
{
  struct NXSTabWireState state;
  if(!native_tabs_state(form->control,&state)||!state.selected)return;
  void *node=form->node;uint64_t control=form->control;
  struct PopupSnapshot snapshot;if(!popup_snapshot(node,&snapshot))return;
  int index=-1;
  if(popup_same_model(form,&snapshot))for(unsigned i=0;i<snapshot.request->count;i++)
    if(radio_node_id(snapshot.nodes[i])==state.selected){index=snapshot.indices[i];break;}
  int changed=index>=0&&index!=snapshot.selected_list;
  popup_snapshot_free(&snapshot);
  if(changed)((void (*)(void *,int))(base+0xe1030e4))(node,index);
  form=find_form(node);if(form&&form->control==control)invalidate_form(form);
}
static int component_tabs_mouse_dispatch(void *manager,void *target,const void *type,const void *event,
    const void *last,void *related,int check,const void *pointer_id,const void *pointer_type,void *down,void *up,
    struct MouseDispatchResult *result)
{
  int button=*(const int *)((const char *)event+120);
  if(!forms_popups_enabled||!same_atom(*(const uintptr_t *)type,0x123a55f8)||(button!=0&&button!=2))return 0;
  void *node=target?((void *(*)(void *))(*(uintptr_t **)target)[9])(target):NULL;
  struct NativeForm *form=form_ancestor(node);
  if(getenv("NEXTSPACE_CHROMIUM_VIEWS_TRACE")&&log_fd>=0)
    dprintf(log_fd,"webui pointer target=%p form=%p kind=%d painted=%d\n",node,form,form?form->kind:0,form?form->painted:0);
  if(!form||(form->kind!=NXS_TABVIEW&&form->kind!=NXS_OUTLINE)||!form->painted||(button==2&&form->kind!=NXS_OUTLINE))return 0;
  uint32_t owner=radio_node_id(form->node);uint64_t control=form->control;
  *result=original_mouse_dispatch(manager,target,type,event,last,related,check,pointer_id,pointer_type,down,up);
  form=find_form(radio_node_for_id(owner));
  unsigned flags=result->event?*(const unsigned short *)((char *)result->event+32):0;
  if(getenv("NEXTSPACE_CHROMIUM_VIEWS_TRACE")&&log_fd>=0)
    dprintf(log_fd,"webui tabs pointer flags=%x form=%p control=%llu\n",flags,form,(unsigned long long)control);
  if(!form||form->control!=control||!(flags&0x100)||(flags&0x20))return 1;
  if(form_request(form,1,0,0,0)) {
    struct FloatPoint point=form_point(form,event);
    if(button==2){component_outline_context(form,point);return 1;}
    struct NXSResponse *response=native_pointer_press(form->kind,control,point.x,point.y,event_modifiers(event),1);
    if(getenv("NEXTSPACE_CHROMIUM_VIEWS_TRACE")&&log_fd>=0)
      dprintf(log_fd,"webui tabs press x=%g y=%g accepted=%g tracking=%g\n",point.x,point.y,response?response->parts[3].x:0,response?response->parts[0].y:0);
    if(form->kind==NXS_OUTLINE) {
      if(response&&response->parts[0].y){active_form=form;refresh_form_watch();invalidate_form(form);}
      return 1;
    }
    for(unsigned i=0;response&&response->parts[0].y&&i<100;i++) {
      struct timespec pause={.tv_nsec=2000000};nanosleep(&pause,NULL);
      response=native_tabs_request(control,37,0,0,1);
    }
    form=find_form(radio_node_for_id(owner));
    if(form&&form->control==control)component_tabs_after_input(form);
  }
  return 1;
}

#include "../../Libraries/NativeUI/Bridge/Outline.inc"

static void component_outline_free(NXSOutlineItem *items,unsigned count)
{if(items){for(unsigned i=0;i<count;i++)free((void *)items[i].title);free(items);}}
static NXSOutlineItem *component_outline_items(struct NativeForm *form,struct PopupSnapshot *snapshot,unsigned *count)
{
 *count=snapshot->request->count/4;if(snapshot->request->count%4)return NULL;
 NXSOutlineItem *items=calloc(*count?*count:1,sizeof(*items));if(!items)return NULL;
 unsigned ready=0;
 for(;ready<*count;ready++) {
  char *label=popup_item_label(form->node,snapshot->nodes[ready*4]);char *end;
  if(!label)break;
  unsigned long parent=strtoul(label,&end,10),flags=0;
  if(end!=label&&*end=='|')flags=strtoul(end+1,&end,10);
  else{free(label);break;}
  if(*end!='|'||flags>15||parent>ready){free(label);break;}
  char *title=strdup(end+1);free(label);if(!title)break;
  items[ready]=(NXSOutlineItem){sizeof(NXSOutlineItem),flags,radio_node_id(snapshot->nodes[ready*4]),parent?radio_node_id(snapshot->nodes[(parent-1)*4]):0,title};
 }
 if(ready!=*count){component_outline_free(items,ready);return NULL;}return items;
}
static char *component_outline_domain(struct NativeForm *form,const NXSOutlineItem *items,unsigned count,size_t *size)
{return native_outline_packet(form->control,items,count,0,size,NXS_OUTLINE_ENABLED|NXS_OUTLINE_EXPANDABLE);}
static struct NXSResponse *component_outline_sync(struct NativeForm *form,struct NXSResponse *response)
{
 if(!response||active_form==form)return response;
 struct PopupSnapshot snapshot;if(!popup_snapshot(form->node,&snapshot))return NULL;
 unsigned count;NXSOutlineItem *items=component_outline_items(form,&snapshot,&count);
 if(!items){popup_snapshot_free(&snapshot);return NULL;}
 response=native_outline_model(form->control,items,count,native_layout_scale(form->node,decode_member((char *)form->node+48)));
 if(response) {
  popup_free_model(form);form->popup_model=component_outline_domain(form,items,count,&form->popup_size);
  if(!form->popup_model)response=NULL;
  if(!form->outline_ready||form->outline_epoch!=atomic_load(&native_host_epoch)) {
   struct NXSNativeActionBatch batch;
   if(native_action_receipts(NXS_OUTLINE,form->control,&form->outline_epoch,&form->outline_cursor,&form->outline_ready,1,&batch)!=1)response=NULL;
  }
 }
 component_outline_free(items,count);popup_snapshot_free(&snapshot);
 if(response){native_wheel_binding(form,1);response=form_request(form,5,0,0,0);}return response;
}
static void component_outline_after_input(struct NativeForm *form)
{
 uint32_t owner=radio_node_id(form->node);uint64_t control=form->control;
 struct NXSNativeActionBatch batch;
 if(native_action_receipts(NXS_OUTLINE,control,&form->outline_epoch,&form->outline_cursor,&form->outline_ready,0,&batch)!=1)return;
 form->outline_cursor=batch.last;
 for(unsigned i=0;i<batch.count;i++) {
  form=find_form(radio_node_for_id(owner));if(!form||form->control!=control)break;
  struct PopupSnapshot snapshot;if(!popup_snapshot(form->node,&snapshot))break;
  unsigned count;NXSOutlineItem *items=component_outline_items(form,&snapshot,&count);size_t size=0;
  char *domain=items?component_outline_domain(form,items,count,&size):NULL;
  const struct NXSActionReceipt *action=batch.actions+i;
  int valid=action->event==NXS_VALUE_CHANGED&&action->state>=-1&&action->state<=1&&action->value>=0&&action->value==trunc(action->value)&&action->value<count&&
   domain&&form->popup_model&&size==form->popup_size&&!memcmp(form->popup_model,domain,size);
  int at=valid?snapshot.indices[(unsigned)action->value*4+action->state+1]:-1;
  free(domain);component_outline_free(items,count);popup_snapshot_free(&snapshot);
  if(at<0){note("native outline stale action discarded");break;}
  ((void (*)(void *,int))(base+0xe1030e4))(form->node,at);
 }
 form=find_form(radio_node_for_id(owner));if(form&&form->control==control)invalidate_form(form);
}

static void component_outline_context(struct NativeForm *form,struct FloatPoint point)
{
 uint64_t identifier=0;
 if(!native_control_item_at_point(NXS_OUTLINE,form->control,point.x,point.y,&identifier)||!identifier)return;
 struct PopupSnapshot snapshot;if(!popup_snapshot(form->node,&snapshot))return;
 unsigned count;NXSOutlineItem *items=component_outline_items(form,&snapshot,&count);size_t size=0;
 char *domain=items?component_outline_domain(form,items,count,&size):NULL;
 int index=-1;
 if(domain&&form->popup_model&&size==form->popup_size&&!memcmp(form->popup_model,domain,size))
  for(unsigned i=0;i<count;i++)if(items[i].identifier==identifier){index=snapshot.indices[i*4+3];break;}
 free(domain);component_outline_free(items,count);popup_snapshot_free(&snapshot);
 if(index>=0)((void (*)(void *,int))(base+0xe1030e4))(form->node,index);
}

#include "forms-webui-menus.inc"
