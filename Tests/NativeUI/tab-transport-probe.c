/* Exercise the shared native tab wire contract with the browser C transport.
 * Fixture data only; AppKit owns tab geometry, drawing and pointer behavior. */
#define _GNU_SOURCE
#include "NativeUI.h"
#include "Bridge/Protocol.h"
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include <math.h>
static void note(const char *message){fprintf(stderr,"%s\n",message);}
#include "Bridge/Transport.inc"
#include "Bridge/Tabs.inc"
_Static_assert(sizeof(struct NXSControlTabsRequest)==56,"Tab model wire ABI");
_Static_assert(offsetof(struct NXSControlTabsRequest,count)==32,"Tab count offset");
_Static_assert(offsetof(struct NXSControlTabsRequest,selected)==40,"Tab identity offset");
_Static_assert(sizeof(struct NXSControlTabItemRequest)==40,"Tab geometry wire ABI");
_Static_assert(offsetof(struct NXSControlTabItemRequest,identifier)==32,"Tab item offset");
_Static_assert(sizeof(struct NXSTabWireState)==48,"Tab state wire ABI");
static const uint64_t large_id=UINT64_C(0xf123456789abcdef);
static unsigned checks,images;
static const char *directory;
static struct NXSResponse *request(unsigned op,double width,double height,int enabled)
{
  struct NXSControlRequest req={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=op,.process=identity(),
    .kind=NXS_TABVIEW,.control=1,.width=width,.height=height,.enabled=enabled};
  struct NXSResponse *r=exchange_bytes(&req,sizeof(req));assert(r);return r;
}
static void check(const char *name,int passed)
{printf("{\"case\":\"%s\",\"passed\":%s}\n",name,passed?"true":"false");assert(passed);checks++;}
static struct NXSTabWireState state(void)
{
  struct NXSResponse *r=request(37,0,0,1);
  assert(r->parts[3].x==1&&r->size==sizeof(*r)+sizeof(struct NXSTabWireState));
  struct NXSTabWireState value;memcpy(&value,r+1,sizeof(value));return value;
}
/* bad: duplicate identity, invalid UTF8, missing selection, malformed length. */
static struct NXSResponse *model(int reordered,int empty,uint64_t selected,double scale,int bad)
{
  const char *labels[]={"One","One","日本語"},*tips[]={"First page","",""};
  const uint64_t identifiers[]={1,2,large_id};unsigned count=empty?0:3;
  unsigned char bytes[1024] __attribute__((aligned(8)))={0};size_t used=sizeof(struct NXSControlTabsRequest);
  for(unsigned i=0;i<count;i++) {
    unsigned index=reordered?(i+2)%3:i;
    const char *label=bad==2&&i==2?"\xff":reordered&&index==0?"Renamed":labels[index];
    struct NXSTabWireItem item={.identifier=bad==1&&i==1?1:identifiers[index],.title_size=strlen(label),.tooltip_size=strlen(tips[index])};
    memcpy(bytes+used,&item,sizeof(item));used+=sizeof(item);
    memcpy(bytes+used,label,item.title_size);used+=item.title_size;
    memcpy(bytes+used,tips[index],item.tooltip_size);used+=item.tooltip_size;
  }
  struct NXSControlTabsRequest *req=(void *)bytes;
  *req=(struct NXSControlTabsRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=36,.process=identity(),
    .kind=NXS_TABVIEW,.control=1,.text_size=used-sizeof(*req),.count=count,.selected=bad==3?42:selected,.scale=scale};
  if(bad==4)req->count++;
  struct NXSResponse *r=exchange_bytes(req,used);assert(r);return r;
}
static struct NXSRectD item(uint64_t identifier)
{
  struct NXSControlTabItemRequest req={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=38,.process=identity(),
    .kind=NXS_TABVIEW,.control=1,.identifier=identifier};
  struct NXSResponse *r=exchange_bytes(&req,sizeof(req));assert(r&&r->parts[3].x==1);return r->parts[6];
}
static void image(struct NXSResponse *r,const char *name,int width,int height)
{
  assert(r->width==width&&r->height==height&&r->stride>=4*width&&r->size==sizeof(*r)+r->stride*height);
  char path[1024];snprintf(path,sizeof(path),"%s/%s.argb",directory,name);FILE *out=fopen(path,"wb");assert(out);
  assert(fwrite(r+1,r->stride,r->height,out)==(size_t)r->height);assert(!fclose(out));
  printf("{\"event\":\"image\",\"name\":\"%s\",\"width\":%d,\"height\":%d,\"stride\":%d}\n",name,width,height,r->stride);images++;
}
static void click(uint64_t identifier,int accepted)
{
  struct NXSRectD rect=item(identifier);assert(rect.width>0&&rect.height>0);
  struct NXSControlRequest req={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=22,.process=identity(),
    .kind=NXS_TABVIEW,.control=1,.x=rect.x+rect.width/2,.y=rect.y+rect.height/2,.state=1};
  struct NXSResponse *r=exchange_bytes(&req,sizeof(req));assert(r&&r->parts[3].x==accepted);
  if(accepted) {
    for(unsigned i=0;i<100&&state().selected!=identifier;i++)usleep(10000);
    assert(state().selected==identifier);
  }
}
static void foreign_connection(const char *path,unsigned operation)
{
  int peer=socket(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0);assert(peer>=0);
  struct timeval timeout={.tv_sec=3};assert(!setsockopt(peer,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout)));
  struct sockaddr_un address={.sun_family=AF_UNIX};assert(strlen(path)<sizeof(address.sun_path));strcpy(address.sun_path,path);
  assert(!connect(peer,(void *)&address,sizeof(address)));
  struct NXSControlRequest req={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,.process=identity(),.kind=NXS_TABVIEW,.control=1};
  assert(send(peer,&req,sizeof(req),MSG_NOSIGNAL)==sizeof(req));struct NXSResponse r;
  assert(recv(peer,&r,sizeof(r),0)==sizeof(r)&&r.parts[3].x==0&&r.parts[0].width==0&&r.parts[5].y==0);close(peer);
}
int main(int argc,char **argv)
{
  assert(argc>=3);directory=argv[2];setvbuf(stdout,NULL,_IOLBF,0);assert(bridge_connect(argv[1]));
  struct NXSRequest bootstrap={.magic=NXS_CHROMIUM_MAGIC,.operation=7};
  struct NXSResponse *r=exchange(bootstrap);assert(r);unsigned caps=r->parts[4].x;
  if(argc>3&&!strcmp(argv[3],"--expect-no-tabs")) {
    check("previous-provider-reports-tabs-unsupported",caps==0);
    r=request(1,400,100,1);check("previous-provider-rejects-tab-creation",!r->width&&!r->height);
  } else {
    check("native-tab-capability-crosses-IPC",caps==NXS_TAB_ITEMS);
    r=request(1,400,100,1);check("native-tab-creation",r->width==400&&r->height==100&&r->parts[2].y==NXS_TAB_ITEMS);
    NXSTabItem shared_items[]={{sizeof(NXSTabItem),1,"One","First page"},{sizeof(NXSTabItem),2,"One",NULL},{sizeof(NXSTabItem),large_id,"日本語",NULL}};
    r=native_tabs_model(1,shared_items,3,large_id,1);
    struct NXSTabWireState shared_state;struct NXSRectD shared_rect;
    check("shared-application-model-serializer",r&&native_tabs_state(1,&shared_state)&&shared_state.selected==large_id&&shared_state.count==3);
    check("shared-native-item-geometry-query",native_tabs_item_rect(1,large_id,&shared_rect)&&shared_rect.width>0);
    check("shared-serializer-preserves-state-on-rejection",!native_tabs_model(1,shared_items,3,42,1)&&native_tabs_state(1,&shared_state)&&shared_state.selected==large_id);
    for(int scale=1;scale<=2;scale++) {
      r=request(1,400,100,1);assert(r->width==400*(scale==1?1:2));
      r=model(0,0,1,scale,0);assert(r->parts[3].x==1);image(r,scale==1?"initial-1":"initial-2",400*scale,100*scale);
      struct NXSTabWireState s=state();check("native-model-content-and-selection",s.count==3&&s.selected==1&&s.selected_index==0&&s.content.width>0);
      struct NXSRectD rect=item(large_id);check("64-bit-item-native-geometry",rect.width>0&&rect.height>0);
      unsigned actions=request(5,0,0,1)->parts[0].width;
      click(large_id,1);check("native-pointer-selects-64-bit-identity",state().selected==large_id&&state().selected_index==2&&request(5,0,0,1)->parts[0].width==actions+1);
      image(request(5,0,0,1),scale==1?"selected-1":"selected-2",400*scale,100*scale);
      click(large_id,1);check("repeat-selected-click-has-no-action",request(5,0,0,1)->parts[0].width==actions+1);
      for(int bad=1;bad<=4;bad++) {
        check("invalid-tab-model-rejected",model(0,0,1,scale,bad)->parts[3].x==0);
        check("invalid-model-preserves-live-selection",state().selected==large_id&&state().count==3);
      }
      double invalid[]={0,9,NAN,INFINITY};
      for(unsigned i=0;i<sizeof(invalid)/sizeof(*invalid);i++)check("invalid-density-rejected",model(0,0,1,invalid[i],0)->parts[3].x==0&&state().selected==large_id);
      foreign_connection(argv[1],37);foreign_connection(argv[1],6);
      check("other-connection-cannot-read-or-destroy",state().selected==large_id);
      r=model(1,0,1,scale,0);assert(r->parts[3].x==1);image(r,scale==1?"reordered-1":"reordered-2",400*scale,100*scale);
      check("reordered-model-retains-native-selection",state().selected==1&&state().selected_index==1);
      r=request(1,180,80,1);image(r,scale==1?"resized-1":"resized-2",180*scale,80*scale);
      request(1,180,80,0);actions=request(5,0,0,0)->parts[0].width;click(2,0);
      check("disabled-native-input-refused",state().selected==1&&request(5,0,0,0)->parts[0].width==actions);
      request(1,180,80,1);r=model(0,1,0,scale,0);assert(r->parts[3].x==1);image(r,scale==1?"empty-1":"empty-2",180*scale,80*scale);
      check("empty-model-native-state",state().count==0&&state().selected_index==-1&&state().selected==0);
      for(unsigned i=0;i<30;i++){assert(model(0,0,large_id,scale,0)->parts[3].x==1);assert(model(0,1,0,scale,0)->parts[3].x==1);}
      check("repeated-empty-restore-through-IPC",state().count==0&&request(5,0,0,1)->parts[0].width==actions);
      check("scaled-oversized-configuration-rejected",!request(1,8192,8192,1)->width&&state().count==0);
      assert(model(0,0,1,2,0)->parts[3].x==1);
      struct NXSTabWireState before=state();
      r=request(1,2048,2048,1);
      check("physical-bitmap-bound-preserves-logical-geometry",!r->width&&state().content.width==before.content.width);
    }
    request(6,0,0,1);r=request(37,0,0,1);check("destroy-retires-transport-state",r->parts[3].x==0&&r->size==sizeof(*r));
    assert(model(0,0,1,1,0)->parts[3].x==0);
    check("late-model-cannot-recreate-destroyed-tab",!request(5,0,0,1)->width);
  }
  close(channel);printf("{\"passed\":%u,\"images\":%u}\n",checks,images);return 0;
}
