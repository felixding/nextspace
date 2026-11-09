/* Compose original native panel/date-picker instances. AppKit owns calendar
 * drawing, selection, keyboard interpretation and native window chrome.
 * No date parser, calendar arithmetic or shortcut table is implemented here.
 * GPL-2.0-or-later. */
@class NXSDatePanelController;
static NXSDatePanelController *active_date_panel;
@interface NXSDatePanelController : NSViewController <NSWindowDelegate> {
 @public NXSControl *owner; NSPanel *panel; NSDatePicker *picker;
}
- (void)refresh;
- (void)position;
- (void)show;
- (void)close;
- (void)dateChanged:(id)sender;
@end
@implementation NXSDatePanelController
- (void)dealloc
{
  if(active_date_panel==self)active_date_panel=nil;
  [panel setDelegate:nil];[panel orderOut:nil];[panel release];[picker release];
  [super dealloc];
}
- (void)refresh
{
  NSDatePicker *source=(NSDatePicker *)owner->view;
  NSDatePickerCell *cell=[[source cell] copy];
  [picker setCell:cell];[cell release];
  [picker setDatePickerStyle:NSClockAndCalendarDatePickerStyle];
  /* The original day calendar selects a date in the requested week. The
   * existing shared model projection supplies the application's week value. */
  if(owner->date_flags&NXS_DATE_WEEK_START)[picker setDatePickerElements:NSYearMonthDayDatePickerElementFlag];
  [picker setTarget:self];[picker setAction:@selector(dateChanged:)];
  if(![picker dateValue])[picker setDateValue:[NSDate date]];
  NSSize size=[[picker cell] cellSize];
  [picker setFrameSize:size];[panel setContentSize:size];
  [picker setNeedsDisplay:YES];
}
- (void)show
{
  if(!panel) {
    picker=[[NSDatePicker alloc] initWithFrame:NSMakeRect(0,0,1,1)];
    panel=[[NSPanel alloc] initWithContentRect:[picker bounds]
      styleMask:NSTitledWindowMask|NSClosableWindowMask|NSUtilityWindowMask
      backing:NSBackingStoreBuffered defer:NO];
    [panel setReleasedWhenClosed:NO];[panel setDelegate:self];
    [panel setTitle:NSLocalizedString(@"Date and Time",nil)];
    [panel setFloatingPanel:YES];[panel setHidesOnDeactivate:YES];
    [panel setContentView:picker];[self setView:picker];
    [picker setNextResponder:self];[self setNextResponder:panel];
    nxs_host_bind_input_window(owner->host,panel);
  }
  [self refresh];
  [self position];
  active_date_panel=self;[panel makeFirstResponder:picker];[panel makeKeyAndOrderFront:nil];[panel display];
}
- (void)position
{
  NSRect anchor=[owner->view convertRect:[owner->view bounds] toView:nil];
  anchor=[[owner->view window] convertRectToScreen:anchor];
  NSRect frame=[panel frame];frame.origin=NSMakePoint(NSMinX(anchor),NSMinY(anchor)-NSHeight(frame));
  frame=[panel constrainFrameRect:frame toScreen:[[owner->view window] screen]];
  if(!NSEqualRects(frame,[panel frame]))[panel setFrame:frame display:NO];
}
- (void)close
{
  if(active_date_panel==self)active_date_panel=nil;
  if([panel isKeyWindow])[panel resignKeyWindow];
  [panel orderOut:nil];
}
- (void)windowWillClose:(NSNotification *)notification
{if(active_date_panel==self)active_date_panel=nil;}
- (void)windowDidResignKey:(NSNotification *)notification
{if(![panel isKeyWindow])[self close];}
/* The native input manager supplies selectors from the user's bindings.
 * These are chooser actions, independent of physical keys. */
- (void)keyDown:(NSEvent *)event {[self interpretKeyEvents:@[event]];}
- (void)cancelOperation:(id)sender {[self close];}
- (void)insertNewline:(id)sender {[self close];}
- (void)insertTab:(id)sender {[panel selectNextKeyView:sender];}
- (void)insertBacktab:(id)sender {[panel selectPreviousKeyView:sender];}
- (void)dateChanged:(id)sender
{
  if(!owner||owner->destroying||!owner->enabled)return;
  NXSControlState before=nxs_gnustep_control_state(owner);
  [(NSDatePicker *)owner->view setDateValue:[picker dateValue]];
  [owner->view setNeedsDisplay:YES];
  NXSControlState after=nxs_gnustep_control_state(owner);
  if(before.state!=after.state||before.value!=after.value)
    [(NXSControlAction *)owner->target changed:picker];
}
@end
static int date_panel_open(NXSControl *control,int open)
{
  if(!control||control->kind!=NXS_DATEPICKER||control->destroying||control->specialized_callback||
     nxs_host_tracking(control->host)||(open!=0&&open!=1)||(open&&!control->enabled))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NXSDatePanelController *controller=control->date_panel;
  if(open) {
    if(active_date_panel&&active_date_panel!=controller)[active_date_panel close];
    if(!controller){controller=[NXSDatePanelController new];controller->owner=control;control->date_panel=controller;}
    if(![controller->panel isVisible])[controller show];
  } else [controller close];
  [pool drain];return 1;
}
static NXSPopupState date_panel_state(NXSControl *control)
{
  NXSPopupState state={.size=sizeof(state),.highlighted=-1};
  NXSDatePanelController *controller=control->date_panel;
  if(controller&&[controller->panel isVisible]) {
    state.visible=1;state.frame=nxs_host_rect_from_view(control->host,controller->picker,[controller->picker bounds]);
  }
  return state;
}
static void date_panel_model_changed(NXSControl *control)
{
  NXSDatePanelController *controller=control->date_panel;
  if(controller&&[controller->panel isVisible]) {
    if(!control->enabled)[controller close];else [controller refresh];
  }
}
static void date_panel_position(NXSControl *control)
{
  NXSDatePanelController *controller=control->date_panel;
  if(controller&&[controller->panel isVisible])[controller position];
}
static void date_panel_focus(NXSControl *control,int focused)
{
  if(active_date_panel&&((focused&&active_date_panel->owner!=control)||(!focused&&active_date_panel->owner==control)))
    [active_date_panel close];
}
static void date_panel_destroy(NXSControl *control)
{
  NXSDatePanelController *controller=control->date_panel;if(!controller)return;
  [controller close];controller->owner=NULL;[controller release];control->date_panel=nil;
}
