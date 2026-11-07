/* Original Gecko group data/lifetime and DOM transactions only.
 * NativeUI's shared binding and original AppKit matrix own the controls.
 * GPL-2.0-or-later. */
#include "pinned-radio-groups.h"
#include "../../Libraries/NativeUI/Bridge/RadioBinding.inc"
struct GeckoRadioSpan {uintptr_t count;void **data;};
_Static_assert(sizeof(struct GeckoRadioSpan)==16,"Original Span returns length then data in x0/x1");
struct GeckoRadioNode {void *node;uint64_t identifier;};
struct GeckoRadioSnapshot {
  void *container,*group,*selected_node;
  struct GeckoRadioNode *nodes;unsigned count;
  NXSRadioItem *items;unsigned visible;
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
static void gecko_radio_addref(void *node)
{((unsigned (*)(void *))(base+NXS_GECKO_RADIO_ADDREF))(node);}
static void gecko_radio_release_node(void *node)
{((unsigned (*)(void *))(base+NXS_GECKO_RADIO_RELEASE))(node);}
static void gecko_radio_nodes_free(struct GeckoRadioNode *nodes,unsigned count,int release)
{if(release)for(unsigned i=0;i<count;i++)gecko_radio_release_node(nodes[i].node);free(nodes);}
static void gecko_radio_snapshot_free(struct GeckoRadioSnapshot *s)
{gecko_radio_nodes_free(s->nodes,s->count,1);free(s->items);memset(s,0,sizeof(*s));}
static void gecko_radio_reset_process(void)
{
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
    /* Retained display items can move without repaint. A member's frame
     * retirement must invalidate the remaining group models and pixels. */
    for(struct Widget *item=widgets;item;item=item->next)if(item->radio_owner==owner)invalidate_widget(item);
    gecko_radio_prune(owner);
  }
}
static int gecko_radio_snapshot(void *anchor,struct GeckoRadioSnapshot *s)
{
  memset(s,0,sizeof(*s));if(node_kind(anchor)!=NXS_RADIO)return 0;
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
  void *manager=*(void **)(base+0xa439c38),*focused=manager?*(void **)((char *)manager+128):NULL;
  for(unsigned i=0;i<s->count;i++) {
    void *node=s->nodes[i].node;
    uint64_t identifier=gecko_radio_identifier(g,node);if(!identifier)identifier=++next_widget;
    s->nodes[i].identifier=identifier;
    void *frame=*(void **)((char *)node+96);if(!frame||frame_kind(frame)!=NXS_RADIO||fabsf(frame_scale(frame)-1)>0.000001f)continue;
    metric_probe=1;int themed=original_intrinsic(frame,NULL,0);metric_probe=0;if(!themed)continue;
    int bounds[4]={0};engine_frame_rect((void *)(base+0x6daae5c),frame,bounds);
    if(bounds[2]<60||bounds[3]<60)continue;
    s->items[s->visible++]=(NXSRadioItem){sizeof(NXSRadioItem),identifier,"",!(*(uint64_t *)((char *)node+112)&16)};
    if(s->selected_node==node)s->selected=identifier;
    if(focused==node)s->focused=identifier;
  }
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
  int changed=!gecko_radio_same_nodes(g,&s)||!native_radio_binding_same(&g->native,s.items,s.visible,1)||g->native.state.selected!=s.selected;
  void *node=w->node;uint64_t id=w->id;gecko_radio_addref(node);g->busy++;
  int okay=s.visible&&native_radio_binding_sync(&g->native,s.items,s.visible,1,s.selected,s.focused,1);
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
  return native_radio_binding_request(&g->native,w->radio_member,&w->radio_rect,operation,w->width,w->height,x,y,modifiers);
}
static int gecko_radio_click_allowed(struct Widget *w)
{
  struct GeckoRadioGroup *g=gecko_radio_group(w->radio_owner);if(!g)return 0;g->native.tracking=0;
  struct GeckoRadioSnapshot s;int okay=gecko_radio_snapshot(w->node,&s);
  if(okay) {
    gecko_radio_model(&s,g);okay=gecko_radio_same_nodes(g,&s)&&native_radio_binding_same(&g->native,s.items,s.visible,1)&&
      native_radio_state(g->native.control,&g->native.state)&&g->native.state.selected==w->radio_member;
  }
  gecko_radio_snapshot_free(&s);return okay;
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
  void *target=gecko_radio_node(g,after.key_cell);
  if(target&&after.key_cell!=g->native.dom_focus&&node_kind(target)==NXS_RADIO&&!(*(uint64_t *)((char *)target+112)&16)) {
    void *manager=*(void **)(base+0xa439c38);
    if(manager)((uint32_t (*)(void *,void *,unsigned))(base+NXS_GECKO_RADIO_FOCUS))(manager,target,1u<<13);
  }
  w=widget_for_node(origin);
  if(w&&w->id==id&&w->radio_owner==owner&&node_kind(origin)==NXS_RADIO&&after.actions!=before.actions&&after.selected) {
    struct GeckoRadioSnapshot s;int valid=gecko_radio_snapshot(origin,&s);
    if(valid){gecko_radio_model(&s,g);valid=gecko_radio_same_nodes(g,&s)&&native_radio_binding_same(&g->native,s.items,s.visible,1);}
    target=valid?gecko_radio_node(g,after.selected):NULL;
    if(target&&node_kind(target)==NXS_RADIO&&!(*(uint64_t *)((char *)target+112)&16))
      ((uint32_t (*)(void *,int,void *))(base+0x58ce09c))(target,1,*(void **)visitor);
    gecko_radio_snapshot_free(&s);
  }
  g->busy--;
  for(struct Widget *item=widgets;item;item=item->next)if(item->radio_owner==owner)invalidate_widget(item);
  w=widget_for_node(origin);if(w&&w->id==id)gecko_radio_sync(w);
  gecko_radio_release_node(origin);gecko_radio_prune(owner);return 0;
}
