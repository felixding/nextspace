/* Native submenu preparation, mutation boundaries and lifetime probe. */
#include "NativeUI.h"
#include <assert.h>
#include <poll.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#define ITEM(p,c,t,k,m,f) {sizeof(NXSMenuItem),p,c,t,k,m,f}
static NXSMenuItem initial[]={ITEM(-1,100,"Edit",NULL,0,NXS_MENU_SUBMENU),
 ITEM(-1,101,"Other",NULL,0,NXS_MENU_SUBMENU),ITEM(1,300,"Unchanged",NULL,0,0),
 ITEM(-1,400,"Original registry action","l",NXS_MENU_COMMAND,NXS_MENU_KEY_ONLY)};
static NXSMenuItem populated[]={ITEM(-1,200,"Undo","z",NXS_MENU_COMMAND,0),
 ITEM(-1,201,"Unavailable",NULL,0,NXS_MENU_DISABLED),
 ITEM(-1,202,"More",NULL,0,NXS_MENU_SUBMENU),ITEM(2,203,"Nested action",NULL,0,0)};
static NXSMenuItem nested[]={ITEM(-1,204,"Fresh nested action",NULL,0,0)};
/* Equivalent eager model uses the provider's original NSMenuView. */
static NXSMenuItem eager[]={ITEM(-1,100,"Edit",NULL,0,NXS_MENU_SUBMENU),
 ITEM(0,200,"Undo","z",NXS_MENU_COMMAND,0),
 ITEM(0,201,"Unavailable",NULL,0,NXS_MENU_DISABLED),
 ITEM(0,202,"More",NULL,0,NXS_MENU_SUBMENU),
 ITEM(3,203,"Nested action",NULL,0,0),
 ITEM(-1,101,"Other",NULL,0,NXS_MENU_SUBMENU),ITEM(5,300,"Unchanged",NULL,0,0)};
