/* Native chooser composition, lifecycle and independent calendar pixels.
 * No calendar, widget or input implementation is copied. GPL-2.0-or-later. */
#import <AppKit/AppKit.h>
#include "NativeUI.h"
#include <assert.h>
#include <objc/runtime.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <poll.h>
#include <unistd.h>
#include <time.h>
@interface NSCalendar (NXSCutoverWitness)
- (void)setGregorianStartDate:(NSDate *)date;
@end
@interface NSInputManager (NXSBindingWitness)
- (void)loadBindingsFromFile:(NSString *)path;
@end
@interface NSGraphicsContext (NXSReadbackWitness)
- (NSDictionary *)GSReadRectAtBackingScale:(NSRect)rect;
@end
static IMP original_panel_key,original_panel_command;
static SEL last_panel_command;
static void panel_key_witness(id self,SEL selector,NSEvent *event)
{fprintf(stderr,"chooser-key: char=%u flags=%lu\n",[[event characters] length]?(unsigned)[[event characters] characterAtIndex:0]:0,(unsigned long)[event modifierFlags]);((void (*)(id,SEL,id))original_panel_key)(self,selector,event);}
static void panel_command_witness(id self,SEL selector,SEL command)
{last_panel_command=command;fprintf(stderr,"chooser-command: %s\n",sel_getName(command));((void (*)(id,SEL,SEL))original_panel_command)(self,selector,command);}
static unsigned checks,actions;
static IMP original_calendar_draw;
static unsigned calendar_draws;
static double calendar_drawing_seconds;
static double monotonic_seconds(void)
{struct timespec now;assert(!clock_gettime(CLOCK_MONOTONIC,&now));return now.tv_sec+now.tv_nsec/1e9;}
static void calendar_draw_witness(id self,SEL selector,NSRect frame,NSView *view)
{
  double started=monotonic_seconds();
  ((void (*)(id,SEL,NSRect,id))original_calendar_draw)(self,selector,frame,view);
  if([[view window] isKindOfClass:[NSPanel class]]) {
    calendar_draws++;calendar_drawing_seconds+=monotonic_seconds()-started;
  }
}
static void check(const char *name,BOOL pass)
{printf("{\"case\":\"%s\",\"passed\":%s}\n",name,pass?"true":"false");fflush(stdout);checks++;assert(pass);}
static void changed(void *context,int event,const NXSControlState *state)
{assert(event==NXS_VALUE_CHANGED&&state->tracking);actions++;}
static void key(NXSControl *control,unsigned code)
{NXSKeyEvent event={.size=sizeof(event),.type=NXS_KEY_DOWN,.key=code,.text=""};check("native-panel-key-is-handled",nxs_control_key(control,&event)==NXS_INPUT_HANDLED);}
static NXSControl *create(void)
{
  NXSControl *control=nxs_control_create(NXS_DATEPICKER,changed,NULL,NULL);assert(control);
  NXSControlConfig config={.size=sizeof(config),.width=260,.height=30,.enabled=1};assert(nxs_control_sync(control,&config));
  assert(nxs_control_set_screen_origin(control,300,240));return control;
}
static NSPanel *panel(void)
{
  for(NSWindow *window in [NSApp windows])if([window isKindOfClass:[NSPanel class]]&&[window isVisible]&&[[window contentView] isKindOfClass:[NSDatePicker class]])return (NSPanel *)window;
  return nil;
}
static void place_panel(NXSControl *control,double x,double y)
{
  NSRect previous=[panel() frame];
  assert(nxs_control_popup_open(control,0)&&nxs_control_set_screen_origin(control,x,y));
  /* Native Wayland window configuration is asynchronous. Measure the mapped
   * panel after dispatch, not its previous frame immediately after a request. */
  for(unsigned i=0;i<10;i++)nxs_native_ui_dispatch_events(.01);
  assert(nxs_control_popup_open(control,1));
  NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:3];
  while(NSEqualRects([panel() frame],previous)&&[deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);
  assert(!NSEqualRects([panel() frame],previous));
}
static void compare(NXSControl *control,NXSDateModel model,const char *directory,double scale)
{
  assert(nxs_control_date_sync(control,&model)&&nxs_control_focus(control,1)&&nxs_control_popup_open(control,1));
  NSDatePicker *actual=(NSDatePicker *)[panel() contentView];assert(actual);
  NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:4];
  while(fabs([[actual window] backingScaleFactor]-scale)>.000001&&[deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);
  /* Compare actual windows at the same device-pixel phase. Reading a
   * fractional subrectangle through Cairo resamples it, while a borderless
   * reference has a different phase from the original panel's content. */
  NSSize outer=[[actual window] frame].size;
  printf("{\"event\":\"provider-window-ready\",\"pid\":%d,\"name\":\"calendar-panel\",\"title\":\"Date and Time\",\"pixel_width\":%ld,\"pixel_height\":%ld}\n",getpid(),lround(outer.width*scale),lround(outer.height*scale));fflush(stdout);
  struct pollfd input={STDIN_FILENO,POLLIN,0};deadline=[NSDate dateWithTimeIntervalSinceNow:10];
  while(poll(&input,1,0)==0&&[deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);
  char reply[32];assert(fgets(reply,sizeof(reply),stdin)&&!strcmp(reply,"captured\n"));
  assert(nxs_control_popup_open(control,0));
  NSDatePicker *reference=[[NSDatePicker alloc] initWithFrame:[actual bounds]];
  NSCalendar *calendar=[[[NSCalendar alloc] initWithCalendarIdentifier:NSGregorianCalendar] autorelease];
  [calendar setGregorianStartDate:[NSDate dateWithTimeIntervalSince1970:-8640000000000.]];
  [reference setCalendar:calendar];[reference setTimeZone:[NSTimeZone timeZoneForSecondsFromGMT:0]];
  [reference setDatePickerElements:NSYearMonthDayDatePickerElementFlag];[reference setDatePickerStyle:NSClockAndCalendarDatePickerStyle];
  [reference setDateValue:[NSDate dateWithTimeIntervalSince1970:model.value]];
  NSPanel *window=[[NSPanel alloc] initWithContentRect:[reference bounds] styleMask:NSTitledWindowMask|NSClosableWindowMask|NSUtilityWindowMask backing:NSBackingStoreBuffered defer:NO];
  [window setReleasedWhenClosed:NO];[window setContentView:reference];[window setFloatingPanel:YES];[window setTitle:@"Native date panel reference calendar-panel"];[window makeKeyAndOrderFront:nil];[window display];
  outer=[window frame].size;
  printf("{\"event\":\"reference\",\"pid\":%d,\"name\":\"calendar-panel\",\"native_window_reference\":true,\"pixel_width\":%ld,\"pixel_height\":%ld}\n",getpid(),lround(outer.width*scale),lround(outer.height*scale));fflush(stdout);
  deadline=[NSDate dateWithTimeIntervalSinceNow:10];
  while(poll(&input,1,0)==0&&[deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);
  assert(fgets(reply,sizeof(reply),stdin)&&!strcmp(reply,"captured\n"));
  [window close];[window release];[reference release];
}
int main(int argc,char **argv)
{
  NSAutoreleasePool *pool=[NSAutoreleasePool new];assert(argc>2);
  fprintf(stderr,"panel-provider: caps=%u error=%s\n",nxs_control_specialized_capabilities(),nxs_native_ui_error());
  check("native-date-panel-capability",(nxs_control_specialized_capabilities()&NXS_SPECIAL_DATE_PANEL)!=0);
  NXSControl *control=create();NXSDateModel model={.size=sizeof(model),.flags=NXS_DATE_UTC|NXS_DATE_ALLOW_EMPTY|NXS_DATE_PROLEPTIC_GREGORIAN,.elements=NXS_DATE_YEAR_MONTH_DAY,.value=1794009600};
  assert(nxs_control_date_sync(control,&model)&&nxs_control_focus(control,1));
  if(getenv("NXS_CALENDAR_PAINT_PROFILE")) {
    Method method=class_getInstanceMethod([NSDatePickerCell class],@selector(drawInteriorWithFrame:inView:));
    original_calendar_draw=method_getImplementation(method);
    class_replaceMethod([NSDatePickerCell class],@selector(drawInteriorWithFrame:inView:),
      (IMP)calendar_draw_witness,method_getTypeEncoding(method));
    for(unsigned iteration=0;iteration<8;iteration++) {
      calendar_draws=0;calendar_drawing_seconds=0;
      double started=monotonic_seconds();
      assert(nxs_control_popup_open(control,1));
      double elapsed=monotonic_seconds()-started;
      assert(panel()&&[[panel() contentView] class]==[NSDatePicker class]);
      printf("{\"event\":\"calendar-presentation\",\"iteration\":%u,\"open_seconds\":%.9f,\"paint_calls\":%u,\"paint_seconds\":%.9f}\n",
        iteration,elapsed,calendar_draws,calendar_drawing_seconds);fflush(stdout);
      assert(nxs_control_popup_open(control,0));
      for(unsigned i=0;i<4;i++)nxs_native_ui_dispatch_events(.01);
    }
    assert(nxs_control_destroy(control));[pool drain];return 0;
  }
  check("date-panel-starts-hidden",!nxs_control_popup_state(control).visible);
  check("date-panel-open-is-accepted",nxs_control_popup_open(control,1));
  check("date-panel-is-original-native-classes",[panel() isKindOfClass:[NSPanel class]]&&[[panel() contentView] class]==[NSDatePicker class]&&[[(NSDatePicker *)[panel() contentView] cell] class]==[NSDatePickerCell class]);
  fprintf(stderr,"date-panel-position: requested-x=300 actual=%s\n",[NSStringFromRect([panel() frame]) UTF8String]);
  check("date-panel-retains-the-supplied-screen-anchor",fabs(NSMinX([panel() frame])-300)<1);
  check("date-panel-open-is-not-an-edit",actions==0&&nxs_control_state(control).value==model.value);
  NXSPopupState state=nxs_control_popup_state(control);
  check("native-date-panel-has-native-calendar-metrics",state.visible&&state.frame.width>100&&state.frame.height>100&&state.highlighted==-1);
  NSPanel *first=panel();check("repeated-open-reuses-native-panel",nxs_control_popup_open(control,1)&&panel()==first);
  NSRect screen=[[NSScreen mainScreen] frame];
  place_panel(control,300,NSHeight(screen)-50);
  NSRect bottom_anchor=NSMakeRect(NSMinX(screen)+300,NSMinY(screen)+20,260,30);
  fprintf(stderr,"date-panel-bottom-edge: screen=%s requested=%s actual=%s relative-y=%.0f\n",[NSStringFromRect(screen) UTF8String],[NSStringFromRect(bottom_anchor) UTF8String],[NSStringFromRect([first frame]) UTF8String],nxs_control_popup_state(control).frame.y);
  check("bottom-edge-calendar-keeps-source-row-clickable",!NSIntersectsRect([first frame],bottom_anchor)&&NSMinY([first frame])>=NSMaxY(bottom_anchor)+4);
  check("repositioning-calendar-does-not-edit-owner",actions==0&&nxs_control_state(control).value==model.value);
  /* Exercise fractional native geometry independently of output density.
   * The original popup's content must stay wholly above its source row. */
  const double heights[]={64./3.,19.2,29.7};
  for(unsigned i=0;i<sizeof(heights)/sizeof(*heights);i++) {
    NXSControlConfig fractional={.size=sizeof(fractional),.width=260,.height=heights[i],.enabled=1};
    assert(nxs_control_sync(control,&fractional));
    place_panel(control,300+2*i,NSHeight(screen)-125);
    NXSPopupState placement=nxs_control_popup_state(control);
    check("fractional-source-row-keeps-calendar-above-and-clickable",placement.visible&&placement.frame.y+placement.frame.height<=-4);
  }
  NXSControlConfig restored={.size=sizeof(restored),.width=260,.height=30,.enabled=1};
  assert(nxs_control_sync(control,&restored));
  place_panel(control,300,50);
  NSRect top_anchor=NSMakeRect(NSMinX(screen)+300,NSMaxY(screen)-80,260,30);
  check("top-edge-calendar-keeps-source-row-clickable",!NSIntersectsRect([first frame],top_anchor)&&NSMaxY([first frame])<=NSMinY(top_anchor)-4);
  place_panel(control,300,240);
  NXSControl *opener=nxs_control_create(NXS_BUTTON,NULL,NULL,NULL);assert(opener);
  NXSControlConfig opener_config={.size=sizeof(opener_config),.width=100,.height=24,.enabled=1};
  assert(nxs_control_sync(opener,&opener_config)&&nxs_control_focus(opener,1));
  assert(nxs_control_popup_open(control,1));
  check("opener-focus-echo-keeps-native-calendar",nxs_control_focus(opener,1)&&nxs_control_popup_state(control).visible);
  check("unfocused-owner-echo-keeps-native-calendar",nxs_control_focus(control,0)&&nxs_control_popup_state(control).visible);
  check("opener-blur-keeps-native-calendar",nxs_control_focus(opener,0)&&nxs_control_popup_state(control).visible);
  check("delayed-opener-refocus-keeps-native-calendar",nxs_control_focus(opener,1)&&nxs_control_popup_state(control).visible);
  assert(nxs_control_focus(control,1)&&nxs_control_destroy(opener));
  key(control,NXS_KEY_RIGHT);
  fprintf(stderr,"panel-key: owner=%.0f actions=%u panel=%.0f key=%d first=%s app=%s\n",nxs_control_state(control).value,actions,[[(NSDatePicker *)[panel() contentView] dateValue] timeIntervalSince1970],[panel() isKeyWindow],class_getName([[panel() firstResponder] class]),class_getName([[NSApp keyWindow] class]));
  check("native-calendar-action-updates-owner-once",nxs_control_state(control).value==1794096000&&actions==1);
  fprintf(stderr,"panel-chain: next=%s nextnext=%s\n",class_getName([[(NSDatePicker *)[panel() contentView] nextResponder] class]),class_getName([[[(NSDatePicker *)[panel() contentView] nextResponder] nextResponder] class]));
  Class controller=NSClassFromString(@"NXSDatePanelController");
  Method key_method=class_getInstanceMethod(controller,@selector(keyDown:)),command_method=class_getInstanceMethod(controller,@selector(doCommandBySelector:));
  original_panel_key=method_getImplementation(key_method);original_panel_command=method_getImplementation(command_method);
  class_replaceMethod(controller,@selector(keyDown:),(IMP)panel_key_witness,method_getTypeEncoding(key_method));
  class_addMethod(controller,@selector(doCommandBySelector:),(IMP)panel_command_witness,method_getTypeEncoding(command_method));
  key(control,NXS_KEY_ESCAPE);
  check("native-installed-escape-selector-cancels-panel",!nxs_control_popup_state(control).visible&&sel_isEqual(last_panel_command,@selector(complete:))&&actions==1);
  assert(nxs_control_popup_open(control,1));
  NSString *bindings=[[NSString stringWithUTF8String:argv[1]] stringByAppendingPathComponent:@"chooser-key-bindings.dict"];
  assert([@{@"F6":@"cancelOperation:"} writeToFile:bindings atomically:YES]);
  [[NSInputManager currentInputManager] loadBindingsFromFile:bindings];
  key(control,NXS_KEY_F1+5);
  check("native-configured-selector-cancels-panel-without-edit",!nxs_control_popup_state(control).visible&&sel_isEqual(last_panel_command,@selector(cancelOperation:))&&actions==1);
  check("hidden-calendar-releases-native-key-window",![first isKeyWindow]);
  assert(nxs_control_popup_open(control,1));model.value=1794182400;assert(nxs_control_date_sync(control,&model));
  check("script-model-replacement-refreshes-native-calendar",[[(NSDatePicker *)[panel() contentView] dateValue] timeIntervalSince1970]==model.value&&actions==1);
  NXSControlConfig disabled={.size=sizeof(disabled),.width=260,.height=30,.enabled=0};assert(nxs_control_sync(control,&disabled));
  check("disabled-owner-closes-native-panel",!nxs_control_popup_state(control).visible&&!nxs_control_popup_open(control,1));
  disabled.enabled=1;assert(nxs_control_sync(control,&disabled)&&nxs_control_focus(control,1));
  model.flags|=NXS_DATE_EMPTY;model.value=0;assert(nxs_control_date_sync(control,&model)&&nxs_control_popup_open(control,1));
  check("empty-panel-shows-calendar-without-filling-owner",[[(NSDatePicker *)[panel() contentView] dateValue] isKindOfClass:[NSDate class]]&&nxs_control_state(control).state==-1&&actions==1);
  key(control,NXS_KEY_RIGHT);check("empty-calendar-edit-initializes-owner",nxs_control_state(control).state==0&&actions==2);
  check("logical-owner-blur-preserves-native-window-focus",nxs_control_focus(control,0)&&nxs_control_popup_state(control).visible&&[panel() isKeyWindow]);
  [panel() resignKeyWindow];
  check("native-key-resignation-closes-calendar",!nxs_control_popup_state(control).visible);
  assert(nxs_control_focus(control,1)&&nxs_control_popup_open(control,1));
  NXSControl *other=create();assert(nxs_control_date_sync(other,&model)&&nxs_control_focus(other,1));
  check("another-logical-owner-focus-keeps-native-calendar",nxs_control_popup_state(control).visible);
  assert(nxs_control_popup_open(other,1));
  check("another-native-panel-replaces-old-calendar",!nxs_control_popup_state(control).visible&&nxs_control_popup_state(other).visible);
  check("destroy-closes-owned-native-panel",nxs_control_destroy(other)&&!panel());
  assert(nxs_control_focus(control,1)&&nxs_control_popup_open(control,1));
  NSPanel *reopened=panel();assert(nxs_control_popup_open(control,0));
  check("explicit-panel-close-releases-native-key-window",![reopened isKeyWindow]);
  assert(nxs_control_popup_open(control,1));
  check("closed-panel-reopens-with-native-key-window",panel()==reopened&&[reopened isKeyWindow]);
  unsigned before_reopen=actions;key(control,NXS_KEY_RIGHT);
  check("reopened-panel-retains-original-native-editing",actions==before_reopen+1);
  assert(nxs_control_popup_open(control,0));
  model.flags&=~NXS_DATE_EMPTY;model.value=1794009600;compare(control,model,argv[1],atof(argv[2]));
  check("owner-destroy-after-panel-lifecycle",nxs_control_destroy(control));
  printf("{\"passed\":%u,\"images\":1,\"api_bytes\":%zu}\n",checks,sizeof(NXSNativeUIAPI));[pool drain];return 0;
}
