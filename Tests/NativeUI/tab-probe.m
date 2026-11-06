/* Native tab model/input contract and an independent ordinary NSTabView.
 * GPL-2.0-or-later. No tab geometry or drawing is implemented here. */
#import <AppKit/AppKit.h>
#include "NativeUI.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <objc/runtime.h>
#include <poll.h>
#include <unistd.h>
struct Probe {NXSControl *control;unsigned actions,checks,images;const char *directory;double scale;};
static const uint64_t large_identifier=UINT64_C(0xf123456789abcdef);
static void check(struct Probe *p,const char *name,BOOL passed)
{printf("{\"case\":\"%s\",\"passed\":%s}\n",name,passed?"true":"false");fflush(stdout);assert(passed);p->checks++;}
/* Deferred host windows need not appear in NSApplication.windows. Observe
 * instantiation without depending on opaque provider struct offsets. */
static IMP original_init;
static NSTabView *observed;
static id witness_init(id self,SEL selector,NSRect frame)
{id view=((id (*)(id,SEL,NSRect))original_init)(self,selector,frame);observed=view;return view;}
static void changed(void *context,int event,const NXSControlState *state)
{
  struct Probe *p=context;assert(event==NXS_VALUE_CHANGED&&state->tracking);
  assert(!nxs_control_destroy(p->control));
  assert(!nxs_control_tab_items(p->control,NULL,0,0));
  p->actions++;
}
static NXSRect top_rect(NSView *view,NSRect rect)
{return (NXSRect){rect.origin.x,[view isFlipped]?rect.origin.y:[view bounds].size.height-NSMaxY(rect),rect.size.width,rect.size.height};}
static BOOL same_rect(NXSRect a,NXSRect b)
{return a.x==b.x&&a.y==b.y&&a.width==b.width&&a.height==b.height;}
static void compare(struct Probe *p,const char *name,const NXSTabItem *items,unsigned count,uint64_t selected,double width,double height)
{
  NSTabView *reference=[[NSTabView alloc] initWithFrame:NSMakeRect(0,0,width,height)];
  for(unsigned i=0;i<count;i++) {
    NSTabViewItem *item=[[NSTabViewItem alloc] initWithIdentifier:[NSNumber numberWithUnsignedLongLong:items[i].identifier]];
    [item setLabel:items[i].title?[NSString stringWithUTF8String:items[i].title]:@""];
    [item setToolTip:items[i].tooltip?[NSString stringWithUTF8String:items[i].tooltip]:nil];
    [reference addTabViewItem:item];[item release];
  }
  if(count)[reference selectTabViewItemWithIdentifier:[NSNumber numberWithUnsignedLongLong:selected]];
  NSWindow *window=[[NSWindow alloc] initWithContentRect:[reference bounds] styleMask:NSBorderlessWindowMask backing:NSBackingStoreBuffered defer:NO];
  [window setReleasedWhenClosed:NO];[[window contentView] addSubview:reference];
  [window setTitle:[NSString stringWithFormat:@"Native tab reference %s",name]];[window orderFront:nil];
  NXSBitmap actual=nxs_control_draw(p->control,p->scale);
  BOOL equal=actual.pixels&&actual.width==lround(width*p->scale)&&actual.height==lround(height*p->scale);
  if(p->directory) {
    char path[1024];snprintf(path,sizeof(path),"%s/%s-native.argb",p->directory,name);FILE *out=fopen(path,"wb");assert(out);
    if(actual.pixels)assert(fwrite(actual.pixels,actual.stride,actual.height,out)==(size_t)actual.height);fclose(out);
  }
  printf("{\"event\":\"reference\",\"pid\":%d,\"name\":\"%s\",\"width\":%.0f,\"height\":%.0f,\"pixel_width\":%d,\"pixel_height\":%d,\"stride\":%d}\n",getpid(),name,width,height,actual.width,actual.height,actual.stride);fflush(stdout);
  struct pollfd input={STDIN_FILENO,POLLIN,0};NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:10];
  while(poll(&input,1,0)==0&&[deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);
  char reply[32];assert(fgets(reply,sizeof(reply),stdin)&&!strcmp(reply,"captured\n"));
  char label[128];snprintf(label,sizeof(label),"%s-native-image-size",name);
  check(p,label,equal);p->images++;
  NXSTabState state=nxs_control_tab_state(p->control);
  check(p,"native-content-rectangle",same_rect(state.content,top_rect(reference,[reference contentRect])));
  for(unsigned i=0;i<count;i++)check(p,"native-item-rectangle",same_rect(nxs_control_tab_item_rect(p->control,items[i].identifier),top_rect(reference,[[reference tabViewItemAtIndex:i] _tabRect])));
  [window close];[window release];[reference release];
}
int main(int argc,char **argv)
{
  if(argc>1&&!strcmp(argv[1],"--expect-no-tabs")) {
    assert(!nxs_control_tab_capabilities()&&!nxs_control_create(NXS_TABVIEW,NULL,NULL,NULL));
    assert(!nxs_control_tab_items(NULL,NULL,0,0)&&nxs_control_tab_state(NULL).selected_index==-1);
    assert(!nxs_control_tab_item_rect(NULL,1).width);
    puts("{\"older_provider_without_tabs\":true}");return 0;
  }
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  struct Probe p={.directory=argc>1?argv[1]:NULL,.scale=argc>2?atof(argv[2]):1};
  assert(nxs_control_tab_capabilities()==NXS_TAB_ITEMS);
  Method method=class_getInstanceMethod([NSTabView class],@selector(initWithFrame:));
  original_init=method_setImplementation(method,(IMP)witness_init);
  p.control=nxs_control_create(NXS_TABVIEW,changed,NULL,&p);assert(p.control);
  method_setImplementation(method,original_init);
  NSTabView *view=observed;check(&p,"actual-native-tab-view",view&&[view class]==[NSTabView class]);
  NXSControlConfig config={.size=sizeof(config),.width=400,.height=100,.enabled=1};assert(nxs_control_sync(p.control,&config));
  NXSTabItem items[]={{sizeof(NXSTabItem),1,"One","First page"},{sizeof(NXSTabItem),2,"One",NULL},{sizeof(NXSTabItem),large_identifier,"日本語",NULL}};
  assert(nxs_control_tab_items(p.control,items,3,1));
  check(&p,"programmatic-model-has-no-user-action",p.actions==0);
  compare(&p,"initial",items,3,1,400,100);
  NSTabViewItem *retained=[view tabViewItemAtIndex:0];
  NXSRect rect=nxs_control_tab_item_rect(p.control,large_identifier);
  assert(nxs_control_track_clicks(p.control,rect.x+rect.width/2,rect.y+rect.height/2,0,1));
  NXSTabState state=nxs_control_tab_state(p.control);
  check(&p,"native-pointer-selection-and-busy-guards",state.selected==large_identifier&&state.selected_index==2&&p.actions==1);
  assert(nxs_control_track_clicks(p.control,rect.x+rect.width/2,rect.y+rect.height/2,0,1));
  check(&p,"selected-item-click-has-no-duplicate-action",p.actions==1);
  compare(&p,"selected",items,3,large_identifier,400,100);
  NXSTabItem invalid[3];memcpy(invalid,items,sizeof(items));invalid[1].identifier=1;
  check(&p,"duplicate-identifiers-rejected",!nxs_control_tab_items(p.control,invalid,3,1));
  invalid[1]=items[1];invalid[2].title="\xff";
  check(&p,"invalid-text-rejected",!nxs_control_tab_items(p.control,invalid,3,1));
  check(&p,"missing-selection-rejected",!nxs_control_tab_items(p.control,items,3,42));
  check(&p,"invalid-model-preserves-selection-and-items",nxs_control_tab_state(p.control).selected==large_identifier&&[view tabViewItemAtIndex:0]==retained&&p.actions==1);
  NXSTabItem reordered[]={items[2],items[0],items[1]};reordered[1].title="Renamed";
  assert(nxs_control_tab_items(p.control,reordered,3,1));
  check(&p,"reorder-retains-native-items",[view tabViewItemAtIndex:1]==retained&&nxs_control_tab_state(p.control).selected_index==1&&p.actions==1);
  compare(&p,"reordered",reordered,3,1,400,100);
  config.width=180;config.height=80;assert(nxs_control_sync(p.control,&config));
  compare(&p,"resized",reordered,3,1,180,80);
  config.enabled=0;assert(nxs_control_sync(p.control,&config));rect=nxs_control_tab_item_rect(p.control,2);
  check(&p,"disabled-control-rejects-pointer",!nxs_control_track_clicks(p.control,rect.x+rect.width/2,rect.y+rect.height/2,0,1)&&nxs_control_tab_state(p.control).selected==1&&p.actions==1);
  config.enabled=1;assert(nxs_control_sync(p.control,&config));
  check(&p,"native-focus-policy",nxs_control_focus(p.control,1)==[view acceptsFirstResponder]);
  assert(nxs_control_tab_items(p.control,NULL,0,0));
  check(&p,"empty-model",nxs_control_tab_state(p.control).count==0&&nxs_control_tab_state(p.control).selected_index==-1&&nxs_control_state(p.control).value==-1);
  compare(&p,"empty",NULL,0,0,180,80);
  assert(nxs_control_tab_items(p.control,items,3,large_identifier));
  check(&p,"restored-model-keeps-64-bit-identity",nxs_control_tab_state(p.control).selected==large_identifier&&p.actions==1);
  for(unsigned i=0;i<100;i++) {
    assert(nxs_control_tab_items(p.control,NULL,0,0));
    assert(nxs_control_tab_items(p.control,items,3,items[i%3].identifier));
  }
  check(&p,"repeated-empty-and-restore-lifecycle",nxs_control_tab_state(p.control).selected==1&&p.actions==1);
  check(&p,"unknown-item-has-empty-geometry",!nxs_control_tab_item_rect(p.control,42).width);
  check(&p,"destroy",nxs_control_destroy(p.control));
  printf("{\"passed\":%u,\"images\":%u,\"api_bytes\":%zu}\n",p.checks,p.images,sizeof(NXSNativeUIAPI));
  [pool drain];return 0;
}
