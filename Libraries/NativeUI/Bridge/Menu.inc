/* Application menu data serialization; no widget or shortcut implementation.
 * Include after Transport.inc. GPL-2.0-or-later. */
#include "../NativeUI.h"
static int native_menu_key_request(uint64_t control,const NXSKeyEvent *event,int mode) {
  const char *text=event->text?event->text:"",*unmodified=event->unmodified_text?event->unmodified_text:"";
  size_t first=strlen(text),second=strlen(unmodified);
  if(first+second>65536)return 0;
  size_t size=sizeof(struct NXSControlInputRequest)+first+second;
  struct NXSControlInputRequest *request=calloc(1,size);if(!request)return 0;
  *request=(struct NXSControlInputRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=27,.process=identity(),
    .control=control,
    .type=event->type,.modifiers=event->modifiers,.key=event->key,.repeat=event->repeat,
    .text_size=first,.unmodified_size=second,.focused=mode};
  memcpy(request+1,text,first);memcpy((char *)(request+1)+first,unmodified,second);
  struct NXSResponse *response=exchange_bytes(request,size);free(request);
  return response&&response->parts[3].x==1;
}
static int __attribute__((unused)) native_application_menu_key(const NXSKeyEvent *event,int execute) {
  return native_menu_key_request(0,event,!!execute);
}
static int __attribute__((unused)) native_model_menu_key(uint64_t control,const NXSKeyEvent *event,int execute) {
  return control&&native_menu_key_request(control,event,execute?1:-1);
}
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
