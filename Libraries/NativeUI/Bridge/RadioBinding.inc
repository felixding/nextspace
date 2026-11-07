/* Shared native group model lifetime/cache; no engine or widget behavior.
 * Include after Radios.inc. GPL-2.0-or-later. */
struct NXSRadioBinding {
  uint64_t control,dom_focus,pointer_actions;
  uint32_t epoch;
  unsigned count,columns;
  NXSRadioItem *items;
  struct NXSRadioWireState state,pointer_state;
  double scale;
  int created,focused,tracking,pointer_pending,pointer_ready;
};
static void native_radio_binding_free_items(NXSRadioItem *items,unsigned count)
{for(unsigned i=0;i<count;i++)free((void *)items[i].title);free(items);}
static int native_radio_binding_contains(const struct NXSRadioBinding *binding,uint64_t identifier)
{for(unsigned i=0;i<binding->count;i++)if(binding->items[i].identifier==identifier)return 1;return 0;}
static int native_radio_binding_same(const struct NXSRadioBinding *binding,const NXSRadioItem *items,unsigned count,unsigned columns)
{
  if(binding->count!=count||binding->columns!=columns)return 0;
  for(unsigned i=0;i<count;i++)if(binding->items[i].identifier!=items[i].identifier||binding->items[i].enabled!=!!items[i].enabled||
    strcmp(binding->items[i].title,items[i].title?items[i].title:""))return 0;
  return 1;
}
static int native_radio_binding_sync(struct NXSRadioBinding *binding,const NXSRadioItem *items,unsigned count,
  unsigned columns,uint64_t selected,uint64_t focused,double scale)
{
  uint32_t epoch=atomic_load(&native_host_epoch);
  if(!binding->created||binding->epoch!=epoch) {
    struct NXSResponse *r=native_radio_request(binding->control,1,1,1,1);
    if(!r||r->width<1||r->height<1||((unsigned)r->parts[1].y&3)!=3)return 0;
    binding->epoch=atomic_load(&native_host_epoch);binding->created=1;binding->focused=0;
    native_radio_binding_free_items(binding->items,binding->count);binding->items=NULL;binding->count=0;
    binding->state=(struct NXSRadioWireState){0};binding->dom_focus=0;
    binding->pointer_state=(struct NXSRadioWireState){0};
    binding->tracking=binding->pointer_pending=binding->pointer_ready=0;binding->pointer_actions=0;
  }
  int same=native_radio_binding_same(binding,items,count,columns);
  uint64_t key=focused!=binding->dom_focus&&focused?focused:binding->state.key_cell;
  int key_present=0;for(unsigned i=0;i<count;i++)if(items[i].identifier==key)key_present=1;
  if(!key_present)key=0;
  if(!same||selected!=binding->state.selected||key!=binding->state.key_cell||scale!=binding->scale) {
    NXSRadioItem *copy=calloc(count?count:1,sizeof(*copy));if(!copy)return 0;
    for(unsigned i=0;i<count;i++) {
      copy[i]=items[i];copy[i].enabled=!!items[i].enabled;copy[i].title=strdup(items[i].title?items[i].title:"");
      if(!copy[i].title){native_radio_binding_free_items(copy,i);return 0;}
    }
    struct NXSRadioWireState state;
    if(!native_radio_response_state(native_radio_model(binding->control,items,count,columns,selected,key,scale),&state)) {
      native_radio_binding_free_items(copy,count);return 0;
    }
    native_radio_binding_free_items(binding->items,binding->count);binding->items=copy;
    binding->count=count;binding->columns=columns;binding->scale=scale;binding->state=state;
  }
  if(binding->focused!=!!focused) {
    struct NXSRadioWireState state;
    if(!native_radio_response_state(native_radio_input(binding->control,!!focused,NULL),&state))return 0;
    binding->state=state;binding->focused=!!focused;
  }
  binding->dom_focus=focused;return 1;
}
static void native_radio_binding_destroy(struct NXSRadioBinding *binding)
{
  if(binding->created&&binding->epoch==atomic_load(&native_host_epoch))native_radio_request(binding->control,6,0,0,1);
  native_radio_binding_free_items(binding->items,binding->count);memset(binding,0,sizeof(*binding));
}
/* Pointer coordinates come from the application member. The native matrix
 * supplies its own cell rectangle; no grid or tracking policy is reproduced. */
static struct NXSResponse *native_radio_binding_request(struct NXSRadioBinding *binding,uint64_t member,
  struct NXSRectD *rectangle,unsigned operation,double width,double height,double x,double y,unsigned modifiers,unsigned clicks)
{
  if(operation==1||(operation==5&&!binding->tracking))return native_radio_item_draw(binding->control,member,width,height);
  if(operation==2) {
    if(!native_radio_item_draw(binding->control,member,width,height)||!native_radio_item_rect(binding->control,member,rectangle))return NULL;
    binding->pointer_actions=binding->state.actions;binding->pointer_pending=binding->pointer_ready=0;
  }
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,.process=identity(),
    .kind=NXS_RADIOGROUP,.control=binding->control,.x=x+rectangle->x,.y=y+rectangle->y,.modifiers=modifiers};
  struct NXSResponse *response=operation==2&&clicks>1?
    native_pointer_press(NXS_RADIOGROUP,binding->control,request.x,request.y,modifiers,clicks):exchange_bytes(&request,sizeof(request));
  if(operation==2)binding->tracking=response&&response->parts[0].y;
  if((operation==4||operation==5)&&response&&!response->parts[0].y) {
    binding->tracking=0;
    if(native_radio_state(binding->control,&binding->state)) {
      binding->pointer_pending=binding->state.actions!=binding->pointer_actions;
      binding->pointer_ready=1;
      binding->pointer_state=binding->state;
      response=native_radio_request(binding->control,44,0,0,1);
    }
  }
  return response;
}
/* A member can retire during an application event callback. End the original
 * native mouseDown before changing its model; discard its now-stale action. */
static void native_radio_binding_cancel(struct NXSRadioBinding *binding)
{
  if(binding->created&&binding->epoch==atomic_load(&native_host_epoch)&&binding->tracking) {
    struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=4,.process=identity(),
      .kind=NXS_RADIOGROUP,.control=binding->control,.x=-10000,.y=-10000};
    struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
    for(unsigned i=0;response&&response->parts[0].y&&i<100;i++) {
      struct timespec pause={.tv_nsec=2000000};nanosleep(&pause,NULL);
      response=native_radio_request(binding->control,5,0,0,1);
    }
    binding->tracking=response&&response->parts[0].y;
    if(response&&!binding->tracking)native_radio_state(binding->control,&binding->state);
  }
  binding->pointer_pending=binding->pointer_ready=0;
}
