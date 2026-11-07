/* Instantiate native controls; drawing and interaction remain in AppKit.
 * GPL-2.0-or-later. */
#import "ViewHost.h"
#include "Provider.h"
#include <math.h>
#include <float.h>
#include <stdlib.h>
#include <string.h>
#include <objc/runtime.h>
struct NXSControl {
  int kind,enabled;
  NSView *view;
  NXSViewHost *host;
  id target;
  NXSControlChanged changed;
  void *context;
  double step;
  NSRange text_selection;
  NXSTextShouldChange text_filter;
  void *text_filter_context;
  SEL text_command;
  NSString *text_value;
  BOOL text_selection_pending,text_editable,text_reveal_pending,destroying,tab_syncing;
};
double nxs_gnustep_control_backing_scale(NXSControl *control)
{return control&&!control->destroying?[[control->view window] backingScaleFactor]:0;}
static int text_control(NXSControl *control)
{return control&&(control->kind==NXS_TEXTFIELD||control->kind==NXS_PASSWORD||control->kind==NXS_TEXTAREA||control->kind==NXS_SEARCHFIELD);}
static NSTextView *text_editor(NXSControl *control)
{return control->kind==NXS_TEXTAREA?(NSTextView *)[(NSScrollView *)control->view documentView]:
  (NSTextView *)[(NSTextField *)control->view currentEditor];}
unsigned nxs_gnustep_control_text_capabilities(void){return NXS_TEXT_MULTILINE|NXS_TEXT_SEARCH|NXS_TEXT_SEARCH_ACTION|NXS_TEXT_SEARCH_CLEAR_COMMAND;}
NXSRect nxs_gnustep_control_search_part(NXSControl *control,int part) {
  if(!control||control->kind!=NXS_SEARCHFIELD||control->destroying)return (NXSRect){0};
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSSearchFieldCell *cell=[(NSSearchField *)control->view cell];
  NSRect bounds=[control->view bounds],rect;
  switch(part) {
    case NXS_SEARCH_BUTTON:rect=[cell searchButtonRectForBounds:bounds];break;
    case NXS_SEARCH_CANCEL:rect=[cell cancelButtonRectForBounds:bounds];break;
    case NXS_SEARCH_TEXT:rect=[cell searchTextRectForBounds:bounds];break;
    default:[pool drain];return (NXSRect){0};
  }
  NXSRect result=nxs_host_rect_from_view(control->host,control->view,rect);
  [pool drain];return result;
}
NXSTextViewport nxs_gnustep_control_text_viewport(NXSControl *control)
{
  NXSTextViewport state={.size=sizeof(state)};
  if(!control||control->kind!=NXS_TEXTAREA||control->destroying)return state;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSView *view=text_editor(control);
  NSRect visible=[[(NSScrollView *)control->view contentView] documentVisibleRect];
  NSSize content=[view bounds].size;
  state.visible=(NXSRect){visible.origin.x,[view isFlipped]?visible.origin.y:content.height-NSMaxY(visible),visible.size.width,visible.size.height};
  state.content=(NXSSize){content.width,content.height};[pool drain];return state;
}
int nxs_gnustep_control_text_scroll(NXSControl *control,double x,double y)
{
  if(!control||control->kind!=NXS_TEXTAREA||control->destroying||!isfinite(x)||!isfinite(y)||nxs_host_tracking(control->host))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSScrollView *scroll=(NSScrollView *)control->view;NSClipView *clip=[scroll contentView];
  NSView *view=[scroll documentView];
  NSPoint point=NSMakePoint(x,[view isFlipped]?y:[view bounds].size.height-y-[clip bounds].size.height);
  [clip scrollToPoint:[clip constrainScrollPoint:point]];[scroll reflectScrolledClipView:clip];
  [control->view setNeedsDisplay:YES];[pool drain];return 1;
}
static int scroll_geometry(NXSControl *control,NSScrollView *scroll,NXSScrollGeometry *geometry)
{
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSClipView *clip=[scroll contentView];NSView *view=[scroll documentView];
  NSSize client=[NSScrollView contentSizeForFrameSize:[scroll frame].size
    hasHorizontalScroller:NO hasVerticalScroller:NO borderType:[scroll borderType]];
  NSPoint minimum=[clip constrainScrollPoint:NSMakePoint(-FLT_MAX,-FLT_MAX)];
  NSPoint maximum=[clip constrainScrollPoint:NSMakePoint(FLT_MAX,FLT_MAX)];
  if(![view isFlipped]) {
    double bottom=[view bounds].size.height-[clip bounds].size.height;
    double first=bottom-maximum.y;maximum.y=bottom-minimum.y;minimum.y=first;
  }
  *geometry=(NXSScrollGeometry){.size=sizeof(*geometry),
    .clip=nxs_host_rect_from_view(control->host,clip,[clip bounds]),
    .client={client.width,client.height},.minimum={minimum.x,minimum.y},.maximum={maximum.x,maximum.y}};
  [pool drain];return 1;
}
int nxs_gnustep_control_text_geometry(NXSControl *control,NXSTextGeometry *geometry)
{
  if(!geometry||geometry->size<sizeof(*geometry)||!control||control->kind!=NXS_TEXTAREA||control->destroying)return 0;
  return scroll_geometry(control,(NSScrollView *)control->view,geometry);
}
int nxs_gnustep_control_wheel(NXSControl *control,const NXSWheelEvent *event)
{return control&&(control->kind==NXS_TEXTAREA||control->kind==NXS_LISTBOX)&&!control->destroying?nxs_host_wheel(control->host,event):0;}
static void slider_model(NXSControl *control)
{
  NSSlider *view=(NSSlider *)control->view;
  double intervals=control->step>0?([view maxValue]-[view minValue])/control->step:0;
  /* Dense domains retain the native continuous presentation. Small domains
   * use the existing native tick/snap implementation, including its keys. */
  NSInteger ticks=isfinite(intervals)&&intervals>=1&&intervals<=63?(NSInteger)llround(intervals)+1:0;
  [view setNumberOfTickMarks:ticks];[view setAllowsTickMarkValuesOnly:ticks>1];
  [view setDoubleValue:[view doubleValue]];
}
@interface NXSControlAction : NSObject {
 @public NXSControl *control;
 @private id editor_delegate;
  id search_cancel_target;
  SEL search_cancel_action;
  id search_submit_target;
  SEL search_submit_action;
  BOOL search_committing;
}
- (void)changed:(id)sender;
- (void)willPopUp:(NSNotification *)notification;
- (void)controlTextDidChange:(NSNotification *)notification;
- (void)controlTextDidEndEditing:(NSNotification *)notification;
- (void)bindTextEditor;
- (void)bindSearchAction;
- (void)searchCancel:(id)sender;
- (void)searchSubmit:(id)sender;
- (void)performSearchClear;
@end
@implementation NXSControlAction
- (void)dealloc {[editor_delegate release];[super dealloc];}
- (BOOL)tabView:(NSTabView *)view shouldSelectTabViewItem:(NSTabViewItem *)item
{return control->tab_syncing||(!control->destroying&&control->enabled);}
- (void)tabView:(NSTabView *)view didSelectTabViewItem:(NSTabViewItem *)item
{
  if(!control->tab_syncing&&control->changed) {
    NXSControlState state=nxs_gnustep_control_state(control);
    control->changed(control->context,NXS_VALUE_CHANGED,&state);
  }
}
/* Preserve NSTextField's complete native delegate/notification path. Only its
 * pre-edit proposal is intercepted; the original editor still performs edits. */
