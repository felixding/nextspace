/* Original Blink group data and DOM transactions. AppKit owns the controls.
 * GPL-2.0-or-later. */
#include "pinned-radio-groups.h"
#include "../../Libraries/NativeUI/Bridge/RadioBinding.inc"
struct RadioSnapshot {
  NXSRadioItem *items;
  uint32_t root,canonical_selected;
  uint64_t selected,focused;
  unsigned count,total;
};
struct NativeRadioGroup {
  struct NativeRadioGroup *next;
  struct NXSRadioBinding native;
  uint32_t root;
  int busy,tracking;
};
static struct NativeRadioGroup *radio_groups;
static int guard_radio_calls(void)
{
#define CHECK_RADIO(name,bytes) if(memcmp((void *)(base+NXS_##name##_OFFSET),nxs_##bytes##_bytes,20))return 0
  CHECK_RADIO(RADIO_NEXT,radio_next);CHECK_RADIO(RADIO_NAME,radio_name);
  CHECK_RADIO(RADIO_NODE_ID,radio_node_id);CHECK_RADIO(RADIO_NODE_FOR_ID,radio_node_for_id);CHECK_RADIO(RADIO_FOCUS,radio_focus);
#undef CHECK_RADIO
  return 1;
}
static uint32_t radio_node_id(void *node)
{return ((uint32_t (*)(void *))(base+NXS_RADIO_NODE_ID_OFFSET))(node);}
static void *radio_node_for_id(uint64_t identifier)
{return identifier&&identifier<=UINT32_MAX?((void *(*)(uint32_t))(base+NXS_RADIO_NODE_FOR_ID_OFFSET))(identifier):NULL;}
static void *radio_next(void *node,int forward)
{return ((void *(*)(void *,int))(base+NXS_RADIO_NEXT_OFFSET))(node,forward);}
static int radio_snapshot(void *anchor,struct RadioSnapshot *snapshot)
{
  memset(snapshot,0,sizeof(*snapshot));
  if(!anchor||input_form_kind(anchor)!=NXS_RADIO)return 0;
  const void *name=((const void *(*)(void *))(base+NXS_RADIO_NAME_OFFSET))(anchor);
  const void *string=name?*(const void *const *)name:NULL;
  int named=string&&*(const uint32_t *)((const char *)string+4);
  void *first=anchor,*node;unsigned guard=0;
  if(named)while((node=radio_next(first,0))) {if(++guard>4096||node==first)return 0;first=node;}
  snapshot->root=radio_node_id(first);snapshot->items=calloc(4096,sizeof(*snapshot->items));
  if(!snapshot->root||!snapshot->items){free(snapshot->items);return 0;}
  for(node=first;node;node=named?radio_next(node,1):NULL) {
    if(++snapshot->total>4096){free(snapshot->items);snapshot->items=NULL;return 0;}
    uint32_t identifier=radio_node_id(node);if(!identifier){free(snapshot->items);snapshot->items=NULL;return 0;}
    int checked=form_state(node,NXS_RADIO);if(checked)snapshot->canonical_selected=identifier;
    /* The original engine layout decides which members have renderable
     * controls. Hidden checked data stays canonical without fake UI cells. */
    if(!decode_member((char *)node+48))continue;
    struct FloatRect box=((struct FloatRect (*)(const void *))(base+NXS_COORDINATE_CLIENT_BOX_OFFSET))(node);
    if(!isfinite(box.width)||!isfinite(box.height)||box.width<1||box.height<1)continue;
    snapshot->items[snapshot->count++]=(NXSRadioItem){sizeof(NXSRadioItem),identifier,"",form_enabled(node)};
    if(checked)snapshot->selected=identifier;
    if(form_focused(node))snapshot->focused=identifier;
  }
  if(!snapshot->count){free(snapshot->items);snapshot->items=NULL;return 0;}
  return 1;
}
static struct NativeRadioGroup *radio_group(uint32_t root)
{for(struct NativeRadioGroup *g=radio_groups;g;g=g->next)if(g->root==root)return g;return NULL;}
static void radio_prune(uint32_t root)
{
  struct NativeRadioGroup **cursor=&radio_groups;
  while(*cursor&&(*cursor)->root!=root)cursor=&(*cursor)->next;
  if(!*cursor||(*cursor)->busy)return;
  for(struct NativeForm *f=native_forms;f;f=f->next)if(f->radio_owner==root)return;
  struct NativeRadioGroup *g=*cursor;*cursor=g->next;native_radio_binding_destroy(&g->native);free(g);
}
static void radio_release(struct NativeForm *form)
{uint32_t owner=form->radio_owner;form->radio_owner=0;form->radio_member=0;if(owner)radio_prune(owner);}
static struct NativeRadioGroup *radio_sync(struct NativeForm *form)
{
  struct NativeRadioGroup *g=radio_group(form->radio_owner);if(g&&(g->busy||g->tracking))return g;
  struct RadioSnapshot snapshot;if(!radio_snapshot(form->node,&snapshot))return NULL;
  g=radio_group(snapshot.root);
  if(!g) {
    g=calloc(1,sizeof(*g));if(!g){free(snapshot.items);return NULL;}
    g->root=snapshot.root;g->native.control=++next_form_control;g->next=radio_groups;radio_groups=g;
  }
  int changed=!native_radio_binding_same(&g->native,snapshot.items,snapshot.count,1)||g->native.state.selected!=snapshot.selected;
  uint32_t anchor=radio_node_id(form->node);uint64_t control=form->control;
  g->busy++;
  int okay=native_radio_binding_sync(&g->native,snapshot.items,snapshot.count,1,snapshot.selected,snapshot.focused,1);
  void *node=radio_node_for_id(anchor);form=node?find_form(node):NULL;
  okay=okay&&form&&form->control==control&&input_form_kind(node)==NXS_RADIO;
  if(okay) {
    uint32_t previous=form->radio_owner;form->radio_owner=g->root;form->radio_member=radio_node_id(form->node);
    if(previous&&previous!=g->root)radio_prune(previous);
    if(changed&&log_fd>=0) {
      dprintf(log_fd,"{\"event\":\"native-radio-model\",\"pid\":%d,\"control\":%llu,\"root\":%u,\"total\":%u,\"canonical_selected\":%u,\"selected\":%llu,\"members\":[",getpid(),(unsigned long long)g->native.control,g->root,snapshot.total,snapshot.canonical_selected,(unsigned long long)snapshot.selected);
      for(unsigned i=0;i<snapshot.count;i++)dprintf(log_fd,"%s{\"id\":%llu,\"enabled\":%d}",i?",":"",(unsigned long long)snapshot.items[i].identifier,snapshot.items[i].enabled);
      dprintf(log_fd,"]}\n");
    }
  }
  free(snapshot.items);g->busy--;
  if(!okay){radio_prune(g->root);return NULL;}return g;
}
static struct NXSResponse *radio_form_request(struct NativeForm *form,int operation,double x,double y,unsigned modifiers)
{
  if(operation==6){radio_release(form);return NULL;}
  struct NativeRadioGroup *g=(operation==1||!form->radio_owner)?radio_sync(form):radio_group(form->radio_owner);
  if(!g)return NULL;
  if(operation==1||(operation==5&&!g->tracking))
    return native_radio_item_draw(g->native.control,form->radio_member,form->rect.width,form->rect.height);
  if(operation==2) {
    if(!native_radio_item_draw(g->native.control,form->radio_member,form->rect.width,form->rect.height)||
       !native_radio_item_rect(g->native.control,form->radio_member,&form->radio_rect))return NULL;
  }
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,.process=identity(),
    .kind=NXS_RADIOGROUP,.control=g->native.control,.x=x+form->radio_rect.x,.y=y+form->radio_rect.y,.modifiers=modifiers};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  if(operation==2)g->tracking=response&&response->parts[0].y;
  if((operation==4||operation==5)&&response&&!response->parts[0].y) {
    g->tracking=0;
    if(native_radio_state(g->native.control,&g->native.state))response=native_radio_request(g->native.control,44,0,0,1);
  }
  return response;
}
static struct NXSResponse *radio_form_focus(struct NativeForm *form)
{
  struct NativeRadioGroup *g=radio_sync(form);return g?native_radio_request(g->native.control,44,0,0,1):NULL;
}
static int radio_click_allowed(struct NativeForm *form)
{
  struct NativeRadioGroup *g=radio_group(form->radio_owner);if(!g)return 0;
  g->tracking=0;struct RadioSnapshot snapshot;int okay=radio_snapshot(form->node,&snapshot);
  if(okay)okay=native_radio_binding_same(&g->native,snapshot.items,snapshot.count,1)&&snapshot.root==g->root&&
    native_radio_state(g->native.control,&g->native.state)&&g->native.state.selected==form->radio_member;
  free(snapshot.items);return okay;
}
static int radio_key_input(struct NativeForm *form,void *event,int type,unsigned key,const char *text,const char *unmodified,unsigned modifiers,int repeat)
{
  unsigned short *flags=(unsigned short *)((char *)event+32);
  struct NativeRadioGroup *g=radio_sync(form);
  if(!g){*flags|=0x40;note("native radio model unavailable; gesture cancelled");return 1;}
  uint32_t owner=g->root,origin=radio_node_id(form->node);uint64_t control=form->control;
  struct NXSRadioWireState before=g->native.state,after;
  NXSKeyEvent input={.size=sizeof(input),.type=type,.key=key,.text=text,.unmodified_text=unmodified,.modifiers=modifiers,.repeat=repeat};
  struct NXSResponse *response=native_radio_input(g->native.control,0,&input);
  if(!native_radio_response_state(response,&after)){*flags|=0x40;note("native radio input unavailable; gesture cancelled");return 1;}
  int result=response->parts[3].x;g->native.state=after;
  if(result==NXS_INPUT_NEXT||result==NXS_INPUT_PREVIOUS) {
    advance_form_focus(form->node,event,result);*flags|=0x40;return 1;
  }
  if(result!=NXS_INPUT_UNHANDLED||after.actions!=before.actions||type==NXS_KEY_UP)*flags|=0x40;
  /* Original engine focus and trusted activation own events, cancellation,
   * radio preactivation and rollback. Re-resolve IDs after every callback. */
  g->busy++;
  if(after.key_cell&&after.key_cell!=g->native.dom_focus&&native_radio_binding_contains(&g->native,after.key_cell)) {
    void *target=radio_node_for_id(after.key_cell);
    if(target&&input_form_kind(target)==NXS_RADIO&&form_enabled(target))
      ((void (*)(void *))(base+NXS_RADIO_FOCUS_OFFSET))(target);
  }
  void *node=radio_node_for_id(origin);form=node?find_form(node):NULL;
  if(form&&form->control==control&&form->radio_owner==owner&&after.actions!=before.actions&&after.selected) {
    struct RadioSnapshot snapshot;
    int valid=radio_snapshot(node,&snapshot)&&snapshot.root==owner&&native_radio_binding_same(&g->native,snapshot.items,snapshot.count,1);
    free(snapshot.items);
    void *target=valid?radio_node_for_id(after.selected):NULL;
    if(target&&input_form_kind(target)==NXS_RADIO&&form_enabled(target))
      ((void (*)(void *,const void *,int))(base+0xdd1402c))(target,event,1);
  }
  g->busy--;
  /* Cached form pointers may have been removed by focus/click listeners. */
  for(struct NativeForm *f=native_forms;f;f=f->next)if(f->radio_owner==owner)invalidate_form(f);
  node=radio_node_for_id(origin);form=node?find_form(node):NULL;
  if(form&&form->control==control)radio_sync(form);
  radio_prune(owner);return 1;
}
