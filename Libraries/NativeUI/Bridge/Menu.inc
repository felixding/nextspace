/* Application menu data serialization; no widget or shortcut implementation.
 * Include after Transport.inc. GPL-2.0-or-later. */
#include "../NativeUI.h"
static int native_menu_model(uint64_t control,const char *title,const NXSMenuItem *items,unsigned count) {
  if(!control||!title||count>4096||(count&&!items))return 0;
  size_t body=strlen(title);
  if(body>65536)return 0;
  for(unsigned i=0;i<count;i++) {
    if(items[i].size<sizeof(*items))return 0;
    size_t label=items[i].title?strlen(items[i].title):0,key=items[i].key_equivalent?strlen(items[i].key_equivalent):0;
    if(label>65536||key>65536||sizeof(struct NXSMenuWireItem)+label+key>65536-body)return 0;
    body+=sizeof(struct NXSMenuWireItem)+label+key;
  }
  size_t size=sizeof(struct NXSMenuModelRequest)+body;
  unsigned char *packet=malloc(size);if(!packet)return 0;
  struct NXSMenuModelRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=25,
    .process=identity(),.control=control,.text_size=body,.count=count,.title_size=strlen(title)};
  memcpy(packet,&request,sizeof(request));size_t offset=sizeof(request);
  memcpy(packet+offset,title,request.title_size);offset+=request.title_size;
  for(unsigned i=0;i<count;i++) {
    const NXSMenuItem *item=&items[i];
    struct NXSMenuWireItem wire={.parent=item->parent,.flags=item->flags,.command=item->command,
      .modifiers=item->modifiers,.title_size=item->title?strlen(item->title):0,
      .key_size=item->key_equivalent?strlen(item->key_equivalent):0};
    memcpy(packet+offset,&wire,sizeof(wire));offset+=sizeof(wire);
    if(wire.title_size)memcpy(packet+offset,item->title,wire.title_size);offset+=wire.title_size;
    if(wire.key_size)memcpy(packet+offset,item->key_equivalent,wire.key_size);offset+=wire.key_size;
  }
  struct NXSResponse *response=exchange_bytes(packet,size);free(packet);
  return response&&response->parts[3].x==1;
}
static struct NXSResponse *native_menu_request(uint64_t control,unsigned operation,int state) {
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,
    .process=identity(),.control=control,.state=state};
  return exchange_bytes(&request,sizeof(request));
}
