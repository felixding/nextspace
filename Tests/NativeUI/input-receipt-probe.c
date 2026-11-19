/* Recover actual native operations without replay or duplicate UI. GPL-2.0-or-later. */
#define _GNU_SOURCE
#include "NativeUI.h"
#include "Bridge/Protocol.h"
#include <assert.h>
#include <stdio.h>
#include <sys/eventfd.h>
static void note(const char *message){fprintf(stderr,"%s\n",message);}
#ifndef NXS_TEST_TRANSPORT
#define NXS_TEST_TRANSPORT "Bridge/Transport.inc"
#endif
#include NXS_TEST_TRANSPORT
#ifdef NXS_TEST_OLD_TRANSPORT
static int native_presentation_uncertain(uint32_t kind,uint64_t control,uint32_t operation){return 0;}
#endif
#include "Bridge/Specialized.inc"
#include "Bridge/ColorBinding.inc"
#include "Bridge/ColorOwners.inc"
#include "Bridge/PopupBinding.inc"
static const char *faults;
static unsigned checks;
static void check(const char *name,int passed)
{printf("{\"case\":\"%s\",\"passed\":%s}\n",name,passed?"true":"false");fflush(stdout);assert(passed);checks++;}
static void drop(unsigned operation)
{char path[1024];snprintf(path,sizeof(path),"%s/drop-next-native-reply-%u",faults,operation);FILE *f=fopen(path,"wx");assert(f);fclose(f);}
static struct NXSResponse *request(unsigned kind,uint64_t control,unsigned operation)
{
  struct NXSControlRequest r={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,
    .process=identity(),.kind=kind,.control=control,.width=100,.height=24,.maximum=1,.enabled=1};
  return exchange_bytes(&r,sizeof(r));
}
static void released(void)
{
  struct NXSControlRequest r={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=4,
    .process=identity(),.kind=NXS_BUTTON,.control=1,.x=-10000,.y=-10000};
  r.operation=3;exchange_bytes(&r,sizeof(r));r.operation=4;
  struct NXSResponse *result=exchange_bytes(&r,sizeof(r));
  for(unsigned i=0;result&&result->parts[0].y&&i<500;i++){usleep(2000);result=request(NXS_BUTTON,1,5);}
  if(result)fprintf(stderr,"cancelled native press: tracking=%.0f actions=%.0f\n",result->parts[0].y,result->parts[0].width);
  check("native-press-releases-without-action",result&&!result->parts[0].y&&!result->parts[0].width);
}
int main(int argc,char **argv)
{
  assert((argc==3||argc==4)&&bridge_connect(argv[1]));faults=argv[2];
  int notifier=eventfd(0,EFD_CLOEXEC|EFD_NONBLOCK);assert(notifier>=0);
  struct NXSControlRequest owner={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=15,.process=identity()};
  struct NXSResponse *r=exchange_bytes_descriptor(&owner,sizeof(owner),notifier);assert(r&&r->parts[3].x==1);
  if(argc==4){assert(!strcmp(argv[3],"--press-only"));goto presses;}
  r=request(NXS_COLORWELL,2,1);assert(r&&r->parts[2].x);
  NXSColorModel color={.size=sizeof(color),.red=.25,.green=.5,.blue=.75,.alpha=1};
  struct NXSColorBinding binding={0};
  drop(59);
  check("lost-native-open-reply-retains-original-picker",native_color_binding_open(&binding,2,&color)&&binding.open);
  int open=0;NXSColorModel selected;
  check("recovered-native-picker-remains-active",native_color_binding_poll(&binding,&selected,&open)==0&&open);
  native_color_binding_end(&binding);
  drop(59);drop(66);
  check("lost-open-and-receipt-never-authorize-browser-fallback",native_color_binding_open(&binding,2,&color)&&binding.open);
  check("uncertain-picker-recovers-through-native-state",native_color_binding_poll(&binding,&selected,&open)==0&&open);
  native_color_binding_end(&binding);
  assert(native_color_owner(2,42,60,2));drop(59);
  check("borrowed-picker-recovers-source-owned-receipt",native_color_binding_borrow(&binding,9,42)&&binding.borrowed);
  check("borrowed-native-picker-remains-active",native_color_binding_poll(&binding,&selected,&open)==0&&open);
  native_color_binding_return(&binding);assert(native_color_owner(2,42,67,0));
  r=request(NXS_DATEPICKER,3,1);assert(r&&r->parts[2].x);
  NXSDateModel date={.size=sizeof(date),.elements=NXS_DATE_YEAR_MONTH_DAY,
    .flags=NXS_DATE_UTC|NXS_DATE_ALLOW_EMPTY,.value=1794009600};
  assert(native_date_sync(3,&date)&&native_popup_binding_origin(NXS_DATEPICKER,3,300,240));
  struct NXSPopupBinding popup={0};drop(14);
  check("lost-calendar-open-reply-retains-original-panel",native_popup_binding_open(&popup,NXS_DATEPICKER,3));
  check("recovered-calendar-native-state-is-readable",native_popup_binding_poll(&popup)>=0);native_popup_binding_end(&popup);
  drop(14);drop(66);
  check("uncertain-calendar-open-never-starts-second-picker",native_popup_binding_open(&popup,NXS_DATEPICKER,3));
  /* This protocol fixture has no browser seat/activation grant. AppKit may
   * close its panel; reading that original state must not run Open again. */
  check("uncertain-calendar-native-state-is-readable",native_popup_binding_poll(&popup)>=0);native_popup_binding_end(&popup);
presses:
  r=request(NXS_BUTTON,1,1);assert(r&&r->parts[2].x);
  struct NXSControlRequest press={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=2,
    .process=identity(),.kind=NXS_BUTTON,.control=1,.x=5,.y=5};
  drop(2);r=exchange_bytes(&press,sizeof(press));uint32_t old_press=press.reserved;
  check("lost-native-press-reply-recovers-tracking-owner",r&&r->parts[3].height==1&&r->parts[0].y);released();
  drop(2);drop(66);r=exchange_bytes(&press,sizeof(press));
  check("unknown-press-is-not-replayed",!r);
  r=request(NXS_BUTTON,1,5);
  for(unsigned i=0;r&&r->parts[0].y&&i<500;i++){usleep(2000);r=request(NXS_BUTTON,1,5);}
  check("unknown-press-cancels-native-tracking-without-action",r&&!r->parts[0].y&&!r->parts[0].width);
  r=exchange_bytes(&press,sizeof(press));assert(r&&r->parts[0].y);
  struct NXSControlRequest stale={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=68,
    .process=identity(),.kind=NXS_BUTTON,.control=1,.value=old_press};
  r=exchange_bytes(&stale,sizeof(stale));
  check("old-cancellation-preserves-a-newer-native-press",r&&!r->parts[3].x&&r->parts[0].y);released();
  printf("{\"passed\":%u}\n",checks);close(notifier);return 0;
}
