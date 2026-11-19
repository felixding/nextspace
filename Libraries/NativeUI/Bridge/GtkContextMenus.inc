/* GTK3 menu model/action adapter. NSMenu owns all presentation and tracking.
 * Include after Transport.inc/Menu.inc; the embedding supplies the existing
 * lifetime/notification setup through NXS_GTK_CONTEXT_PREPARE. */
struct GtkContextList {void *data;struct GtkContextList *next,*previous;};
struct GtkContextAction {void *widget,*group,*target,*action,*submenu;char *name;uint64_t parent;};
struct GtkContextSource {struct GtkContextSource *next;void *widget,*model;};
static struct GtkContextSource *gtk_context_sources;
struct GtkContextMenu {
  struct GtkContextMenu *next;void *widget,*model;uint64_t control,selected,generation;
  NXSMenuItem *items;struct GtkContextAction *actions;unsigned count,preparing;int closing,close_deferred;
};
static struct GtkContextMenu *gtk_context_menus;
static int gtk_context_owns_keys(void)
{
  for(struct GtkContextMenu *m=gtk_context_menus;m;m=m->next)
    if(!m->closing&&m->generation==native_callback_generation)return 1;
  return 0;
}
static uint64_t gtk_context_next;
static unsigned gtk_context_watch;
static int gtk_context_watch_fd=-1;
static uint64_t gtk_context_watch_generation;
#define GTK_CONTEXT_FUNCTION(result,name,args) static result (*nxs_##name)args
GTK_CONTEXT_FUNCTION(void *,gtk_widget_get_toplevel,(void *));
GTK_CONTEXT_FUNCTION(void *,gtk_widget_get_window,(void *));
GTK_CONTEXT_FUNCTION(void,gtk_widget_realize,(void *));
GTK_CONTEXT_FUNCTION(void,gtk_widget_set_mapped,(void *,int));
GTK_CONTEXT_FUNCTION(int,gtk_widget_get_mapped,(void *));
GTK_CONTEXT_FUNCTION(void,gtk_widget_unmap,(void *));
GTK_CONTEXT_FUNCTION(void *,gdk_event_copy,(const void *));
GTK_CONTEXT_FUNCTION(void,gdk_event_free,(void *));
GTK_CONTEXT_FUNCTION(void *,gdk_window_get_toplevel,(void *));
GTK_CONTEXT_FUNCTION(void *,gdk_window_get_parent,(void *));
GTK_CONTEXT_FUNCTION(void,gdk_window_coords_to_parent,(void *,double,double,double *,double *));
GTK_CONTEXT_FUNCTION(struct GtkContextList *,gtk_container_get_children,(void *));
GTK_CONTEXT_FUNCTION(void *,gtk_menu_item_get_submenu,(void *));
GTK_CONTEXT_FUNCTION(const char *,gtk_menu_item_get_label,(void *));
GTK_CONTEXT_FUNCTION(void *,gtk_bin_get_child,(void *));
GTK_CONTEXT_FUNCTION(const char *,gtk_label_get_text,(void *));
GTK_CONTEXT_FUNCTION(int,gtk_widget_get_sensitive,(void *));
GTK_CONTEXT_FUNCTION(int,gtk_widget_get_visible,(void *));
GTK_CONTEXT_FUNCTION(int,gtk_check_menu_item_get_active,(void *));
GTK_CONTEXT_FUNCTION(void,gtk_menu_item_activate,(void *));
GTK_CONTEXT_FUNCTION(void *,gtk_widget_get_action_group,(void *,const char *));
GTK_CONTEXT_FUNCTION(int,g_menu_model_get_n_items,(void *));
GTK_CONTEXT_FUNCTION(void *,g_menu_model_get_item_link,(void *,int,const char *));
GTK_CONTEXT_FUNCTION(void *,g_menu_model_get_item_attribute_value,(void *,int,const char *,const void *));
GTK_CONTEXT_FUNCTION(const char *,g_variant_get_string,(void *,size_t *));
GTK_CONTEXT_FUNCTION(const char *,g_variant_get_type_string,(void *));
GTK_CONTEXT_FUNCTION(int,g_variant_get_boolean,(void *));
GTK_CONTEXT_FUNCTION(void,g_variant_unref,(void *));
GTK_CONTEXT_FUNCTION(int,g_action_group_has_action,(void *,const char *));
GTK_CONTEXT_FUNCTION(int,g_action_group_get_action_enabled,(void *,const char *));
GTK_CONTEXT_FUNCTION(void *,g_action_group_get_action_state,(void *,const char *));
GTK_CONTEXT_FUNCTION(void,g_action_group_activate_action,(void *,const char *,void *));
GTK_CONTEXT_FUNCTION(void *,g_action_map_lookup_action,(void *,const char *));
GTK_CONTEXT_FUNCTION(uintptr_t,g_action_map_get_type,(void));
GTK_CONTEXT_FUNCTION(int,g_action_get_enabled,(void *));
GTK_CONTEXT_FUNCTION(void *,g_action_get_state,(void *));
GTK_CONTEXT_FUNCTION(void,g_action_activate,(void *,void *));
GTK_CONTEXT_FUNCTION(void,g_action_change_state,(void *,void *));
GTK_CONTEXT_FUNCTION(void,g_action_group_change_action_state,(void *,const char *,void *));
GTK_CONTEXT_FUNCTION(void *,g_variant_new_boolean,(int));
GTK_CONTEXT_FUNCTION(void *,g_variant_ref_sink,(void *));
GTK_CONTEXT_FUNCTION(void *,g_object_get_data,(void *,const char *));
GTK_CONTEXT_FUNCTION(unsigned long,g_signal_connect_data,(void *,const char *,void *,void *,void *,int));
GTK_CONTEXT_FUNCTION(void,g_signal_handler_disconnect,(void *,unsigned long));
GTK_CONTEXT_FUNCTION(void,g_object_weak_ref,(void *,void (*)(void *,void *),void *));
GTK_CONTEXT_FUNCTION(uintptr_t,gtk_separator_menu_item_get_type,(void));
GTK_CONTEXT_FUNCTION(uintptr_t,gtk_check_menu_item_get_type,(void));
GTK_CONTEXT_FUNCTION(uintptr_t,gtk_label_get_type,(void));
GTK_CONTEXT_FUNCTION(int,g_type_check_instance_is_a,(void *,uintptr_t));
GTK_CONTEXT_FUNCTION(void *,g_object_ref,(void *));
GTK_CONTEXT_FUNCTION(void,g_object_unref,(void *));
GTK_CONTEXT_FUNCTION(void,g_list_free,(void *));
GTK_CONTEXT_FUNCTION(void,g_signal_emit_by_name,(void *,const char *,...));
GTK_CONTEXT_FUNCTION(unsigned,g_idle_add,(int (*)(void *),void *));
GTK_CONTEXT_FUNCTION(unsigned,g_unix_fd_add,(int,unsigned,int (*)(int,unsigned,void *),void *));
GTK_CONTEXT_FUNCTION(int,g_source_remove,(unsigned));
GTK_CONTEXT_FUNCTION(int,g_main_context_iteration,(void *,int));
GTK_CONTEXT_FUNCTION(int64_t,g_get_monotonic_time,(void));
GTK_CONTEXT_FUNCTION(void,g_usleep,(unsigned long));
#undef GTK_CONTEXT_FUNCTION
static int gtk_context_load(void)
{
  if(nxs_g_idle_add)return 1;
#define GTK_CONTEXT_LOAD(name) do {nxs_##name=dlsym(RTLD_NEXT,#name);if(!nxs_##name){note("GTK context missing " #name);return 0;}} while(0)
  GTK_CONTEXT_LOAD(gtk_widget_get_toplevel);GTK_CONTEXT_LOAD(gtk_widget_get_window);
  GTK_CONTEXT_LOAD(gtk_widget_realize);GTK_CONTEXT_LOAD(gtk_widget_set_mapped);
  GTK_CONTEXT_LOAD(gtk_widget_get_mapped);GTK_CONTEXT_LOAD(gtk_widget_unmap);
  GTK_CONTEXT_LOAD(gdk_event_copy);GTK_CONTEXT_LOAD(gdk_event_free);
  GTK_CONTEXT_LOAD(gdk_window_get_toplevel);GTK_CONTEXT_LOAD(gdk_window_get_parent);GTK_CONTEXT_LOAD(gdk_window_coords_to_parent);
  GTK_CONTEXT_LOAD(gtk_container_get_children);GTK_CONTEXT_LOAD(gtk_menu_item_get_submenu);
  GTK_CONTEXT_LOAD(gtk_menu_item_get_label);GTK_CONTEXT_LOAD(gtk_bin_get_child);GTK_CONTEXT_LOAD(gtk_label_get_text);
  GTK_CONTEXT_LOAD(gtk_widget_get_sensitive);GTK_CONTEXT_LOAD(gtk_widget_get_visible);
  GTK_CONTEXT_LOAD(gtk_check_menu_item_get_active);GTK_CONTEXT_LOAD(gtk_menu_item_activate);
  GTK_CONTEXT_LOAD(gtk_widget_get_action_group);GTK_CONTEXT_LOAD(g_menu_model_get_n_items);
  GTK_CONTEXT_LOAD(g_menu_model_get_item_link);GTK_CONTEXT_LOAD(g_menu_model_get_item_attribute_value);
  GTK_CONTEXT_LOAD(g_variant_get_string);GTK_CONTEXT_LOAD(g_variant_get_type_string);GTK_CONTEXT_LOAD(g_variant_get_boolean);GTK_CONTEXT_LOAD(g_variant_unref);
  GTK_CONTEXT_LOAD(g_action_group_has_action);GTK_CONTEXT_LOAD(g_action_group_get_action_enabled);
  GTK_CONTEXT_LOAD(g_action_group_get_action_state);GTK_CONTEXT_LOAD(g_action_group_activate_action);GTK_CONTEXT_LOAD(g_object_weak_ref);
  GTK_CONTEXT_LOAD(g_action_map_lookup_action);GTK_CONTEXT_LOAD(g_action_map_get_type);GTK_CONTEXT_LOAD(g_action_get_enabled);GTK_CONTEXT_LOAD(g_action_get_state);
  GTK_CONTEXT_LOAD(g_action_activate);GTK_CONTEXT_LOAD(g_action_change_state);GTK_CONTEXT_LOAD(g_action_group_change_action_state);GTK_CONTEXT_LOAD(g_variant_new_boolean);GTK_CONTEXT_LOAD(g_variant_ref_sink);
  GTK_CONTEXT_LOAD(g_object_get_data);GTK_CONTEXT_LOAD(g_signal_connect_data);GTK_CONTEXT_LOAD(g_signal_handler_disconnect);
  GTK_CONTEXT_LOAD(gtk_separator_menu_item_get_type);GTK_CONTEXT_LOAD(gtk_check_menu_item_get_type);GTK_CONTEXT_LOAD(gtk_label_get_type);
  GTK_CONTEXT_LOAD(g_type_check_instance_is_a);GTK_CONTEXT_LOAD(g_object_ref);GTK_CONTEXT_LOAD(g_object_unref);
  GTK_CONTEXT_LOAD(g_list_free);GTK_CONTEXT_LOAD(g_signal_emit_by_name);GTK_CONTEXT_LOAD(g_unix_fd_add);GTK_CONTEXT_LOAD(g_source_remove);
  GTK_CONTEXT_LOAD(g_idle_add);
  GTK_CONTEXT_LOAD(g_main_context_iteration);GTK_CONTEXT_LOAD(g_get_monotonic_time);GTK_CONTEXT_LOAD(g_usleep);
#undef GTK_CONTEXT_LOAD
  return 1;
}
static struct GtkContextMenu *gtk_context_find(uint64_t control,void *widget)
{
  for(struct GtkContextMenu *m=gtk_context_menus;m;m=m->next)
    if((control&&m->control==control)||(widget&&m->widget==widget))return m;
  return NULL;
}
static void gtk_context_action_free(NXSMenuItem *item,struct GtkContextAction *a)
{
  free((void *)item->title);free(a->name);
  if(a->widget)nxs_g_object_unref(a->widget);
  if(a->group)nxs_g_object_unref(a->group);
  if(a->target)nxs_g_variant_unref(a->target);
  if(a->action)nxs_g_object_unref(a->action);
  if(a->submenu)nxs_g_object_unref(a->submenu);
  memset(item,0,sizeof(*item));memset(a,0,sizeof(*a));
}
static void gtk_context_free(struct GtkContextMenu *m)
{
  for(unsigned i=0;i<m->count;i++)gtk_context_action_free(&m->items[i],&m->actions[i]);
  free(m->items);free(m->actions);if(m->model)nxs_g_object_unref(m->model);nxs_g_object_unref(m->widget);free(m);
}
static void gtk_context_source_free(void *data,void *widget)
{
  struct GtkContextSource *source=data,**link=&gtk_context_sources;
  while(*link&&*link!=source)link=&(*link)->next;
  if(*link)*link=source->next;
  nxs_g_object_unref(source->model);free(source);
}
void *gtk_menu_new_from_model(void *model)
{
  static void *(*original)(void *);
  if(!original)original=dlsym(RTLD_NEXT,"gtk_menu_new_from_model");
  void *widget=original?original(model):NULL;
  if(widget&&model&&gtk_context_load()) {
    struct GtkContextSource *source=calloc(1,sizeof(*source));
    if(source) {
      source->widget=widget;source->model=nxs_g_object_ref(model);source->next=gtk_context_sources;gtk_context_sources=source;
      nxs_g_object_weak_ref(widget,gtk_context_source_free,source);
    }
  }
  return widget;
}
static int gtk_context_append(struct GtkContextMenu *m,int parent,unsigned flags,const char *title,struct GtkContextAction action)
{
  if(m->count>=4096)return 0;
  char *copy=strdup(title?title:"");if(!copy)return 0;
  NXSMenuItem *items=realloc(m->items,(m->count+1)*sizeof(*items));
  if(!items){free(copy);return 0;}m->items=items;
  struct GtkContextAction *actions=realloc(m->actions,(m->count+1)*sizeof(*actions));
  if(!actions){free(copy);return 0;}m->actions=actions;
  unsigned at=m->count++;
  m->items[at]=(NXSMenuItem){.size=sizeof(NXSMenuItem),.parent=parent,.command=flags&NXS_MENU_SEPARATOR?0:at+1,.title=copy,.flags=flags};
  action.parent=parent<0?0:m->items[parent].command;
  m->actions[at]=action;return 1;
}
static char *gtk_context_attribute(void *model,int index,const char *attribute)
{
  void *value=nxs_g_menu_model_get_item_attribute_value(model,index,attribute,NULL);if(!value)return NULL;
  const char *type=nxs_g_variant_get_type_string(value);
  char *copy=!strcmp(type,"s")?strdup(nxs_g_variant_get_string(value,NULL)):NULL;
  nxs_g_variant_unref(value);return copy;
}
static int gtk_context_project_model(struct GtkContextMenu *m,void *model,int parent,unsigned depth)
{
  if(depth>16)return 0;
  int count=nxs_g_menu_model_get_n_items(model);
  for(int i=0;i<count;i++) {
    void *section=nxs_g_menu_model_get_item_link(model,i,"section");
    if(section) {
      int nonempty=nxs_g_menu_model_get_n_items(section)>0,okay=1;
      if(nonempty&&m->count&&m->items[m->count-1].parent==parent&&!(m->items[m->count-1].flags&NXS_MENU_SEPARATOR))okay=gtk_context_append(m,parent,NXS_MENU_SEPARATOR,"",(struct GtkContextAction){0});
      if(okay&&nonempty)okay=gtk_context_project_model(m,section,parent,depth+1);
      nxs_g_object_unref(section);if(!okay)return 0;continue;
    }
    void *sub=nxs_g_menu_model_get_item_link(model,i,"submenu");
    char *label=gtk_context_attribute(model,i,"label"),*qualified=gtk_context_attribute(model,i,sub?"submenu-action":"action");
    struct GtkContextAction action={0};unsigned flags=sub?NXS_MENU_SUBMENU:0;
    if(qualified) {
      char *dot=strchr(qualified,'.');
      if(dot){*dot=0;void *group=nxs_gtk_widget_get_action_group(m->widget,qualified);if(group){action.group=nxs_g_object_ref(group);action.name=strdup(dot+1);if(nxs_g_type_check_instance_is_a(group,nxs_g_action_map_get_type())){void *a=nxs_g_action_map_lookup_action(group,dot+1);if(a)action.action=nxs_g_object_ref(a);}}}
      action.target=nxs_g_menu_model_get_item_attribute_value(model,i,"target",NULL);
    }
    if(!sub) {
      if(!(action.action?nxs_g_action_get_enabled(action.action):action.group&&action.name&&nxs_g_action_group_has_action(action.group,action.name)&&nxs_g_action_group_get_action_enabled(action.group,action.name)))flags|=NXS_MENU_DISABLED;
      if(action.action||(action.group&&action.name)) {
        void *state=action.action?nxs_g_action_get_state(action.action):nxs_g_action_group_get_action_state(action.group,action.name);
        if(state){if(!strcmp(nxs_g_variant_get_type_string(state),"b")&&nxs_g_variant_get_boolean(state))flags|=NXS_MENU_CHECKED;nxs_g_variant_unref(state);}
      }
    }
    if(sub)action.submenu=nxs_g_object_ref(sub);
    unsigned at=m->count;int okay=gtk_context_append(m,parent,flags,label,action);
    free(label);free(qualified);
    if(!okay){NXSMenuItem unused={0};gtk_context_action_free(&unused,&action);}
    if(okay&&sub)okay=gtk_context_project_model(m,sub,at,depth+1);
    if(sub)nxs_g_object_unref(sub);
    if(!okay)return 0;
  }
  return 1;
}
static int gtk_context_project(struct GtkContextMenu *m,void *shell,int parent,unsigned depth)
{
  if(depth>16)return 0;
  struct GtkContextList *children=nxs_gtk_container_get_children(shell);int okay=1;
  for(struct GtkContextList *p=children;p&&okay;p=p->next) {
    void *widget=p->data;if(!nxs_gtk_widget_get_visible(widget))continue;
    if(m->count>=4096){okay=0;break;}
    unsigned flags=0;const char *title="";void *sub=NULL;
    if(nxs_g_type_check_instance_is_a(widget,nxs_gtk_separator_menu_item_get_type()))flags=NXS_MENU_SEPARATOR;
    else {
      title=nxs_gtk_menu_item_get_label(widget);void *label=nxs_gtk_bin_get_child(widget);
      if(label&&nxs_g_type_check_instance_is_a(label,nxs_gtk_label_get_type()))title=nxs_gtk_label_get_text(label);
      sub=nxs_gtk_menu_item_get_submenu(widget);
      if(sub)flags|=NXS_MENU_SUBMENU;
      if(!nxs_gtk_widget_get_sensitive(widget))flags|=NXS_MENU_DISABLED;
      if(nxs_g_type_check_instance_is_a(widget,nxs_gtk_check_menu_item_get_type())&&nxs_gtk_check_menu_item_get_active(widget))flags|=NXS_MENU_CHECKED;
    }
    unsigned at=m->count;
    struct GtkContextAction action={.widget=nxs_g_object_ref(widget)};
    okay=gtk_context_append(m,parent,flags,title,action);
    if(!okay){nxs_g_object_unref(action.widget);break;}
    if(sub)okay=gtk_context_project(m,sub,at,depth+1);
  }
  nxs_g_list_free(children);return okay;
}
static void *gtk_context_model_identity(void *model)
{
  void *key=nxs_g_object_get_data(model,"nextspace-native-menu-source");return key?key:model;
}
static void *gtk_context_branch_model(void *model,void *identity,unsigned depth)
{
  if(depth>16)return NULL;
  if(gtk_context_model_identity(model)==identity)return nxs_g_object_ref(model);
  int count=nxs_g_menu_model_get_n_items(model);
  for(int i=0;i<count;i++)for(unsigned k=0;k<2;k++) {
    void *child=nxs_g_menu_model_get_item_link(model,i,k?"submenu":"section");
    if(!child)continue;
    void *found=gtk_context_branch_model(child,identity,depth+1);nxs_g_object_unref(child);
    if(found)return found;
  }
  return NULL;
}
static int gtk_context_labels_ready(void *,unsigned);
static int gtk_context_prepare_branch(struct GtkContextMenu *m,unsigned index,unsigned phase)
{
  struct GtkContextAction *a=&m->actions[index];
  if(!a->submenu)return 0;
  void *identity=gtk_context_model_identity(a->submenu);
  /* Keep the original action alive while its own callback rebuilds the model.
   * Neither action names nor source commands are reconstructed here. */
  if(a->action||(a->group&&a->name)) {
    void *state=nxs_g_variant_ref_sink(nxs_g_variant_new_boolean(phase==2));
    if(a->action){void *action=nxs_g_object_ref(a->action);nxs_g_action_change_state(action,state);nxs_g_object_unref(action);}
    else nxs_g_action_group_change_action_state(a->group,a->name,state);
    nxs_g_variant_unref(state);
  }
  if(phase==3)return 1;
  if(m->closing)return 0;
  uint64_t branch=m->items[index].command;
  void *model=NULL;int64_t deadline=nxs_g_get_monotonic_time()+1000000;
  for(;;) {
    if(m->closing)return 0;
    model=gtk_context_branch_model(m->model,identity,0);
    if(model&&gtk_context_labels_ready(model,0))break;
    if(model)nxs_g_object_unref(model);
    if(nxs_g_get_monotonic_time()>=deadline){note("GTK submenu source labels not ready");native_menu_request(m->control,30,0);return 0;}
    /* Reuse the application's GTK event loop for its asynchronous model
     * preparation. Source close/destruction defers this registry's cleanup
     * until this callback unwinds; no control or localization is reproduced. */
    nxs_g_main_context_iteration(NULL,0);nxs_g_usleep(1000);
  }
  struct GtkContextMenu prepared={.widget=m->widget};
  int okay=gtk_context_project_model(&prepared,model,-1,0);nxs_g_object_unref(model);
  /* Retire only this hidden branch's action references. Reuse its slots so
   * repeated submenu opening does not accumulate models or command objects. */
  unsigned char obsolete[4096]={0};
  for(unsigned pass=0;pass<17;pass++)for(unsigned i=0;i<m->count;i++) {
    uint64_t parent=m->actions[i].parent;
    if(m->items[i].size&&(parent==branch||(parent&&parent<=m->count&&obsolete[parent-1])))obsolete[i]=1;
  }
  if(okay)for(unsigned i=0;i<m->count;i++)if(obsolete[i])gtk_context_action_free(&m->items[i],&m->actions[i]);
  unsigned moved=0;
  for(unsigned i=0;okay&&i<prepared.count;i++) {
    unsigned slot=0;while(slot<m->count&&m->items[slot].size)slot++;
    if(slot==m->count) {
      if(m->count>=4096){okay=0;break;}
      NXSMenuItem *items=realloc(m->items,(m->count+1)*sizeof(*items));if(!items){okay=0;break;}m->items=items;
      struct GtkContextAction *actions=realloc(m->actions,(m->count+1)*sizeof(*actions));if(!actions){okay=0;break;}m->actions=actions;m->count++;
    }
    NXSMenuItem item=prepared.items[i];struct GtkContextAction action=prepared.actions[i];
    item.command=item.flags&NXS_MENU_SEPARATOR?0:slot+1;
    action.parent=item.parent<0?branch:prepared.items[item.parent].command;
    m->items[slot]=item;m->actions[slot]=action;
    prepared.items[i].command=item.command;
    /* Ownership moves to the live command registry; the temporary wire model
     * borrows its title until the synchronous branch replacement returns. */
    memset(&prepared.actions[i],0,sizeof(prepared.actions[i]));
    moved++;
  }
  if(okay)okay=native_context_menu_branch(m->control,branch,prepared.items,prepared.count);
  if(!okay)native_menu_request(m->control,30,0);
  for(unsigned i=moved;i<prepared.count;i++)gtk_context_action_free(&prepared.items[i],&prepared.actions[i]);
  free(prepared.items);free(prepared.actions);return okay;
}
static int gtk_context_closed_idle(void *data)
{
  struct GtkContextMenu *m=data,**link=&gtk_context_menus;
  if(m->preparing){m->close_deferred=1;return 0;}
  while(*link&&*link!=m)link=&(*link)->next;
  if(*link)*link=m->next;
  native_menu_request(m->control,29,0);
  /* Execute the original GTK action only after native tracking ends. Firefox
   * still owns password actions, checked state and DOM command dispatch. */
  if(m->selected&&m->selected<=m->count) {
    struct GtkContextAction *a=&m->actions[m->selected-1];
    if(a->action)nxs_g_action_activate(a->action,a->target);
    else if(a->group&&a->name)nxs_g_action_group_activate_action(a->group,a->name,a->target);
    else if(a->widget)nxs_gtk_menu_item_activate(a->widget);
  }
  nxs_g_signal_emit_by_name(m->widget,"selection-done");
  if(nxs_gtk_widget_get_mapped(m->widget))nxs_gtk_widget_unmap(m->widget);
  gtk_context_free(m);return 0;
}
static int gtk_context_command(const struct NXSNativeMenuCommand *request)
{
  if(log_fd>=0)dprintf(log_fd,"%d GTK context command control=%llu command=%llu phase=%u identity=%u received=%u\n",getpid(),(unsigned long long)request->control,(unsigned long long)request->command,request->phase,identity(),request->process);
  if(request->process!=identity())return 0;
  struct GtkContextMenu *m=gtk_context_find(request->control,NULL);if(!m||m->closing)return 0;
  if(!request->command) {
    if(request->phase!=NXS_COMMAND_EXECUTE)return 0;
    m->closing=1;return nxs_g_idle_add(gtk_context_closed_idle,m)!=0;
  }
  if(request->command>m->count||!m->items[request->command-1].size)return 0;
  unsigned index=request->command-1;
  if(request->phase>1) {
    m->preparing++;int accepted=gtk_context_prepare_branch(m,index,request->phase);m->preparing--;
    if(!m->preparing&&m->close_deferred){m->close_deferred=0;nxs_g_idle_add(gtk_context_closed_idle,m);}
    return accepted;
  }
  struct GtkContextAction *a=&m->actions[index];
  int enabled=!(m->items[index].flags&(NXS_MENU_SEPARATOR|NXS_MENU_SUBMENU|NXS_MENU_DISABLED))&&
    (a->action?nxs_g_action_get_enabled(a->action):a->group&&a->name?nxs_g_action_group_has_action(a->group,a->name)&&nxs_g_action_group_get_action_enabled(a->group,a->name):a->widget&&nxs_gtk_widget_get_sensitive(a->widget));
  if(enabled&&request->phase==NXS_COMMAND_EXECUTE)m->selected=request->command;
  return enabled;
}
static int gtk_context_callback_ready(int fd,unsigned condition,void *generation)
{
  int current=fd==native_edit_channel&&(uint64_t)(uintptr_t)generation==native_callback_generation;
  if(!current||condition&~1u) {
    if(fd==gtk_context_watch_fd&&(uint64_t)(uintptr_t)generation==gtk_context_watch_generation)gtk_context_watch=0;
    if(current)native_callbacks_dispatch();
    for(struct GtkContextMenu *m=gtk_context_menus;m;m=m->next)
      if(!m->closing&&m->generation!=native_callback_generation) {
        m->closing=1;m->selected=0;nxs_g_idle_add(gtk_context_closed_idle,m);
      }
    return 0;
  }
  native_callbacks_dispatch();return 1;
}
static int gtk_context_watch_owner(void)
{
  if(gtk_context_watch&&gtk_context_watch_fd==native_edit_channel&&gtk_context_watch_generation==native_callback_generation)return 1;
  if(gtk_context_watch)nxs_g_source_remove(gtk_context_watch);
  gtk_context_watch_fd=native_edit_channel;gtk_context_watch_generation=native_callback_generation;
  gtk_context_watch=nxs_g_unix_fd_add(native_edit_channel,1,gtk_context_callback_ready,(void *)(uintptr_t)native_callback_generation);
  return gtk_context_watch!=0;
}
static void gtk_context_present(void *widget,void *window,const void *rectangle,int rect_anchor,int menu_anchor,const void *event)
{
  static void (*original)(void *,void *,const void *,int,int,const void *);
  if(!original)original=dlsym(RTLD_NEXT,"gtk_menu_popup_at_rect");
  const int *rect=rectangle;
  struct GtkContextMenu *m=NULL;NXSGtk3SurfaceGeometry geometry={0};
  int loaded=gtk_context_load();
  void *top=loaded&&window?nxs_gdk_window_get_toplevel(window):NULL;
  double anchor_x=rect?rect[0]:0,anchor_y=rect?rect[1]:0;void *local=window;
  for(unsigned depth=0;loaded&&local&&top&&local!=top&&depth<128;depth++) {
    nxs_gdk_window_coords_to_parent(local,anchor_x,anchor_y,&anchor_x,&anchor_y);
    local=nxs_gdk_window_get_parent(local);
  }
  int located=loaded&&top&&local==top&&gtk_surface_geometry&&gtk_surface_geometry(top,&geometry,NULL);
  int ready=located&&geometry.mapped&&NXS_GTK_CONTEXT_PREPARE(gtk_context_command);
  int okay=rectangle&&ready&&gtk_context_watch_owner();
  if(log_fd>=0)dprintf(log_fd,"%d GTK context setup loaded=%d geometry=%d mapped=%u ready=%d watch=%d\n",getpid(),loaded,located,geometry.mapped,ready,okay);
  if(okay) {
    m=calloc(1,sizeof(*m));okay=m!=NULL;
    if(m){
      m->widget=nxs_g_object_ref(widget);m->control=(1ull<<40)|++gtk_context_next;m->generation=native_callback_generation;nxs_gtk_widget_realize(widget);
      struct GtkContextSource *source=gtk_context_sources;while(source&&source->widget!=widget)source=source->next;
      if(source)m->model=nxs_g_object_ref(source->model);
      okay=source?gtk_context_project_model(m,source->model,-1,0):gtk_context_project(m,widget,-1,0);
    }
  }
  if(okay)okay=m->model?native_context_menu_live_model(m->control,native_context_menu_title(),m->items,m->count):native_context_menu_model(m->control,native_context_menu_title(),m->items,m->count);
  if(log_fd>=0)dprintf(log_fd,"%d GTK context model count=%u accepted=%d\n",getpid(),m?m->count:0,okay);
  if(okay) {
    m->next=gtk_context_menus;gtk_context_menus=m;
    /* The source toolkit remains the model/lifecycle owner. Its original
     * unmap signal closes that model; only the native NSMenu is displayed. */
    nxs_gtk_widget_set_mapped(widget,1);
    okay=native_menu_popup_request(m->control,geometry.x+anchor_x,geometry.y+anchor_y);
    if(okay){note("shared native GTK context menu presented");return;}
    gtk_context_menus=m->next;native_menu_request(m->control,29,0);nxs_gtk_widget_set_mapped(widget,0);
  }
  if(m)gtk_context_free(m);
  note("GTK context menu binding unavailable; original retained");
  if(original)original(widget,window,rectangle,rect_anchor,menu_anchor,event);
}
struct GtkContextOpen {
  struct GtkContextOpen *next;void *widget,*window,*event;int rect[4],rect_anchor,menu_anchor,cancelled;
  void *model;unsigned idle;unsigned long changed;
};
static struct GtkContextOpen *gtk_context_opening;
static int gtk_context_labels_ready(void *model,unsigned depth)
{
  if(depth>16)return 0;
  int count=nxs_g_menu_model_get_n_items(model);
  for(int i=0;i<count;i++) {
    void *section=nxs_g_menu_model_get_item_link(model,i,"section");
    if(section){int ready=gtk_context_labels_ready(section,depth+1);nxs_g_object_unref(section);if(!ready)return 0;continue;}
    char *label=gtk_context_attribute(model,i,"label");int ready=label&&*label;free(label);
    if(!ready)return 0;
    void *sub=nxs_g_menu_model_get_item_link(model,i,"submenu");
    if(sub){ready=gtk_context_labels_ready(sub,depth+1);nxs_g_object_unref(sub);if(!ready)return 0;}
  }
  return 1;
}
static int gtk_context_present_idle(void *);
static void gtk_context_open_changed(void *model,int position,int removed,int added,void *data)
{
  struct GtkContextOpen *r=data;
  if(!r->idle)r->idle=nxs_g_idle_add(gtk_context_present_idle,r);
}
static int gtk_context_present_idle(void *data)
{
  struct GtkContextOpen *r=data,**link=&gtk_context_opening;
  r->idle=0;
  /* Original applications can translate their menu labels asynchronously.
   * Observe the live GMenuModel instead of displaying a preliminary blank
   * snapshot or copying their localization implementation. */
  if(!r->cancelled&&r->model&&!gtk_context_labels_ready(r->model,0))return 0;
  while(*link&&*link!=r)link=&(*link)->next;
  if(*link)*link=r->next;
  if(r->changed)nxs_g_signal_handler_disconnect(r->model,r->changed);
  if(!r->cancelled)gtk_context_present(r->widget,r->window,r->rect,r->rect_anchor,r->menu_anchor,r->event);
  else {
    nxs_gtk_widget_realize(r->widget);nxs_gtk_widget_set_mapped(r->widget,1);nxs_gtk_widget_unmap(r->widget);
  }
  if(r->event)nxs_gdk_event_free(r->event);
  if(r->model)nxs_g_object_unref(r->model);
  nxs_g_object_unref(r->widget);nxs_g_object_unref(r->window);free(r);return 0;
}
void gtk_menu_popup_at_rect(void *widget,void *window,const void *rectangle,int rect_anchor,int menu_anchor,const void *event)
{
  if(!widget||!window||!rectangle||!gtk_context_load()) {
    static void (*original)(void *,void *,const void *,int,int,const void *);
    if(!original)original=dlsym(RTLD_NEXT,"gtk_menu_popup_at_rect");
    if(original)original(widget,window,rectangle,rect_anchor,menu_anchor,event);return;
  }
  struct GtkContextOpen *r=calloc(1,sizeof(*r));
  if(!r){gtk_context_present(widget,window,rectangle,rect_anchor,menu_anchor,event);return;}
  r->widget=nxs_g_object_ref(widget);r->window=nxs_g_object_ref(window);
  r->event=event?nxs_gdk_event_copy(event):NULL;memcpy(r->rect,rectangle,sizeof(r->rect));
  r->rect_anchor=rect_anchor;r->menu_anchor=menu_anchor;
  for(struct GtkContextSource *s=gtk_context_sources;s;s=s->next)if(s->widget==widget) {
    r->model=nxs_g_object_ref(s->model);
    r->changed=nxs_g_signal_connect_data(r->model,"items-changed",gtk_context_open_changed,r,NULL,0);break;
  }
  r->next=gtk_context_opening;gtk_context_opening=r;
  /* Original popupshown handlers may replace GTK model items. Project on the
   * ordinary GTK idle queue after those handlers, rather than retaining the
   * preliminary item objects from inside the popup call. */
  r->idle=nxs_g_idle_add(gtk_context_present_idle,r);if(!r->idle)gtk_context_present_idle(r);
}
void gtk_menu_popdown(void *widget)
{
  for(struct GtkContextOpen *r=gtk_context_opening;r;r=r->next)if(r->widget==widget){r->cancelled=1;if(!r->idle)r->idle=nxs_g_idle_add(gtk_context_present_idle,r);return;}
  struct GtkContextMenu *m=gtk_context_find(0,widget);
  if(m&&!m->closing){native_menu_request(m->control,30,0);return;}
  static void (*original)(void *);if(!original)original=dlsym(RTLD_NEXT,"gtk_menu_popdown");
  if(original)original(widget);
}
