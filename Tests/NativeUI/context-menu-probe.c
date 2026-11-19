/* Original NSMenu transient tracking through the shared provider. */
#include "NativeUI.h"
#include <assert.h>
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static NXSMenu *menu;static unsigned actions;static unsigned long long last;static int quit;
static int command(void *unused,uint64_t identifier,unsigned phase)
{(void)unused;if(phase==NXS_COMMAND_EXECUTE){actions++;last=identifier;}return identifier!=3;}
static void state(void)
{
 NXSMenuState s=nxs_menu_state(menu,-1);
 printf("{\"visible\":%d,\"tracking\":%d,\"frame\":[%g,%g,%g,%g],\"actions\":%u,\"last\":%llu}\n",s.visible,s.tracking,s.frame.x,s.frame.y,s.frame.width,s.frame.height,actions,last);fflush(stdout);
}
static void pump(void *unused)
{
 (void)unused;char b[128];struct pollfd f={0,POLLIN,0};
 if(poll(&f,1,0)>0&&fgets(b,sizeof(b),stdin)) {
  if(!strncmp(b,"escape",6)||!strncmp(b,"copy",4)) {
   int copy=!strncmp(b,"copy",4);
   NXSKeyEvent key={.size=sizeof(key),.type=NXS_KEY_DOWN,.key=copy?NXS_KEY_TEXT:NXS_KEY_ESCAPE,
    .modifiers=copy?NXS_ALT:0,.text=copy?"c":"",.unmodified_text=copy?"c":""};
   int handled=strstr(b,"query")?nxs_menu_key_query(menu,&key):nxs_menu_key(menu,&key);
   printf("{\"key_handled\":%d,\"query\":%d}\n",handled,strstr(b,"query")!=NULL);fflush(stdout);
  }
  if(!strncmp(b,"cancel",6))nxs_menu_cancel(menu);
  if(!strncmp(b,"quit",4)){quit=1;nxs_menu_cancel(menu);}
  state();
 }
}
int main(void)
{
 setbuf(stdout,NULL);setbuf(stdin,NULL);
 menu=nxs_menu_create("Context",command,pump,NULL);assert(menu);
 NXSMenuItem items[]={
  {.size=sizeof(NXSMenuItem),.parent=-1,.command=1,.title="Copy",.key_equivalent="c",.modifiers=NXS_MENU_COMMAND},
  {.size=sizeof(NXSMenuItem),.parent=-1,.flags=NXS_MENU_SEPARATOR},
  {.size=sizeof(NXSMenuItem),.parent=-1,.command=2,.title="Checked",.flags=NXS_MENU_CHECKED},
  {.size=sizeof(NXSMenuItem),.parent=-1,.command=3,.title="Disabled",.flags=NXS_MENU_DISABLED},
  {.size=sizeof(NXSMenuItem),.parent=-1,.title="Submenu",.flags=NXS_MENU_SUBMENU},
  {.size=sizeof(NXSMenuItem),.parent=4,.command=4,.title="Nested action"}};
 assert(nxs_menu_items(menu,items,sizeof(items)/sizeof(*items)));
 puts("{\"ready\":true}");char b[128];
 while(!quit&&fgets(b,sizeof(b),stdin)) {
  if(!strncmp(b,"open",4)){double x=300,y=200;sscanf(b+4,"%lf%lf",&x,&y);int ok=nxs_menu_popup(menu,x,y);printf("{\"closed\":true,\"accepted\":%d}\n",ok);}
  else if(!strncmp(b,"quit",4))quit=1;
  state();
 }
 assert(nxs_menu_destroy(menu));return 0;
}
