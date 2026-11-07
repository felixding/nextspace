/* Shared application list serialization and native snapshots. No list control,
 * selection, navigation, layout or drawing implementation. GPL-2.0-or-later. */
#include "../NativeUI.h"
static struct NXSResponse *native_list_request(uint64_t control,unsigned operation,double width,double height,int enabled)
{
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,
    .process=identity(),.kind=NXS_LISTBOX,.control=control,.width=width,.height=height,.enabled=enabled};
  return exchange_bytes(&request,sizeof(request));
}
/* The selection is borrowed from the transport response until the next RPC. */
static int native_list_response_state(const struct NXSResponse *response,struct NXSListWireState *state,const uint64_t **selection)
{
  if(!response||!state||!selection||response->width||response->height||response->stride||response->size<sizeof(*response)+sizeof(*state))return 0;
  struct NXSListWireState value;memcpy(&value,response+1,sizeof(value));
  if(value.count>4096||value.selected_count>value.count||(value.flags&~NXS_LIST_MULTIPLE)||value.reserved||
     (!(value.flags&NXS_LIST_MULTIPLE)&&value.selected_count>1)||
     response->size!=sizeof(*response)+sizeof(value)+value.selected_count*sizeof(uint64_t))return 0;
  const uint64_t *ids=(const uint64_t *)((const unsigned char *)(response+1)+sizeof(value));
  for(unsigned i=0;i<value.selected_count;i++) {
    if(!ids[i])return 0;
    for(unsigned j=0;j<i;j++)if(ids[i]==ids[j])return 0;
  }
  *state=value;*selection=ids;return 1;
}
static struct NXSResponse *native_list_model(uint64_t control,const NXSListItem *items,unsigned count,unsigned flags,uint64_t key_cell,double scale)
{
  if(!control||count>4096||(count&&!items)||(flags&~NXS_LIST_MULTIPLE))return NULL;
  size_t body=0;
  for(unsigned i=0;i<count;i++) {
    if(items[i].size<sizeof(*items)||!items[i].identifier)return NULL;
    size_t title=items[i].title?strnlen(items[i].title,65537):0;
    if(title>65536||sizeof(struct NXSListWireItem)+title>65536-body)return NULL;
    body+=sizeof(struct NXSListWireItem)+title;
  }
  size_t size=sizeof(struct NXSControlListRequest)+body;unsigned char *packet=malloc(size);if(!packet)return NULL;
  struct NXSControlListRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=48,.process=identity(),
    .kind=NXS_LISTBOX,.control=control,.text_size=body,.count=count,.flags=flags,.key_cell=key_cell,.scale=scale};
  memcpy(packet,&request,sizeof(request));size_t offset=sizeof(request);
  for(unsigned i=0;i<count;i++) {
    struct NXSListWireItem item={.identifier=items[i].identifier,.enabled=!!items[i].enabled,.selected=!!items[i].selected,
      .title_size=items[i].title?strlen(items[i].title):0};
    memcpy(packet+offset,&item,sizeof(item));offset+=sizeof(item);
    if(item.title_size)memcpy(packet+offset,items[i].title,item.title_size);offset+=item.title_size;
  }
  struct NXSResponse *response=exchange_bytes(packet,size);free(packet);
  return response&&response->parts[3].x==1?response:NULL;
}
static int native_list_state(uint64_t control,struct NXSListWireState *state,const uint64_t **selection)
{
  struct NXSResponse *response=native_list_request(control,49,0,0,1);
  return response&&response->parts[3].x==1&&native_list_response_state(response,state,selection);
}
static int native_list_item_rect(uint64_t control,uint64_t identifier,struct NXSRectD *rect)
{
  struct NXSControlListItemRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=50,
    .process=identity(),.kind=NXS_LISTBOX,.control=control,.identifier=identifier};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  if(!response||!rect||response->parts[3].x!=1)return 0;*rect=response->parts[6];return rect->width>0&&rect->height>0;
}
static int native_list_item_geometry(uint64_t control,uint64_t identifier,struct NXSRectD *rect,struct NXSListWireState *state)
{
  struct NXSControlListItemRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=50,
    .process=identity(),.kind=NXS_LISTBOX,.control=control,.identifier=identifier};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));const uint64_t *selection;
  if(!response||!rect||!state||response->parts[3].x!=1||!native_list_response_state(response,state,&selection))return 0;
  *rect=response->parts[6];return rect->width>0&&rect->height>0;
}
static struct NXSResponse *native_list_scroll(uint64_t control,double x,double y)
{
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=51,
    .process=identity(),.kind=NXS_LISTBOX,.control=control,.x=x,.y=y};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));return response&&response->parts[3].x==1?response:NULL;
}
static struct NXSResponse *native_list_wheel(uint64_t control,const NXSWheelEvent *event)
{
  if(!event||event->size<sizeof(*event))return NULL;
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=35,
    .process=identity(),.kind=NXS_LISTBOX,.control=control,.x=event->x,.y=event->y,.minimum=event->delta_x,.maximum=event->delta_y,.modifiers=event->modifiers};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));return response&&response->parts[3].x==1?response:NULL;
}
static int native_list_geometry(uint64_t control,NXSScrollGeometry *geometry)
{
  struct NXSResponse *response=native_list_request(control,52,0,0,1);
  if(!response||!geometry||response->parts[3].x!=1||response->size!=sizeof(*response)+sizeof(*geometry))return 0;
  NXSScrollGeometry value;memcpy(&value,response+1,sizeof(value));
  if(value.size!=sizeof(value))return 0;*geometry=value;return 1;
}
#include "Inputs.inc"
static struct NXSResponse *native_list_input(uint64_t control,int focused,const NXSKeyEvent *event)
{return native_control_input(NXS_LISTBOX,control,focused,event);}