- (BOOL)respondsToSelector:(SEL)selector
{return [super respondsToSelector:selector]||[editor_delegate respondsToSelector:selector];}
- (NSMethodSignature *)methodSignatureForSelector:(SEL)selector
{return [super methodSignatureForSelector:selector]?:[editor_delegate methodSignatureForSelector:selector];}
- (void)forwardInvocation:(NSInvocation *)invocation
{if([editor_delegate respondsToSelector:[invocation selector]])[invocation invokeWithTarget:editor_delegate];
 else [super forwardInvocation:invocation];}
- (void)bindTextEditor
{
  NSTextView *editor=text_editor(control);
  if(!editor)return;
  if(control->kind==NXS_TEXTAREA){if([editor delegate]!=self)[editor setDelegate:(id)self];return;}
  if(control->text_filter) {
    if([editor delegate]!=self) {
      id previous=[[editor delegate] retain];[editor_delegate release];editor_delegate=previous;
      [editor setDelegate:(id)self];
    }
  } else if([editor delegate]==self) {
    [editor setDelegate:editor_delegate];[editor_delegate release];editor_delegate=nil;
  }
}
- (BOOL)textView:(NSTextView *)editor shouldChangeTextInRange:(NSRange)range replacementString:(NSString *)text
{
  if([editor_delegate respondsToSelector:_cmd]&&
     ![editor_delegate textView:editor shouldChangeTextInRange:range replacementString:text])return NO;
  if(!text||!control->text_filter)return YES;
  if(control->destroying)return NO;
  NSRange selection=[editor selectedRange];
  NXSTextEdit edit={.size=sizeof(edit),.range_start=range.location,.range_length=range.length,
    .selection_start=selection.location,.selection_length=selection.length,
    .replacement=[text UTF8String],.command=control->text_command?sel_getName(control->text_command):NULL};
  BOOL accepted=edit.replacement&&control->text_filter(control->text_filter_context,&edit);
  /* An external editor may commit the proposal and reject the local duplicate.
   * Finish native caret reveal only when its canonical model actually changes. */
  if(!accepted&&control->kind==NXS_TEXTAREA)control->text_reveal_pending=YES;
  return accepted;
}
- (BOOL)control:(NSControl *)view textView:(NSTextView *)editor doCommandBySelector:(SEL)selector
{control->text_command=selector;return nxs_host_command(control->host,selector,NXS_COMMAND_EXECUTE)>=0;}
- (BOOL)textView:(NSTextView *)editor doCommandBySelector:(SEL)selector
{
  if(control->kind!=NXS_TEXTAREA)
    return [editor_delegate respondsToSelector:_cmd]&&[editor_delegate textView:editor doCommandBySelector:selector];
  control->text_command=selector;return nxs_host_command(control->host,selector,NXS_COMMAND_EXECUTE)>=0;
}
- (void)textDidChange:(NSNotification *)notification {[self controlTextDidChange:notification];}
- (void)willSendTextAction:(NSNotification *)notification
{if(nxs_host_focused(control->host))control->text_command=[[[notification userInfo] objectForKey:@"MenuItem"] action];}
- (void)controlTextDidBeginEditing:(NSNotification *)notification {[self bindTextEditor];}
- (void)bindSearchAction
{
  NSButtonCell *button=[[(NSSearchField *)control->view cell] cancelButtonCell];
  search_cancel_target=[button target];search_cancel_action=[button action];
  [button setTarget:self];[button setAction:@selector(searchCancel:)];
  button=[[(NSSearchField *)control->view cell] searchButtonCell];
  search_submit_target=[button target];search_submit_action=[button action];
  [button setTarget:self];[button setAction:@selector(searchSubmit:)];
}
- (void)searchSubmit:(id)sender
{
  [NSApp sendAction:search_submit_action to:search_submit_target from:sender];
  nxs_host_command(control->host,@selector(performClick:),NXS_COMMAND_EXECUTE);
}
- (void)searchCancel:(id)sender
{
  /* An embedding may defer this original action to its cancellable default
   * phase. Unknown commands retain the original immediate native behavior. */
  if(!search_committing&&nxs_host_command(control->host,@selector(clearSearch:),NXS_COMMAND_EXECUTE)>=0)return;
  /* Observe the original native button action, including its actual result.
   * Text-change actions from the same search cell are distinct from this. */
  NSTextView *editor=text_editor(control);
  control->text_value=[(editor?[editor string]:[(NSTextField *)control->view stringValue]) copy];
  if(editor)control->text_selection=[editor selectedRange];
  [NSApp sendAction:search_cancel_action to:search_cancel_target from:sender];
  [control->text_value release];control->text_value=nil;
}
- (void)performSearchClear
{
  search_committing=YES;
  @try {
    NSSearchFieldCell *cell=[(NSSearchField *)control->view cell];
    [[cell cancelButtonCell] performClickWithFrame:[cell cancelButtonRectForBounds:[control->view bounds]] inView:control->view];
  }
  @finally {search_committing=NO;}
}
- (void)changed:(id)sender
{
  if(control->kind==NXS_SEARCHFIELD&&control->text_filter&&control->text_value) {
    /* The original search cell has already chosen and performed its action.
     * Transport its clear result through the same application edit gate. */
    NSString *value=[[(NSSearchField *)control->view cell] stringValue];
    if(![value length]&&![value isEqualToString:control->text_value]) {
      NSRange selection=control->text_selection;
      NXSTextEdit edit={.size=sizeof(edit),.range_length=[control->text_value length],
        .selection_start=selection.location,.selection_length=selection.length,
        .replacement=[value UTF8String],.command="delete:"};
      if(!control->text_editable||!control->text_filter(control->text_filter_context,&edit))
        [[(NSSearchField *)control->view cell] setStringValue:control->text_value];
    }
  }
  if(!control->changed)return;
  NXSControlState state=nxs_gnustep_control_state(control);
  control->changed(control->context,(control->kind==NXS_SLIDER||control->kind==NXS_POPUP)?NXS_VALUE_CHANGED:NXS_ACTIVATE,&state);
}
- (void)willPopUp:(NSNotification *)notification
{nxs_host_bind_input_window(control->host,[[(NSPopUpButton *)control->view menu] window]);}
- (void)controlTextDidChange:(NSNotification *)notification
{
  [control->view setNeedsDisplay:YES];
  if(control->changed) {
    NXSControlState state=nxs_gnustep_control_state(control);
    control->changed(control->context,NXS_TEXT_CHANGED,&state);
  }
}
- (void)controlTextDidEndEditing:(NSNotification *)notification
{
  NSText *editor=[[notification userInfo] objectForKey:@"NSFieldEditor"];
  if(editor)control->text_selection=[editor selectedRange];
}
@end

