/* Typed specialized native models through the shared transport.
 * GPL-2.0-or-later. */
#define _GNU_SOURCE
#include "NativeUI.h"
#include "Bridge/Protocol.h"
#include <assert.h>
#include <stdio.h>
#include <math.h>
static void note(const char *message){fprintf(stderr,"%s\n",message);}
#include "Bridge/Transport.inc"
#include "Bridge/Specialized.inc"
_Static_assert(sizeof(struct NXSControlColorRequest)==64,"Color wire layout");
_Static_assert(sizeof(struct NXSControlDateRequest)==72,"Date wire layout");
static unsigned checks,images;
static void check(const char *name,int passed)
{printf("{\"case\":\"%s\",\"passed\":%s}\n",name,passed?"true":"false");fflush(stdout);assert(passed);checks++;}
static struct NXSResponse *request(unsigned operation,int kind,int enabled)
{
  struct NXSControlRequest req={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,.process=identity(),.kind=kind,.control=1,
    .width=kind==NXS_STEPPER?24:kind==NXS_COLORWELL?120:260,.height=kind==NXS_STEPPER?26:24,.minimum=-10,.maximum=10,.value=2,.enabled=enabled};
  struct NXSResponse *r=exchange_bytes(&req,sizeof(req));assert(r);return r;
}
static void image(int kind,const char *directory,const char *name)
{
  struct NXSResponse *r=request(5,kind,1);assert(r->width>0&&r->height>0&&r->stride==r->width*4&&r->size==sizeof(*r)+r->stride*r->height);
  char path[1024];snprintf(path,sizeof(path),"%s/%s.argb",directory,name);FILE *out=fopen(path,"wb");assert(out&&fwrite(r+1,r->stride,r->height,out)==(size_t)r->height);fclose(out);
  printf("{\"event\":\"image\",\"name\":\"%s\",\"reference\":\"%s\",\"width\":%d,\"height\":%d,\"stride\":%d}\n",name,name,r->width,r->height,r->stride);images++;
}
static void foreign(const char *path,int kind,unsigned operation)
{
  int fd=socket(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0);assert(fd>=0);struct sockaddr_un addr={.sun_family=AF_UNIX};assert(strlen(path)<sizeof(addr.sun_path));strcpy(addr.sun_path,path);assert(!connect(fd,(void *)&addr,sizeof(addr)));
  struct NXSControlRequest req={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,.process=identity(),.kind=kind,.control=1};
  assert(send(fd,&req,sizeof(req),MSG_NOSIGNAL)==sizeof(req));struct NXSResponse r;assert(recv(fd,&r,sizeof(r),0)==sizeof(r));
  check("foreign-connection-cannot-read-owned-model",r.parts[3].x==0&&r.size==sizeof(r));close(fd);
}
int main(int argc,char **argv)
{
  assert(argc>3&&bridge_connect(argv[1]));int old=argc>4&&!strcmp(argv[4],"--expect-no-specialized");
  if(old) {
    for(int kind=NXS_STEPPER;kind<=NXS_DATEPICKER;kind++){struct NXSResponse *r=request(1,kind,1);check("older-provider-rejects-specialized-kind",!r->width&&!r->height);}
    puts("{\"images\":0}");return 0;
  }
  check("native-stepper-configured",request(1,NXS_STEPPER,1)->width==24);
  struct NXSControlStepRequest step={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=10,.process=identity(),.kind=NXS_STEPPER,.control=1,.step=.5};
  struct NXSResponse *r=exchange_bytes(&step,sizeof(step));check("native-stepper-increment",r&&r->parts[5].x==.5);
  image(NXS_STEPPER,argv[2],"stepper");request(1,NXS_STEPPER,0);image(NXS_STEPPER,argv[2],"stepper-disabled");request(6,NXS_STEPPER,1);
  request(1,NXS_COLORWELL,1);
  NXSColorModel colors[]={{sizeof(NXSColorModel),1,0,0,1},{sizeof(NXSColorModel),.25,.5,.75,.5},{sizeof(NXSColorModel),0,1,0,1}};
  for(unsigned i=0;i<3;i++) {
    if(i==2)request(1,NXS_COLORWELL,0);
    check("owned-native-color-model",native_color_sync(1,&colors[i]));
    NXSColorModel actual={.size=sizeof(actual)};assert(native_color_get(1,&actual));
    check("native-color-readback",fabs(actual.red-colors[i].red)<.000001&&fabs(actual.green-colors[i].green)<.000001&&fabs(actual.blue-colors[i].blue)<.000001&&fabs(actual.alpha-colors[i].alpha)<.000001);
    NXSColorModel invalid=colors[i];invalid.blue=NAN;check("invalid-color-rejected",!native_color_sync(1,&invalid));
    char name[32];snprintf(name,sizeof(name),"color-%u",i);image(NXS_COLORWELL,argv[2],name);
  }
  request(1,NXS_COLORWELL,1);
  struct NXSControlRequest pointer={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=2,.process=identity(),.kind=NXS_COLORWELL,.control=1,.x=60,.y=12};
  r=exchange_bytes(&pointer,sizeof(pointer));assert(r);check("native-color-pointer-keeps-owned-tracking",request(5,NXS_COLORWELL,1)->parts[0].y==1&&!native_color_sync(1,&colors[0]));
  pointer.operation=4;r=exchange_bytes(&pointer,sizeof(pointer));check("native-color-release-opens-original-panel",r&&!r->parts[0].y&&r->parts[0].height==1);
  r=native_control_perform_click(NXS_COLORWELL,1,0);check("native-color-semantic-action-uses-existing-transport",r&&r->parts[0].height==0);
  pointer.operation=2;r=exchange_bytes(&pointer,sizeof(pointer));assert(r);
  pointer.operation=4;pointer.x=pointer.y=-1;r=exchange_bytes(&pointer,sizeof(pointer));check("native-outside-release-cancels-panel-activation",r&&!r->parts[0].y&&!r->parts[0].height);
  foreign(argv[1],NXS_COLORWELL,56);request(6,NXS_COLORWELL,1);check("retired-color-owner-rejected",!native_color_sync(1,&colors[0]));
  request(1,NXS_DATEPICKER,1);
  for(unsigned i=1;i<=7;i++) {
    NXSDateModel m={.size=sizeof(m),.flags=7,.elements=i>5?NXS_DATE_YEAR_MONTH_DAY:i,.style=i==6?NXS_DATE_CALENDAR:i==7?NXS_DATE_TEXT:0,.value=1700000000,.minimum=1600000000,.maximum=1800000000};
    check("owned-native-date-model",native_date_sync(1,&m));NXSDateModel actual={.size=sizeof(actual)};assert(native_date_get(1,&actual));
    check("native-date-readback",actual.flags==m.flags&&actual.elements==m.elements&&actual.style==m.style&&actual.value==m.value&&actual.minimum==m.minimum&&actual.maximum==m.maximum);
    NXSDateModel invalid=m;invalid.style=3;check("invalid-date-style-rejected",!native_date_sync(1,&invalid));
    char name[32];snprintf(name,sizeof(name),"date-%u",i);image(NXS_DATEPICKER,argv[2],name);
  }
  foreign(argv[1],NXS_DATEPICKER,58);request(6,NXS_DATEPICKER,1);
  NXSDateModel missing={.size=sizeof(missing),.elements=NXS_DATE_YEAR_MONTH_DAY};check("retired-date-owner-rejected",!native_date_sync(1,&missing));
  printf("{\"passed\":%u,\"images\":%u}\n",checks,images);return 0;
}
