/* Independent ordinary NSPopUpButton title/selection reference. GPL-2.0-or-later. */
#import <AppKit/AppKit.h>
#include "NativeUI.h"
#include <assert.h>
#include <math.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <objc/runtime.h>
_Static_assert(offsetof(NXSNativeUIAPI,control_popup_title)==472,"Existing API prefix");
struct Probe {NXSControl *control;NSPopUpButton *native;unsigned actions,checks,images,phase,loops;const char *directory;double scale,x,y;};
static IMP original_init;static NSPopUpButton *observed;
static id witness_init(id self,SEL selector,NSRect frame,BOOL pulls)
{id view=((id (*)(id,SEL,NSRect,BOOL))original_init)(self,selector,frame,pulls);observed=view;return view;}
static void check(struct Probe *p,const char *name,BOOL passed)
{printf("{\"case\":\"%s\",\"passed\":%s}\n",name,passed?"true":"false");fflush(stdout);assert(passed);p->checks++;}
static void changed(void *context,int event,const NXSControlState *state)
{
 struct Probe *p=context;assert(event==NXS_VALUE_CHANGED&&state->tracking);
 assert(!nxs_control_popup_title(p->control,"Busy"));p->actions++;
}
static void pump(void *context)
{
 struct Probe *p=context;
 assert(++p->loops<5000);
 assert(!nxs_control_popup_title(p->control,"Busy"));
 if(!p->phase){NXSRect rect=nxs_control_popup_item_rect(p->control,2);assert(rect.width>0);p->phase=1;p->x=rect.x+rect.width/2;p->y=rect.y+rect.height/2;nxs_control_send(p->control,NXS_MOVE,p->x,p->y,0);}
 else if(p->phase==1&&nxs_control_popup_state(p->control).highlighted==2){NXSRect rect=nxs_control_popup_item_rect(p->control,2);p->phase=2;nxs_control_send(p->control,NXS_RELEASE,rect.x+rect.width/2,rect.y+rect.height/2,0);}
 else if(p->phase==1){NXSRect rect=nxs_control_popup_item_rect(p->control,2);double x=rect.x+rect.width/2,y=rect.y+rect.height/2;if(x!=p->x||y!=p->y){p->x=x;p->y=y;nxs_control_send(p->control,NXS_MOVE,x,y,0);}}
}
static void key(struct Probe *p,unsigned key,const char *text)
{NXSKeyEvent event={.size=sizeof(event),.type=NXS_KEY_DOWN,.key=key,.text=text};assert(nxs_control_key(p->control,&event)==NXS_INPUT_HANDLED);}
static void compare(struct Probe *p,const char *name,const NXSPopupItem *items,unsigned count,int selected,const char *title,int enabled)
{
 NSPopUpButton *reference=[[NSPopUpButton alloc] initWithFrame:NSMakeRect(0,0,180,24) pullsDown:NO];
 NSMenu *menu=[[NSMenu alloc] initWithTitle:@""];[menu setAutoenablesItems:NO];
 for(unsigned i=0;i<count;i++)if(items[i].separator)[menu addItem:[NSMenuItem separatorItem]];
 else {id item=[menu addItemWithTitle:[NSString stringWithUTF8String:items[i].title] action:NULL keyEquivalent:@""];[item setEnabled:items[i].enabled];}
 [reference setMenu:menu];[menu release];[reference selectItemAtIndex:selected];
 if(title){[[reference cell] setUsesItemFromMenu:NO];[[reference cell] setTitle:[NSString stringWithUTF8String:title]];}
 [reference setEnabled:enabled];
 NSWindow *window=[[NSWindow alloc] initWithContentRect:[reference bounds] styleMask:NSBorderlessWindowMask backing:NSBackingStoreBuffered defer:NO];
 [window setReleasedWhenClosed:NO];[[window contentView] addSubview:reference];
 [window setTitle:[NSString stringWithFormat:@"Native popup title reference %s",name]];[window orderFront:nil];[window display];
 NXSBitmap actual=nxs_control_draw(p->control,p->scale);assert(actual.pixels);
 BOOL dirty=nxs_control_needs_display(p->control);
 char path[1024];snprintf(path,sizeof(path),"%s/%s-native.argb",p->directory,name);FILE *out=fopen(path,"wb");assert(out);
 assert(fwrite(actual.pixels,actual.stride,actual.height,out)==(size_t)actual.height);fclose(out);
 printf("{\"event\":\"reference\",\"pid\":%d,\"name\":\"%s\",\"width\":180,\"height\":24,\"pixel_width\":%d,\"pixel_height\":%d,\"stride\":%d}\n",getpid(),name,actual.width,actual.height,actual.stride);fflush(stdout);
 struct pollfd input={STDIN_FILENO,POLLIN,0};NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:10];
 while(poll(&input,1,0)==0&&[deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);
 char reply[32];assert(fgets(reply,sizeof(reply),stdin)&&!strcmp(reply,"captured\n"));
 check(p,"whole-native-image-size",actual.width==lround(180*p->scale)&&actual.height==lround(24*p->scale));p->images++;
 NXSSize size=nxs_control_size(p->control);NSSize expected=[[reference cell] cellSize];
 check(p,"native-preferred-size",size.width==expected.width&&size.height==expected.height);
 check(p,"native-draw-consumes-invalidation",!dirty);
 [window close];[window release];[reference release];
}
int main(int argc,char **argv)
{
 NSAutoreleasePool *pool=[NSAutoreleasePool new];
 if(argc>1&&!strcmp(argv[1],"--expect-no-popup-title")) {
  assert(!nxs_control_popup_title_capabilities());
  NXSControl *control=nxs_control_create(NXS_POPUP,NULL,NULL,NULL);assert(control);
  NXSPopupItem item={sizeof(item),"Existing",1,0};assert(nxs_control_popup_items(control,&item,1,0));
  assert(!nxs_control_popup_title(control,"Unsupported")&&!nxs_control_popup_title(control,NULL));
  assert(nxs_control_state(control).value==0&&nxs_control_destroy(control));
  puts("{\"older_provider_without_popup_title\":true}");[pool drain];return 0;
 }
 assert(argc>1);struct Probe p={.directory=argv[1],.scale=argc>2?atof(argv[2]):1};
 check(&p,"native-popup-title-capability",nxs_control_popup_title_capabilities()==1&&nxs_control_popup_capabilities()==NXS_POPUP_ITEMS);
 Method method=class_getInstanceMethod([NSPopUpButton class],@selector(initWithFrame:pullsDown:));original_init=method_setImplementation(method,(IMP)witness_init);
 p.control=nxs_control_create(NXS_POPUP,changed,pump,&p);assert(p.control);method_setImplementation(method,original_init);p.native=observed;
 check(&p,"actual-native-popup",[p.native class]==[NSPopUpButton class]&&[[p.native cell] class]==[NSPopUpButtonCell class]);
 NXSControlConfig config={.size=sizeof(config),.width=180,.height=24,.enabled=1,.value=-1};assert(nxs_control_sync(p.control,&config));
 assert(nxs_control_set_screen_origin(p.control,240,160));
 NXSPopupItem items[]={{sizeof(NXSPopupItem),"First",1,0},{sizeof(NXSPopupItem),"Disabled",0,0},{sizeof(NXSPopupItem),"Second",1,0}};
 assert(nxs_control_popup_items(p.control,items,3,-1));assert(nxs_control_popup_title(p.control,"Hidden selected"));
 check(&p,"title-preserves-empty-selection-and-menu",[p.native numberOfItems]==3&&[p.native indexOfSelectedItem]==-1&&[[p.native cell] usesItemFromMenu]==NO&&p.actions==0);
 compare(&p,"hidden-selected",items,3,-1,"Hidden selected",1);
 assert(nxs_control_popup_title(p.control,""));compare(&p,"empty-title",items,3,-1,"",1);
 assert(nxs_control_popup_title(p.control,"日本語"));compare(&p,"unicode-title",items,3,-1,"日本語",1);
 check(&p,"invalid-title-is-atomic",!nxs_control_popup_title(p.control,"\xff")&&[[[p.native cell] title] isEqualToString:@"日本語"]&&p.actions==0);
 assert(nxs_control_popup_items(p.control,items,3,0));
 check(&p,"model-retains-independent-title",[[[p.native cell] title] isEqualToString:@"日本語"]&&[p.native indexOfSelectedItem]==0);
 compare(&p,"model-replaced",items,3,0,"日本語",1);
 assert(nxs_control_popup_title(p.control,NULL));compare(&p,"menu-title-restored",items,3,0,NULL,1);
 check(&p,"restore-preserves-labels-and-selection",[[p.native cell] usesItemFromMenu]&&[[p.native itemTitleAtIndex:0] isEqualToString:@"First"]&&[p.native indexOfSelectedItem]==0&&!p.actions);
 assert(nxs_control_popup_title(p.control,"Hidden selected"));assert(nxs_control_focus(p.control,1));
 key(&p,NXS_KEY_TEXT," ");check(&p,"open-menu-rejects-title-mutation",!nxs_control_popup_title(p.control,"Busy")&&nxs_control_popup_state(p.control).visible);
 key(&p,NXS_KEY_ESCAPE,NULL);check(&p,"cancel-retains-title-and-selection",p.actions==0&&[p.native indexOfSelectedItem]==0&&[[[p.native cell] title] isEqualToString:@"Hidden selected"]);
 assert(nxs_control_focus(p.control,0));nxs_control_track(p.control,18,12,0);
 check(&p,"native-selection-with-independent-title",p.phase==2&&p.actions==1&&nxs_control_state(p.control).value==2&&[[[p.native cell] title] isEqualToString:@"Hidden selected"]);
 assert(nxs_control_popup_title(p.control,NULL));compare(&p,"selected-menu-title",items,3,2,NULL,1);
 config.enabled=0;config.value=2;assert(nxs_control_sync(p.control,&config));assert(nxs_control_popup_title(p.control,"Disabled selection"));
 compare(&p,"disabled-title",items,3,2,"Disabled selection",0);
 assert(nxs_control_popup_items(p.control,NULL,0,-1));assert(nxs_control_popup_title(p.control,"Empty model"));
 compare(&p,"empty-model-title",NULL,0,-1,"Empty model",0);
 check(&p,"empty-model-keeps-native-title-without-fake-item",![p.native numberOfItems]&&nxs_control_state(p.control).value==-1&&!nxs_control_popup_open(p.control,1));
 for(unsigned i=0;i<100;i++){assert(nxs_control_popup_title(p.control,"Repeat"));assert(nxs_control_popup_title(p.control,NULL));}
 check(&p,"repeated-title-lifecycle-emits-no-action",p.actions==1&&!nxs_control_popup_title(NULL,"Invalid"));
 check(&p,"destroy",nxs_control_destroy(p.control));
 printf("{\"passed\":%u,\"images\":%u,\"api_bytes\":%zu}\n",p.checks,p.images,sizeof(NXSNativeUIAPI));[pool drain];return 0;
}