#include "Toolbar.inc"
#include "Radio.inc"
#include "List.inc"

NXSControl *nxs_gnustep_control_create(int kind,NXSControlChanged changed,NXSPump pump,void *context)
{
  if(kind<NXS_BUTTON||kind>NXS_SEARCHFIELD)return NULL;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  if(!nxs_host_initialize()){[pool drain];return NULL;}
  NXSControl *control=calloc(1,sizeof(*control));
  if(!control){[pool drain];return NULL;}
  NSView *view=nil;
  if(kind==NXS_LISTBOX) {
    view=list_create(control);
  } else if(kind==NXS_RADIOGROUP) {
    view=radio_create(control);
  } else if(kind==NXS_TOOLBAR) {
    view=toolbar_create(control);
  } else if(kind==NXS_TABVIEW) {
    view=[[NSTabView alloc] initWithFrame:NSMakeRect(0,0,320,120)];
  } else if(kind==NXS_TEXTAREA) {
    NSScrollView *scroll=[[NSScrollView alloc] initWithFrame:NSMakeRect(0,0,180,96)];
    [scroll setBorderType:NSBezelBorder];[scroll setHasVerticalScroller:YES];
    [scroll setAutohidesScrollers:YES];
    NSTextView *editor=[[NSTextView alloc] initWithFrame:NSMakeRect(0,0,[scroll contentSize].width,[scroll contentSize].height)];
    [editor setRichText:NO];[editor setAllowsUndo:YES];
    [editor setMinSize:NSZeroSize];[editor setMaxSize:NSMakeSize(FLT_MAX,FLT_MAX)];
    [editor setHorizontallyResizable:NO];[editor setVerticallyResizable:YES];
    [editor setAutoresizingMask:NSViewWidthSizable];
    [[editor textContainer] setWidthTracksTextView:YES];
    [scroll setDocumentView:editor];[editor release];view=scroll;
  } else if(kind==NXS_TEXTFIELD||kind==NXS_PASSWORD||kind==NXS_SEARCHFIELD) {
    view=kind==NXS_PASSWORD?[[NSSecureTextField alloc] initWithFrame:NSMakeRect(0,0,120,24)]:
      kind==NXS_SEARCHFIELD?[[NSSearchField alloc] initWithFrame:NSMakeRect(0,0,120,24)]:
      [[NSTextField alloc] initWithFrame:NSMakeRect(0,0,120,24)];
  } else if(kind==NXS_POPUP) {
    view=[[NSPopUpButton alloc] initWithFrame:NSMakeRect(0,0,120,24) pullsDown:NO];
    [(NSPopUpButton *)view setAutoenablesItems:NO];
  } else if(kind==NXS_SLIDER) {
    NSSlider *slider=[[NSSlider alloc] initWithFrame:NSMakeRect(0,0,120,24)];
    [slider setContinuous:YES];view=slider;
  } else if(kind==NXS_PROGRESS) {
    NSProgressIndicator *progress=[[NSProgressIndicator alloc] initWithFrame:NSMakeRect(0,0,120,20)];
    [progress setStyle:NSProgressIndicatorBarStyle];[progress setIndeterminate:NO];
    [progress setDisplayedWhenStopped:YES];view=progress;
  } else {
    NSButton *button=[[NSButton alloc] initWithFrame:NSMakeRect(0,0,120,24)];
    [button setButtonType:kind==NXS_CHECKBOX?NSSwitchButton:kind==NXS_RADIO?NSRadioButton:NSMomentaryPushInButton];
    if(kind!=NXS_BUTTON)[button setBordered:NO];
    view=button;
  }
  control->host=nxs_host_create(view,pump,context);control->view=view;[view release];
  if(!control->host){[control->target release];free(control);[pool drain];return NULL;}
  control->kind=kind;control->enabled=1;control->text_editable=YES;control->changed=changed;control->context=context;
  control->text_selection=NSMakeRange(NSNotFound,0);
  if(kind!=NXS_PROGRESS&&kind!=NXS_TOOLBAR&&kind!=NXS_RADIOGROUP&&kind!=NXS_LISTBOX) {
    NXSControlAction *target=[NXSControlAction new];target->control=control;control->target=target;
    if(kind==NXS_TABVIEW)[(NSTabView *)view setDelegate:(id)target];
    else if(kind!=NXS_TEXTAREA){[(NSControl *)view setTarget:target];[(NSControl *)view setAction:@selector(changed:)];}
    if(text_control(control)) {
      if(kind==NXS_TEXTAREA)[text_editor(control) setDelegate:(id)target];
      else [(NSTextField *)view setDelegate:(id)target];
      [[NSNotificationCenter defaultCenter] addObserver:target selector:@selector(willSendTextAction:)
        name:NSMenuWillSendActionNotification object:[NSTextView defaultMenu]];
    }
    if(kind==NXS_SEARCHFIELD)[target bindSearchAction];
    if(kind==NXS_POPUP)[[NSNotificationCenter defaultCenter] addObserver:target
      selector:@selector(willPopUp:) name:NSPopUpButtonWillPopUpNotification object:view];
  }
  [pool drain];return control;
}
int nxs_gnustep_control_destroy(NXSControl *control)
{
  if(!control)return 1;
  if(control->destroying)return 0;
  control->destroying=YES;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  if(control->kind==NXS_POPUP) {
    if(nxs_host_tracking(control->host)){control->destroying=NO;[pool drain];return 0;}
    [(NSPopUpButtonCell *)[(NSPopUpButton *)control->view cell] dismissPopUp];
  }
  NSView *view=[control->view retain];
  if(!nxs_host_destroy(control->host)){control->destroying=NO;[view release];[pool drain];return 0;}
  if(control->kind==NXS_LISTBOX)[(NSBrowser *)view setDelegate:nil];
  else if(control->kind==NXS_TEXTAREA)[(NSTextView *)[(NSScrollView *)view documentView] setDelegate:nil];
  else if(control->kind==NXS_TABVIEW)[(NSTabView *)view setDelegate:nil];
  else if(text_control(control))[(NSTextField *)view setDelegate:nil];
  if(control->kind==NXS_POPUP||text_control(control))[[NSNotificationCenter defaultCenter] removeObserver:control->target];
  if(control->kind==NXS_PROGRESS)[(NSProgressIndicator *)view stopAnimation:nil];
  [view release];
  [control->target release];[control->text_value release];free(control);[pool drain];return 1;
}
int nxs_gnustep_control_sync(NXSControl *control,const NXSControlConfig *config)
{
  if(control&&(control->kind==NXS_RADIOGROUP||control->kind==NXS_LISTBOX)&&nxs_host_tracking(control->host))return 0;
  if(!control||!config||config->size<sizeof(*config)||!isfinite(config->width)||!isfinite(config->height)||
     config->width<1||config->height<1||config->width>32768||config->height>32768||
     !isfinite(config->minimum)||!isfinite(config->maximum)||!isfinite(config->value)||config->minimum>config->maximum||
     config->state<-1||config->state>1)return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSString *title=nil;
  if(control->kind==NXS_BUTTON||control->kind==NXS_CHECKBOX||control->kind==NXS_RADIO) {
    title=config->title?[NSString stringWithUTF8String:config->title]:@"";
    if(!title){[pool drain];return 0;}
  }
  nxs_host_resize(control->host,NSMakeSize(config->width,config->height));control->enabled=!!config->enabled;
  if(control->kind==NXS_TEXTAREA) {
    NSTextView *editor=text_editor(control);
    [editor setEditable:control->enabled&&control->text_editable];[editor setSelectable:control->enabled];
    [editor sizeToFit];
  } else if(control->kind==NXS_PROGRESS) {
    NSProgressIndicator *view=(NSProgressIndicator *)control->view;
    [view setMinValue:config->minimum];[view setMaxValue:config->maximum];[view setDoubleValue:config->value];
    [view setIndeterminate:!!config->indeterminate];
    if(config->indeterminate&&control->enabled)[view startAnimation:nil];
    else [view stopAnimation:nil];
  } else if(control->kind==NXS_LISTBOX) {
    list_enabled(control);
  } else if(control->kind==NXS_RADIOGROUP) {
    radio_enabled(control);
  } else if(control->kind==NXS_TOOLBAR) {
    toolbar_layout(control);
  } else if(control->kind==NXS_TABVIEW) {
    [control->view setNeedsDisplay:YES];
  } else {
    [(NSControl *)control->view setEnabled:control->enabled];
    if(control->kind==NXS_SLIDER) {
      NSSlider *view=(NSSlider *)control->view;
      [view setAllowsTickMarkValuesOnly:NO];
      [view setMinValue:config->minimum];[view setMaxValue:config->maximum];[view setDoubleValue:config->value];
      slider_model(control);
    } else if(control->kind==NXS_POPUP) {
      NSPopUpButton *view=(NSPopUpButton *)control->view;
      /* Selecting even the same item synchronizes the native highlighted item
       * into selection. Leave live menu input entirely with the native menu. */
      if(![[[view menu] window] isVisible]&&config->value!=[view indexOfSelectedItem]&&
         config->value>=-1&&config->value<[view numberOfItems]&&floor(config->value)==config->value)
        [view selectItemAtIndex:(NSInteger)config->value];
    } else if(!text_control(control)) {
      NSButton *view=(NSButton *)control->view;
      [view setTitle:title];[view setAllowsMixedState:control->kind==NXS_CHECKBOX&&config->state==-1];
      [view setState:config->state];
    }
  }
  [pool drain];return 1;
}
NXSControlState nxs_gnustep_control_state(NXSControl *control)
{
  NXSControlState state={.size=sizeof(state)};
  if(!control)return state;
  state.enabled=control->enabled;state.tracking=nxs_host_tracking(control->host);
  if(control->kind==NXS_LISTBOX) {
    state.value=[list_matrix(control) selectedRow];state.state=[[list_matrix(control) selectedCells] count]>0;
  } else if(control->kind==NXS_TOOLBAR) {
    NXSToolbarAction *target=control->target;state.value=-1;
    for(unsigned i=0;i<[target->models count];i++)if([[[target->models objectAtIndex:i] objectForKey:@"id"] unsignedLongLongValue]==target->command){state.value=i;break;}
  } else if(control->kind==NXS_RADIOGROUP) {
    state.value=radio_index(control,[(NSMatrix *)control->view selectedCell]);
    state.state=[[(NSMatrix *)control->view selectedCell] state];
  } else if(control->kind==NXS_TABVIEW)state.value=nxs_gnustep_control_tab_state(control).selected_index;
  else if(control->kind==NXS_PROGRESS)state.value=[(NSProgressIndicator *)control->view doubleValue];
  else if(!text_control(control)) {
    state.value=control->kind==NXS_POPUP?[(NSPopUpButton *)control->view indexOfSelectedItem]:[(NSControl *)control->view doubleValue];
    if(control->kind!=NXS_SLIDER&&control->kind!=NXS_POPUP)state.state=[(NSButton *)control->view state];
  }
  return state;
}
NXSSize nxs_gnustep_control_size(NXSControl *control)
{
  if(!control)return (NXSSize){0};
  NSSize size=control->kind==NXS_RADIOGROUP?((NXSRadioAction *)control->target)->preferred:
    control->kind==NXS_TOOLBAR?NSMakeSize([control->view frame].size.width,[control->view _heightFromLayout]):control->kind==NXS_TABVIEW?[(NSTabView *)control->view minimumSize]:
    (control->kind==NXS_PROGRESS||control->kind==NXS_TEXTAREA||control->kind==NXS_LISTBOX)?[control->view frame].size:[[(NSControl *)control->view cell] cellSize];
  return (NXSSize){size.width,size.height};
}
NXSBitmap nxs_gnustep_control_draw(NXSControl *control,double scale)
{return control?nxs_host_draw(control->host,scale):(NXSBitmap){0};}
void nxs_gnustep_control_track(NXSControl *control,double x,double y,unsigned modifiers)
{if(control&&(control->enabled||control->kind==NXS_LISTBOX)&&control->kind!=NXS_PROGRESS)nxs_host_track(control->host,x,y,modifiers);}
int nxs_gnustep_control_track_clicks(NXSControl *control,double x,double y,unsigned modifiers,unsigned clicks)
{return control&&(control->enabled||control->kind==NXS_LISTBOX)&&control->kind!=NXS_PROGRESS?nxs_host_track_clicks(control->host,x,y,modifiers,clicks):0;}
void nxs_gnustep_control_send(NXSControl *control,int event,double x,double y,unsigned modifiers)
{if(control)nxs_host_send(control->host,event,x,y,modifiers);}
static void perform_native_click(NSView *view,void *member)
{
  if(member)[(NSMatrix *)view selectCell:(NSCell *)member];
  [(NSControl *)view performClick:nil];
}
static void perform_native_search_clear(NSView *view,void *target)
{[(NXSControlAction *)target performSearchClear];}
int nxs_gnustep_control_perform_click(NXSControl *control,uint64_t item)
{
  if(!control||control->destroying||!control->enabled||nxs_host_tracking(control->host))return 0;
  if(control->kind==NXS_SEARCHFIELD)
    return item==NXS_SEARCH_CANCEL?nxs_host_action(control->host,perform_native_search_clear,control->target):0;
  NSCell *member=nil;
  if(control->kind==NXS_RADIOGROUP) {
    NXSRadioAction *target=control->target;
    member=[[target->models objectForKey:@(item)] objectForKey:@"cell"];
    if(!member||![member isEnabled])return 0;
  } else if(item||(control->kind!=NXS_BUTTON&&control->kind!=NXS_CHECKBOX&&control->kind!=NXS_RADIO))return 0;
  return nxs_host_action(control->host,perform_native_click,member);
}
int nxs_gnustep_control_focus(NXSControl *control,int focused)
{
  if(!control||(focused&&(!control->enabled||control->kind==NXS_PROGRESS)))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  int accepted=nxs_host_focus(control->host,focused);
  if(accepted&&focused&&text_control(control)&&control->text_selection_pending) {
    [text_editor(control) setSelectedRange:control->text_selection];
    control->text_selection_pending=NO;
  }
  if(accepted&&focused&&text_control(control))[(NXSControlAction *)control->target bindTextEditor];
  [pool drain];return accepted;
}
int nxs_gnustep_control_focused(NXSControl *control)
{return control?nxs_host_focused(control->host):0;}
const char *nxs_gnustep_control_text_command(NXSControl *control)
{return text_control(control)&&control->text_command?sel_getName(control->text_command):NULL;}
int nxs_gnustep_control_command_filter(NXSControl *control,NXSCommandFilter filter,void *context)
{return control&&!control->destroying?nxs_host_command_filter(control->host,filter,context):0;}
int nxs_gnustep_control_key(NXSControl *control,const NXSKeyEvent *event)
{
  if(control){control->text_command=NULL;control->text_reveal_pending=NO;}
  return control&&control->enabled&&control->kind!=NXS_PROGRESS?nxs_host_key(control->host,event):NXS_INPUT_UNHANDLED;
}
int nxs_gnustep_control_needs_display(NXSControl *control)
{return control?nxs_host_needs_display(control->host):0;}
int nxs_gnustep_control_set_step(NXSControl *control,double step)
{
  if(!control||control->kind!=NXS_SLIDER||!isfinite(step)||step<0)return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  control->step=step;slider_model(control);[pool drain];return 1;
}
int nxs_gnustep_control_popup_items(NXSControl *control,const NXSPopupItem *items,uint32_t count,int selected)
{
  if(!control||control->kind!=NXS_POPUP||count>65536||(!items&&count)||selected<-1||
     (selected>=0&&(uint32_t)selected>=count)||nxs_host_tracking(control->host))return 0;
  NSPopUpButton *view=(NSPopUpButton *)control->view;
  if([[[view menu] window] isVisible])return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSMutableArray *titles=[NSMutableArray arrayWithCapacity:count];
  for(uint32_t i=0;i<count;i++) {
    if(items[i].size<sizeof(items[i])){[pool drain];return 0;}
    NSString *title=items[i].title?[NSString stringWithUTF8String:items[i].title]:@"";
    if(!title||(items[i].separator&&selected==(int)i)){
      [pool drain];return 0;
    }
    [titles addObject:title];
  }
  /* NSMenu preserves ordered duplicate labels. Its native popup ownership
   * already supplies selection and action dispatch for items with no custom
   * action; no private popup selector or selection implementation is needed. */
  NSMenu *menu=[[NSMenu alloc] initWithTitle:@""];[menu setAutoenablesItems:NO];
  for(uint32_t i=0;i<count;i++) {
    if(items[i].separator)[menu addItem:[NSMenuItem separatorItem]];
    else {
      id item=[menu addItemWithTitle:[titles objectAtIndex:i] action:NULL keyEquivalent:@""];
      [item setEnabled:!!items[i].enabled];
    }
  }
  nxs_host_unbind_input_windows(control->host);
  [view setMenu:menu];[menu release];
  [view selectItemAtIndex:selected];[view synchronizeTitleAndSelectedItem];
  [view setEnabled:control->enabled];
  [pool drain];return 1;
}
int nxs_gnustep_control_popup_title(NXSControl *control,const char *title)
{
  if(!control||control->kind!=NXS_POPUP||control->destroying||nxs_host_tracking(control->host))return 0;
  NSPopUpButton *view=(NSPopUpButton *)control->view;
  if([[[view menu] window] isVisible])return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSString *value=title?[NSString stringWithUTF8String:title]:nil;
  if(title&&!value){[pool drain];return 0;}
  NSPopUpButtonCell *cell=(NSPopUpButtonCell *)[view cell];
  [cell setUsesItemFromMenu:title==NULL];
  if(title)[cell setTitle:value];else [view synchronizeTitleAndSelectedItem];
  [view setNeedsDisplay:YES];[pool drain];return 1;
}
NXSPopupState nxs_gnustep_control_popup_state(NXSControl *control)
{
  NXSPopupState result={.size=sizeof(result),.highlighted=-1};
  if(!control||control->kind!=NXS_POPUP)return result;
  NSMenuView *view=[[(NSPopUpButton *)control->view menu] menuRepresentation];
  result.visible=[[view window] isVisible];
  if(result.visible){nxs_host_bind_input_window(control->host,[view window]);result.highlighted=[view highlightedItemIndex];result.frame=nxs_host_rect_from_view(control->host,view,[view bounds]);}
  return result;
}
NXSRect nxs_gnustep_control_popup_item_rect(NXSControl *control,int index)
{
  if(!control||control->kind!=NXS_POPUP||index<0||index>=[(NSPopUpButton *)control->view numberOfItems])return (NXSRect){0};
  NSMenuView *view=[[(NSPopUpButton *)control->view menu] menuRepresentation];
  return [[view window] isVisible]?nxs_host_rect_from_view(control->host,view,[view rectOfItemAtIndex:index]):(NXSRect){0};
}
int nxs_gnustep_control_set_screen_origin(NXSControl *control,double x,double y)
{
  if(!control)return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  int result=nxs_host_set_screen_origin(control->host,x,y);[pool drain];return result;
}
int nxs_gnustep_control_popup_open(NXSControl *control,int open)
{
  if(!control||control->kind!=NXS_POPUP||nxs_host_tracking(control->host)||(open&&!control->enabled))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSPopUpButton *view=(NSPopUpButton *)control->view;
  NSPopUpButtonCell *cell=(NSPopUpButtonCell *)[view cell];
  if(open) {
    if(![view numberOfItems]){[pool drain];return 0;}
    if(![[[view menu] window] isVisible])[cell attachPopUpWithFrame:[view bounds] inView:view];
  } else [cell dismissPopUp];
  [pool drain];return 1;
}

