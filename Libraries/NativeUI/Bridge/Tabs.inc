/* Application tab data serialization; no widget implementation.
 * Include after Protocol.h and Transport.inc. GPL-2.0-or-later. */
#include "../NativeUI.h"
static struct NXSResponse *native_tabs_request(uint64_t control,unsigned operation,double width,double height,int enabled) {
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,
    .process=identity(),.kind=NXS_TABVIEW,.control=control,.width=width,.height=height,.enabled=enabled};
  return exchange_bytes(&request,sizeof(request));
}
static struct NXSResponse *native_tabs_model(uint64_t control,const NXSTabItem *items,unsigned count,uint64_t selected,double scale) {
  if(!control||count>4096||(count&&!items))return NULL;
  size_t body=0;
  for(unsigned i=0;i<count;i++) {
    if(items[i].size<sizeof(*items))return NULL;
    size_t title=items[i].title?strlen(items[i].title):0,tip=items[i].tooltip?strlen(items[i].tooltip):0;
    if(title>65536||tip>65536||sizeof(struct NXSTabWireItem)+title+tip>65536-body)return NULL;
    body+=sizeof(struct NXSTabWireItem)+title+tip;
  }
  size_t size=sizeof(struct NXSControlTabsRequest)+body;unsigned char *packet=malloc(size);if(!packet)return NULL;
  struct NXSControlTabsRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=36,.process=identity(),
    .kind=NXS_TABVIEW,.control=control,.text_size=body,.count=count,.selected=selected,.scale=scale};
  memcpy(packet,&request,sizeof(request));size_t offset=sizeof(request);
  for(unsigned i=0;i<count;i++) {
    struct NXSTabWireItem item={.identifier=items[i].identifier,.title_size=items[i].title?strlen(items[i].title):0,.tooltip_size=items[i].tooltip?strlen(items[i].tooltip):0};
    memcpy(packet+offset,&item,sizeof(item));offset+=sizeof(item);
    if(item.title_size)memcpy(packet+offset,items[i].title,item.title_size);offset+=item.title_size;
    if(item.tooltip_size)memcpy(packet+offset,items[i].tooltip,item.tooltip_size);offset+=item.tooltip_size;
  }
  struct NXSResponse *response=exchange_bytes(packet,size);free(packet);
  return response&&response->parts[3].x==1?response:NULL;
}
static int native_tabs_state(uint64_t control,struct NXSTabWireState *state) {
  struct NXSResponse *r=native_tabs_request(control,37,0,0,1);
  if(!r||r->parts[3].x!=1||r->size!=sizeof(*r)+sizeof(*state))return 0;
  memcpy(state,r+1,sizeof(*state));return 1;
}
static int native_tabs_item_rect(uint64_t control,uint64_t identifier,struct NXSRectD *rect) {
  struct NXSControlTabItemRequest req={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=38,.process=identity(),
    .kind=NXS_TABVIEW,.control=control,.identifier=identifier};
  struct NXSResponse *r=exchange_bytes(&req,sizeof(req));
  if(!r||r->parts[3].x!=1)return 0;*rect=r->parts[6];return 1;
}
