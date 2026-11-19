/* A successful native presentation survives an unavailable follow-up read.
 * The provider and real NSColorPanel remain unchanged. GPL-2.0-or-later. */
#define _GNU_SOURCE
#include "NativeUI.h"
#include "Bridge/Protocol.h"
#include <assert.h>
#include <stdio.h>
static void note(const char *message){fprintf(stderr,"%s\n",message);}
#include "Bridge/Transport.inc"
#include "Bridge/Specialized.inc"
static int status_unavailable;
static struct NXSResponse *with_status_outage(void *data,size_t size)
{
  const struct NXSControlRequest *request=data;
  if(status_unavailable&&request->magic==NXS_CHROMIUM_CONTROL_MAGIC&&request->operation==0) {
    errno=EAGAIN;return NULL;
  }
  return exchange_bytes(data,size);
}
#define exchange_bytes with_status_outage
#ifndef NXS_TEST_COLOR_BINDING
#define NXS_TEST_COLOR_BINDING "Bridge/ColorBinding.inc"
#endif
#include NXS_TEST_COLOR_BINDING
#undef exchange_bytes
static unsigned checks;
static void check(const char *name,int passed)
{printf("{\"case\":\"%s\",\"passed\":%s}\n",name,passed?"true":"false");fflush(stdout);if(!passed)exit(1);checks++;}
int main(int argc,char **argv)
{
  assert(argc==2&&bridge_connect(argv[1]));
  struct NXSControlRequest configure={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=1,
    .process=identity(),.kind=NXS_COLORWELL,.control=1,.width=80,.height=24,.maximum=1,.enabled=1};
  struct NXSResponse *r=exchange_bytes(&configure,sizeof(configure));
  check("real-native-well-configured",r&&r->width==80);
  struct NXSColorBinding binding={0};
  NXSColorModel model={.size=sizeof(model),.red=.25,.green=.5,.blue=.75,.alpha=1};
  status_unavailable=1;
  check("native-presentation-accepted-with-followup-read-unavailable",native_color_binding_open(&binding,1,&model));
  status_unavailable=0;
  int open=0;NXSColorModel selected;
  check("original-native-panel-remains-open",native_color_binding_poll(&binding,&selected,&open)==0&&open);
  native_color_binding_end(&binding);
  configure.operation=0;r=exchange_bytes(&configure,sizeof(configure));
  check("original-native-panel-closes-explicitly",r&&!r->parts[0].height&&!binding.open);
  printf("{\"passed\":%u}\n",checks);return 0;
}
