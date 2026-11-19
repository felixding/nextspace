/* Shared radio groups against independent ordinary native matrices.
 * GPL-2.0-or-later. */
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
_Static_assert(offsetof(NXSNativeUIAPI,control_radio_items)==480,"Existing provider prefix");
_Static_assert(offsetof(NXSNativeUIAPI,control_perform_click)==520,"Existing 520-byte provider prefix");
_Static_assert(sizeof(NXSRadioState)==40,"Radio state ABI");
static IMP original_init;static NSMatrix *observed;
static id witness_init(id self,SEL selector,NSRect frame,NSMatrixMode mode,Class kind,NSInteger rows,NSInteger columns)
{
  id matrix=((id (*)(id,SEL,NSRect,NSMatrixMode,Class,NSInteger,NSInteger))original_init)(self,selector,frame,mode,kind,rows,columns);
  observed=matrix;return matrix;
}
struct Probe {
  NXSControl *control;NSMatrix *native;NXSRadioItem items[4];
  unsigned checks,images,callbacks,phase,loops;double scale,x,y;int enabled;
  const char *directory;
};
static uint64_t identifier(unsigned index){return UINT64_C(0x1000000000000001)+index;}
static void check(struct Probe *p,const char *name,BOOL passed)
{printf("{\"case\":\"%s\",\"passed\":%s}\n",name,passed?"true":"false");fflush(stdout);assert(passed);p->checks++;}
static NSInteger index_of(struct Probe *p,uint64_t identity)
{for(unsigned i=0;i<4;i++)if(p->items[i].identifier==identity)return i;return -1;}
static void state(struct Probe *p,const char *name,uint64_t selected,uint64_t key,uint64_t actions)
{
  NXSRadioState s=nxs_control_radio_state(p->control);NXSControlState common=nxs_control_state(p->control);
  NSInteger rows,columns;[p->native getNumberOfRows:&rows columns:&columns];
  NSInteger sr,sc,kr,kc;
  BOOL native_selected=[p->native getRow:&sr column:&sc ofCell:[p->native selectedCell]];
  BOOL native_key=[p->native getRow:&kr column:&kc ofCell:[p->native keyCell]];
  BOOL checked=YES;unsigned i=0;
  for(NSCell *cell in [p->native cells])checked=checked&&[cell state]==(p->items[i++].identifier==selected);
  check(p,name,s.selected==selected&&s.key_cell==key&&s.actions==actions&&s.count==4&&
    s.rows==rows&&s.columns==columns&&[p->native class]==[NSMatrix class]&&
    common.value==index_of(p,selected)&&common.state==!!selected&&checked&&
    (native_selected?p->items[sr*columns+sc].identifier:0)==selected&&
    (native_key?p->items[kr*columns+kc].identifier:0)==key);
}
static void changed(void *context,int event,const NXSControlState *value)
{
  struct Probe *p=context;p->callbacks++;
  assert(event==NXS_ACTIVATE&&value->tracking&&nxs_control_radio_state(p->control).actions==p->callbacks);
  assert(!nxs_control_radio_items(p->control,NULL,0,1,0,0));
  NXSControlConfig config={.size=sizeof(config),.width=180,.height=99,.enabled=1};
  assert(!nxs_control_sync(p->control,&config)&&!nxs_control_destroy(p->control));
  if(nxs_control_activation_capabilities())assert(!nxs_control_perform_click(p->control,identifier(0)));
}
static void pump(void *context)
{
  struct Probe *p=context;assert(++p->loops<5000);
  assert(!nxs_control_radio_items(p->control,NULL,0,1,0,0)&&!nxs_control_destroy(p->control));
  nxs_control_send(p->control,p->phase++?NXS_RELEASE:NXS_MOVE,p->x,p->y,0);
}
static void model(struct Probe *p,unsigned columns,uint64_t selected,uint64_t key)
{
  uint64_t actions=nxs_control_radio_state(p->control).actions;
  NXSControlConfig config={.size=sizeof(config),.width=columns==4?432:columns==2?216:180,
    .height=columns==4?24:columns==2?49:99,.enabled=p->enabled};
  /* Native setKeyCell: respects enabled state; enable before requesting focus. */
  assert(nxs_control_sync(p->control,&config));
  assert(nxs_control_radio_items(p->control,p->items,4,columns,selected,key));p->native=observed;
  check(p,"model-replacement-emits-no-action",nxs_control_radio_state(p->control).actions==actions);
  assert(nxs_control_sync(p->control,&config));
}
static int key(struct Probe *p,unsigned logical,const char *text,unsigned modifiers)
{
  NXSKeyEvent input={.size=sizeof(input),.type=NXS_KEY_DOWN,.key=logical,.text=text,.unmodified_text=text,.modifiers=modifiers};
  int result=nxs_control_key(p->control,&input);
  uint64_t actions=nxs_control_radio_state(p->control).actions;
  input.type=NXS_KEY_UP;nxs_control_key(p->control,&input);
  assert(nxs_control_radio_state(p->control).actions==actions);return result;
}
static void click(struct Probe *p,unsigned from,int to)
{
  NXSRect start=nxs_control_radio_item_rect(p->control,p->items[from].identifier);
  NXSRect end=to<0?(NXSRect){.x=-20,.y=-20}:nxs_control_radio_item_rect(p->control,p->items[to].identifier);
  p->x=end.x+end.width/2;p->y=end.y+end.height/2;p->phase=p->loops=0;
  assert(nxs_control_track_clicks(p->control,start.x+start.width/2,start.y+start.height/2,0,1));
  assert(p->phase==2);
}
static void compare(struct Probe *p,const char *name,BOOL focused)
{
  NXSRadioState state=nxs_control_radio_state(p->control);NSSize frame=[p->native frame].size;
  NSMatrix *reference=[[NSMatrix alloc] initWithFrame:NSZeroRect mode:NSRadioModeMatrix
    cellClass:[NSButtonCell class] numberOfRows:0 numberOfColumns:state.columns];
  [reference setAllowsEmptySelection:YES];NSMutableArray *all=[NSMutableArray array];
  for(unsigned row=0;row<state.rows;row++) {
    NSMutableArray *line=[NSMutableArray array];
    for(unsigned column=0;column<state.columns;column++) {
      unsigned i=row*state.columns+column;
      NSButtonCell *cell=[[NSButtonCell alloc] initTextCell:[NSString stringWithUTF8String:p->items[i].title]];
      [cell setButtonType:NSRadioButton];[cell setBordered:NO];[cell setEnabled:p->enabled&&p->items[i].enabled];
      [line addObject:cell];[all addObject:cell];[cell release];
    }
    [reference addRowWithCells:line];
  }
  if(state.selected){NSInteger i=index_of(p,state.selected),r,c;assert([reference getRow:&r column:&c ofCell:[all objectAtIndex:i]]);[reference selectCellAtRow:r column:c];}
  [reference setAllowsEmptySelection:NO];
  if(state.key_cell)[reference setKeyCell:[all objectAtIndex:index_of(p,state.key_cell)]];
  [reference sizeToFit];NXSSize preferred=nxs_control_size(p->control);
  check(p,"native-matrix-preferred-size",preferred.width==[reference frame].size.width&&preferred.height==[reference frame].size.height);
  [reference setFrameSize:frame];
  for(unsigned i=0;i<4;i++) {
    NSInteger row,column;assert([reference getRow:&row column:&column ofCell:[all objectAtIndex:i]]);
    NSRect expected=[reference cellFrameAtRow:row column:column];NXSRect actual=nxs_control_radio_item_rect(p->control,p->items[i].identifier);
    assert(actual.x==expected.origin.x&&actual.y==expected.origin.y&&actual.width==expected.size.width&&actual.height==expected.size.height);
  }
  check(p,"native-cell-geometry",nxs_control_radio_item_rect(p->control,UINT64_MAX).width==0);
  NSWindow *window=[[NSWindow alloc] initWithContentRect:[reference bounds] styleMask:NSTitledWindowMask backing:NSBackingStoreBuffered defer:NO];
  [window setReleasedWhenClosed:NO];[window setBackgroundColor:[NSColor controlBackgroundColor]];
  [[window contentView] addSubview:reference];
  /* Keep keyboard focus on an ordinary native control outside the capture
   * when testing an unfocused matrix. A window/nil responder lets AppKit
   * choose its initial matrix again during delayed activation at 2x. */
  NSButton *other=[[NSButton alloc] initWithFrame:NSMakeRect(-100,-100,1,1)];
  [[window contentView] addSubview:other];[other release];
  NSView *responder=focused?(NSView *)reference:other;[window setInitialFirstResponder:responder];
  [window setTitle:[NSString stringWithFormat:@"Native radio group reference %s",name]];
  [window makeKeyAndOrderFront:nil];[NSApp activateIgnoringOtherApps:YES];
  /* The first real activation may choose an initial responder. Set the
   * reference's requested focus after the compositor/client handshake. */
  printf("{\"event\":\"reference-ready\",\"name\":\"%s\"}\n",name);fflush(stdout);
  struct pollfd input={STDIN_FILENO,POLLIN,0};NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:10];
  while(poll(&input,1,0)==0&&[deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);
  char reply[32];assert(fgets(reply,sizeof(reply),stdin)&&!strcmp(reply,"ready\n"));
  deadline=[NSDate dateWithTimeIntervalSinceNow:5];
  while((![NSApp isActive]||![window isKeyWindow])&&[deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);
  assert([window makeFirstResponder:responder]);[window display];
  assert(nxs_control_focus(p->control,focused));NXSBitmap actual=nxs_control_draw(p->control,p->scale);assert(actual.pixels);
  char path[1024];snprintf(path,sizeof(path),"%s/%s-native.argb",p->directory,name);FILE *file=fopen(path,"wb");assert(file);
  assert(fwrite(actual.pixels,actual.stride,actual.height,file)==(size_t)actual.height);fclose(file);
  NSRect crop=[reference convertRect:[reference bounds] toView:nil];NSSize outer=[window frame].size;
  printf("{\"event\":\"reference\",\"name\":\"%s\",\"width\":%g,\"height\":%g,\"pixel_width\":%d,\"pixel_height\":%d,\"stride\":%d,\"window_pixel_width\":%ld,\"window_pixel_height\":%ld,\"crop_x\":%g,\"crop_y\":%g}\n",
    name,frame.width,frame.height,actual.width,actual.height,actual.stride,lround(outer.width*p->scale),lround(outer.height*p->scale),crop.origin.x,outer.height-NSMaxY(crop));fflush(stdout);
  deadline=[NSDate dateWithTimeIntervalSinceNow:10];
  while(poll(&input,1,0)==0&&[deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);
  assert(fgets(reply,sizeof(reply),stdin)&&!strcmp(reply,"captured\n"));p->images++;
  [window close];[window release];[reference release];
}
int main(int argc,char **argv)
{
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  if(argc>1&&!strcmp(argv[1],"--expect-no-activation")) {
    assert(!nxs_control_activation_capabilities()&&!nxs_control_perform_click(NULL,0));
    NXSControl *group=nxs_control_create(NXS_RADIOGROUP,NULL,NULL,NULL);assert(group);
    assert(!nxs_control_perform_click(group,1)&&nxs_control_destroy(group));
    puts("{\"older_provider_without_semantic_activation\":true}");[pool drain];return 0;
  }
  if(argc>1&&!strcmp(argv[1],"--expect-no-radio")) {
    assert(!nxs_control_radio_capabilities()&&!nxs_control_create(NXS_RADIOGROUP,NULL,NULL,NULL));
    assert(!nxs_control_radio_items(NULL,NULL,0,1,0,0));
    assert(!nxs_control_radio_state(NULL).selected&&!nxs_control_radio_item_rect(NULL,1).width);
    puts("{\"older_provider_without_radio_groups\":true}");[pool drain];return 0;
  }
  if(argc>1&&!strcmp(argv[1],"--expect-no-radio-size")) {
    assert(nxs_control_radio_capabilities()==NXS_RADIO_GROUP);
    NXSControl *group=nxs_control_create(NXS_RADIOGROUP,NULL,NULL,NULL);assert(group);
    assert(nxs_control_backing_scale(group)==0);
    NXSRadioItem items[]={{sizeof(NXSRadioItem),1,"One",1},{sizeof(NXSRadioItem),2,"Two",1}};
    assert(nxs_control_radio_items(group,items,2,1,1,1));
    assert(!nxs_control_radio_cell_size(group,16,16)&&nxs_control_radio_state(group).selected==1);
    assert(nxs_control_destroy(group));puts("{\"prior_groups_without_cell_size\":true}");[pool drain];return 0;
  }
  assert(argc>1&&nxs_control_radio_capabilities()==(NXS_RADIO_GROUP|NXS_RADIO_CELL_SIZE));
  Method method=class_getInstanceMethod([NSMatrix class],@selector(initWithFrame:mode:cellClass:numberOfRows:numberOfColumns:));
  original_init=method_setImplementation(method,(IMP)witness_init);
  struct Probe p={.directory=argv[1],.scale=argc>2?atof(argv[2]):1,.enabled=1};
  const char *titles[]={"First","Disabled","Third","Fourth"};
  for(unsigned i=0;i<4;i++)p.items[i]=(NXSRadioItem){sizeof(NXSRadioItem),identifier(i),titles[i],i!=1};
  p.control=nxs_control_create(NXS_RADIOGROUP,changed,pump,&p);assert(p.control);
  check(&p,"actual-native-backing-density",nxs_control_backing_scale(p.control)==p.scale&&nxs_control_backing_scale(NULL)==0);
  model(&p,1,identifier(0),identifier(0));NSArray *original_cells=[[p.native cells] copy];
  state(&p,"initial-full-width-identities",identifier(0),identifier(0),0);compare(&p,"unfocused",NO);compare(&p,"focused",YES);
  assert(key(&p,NXS_KEY_DOWN_ARROW,NULL,0)==NXS_INPUT_HANDLED);
  state(&p,"native-down-skips-disabled",identifier(2),identifier(2),1);compare(&p,"arrow-selected",YES);
  key(&p,NXS_KEY_DOWN_ARROW,NULL,NXS_SHIFT);
  state(&p,"native-shift-arrow-focus-separate-from-selection",identifier(2),identifier(3),2);compare(&p,"focus-separate",YES);
  key(&p,NXS_KEY_DOWN_ARROW,NULL,NXS_SHIFT);state(&p,"native-boundary-no-wrap-or-extra-action",identifier(2),identifier(3),2);
  key(&p,NXS_KEY_TEXT," ",0);state(&p,"space-selects-native-key-cell",identifier(3),identifier(3),3);compare(&p,"space-selected",YES);
  check(&p,"native-tab-traversal",key(&p,NXS_KEY_TAB,NULL,0)==NXS_INPUT_NEXT);
  key(&p,NXS_KEY_ENTER,NULL,0);state(&p,"return-does-not-activate-radio",identifier(3),identifier(3),3);
  NXSRadioItem swap=p.items[0];p.items[0]=p.items[3];p.items[3]=swap;
  model(&p,1,identifier(3),identifier(0));
  check(&p,"model-replacement-preserves-host-focus",nxs_control_focused(p.control));
  for(unsigned i=0;i<4;i++)assert([[p.native cells] objectAtIndex:i]==[original_cells objectAtIndex:(p.items[i].identifier-identifier(0))]);
  check(&p,"reorder-retains-original-native-cells",[[p.native cells] count]==4);compare(&p,"reordered",YES);
  p.items[0].title="日本語の選択";model(&p,1,identifier(3),identifier(0));compare(&p,"unicode-title",YES);
  p.enabled=0;NXSControlConfig disabled={.size=sizeof(disabled),.width=180,.height=99,.enabled=0};
  assert(nxs_control_sync(p.control,&disabled));
  check(&p,"disabled-group-rejects-native-keys",key(&p,NXS_KEY_DOWN_ARROW,NULL,0)==NXS_INPUT_UNHANDLED);
  state(&p,"disabled-group-retains-native-model",identifier(3),identifier(0),3);compare(&p,"disabled",NO);
  p.enabled=1;model(&p,1,0,identifier(2));compare(&p,"empty-selection",YES);
  key(&p,NXS_KEY_TEXT," ",0);state(&p,"empty-selection-space-uses-native-focus",identifier(2),identifier(2),4);
  model(&p,4,identifier(0),identifier(0));compare(&p,"horizontal",YES);
  model(&p,2,identifier(0),identifier(0));compare(&p,"grid",YES);
  model(&p,1,identifier(0),identifier(0));click(&p,2,2);
  state(&p,"native-pointer-selects-member",identifier(2),identifier(2),5);compare(&p,"pointer",YES);
  click(&p,1,1);state(&p,"native-disabled-pointer-keeps-selection-and-action",identifier(2),identifier(2),6);
  click(&p,0,-1);state(&p,"native-outside-release-restores-selection",identifier(2),identifier(2),7);
  NXSRadioState before=nxs_control_radio_state(p.control);NSMatrix *matrix=p.native;
  NXSRadioItem invalid[4];memcpy(invalid,p.items,sizeof(invalid));invalid[1].identifier=invalid[0].identifier;
  check(&p,"duplicate-identities-rejected",!nxs_control_radio_items(p.control,invalid,4,1,identifier(0),0));
  memcpy(invalid,p.items,sizeof(invalid));invalid[1].title="\xff";
  check(&p,"invalid-utf8-rejected",!nxs_control_radio_items(p.control,invalid,4,1,identifier(0),0));
  check(&p,"invalid-members-and-grid-rejected",!nxs_control_radio_items(p.control,p.items,4,5,0,0)&&
    !nxs_control_radio_items(p.control,p.items,4,1,UINT64_MAX,0)&&!nxs_control_radio_items(p.control,p.items,4,1,0,UINT64_MAX));
  NXSRadioState after=nxs_control_radio_state(p.control);
  check(&p,"invalid-models-are-atomic",!memcmp(&before,&after,sizeof(before))&&matrix==p.native);
  char *huge=malloc(40001);assert(huge);memset(huge,'M',40000);huge[40000]=0;
  memcpy(invalid,p.items,sizeof(invalid));invalid[0].title=huge;
  check(&p,"native-preferred-backing-bound-rejected",!nxs_control_radio_items(p.control,invalid,4,1,identifier(0),0));
  state(&p,"native-size-rejection-restores-original-cells",identifier(2),identifier(2),7);
  for(unsigned i=0;i<50;i++)model(&p,i%2?1:2,identifier(0),identifier(0));
  state(&p,"repeated-model-replacement-has-no-actions",identifier(0),identifier(0),7);
  /* Keep the cell sizing reference independent of Alternate's native
   * transient highlight, which a freshly constructed matrix does not have. */
  model(&p,1,identifier(3),identifier(0));
  before=nxs_control_radio_state(p.control);NSSize old_size=[p.native cellSize];
  check(&p,"application-cell-bounds-use-native-layout",nxs_control_radio_cell_size(p.control,32,30)&&
    [p.native cellSize].width==32&&[p.native cellSize].height==30);
  after=nxs_control_radio_state(p.control);
  check(&p,"cell-layout-retains-native-identities-and-actions",!memcmp(&before,&after,sizeof(before)));
  compare(&p,"cell-bounds",NO);
  check(&p,"oversized-cell-grid-is-rejected",!nxs_control_radio_cell_size(p.control,8192,8192)&&
    [p.native cellSize].width==32&&[p.native cellSize].height==30);
  check(&p,"invalid-cell-bounds-are-rejected",!nxs_control_radio_cell_size(p.control,NAN,16)&&
    !nxs_control_radio_cell_size(p.control,16,INFINITY)&&!nxs_control_radio_cell_size(p.control,0,16));
  assert(nxs_control_radio_cell_size(p.control,old_size.width,old_size.height));
  model(&p,1,identifier(3),identifier(3));assert(nxs_control_focus(p.control,1));
  key(&p,NXS_KEY_DOWN_ARROW,NULL,NXS_SUPER);
  state(&p,"native-alternate-retains-disabled-key-context",identifier(3),identifier(1),8);
  BOOL highlighted[4];for(unsigned i=0;i<4;i++)highlighted[i]=[[[p.native cells] objectAtIndex:i] isHighlighted];
  check(&p,"oversized-model-rejects-disabled-key-context",!nxs_control_radio_items(p.control,invalid,4,1,identifier(0),0));
  state(&p,"native-size-rejection-restores-disabled-key-context",identifier(3),identifier(1),8);
  for(unsigned i=0;i<4;i++)assert(highlighted[i]==[[[p.native cells] objectAtIndex:i] isHighlighted]);free(huge);
  assert(nxs_control_radio_items(p.control,NULL,0,1,0,0));p.native=observed;
  NXSRadioState empty=nxs_control_radio_state(p.control);
  check(&p,"empty-model-has-no-placeholder-controls",!empty.count&&!empty.rows&&!empty.selected&&!empty.key_cell&&[[p.native cells] count]==0&&empty.actions==8);
  check(&p,"empty-model-has-no-invented-size",nxs_control_size(p.control).width==0&&nxs_control_size(p.control).height==0);
  check(&p,"destroy",nxs_control_destroy(p.control));[original_cells release];
  if(nxs_control_activation_capabilities()) {
    p.callbacks=0;p.control=nxs_control_create(NXS_RADIOGROUP,changed,pump,&p);assert(p.control);
    model(&p,1,identifier(0),identifier(0));
    check(&p,"semantic-click-rejects-disabled-and-unknown-members",!nxs_control_perform_click(p.control,identifier(1))&&
      !nxs_control_perform_click(p.control,UINT64_MAX)&&!nxs_control_perform_click(p.control,0));
    state(&p,"rejected-semantic-click-retains-native-state",identifier(0),identifier(0),0);
    check(&p,"semantic-member-click-accepted",nxs_control_perform_click(p.control,identifier(2)));
    state(&p,"semantic-click-native-selection-key-and-action",identifier(2),identifier(2),1);
    check(&p,"semantic-click-does-not-invent-input-focus",!nxs_control_focused(p.control));compare(&p,"semantic-unfocused",NO);
    assert(nxs_control_focus(p.control,1));
    check(&p,"selected-member-semantic-click-acts-again",nxs_control_perform_click(p.control,identifier(2)));
    state(&p,"selected-semantic-click-keeps-native-state",identifier(2),identifier(2),2);compare(&p,"semantic-focused",YES);
    check(&p,"another-member-semantic-click-accepted",nxs_control_perform_click(p.control,identifier(3)));
    state(&p,"another-member-semantic-click-uses-native-selection",identifier(3),identifier(3),3);compare(&p,"semantic-other",YES);
    p.enabled=0;assert(nxs_control_sync(p.control,&disabled));
    check(&p,"disabled-group-rejects-semantic-click",!nxs_control_perform_click(p.control,identifier(0)));
    state(&p,"disabled-semantic-click-retains-native-state",identifier(3),identifier(3),3);compare(&p,"semantic-disabled",NO);
    check(&p,"semantic-control-destroy",nxs_control_destroy(p.control));
  }
  p.callbacks=0;p.enabled=1;p.control=nxs_control_create(NXS_RADIOGROUP,changed,pump,&p);assert(p.control);
  for(unsigned i=0;i<4;i++)p.items[i]=(NXSRadioItem){sizeof(NXSRadioItem),identifier(i),titles[i],i!=1};
  assert(nxs_control_radio_items(p.control,p.items,3,2,identifier(0),identifier(0)));p.native=observed;
  NXSRadioState partial=nxs_control_radio_state(p.control);
  NSCell *vacant=[p.native cellAtRow:1 column:1];
  check(&p,"partial-row-keeps-three-application-members",partial.count==3&&partial.rows==2&&partial.columns==2&&
    !nxs_control_radio_item_rect(p.control,identifier(3)).width);
  check(&p,"partial-row-native-empty-slot-cannot-take-focus",[vacant class]==[NSCell class]&&
    ![vacant isEnabled]&&![vacant acceptsFirstResponder]);
  assert(nxs_control_focus(p.control,1));key(&p,NXS_KEY_DOWN_ARROW,NULL,0);
  check(&p,"partial-row-native-navigation-selects-real-member",nxs_control_radio_state(p.control).selected==identifier(2));
  key(&p,NXS_KEY_RIGHT,NULL,0);
  check(&p,"partial-row-native-navigation-skips-empty-slot",nxs_control_radio_state(p.control).selected==identifier(2));
  check(&p,"partial-row-control-destroy",nxs_control_destroy(p.control));
  printf("{\"passed\":%u,\"images\":%u,\"api_bytes\":%zu,\"semantic_activation\":%s}\n",p.checks,p.images,sizeof(NXSNativeUIAPI),nxs_control_activation_capabilities()?"true":"false");
  [pool drain];return 0;
}
