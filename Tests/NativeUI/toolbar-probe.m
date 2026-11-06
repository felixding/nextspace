/* Native toolbar contract against an ordinary embedded NSToolbar representation. No toolbar
 * layout, drawing, hit testing or tracking implementation. GPL-2.0-or-later. */
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
_Static_assert(sizeof(NXSToolbarItem)==48,"Toolbar item ABI");
_Static_assert(sizeof(NXSToolbarState)==112,"Toolbar state ABI");
_Static_assert(offsetof(NXSNativeUIAPI,control_toolbar_items)==448,"Existing API prefix");
@interface NSToolbar (NativeProbe)
- (NSView *)_toolbarView;
@end
@interface NSView (NativeProbe)
- (CGFloat)_heightFromLayout;
- (NSView *)_backView;
- (void)_reload;
@end
struct Probe {NXSControl *control;unsigned checks,images,actions,phase,loops;const char *directory;double scale;uint64_t wanted;NXSRect press;};
static const uint64_t large_identifier=UINT64_C(0xf123456789abcdef);
static IMP original_init;static NSToolbar *observed;
static id witness_init(id self,SEL selector,NSString *identifier)
{id toolbar=((id (*)(id,SEL,id))original_init)(self,selector,identifier);observed=toolbar;return toolbar;}
static void check(struct Probe *p,const char *name,BOOL passed)
{printf("{\"case\":\"%s\",\"passed\":%s}\n",name,passed?"true":"false");fflush(stdout);assert(passed);p->checks++;}
static void changed(void *context,int event,const NXSControlState *state)
{
 struct Probe *p=context;assert(event==NXS_ACTIVATE&&state->tracking);
 assert(!nxs_control_destroy(p->control));assert(!nxs_control_toolbar_items(p->control,NULL,0,0,0));
 p->actions++;
}
static void pump(void *context)
{
 struct Probe *p=context;if(!p->phase)return;assert(++p->loops<5000);
 if(p->phase==1){p->phase=0;nxs_control_send(p->control,NXS_RELEASE,p->press.x+p->press.width/2,p->press.y+p->press.height/2,0);}
 else if(p->phase==2) {
  NXSToolbarState state=nxs_control_toolbar_state(p->control);
  if(state.flags&NXS_TOOLBAR_MENU_VISIBLE) {
   NXSRect rect=nxs_control_toolbar_item_rect(p->control,p->wanted);
   if(!p->wanted){p->phase=0;nxs_control_send(p->control,NXS_RELEASE,-10000,-10000,0);return;}
   if(rect.width>0){
    printf("{\"event\":\"overflow-menu\",\"pid\":%d,\"x\":%f,\"y\":%f,\"width\":%f,\"height\":%f}\n",getpid(),400+state.menu.x,400+state.menu.y,state.menu.width,state.menu.height);fflush(stdout);
    struct pollfd input={STDIN_FILENO,POLLIN,0};NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:10];
    while(poll(&input,1,0)==0&&[deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.005);
    char reply[32];assert(fgets(reply,sizeof(reply),stdin)&&!strcmp(reply,"captured\n"));
    check(p,"native-overflow-placement-near-owner",state.menu.x>=-190&&state.menu.x<=380&&state.menu.y>=-state.menu.height&&state.menu.y<=124);p->phase=3;p->press=rect;nxs_control_send(p->control,NXS_MOVE,rect.x+rect.width/2,rect.y+rect.height/2,0);}
  }
 } else if(p->phase==3) {
  NXSToolbarState state=nxs_control_toolbar_state(p->control);
  if(state.highlighted>=0){p->phase=0;nxs_control_send(p->control,NXS_RELEASE,p->press.x+p->press.width/2,p->press.y+p->press.height/2,0);}
  else {NXSRect rect=nxs_control_toolbar_item_rect(p->control,p->wanted);if(memcmp(&rect,&p->press,sizeof(rect))){p->press=rect;nxs_control_send(p->control,NXS_MOVE,rect.x+rect.width/2,rect.y+rect.height/2,0);}}
 }
}
@interface ReferenceToolbar : NSObject <NSToolbarDelegate> {
 @public NSArray *identifiers;NSDictionary *items;
}
@end
@implementation ReferenceToolbar
- (void)dealloc {[identifiers release];[items release];[super dealloc];}
- (NSArray *)toolbarAllowedItemIdentifiers:(NSToolbar *)t{return identifiers;}
- (NSArray *)toolbarDefaultItemIdentifiers:(NSToolbar *)t{return identifiers;}
- (NSToolbarItem *)toolbar:(NSToolbar *)t itemForItemIdentifier:(NSString *)key willBeInsertedIntoToolbar:(BOOL)flag{return [items objectForKey:key];}
- (void)invoke:(id)sender{}
- (BOOL)validateToolbarItem:(NSToolbarItem *)item{return [item tag]!=-1;}
@end
static NSToolbar *reference_toolbar;
static ReferenceToolbar *reference_delegate;
static NXSRect native_rect(NSView *root,NSView *view)
{
 NSRect rect=[root convertRect:[view bounds] fromView:view];
 return (NXSRect){rect.origin.x,[root isFlipped]?rect.origin.y:[root bounds].size.height-NSMaxY(rect),rect.size.width,rect.size.height};
}
static BOOL same_rect(NXSRect a,NXSRect b)
{return a.x==b.x&&a.y==b.y&&a.width==b.width&&a.height==b.height;}
static void dirty_views(NSView *view,unsigned depth)
{NSLog(@"Toolbar view %u %@ dirty=%d frame=%@ hidden=%d",depth,NSStringFromClass([view class]),[view needsDisplay],NSStringFromRect([view frame]),[view isHidden]);for(NSView *child in [view subviews])dirty_views(child,depth+1);}
static void compare(struct Probe *p,const char *name,const NXSToolbarItem *data,unsigned count,unsigned mode,unsigned size,double width)
{
 ReferenceToolbar *delegate=[ReferenceToolbar new];NSMutableArray *ids=[NSMutableArray array];NSMutableDictionary *items=[NSMutableDictionary dictionary];
 for(unsigned i=0;i<count;i++) {
  NSString *key=data[i].type==NXS_TOOLBAR_SPACE?NSToolbarSpaceItemIdentifier:data[i].type==NXS_TOOLBAR_FLEXIBLE_SPACE?NSToolbarFlexibleSpaceItemIdentifier:data[i].type==NXS_TOOLBAR_SEPARATOR?NSToolbarSeparatorItemIdentifier:[NSString stringWithFormat:@"reference.%u",i];
  [ids addObject:key];if(data[i].type!=NXS_TOOLBAR_ACTION)continue;
  NSToolbarItem *item=[[NSToolbarItem alloc] initWithItemIdentifier:key];
  [item setLabel:data[i].title?[NSString stringWithUTF8String:data[i].title]:@""];
  [item setPaletteLabel:[item label]];[item setToolTip:data[i].tooltip?[NSString stringWithUTF8String:data[i].tooltip]:@""];
  [item setImage:data[i].image_name?[[[NSImage imageNamed:[NSString stringWithUTF8String:data[i].image_name]] copy] autorelease]:nil];
  [item setTarget:delegate];[item setAction:@selector(invoke:)];[item setTag:data[i].enabled?0:-1];[item setEnabled:data[i].enabled];
  [items setObject:item forKey:key];[item release];
 }
 delegate->identifiers=[ids copy];delegate->items=[items copy];
 /* Emptying an existing toolbar preserves AppKit's last native height.
  * Compare that lifecycle against the preceding ordinary toolbar instance. */
 if(count) {
  [reference_toolbar setDelegate:nil];[reference_toolbar release];[reference_delegate release];
  reference_toolbar=[[NSToolbar alloc] initWithIdentifier:[[NSProcessInfo processInfo] globallyUniqueString]];
  [reference_toolbar setDisplayMode:mode];[reference_toolbar setSizeMode:size];
  reference_delegate=delegate;[reference_toolbar setDelegate:delegate];
 } else {
  [delegate release];delegate=reference_delegate;
  while([[reference_toolbar items] count])[reference_toolbar removeItemAtIndex:0];
 }
 NSToolbar *toolbar=reference_toolbar;
 [toolbar setDisplayMode:mode];[toolbar setSizeMode:size];
 NSView *view=[toolbar _toolbarView];[view setFrameSize:NSMakeSize(width,[view frame].size.height)];[view _reload];
 double height=[view _heightFromLayout];[view setFrame:NSMakeRect(0,0,width,height)];[view _reload];
 NSWindow *window=[[NSWindow alloc] initWithContentRect:[view bounds] styleMask:NSBorderlessWindowMask backing:NSBackingStoreBuffered defer:NO];
 [window setReleasedWhenClosed:NO];[[window contentView] addSubview:view];[toolbar validateVisibleItems];
 NXSControlConfig config={.size=sizeof(config),.width=width,.height=height,.enabled=1};assert(nxs_control_sync(p->control,&config));
 [window setTitle:[NSString stringWithFormat:@"Native toolbar reference %s",name]];[window orderFront:nil];[window display];
 NXSBitmap actual=nxs_control_draw(p->control,p->scale);
 BOOL dirty=nxs_control_needs_display(p->control);if(dirty)dirty_views([observed _toolbarView],0);
 char path[1024];snprintf(path,sizeof(path),"%s/%s-native.argb",p->directory,name);FILE *out=fopen(path,"wb");assert(out);assert(actual.pixels&&fwrite(actual.pixels,actual.stride,actual.height,out)==(size_t)actual.height);fclose(out);
 NSRect rect=[view convertRect:[view bounds] toView:nil];
 printf("{\"event\":\"reference\",\"pid\":%d,\"name\":\"%s\",\"width\":%.0f,\"height\":%.0f,\"pixel_width\":%d,\"pixel_height\":%d,\"stride\":%d,\"reference_x\":%.0f,\"reference_y\":%.0f}\n",getpid(),name,width,height,actual.width,actual.height,actual.stride,rect.origin.x,[window frame].size.height-NSMaxY(rect));fflush(stdout);
 struct pollfd input={STDIN_FILENO,POLLIN,0};NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:10];while(poll(&input,1,0)==0&&[deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);
 char reply[32];assert(fgets(reply,sizeof(reply),stdin)&&!strcmp(reply,"captured\n"));
 check(p,"whole-native-image-size",actual.width==lround(width*p->scale)&&actual.height==lround(height*p->scale));p->images++;
 check(p,"native-draw-consumes-invalidation",!dirty);
 NXSToolbarState state=nxs_control_toolbar_state(p->control);
 check(p,"native-toolbar-preferred-height",state.preferred.height==height);
 check(p,"native-visible-item-count",state.visible_count==[[toolbar visibleItems] count]);
 for(unsigned i=0;i<count;i++) {
  NSToolbarItem *item=[[toolbar items] objectAtIndex:i];NXSRect rect=[[toolbar visibleItems] containsObject:item]?native_rect(view,[(id)item _backView]):(NXSRect){0};
  check(p,"native-item-geometry",same_rect(nxs_control_toolbar_item_rect(p->control,data[i].identifier),rect));
 }
 [view removeFromSuperview];[window close];[window release];
}
int main(int argc,char **argv)
{
 if(argc>1&&!strcmp(argv[1],"--expect-no-toolbar")) {
  assert(!nxs_control_toolbar_capabilities()&&!nxs_control_create(NXS_TOOLBAR,NULL,NULL,NULL));
  assert(!nxs_control_toolbar_items(NULL,NULL,0,0,0));assert(nxs_control_toolbar_state(NULL).highlighted==-1);assert(!nxs_control_toolbar_item_rect(NULL,1).width);
  puts("{\"older_provider_without_toolbar\":true}");return 0;
 }
 NSAutoreleasePool *pool=[NSAutoreleasePool new];struct Probe p={.directory=argc>1?argv[1]:NULL,.scale=argc>2?atof(argv[2]):1};assert(p.directory);
 check(&p,"native-toolbar-capability",nxs_control_toolbar_capabilities()==NXS_TOOLBAR_ITEMS);
 Method method=class_getInstanceMethod([NSToolbar class],@selector(initWithIdentifier:));original_init=method_setImplementation(method,(IMP)witness_init);
 p.control=nxs_control_create(NXS_TOOLBAR,changed,pump,&p);assert(p.control);method_setImplementation(method,original_init);NSToolbar *toolbar=observed;
 check(&p,"actual-native-toolbar",[toolbar class]==[NSToolbar class]&&[[toolbar _toolbarView] isKindOfClass:NSClassFromString(@"GSToolbarView")]);
 NXSToolbarItem items[]={{sizeof(NXSToolbarItem),NXS_TOOLBAR_ACTION,1,"Back","Go back","common_ArrowLeft",1,0},{sizeof(NXSToolbarItem),NXS_TOOLBAR_ACTION,large_identifier,"日本語","Forward","common_ArrowRight",1,0},{sizeof(NXSToolbarItem),NXS_TOOLBAR_FLEXIBLE_SPACE,3,NULL,NULL,NULL,0,0},{sizeof(NXSToolbarItem),NXS_TOOLBAR_ACTION,4,"Disabled",NULL,NULL,0,0},{sizeof(NXSToolbarItem),NXS_TOOLBAR_ACTION,5,"Last",NULL,NULL,1,0}};
 NXSControlConfig config={.size=sizeof(config),.width=600,.height=64,.enabled=1};assert(nxs_control_sync(p.control,&config));
 assert(nxs_control_toolbar_items(p.control,items,5,NXS_TOOLBAR_IMAGE_AND_LABEL,NXS_TOOLBAR_REGULAR));check(&p,"programmatic-model-emits-no-action",p.actions==0);
 compare(&p,"initial",items,5,1,1,600);
 NXSRect rect=nxs_control_toolbar_item_rect(p.control,large_identifier);p.press=rect;p.phase=1;p.loops=0;assert(nxs_control_track_clicks(p.control,rect.x+rect.width/2,rect.y+rect.height/2,0,1));
 check(&p,"native-button-action-keeps-64-bit-command",p.actions==1&&nxs_control_toolbar_state(p.control).command==large_identifier&&nxs_control_state(p.control).value==1);
 config.enabled=0;assert(nxs_control_sync(p.control,&config));p.press=rect;p.phase=1;p.loops=0;
 assert(!nxs_control_track_clicks(p.control,rect.x+rect.width/2,rect.y+rect.height/2,0,1));p.phase=0;
 check(&p,"disabled-toolbar-has-no-action",p.actions==1&&![[[toolbar items] objectAtIndex:1] isEnabled]);
 config.enabled=1;assert(nxs_control_sync(p.control,&config));
 check(&p,"reenabled-toolbar-native-validation",[[[toolbar items] objectAtIndex:1] isEnabled]);
 NSToolbarItem *retained=[[toolbar items] objectAtIndex:0];
 NXSToolbarItem bad[5];memcpy(bad,items,sizeof(items));bad[1].identifier=1;check(&p,"duplicate-ids-rejected",!nxs_control_toolbar_items(p.control,bad,5,1,1));
 bad[1]=items[1];bad[1].title="\xff";check(&p,"invalid-text-rejected",!nxs_control_toolbar_items(p.control,bad,5,1,1));
 bad[1]=items[1];bad[1].image_name="nxs_missing_image";check(&p,"missing-native-image-rejected",!nxs_control_toolbar_items(p.control,bad,5,1,1));
 check(&p,"invalid-model-keeps-native-items-and-command",[[toolbar items] objectAtIndex:0]==retained&&nxs_control_toolbar_state(p.control).command==large_identifier&&p.actions==1);
 NXSToolbarItem order[]={items[1],items[0],items[2],items[3],items[4],{sizeof(NXSToolbarItem),NXS_TOOLBAR_SPACE,6,NULL,NULL,NULL,0,0},{sizeof(NXSToolbarItem),NXS_TOOLBAR_SEPARATOR,7,NULL,NULL,NULL,0,0}};order[1].title="Renamed";assert(nxs_control_toolbar_items(p.control,order,7,3,2));
 check(&p,"reorder-retains-native-button-items",[[toolbar items] objectAtIndex:1]==retained&&p.actions==1);compare(&p,"reordered",order,7,3,2,600);
 rect=nxs_control_toolbar_item_rect(p.control,4);p.press=rect;p.phase=1;p.loops=0;assert(nxs_control_track_clicks(p.control,rect.x+rect.width/2,rect.y+rect.height/2,0,1));
 check(&p,"disabled-item-has-no-action",p.actions==1);
 assert(nxs_control_toolbar_items(p.control,items,5,1,1));compare(&p,"overflow",items,5,1,1,190);
 NXSToolbarState state=nxs_control_toolbar_state(p.control);check(&p,"native-overflow-button",state.visible_count<state.count&&state.overflow.width>0);
 p.wanted=5;p.phase=2;p.loops=0;rect=state.overflow;assert(nxs_control_set_screen_origin(p.control,400,400));assert(nxs_control_track_clicks(p.control,rect.x+rect.width/2,rect.y+rect.height/2,0,1));
 check(&p,"native-overflow-menu-activates-original-item",p.actions==2&&nxs_control_toolbar_state(p.control).command==5&&!nxs_control_toolbar_state(p.control).flags);
 p.wanted=0;p.phase=2;p.loops=0;rect=nxs_control_toolbar_state(p.control).overflow;
 assert(nxs_control_track_clicks(p.control,rect.x+rect.width/2,rect.y+rect.height/2,0,1));
 check(&p,"native-overflow-cancel-preserves-command",p.actions==2&&nxs_control_toolbar_state(p.control).command==5&&!nxs_control_toolbar_state(p.control).flags);
 assert(nxs_control_toolbar_items(p.control,NULL,0,1,1));check(&p,"empty-model",nxs_control_toolbar_state(p.control).count==0&&nxs_control_toolbar_state(p.control).command==0);compare(&p,"empty",NULL,0,1,1,190);
 assert(nxs_control_toolbar_items(p.control,items,5,1,1));config.width=600;config.height=nxs_control_toolbar_state(p.control).preferred.height;assert(nxs_control_sync(p.control,&config));
 rect=nxs_control_toolbar_item_rect(p.control,1);p.press=rect;p.phase=1;p.loops=0;
 assert(nxs_control_track_clicks(p.control,rect.x+rect.width/2,rect.y+rect.height/2,0,1));
 check(&p,"restored-toolbar-native-action",p.actions==3&&nxs_control_toolbar_state(p.control).command==1);
 check(&p,"unknown-item-geometry",!nxs_control_toolbar_item_rect(p.control,42).width);check(&p,"destroy",nxs_control_destroy(p.control));
 [reference_toolbar setDelegate:nil];[reference_toolbar release];[reference_delegate release];
 printf("{\"passed\":%u,\"images\":%u,\"api_bytes\":%zu}\n",p.checks,p.images,sizeof(NXSNativeUIAPI));[pool drain];return 0;
}
