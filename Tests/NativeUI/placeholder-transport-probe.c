/* Shared placeholder model RPC, with original native desktop image witnesses.
 * GPL-2.0-or-later. */
#define _GNU_SOURCE
#include "NativeUI.h"
#include "Bridge/Protocol.h"
#include <assert.h>
#include <stdio.h>
static void note(const char *message){fprintf(stderr,"%s\n",message);}
#include "Bridge/Transport.inc"
#include "Bridge/TextPlaceholder.inc"
static unsigned checks,images;
static void check(const char *name,int passed)
{printf("{\"case\":\"%s\",\"passed\":%s}\n",name,passed?"true":"false");fflush(stdout);assert(passed);checks++;}
static struct NXSResponse *request(unsigned operation,int kind,int enabled)
{
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,.process=identity(),
    .kind=kind,.control=1,.width=260,.height=24,.enabled=enabled};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));assert(response);return response;
}
static int raw_placeholder(int kind,int state,const void *text,size_t length)
{
  size_t size=sizeof(struct NXSControlRequest)+length;struct NXSControlRequest *p=calloc(1,size);assert(p);
  *p=(struct NXSControlRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=54,.process=identity(),.kind=kind,.control=1,.state=state,.text_size=length};
  if(length)memcpy(p+1,text,length);struct NXSResponse *r=exchange_bytes(p,size);free(p);assert(r);return r->parts[3].x==1;
}
int main(int argc,char **argv)
{
  assert(argc>3&&bridge_connect(argv[1]));
  int old=argc>4&&!strcmp(argv[4],"--expect-no-placeholder");double density=atof(argv[3]);
  for(int kind=7;kind<=14;kind++) {
    if(kind!=7&&kind!=8&&kind!=14)continue;
    request(1,kind,1);
    if(old){check("older-provider-rejects-placeholder",!native_text_placeholder(kind,1,"Unsupported"));request(6,kind,1);continue;}
    struct {const char *label,*placeholder,*value;int enabled,editable;} cases[]={
      {"ascii","Find a word","",1,1},{"unicode","検索α","",1,1},
      {"value","Hidden while populated","Existing",1,1},{"empty","","",1,1},
      {"removed",NULL,"",1,1},{"disabled","Unavailable","",0,1},
      {"readonly","Read only hint","",1,0},{"restored","Restored hint","",1,1}};
    for(unsigned i=0;i<sizeof(cases)/sizeof(*cases);i++) {
      request(1,kind,cases[i].enabled);
      size_t length=strlen(cases[i].value),size=sizeof(struct NXSControlTextRequest)+length;
      struct NXSControlTextRequest *p=calloc(1,size);assert(p);
      *p=(struct NXSControlTextRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=17,.process=identity(),.kind=kind,.control=1,.text_size=length,.editable=cases[i].editable};
      memcpy(p+1,cases[i].value,length);struct NXSResponse *r=exchange_bytes(p,size);free(p);assert(r&&r->parts[3].x==1);
      check("owned-placeholder-accepted",native_text_placeholder(kind,1,cases[i].placeholder));
      check("malformed-placeholder-rejected",!raw_placeholder(kind,2,"Wrong",5)&&!raw_placeholder(kind,0,"Wrong",5)&&!raw_placeholder(kind,1,"\xff",1)&&!raw_placeholder(kind,1,"A\0B",3));
      r=request(18,kind,cases[i].enabled);assert(r->parts[3].x==1);
      struct NXSTextResponse state;memcpy(&state,r+1,sizeof(state));
      check("placeholder-preserves-canonical-text-state",state.text_size==length&&!memcmp((char *)(r+1)+sizeof(state),cases[i].value,length)&&!state.selection_start&&!state.selection_length&&!!(state.flags&2)==cases[i].editable);
      r=request(5,kind,cases[i].enabled);assert(r->width==260*density&&r->height==24*density&&r->size==sizeof(*r)+r->stride*r->height);
      char name[64],path[1024];snprintf(name,sizeof(name),"kind-%d-%s",kind,cases[i].label);snprintf(path,sizeof(path),"%s/%s.argb",argv[2],name);
      FILE *out=fopen(path,"wb");assert(out&&fwrite(r+1,r->stride,r->height,out)==(size_t)r->height);fclose(out);
      printf("{\"event\":\"image\",\"name\":\"%s\",\"reference\":\"%s\",\"width\":%d,\"height\":%d,\"stride\":%d}\n",name,name,r->width,r->height,r->stride);images++;
    }
    int foreign=socket(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0);assert(foreign>=0);
    struct sockaddr_un address={.sun_family=AF_UNIX};assert(strlen(argv[1])<sizeof(address.sun_path));strcpy(address.sun_path,argv[1]);assert(!connect(foreign,(void *)&address,sizeof(address)));
    struct NXSControlRequest denied={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=54,.process=identity(),.kind=kind,.control=1};
    assert(send(foreign,&denied,sizeof(denied),MSG_NOSIGNAL)==sizeof(denied));struct NXSResponse response;
    assert(recv(foreign,&response,sizeof(response),0)==sizeof(response));check("foreign-connection-cannot-change-placeholder",response.parts[3].x==0);close(foreign);
    request(6,kind,1);check("retired-control-rejects-placeholder",!native_text_placeholder(kind,1,"Retired"));
  }
  request(1,NXS_TEXTAREA,1);check("multiline-rejects-placeholder",!native_text_placeholder(NXS_TEXTAREA,1,"Unsupported"));request(6,NXS_TEXTAREA,1);
  printf("{\"passed\":%u,\"images\":%u}\n",checks,images);return 0;
}
