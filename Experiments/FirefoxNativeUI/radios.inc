/* Original Gecko group data/lifetime and DOM transactions only.
 * NativeUI's shared binding and original AppKit matrix own the controls.
 * GPL-2.0-or-later. */
#include "pinned-radio-groups.h"
#include "pinned-radio-pointer.h"
#include "../../Libraries/NativeUI/Bridge/RadioBinding.inc"
struct GeckoRadioSpan {uintptr_t count;void **data;};
_Static_assert(sizeof(struct GeckoRadioSpan)==16,"Original Span returns length then data in x0/x1");
struct GeckoRadioNode {void *node;uint64_t identifier;};
struct GeckoRadioSnapshot {
  void *container,*group,*selected_node;
  struct GeckoRadioNode *nodes;unsigned count;
  NXSRadioItem *items;unsigned visible,columns;
  uint64_t selected,focused;
};
struct GeckoRadioGroup {
  struct GeckoRadioGroup *next;
  void *container,*group;
  struct GeckoRadioNode *nodes;unsigned count;
  struct NXSRadioBinding native;
  int busy;
};
static struct GeckoRadioGroup *gecko_radio_groups;
static void *gecko_radio_name_atom,*gecko_radio_id_atom;
static char *component_attribute(const void *node,const char *name,void **atom)
{
 if(!node||memcmp((void *)(base+NXS_GECKO_RADIO_ATTR),gecko_radio_attr_bytes,sizeof(gecko_radio_attr_bytes))||
    memcmp((void *)(base+NXS_GECKO_RADIO_ATOMIZE),gecko_radio_atomize_bytes,sizeof(gecko_radio_atomize_bytes)))return NULL;
 if(!*atom)*atom=((void *(*)(const char *))(base+NXS_GECKO_RADIO_ATOMIZE))(name);
 if(!*atom)return NULL;
 static const uint16_t empty;struct GeckoString value={.data=&empty,.flags=1};
 ((int (*)(const void *,const void *,void *))(base+NXS_GECKO_RADIO_ATTR))(node,*atom,&value);
 char *text=utf8_text(value.data,value.length);
 ((void (*)(void *))(base+NXS_GECKO_RADIO_STRING_RELEASE))(&value);return text;
}
static int native_component_node(const void *node)
{
 const char *prefix=getenv("NEXTSPACE_FIREFOX_WEBUI_PREFIX");
 if(!frontend_requested||!prefix||!*prefix)return 0;
 static void *atom;char *value=component_attribute(node,"data-nextspace-native-widget",&atom);
 int owned=value&&!strcmp(value,prefix);free(value);return owned;
}
struct ComponentRadioNode {void *node;unsigned order;};
static char *component_radio_key(const void *node,unsigned *order)
{
 const char *prefix=getenv("NEXTSPACE_FIREFOX_WEBUI_PREFIX");if(!prefix||!*prefix)return NULL;
 char *name=component_attribute(node,"name",&gecko_radio_name_atom);
 size_t size=strlen(prefix);char *separator=name?strrchr(name,':'):NULL;
 if(!name||strncmp(name,prefix,size)||!separator){free(name);return NULL;}
 char *end;unsigned long index=strtoul(separator+1,&end,10);
 if(end==separator+1||*end||index>=4096){free(name);return NULL;}
 *separator=0;*order=index;return name;
}
static int component_radio_order(const void *a,const void *b)
{
 unsigned x=((const struct ComponentRadioNode *)a)->order,y=((const struct ComponentRadioNode *)b)->order;
 return (x>y)-(x<y);
}
static void gecko_radio_addref(void *node)
{((unsigned (*)(void *))(base+NXS_GECKO_RADIO_ADDREF))(node);}
static void gecko_radio_release_node(void *node)
{((unsigned (*)(void *))(base+NXS_GECKO_RADIO_RELEASE))(node);}
static void gecko_radio_nodes_free(struct GeckoRadioNode *nodes,unsigned count,int release)
{if(release)for(unsigned i=0;i<count;i++)gecko_radio_release_node(nodes[i].node);free(nodes);}
static void gecko_radio_snapshot_free(struct GeckoRadioSnapshot *s)
{gecko_radio_nodes_free(s->nodes,s->count,1);free(s->items);memset(s,0,sizeof(*s));}
static int component_radio_snapshot(void *anchor,struct GeckoRadioSnapshot *s)
{
 unsigned order;char *key=component_radio_key(anchor,&order);if(!key)return -1;
 struct ComponentRadioNode *members=calloc(4096,sizeof(*members));if(!members){free(key);return 0;}
 unsigned count=0;int valid=1;
 for(struct Widget *w=widgets;w;w=w->next) {
  if(w->kind!=NXS_RADIO)continue;
  unsigned index;char *candidate=component_radio_key(w->node,&index);
  if(candidate&&!strcmp(candidate,key)) {
   if(count==4096)valid=0;
   else members[count++]=(struct ComponentRadioNode){w->node,index};
  }
  free(candidate);if(!valid)break;
 }
 free(key);qsort(members,count,sizeof(*members),component_radio_order);
 s->nodes=calloc(count?count:1,sizeof(*s->nodes));s->items=calloc(count?count:1,sizeof(*s->items));
 if(!count||!s->nodes||!s->items)valid=0;
 if(valid)for(unsigned i=0;i<count;i++) {
  if(i&&members[i].order==members[i-1].order){valid=0;break;}
  void *node=members[i].node;gecko_radio_addref(node);s->nodes[s->count++].node=node;
  if(*((const unsigned char *)node+458)&32)s->selected_node=node;
 }
 if(valid)s->container=s->group=members[0].node;
 free(members);if(!valid){gecko_radio_snapshot_free(s);return 0;}return 1;
}
static void gecko_radio_reset_process(void)
{
  memset(&radio_pointer_source,0,sizeof(radio_pointer_source));
  /* A fork inherits caches, not their parent's remote object ownership.
   * As with Widget's existing reset, do not touch inherited engine objects. */
  while(gecko_radio_groups) {
    struct GeckoRadioGroup *g=gecko_radio_groups;gecko_radio_groups=g->next;
    gecko_radio_nodes_free(g->nodes,g->count,0);
    native_radio_binding_free_items(g->native.items,g->native.count);free(g);
  }
}
static struct GeckoRadioGroup *gecko_radio_group(uint64_t owner)
{for(struct GeckoRadioGroup *g=gecko_radio_groups;g;g=g->next)if(g->native.control==owner)return g;return NULL;}
static void gecko_radio_prune(uint64_t owner)
{
  struct GeckoRadioGroup **cursor=&gecko_radio_groups;
  while(*cursor&&(*cursor)->native.control!=owner)cursor=&(*cursor)->next;
  if(!*cursor||(*cursor)->busy)return;
  for(struct Widget *w=widgets;w;w=w->next)if(w->radio_owner==owner)return;
  struct GeckoRadioGroup *g=*cursor;*cursor=g->next;
  native_radio_binding_destroy(&g->native);gecko_radio_nodes_free(g->nodes,g->count,1);free(g);
}
static void gecko_radio_release(struct Widget *w)
{
  uint64_t owner=w->radio_owner;w->radio_owner=w->radio_member=0;
  if(owner) {
    struct GeckoRadioGroup *g=gecko_radio_group(owner);
    if(g){g->busy++;native_radio_binding_cancel(&g->native);g->busy--;}
    /* Retained display items can move without repaint. A member's frame
     * retirement must invalidate the remaining group models and pixels. */
    for(struct Widget *item=widgets;item;item=item->next)if(item->radio_owner==owner)invalidate_widget(item);
    gecko_radio_prune(owner);
  }
}
static int gecko_radio_snapshot(void *anchor,struct GeckoRadioSnapshot *s)
{
  memset(s,0,sizeof(*s));if(node_kind(anchor)!=NXS_RADIO)return 0;
  int component=component_radio_snapshot(anchor,s);if(component>=0)return component;
  if(!gecko_radio_name_atom)gecko_radio_name_atom=((void *(*)(const char *))(base+NXS_GECKO_RADIO_ATOMIZE))("name");
  if(!gecko_radio_name_atom)return 0;
  /* GetCurrentRadioGroupContainer is inlined in the pinned VisitGroup and
   * RadioSetChecked. The latter's guarded load is HTMLInputElement+464. */
  s->container=*(void **)((char *)anchor+464);
  struct GeckoRadioSpan span={.count=1,.data=&anchor};
  if(s->container) {
    static const uint16_t empty;struct GeckoString name={.data=&empty,.flags=1};
    ((int (*)(const void *,const void *,void *))(base+NXS_GECKO_RADIO_ATTR))(anchor,gecko_radio_name_atom,&name);
    s->group=((void *(*)(void *,const void *))(base+NXS_GECKO_RADIO_GROUP))(s->container,&name);
    span=((struct GeckoRadioSpan (*)(void *,void *))(base+NXS_GECKO_RADIO_MEMBERS))(s->container,s->group);
    s->selected_node=((void *(*)(void *,const void *))(base+NXS_GECKO_RADIO_SELECTED))(s->container,&name);
    ((void (*)(void *))(base+NXS_GECKO_RADIO_STRING_RELEASE))(&name);
  } else {
    s->group=anchor;
    /* The original SetCheckedInternal sets mChecked at +458, mask32. */
    if(*((const unsigned char *)anchor+458)&32)s->selected_node=anchor;
  }
  if(!span.count||span.count>4096||!span.data)return 0;
  s->nodes=calloc(span.count,sizeof(*s->nodes));s->items=calloc(span.count,sizeof(*s->items));
  if(!s->nodes||!s->items){gecko_radio_snapshot_free(s);return 0;}
  for(unsigned i=0;i<span.count;i++) {
    void *node=span.data[i];if(node_kind(node)!=NXS_RADIO){gecko_radio_snapshot_free(s);return 0;}
    gecko_radio_addref(node);s->nodes[s->count++].node=node;
  }
  return 1;
}
static uint64_t gecko_radio_identifier(const struct GeckoRadioGroup *g,void *node)
{for(unsigned i=0;i<g->count;i++)if(g->nodes[i].node==node)return g->nodes[i].identifier;return 0;}
static void *gecko_radio_node(const struct GeckoRadioGroup *g,uint64_t identifier)
{for(unsigned i=0;i<g->count;i++)if(g->nodes[i].identifier==identifier)return g->nodes[i].node;return NULL;}
static void gecko_radio_model(struct GeckoRadioSnapshot *s,const struct GeckoRadioGroup *g)
{
  struct NXSRectD positions[4096];
  void *manager=*(void **)(base+0xa439c38),*focused=manager?*(void **)((char *)manager+128):NULL;
  for(unsigned i=0;i<s->count;i++) {
    void *node=s->nodes[i].node;
    uint64_t identifier=gecko_radio_identifier(g,node);if(!identifier)identifier=++next_widget;
    s->nodes[i].identifier=identifier;
    void *frame=*(void **)((char *)node+96);if(!frame||frame_kind(frame)!=NXS_RADIO||!frame_scale_supported(frame))continue;
    metric_probe=1;int themed=original_intrinsic(frame,NULL,0);metric_probe=0;if(!themed)continue;
    int bounds[4]={0};engine_frame_rect((void *)(base+0x6daae5c),frame,bounds);
    if(bounds[2]<60||bounds[3]<60)continue;
    double x,y;if(!gecko_frame_device_origin(frame,&x,&y))continue;
    positions[s->visible]=(struct NXSRectD){x,y,bounds[2]/frame_units(frame),bounds[3]/frame_units(frame)};
    s->items[s->visible++]=(NXSRadioItem){sizeof(NXSRadioItem),identifier,"",!(*(uint64_t *)((char *)node+112)&16)};
    if(s->selected_node==node)s->selected=identifier;
    if(focused==node)s->focused=identifier;
  }
  s->columns=native_radio_columns(positions,s->visible);
}
static int gecko_radio_same_nodes(const struct GeckoRadioGroup *g,const struct GeckoRadioSnapshot *s)
{
  if(g->container!=s->container||g->group!=s->group||g->count!=s->count)return 0;
  for(unsigned i=0;i<s->count;i++)if(g->nodes[i].node!=s->nodes[i].node)return 0;
  return 1;
}
static void gecko_radio_trace(const struct GeckoRadioGroup *g,const struct GeckoRadioSnapshot *s)
{
  if(log_fd<0)return;
  if(!gecko_radio_id_atom)gecko_radio_id_atom=((void *(*)(const char *))(base+NXS_GECKO_RADIO_ATOMIZE))("id");
  uint64_t selected=gecko_radio_identifier(g,s->selected_node);
  dprintf(log_fd,"{\"event\":\"native-radio-model\",\"pid\":%d,\"control\":%llu,\"root\":%llu,\"total\":%u,\"canonical_selected\":%llu,\"selected\":%llu,\"members\":[",getpid(),(unsigned long long)g->native.control,(unsigned long long)g->nodes[0].identifier,g->count,(unsigned long long)selected,(unsigned long long)s->selected);
  for(unsigned i=0;i<s->visible;i++)dprintf(log_fd,"%s{\"id\":%llu,\"enabled\":%d}",i?",":"",(unsigned long long)s->items[i].identifier,s->items[i].enabled);
  dprintf(log_fd,"],\"nodes\":[");
  for(unsigned i=0;i<g->count;i++) {
    static const uint16_t empty;struct GeckoString id={.data=&empty,.flags=1};
    ((int (*)(const void *,const void *,void *))(base+NXS_GECKO_RADIO_ATTR))(g->nodes[i].node,gecko_radio_id_atom,&id);
    char *text=utf8_text(id.data,id.length);((void (*)(void *))(base+NXS_GECKO_RADIO_STRING_RELEASE))(&id);
    dprintf(log_fd,"%s{\"id\":%llu,\"dom_id_hex\":\"",i?",":"",(unsigned long long)g->nodes[i].identifier);
    if(text)for(unsigned char *p=(unsigned char *)text;*p;p++)dprintf(log_fd,"%02x",*p);
    free(text);dprintf(log_fd,"\"}");
  }
  dprintf(log_fd,"]}\n");
}
static struct GeckoRadioGroup *gecko_radio_sync(struct Widget *w)
{
  struct GeckoRadioGroup *g=gecko_radio_group(w->radio_owner);if(g&&(g->busy||g->native.tracking))return g;
  struct GeckoRadioSnapshot s;if(!gecko_radio_snapshot(w->node,&s))return NULL;
  for(g=gecko_radio_groups;g;g=g->next)if(g->container==s.container&&g->group==s.group)break;
  if(!g) {
    g=calloc(1,sizeof(*g));if(!g){gecko_radio_snapshot_free(&s);return NULL;}
    g->container=s.container;g->group=s.group;g->native.control=++next_widget;g->next=gecko_radio_groups;gecko_radio_groups=g;
  }
  gecko_radio_model(&s,g);
  int changed=!gecko_radio_same_nodes(g,&s)||!native_radio_binding_same(&g->native,s.items,s.visible,s.columns)||g->native.state.selected!=s.selected;
  void *node=w->node;uint64_t id=w->id;gecko_radio_addref(node);g->busy++;
  double scale=frame_scale(w->frame);
  native_control_presentation(NXS_RADIOGROUP,g->native.control,scale);
  int okay=s.visible&&native_radio_binding_sync(&g->native,s.items,s.visible,s.columns,s.selected,s.focused,scale);
  w=widget_for_node(node);okay=okay&&w&&w->id==id&&node_kind(node)==NXS_RADIO;
  if(okay) {
    gecko_radio_nodes_free(g->nodes,g->count,1);g->nodes=s.nodes;g->count=s.count;s.nodes=NULL;s.count=0;
    uint64_t previous=w->radio_owner;w->radio_owner=g->native.control;w->radio_member=gecko_radio_identifier(g,node);
    if(previous&&previous!=w->radio_owner)gecko_radio_prune(previous);
    if(changed) {
      gecko_radio_trace(g,&s);
      for(struct Widget *item=widgets;item;item=item->next)if(item!=w&&item->radio_owner==g->native.control)invalidate_widget(item);
    }
  }
  gecko_radio_release_node(node);gecko_radio_snapshot_free(&s);g->busy--;
  if(!okay){gecko_radio_prune(g->native.control);return NULL;}return g;
}
static struct NXSResponse *gecko_radio_request(struct Widget *w,unsigned operation,double x,double y,unsigned modifiers)
{
  if(operation==6){gecko_radio_release(w);return NULL;}
  struct GeckoRadioGroup *g=(operation==1||!w->radio_owner)?gecko_radio_sync(w):gecko_radio_group(w->radio_owner);if(!g)return NULL;
  return native_radio_binding_request(&g->native,w->radio_member,&w->radio_rect,operation,w->width,w->height,x,y,modifiers,w->radio_clicks);
}
static void gecko_radio_pointer_capture(void *frame)
{
  reset_widget_process();
  if(radio_pointer_source.node)gecko_radio_release_node(radio_pointer_source.node);
  memset(&radio_pointer_source,0,sizeof(radio_pointer_source));
  if(active_widget&&active_widget->kind==NXS_RADIO) {
    struct GeckoRadioGroup *g=gecko_radio_group(active_widget->radio_owner);
    if(g){g->busy++;native_radio_binding_cancel(&g->native);g->busy--;}
    active_widget=NULL;
  }
  struct Widget *w=widget_for_frame(frame);
  if(!w||w->kind!=NXS_RADIO||!w->painted||node_kind(w->node)!=NXS_RADIO)return;
  gecko_radio_addref(w->node);radio_pointer_source.node=w->node;
  radio_pointer_source.control=w->id;radio_pointer_source.context=*(void **)((char *)frame+40);radio_pointer_source.active=1;
}
static void gecko_radio_pointer_release_context(void *context)
{
  if(radio_pointer_source.active&&radio_pointer_source.context==context) {
    if(radio_pointer_source.node)gecko_radio_release_node(radio_pointer_source.node);
    /* Keep a non-owning cancellation marker until mouseup or the next press. */
    radio_pointer_source.node=radio_pointer_source.context=NULL;
  }
}
static void gecko_radio_native_focus(struct GeckoRadioGroup *g,const struct NXSRadioWireState *state)
{
  void *target=gecko_radio_node(g,state->key_cell);
  if(!target||node_kind(target)!=NXS_RADIO||(*(uint64_t *)((char *)target+112)&16))return;
  void *manager=*(void **)(base+0xa439c38);
  if(manager&&*(void **)((char *)manager+128)!=target)
    ((uint32_t (*)(void *,void *,unsigned))(base+NXS_GECKO_RADIO_FOCUS))(manager,target,1u<<13);
}
static void *gecko_radio_action_target(struct GeckoRadioGroup *g,void *origin,uint64_t id,uint64_t selected)
{
  struct Widget *w=widget_for_node(origin);
  if(!w||w->id!=id||w->radio_owner!=g->native.control||node_kind(origin)!=NXS_RADIO||!selected)return NULL;
  struct GeckoRadioSnapshot s;int valid=gecko_radio_snapshot(origin,&s);
  if(valid){gecko_radio_model(&s,g);valid=gecko_radio_same_nodes(g,&s)&&native_radio_binding_same(&g->native,s.items,s.visible,s.columns);}
  void *target=valid?gecko_radio_node(g,selected):NULL;
  gecko_radio_snapshot_free(&s);
  return target&&node_kind(target)==NXS_RADIO&&!(*(uint64_t *)((char *)target+112)&16)?target:NULL;
}
static void *gecko_radio_pointer_target(void *origin,uint64_t id)
{
  struct Widget *w=widget_for_node(origin);
  if(!w||w->id!=id||node_kind(origin)!=NXS_RADIO)return NULL;
  struct GeckoRadioGroup *g=gecko_radio_group(w->radio_owner);
  if(!g||!g->native.pointer_ready||g->native.epoch!=atomic_load(&native_host_epoch))return NULL;
  struct NXSRadioWireState after=g->native.pointer_state;int action=g->native.pointer_pending;
  g->native.pointer_pending=g->native.pointer_ready=0;
  g->busy++;
  if(gecko_radio_action_target(g,origin,id,after.key_cell))gecko_radio_native_focus(g,&after);
  void *target=action?gecko_radio_action_target(g,origin,id,after.selected):NULL;g->busy--;
  if(!target) {
    for(struct Widget *item=widgets;item;item=item->next)if(item->radio_owner==g->native.control)invalidate_widget(item);
    gecko_radio_prune(g->native.control);
  }
  return target;
}
static void gecko_radio_pointer_complete(void *origin,uint64_t id)
{
  struct Widget *w=widget_for_node(origin);if(!w||w->id!=id)return;
  uint64_t owner=w->radio_owner;
  for(struct Widget *item=widgets;item;item=item->next)if(item->radio_owner==owner)invalidate_widget(item);
  gecko_radio_sync(w);gecko_radio_prune(owner);
}
static uint32_t gecko_radio_key(struct Widget *w,void *event,void *visitor)
{
  int *status=(int *)((char *)visitor+24);struct GeckoRadioGroup *g=gecko_radio_sync(w);
  if(!g){*status=1;return 0;}
  struct NXSRadioWireState before=g->native.state,after;
  unsigned message=*(const uint16_t *)((char *)event+18);char *text=key_text(event);
  if(!text){*status=1;return 0;}
  int modifier=text_modifier_event(event);
  NXSKeyEvent input={.size=sizeof(input),.type=modifier?NXS_KEY_MODIFIERS:message==4?NXS_KEY_DOWN:NXS_KEY_UP,
    .key=modifier?NXS_KEY_TEXT:logical_key(*(uint32_t *)((char *)event+200)),
    .modifiers=widget_modifiers(event),.text=modifier?"":text,.unmodified_text=modifier?"":text,.repeat=!!*((uint8_t *)event+223)};
  struct NXSResponse *response=native_radio_input(g->native.control,0,&input);free(text);
  if(!native_radio_response_state(response,&after)){*status=1;return 0;}
  int handled=response->parts[3].x;g->native.state=after;
  if(handled==NXS_INPUT_NEXT||handled==NXS_INPUT_PREVIOUS){if(advance_focus(w->node,handled))*status=1;return 0;}
  if(handled!=NXS_INPUT_UNHANDLED||after.actions!=before.actions||message==3)*status=1;
  void *origin=w->node;uint64_t id=w->id,owner=g->native.control;gecko_radio_addref(origin);g->busy++;
  gecko_radio_native_focus(g,&after);
  void *target=after.actions!=before.actions?gecko_radio_action_target(g,origin,id,after.selected):NULL;
  if(target)((uint32_t (*)(void *,int,void *))(base+0x58ce09c))(target,1,*(void **)visitor);
  g->busy--;
  for(struct Widget *item=widgets;item;item=item->next)if(item->radio_owner==owner)invalidate_widget(item);
  w=widget_for_node(origin);if(w&&w->id==id)gecko_radio_sync(w);
  gecko_radio_release_node(origin);gecko_radio_prune(owner);return 0;
}

static struct Detour radio_pointer_detours[]={
  {NXS_GECKO_RADIO_POINTER_PRE_EVENT_OFFSET,gecko_radio_pointer_pre_event_bytes,radio_pre_event,(void **)&original_radio_pre_event}
};
