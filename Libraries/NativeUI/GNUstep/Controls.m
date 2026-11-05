/* Instantiate native controls; drawing and interaction remain in AppKit.
 * GPL-2.0-or-later. */
#import "ViewHost.h"
#include "Provider.h"
#include <math.h>
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
  BOOL text_selection_pending,destroying;
};
static int text_control(NXSControl *control)
{return control&&(control->kind==NXS_TEXTFIELD||control->kind==NXS_PASSWORD);}
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
}
- (void)changed:(id)sender;
- (void)willPopUp:(NSNotification *)notification;
- (void)controlTextDidChange:(NSNotification *)notification;
- (void)controlTextDidEndEditing:(NSNotification *)notification;
- (void)bindTextEditor;
@end
@implementation NXSControlAction
- (void)dealloc {[editor_delegate release];[super dealloc];}
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
  NSTextView *editor=(NSTextView *)[(NSTextField *)control->view currentEditor];
  if(!editor)return;
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
  return edit.replacement&&control->text_filter(control->text_filter_context,&edit);
}
- (BOOL)control:(NSControl *)view textView:(NSTextView *)editor doCommandBySelector:(SEL)selector
{control->text_command=selector;return nxs_host_command(control->host,selector,NXS_COMMAND_EXECUTE)>=0;}
- (void)willSendTextAction:(NSNotification *)notification
{if(nxs_host_focused(control->host))control->text_command=[[[notification userInfo] objectForKey:@"MenuItem"] action];}
- (void)controlTextDidBeginEditing:(NSNotification *)notification {[self bindTextEditor];}
- (void)changed:(id)sender
{
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

NXSControl *nxs_gnustep_control_create(int kind,NXSControlChanged changed,NXSPump pump,void *context)
{
  if(kind<NXS_BUTTON||kind>NXS_PASSWORD)return NULL;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  if(!nxs_host_initialize()){[pool drain];return NULL;}
  NXSControl *control=calloc(1,sizeof(*control));
  if(!control){[pool drain];return NULL;}
  NSView *view=nil;
  if(kind==NXS_TEXTFIELD||kind==NXS_PASSWORD) {
    view=kind==NXS_PASSWORD?[[NSSecureTextField alloc] initWithFrame:NSMakeRect(0,0,120,24)]:
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
  if(!control->host){free(control);[pool drain];return NULL;}
  control->kind=kind;control->enabled=1;control->changed=changed;control->context=context;
  control->text_selection=NSMakeRange(NSNotFound,0);
  if(kind!=NXS_PROGRESS) {
    NXSControlAction *target=[NXSControlAction new];target->control=control;control->target=target;
    [(NSControl *)view setTarget:target];[(NSControl *)view setAction:@selector(changed:)];
    if(text_control(control)) {
      [(NSTextField *)view setDelegate:(id)target];
      [[NSNotificationCenter defaultCenter] addObserver:target selector:@selector(willSendTextAction:)
        name:NSMenuWillSendActionNotification object:[NSTextView defaultMenu]];
    }
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
  if(text_control(control))[(NSTextField *)view setDelegate:nil];
  if(control->kind==NXS_POPUP||text_control(control))[[NSNotificationCenter defaultCenter] removeObserver:control->target];
  if(control->kind==NXS_PROGRESS)[(NSProgressIndicator *)view stopAnimation:nil];
  [view release];
  [control->target release];free(control);[pool drain];return 1;
}
int nxs_gnustep_control_sync(NXSControl *control,const NXSControlConfig *config)
{
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
  if(control->kind==NXS_PROGRESS) {
    NSProgressIndicator *view=(NSProgressIndicator *)control->view;
    [view setMinValue:config->minimum];[view setMaxValue:config->maximum];[view setDoubleValue:config->value];
    [view setIndeterminate:!!config->indeterminate];
    if(config->indeterminate&&control->enabled)[view startAnimation:nil];
    else [view stopAnimation:nil];
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
  if(control->kind==NXS_PROGRESS)state.value=[(NSProgressIndicator *)control->view doubleValue];
  else if(!text_control(control)) {
    state.value=control->kind==NXS_POPUP?[(NSPopUpButton *)control->view indexOfSelectedItem]:[(NSControl *)control->view doubleValue];
    if(control->kind!=NXS_SLIDER&&control->kind!=NXS_POPUP)state.state=[(NSButton *)control->view state];
  }
  return state;
}
NXSSize nxs_gnustep_control_size(NXSControl *control)
{
  if(!control)return (NXSSize){0};
  NSSize size=control->kind==NXS_PROGRESS?[control->view frame].size:[[(NSControl *)control->view cell] cellSize];
  return (NXSSize){size.width,size.height};
}
NXSBitmap nxs_gnustep_control_draw(NXSControl *control,double scale)
{return control?nxs_host_draw(control->host,scale):(NXSBitmap){0};}
void nxs_gnustep_control_track(NXSControl *control,double x,double y,unsigned modifiers)
{if(control&&control->enabled&&control->kind!=NXS_PROGRESS)nxs_host_track(control->host,x,y,modifiers);}
int nxs_gnustep_control_track_clicks(NXSControl *control,double x,double y,unsigned modifiers,unsigned clicks)
{return control&&control->enabled&&control->kind!=NXS_PROGRESS?nxs_host_track_clicks(control->host,x,y,modifiers,clicks):0;}
void nxs_gnustep_control_send(NXSControl *control,int event,double x,double y,unsigned modifiers)
{if(control)nxs_host_send(control->host,event,x,y,modifiers);}
int nxs_gnustep_control_focus(NXSControl *control,int focused)
{
  if(!control||(focused&&(!control->enabled||control->kind==NXS_PROGRESS)))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  int accepted=nxs_host_focus(control->host,focused);
  if(accepted&&focused&&text_control(control)&&control->text_selection_pending) {
    [[(NSTextField *)control->view currentEditor] setSelectedRange:control->text_selection];
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
  if(control)control->text_command=NULL;
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
  NSTextField *view=(NSTextField *)control->view;
  NSString *current=[view currentEditor]?[[view currentEditor] string]:[view stringValue];
  if(![current isEqualToString:text])[view setStringValue:text];
  if([view isEditable]!=!!model->editable)[view setEditable:!!model->editable];
  [(NXSControlAction *)control->target bindTextEditor];
  control->text_selection=model->selection_start==NXS_TEXT_NO_SELECTION?NSMakeRange(NSNotFound,0):
    NSMakeRange(model->selection_start,model->selection_length);
  NSText *editor=[view currentEditor];
  control->text_selection_pending=!editor&&control->text_selection.location!=NSNotFound;
  if(editor&&control->text_selection.location!=NSNotFound&&
     !NSEqualRanges([editor selectedRange],control->text_selection))
    [editor setSelectedRange:control->text_selection];
  [view setNeedsDisplay:YES];[pool drain];return 1;
}
size_t nxs_gnustep_control_text_get(NXSControl *control,char *buffer,size_t capacity,NXSTextState *state)
{
  if(!text_control(control)||(state&&state->size<sizeof(*state)))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSTextField *view=(NSTextField *)control->view;NSTextView *editor=(NSTextView *)[view currentEditor];
  NSString *text=editor?[editor string]:[view stringValue];
  const char *utf8=[text UTF8String];size_t required=utf8?strlen(utf8)+1:0;
  if(editor)control->text_selection=[editor selectedRange];
  NSRange marked=editor&&[editor hasMarkedText]?[editor markedRange]:NSMakeRange(NSNotFound,0);
  if(state)*state=(NXSTextState){.size=sizeof(*state),
    .selection_start=control->text_selection.location==NSNotFound?NXS_TEXT_NO_SELECTION:control->text_selection.location,
    .selection_length=control->text_selection.length,
    .marked_start=marked.location==NSNotFound?NXS_TEXT_NO_SELECTION:marked.location,.marked_length=marked.length,
    .editing=editor!=nil,.editable=[view isEditable],.secure=control->kind==NXS_PASSWORD};
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
