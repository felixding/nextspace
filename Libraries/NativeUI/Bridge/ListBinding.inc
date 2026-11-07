/* Shared list model/snapshot lifetime. The provider owns every control,
 * selection, navigation, layout and tracking decision. Include after Lists.inc.
 * GPL-2.0-or-later. */
struct NXSListBinding {
  uint64_t control;
  uint32_t epoch;
  unsigned count,flags;
  NXSListItem *items;
  struct NXSListWireState state;
  NXSScrollGeometry geometry;
  uint32_t geometry_epoch;
  int geometry_checked,geometry_supported,geometry_ready;
  uint64_t *selection;
  uint32_t *pixels;
  int pixel_width,pixel_height,created,focused,enabled,tracking;
  double width,height,scale;
};
static void native_list_binding_free_items(NXSListItem *items,unsigned count)
{for(unsigned i=0;i<count;i++)free((void *)items[i].title);free(items);}
static int native_list_binding_same(const struct NXSListBinding *binding,const NXSListItem *items,unsigned count,unsigned flags)
{
  if(binding->count!=count||binding->flags!=flags)return 0;
  for(unsigned i=0;i<count;i++)if(binding->items[i].identifier!=items[i].identifier||
    binding->items[i].enabled!=!!items[i].enabled||binding->items[i].selected!=!!items[i].selected||
    strcmp(binding->items[i].title,items[i].title?items[i].title:""))return 0;
  return 1;
}
static int native_list_binding_snapshot(struct NXSListBinding *binding,const struct NXSResponse *response)
{
  struct NXSListWireState state;const uint64_t *ids;
  if(!native_list_response_state(response,&state,&ids))return 0;
  uint64_t *copy=malloc((state.selected_count?state.selected_count:1)*sizeof(*copy));if(!copy)return 0;
  memcpy(copy,ids,state.selected_count*sizeof(*copy));free(binding->selection);
  binding->selection=copy;binding->state=state;return 1;
}
static int native_list_binding_refresh(struct NXSListBinding *binding)
{
  if(!binding->created||binding->epoch!=atomic_load(&native_host_epoch))return 0;
  struct NXSResponse *response=native_list_request(binding->control,49,0,0,1);
  if(!response||response->parts[3].x!=1||!native_list_binding_snapshot(binding,response))return 0;
  uint32_t epoch=atomic_load(&native_host_epoch);
  if(!binding->geometry_checked||binding->geometry_epoch!=epoch) {
    response=exchange((struct NXSRequest){.magic=NXS_CHROMIUM_MAGIC,.operation=7,.process=identity()});
    binding->geometry_supported=response&&response->parts[3].y==NXS_SCROLL_GEOMETRY;
    binding->geometry_checked=!!response;binding->geometry_epoch=atomic_load(&native_host_epoch);
  }
  binding->geometry_ready=binding->geometry_supported&&native_list_geometry(binding->control,&binding->geometry);
  response=native_list_request(binding->control,5,0,0,1);
  if(!response||response->width<1||response->height<1||response->width>8192||response->height>8192||
    response->stride!=response->width*4||response->size!=sizeof(*response)+(size_t)response->stride*response->height)return 0;
  uint32_t *pixels=malloc((size_t)response->stride*response->height);if(!pixels)return 0;
  memcpy(pixels,response+1,(size_t)response->stride*response->height);free(binding->pixels);
  binding->pixels=pixels;binding->pixel_width=response->width;binding->pixel_height=response->height;
  binding->tracking=!!response->parts[0].y;return 1;
}
static int native_list_binding_sync(struct NXSListBinding *binding,const NXSListItem *items,unsigned count,unsigned flags,
  double width,double height,int enabled,int focused)
{
  if(!binding||!binding->control||count>4096||(count&&!items)||(flags&~NXS_LIST_MULTIPLE))return 0;
  uint32_t epoch=atomic_load(&native_host_epoch);
  if(!binding->created||binding->epoch!=epoch) {
    struct NXSResponse *response=native_list_request(binding->control,1,width,height,!!enabled);
    if(!response||response->width<1||response->height<1||response->parts[5].y<1)return 0;
    binding->epoch=atomic_load(&native_host_epoch);binding->created=1;
    binding->focused=binding->tracking=0;binding->scale=response->parts[5].y;
    binding->width=width;binding->height=height;binding->enabled=!!enabled;
    native_list_binding_free_items(binding->items,binding->count);binding->items=NULL;binding->count=0;
    binding->state=(struct NXSListWireState){0};free(binding->selection);binding->selection=NULL;
    binding->geometry=(NXSScrollGeometry){0};binding->geometry_checked=binding->geometry_ready=binding->geometry_supported=0;
    /* Force even an empty model to establish its flags in the new host. */
    binding->flags=~flags;
  }
  if(binding->tracking)return native_list_binding_refresh(binding);
  if(binding->width!=width||binding->height!=height||binding->enabled!=!!enabled) {
    struct NXSResponse *response=native_list_request(binding->control,1,width,height,!!enabled);
    if(!response||response->width<1||response->height<1)return 0;
    binding->width=width;binding->height=height;binding->enabled=!!enabled;binding->scale=response->parts[5].y;
  }
  if(!native_list_binding_same(binding,items,count,flags)) {
    NXSListItem *copy=calloc(count?count:1,sizeof(*copy));if(!copy)return 0;
    uint64_t key=0;
    for(unsigned i=0;i<count;i++) {
      copy[i]=items[i];copy[i].enabled=!!items[i].enabled;copy[i].selected=!!items[i].selected;
      copy[i].title=strdup(items[i].title?items[i].title:"");
      if(!copy[i].title){native_list_binding_free_items(copy,i);return 0;}
      if(items[i].identifier==binding->state.key_cell)key=items[i].identifier;
    }
    if(!native_list_binding_snapshot(binding,native_list_model(binding->control,items,count,flags,key,binding->scale))) {
      native_list_binding_free_items(copy,count);return 0;
    }
    native_list_binding_free_items(binding->items,binding->count);binding->items=copy;binding->count=count;binding->flags=flags;
  }
  if(binding->focused!=!!focused) {
    if(!native_list_binding_snapshot(binding,native_list_input(binding->control,focused,NULL)))return 0;
    binding->focused=!!focused;
  }
  return native_list_binding_refresh(binding);
}
static int native_list_binding_scroll(struct NXSListBinding *binding,double x,double y)
{
  if(!binding||!binding->created||binding->epoch!=atomic_load(&native_host_epoch))return 0;
  return native_list_binding_snapshot(binding,native_list_scroll(binding->control,x,y))&&native_list_binding_refresh(binding);
}
static int native_list_binding_wheel(struct NXSListBinding *binding,const NXSWheelEvent *event)
{
  if(!binding||!binding->created||binding->epoch!=atomic_load(&native_host_epoch))return 0;
  return native_list_binding_snapshot(binding,native_list_wheel(binding->control,event))&&native_list_binding_refresh(binding);
}
static void native_list_binding_destroy(struct NXSListBinding *binding)
{
  if(binding->created&&binding->epoch==atomic_load(&native_host_epoch))native_list_request(binding->control,6,0,0,1);
  native_list_binding_free_items(binding->items,binding->count);free(binding->selection);free(binding->pixels);
  memset(binding,0,sizeof(*binding));
}
