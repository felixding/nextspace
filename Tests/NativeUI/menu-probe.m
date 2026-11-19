/* Native application-menu binding and independent direct-AppKit reference.
 * Test labels/commands are fixture data, not a production shortcut policy. */
#import <AppKit/AppKit.h>
#include "NativeUI.h"
#include <assert.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
_Static_assert(offsetof(NXSNativeUIAPI,menu_model_flags)==760,"Preserve the previous provider prefix");
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
 ITEM(-1,0,"Empty",NULL,0,NXS_MENU_SUBMENU),
 ITEM(-1,71,"Registry action","w",NXS_MENU_COMMAND,NXS_MENU_KEY_ONLY),
 ITEM(-1,72,"Opaque application Copy","c",NXS_MENU_COMMAND,NXS_MENU_KEY_ONLY)
};
struct Probe {NXSMenu *menu;NXSControl *field;int allow,queries,actions,pumps,done,editor_commands,context_deactivation;uint64_t last;};
static void state(struct Probe *,int);
static void input(struct Probe *);
static void pump(void *context)
{
 struct Probe *p=context;p->pumps++;assert(nxs_menu_state(p->menu,-1).tracking);
 if(p->context_deactivation) {
  if(!nxs_menu_state(p->menu,-1).visible)return;
  assert(nxs_menu_auxiliary_parent(p->menu,NULL));
  [NSApp activateIgnoringOtherApps:YES];
  [NSApp deactivate];
  assert(nxs_menu_state(p->menu,-1).visible);
  assert(nxs_menu_cancel(p->menu));p->done=1;return;
 }
 assert(!nxs_menu_destroy(p->menu));
 NXSKeyEvent key={.size=sizeof(key),.type=NXS_KEY_DOWN,.key=NXS_KEY_TEXT,.text="X",.unmodified_text="X"};
 assert(nxs_control_key(p->field,&key)==NXS_INPUT_UNHANDLED);
 assert(!nxs_control_track_clicks(p->field,1,1,0,1));
 input(p);nxs_native_ui_dispatch_events(0);
}
static int command(void *context,uint64_t command,unsigned phase)
{
 struct Probe *p=context;assert(command>=64&&command<=72&&phase<=NXS_COMMAND_EXECUTE);
 assert(nxs_menu_state(p->menu,-1).tracking);
 assert(!nxs_menu_destroy(p->menu));assert(!nxs_menu_show(p->menu,0));
 assert(!nxs_menu_items(p->menu,model,sizeof(model)/sizeof(*model)));
 if(phase==NXS_COMMAND_VALIDATE){p->queries++;return p->allow;}
 p->actions++;p->last=command;return p->allow;
}
static int editor_command(void *context,const char *selector,unsigned phase)
{
 struct Probe *p=context;if(strcmp(selector,"copy:"))return -1;
 if(phase==NXS_COMMAND_EXECUTE)p->editor_commands++;
 return 1;
}
static NXSKeyEvent event(const char *text,unsigned modifiers)
{return (NXSKeyEvent){.size=sizeof(NXSKeyEvent),.type=NXS_KEY_DOWN,.key=NXS_KEY_TEXT,.text=text,.unmodified_text=text,.modifiers=modifiers};}
struct KeyIsolation {NXSMenu *application,*context;int actions,pumped;};
static int isolation_command(void *context,uint64_t identifier,unsigned phase)
{
 struct KeyIsolation *p=context;
 if(phase==NXS_COMMAND_EXECUTE)p->actions++;
 return 1;
}
static void isolation_pump(void *context)
{
 struct KeyIsolation *p=context;
 if(p->pumped||!nxs_menu_state(p->context,-1).visible)return;
 p->pumped=1;NXSKeyEvent key=event("j",NXS_ALT);
 assert(!nxs_menu_key_query(p->context,&key));
 assert(!p->actions); /* A context query must not execute another menu. */
 assert(!nxs_menu_key(p->context,&key)&&!p->actions);
 assert(nxs_menu_state(p->context,-1).visible);
 assert(nxs_menu_cancel(p->context));
}
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
  if(!(data.flags&NXS_MENU_KEY_ONLY))[parent addItem:item];[items addObject:item];
  if(data.flags&NXS_MENU_SUBMENU)[item setSubmenu:[[[NSMenu alloc] initWithTitle:title] autorelease]];
 }
 [NSApp setMainMenu:root];[[root window] setTitle:@"Native menu fixture"];[root sizeToFit];[root display];return root;
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
 if(argc>1&&!strcmp(argv[1],"--expect-no-query")) {
  assert(!(nxs_native_ui_menu_capabilities()&NXS_MENU_KEY_QUERY)&&!nxs_menu_key_query(NULL,NULL));
  puts("{\"unsupported_key_query_rejected\":true}");return 0;
 }
 NSAutoreleasePool *pool=[NSAutoreleasePool new];
 if(argc>1&&!strcmp(argv[1],"--context-key-isolation")) {
  struct KeyIsolation p={0};
  p.application=nxs_menu_create("Application",isolation_command,NULL,&p);
  p.context=nxs_menu_create("Context",isolation_command,isolation_pump,&p);
  NXSMenuItem application=ITEM(-1,1,"Application action","j",NXS_MENU_COMMAND,0);
  NXSMenuItem context=ITEM(-1,2,"Context action",NULL,0,0);
  assert(p.application&&p.context);
  assert(nxs_menu_items(p.application,&application,1)&&nxs_menu_show(p.application,1));
  assert(nxs_menu_items(p.context,&context,1)&&nxs_menu_popup(p.context,300,120));
  assert(p.pumped&&!p.actions);
  NXSKeyEvent key=event("j",NXS_ALT);
  assert(nxs_menu_key_query(p.application,&key)&&!p.actions);
  assert(nxs_menu_key(p.application,&key)&&p.actions==1);
  assert(nxs_menu_destroy(p.context));
  assert(nxs_menu_show(p.application,0)&&nxs_menu_destroy(p.application));
  puts("{\"unmatched_context_key_does_not_execute_application_menu\":true}");
  [pool drain];return 0;
 }
 struct Probe p={.allow=1};p.menu=nxs_menu_create("Native menu fixture",command,pump,&p);assert(p.menu);
 assert((nxs_native_ui_menu_capabilities()&(NXS_MENU_MODELS|NXS_MENU_CANCEL))==(NXS_MENU_MODELS|NXS_MENU_CANCEL));
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
 if(argc>1&&!strcmp(argv[1],"--initial-window-policy")) {
  assert(nxs_menu_show(p.menu,1));
  NSMenu *original=[NSApp mainMenu];assert(original);
  /* The pinned NSMenu owns a distinct deferred transient window. Inspect
   * its native property before display, rather than mapping it for the test. */
  NSWindow *transient=[original valueForKey:@"_bWindow"];
  assert(transient&&transient!=[original window]&&![transient isVisible]);
  assert(![[original window] hidesOnDeactivate]&&![transient hidesOnDeactivate]);
  assert(nxs_menu_cancel(p.menu)&&nxs_menu_destroy(p.menu));
  puts("{\"foreign_menu_lifetime_precedes_transient_display\":true}");[pool drain];return 0;
 }
 if(argc>1&&!strcmp(argv[1],"--context-deactivation")) {
  p.context_deactivation=1;
  assert(nxs_menu_popup(p.menu,300,120));assert(p.done);
  assert(nxs_menu_destroy(p.menu));
  puts("{\"foreign_context_survives_host_deactivation\":true}");[pool drain];return 0;
 }
 assert(!nxs_menu_lifecycle(p.menu,command,&p)); /* This model's branches have zero identities. */
 NXSMenuItem bad=model[1];bad.parent=0;assert(!nxs_menu_items(p.menu,&bad,1));
 bad.parent=-2;assert(!nxs_menu_items(p.menu,&bad,1));bad=model[1];bad.title="\xff";assert(!nxs_menu_items(p.menu,&bad,1));
 bad=model[1];bad.flags=128;assert(!nxs_menu_items(p.menu,&bad,1));bad=model[1];bad.flags=NXS_MENU_CHECKED|NXS_MENU_MIXED;assert(!nxs_menu_items(p.menu,&bad,1));
 assert(!nxs_menu_items(p.menu,NULL,1));assert(!nxs_menu_items(p.menu,model,4097));
 assert(!nxs_menu_state(p.menu,1).visible&&nxs_menu_state(p.menu,1).enabled);
 NXSKeyEvent key=event("z",NXS_ALT);
 if(nxs_native_ui_menu_capabilities()&NXS_MENU_KEY_QUERY) {
  assert(nxs_menu_key_query(p.menu,&key)&&!p.actions&&p.queries);
  assert(!nxs_menu_state(p.menu,-1).visible&&nxs_menu_state(p.menu,1).highlighted==-1);
  p.allow=0;assert(nxs_menu_key_query(p.menu,&key)&&!p.actions);p.allow=1;
  key=event("q",NXS_ALT);assert(!nxs_menu_key_query(p.menu,&key)&&!p.actions);
  key=event("z",NXS_ALT);key.type=NXS_KEY_UP;assert(!nxs_menu_key_query(p.menu,&key));key.type=NXS_KEY_DOWN;
 }
 assert(nxs_menu_key(p.menu,&key));assert(p.actions==1&&p.last==64&&p.queries);
 p.allow=0;assert(nxs_menu_key(p.menu,&key));assert(p.actions==1&&!nxs_menu_state(p.menu,1).enabled);p.allow=1;
 key=event("q",NXS_ALT);assert(!nxs_menu_key(p.menu,&key));
 key=event("z",NXS_ALT);key.type=NXS_KEY_UP;assert(!nxs_menu_key(p.menu,&key));key.type=NXS_KEY_DOWN;
 assert(nxs_menu_show(p.menu,1));assert([NSApp mainMenu]&&nxs_menu_state(p.menu,-1).visible);
 NSMenu *root=[NSApp mainMenu];assert([[root itemAtIndex:0] hasSubmenu]);
 [NSApp activateIgnoringOtherApps:YES];
 [NSApp deactivate];
 assert(nxs_menu_state(p.menu,-1).visible); /* The external app still owns this menu. */
 assert([[root title] isEqual:@"Native menu fixture"]);
 [root setMain:YES];
 assert([[[root window] title] isEqual:@"Native menu fixture"]);
 if(nxs_native_ui_menu_capabilities()&NXS_MENU_KEY_QUERY) {
  int actions=p.actions;
  NXSKeyEvent direct=event("d",NXS_ALT);
  assert(nxs_menu_key_query(p.menu,&direct)&&p.actions==actions);
  assert(nxs_menu_state(p.menu,-1).visible&&nxs_menu_state(p.menu,6).highlighted==-1);
 }
 NSMenu *edit=[[root itemAtIndex:0] submenu];[edit update];
 /* Geometry reads and unmatched native keys must not synchronously validate
  * every opaque application command. NSMenu validates its actual match. */
 int quiet_queries=p.queries;
 (void)nxs_menu_state(p.menu,-1);
 assert(p.queries==quiet_queries);
 NXSKeyEvent unmatched=event("q",NXS_CONTROL);
 assert(!nxs_menu_key_query(p.menu,&unmatched)&&p.queries==quiet_queries);
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
 NXSKeyEvent remapped=event("w",NXS_SUPER);actions=p.actions;
 assert(nxs_menu_key(p.menu,&remapped)&&p.actions==actions+1&&p.last==71);
 [[NSUserDefaults standardUserDefaults] removeVolatileDomainForName:NSArgumentDomain];
 if(saved)[[NSUserDefaults standardUserDefaults] setVolatileDomain:saved forName:NSArgumentDomain];[saved release];
 NSWindow *rootWindow=[root window];
 assert(nxs_menu_items(p.menu,model,sizeof(model)/sizeof(*model)));assert(nxs_menu_state(p.menu,-1).visible);
 assert([NSApp mainMenu]==root&&[root window]==rootWindow);
 /* Updating command availability must retain the open native submenu and
  * its existing NSMenuItems, including unrelated key-only bindings. */
 NSMenuItem *originalEdit=[root itemAtIndex:0];
 edit=[originalEdit submenu];
 [[root menuRepresentation] attachSubmenuForItemAtIndex:0];
 assert([root attachedMenu]==edit&&[[edit window] isVisible]);
 model[10].flags|=NXS_MENU_DISABLED;
 model[7].flags=NXS_MENU_MIXED;
 assert(nxs_menu_items(p.menu,model,sizeof(model)/sizeof(*model)));
 assert([root itemAtIndex:0]==originalEdit&&[root attachedMenu]==edit&&[[edit window] isVisible]);
 assert([[root itemAtIndex:2] state]==NSMixedState);
 NXSKeyEvent unavailable=event("w",NXS_ALT);int state_actions=p.actions;
 assert(nxs_menu_key(p.menu,&unavailable)&&p.actions==state_actions);
 model[10].flags&=~NXS_MENU_DISABLED;
 model[7].flags=NXS_MENU_CHECKED;
 assert(nxs_menu_items(p.menu,model,sizeof(model)/sizeof(*model)));
 assert([root attachedMenu]==edit&&[[edit window] isVisible]);
 [edit close];
 /* Commands absent from the visible application menu still use native key
  * matching, preferences, validation and action dispatch. Their bindings must
  * neither add a displayed row nor create an auxiliary menu window. */
 assert([root numberOfItems]==5);
 NXSKeyEvent registry=event("w",NXS_ALT);actions=p.actions;
 assert(nxs_menu_key_query(p.menu,&registry)&&p.actions==actions);
 assert(nxs_control_key(field,&registry)==NXS_INPUT_HANDLED&&p.actions==actions+1&&p.last==71);
 assert(!nxs_menu_state(p.menu,10).visible);
 p.allow=0;actions=p.actions;
 assert(nxs_menu_key(p.menu,&registry)&&p.actions==actions);p.allow=1;
 assert(nxs_control_command_filter(field,editor_command,&p));
 actions=p.actions;NXSKeyEvent copy=event("c",NXS_ALT);
 assert(nxs_control_key(field,&copy)==NXS_INPUT_HANDLED);
 assert(p.editor_commands==1&&p.actions==actions);
 int queries=p.queries;NXSKeyEvent beginning=event("a",NXS_CONTROL);
 assert(nxs_control_key(field,&beginning)==NXS_INPUT_HANDLED&&p.queries==queries);
 NXSTextState native_selection={.size=sizeof(native_selection)};
 assert(nxs_control_text_get(field,value,sizeof(value),&native_selection));
 assert(native_selection.selection_start==0&&!native_selection.selection_length);
 assert(nxs_control_key(field,&registry)==NXS_INPUT_HANDLED&&p.actions==actions+1&&p.last==71);
 assert(nxs_control_command_filter(field,NULL,NULL));
 if(argc>1&&!strcmp(argv[1],"--hold")) {
  p.actions=0;p.last=0;puts("{\"event\":\"menu-live\"}");
  while(!p.done){input(&p);nxs_native_ui_dispatch_events(.005);}
 }
 assert(nxs_control_destroy(field));
 assert(nxs_menu_show(p.menu,0)&&![NSApp mainMenu]);assert(nxs_menu_destroy(p.menu));
 /* Remote model snapshots keep passive native drawing independent of IPC.
  * Actual matching/dispatch and explicit item reads still consult the owner. */
 assert(nxs_native_ui_menu_capabilities()&NXS_MENU_STATE_SNAPSHOTS);
 struct Probe snapshot={.allow=1};
 snapshot.menu=nxs_menu_create("Remote menu snapshot",command,NULL,&snapshot);assert(snapshot.menu);
 NXSMenuItem remote=ITEM(-1,64,"Remote command","x",NXS_MENU_COMMAND,NXS_MENU_ENABLED_SNAPSHOT);
 assert(nxs_menu_items(snapshot.menu,&remote,1)&&nxs_menu_show(snapshot.menu,1));
 NSMenu *snapshot_root=[NSApp mainMenu];[snapshot_root update];[snapshot_root sizeToFit];[snapshot_root display];
 nxs_native_ui_dispatch_events(.02);
 assert(!snapshot.queries&&nxs_menu_state(snapshot.menu,-1).visible);
 NXSKeyEvent remote_key=event("x",NXS_ALT);
 assert(nxs_menu_key_query(snapshot.menu,&remote_key)&&snapshot.queries&&!snapshot.actions);
 int snapshot_queries=snapshot.queries;
 assert(nxs_menu_key(snapshot.menu,&remote_key)&&snapshot.actions==1&&snapshot.queries>snapshot_queries);
 snapshot.allow=0;snapshot_queries=snapshot.queries;
 assert(nxs_menu_key(snapshot.menu,&remote_key)&&snapshot.actions==1&&snapshot.queries>snapshot_queries);
 assert(!nxs_menu_state(snapshot.menu,0).enabled);
 snapshot.allow=1;snapshot_queries=snapshot.queries;
 assert(nxs_menu_key(snapshot.menu,&remote_key)&&snapshot.actions==2&&snapshot.queries>snapshot_queries);
 snapshot_queries=snapshot.queries;
 [snapshot_root update];[snapshot_root sizeToFit];[snapshot_root display];
 assert(snapshot.queries==snapshot_queries);
 unmatched=event("q",NXS_CONTROL);
 assert(!nxs_menu_key_query(snapshot.menu,&unmatched)&&snapshot.queries==snapshot_queries);
 assert(nxs_menu_show(snapshot.menu,0)&&nxs_menu_destroy(snapshot.menu));
 [pool drain];puts("{\"passive_menu_snapshot\":true,\"native_menu_model\":true,\"native_submenus\":true,\"native_key_equivalents\":true,\"native_modifier_preferences\":true,\"application_validation\":true,\"field_menu_routing\":true,\"atomic_invalid_model_rejection\":true,\"reentrant_mutation_rejected\":true,\"show_hide_destroy\":true}");return 0;
}
