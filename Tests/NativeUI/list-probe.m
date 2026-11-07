/* Shared flat lists compared with an independent ordinary NSBrowser.
 * GPL-2.0-or-later. */
#import <AppKit/AppKit.h>
#include "NativeUI.h"
#include "Bridge/Protocol.h"
#include <assert.h>
#include <float.h>
#include <math.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <objc/runtime.h>
_Static_assert(offsetof(NXSNativeUIAPI,control_list_items)==528,"Preserve the prior provider prefix");
_Static_assert(offsetof(NXSNativeUIAPI,control_scroll_geometry)==568,"Preserve the list provider prefix");
_Static_assert(sizeof(NXSListState)==88,"Typed native list state");
static IMP original_init;static NSBrowser *observed;
static id witness_init(id self,SEL selector,NSRect frame)
{id result=((id (*)(id,SEL,NSRect))original_init)(self,selector,frame);observed=result;return result;}
@interface ReferenceData : NSObject {
 @public NSArray *rows;unsigned actions;
}
@end
@implementation ReferenceData
- (void)dealloc {[rows release];[super dealloc];}
- (NSInteger)browser:(NSBrowser *)browser numberOfRowsInColumn:(NSInteger)column {return column?0:[rows count];}
- (void)browser:(NSBrowser *)browser willDisplayCell:(NSBrowserCell *)cell atRow:(NSInteger)row column:(NSInteger)column
{NSDictionary *value=[rows objectAtIndex:row];[cell setStringValue:[value objectForKey:@"title"]];[cell setLeaf:YES];[cell setEnabled:[[value objectForKey:@"enabled"] boolValue]];}
- (void)changed:(id)sender {actions++;}
@end
struct Probe {
 NXSControl *control;NSBrowser *native,*reference;NSWindow *window;ReferenceData *data;
 NXSListItem items[32];unsigned count,flags,checks,images,callbacks,phase,loops,modifiers;
 uint64_t action_base;double scale,x,y;const char *directory;
};
static uint64_t identifier(unsigned i){return UINT64_C(0xf000000000000001)+i;}
static void check(struct Probe *p,const char *name,BOOL value)
{printf("{\"case\":\"%s\",\"passed\":%s}\n",name,value?"true":"false");fflush(stdout);assert(value);p->checks++;}
static uint64_t cell_id(struct Probe *p,NSMatrix *matrix,NSCell *cell)
{NSInteger row,column;return cell&&[matrix getRow:&row column:&column ofCell:cell]?p->items[row].identifier:0;}
static void state(struct Probe *p,const char *name)
{
 NSMatrix *native=[p->native matrixInColumn:0],*ref=[p->reference matrixInColumn:0];NXSListState actual=nxs_control_list_state(p->control);
 uint64_t selected[32]={0};size_t count=nxs_control_list_selection(p->control,selected,32);NSArray *expected=[ref selectedCells];
 BOOL equal=count==[expected count]&&actual.selected_count==count&&actual.count==p->count&&actual.flags==p->flags;
 for(size_t i=0;i<count&&equal;i++)equal=selected[i]==cell_id(p,ref,[expected objectAtIndex:i]);
 if(!equal||actual.primary!=cell_id(p,ref,[ref selectedCell])||actual.key_cell!=cell_id(p,ref,[ref keyCell])||actual.actions!=p->action_base+p->data->actions)
 fprintf(stderr,"state %s count=%zu expected=%lu primary=%llu expected=%llu key=%llu expected=%llu actions=%llu base=%llu reference=%u callbacks=%u\n",name,count,(unsigned long)[expected count],(unsigned long long)actual.primary,(unsigned long long)cell_id(p,ref,[ref selectedCell]),(unsigned long long)actual.key_cell,(unsigned long long)cell_id(p,ref,[ref keyCell]),(unsigned long long)actual.actions,(unsigned long long)p->action_base,p->data->actions,p->callbacks);
 check(p,name,equal&&actual.primary==cell_id(p,ref,[ref selectedCell])&&actual.key_cell==cell_id(p,ref,[ref keyCell])&&
  actual.actions==p->action_base+p->data->actions&&actual.actions==p->callbacks&&[p->native class]==[NSBrowser class]&&
  [native isKindOfClass:[NSMatrix class]]&&[native numberOfRows]==p->count);
}
static void changed(void *context,int event,const NXSControlState *value)
{
 struct Probe *p=context;p->callbacks++;assert(event==NXS_VALUE_CHANGED&&value->tracking);
 assert(!nxs_control_destroy(p->control)&&!nxs_control_list_items(p->control,NULL,0,0,0)&&!nxs_control_list_scroll(p->control,0,0));
 NXSControlConfig c={.size=sizeof(c),.width=180,.height=96,.enabled=1};assert(!nxs_control_sync(p->control,&c));
}
static void pump(void *context)
{
 struct Probe *p=context;assert(++p->loops<2000);
 assert(!nxs_control_destroy(p->control)&&!nxs_control_list_scroll(p->control,0,0));
 nxs_control_send(p->control,NXS_RELEASE,p->x,p->y,p->modifiers);p->phase++;
}
static void model(struct Probe *p,unsigned count,unsigned flags,uint64_t selected)
{
 if(p->window){[p->window close];[p->window release];[p->reference release];[p->data release];}
 p->count=count;p->flags=flags;p->action_base=nxs_control_list_state(p->control).actions;
 NSMutableArray *rows=[NSMutableArray array];
 for(unsigned i=0;i<count;i++) {
  p->items[i]=(NXSListItem){sizeof(NXSListItem),identifier(i),i==0?"Alpha":i==1?"Bravo":i==2?"Charlie":i==3?"Delta":"Long row",i!=1,!!(selected&(UINT64_C(1)<<i))};
  [rows addObject:@{@"title":[NSString stringWithUTF8String:p->items[i].title],@"enabled":@(p->items[i].enabled)}];
 }
 assert(nxs_control_list_items(p->control,p->items,count,flags,0));NXSControlConfig config={.size=sizeof(config),.width=180,.height=96,.enabled=1};assert(nxs_control_sync(p->control,&config));
 p->data=[ReferenceData new];p->data->rows=[rows copy];p->reference=[[NSBrowser alloc] initWithFrame:NSMakeRect(0,0,180,96)];
 [p->reference setMaxVisibleColumns:1];[p->reference setMinColumnWidth:1];[p->reference setTitled:NO];[p->reference setSeparatesColumns:NO];[p->reference setHasHorizontalScroller:NO];
 [p->reference setAllowsEmptySelection:YES];[p->reference setAllowsMultipleSelection:!!(flags&NXS_LIST_MULTIPLE)];
 [p->reference setDelegate:p->data];[p->reference setTarget:p->data];[p->reference setAction:@selector(changed:)];[p->reference loadColumnZero];
 NSMatrix *matrix=[p->reference matrixInColumn:0];[matrix deselectAllCells];for(unsigned i=0;i<count;i++)if(p->items[i].selected)[matrix selectCellAtRow:i column:0];
 p->window=[[NSWindow alloc] initWithContentRect:[p->reference bounds] styleMask:NSTitledWindowMask backing:NSBackingStoreBuffered defer:NO];
 [p->window setReleasedWhenClosed:NO];[p->window setBackgroundColor:[NSColor controlBackgroundColor]];[[p->window contentView] addSubview:p->reference];
 [p->window setTitle:@"Native list input reference"];[p->window makeKeyAndOrderFront:nil];[p->window makeFirstResponder:p->reference];state(p,"original-native-list-model-and-identities");
}
static void key(struct Probe *p,unsigned logical,unsigned key_code,unsigned modifiers)
{
 NXSKeyEvent input={.size=sizeof(input),.type=NXS_KEY_DOWN,.key=logical,.modifiers=modifiers};
 assert(nxs_control_focus(p->control,1));nxs_control_key(p->control,&input);input.type=NXS_KEY_UP;nxs_control_key(p->control,&input);
 assert(nxs_control_focus(p->control,0));[p->window makeFirstResponder:p->reference];
 printf("{\"event\":\"reference-key-ready\",\"title\":\"%s\",\"code\":%u,\"modifiers\":%u}\n",[[p->window title] UTF8String],key_code,modifiers);fflush(stdout);
 struct pollfd poll_input={STDIN_FILENO,POLLIN,0};NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:10];
 while(poll(&poll_input,1,0)==0&&[deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);
 char reply[32];assert(fgets(reply,sizeof(reply),stdin)&&!strcmp(reply,"key-done\n"));
 nxs_native_ui_dispatch_events(.05);state(p,"keyboard-selection-action-and-key-cell-match-ordinary-native-list");
}
static void pointer_at(struct Probe *p,double x,double y,NSPoint location,unsigned modifiers)
{
 p->x=x;p->y=y;p->phase=p->loops=0;p->modifiers=modifiers;
 assert(nxs_control_track_clicks(p->control,x,y,modifiers,1));assert(p->phase);
 assert(nxs_control_focus(p->control,0));
 printf("{\"event\":\"reference-pointer-ready\",\"title\":\"%s\",\"x\":%g,\"y\":%g,\"modifiers\":%u}\n",[[p->window title] UTF8String],location.x,[p->window frame].size.height-location.y,modifiers);fflush(stdout);
 struct pollfd poll_input={STDIN_FILENO,POLLIN,0};NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:10];
 while(poll(&poll_input,1,0)==0&&[deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);
 char reply[32];assert(fgets(reply,sizeof(reply),stdin)&&!strcmp(reply,"pointer-done\n"));
 deadline=[NSDate dateWithTimeIntervalSinceNow:3];
 while(p->action_base+p->data->actions<nxs_control_list_state(p->control).actions&&[deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);
 nxs_native_ui_dispatch_events(.01);state(p,"pointer-selection-actions-match-original-native-window");
}
static void pointer(struct Probe *p,unsigned row,unsigned modifiers)
{
 NXSRect rect=nxs_control_list_item_rect(p->control,p->items[row].identifier);assert(rect.width>0&&rect.height>0);
 NSMatrix *matrix=[p->reference matrixInColumn:0];NSRect cell=[matrix cellFrameAtRow:row column:0];
 NSPoint location=[matrix convertPoint:NSMakePoint(NSMidX(cell),NSMidY(cell)) toView:nil];
 pointer_at(p,rect.x+rect.width/2,rect.y+rect.height/2,location,modifiers);
}

static void compare(struct Probe *p,const char *name,BOOL focused)
{
 /* Input is checked against p->reference. Render its resulting state in a
  * fresh ordinary control so old transparent-cell damage is not the oracle. */
 NSMatrix *input_matrix=[p->reference matrixInColumn:0];NSArray *input_selected=[input_matrix selectedCells];
 NSRect visible=[input_matrix visibleRect];NSSize content=[input_matrix bounds].size;
 struct NXSListWireState expected={.count=[input_matrix numberOfRows],.selected_count=[input_selected count],
  .flags=[p->reference allowsMultipleSelection]?NXS_LIST_MULTIPLE:0,.primary=cell_id(p,input_matrix,[input_matrix selectedCell]),
  .key_cell=cell_id(p,input_matrix,[input_matrix keyCell]),.actions=p->action_base+p->data->actions,
  .visible={visible.origin.x,visible.origin.y,visible.size.width,visible.size.height},.content_width=content.width,.content_height=content.height};
 char state_path[1024];snprintf(state_path,sizeof(state_path),"%s/%s-state.bin",p->directory,name);FILE *state_file=fopen(state_path,"wb");assert(state_file);
 assert(fwrite(&expected,sizeof(expected),1,state_file)==1);
 for(NSCell *cell in input_selected){uint64_t identity=cell_id(p,input_matrix,cell);assert(fwrite(&identity,sizeof(identity),1,state_file)==1);}fclose(state_file);
 NSScrollView *input_scroll=(NSScrollView *)[[input_matrix superview] superview];NSScroller *input_scroller=[input_scroll verticalScroller];
 NSClipView *input_clip=[input_scroll contentView];
 NSRect clip_rect=[input_clip convertRect:[input_clip bounds] toView:p->reference];
 NSSize client=[NSScrollView contentSizeForFrameSize:[input_scroll frame].size hasHorizontalScroller:NO hasVerticalScroller:NO borderType:[input_scroll borderType]];
 NSPoint minimum=[input_clip constrainScrollPoint:NSMakePoint(-FLT_MAX,-FLT_MAX)],maximum=[input_clip constrainScrollPoint:NSMakePoint(FLT_MAX,FLT_MAX)];
 NXSScrollGeometry geometry={.size=sizeof(geometry)},wanted={0};wanted.size=sizeof(wanted);
 wanted.clip=(NXSRect){clip_rect.origin.x,[p->reference isFlipped]?clip_rect.origin.y:[p->reference bounds].size.height-NSMaxY(clip_rect),clip_rect.size.width,clip_rect.size.height};
 wanted.client=(NXSSize){client.width,client.height};wanted.minimum=(NXSPoint){minimum.x,minimum.y};wanted.maximum=(NXSPoint){maximum.x,maximum.y};
 uint64_t actions=nxs_control_list_state(p->control).actions;
 check(p,"native-scroll-geometry-matches-independent-ordinary-list",nxs_control_scroll_geometry(p->control,&geometry)&&geometry.size==sizeof(geometry)&&
   !memcmp(&geometry.clip,&wanted.clip,sizeof(geometry)-offsetof(NXSScrollGeometry,clip))&&nxs_control_list_state(p->control).actions==actions);
 snprintf(state_path,sizeof(state_path),"%s/%s-geometry.bin",p->directory,name);state_file=fopen(state_path,"wb");assert(state_file);assert(fwrite(&wanted,sizeof(wanted),1,state_file)==1);fclose(state_file);
 NSRect arrow=[input_scroller convertRect:[input_scroller rectForPart:NSScrollerIncrementLine] toView:p->reference];
 struct NXSRectD scroll_part={arrow.origin.x,[p->reference isFlipped]?arrow.origin.y:[p->reference bounds].size.height-NSMaxY(arrow),arrow.size.width,arrow.size.height};
 snprintf(state_path,sizeof(state_path),"%s/%s-scroll-part.bin",p->directory,name);state_file=fopen(state_path,"wb");assert(state_file);assert(fwrite(&scroll_part,sizeof(scroll_part),1,state_file)==1);fclose(state_file);


 ReferenceData *data=[ReferenceData new];NSMutableArray *rows=[NSMutableArray array];
 for(NSBrowserCell *cell in [input_matrix cells])[rows addObject:@{@"title":[cell stringValue],@"enabled":@([cell isEnabled])}];
 data->rows=[rows copy];NSSize frame=[p->reference frame].size;
 NSBrowser *reference=[[NSBrowser alloc] initWithFrame:NSMakeRect(0,0,frame.width,frame.height)];
 [reference setMaxVisibleColumns:1];[reference setMinColumnWidth:1];[reference setTitled:NO];[reference setSeparatesColumns:NO];[reference setHasHorizontalScroller:NO];
 [reference setAllowsEmptySelection:YES];[reference setAllowsMultipleSelection:[p->reference allowsMultipleSelection]];[reference setDelegate:data];[reference loadColumnZero];
 NSMatrix *snapshot=[reference matrixInColumn:0];[snapshot deselectAllCells];
 for(NSUInteger i=0;i<[rows count];i++)if([input_selected containsObject:[input_matrix cellAtRow:i column:0]])[snapshot selectCellAtRow:i column:0];
 NSInteger key_row,key_column;BOOL key=[input_matrix getRow:&key_row column:&key_column ofCell:[input_matrix keyCell]];
 if(key)[snapshot setKeyCell:[snapshot cellAtRow:key_row column:0]];
 NSWindow *window=[[NSWindow alloc] initWithContentRect:[reference bounds] styleMask:NSTitledWindowMask backing:NSBackingStoreBuffered defer:NO];
 [window setReleasedWhenClosed:NO];[window setBackgroundColor:[NSColor controlBackgroundColor]];[[window contentView] addSubview:reference];
 NSClipView *clip=(NSClipView *)[snapshot superview];[clip scrollToPoint:[clip constrainScrollPoint:[input_matrix visibleRect].origin]];[(NSScrollView *)[clip superview] reflectScrolledClipView:clip];
 [window setTitle:[NSString stringWithFormat:@"Native list reference %s",name]];[window makeKeyAndOrderFront:nil];[NSApp activateIgnoringOtherApps:YES];
 printf("{\"event\":\"reference-ready\",\"name\":\"%s\"}\n",name);fflush(stdout);
 struct pollfd poll_input={STDIN_FILENO,POLLIN,0};NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:10];
 while(poll(&poll_input,1,0)==0&&[deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);
 char reply[32];assert(fgets(reply,sizeof(reply),stdin)&&!strcmp(reply,"ready\n"));
 nxs_native_ui_dispatch_events(.02);
 NSButton *other=[[NSButton alloc] initWithFrame:NSMakeRect(-100,-100,1,1)];[[window contentView] addSubview:other];
 assert([window makeFirstResponder:focused?(NSView *)reference:other]);
 /* A full reference image needs the matrix background as well as dirty cells.
  * Repainting only a transparent cell title can composite its glyphs twice. */

 assert(nxs_control_focus(p->control,focused));check(p,"native-descendant-matrix-focus-is-recognized",nxs_control_focused(p->control)==focused);
 NXSBitmap actual=nxs_control_draw(p->control,p->scale);assert(actual.pixels);
 /* The independent real window must own the application's logical key window
  * while it is measured; the provider pixels above retain their focused image. */
 assert(nxs_control_focus(p->control,0));
 [window makeFirstResponder:focused?(NSView *)reference:other];
 [[reference matrixInColumn:0] setNeedsDisplay:YES];[window display];
 [window flushWindow];
 char path[1024];snprintf(path,sizeof(path),"%s/%s-native.argb",p->directory,name);FILE *file=fopen(path,"wb");assert(file);assert(fwrite(actual.pixels,actual.stride,actual.height,file)==(size_t)actual.height);fclose(file);
 NSRect crop=[reference convertRect:[reference bounds] toView:nil];NSSize outer=[window frame].size;
 printf("{\"event\":\"reference\",\"name\":\"%s\",\"width\":%g,\"height\":%g,\"pixel_width\":%d,\"pixel_height\":%d,\"stride\":%d,\"window_pixel_width\":%ld,\"window_pixel_height\":%ld,\"crop_x\":%g,\"crop_y\":%g}\n",name,frame.width,frame.height,actual.width,actual.height,actual.stride,lround(outer.width*p->scale),lround(outer.height*p->scale),crop.origin.x,outer.height-NSMaxY(crop));fflush(stdout);
 /* Freeze the completed ordinary window paint until screencopy finishes.
  * Servicing pending focus damage here can repaint a transparent title over
  * its prior glyphs after the complete matrix image was already produced. */
 deadline=[NSDate dateWithTimeIntervalSinceNow:10];while(poll(&poll_input,1,5)==0&&[deadline timeIntervalSinceNow]>0){}
 assert(fgets(reply,sizeof(reply),stdin)&&!strcmp(reply,"captured\n"));p->images++;[other removeFromSuperview];[other release];[window close];[window release];[reference release];[data release];
}
int main(int argc,char **argv)
{
 NSAutoreleasePool *pool=[NSAutoreleasePool new];
 if(argc>1&&!strcmp(argv[1],"--expect-no-scroll")) {
  assert(nxs_native_ui_api()->size==568&&!nxs_control_scroll_capabilities()&&nxs_control_list_capabilities()==NXS_LIST_ITEMS);
  NXSControl *list=nxs_control_create(NXS_LISTBOX,NULL,NULL,NULL),*text=nxs_control_create(NXS_TEXTAREA,NULL,NULL,NULL);assert(list&&text);
  NXSScrollGeometry geometry,saved;memset(&geometry,0x6a,sizeof(geometry));geometry.size=sizeof(geometry);saved=geometry;
  assert(!nxs_control_scroll_geometry(list,&geometry)&&!memcmp(&geometry,&saved,sizeof(geometry)));
  assert(!nxs_control_scroll_geometry(text,&geometry)&&!memcmp(&geometry,&saved,sizeof(geometry)));
  assert(nxs_control_text_geometry(text,&geometry)&&nxs_control_destroy(list)&&nxs_control_destroy(text));
  puts("{\"older_list_provider_without_scroll_geometry\":true}");[pool drain];return 0;
 }
 if(argc>1&&!strcmp(argv[1],"--expect-no-list")) {
  assert(!nxs_control_list_capabilities()&&!nxs_control_create(NXS_LISTBOX,NULL,NULL,NULL));
  assert(!nxs_control_list_items(NULL,NULL,0,0,0)&&!nxs_control_list_scroll(NULL,0,0)&&!nxs_control_list_selection(NULL,NULL,0));
  printf("{\"older_provider_without_lists\":true}\n");[pool drain];return 0;
 }
 assert(argc>2&&nxs_control_list_capabilities()==NXS_LIST_ITEMS&&nxs_control_scroll_capabilities()==NXS_SCROLL_GEOMETRY);struct Probe p={.directory=argv[1],.scale=atof(argv[2])};
 NXSControl *bootstrap=nxs_control_create(NXS_BUTTON,NULL,NULL,NULL);assert(bootstrap&&nxs_control_destroy(bootstrap));
 NXSScrollGeometry invalid={.size=sizeof(invalid)};
 check(&p,"invalid-scroll-geometry-control-and-buffer-rejected",!nxs_control_scroll_geometry(NULL,&invalid));
 NXSControl *text=nxs_control_create(NXS_TEXTAREA,NULL,NULL,NULL);assert(text);
 NXSTextGeometry previous={.size=sizeof(previous)};NXSScrollGeometry shared={.size=sizeof(shared)};
 check(&p,"text-and-list-share-one-scroll-geometry-entry",nxs_control_text_geometry(text,&previous)&&nxs_control_scroll_geometry(text,&shared)&&
   previous.size==shared.size&&!memcmp(&previous.clip,&shared.clip,sizeof(shared)-offsetof(NXSScrollGeometry,clip)));
 assert(nxs_control_destroy(text));
 Method init=class_getInstanceMethod([NSBrowser class],@selector(initWithFrame:));original_init=method_setImplementation(init,(IMP)witness_init);
 p.control=nxs_control_create(NXS_LISTBOX,changed,pump,&p);assert(p.control);p.native=observed;method_setImplementation(init,original_init);
 invalid.size=sizeof(invalid)-1;
 check(&p,"short-scroll-geometry-buffer-rejected",!nxs_control_scroll_geometry(p.control,&invalid)&&!nxs_control_scroll_geometry(p.control,NULL));
 check(&p,"actual-native-browser-control",[p.native class]==[NSBrowser class]);
 model(&p,4,0,1);compare(&p,"single",YES);key(&p,NXS_KEY_DOWN_ARROW,108,0);compare(&p,"single-key",YES);
 key(&p,NXS_KEY_DOWN_ARROW,108,0);compare(&p,"single-next",YES);
 pointer(&p,0,0);compare(&p,"single-pointer",YES);
 model(&p,4,NXS_LIST_MULTIPLE,5);compare(&p,"multiple",YES);key(&p,NXS_KEY_DOWN_ARROW,108,NXS_SHIFT);compare(&p,"multiple-shift",YES);
 NSMatrix *same=[p.native matrixInColumn:0];NSCell *same_cell=[same cellAtRow:0 column:0];
 check(&p,"unchanged-model-keeps-native-cell-and-key-context",nxs_control_list_items(p.control,p.items,p.count,p.flags,0)&&[p.native matrixInColumn:0]==same&&[same cellAtRow:0 column:0]==same_cell);state(&p,"unchanged-model-keeps-native-selection-and-action-count");
 pointer(&p,3,NXS_SHIFT);compare(&p,"multiple-pointer",YES);
 NXSListItem bad=p.items[0];bad.identifier=p.items[1].identifier;NXSListItem saved=p.items[0];p.items[0]=bad;
 check(&p,"duplicate-identities-rejected-without-model-mutation",!nxs_control_list_items(p.control,p.items,p.count,p.flags,0));p.items[0]=saved;state(&p,"rejected-model-keeps-native-state");
 check(&p,"multiple-selection-in-single-mode-is-rejected",!nxs_control_list_items(p.control,p.items,p.count,0,0));
 const char *saved_title=p.items[0].title;p.items[0].title="\xff";check(&p,"invalid-UTF8-list-model-is-atomic",!nxs_control_list_items(p.control,p.items,p.count,p.flags,0));p.items[0].title=saved_title;
 state(&p,"invalid-inputs-preserve-actual-native-state");
 check(&p,"unknown-key-and-flags-rejected",!nxs_control_list_items(p.control,p.items,p.count,p.flags,UINT64_MAX)&&!nxs_control_list_items(p.control,p.items,p.count,2,0));
 uint64_t small=UINT64_MAX;size_t count=nxs_control_list_selection(p.control,NULL,0);if(count>1)check(&p,"small-selection-buffer-is-untouched",nxs_control_list_selection(p.control,&small,1)==count&&small==UINT64_MAX);
 model(&p,24,NXS_LIST_MULTIPLE,1);compare(&p,"scrollable",YES);
 assert(nxs_control_list_scroll(p.control,0,120));NSMatrix *matrix=[p.reference matrixInColumn:0];NSClipView *clip=(NSClipView *)[matrix superview];[clip scrollToPoint:[clip constrainScrollPoint:NSMakePoint(0,120)]];[(NSScrollView *)[clip superview] reflectScrolledClipView:clip];
 NXSListState scroll=nxs_control_list_state(p.control);check(&p,"original-native-scroll-position",scroll.visible.y==[matrix visibleRect].origin.y&&scroll.visible.y>0);compare(&p,"scrolled",YES);
 uint64_t before=nxs_control_list_state(p.control).actions;
 check(&p,"wheel-is-dispatched-to-native-list-responder",nxs_control_wheel(p.control,&(NXSWheelEvent){.size=sizeof(NXSWheelEvent),.x=90,.y=50,.delta_y=20}));
 NXSListState wheel=nxs_control_list_state(p.control);check(&p,"wheel-scrolls-native-clip-without-selection-action",wheel.visible.y>scroll.visible.y&&wheel.actions==before);
 [clip scrollToPoint:[clip constrainScrollPoint:NSMakePoint(wheel.visible.x,wheel.visible.y)]];[(NSScrollView *)[clip superview] reflectScrolledClipView:clip];compare(&p,"wheel",YES);
 NXSControlConfig disabled={.size=sizeof(disabled),.width=180,.height=96,.enabled=0};assert(nxs_control_sync(p.control,&disabled));
 [p.reference setEnabled:NO];[matrix setEnabled:NO];for(NSCell *cell in [matrix cells])[cell setEnabled:NO];
 check(&p,"disabled-list-rejects-key-input",nxs_control_key(p.control,&(NXSKeyEvent){.size=sizeof(NXSKeyEvent),.key=NXS_KEY_DOWN_ARROW})==NXS_INPUT_UNHANDLED);compare(&p,"disabled",NO);
 assert(nxs_control_list_scroll(p.control,0,0));[clip scrollToPoint:[clip constrainScrollPoint:NSZeroPoint]];[(NSScrollView *)[clip superview] reflectScrolledClipView:clip];
 NSScrollView *native_scroll=(NSScrollView *)[[[p.native matrixInColumn:0] superview] superview];
 NSScroller *native_scroller=[native_scroll verticalScroller];NSRect part=[native_scroller rectForPart:NSScrollerIncrementLine];
 NSPoint point=[native_scroller convertPoint:NSMakePoint(NSMidX(part),NSMidY(part)) toView:p.native];
 NSScrollView *ref_scroll=(NSScrollView *)[[matrix superview] superview];NSScroller *ref_scroller=[ref_scroll verticalScroller];NSRect ref_part=[ref_scroller rectForPart:NSScrollerIncrementLine];
 NSPoint location=[ref_scroller convertPoint:NSMakePoint(NSMidX(ref_part),NSMidY(ref_part)) toView:nil];
 pointer_at(&p,point.x,[p.native isFlipped]?point.y:[p.native bounds].size.height-point.y,location,0);
 check(&p,"disabled-rows-retain-original-native-scrollbar-input",nxs_control_list_state(p.control).visible.y==[matrix visibleRect].origin.y&&nxs_control_list_state(p.control).visible.y>0);compare(&p,"disabled-scrolled",NO);

 disabled.enabled=1;assert(nxs_control_sync(p.control,&disabled));model(&p,0,0,0);compare(&p,"empty",NO);
 check(&p,"unknown-row-geometry-is-empty",!nxs_control_list_item_rect(p.control,UINT64_MAX).width);
 check(&p,"nonfinite-scroll-rejected",!nxs_control_list_scroll(p.control,NAN,0));
 check(&p,"native-list-destroy",nxs_control_destroy(p.control));[p.window close];[p.window release];[p.reference release];[p.data release];
 printf("{\"passed\":%u,\"images\":%u,\"api_bytes\":%zu}\n",p.checks,p.images,sizeof(NXSNativeUIAPI));[pool drain];return 0;
}