struct State {NXSMenu *menu;int done,mode,opens,closes,actions;uint64_t last;};
static void input(struct State *s);
static void pump(void *context){input(context);}
static int command(void *context,uint64_t command,unsigned phase)
{
 struct State *s=context;
 assert(command==200||command==201||command==203||command==204||command==300||command==400);
 if(phase==NXS_COMMAND_EXECUTE){s->actions++;s->last=command;}
 return command!=201;
}
static int lifecycle(void *context,uint64_t branch,unsigned phase)
{
 struct State *s=context;assert(branch==100||branch==101||branch==202);
 assert(nxs_menu_state(s->menu,-1).tracking);
 assert(!nxs_menu_destroy(s->menu)&&!nxs_menu_show(s->menu,0));
 assert(!nxs_menu_items(s->menu,initial,3));
 assert(!nxs_menu_lifecycle(s->menu,NULL,NULL));
 if(phase==NXS_MENU_WILL_OPEN) {
  s->opens++;
  assert(!nxs_menu_branch_items(s->menu,branch==101?100:101,nested,1));
  if(s->mode==1)return 0;
  if(s->mode==2){assert(nxs_menu_cancel(s->menu));return 1;}
  if(branch==100) {
   NXSMenuItem duplicate=ITEM(-1,101,"Duplicate identity",NULL,0,0);
   assert(!nxs_menu_branch_items(s->menu,100,&duplicate,1));
   assert(nxs_menu_branch_items(s->menu,100,populated,4));
  } else if(branch==202)assert(nxs_menu_branch_items(s->menu,202,nested,1));
 } else {
  assert(phase==NXS_MENU_DID_CLOSE);s->closes++;
  assert(!nxs_menu_branch_items(s->menu,branch,nested,1));
 }
 printf("{\"event\":\"lifecycle\",\"branch\":%llu,\"phase\":%u,\"opens\":%d,\"closes\":%d}\n",(unsigned long long)branch,phase,s->opens,s->closes);fflush(stdout);
 return 1;
}
static void state(struct State *s,int index)
{
 NXSMenuState v=nxs_menu_state(s->menu,index);
 printf("{\"event\":\"state\",\"index\":%d,\"visible\":%d,\"tracking\":%d,\"enabled\":%d,\"highlighted\":%d,\"frame\":[%g,%g,%g,%g],\"item\":[%g,%g,%g,%g],\"opens\":%d,\"closes\":%d,\"actions\":%d,\"last\":%llu}\n",index,v.visible,v.tracking,v.enabled,v.highlighted,v.frame.x,v.frame.y,v.frame.width,v.frame.height,v.item_frame.x,v.item_frame.y,v.item_frame.width,v.item_frame.height,s->opens,s->closes,s->actions,(unsigned long long)s->last);fflush(stdout);
}
static void input(struct State *s)
{
 struct pollfd ready={0,POLLIN,0};if(poll(&ready,1,0)<=0)return;
 char line[64];if(!fgets(line,sizeof(line),stdin)||!strncmp(line,"quit",4)){s->done=1;nxs_menu_cancel(s->menu);return;}
 int index;
 if(sscanf(line,"state %d",&index)==1)state(s,index);
 else if(!strncmp(line,"reject",6))s->mode=1;
 else if(!strncmp(line,"cancel",6))s->mode=2;
 else if(!strncmp(line,"allow",5))s->mode=0;
 else if(!strncmp(line,"show",4))assert(nxs_menu_show(s->menu,1));
 else if(!strncmp(line,"sync",4)){puts("{\"event\":\"sync\"}");fflush(stdout);}
}
int main(int argc,char **argv)
{
 setvbuf(stdin,NULL,_IONBF,0);setvbuf(stdout,NULL,_IOLBF,0);
 if(argc>1&&!strcmp(argv[1],"--expect-no-lifecycle")) {
  assert(!(nxs_native_ui_menu_capabilities()&NXS_MENU_LIFECYCLE));
  assert(!nxs_menu_lifecycle(NULL,lifecycle,NULL));
  assert(!nxs_menu_branch_items(NULL,100,populated,4));
  puts("{\"unsupported_lifecycle_rejected\":true}");return 0;
 }
 assert(nxs_native_ui_menu_capabilities()&NXS_MENU_LIFECYCLE);
 struct State s={0};s.menu=nxs_menu_create("Lifecycle fixture",command,pump,&s);assert(s.menu);
 if(argc>1&&!strcmp(argv[1],"--eager"))assert(nxs_menu_items(s.menu,eager,7));
 else {
  assert(nxs_menu_lifecycle(s.menu,lifecycle,&s));
  assert(nxs_menu_items(s.menu,initial,4));
  NXSKeyEvent key={.size=sizeof(key),.type=NXS_KEY_DOWN,.modifiers=NXS_ALT,.text="l",.unmodified_text="l"};
  assert(nxs_menu_key_query(s.menu,&key)&&!s.actions);
  assert(nxs_menu_key(s.menu,&key)&&s.actions==1&&s.last==400);
  assert(!nxs_menu_branch_items(s.menu,100,NULL,1));
  assert(!nxs_menu_branch_items(s.menu,100,initial,4097));
  assert(nxs_menu_branch_items(s.menu,100,populated,4));
  assert(nxs_menu_key(s.menu,&key)&&s.actions==2&&s.last==400);
  assert(!nxs_menu_branch_items(s.menu,100,&initial[3],1));
  assert(nxs_menu_items(s.menu,initial,4));s.actions=0;s.last=0;
 }
 assert(nxs_menu_show(s.menu,1));
 assert(!nxs_menu_lifecycle(s.menu,NULL,NULL));
 puts("{\"event\":\"ready\"}");
 while(!s.done){input(&s);nxs_native_ui_dispatch_events(.005);}
 assert(nxs_menu_destroy(s.menu));puts("{\"event\":\"stopped\"}");return 0;
}