/* Text data and selection are native NSString/NSText state. Editing, key
 * interpretation, layout, selection painting and secure rendering stay native. */
int nxs_gnustep_control_text_sync(NXSControl *control,const NXSTextModel *model)
{
  if(!text_control(control)||!model||model->size<sizeof(*model)||control->destroying||
     nxs_host_tracking(control->host))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSString *text=model->text?[NSString stringWithUTF8String:model->text]:@"";
  if(!text||(model->selection_start!=NXS_TEXT_NO_SELECTION&&
     (model->selection_start>[text length]||model->selection_length>[text length]-model->selection_start))) {
    [pool drain];return 0;
  }
  NSTextView *editor=text_editor(control);
  NSString *current=editor?[editor string]:[(NSTextField *)control->view stringValue];
  BOOL model_changed=![current isEqualToString:text]||
    (editor&&model->selection_start!=NXS_TEXT_NO_SELECTION&&
     !NSEqualRanges([editor selectedRange],NSMakeRange(model->selection_start,model->selection_length)));
  if(![current isEqualToString:text]) {
    if(control->kind==NXS_TEXTAREA){[editor setString:text];[editor sizeToFit];}
    else [(NSTextField *)control->view setStringValue:text];
  }
  control->text_editable=!!model->editable;
  if(control->kind==NXS_TEXTAREA)[editor setEditable:control->enabled&&control->text_editable];
  else if([(NSTextField *)control->view isEditable]!=control->text_editable)
    [(NSTextField *)control->view setEditable:control->text_editable];
  [(NXSControlAction *)control->target bindTextEditor];
  control->text_selection=model->selection_start==NXS_TEXT_NO_SELECTION?NSMakeRange(NSNotFound,0):
    NSMakeRange(model->selection_start,model->selection_length);
  /* NSTextField may end editing when its value changes. Read its current
   * editor again so a subsequent native focus applies the pending range. */
  editor=text_editor(control);
  control->text_selection_pending=!editor&&control->text_selection.location!=NSNotFound;
  if(editor&&control->text_selection.location!=NSNotFound&&
     !NSEqualRanges([editor selectedRange],control->text_selection))
    [editor setSelectedRange:control->text_selection];
  if(control->text_reveal_pending&&model_changed&&nxs_host_focused(control->host))
    [editor scrollRangeToVisible:[editor selectedRange]];
  control->text_reveal_pending=NO;
  [control->view setNeedsDisplay:YES];[pool drain];return 1;
}
size_t nxs_gnustep_control_text_get(NXSControl *control,char *buffer,size_t capacity,NXSTextState *state)
{
  if(!text_control(control)||(state&&state->size<sizeof(*state)))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSTextView *editor=text_editor(control);
  NSString *text=editor?[editor string]:[(NSTextField *)control->view stringValue];
  const char *utf8=[text UTF8String];size_t required=utf8?strlen(utf8)+1:0;
  if(editor)control->text_selection=[editor selectedRange];
  NSRange marked=editor&&[editor hasMarkedText]?[editor markedRange]:NSMakeRange(NSNotFound,0);
  if(state)*state=(NXSTextState){.size=sizeof(*state),
    .selection_start=control->text_selection.location==NSNotFound?NXS_TEXT_NO_SELECTION:control->text_selection.location,
    .selection_length=control->text_selection.length,
    .marked_start=marked.location==NSNotFound?NXS_TEXT_NO_SELECTION:marked.location,.marked_length=marked.length,
    .editing=control->kind==NXS_TEXTAREA?nxs_host_focused(control->host):editor!=nil,
    .editable=control->text_editable,.secure=control->kind==NXS_PASSWORD};
  if(buffer&&capacity){if(required&&capacity>=required)memcpy(buffer,utf8,required);else buffer[0]=0;}
  [pool drain];return required;
}
int nxs_gnustep_control_text_filter(NXSControl *control,NXSTextShouldChange filter,void *context)
{
  if(!text_control(control)||control->destroying||nxs_host_tracking(control->host))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  control->text_filter=filter;control->text_filter_context=context;
  [(NXSControlAction *)control->target bindTextEditor];
  [pool drain];return 1;
}

