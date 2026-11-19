/* A native action arriving between transport replies must not be lost.
 * Exercises the production bridge with deterministic response-boundary input.
 * No colour control or browser behaviour is implemented here. GPL-2.0-or-later. */
#include "NativeUI.h"
#include "Bridge/Protocol.h"
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static _Atomic uint32_t native_host_epoch=1;
static uint32_t identity(void){return 1;}
static struct {struct NXSResponse reply;NXSColorModel model;} packet;
static NXSColorModel color;
static double actions,model_actions;
static int inject_after_snapshot,bad_payload;
/* This snapshot-only fixture always returns a synchronous transport reply. */
static int native_presentation_uncertain(unsigned kind,uint64_t control,unsigned operation)
{(void)kind;(void)control;(void)operation;return 0;}
static struct NXSResponse *exchange_bytes(void *data,size_t size)
{
  const struct NXSControlRequest *request=data;(void)size;
  memset(&packet,0,sizeof(packet));packet.reply.size=sizeof(packet.reply);
  packet.reply.parts[3].x=1;packet.reply.parts[0].height=1;
  packet.reply.parts[0].width=actions;packet.reply.parts[2].height=model_actions;
  if(request->operation==56) {
    packet.model=color;
    if(!bad_payload)packet.reply.size+=sizeof(packet.model);
  }
  /* One user action occurs after the complete response has been sampled.
   * Two separate reads can combine its colour with an older action count. */
  if(inject_after_snapshot&&(request->operation==0||request->operation==56)) {
    inject_after_snapshot=0;actions++;
    color=(NXSColorModel){.size=sizeof(color),.alpha=1};
  }
  return &packet.reply;
}
#include "Bridge/Specialized.inc"
#ifndef NXS_TEST_COLOR_BINDING
#define NXS_TEST_COLOR_BINDING "Bridge/ColorBinding.inc"
#endif
#include NXS_TEST_COLOR_BINDING
static unsigned checks;
static void check(const char *name,int passed)
{
  printf("{\"case\":\"%s\",\"passed\":%s}\n",name,passed?"true":"false");fflush(stdout);
  if(!passed)exit(1);checks++;
}
static struct NXSColorBinding initial(void)
{
  color=(NXSColorModel){.size=sizeof(color),.red=.25,.green=.5,.blue=.75,.alpha=1};
  actions=model_actions=0;inject_after_snapshot=bad_payload=0;atomic_store(&native_host_epoch,1);
  return (struct NXSColorBinding){.control=1,.epoch=1,.token=1,.color=color,.open=1};
}
int main(void)
{
  struct NXSColorBinding binding=initial();NXSColorModel selected;int open=0;
  inject_after_snapshot=1;
  check("event-after-snapshot-is-not-reported-early",native_color_binding_poll(&binding,&selected,&open)==0&&open);
  check("later-native-black-selection-is-delivered",native_color_binding_poll(&binding,&selected,&open)==1&&selected.red==0&&selected.green==0&&selected.blue==0&&selected.alpha==1);
  check("native-selection-is-delivered-once",native_color_binding_poll(&binding,&selected,&open)==0);
  binding=initial();color=(NXSColorModel){.size=sizeof(color),.alpha=1};actions=1;
  check("native-change-before-snapshot-is-delivered",native_color_binding_poll(&binding,&selected,&open)==1);
  color=(NXSColorModel){.size=sizeof(color),.red=.5,.alpha=1};model_actions=actions=2;
  check("application-model-echo-is-not-native-input",native_color_binding_poll(&binding,&selected,&open)==0);
  color=(NXSColorModel){.size=sizeof(color),.alpha=1};actions=3;
  check("native-input-after-model-echo-is-delivered",native_color_binding_poll(&binding,&selected,&open)==1);
  bad_payload=1;
  check("incomplete-model-snapshot-is-rejected",native_color_binding_poll(&binding,&selected,&open)<0);
  bad_payload=0;atomic_store(&native_host_epoch,2);
  check("replaced-host-snapshot-is-rejected",native_color_binding_poll(&binding,&selected,&open)<0);
  binding.open=0;
  check("retired-session-cannot-poll",native_color_binding_poll(&binding,&selected,&open)<0);
  printf("{\"passed\":%u}\n",checks);return 0;
}
