/* A model query can pump a different client's ordinary control activation. */
#import <AppKit/AppKit.h>
#include "NativeUI.h"
#include <assert.h>
#include <stdio.h>
struct Probe {NXSControl *color,*button;int queries,opened,clicked;};
static int command(void *context,uint64_t identifier,unsigned phase)
{
  struct Probe *probe=context;
  if(phase==NXS_COMMAND_VALIDATE) {
    probe->queries++;
    probe->opened=nxs_control_color_open(probe->color,1);
    if(probe->opened)assert(nxs_control_color_open(probe->color,0));
    probe->clicked=nxs_control_perform_click(probe->button,0);
  }
  return 1;
}
int main(void)
{
  setvbuf(stdout,NULL,_IOLBF,0);
  NSAutoreleasePool *pool=[NSAutoreleasePool new];struct Probe probe={0};
  NXSControlConfig config={.size=sizeof(config),.width=80,.height=24,.enabled=1};
  probe.color=nxs_control_create(NXS_COLORWELL,NULL,NULL,NULL);
  probe.button=nxs_control_create(NXS_BUTTON,NULL,NULL,NULL);
  assert(probe.color&&probe.button);
  assert(nxs_control_sync(probe.color,&config)&&nxs_control_sync(probe.button,&config));
  NXSMenu *menu=nxs_menu_create("Model query",command,NULL,&probe);assert(menu);
  NXSMenuItem item={.size=sizeof(item),.parent=-1,.command=1,.title="Availability"};
  assert(nxs_menu_items(menu,&item,1));
  nxs_menu_state(menu,0);
  printf("{\"queries\":%d,\"color_opened\":%d,\"button_clicked\":%d}\n",probe.queries,probe.opened,probe.clicked);
  assert(probe.queries&&probe.opened&&probe.clicked);
  assert(nxs_menu_destroy(menu));
  assert(nxs_control_destroy(probe.color)&&nxs_control_destroy(probe.button));
  [pool drain];return 0;
}
