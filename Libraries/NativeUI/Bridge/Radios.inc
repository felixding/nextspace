/* Shared application group serialization and native state/geometry transport.
 * Include after Protocol.h and Transport.inc. GPL-2.0-or-later. */
#include "../NativeUI.h"
static struct NXSResponse *native_radio_request(uint64_t control,unsigned operation,double width,double height,int enabled)
{
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,
    .process=identity(),.kind=NXS_RADIOGROUP,.control=control,.width=width,.height=height,.enabled=enabled};
  return exchange_bytes(&request,sizeof(request));
}
static int native_radio_response_state(const struct NXSResponse *response,struct NXSRadioWireState *state)
{
  if(!response||!state||response->width||response->height||response->stride||response->size!=sizeof(*response)+sizeof(*state))return 0;
  memcpy(state,response+1,sizeof(*state));return 1;
}
static struct NXSResponse *native_radio_model(uint64_t control,const NXSRadioItem *items,unsigned count,
  unsigned columns,uint64_t selected,uint64_t key_cell,double scale)
{
  if(!control||count>4096||(count&&!items)||!columns||count%columns)return NULL;
  size_t body=0;
  for(unsigned i=0;i<count;i++) {
    if(items[i].size<sizeof(*items)||!items[i].identifier)return NULL;
    size_t title=items[i].title?strnlen(items[i].title,65537):0;
    if(title>65536||sizeof(struct NXSRadioWireItem)+title>65536-body)return NULL;
    body+=sizeof(struct NXSRadioWireItem)+title;
  }
  size_t size=sizeof(struct NXSControlRadioRequest)+body;unsigned char *packet=malloc(size);if(!packet)return NULL;
  struct NXSControlRadioRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=43,.process=identity(),
    .kind=NXS_RADIOGROUP,.control=control,.text_size=body,.count=count,.columns=columns,
    .selected=selected,.key_cell=key_cell,.scale=scale};
  memcpy(packet,&request,sizeof(request));size_t offset=sizeof(request);
  for(unsigned i=0;i<count;i++) {
    struct NXSRadioWireItem item={.identifier=items[i].identifier,.enabled=!!items[i].enabled,
      .title_size=items[i].title?strlen(items[i].title):0};
    memcpy(packet+offset,&item,sizeof(item));offset+=sizeof(item);
    if(item.title_size)memcpy(packet+offset,items[i].title,item.title_size);offset+=item.title_size;
  }
  struct NXSResponse *response=exchange_bytes(packet,size);free(packet);
  return response&&response->parts[3].x==1?response:NULL;
}
static int native_radio_state(uint64_t control,struct NXSRadioWireState *state)
{
  struct NXSResponse *response=native_radio_request(control,44,0,0,1);
  return response&&response->parts[3].x==1&&native_radio_response_state(response,state);
}
static struct NXSResponse *native_radio_item_request(uint64_t control,uint64_t identifier,unsigned operation)
{
  struct NXSControlRadioItemRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,
    .process=identity(),.kind=NXS_RADIOGROUP,.control=control,.identifier=identifier};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  return response&&response->parts[3].x==1?response:NULL;
}
static int native_radio_item_rect(uint64_t control,uint64_t identifier,struct NXSRectD *rectangle)
{
  struct NXSResponse *response=native_radio_item_request(control,identifier,45);
  if(!response||!rectangle)return 0;*rectangle=response->parts[6];return rectangle->width>0&&rectangle->height>0;
}
static struct NXSResponse *native_radio_item_draw(uint64_t control,uint64_t identifier,double width,double height)
{
  struct NXSControlRadioItemRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=46,.process=identity(),
    .kind=NXS_RADIOGROUP,.control=control,.identifier=identifier,.width=width,.height=height};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  return response&&response->parts[3].x==1?response:NULL;
}
static struct NXSResponse *native_radio_input(uint64_t control,int focused,const NXSKeyEvent *event)
{
  if(!control||(event&&event->size<sizeof(*event)))return NULL;
  size_t text=event&&event->text?strnlen(event->text,65537):0;
  size_t unmodified=event&&event->unmodified_text?strnlen(event->unmodified_text,65537):0;
  if(text+unmodified>65536)return NULL;
  size_t size=sizeof(struct NXSControlInputRequest)+text+unmodified;
  struct NXSControlInputRequest *request=calloc(1,size);if(!request)return NULL;
  *request=(struct NXSControlInputRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=event?8:7,
    .process=identity(),.kind=NXS_RADIOGROUP,.control=control,.focused=!!focused};
  if(event) {
    request->type=event->type;request->modifiers=event->modifiers;request->key=event->key;
    request->repeat=event->repeat;request->text_size=text;request->unmodified_size=unmodified;
    if(text)memcpy(request+1,event->text,text);
    if(unmodified)memcpy((char *)(request+1)+text,event->unmodified_text,unmodified);
  }
  struct NXSResponse *response=exchange_bytes(request,size);free(request);return response;
}
