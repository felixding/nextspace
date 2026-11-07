/* Shared native-list packets against independent native state/images.
 * No widget or selection implementation. GPL-2.0-or-later. */
#define _GNU_SOURCE
#include "NativeUI.h"
#include "Bridge/Protocol.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
static void note(const char *message){fprintf(stderr,"%s\n",message);}
#include "Bridge/Transport.inc"
#include "Bridge/Lists.inc"
_Static_assert(sizeof(struct NXSControlListRequest)==56,"List model wire");
_Static_assert(sizeof(struct NXSListWireItem)==24,"List row wire");
_Static_assert(sizeof(struct NXSControlListItemRequest)==40,"List geometry wire");
_Static_assert(sizeof(struct NXSListWireState)==88,"List state wire");
static unsigned checks,images,count,flags;static double scale;static const char *directory,*reference;
static NXSListItem items[32];
struct Snapshot {struct NXSListWireState value;uint64_t ids[4096];};
static uint64_t identifier(unsigned i){return UINT64_C(0xf000000000000001)+i;}
static void check(const char *name,int value)
{printf("{\"case\":\"%s\",\"passed\":%s}\n",name,value?"true":"false");fflush(stdout);assert(value);checks++;}
static struct Snapshot snapshot(void)
{
  struct Snapshot s={0};const uint64_t *selection=NULL;
  assert(native_list_state(1,&s.value,&selection));memcpy(s.ids,selection,s.value.selected_count*sizeof(*selection));return s;
}
static void expected(const char *name)
{
  char path[1024];snprintf(path,sizeof(path),"%s/%s-state.bin",reference,name);FILE *in=fopen(path,"rb");assert(in);
  struct Snapshot want={0},actual=snapshot();assert(fread(&want.value,sizeof(want.value),1,in)==1&&want.value.selected_count<=4096);
  assert(fread(want.ids,sizeof(uint64_t),want.value.selected_count,in)==want.value.selected_count&&fgetc(in)==EOF);fclose(in);
  if(memcmp(&actual,&want,sizeof(want.value)+want.value.selected_count*sizeof(uint64_t)))
    fprintf(stderr,"%s actual count %u selection %u primary %llu key %llu actions %llu y %g; expected count %u selection %u primary %llu key %llu actions %llu y %g\n",name,actual.value.count,actual.value.selected_count,(unsigned long long)actual.value.primary,(unsigned long long)actual.value.key_cell,(unsigned long long)actual.value.actions,actual.value.visible.y,want.value.count,want.value.selected_count,(unsigned long long)want.value.primary,(unsigned long long)want.value.key_cell,(unsigned long long)want.value.actions,want.value.visible.y);
  check(name,!memcmp(&actual,&want,sizeof(want.value)+want.value.selected_count*sizeof(uint64_t)));
}
static void image(const char *name)
{
  struct NXSResponse *r=native_list_request(1,5,0,0,1);assert(r&&r->width>0&&r->height>0&&r->stride>=r->width*4&&r->size==sizeof(*r)+r->stride*r->height);
  char path[1024];snprintf(path,sizeof(path),"%s/%s.argb",directory,name);FILE *out=fopen(path,"wb");assert(out);assert(fwrite(r+1,r->stride,r->height,out)==(size_t)r->height);fclose(out);
  printf("{\"event\":\"image\",\"name\":\"%s\",\"reference\":\"%s\",\"member\":0,\"width\":%d,\"height\":%d,\"stride\":%d}\n",name,name,r->width,r->height,r->stride);images++;
}
static void model(unsigned n,unsigned mode,uint64_t selected)
{
  count=n;flags=mode;for(unsigned i=0;i<count;i++)items[i]=(NXSListItem){sizeof(NXSListItem),identifier(i),i==0?"Alpha":i==1?"Bravo":i==2?"Charlie":i==3?"Delta":"Long row",i!=1,!!(selected&(UINT64_C(1)<<i))};
  struct NXSResponse *r=native_list_model(1,items,count,flags,0,scale);struct NXSListWireState value;const uint64_t *ids;
  check("native-model-reply-includes-complete-typed-selection",r&&native_list_response_state(r,&value,&ids)&&value.count==count&&value.flags==flags);
}
static void key(unsigned modifiers)
{
  NXSKeyEvent input={.size=sizeof(input),.type=NXS_KEY_DOWN,.key=NXS_KEY_DOWN_ARROW,.modifiers=modifiers};
  struct NXSListWireState value;const uint64_t *ids;struct NXSResponse *r=native_list_input(1,0,&input);
  check("native-key-returns-typed-state-and-selection",r&&native_list_response_state(r,&value,&ids));uint64_t actions=value.actions;
  input.type=NXS_KEY_UP;r=native_list_input(1,0,&input);assert(native_list_response_state(r,&value,&ids));check("native-key-up-adds-no-action",value.actions==actions);
}
static struct NXSResponse *pointer(unsigned op,double x,double y,unsigned modifiers)
{
  struct NXSControlRequest req={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=op,.process=identity(),.kind=NXS_LISTBOX,.control=1,.x=x,.y=y,.state=1,.modifiers=modifiers};
  return exchange_bytes(&req,sizeof(req));
}
static void click_at(double x,double y,unsigned modifiers)
{
  struct NXSResponse *r=pointer(22,x,y,modifiers);check("native-list-pointer-accepted",r&&r->parts[3].x==1);
  struct Snapshot busy=snapshot();(void)busy;
  check("native-list-model-rejected-during-tracking",!native_list_model(1,items,count,flags,0,scale));
  check("native-list-scroll-rejected-during-tracking",!native_list_scroll(1,0,0));
  r=native_list_request(1,1,180,96,1);check("native-list-config-rejected-during-tracking",r&&!r->width);
  r=native_list_request(1,5,0,0,1);check("native-list-remains-renderable-during-tracking",r&&r->width>0&&r->parts[0].y);
  assert(pointer(3,x,y,modifiers));assert(pointer(4,x,y,modifiers));
  for(unsigned i=0;i<400;i++) {
    r=native_list_request(1,49,0,0,1);if(!r->parts[0].y)return;usleep(2000);
  }
  assert(!"Native tracking did not finish");
}
static void click(unsigned row,unsigned modifiers)
{struct NXSRectD rect;assert(native_list_item_rect(1,identifier(row),&rect));click_at(rect.x+rect.width/2,rect.y+rect.height/2,modifiers);}
static struct NXSResponse *bad_model(unsigned bad)
{
  unsigned char packet[1024] __attribute__((aligned(8)))={0};size_t used=sizeof(struct NXSControlListRequest);
  for(unsigned i=0;i<4;i++) {
    const char *title=bad==2&&i==0?"\xff":items[i].title;
    struct NXSListWireItem item={.identifier=bad==1&&i==1?items[0].identifier:bad==9&&i==0?0:items[i].identifier,
      .enabled=bad==5?2:items[i].enabled,.selected=bad==6?2:items[i].selected,.title_size=strlen(title),.reserved=bad==7?1:0};
    memcpy(packet+used,&item,sizeof(item));used+=sizeof(item);memcpy(packet+used,title,item.title_size);used+=item.title_size;
  }
  if(bad==8)packet[used++]=1;
  struct NXSControlListRequest *req=(void *)packet;*req=(struct NXSControlListRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=48,
    .process=identity(),.kind=NXS_LISTBOX,.control=1,.text_size=used-sizeof(*req),.count=bad==4?5:4,.flags=bad==10?2:flags,
    .key_cell=bad==3?UINT64_MAX:0,.scale=scale};return exchange_bytes(packet,used);
}
static void foreign(const char *path,unsigned op)
{
  int peer=socket(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0);assert(peer>=0);struct timeval timeout={.tv_sec=3};assert(!setsockopt(peer,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout)));
  struct sockaddr_un address={.sun_family=AF_UNIX};assert(strlen(path)<sizeof(address.sun_path));strcpy(address.sun_path,path);assert(!connect(peer,(void *)&address,sizeof(address)));
  struct NXSControlRequest req={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=op,.process=identity(),.kind=NXS_LISTBOX,.control=1,.width=180,.height=96,.enabled=1};
  struct NXSControlListRequest model_req={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=48,.process=identity(),.kind=NXS_LISTBOX,.control=1,.scale=scale};
  struct NXSControlListItemRequest rect_req={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=50,.process=identity(),.kind=NXS_LISTBOX,.control=1,.identifier=identifier(0)};
  struct NXSControlInputRequest key_req={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=op,.process=identity(),.kind=NXS_LISTBOX,.control=1,.focused=1,.key=NXS_KEY_DOWN_ARROW};
  const void *data=&req;size_t size=sizeof(req);if(op==48){data=&model_req;size=sizeof(model_req);}else if(op==50){data=&rect_req;size=sizeof(rect_req);}else if(op==7||op==8){data=&key_req;size=sizeof(key_req);}
  assert(send(peer,data,size,MSG_NOSIGNAL)==(ssize_t)size);struct NXSResponse response;assert(recv(peer,&response,sizeof(response),0)==sizeof(response));
  check("another-connection-cannot-read-change-input-or-destroy-list",!response.width&&!response.parts[3].x&&!response.parts[0].width&&response.size==sizeof(response));close(peer);
}
int main(int argc,char **argv)
{
  assert(argc>=5);directory=argv[2];scale=atof(argv[3]);reference=argv[4];setvbuf(stdout,NULL,_IOLBF,0);assert(bridge_connect(argv[1]));
  struct NXSResponse *r=exchange((struct NXSRequest){.magic=NXS_CHROMIUM_MAGIC,.operation=7});assert(r);
  if(argc>5&&!strcmp(argv[5],"--expect-no-list")) {
    check("older-provider-advertises-no-list-wire",r->parts[3].x==0);
    r=native_list_request(1,1,180,96,1);check("older-provider-rejects-list-creation",r&&!r->width);
    check("older-provider-rejects-typed-list-query",!native_list_state(1,&(struct NXSListWireState){0},&(const uint64_t *){0}));
  } else {
    check("native-list-capability-crosses-shared-wire",r->parts[3].x==NXS_LIST_ITEMS);
    r=native_list_request(1,1,180,96,1);check("native-list-created-at-actual-density",r&&r->width==lround(180*scale)&&r->height==lround(96*scale)&&r->parts[5].y==scale);
    r=native_list_request(99,1,scale>1?2048:8192,scale>1?2048:8192,1);check("oversized-initial-list-is-rejected",r&&!r->width);
    check("rejected-initial-list-registers-no-native-state",!native_list_state(99,&(struct NXSListWireState){0},&(const uint64_t *){0}));
    r=native_list_request(99,1,180,96,1);check("valid-create-after-rejected-initial-size-succeeds",r&&r->width>0);assert(native_list_request(99,6,0,0,1));
    model(4,0,1);assert(native_list_input(1,1,NULL));expected("single");image("single");key(0);expected("single-key");image("single-key");key(0);expected("single-next");image("single-next");
    for(unsigned op=1;op<=8;op++)if(op!=2&&op!=3&&op!=4&&op!=5)foreign(argv[1],op);
    foreign(argv[1],48);foreign(argv[1],49);foreign(argv[1],50);foreign(argv[1],51);foreign(argv[1],35);expected("single-next");
    click(0,0);expected("single-pointer");image("single-pointer");
    model(4,1,5);expected("multiple");image("multiple");key(NXS_SHIFT);expected("multiple-shift");image("multiple-shift");
    check("same-model-is-a-native-no-op",native_list_model(1,items,count,flags,0,scale)!=NULL);expected("multiple-shift");click(3,NXS_SHIFT);expected("multiple-pointer");image("multiple-pointer");
    for(unsigned bad=1;bad<=10;bad++){r=bad_model(bad);check("malformed-list-model-rejected",r&&!r->parts[3].x);expected("multiple-pointer");}
    check("single-mode-rejects-multiple-selected-rows",!native_list_model(1,items,count,0,0,scale));expected("multiple-pointer");
    double invalid[]={0,9,NAN,INFINITY,scale*.5};for(unsigned i=0;i<5;i++){check("wrong-native-density-rejected-atomically",!native_list_model(1,items,count,flags,0,invalid[i]));expected("multiple-pointer");}
    r=native_list_request(1,1,scale>1?2048:8192,scale>1?2048:8192,1);check("actual-density-bitmap-budget-is-enforced",r&&!r->width);expected("multiple-pointer");
    model(24,1,1);expected("scrollable");image("scrollable");check("native-scroll-position-crosses-IPC",native_list_scroll(1,0,120)!=NULL);expected("scrolled");image("scrolled");
    check("native-wheel-crosses-existing-input-operation",native_list_wheel(1,&(NXSWheelEvent){.size=sizeof(NXSWheelEvent),.x=90,.y=50,.delta_y=20})!=NULL);expected("wheel");image("wheel");
    assert(native_list_request(1,1,180,96,0));assert(native_list_input(1,0,NULL));expected("disabled");image("disabled");assert(native_list_scroll(1,0,0));
    char path[1024];snprintf(path,sizeof(path),"%s/disabled-scroll-part.bin",reference);FILE *part_file=fopen(path,"rb");assert(part_file);struct NXSRectD part;assert(fread(&part,sizeof(part),1,part_file)==1&&part.width>0&&part.height>0);fclose(part_file);
    click_at(part.x+part.width/2,part.y+part.height/2,0);expected("disabled-scrolled");image("disabled-scrolled");
    assert(native_list_request(1,1,180,96,1));model(0,0,0);expected("empty");image("empty");
    struct NXSRectD unknown;check("unknown-row-has-no-native-rectangle",!native_list_item_rect(1,UINT64_MAX,&unknown));
    check("invalid-scroll-rejected",!native_list_scroll(1,NAN,0));
    assert(native_list_request(1,6,0,0,1));check("destroy-retires-owned-list",!native_list_state(1,&(struct NXSListWireState){0},&(const uint64_t *){0}));check("late-model-does-not-recreate-retired-list",!native_list_model(1,NULL,0,0,0,scale));
  }
  close(channel);printf("{\"passed\":%u,\"images\":%u}\n",checks,images);return 0;
}
