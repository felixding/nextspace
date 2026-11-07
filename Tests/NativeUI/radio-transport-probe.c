/* Native group model/input/pixel transport. No widget implementation. */
#define _GNU_SOURCE
#include "NativeUI.h"
#include "Bridge/Protocol.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
static void note(const char *message){fprintf(stderr,"%s\n",message);}
#include "Bridge/Transport.inc"
#include "Bridge/Radios.inc"
_Static_assert(sizeof(struct NXSControlRadioRequest)==64,"Radio model wire ABI");
_Static_assert(sizeof(struct NXSControlRadioItemRequest)==56,"Radio item wire ABI");
_Static_assert(sizeof(struct NXSRadioWireState)==40,"Radio state wire ABI");
static unsigned checks,images;static double scale;static const char *directory;
static uint64_t id(unsigned index){return UINT64_C(0x1000000000000001)+index;}
static NXSRadioItem items[4];
static void check(const char *name,int passed)
{printf("{\"case\":\"%s\",\"passed\":%s}\n",name,passed?"true":"false");fflush(stdout);assert(passed);checks++;}
static struct NXSRadioWireState state(void)
{struct NXSRadioWireState result;assert(native_radio_state(1,&result));return result;}
static void expect(const char *name,uint64_t selected,uint64_t key,uint64_t actions)
{struct NXSRadioWireState s=state();check(name,s.selected==selected&&s.key_cell==key&&s.actions==actions);}
static struct NXSResponse *model(unsigned columns,uint64_t selected,uint64_t key)
{
  struct NXSResponse *r=native_radio_model(1,items,4,columns,selected,key,scale);assert(r);
  struct NXSRadioWireState snapshot;assert(native_radio_response_state(r,&snapshot));
  return native_radio_request(1,1,columns==4?432:columns==2?216:180,columns==4?24:columns==2?49:99,1);
}
static void image(struct NXSResponse *r,const char *name,const char *reference,int member)
{
  assert(r&&r->width>0&&r->height>0&&r->stride>=4*r->width&&r->size==sizeof(*r)+r->stride*r->height);
  char path[1024];snprintf(path,sizeof(path),"%s/%s.argb",directory,name);FILE *out=fopen(path,"wb");assert(out);
  assert(fwrite(r+1,r->stride,r->height,out)==(size_t)r->height);fclose(out);
  printf("{\"event\":\"image\",\"name\":\"%s\",\"reference\":\"%s\",\"member\":%d,\"width\":%d,\"height\":%d,\"stride\":%d,\"crop\":[%g,%g,%g,%g]}\n",
    name,reference,member,r->width,r->height,r->stride,r->parts[6].x,r->parts[6].y,r->parts[6].width,r->parts[6].height);images++;
}
static struct NXSRadioWireState key(unsigned logical,const char *text,unsigned modifiers)
{
  NXSKeyEvent input={.size=sizeof(input),.type=NXS_KEY_DOWN,.key=logical,.text=text,.modifiers=modifiers};
  struct NXSResponse *r=native_radio_input(1,0,&input);struct NXSRadioWireState result;
  assert(native_radio_response_state(r,&result));input.type=NXS_KEY_UP;
  struct NXSRadioWireState after;assert(native_radio_response_state(native_radio_input(1,0,&input),&after));
  assert(after.actions==result.actions);return result;
}
static struct NXSResponse *pointer(unsigned operation,double x,double y)
{
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,
    .process=identity(),.kind=NXS_RADIOGROUP,.control=1,.x=x,.y=y,.state=1};
  return exchange_bytes(&request,sizeof(request));
}
static void click(uint64_t from,uint64_t to,uint64_t actions)
{
  struct NXSRectD start,end;assert(native_radio_item_rect(1,from,&start));
  if(to)assert(native_radio_item_rect(1,to,&end));else end=(struct NXSRectD){.x=-20,.y=-20};
  struct NXSResponse *r=pointer(22,start.x+start.width/2,start.y+start.height/2);assert(r&&r->parts[3].x==1);
  check("busy-native-model-rejected",!native_radio_model(1,items,4,1,id(0),id(0),scale));
  assert(pointer(3,end.x+end.width/2,end.y+end.height/2));
  assert(pointer(4,end.x+end.width/2,end.y+end.height/2));
  for(unsigned i=0;i<100&&state().actions!=actions;i++)usleep(10000);
  assert(state().actions==actions);
}
static struct NXSResponse *bad_model(unsigned bad)
{
  unsigned char bytes[1024] __attribute__((aligned(8)))={0};size_t used=sizeof(struct NXSControlRadioRequest);
  for(unsigned i=0;i<4;i++) {
    const char *title=bad==2&&i==0?"\xff":items[i].title;
    struct NXSRadioWireItem item={.identifier=bad==1&&i==1?items[0].identifier:items[i].identifier,
      .enabled=bad==5?2:items[i].enabled,.title_size=strlen(title)};
    memcpy(bytes+used,&item,sizeof(item));used+=sizeof(item);memcpy(bytes+used,title,item.title_size);used+=item.title_size;
  }
  struct NXSControlRadioRequest *request=(void *)bytes;
  *request=(struct NXSControlRadioRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=43,.process=identity(),
    .kind=NXS_RADIOGROUP,.control=1,.text_size=used-sizeof(*request),.count=bad==4?5:4,.columns=1,
    .selected=bad==3?UINT64_MAX:id(0),.key_cell=id(0),.scale=scale};
  return exchange_bytes(bytes,used);
}
static void foreign_connection(const char *path,unsigned operation)
{
  int peer=socket(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0);assert(peer>=0);
  struct timeval timeout={.tv_sec=3};assert(!setsockopt(peer,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout)));
  struct sockaddr_un address={.sun_family=AF_UNIX};assert(strlen(path)<sizeof(address.sun_path));strcpy(address.sun_path,path);
  assert(!connect(peer,(void *)&address,sizeof(address)));
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,
    .process=identity(),.kind=NXS_RADIOGROUP,.control=1,.width=180,.height=99,.enabled=1};
  assert(send(peer,&request,sizeof(request),MSG_NOSIGNAL)==sizeof(request));struct NXSResponse response;
  assert(recv(peer,&response,sizeof(response),0)==sizeof(response)&&response.parts[3].x==0&&response.width==0&&response.parts[0].width==0);close(peer);
}
int main(int argc,char **argv)
{
  assert(argc>=4);directory=argv[2];scale=atof(argv[3]);setvbuf(stdout,NULL,_IOLBF,0);assert(bridge_connect(argv[1]));
  struct NXSRequest bootstrap={.magic=NXS_CHROMIUM_MAGIC,.operation=7};struct NXSResponse *r=exchange(bootstrap);assert(r);
  unsigned capabilities=r->parts[4].y;
  if(argc>4&&!strcmp(argv[4],"--expect-no-radio")) {
    check("previous-provider-reports-no-radio-wire",capabilities==0);
    r=native_radio_request(1,1,180,99,1);check("previous-provider-rejects-group-creation",r&&!r->width&&!r->height);
  } else {
    check("native-radio-capability-crosses-IPC",capabilities==(NXS_RADIO_GROUP|NXS_RADIO_CELL_SIZE));
    const char *titles[]={"First","Disabled","Third","Fourth"};
    for(unsigned i=0;i<4;i++)items[i]=(NXSRadioItem){sizeof(NXSRadioItem),id(i),titles[i],i!=1};
    /* Creation uses the host's default density; the model request supplies
     * the application's requested raster density before comparisons. */
    r=native_radio_request(1,1,180,99,1);check("native-group-created",r&&r->width>0&&r->height>0);
    r=model(1,id(0),id(0));image(r,"unfocused","unfocused",0);
    if(scale>1) {
      r=native_radio_request(1,1,2048,2048,1);
      check("actual-density-backing-limit-rejects-large-config",r&&!r->width&&!r->height&&state().selected==id(0));
    }
    struct NXSRadioWireState focus;assert(native_radio_response_state(native_radio_input(1,1,NULL),&focus));
    expect("exact-native-initial-identity",id(0),id(0),0);
    image(native_radio_request(1,5,0,0,1),"focused","focused",0);
    struct NXSRadioWireState result=key(NXS_KEY_DOWN_ARROW,NULL,0);
    check("native-key-reply-carries-exact-target",result.selected==id(2)&&result.key_cell==id(2)&&result.actions==1);
    image(native_radio_request(1,5,0,0,1),"arrow-selected","arrow-selected",0);
    result=key(NXS_KEY_DOWN_ARROW,NULL,NXS_SHIFT);
    check("native-key-focus-separate-from-selection",result.selected==id(2)&&result.key_cell==id(3)&&result.actions==2);
    image(native_radio_request(1,5,0,0,1),"focus-separate","focus-separate",0);
    key(NXS_KEY_DOWN_ARROW,NULL,NXS_SHIFT);expect("native-boundary-sends-no-extra-action",id(2),id(3),2);
    key(NXS_KEY_TEXT," ",0);expect("native-space-selects-key-cell",id(3),id(3),3);
    image(native_radio_request(1,5,0,0,1),"space-selected","space-selected",0);
    for(unsigned bad=1;bad<=5;bad++) {
      r=bad_model(bad);check("invalid-radio-model-rejected",r&&r->parts[3].x==0);
      expect("invalid-model-preserves-native-state",id(3),id(3),3);
    }
    double invalid[]={0,9,NAN,INFINITY};
    for(unsigned i=0;i<4;i++)check("invalid-density-rejected",!native_radio_model(1,items,4,1,id(0),id(0),invalid[i]));
    foreign_connection(argv[1],44);foreign_connection(argv[1],1);foreign_connection(argv[1],6);
    expect("other-connection-cannot-read-change-destroy",id(3),id(3),3);
    model(1,id(0),id(0));click(id(2),id(2),4);expect("native-pointer-selects-member",id(2),id(2),4);
    image(native_radio_item_request(1,id(2),46),"member-selected","arrow-selected",1);
    click(id(1),id(1),5);expect("native-disabled-pointer-retains-selection-and-action",id(2),id(2),5);
    click(id(0),0,6);expect("native-outside-release-restores-selection",id(2),id(2),6);
    NXSRadioItem swap=items[0];items[0]=items[3];items[3]=swap;
    r=model(1,id(3),id(0));image(r,"reordered","reordered",0);
    items[0].title="日本語の選択";r=model(1,id(3),id(0));image(r,"unicode-title","unicode-title",0);
    r=native_radio_request(1,1,180,99,0);image(r,"disabled","disabled",0);
    check("disabled-native-key-refused",native_radio_input(1,0,&(NXSKeyEvent){.size=sizeof(NXSKeyEvent),.type=NXS_KEY_DOWN,.key=NXS_KEY_DOWN_ARROW})->parts[3].x==NXS_INPUT_UNHANDLED);
    assert(native_radio_input(1,0,NULL));assert(native_radio_request(1,1,180,99,1));
    model(1,id(3),id(0));
    assert(native_radio_input(1,1,NULL));
    image(native_radio_request(1,5,0,0,1),"re-enabled","unicode-title",0);
    model(1,0,id(2));expect("empty-selection-retains-native-key",0,id(2),6);
    image(native_radio_request(1,5,0,0,1),"empty-selection","empty-selection",0);
    model(4,id(0),id(0));image(native_radio_request(1,5,0,0,1),"horizontal","horizontal",0);
    model(2,id(0),id(0));image(native_radio_request(1,5,0,0,1),"grid","grid",0);
    model(1,id(3),id(0));assert(native_radio_input(1,0,NULL));
    struct NXSRadioWireState before=state();
    for(unsigned i=0;i<4;i++) {
      image(native_radio_item_draw(1,items[i].identifier,32,30),i==0?"cell-first":i==1?"cell-disabled":i==2?"cell-third":"cell-fourth","cell-bounds",1);
      struct NXSRadioWireState after=state();check("member-render-retains-native-state",!memcmp(&before,&after,sizeof(before)));
    }
    check("invalid-member-size-rejected",!native_radio_item_draw(1,id(2),NAN,16)&&!native_radio_item_draw(1,id(2),8192,8192));
    check("unknown-member-has-no-native-pixels",!native_radio_item_request(1,UINT64_MAX,46));
    check("empty-model-has-no-placeholders",native_radio_model(1,NULL,0,1,0,0,scale)&&state().count==0&&state().selected==0);
    for(unsigned i=0;i<20;i++) {
      assert(native_radio_model(1,items,4,1,id(3),id(0),scale));
      assert(native_radio_model(1,NULL,0,1,0,0,scale));
    }
    check("repeated-empty-restore-has-no-actions",state().actions==6);
    model(1,id(3),id(0));assert(native_radio_request(1,6,0,0,1));
    struct NXSRadioWireState retired;check("destroy-retires-native-state",!native_radio_state(1,&retired));
    check("late-model-cannot-recreate-retired-group",!native_radio_model(1,items,4,1,id(3),id(0),scale));
  }
  close(channel);printf("{\"passed\":%u,\"images\":%u}\n",checks,images);return 0;
}