static void remove_tab_item(NSTabView *view,NSTabViewItem *item)
{
  /* This private host has no following native pane. Detach the outgoing key
   * link before releasing a selected item; NSTabView retains a cached link. */
  if(item==[view selectedTabViewItem])[view setNextKeyView:nil];
  [view removeTabViewItem:item];
}
int nxs_gnustep_control_tab_items(NXSControl *control,const NXSTabItem *items,uint32_t count,uint64_t selected)
{
  if(!control||control->kind!=NXS_TABVIEW||control->destroying||control->tab_syncing||
     nxs_host_tracking(control->host)||count>4096||(count&&!items)||(!count&&selected)||(count&&!selected))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSMutableArray *labels=[NSMutableArray arrayWithCapacity:count],*tips=[NSMutableArray arrayWithCapacity:count];
  NSMutableArray *identifiers=[NSMutableArray arrayWithCapacity:count];
  NSMutableSet *seen=[NSMutableSet setWithCapacity:count];
  for(uint32_t i=0;i<count;i++) {
    if(items[i].size<sizeof(items[i])||!items[i].identifier){[pool drain];return 0;}
    NSNumber *identifier=[NSNumber numberWithUnsignedLongLong:items[i].identifier];
    NSString *label=items[i].title?[NSString stringWithUTF8String:items[i].title]:@"";
    NSString *tip=items[i].tooltip?[NSString stringWithUTF8String:items[i].tooltip]:nil;
    if(!label||(items[i].tooltip&&!tip)||[seen containsObject:identifier]){[pool drain];return 0;}
    [seen addObject:identifier];[identifiers addObject:identifier];[labels addObject:label];
    [tips addObject:tip?:[NSNull null]];
  }
  if(count&&![seen containsObject:[NSNumber numberWithUnsignedLongLong:selected]]){[pool drain];return 0;}
  NSTabView *view=(NSTabView *)control->view;
  NSMutableDictionary *existing=[NSMutableDictionary dictionary];
  for(NSTabViewItem *item in [view tabViewItems])[existing setObject:item forKey:[item identifier]];
  NSMutableArray *ordered=[NSMutableArray arrayWithCapacity:count];
  for(uint32_t i=0;i<count;i++) {
    NSTabViewItem *item=[existing objectForKey:[identifiers objectAtIndex:i]];
    if(!item)item=[[[NSTabViewItem alloc] initWithIdentifier:[identifiers objectAtIndex:i]] autorelease];
    [ordered addObject:item];
  }
  control->tab_syncing=YES;
  @try {
    for(uint32_t i=0;i<count;i++) {
      NSTabViewItem *item=[ordered objectAtIndex:i];
      NSInteger old=[view indexOfTabViewItem:item];
      if(old!=i) {
        if(old!=NSNotFound)remove_tab_item(view,item);
        [view insertTabViewItem:item atIndex:i];
      }
      [item setLabel:[labels objectAtIndex:i]];
      id tip=[tips objectAtIndex:i];[item setToolTip:tip==[NSNull null]?nil:tip];
    }
    while([view numberOfTabViewItems]>count)remove_tab_item(view,[view tabViewItemAtIndex:count]);
    NSTabViewItem *item=count?[view tabViewItemAtIndex:[view indexOfTabViewItemWithIdentifier:
      [NSNumber numberWithUnsignedLongLong:selected]]]:nil;
    if([view selectedTabViewItem]!=item)[view selectTabViewItem:item];
    [view setNeedsDisplay:YES];
  } @finally {control->tab_syncing=NO;}
  [pool drain];return 1;
}
NXSTabState nxs_gnustep_control_tab_state(NXSControl *control)
{
  NXSTabState state={.size=sizeof(state),.selected_index=-1};
  if(!control||control->kind!=NXS_TABVIEW||control->destroying)return state;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSTabView *view=(NSTabView *)control->view;NSTabViewItem *item=[view selectedTabViewItem];
  state.count=(uint32_t)[view numberOfTabViewItems];
  if(item){state.selected=[[item identifier] unsignedLongLongValue];state.selected_index=(int32_t)[view indexOfTabViewItem:item];}
  state.content=nxs_host_rect_from_view(control->host,view,[view contentRect]);
  [pool drain];
  return state;
}
NXSRect nxs_gnustep_control_tab_item_rect(NXSControl *control,uint64_t identifier)
{
  if(!control||control->kind!=NXS_TABVIEW||control->destroying)return (NXSRect){0};
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSTabView *view=(NSTabView *)control->view;
  NSInteger index=[view indexOfTabViewItemWithIdentifier:[NSNumber numberWithUnsignedLongLong:identifier]];
  NXSRect rect=index==NSNotFound?(NXSRect){0}:nxs_host_rect_from_view(control->host,view,[[view tabViewItemAtIndex:index] _tabRect]);
  [pool drain];return rect;
}
