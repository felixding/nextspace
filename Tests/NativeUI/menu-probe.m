/* Native application-menu binding and independent direct-AppKit reference.
 * Test labels/commands are fixture data, not a production shortcut policy. */
#import <AppKit/AppKit.h>
#include "NativeUI.h"
#include <assert.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ITEM(p,c,t,k,m,f) {sizeof(NXSMenuItem),p,c,t,k,m,f}
static NXSMenuItem model[]={
 ITEM(-1,0,"Edit",NULL,0,NXS_MENU_SUBMENU),
 ITEM(0,64,"Undo","z",NXS_MENU_COMMAND,0),
 ITEM(0,65,"Redo","Z",NXS_MENU_COMMAND|NXS_MENU_SHIFT,0),
 ITEM(0,0,NULL,NULL,0,NXS_MENU_SEPARATOR),
 ITEM(0,66,"Duplicate",NULL,0,0),ITEM(0,67,"Duplicate",NULL,0,NXS_MENU_DISABLED),
 ITEM(-1,68,"Direct","d",NXS_MENU_COMMAND,0),
 ITEM(-1,69,"Checked",NULL,0,NXS_MENU_CHECKED),
 ITEM(-1,70,"Mixed",NULL,0,NXS_MENU_MIXED),
 ITEM(-1,0,"Empty",NULL,0,NXS_MENU_SUBMENU)
};
struct Probe {NXSMenu *menu;NXSControl *field;int allow,queries,actions,pumps,done;uint64_t last;};
static void state(struct Probe *,int);
static void input(struct Probe *);
static void pump(void *context)
{
 struct Probe *p=context;p->pumps++;assert(nxs_menu_state(p->menu,-1).tracking);
 assert(!nxs_menu_destroy(p->menu));
 NXSKeyEvent key={.size=sizeof(key),.type=NXS_KEY_DOWN,.key=NXS_KEY_TEXT,.text="X",.unmodified_text="X"};
 assert(nxs_control_key(p->field,&key)==NXS_INPUT_UNHANDLED);
 assert(!nxs_control_track_clicks(p->field,1,1,0,1));
 input(p);nxs_native_ui_dispatch_events(0);
}
static int command(void *context,uint64_t command,unsigned phase)
{
 struct Probe *p=context;assert(command>=64&&command<=70&&phase<=NXS_COMMAND_EXECUTE);
 assert(nxs_menu_state(p->menu,-1).tracking);
 assert(!nxs_menu_destroy(p->menu));assert(!nxs_menu_show(p->menu,0));
 assert(!nxs_menu_items(p->menu,model,sizeof(model)/sizeof(*model)));
 if(phase==NXS_COMMAND_VALIDATE){p->queries++;return p->allow;}
 p->actions++;p->last=command;return p->allow;
}
static NXSKeyEvent event(const char *text,unsigned modifiers)
{return (NXSKeyEvent){.size=sizeof(NXSKeyEvent),.type=NXS_KEY_DOWN,.key=NXS_KEY_TEXT,.text=text,.unmodified_text=text,.modifiers=modifiers};}
static void state(struct Probe *p,int index)
{
 NXSMenuState s=nxs_menu_state(p->menu,index);
 printf("{\"index\":%d,\"visible\":%d,\"tracking\":%d,\"enabled\":%d,\"highlighted\":%d,\"frame\":[%.3f,%.3f,%.3f,%.3f],\"item\":[%.3f,%.3f,%.3f,%.3f],\"actions\":%d,\"last\":%llu,\"pumps\":%d}\n",
 index,s.visible,s.tracking,s.enabled,s.highlighted,s.frame.x,s.frame.y,s.frame.width,s.frame.height,
 s.item_frame.x,s.item_frame.y,s.item_frame.width,s.item_frame.height,p->actions,(unsigned long long)p->last,p->pumps);fflush(stdout);
}
static void input(struct Probe *p)
{
 struct pollfd ready={0,POLLIN,0};if(poll(&ready,1,0)<=0)return;
 char line[64];if(!fgets(line,sizeof(line),stdin)||!strncmp(line,"quit",4)){p->done=1;return;}
 int index;if(sscanf(line,"state %d",&index)==1)state(p,index);
 else if(!strncmp(line,"disable",7)){p->allow=0;state(p,1);}
 else if(!strncmp(line,"enable",6)){p->allow=1;state(p,1);}
 else if(!strncmp(line,"hide",4)){printf("{\"ok\":%s}\n",nxs_menu_show(p->menu,0)?"true":"false");}
 else if(!strncmp(line,"show",4)){printf("{\"ok\":%s}\n",nxs_menu_show(p->menu,1)?"true":"false");}
 else if(!strncmp(line,"cancel",6)){printf("{\"ok\":%s}\n",nxs_menu_cancel(p->menu)?"true":"false");}
 else if(!strncmp(line,"mutate",6)){printf("{\"ok\":%s}\n",nxs_menu_items(p->menu,model,sizeof(model)/sizeof(*model))?"true":"false");}
 fflush(stdout);
}
@interface ReferenceTarget : NSObject
- (void)invoke:(id)sender;
@end
@implementation ReferenceTarget
- (void)invoke:(id)sender {(void)sender;}
- (BOOL)validateMenuItem:(NSMenuItem *)item {return [item tag]!=67;}
@end
static NSMenu *reference(void)
{
 NSMenu *root=[[[NSMenu alloc] initWithTitle:@"Native menu fixture"] autorelease];
 NSMutableArray *items=[NSMutableArray array];ReferenceTarget *target=[ReferenceTarget new];
 for(unsigned i=0;i<sizeof(model)/sizeof(*model);i++) {
  NXSMenuItem data=model[i];NSMenu *parent=data.parent<0?root:[[items objectAtIndex:data.parent] submenu];
  NSString *title=data.title?[NSString stringWithUTF8String:data.title]:@"";
  id item=data.flags&NXS_MENU_SEPARATOR?[NSMenuItem separatorItem]:
   [[[NSMenuItem alloc] initWithTitle:title action:@selector(invoke:) keyEquivalent:data.key_equivalent?[NSString stringWithUTF8String:data.key_equivalent]:@""] autorelease];
  [item setTarget:target];[item setTag:data.command];
  [item setKeyEquivalentModifierMask:((data.modifiers&NXS_MENU_COMMAND)?NSCommandKeyMask:0)|((data.modifiers&NXS_MENU_SHIFT)?NSShiftKeyMask:0)];
  [item setState:data.flags&NXS_MENU_MIXED?NSMixedState:data.flags&NXS_MENU_CHECKED?NSOnState:NSOffState];
  [parent addItem:item];[items addObject:item];
  if(data.flags&NXS_MENU_SUBMENU)[item setSubmenu:[[[NSMenu alloc] initWithTitle:title] autorelease]];
 }
 [NSApp setMainMenu:root];[root display];return root;
}
int main(int argc,char **argv)
{
 setvbuf(stdout,NULL,_IOLBF,0);
 if(argc>1&&!strcmp(argv[1],"--expect-no-menu")) {
  assert(!nxs_native_ui_menu_capabilities());assert(!nxs_menu_create("Old",command,NULL,NULL));
  assert(!nxs_menu_items(NULL,NULL,0)&&!nxs_menu_show(NULL,1)&&!nxs_menu_key(NULL,NULL));
  assert(nxs_menu_state(NULL,-1).highlighted==-1);puts("{\"unsupported_menu_rejected\":true}");return 0;
 }
 if(argc>1&&!strcmp(argv[1],"--expect-no-cancel")) {
  assert(nxs_native_ui_menu_capabilities()==NXS_MENU_MODELS&&!nxs_menu_cancel(NULL));
  puts("{\"unsupported_cancel_rejected\":true}");return 0;
 }
 NSAutoreleasePool *pool=[NSAutoreleasePool new];
 struct Probe p={.allow=1};p.menu=nxs_menu_create("Native menu fixture",command,pump,&p);assert(p.menu);
 assert(nxs_native_ui_menu_capabilities()==(NXS_MENU_MODELS|NXS_MENU_CANCEL));
 if(argc>1&&!strcmp(argv[1],"--reference")) {
  assert(nxs_menu_destroy(p.menu));reference();puts("{\"event\":\"reference-live\"}");
  while(!feof(stdin)) {
   struct pollfd input={0,POLLIN,0};if(poll(&input,1,0)>0){
    char line[64];if(!fgets(line,sizeof(line),stdin)||!strncmp(line,"quit",4))break;
    if(!strncmp(line,"hide",4))[[NSApp mainMenu] close];
    else if(!strncmp(line,"show",4))[[NSApp mainMenu] display];
    puts("{\"ok\":true}");
   }
   nxs_native_ui_dispatch_events(.005);
  }
  [[NSApp mainMenu] close];[NSApp setMainMenu:nil];[pool drain];return 0;
 }
 assert(!nxs_menu_create("Invalid",NULL,NULL,NULL));assert(nxs_menu_destroy(NULL));
 assert(nxs_menu_items(p.menu,model,sizeof(model)/sizeof(*model)));
 NXSMenuItem bad=model[1];bad.parent=0;assert(!nxs_menu_items(p.menu,&bad,1));
 bad.parent=-2;assert(!nxs_menu_items(p.menu,&bad,1));bad=model[1];bad.title="\xff";assert(!nxs_menu_items(p.menu,&bad,1));
 bad=model[1];bad.flags=32;assert(!nxs_menu_items(p.menu,&bad,1));bad=model[1];bad.flags=NXS_MENU_CHECKED|NXS_MENU_MIXED;assert(!nxs_menu_items(p.menu,&bad,1));
 assert(!nxs_menu_items(p.menu,NULL,1));assert(!nxs_menu_items(p.menu,model,4097));
 assert(!nxs_menu_state(p.menu,1).visible&&nxs_menu_state(p.menu,1).enabled);
 NXSKeyEvent key=event("z",NXS_ALT);assert(nxs_menu_key(p.menu,&key));assert(p.actions==1&&p.last==64&&p.queries);
 p.allow=0;assert(nxs_menu_key(p.menu,&key));assert(p.actions==1&&!nxs_menu_state(p.menu,1).enabled);p.allow=1;
 key=event("q",NXS_ALT);assert(!nxs_menu_key(p.menu,&key));
 key=event("z",NXS_ALT);key.type=NXS_KEY_UP;assert(!nxs_menu_key(p.menu,&key));key.type=NXS_KEY_DOWN;
 assert(nxs_menu_show(p.menu,1));assert([NSApp mainMenu]&&nxs_menu_state(p.menu,-1).visible);
 NSMenu *root=[NSApp mainMenu];assert([[root itemAtIndex:0] hasSubmenu]);
 NSMenu *edit=[[root itemAtIndex:0] submenu];[edit update];
 assert([[edit itemAtIndex:2] isSeparatorItem]);assert(![[edit itemAtIndex:4] isEnabled]);
 assert([[[edit itemAtIndex:3] title] isEqual:[[edit itemAtIndex:4] title]]);
 assert([[root itemAtIndex:2] state]==NSOnState&&[[root itemAtIndex:3] state]==NSMixedState);
 assert(![[root itemAtIndex:4] isEnabled]);
 NXSMenu *other=nxs_menu_create("Other",command,NULL,&p);assert(other&&!nxs_menu_show(other,1));assert(nxs_menu_destroy(other));
 NXSControl *field=nxs_control_create(NXS_TEXTFIELD,NULL,NULL,NULL);assert(field);p.field=field;
 NXSControlConfig config={.size=sizeof(config),.width=180,.height=24,.enabled=1};assert(nxs_control_sync(field,&config));
 NXSTextModel text={.size=sizeof(text),.text="Hello",.selection_start=5,.editable=1};
 assert(nxs_control_text_sync(field,&text)&&nxs_control_focus(field,1));
 int actions=p.actions;assert(nxs_control_key(field,&key)==NXS_INPUT_HANDLED);assert(p.actions==actions+1&&p.last==64);
 char value[64];assert(nxs_control_text_get(field,value,sizeof(value),NULL)&&!strcmp(value,"Hello"));
 NSDictionary *saved=[[[NSUserDefaults standardUserDefaults] volatileDomainForName:NSArgumentDomain] copy];
 NSMutableDictionary *prefs=[NSMutableDictionary dictionaryWithDictionary:saved?:@{}];
 [prefs setObject:@"Super_L" forKey:@"GSFirstCommandKey"];[prefs setObject:@"Alt_L" forKey:@"GSFirstAlternateKey"];
 [[NSUserDefaults standardUserDefaults] removeVolatileDomainForName:NSArgumentDomain];
 [[NSUserDefaults standardUserDefaults] setVolatileDomain:prefs forName:NSArgumentDomain];
 key=event("z",NXS_SUPER);actions=p.actions;assert(nxs_menu_key(p.menu,&key)&&p.actions==actions+1);
 [[NSUserDefaults standardUserDefaults] removeVolatileDomainForName:NSArgumentDomain];
 if(saved)[[NSUserDefaults standardUserDefaults] setVolatileDomain:saved forName:NSArgumentDomain];[saved release];
 assert(nxs_menu_items(p.menu,model,sizeof(model)/sizeof(*model)));assert(nxs_menu_state(p.menu,-1).visible);
 if(argc>1&&!strcmp(argv[1],"--hold")) {
  p.actions=0;p.last=0;puts("{\"event\":\"menu-live\"}");
  while(!p.done){input(&p);nxs_native_ui_dispatch_events(.005);}
 }
 assert(nxs_control_destroy(field));
 assert(nxs_menu_show(p.menu,0)&&![NSApp mainMenu]);assert(nxs_menu_destroy(p.menu));
 [pool drain];puts("{\"native_menu_model\":true,\"native_submenus\":true,\"native_key_equivalents\":true,\"native_modifier_preferences\":true,\"application_validation\":true,\"field_menu_routing\":true,\"atomic_invalid_model_rejection\":true,\"reentrant_mutation_rejected\":true,\"show_hide_destroy\":true}");return 0;
}
