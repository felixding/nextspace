/* Measure the existing native date editor; never implement a date widget here.
 * GPL-2.0-or-later. */
#define _GNU_SOURCE
#import <AppKit/AppKit.h>
#include "NativeUI.h"
#include <objc/runtime.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <string.h>
#include <poll.h>
#include <unistd.h>
#include <dlfcn.h>
static unsigned checks,actions,images;
static IMP original_init;
static NSDatePicker *observed;
@interface NSDatePickerCell (NXSDateInputWitness)
- (NSInteger)_dayAtRow:(NSInteger)row column:(NSInteger)column;
- (NSRect)_dayCellRectAtRow:(NSInteger)row column:(NSInteger)column inFrame:(NSRect)frame ofView:(NSView *)view;
@end
static id witness_init(id self,SEL selector,NSRect frame)
{id result=((id (*)(id,SEL,NSRect))original_init)(self,selector,frame);observed=result;return result;}
static void check(const char *name,BOOL passed)
{printf("{\"case\":\"%s\",\"passed\":%s}\n",name,passed?"true":"false");fflush(stdout);checks++;assert(passed);}
static void changed(void *context,int event,const NXSControlState *state)
{assert(event==NXS_VALUE_CHANGED);actions++;}
static void key(NXSControl *control,unsigned code,const char *text)
{NXSKeyEvent event={.size=sizeof(event),.type=NXS_KEY_DOWN,.key=code,.text=text};nxs_control_key(control,&event);}
static double value(NXSControl *control)
{NXSDateModel model={.size=sizeof(model)};assert(nxs_control_date_get(control,&model));return model.value;}
static void compare(NXSControl *control,NXSDateModel *model,const char *directory,const char *name,double scale)
{
  assert(nxs_control_focus(control,0)&&nxs_control_date_sync(control,model));
  NSDatePicker *reference=[[NSDatePicker alloc] initWithFrame:NSMakeRect(0,0,260,30)];
  NSDatePickerElementFlags flags=model->elements==NXS_DATE_HOUR_MINUTE_SECOND?NSHourMinuteSecondDatePickerElementFlag:
    model->elements==NXS_DATE_DATE_AND_TIME?(NSYearMonthDayDatePickerElementFlag|NSHourMinuteSecondDatePickerElementFlag):NSYearMonthDayDatePickerElementFlag;
  [reference setDatePickerElements:flags];[reference setDatePickerStyle:model->style];
  [reference setTimeZone:[NSTimeZone timeZoneForSecondsFromGMT:0]];
  [reference setDateValue:[NSDate dateWithTimeIntervalSince1970:model->value]];
  NXSSize preferred=nxs_control_size(control);NSSize expected=[[reference cell] cellSize];
  check("original-date-preferred-cell-size",preferred.width==expected.width&&preferred.height==expected.height);
  NSSize size=model->style==NXS_DATE_CALENDAR?NSMakeSize(ceil(expected.width),ceil(expected.height)):NSMakeSize(260,30);
  NXSControlConfig config={.size=sizeof(config),.width=size.width,.height=size.height,.enabled=1};
  assert(nxs_control_sync(control,&config));[reference setFrameSize:size];
  NSWindow *window=[[NSWindow alloc] initWithContentRect:[reference bounds] styleMask:NSBorderlessWindowMask backing:NSBackingStoreBuffered defer:NO];
  [window setReleasedWhenClosed:NO];[[window contentView] addSubview:reference];
  [window setTitle:[NSString stringWithFormat:@"Native date input reference %s",name]];[window orderFront:nil];[window display];
  NXSBitmap bitmap=nxs_control_draw(control,scale);assert(bitmap.pixels);
  char path[1024];snprintf(path,sizeof(path),"%s/%s-native.argb",directory,name);FILE *out=fopen(path,"wb");assert(out);
  assert(fwrite(bitmap.pixels,bitmap.stride,bitmap.height,out)==(size_t)bitmap.height);fclose(out);
  printf("{\"event\":\"reference\",\"pid\":%d,\"name\":\"%s\",\"pixel_width\":%d,\"pixel_height\":%d,\"stride\":%d}\n",getpid(),name,bitmap.width,bitmap.height,bitmap.stride);fflush(stdout);
  struct pollfd input={STDIN_FILENO,POLLIN,0};NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:10];
  while(poll(&input,1,0)==0&&[deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);
  char reply[32];assert(fgets(reply,sizeof(reply),stdin)&&!strcmp(reply,"captured\n"));images++;
  [window close];[window release];[reference release];
}
int main(int argc,char **argv)
{
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  Method method=class_getInstanceMethod([NSDatePicker class],@selector(initWithFrame:));
  original_init=method_getImplementation(method);
  class_replaceMethod([NSDatePicker class],@selector(initWithFrame:),(IMP)witness_init,method_getTypeEncoding(method));
  NXSControl *control=nxs_control_create(NXS_DATEPICKER,changed,NULL,NULL);assert(control);
  class_replaceMethod([NSDatePicker class],@selector(initWithFrame:),original_init,method_getTypeEncoding(method));
  check("date-editor-is-original-native-class",[observed class]==[NSDatePicker class]&&[[observed cell] class]==[NSDatePickerCell class]);
  Dl_info gui_image,base_image;
  assert(dladdr((void *)class_getMethodImplementation([NSDatePicker class],@selector(keyDown:)),&gui_image));
  assert(dladdr((void *)class_getMethodImplementation([NSCalendar class],@selector(rangeOfUnit:inUnit:forDate:)),&base_image));
  printf("{\"event\":\"native-library-images\",\"gui\":\"%s\",\"base\":\"%s\"}\n",gui_image.dli_fname,base_image.dli_fname);fflush(stdout);
  NXSControlConfig config={.size=sizeof(config),.width=260,.height=30,.enabled=1};
  assert(nxs_control_sync(control,&config));
  NXSDateModel model={.size=sizeof(model),.flags=NXS_DATE_UTC,.elements=NXS_DATE_YEAR_MONTH_DAY,.value=1794054600};
  assert(nxs_control_date_sync(control,&model));
  check("date-model-sync-is-not-a-user-action",actions==0);
  assert(nxs_control_focus(control,1));
  NXSKeyEvent event={.size=sizeof(event),.type=NXS_KEY_DOWN,.key=NXS_KEY_UP_ARROW,.text=""};
  double before=[[observed dateValue] timeIntervalSince1970];
  int handled=nxs_control_key(control,&event);
  printf("{\"event\":\"date-key-observed\",\"handled\":%d,\"actions\":%u,\"before\":%.17g,\"after\":%.17g,\"native_segmented_editor\":%s}\n",handled,actions,before,[[observed dateValue] timeIntervalSince1970],[[observed cell] respondsToSelector:NSSelectorFromString(@"_handleKeyEvent:")]?"true":"false");fflush(stdout);
  check("original-native-date-key-produces-real-target-action",actions>0&&[[observed dateValue] timeIntervalSince1970]!=before);
  unsigned prior=actions;
  model.elements=NXS_DATE_HOUR_MINUTE_SECOND;assert(nxs_control_date_sync(control,&model));
  before=value(control);prior=actions;
  key(control,NXS_KEY_UP_ARROW,"");
  check("native-hour-key-retains-original-calendar-action",value(control)==before+3600&&actions==prior+1);
  key(control,NXS_KEY_RIGHT,"");before=value(control);prior=actions;
  key(control,NXS_KEY_UP_ARROW,"");
  check("native-field-navigation-then-minute-action",value(control)==before+60&&actions==prior+1);
  model.flags=NXS_DATE_UTC|NXS_DATE_MINIMUM|NXS_DATE_MAXIMUM;model.minimum=model.maximum=model.value;
  assert(nxs_control_date_sync(control,&model));prior=actions;key(control,NXS_KEY_UP_ARROW,"");
  check("native-date-clamping-emits-no-false-action",value(control)==model.value&&actions==prior);
  model.flags=NXS_DATE_UTC;model.elements=NXS_DATE_YEAR_MONTH_DAY;model.style=NXS_DATE_CALENDAR;
  assert(nxs_control_date_sync(control,&model));before=value(control);prior=actions;
  key(control,NXS_KEY_LEFT,"");
  check("original-calendar-left-key-changes-one-day",value(control)==before-86400&&actions==prior+1);
  before=value(control);prior=actions;key(control,NXS_KEY_UP_ARROW,"");
  check("original-calendar-up-key-changes-one-week",value(control)==before-604800&&actions==prior+1);
  assert(nxs_control_date_sync(control,&model));
  NSCalendar *calendar=[observed calendar];if(!calendar)calendar=[NSCalendar currentCalendar];
  NSDate *date=[observed dateValue];
  NSDateComponents *parts=[calendar components:NSCalendarUnitEra|NSCalendarUnitYear|NSCalendarUnitMonth fromDate:date];
  [parts setDay:1];NSRange days=[calendar rangeOfUnit:NSCalendarUnitDay inUnit:NSCalendarUnitMonth forDate:date];
  unsigned grid=0;for(unsigned i=0;i<42;i++)if([[observed cell] _dayAtRow:i/7 column:i%7]>0)grid++;
  printf("{\"event\":\"calendar-grid-observed\",\"days\":%lu,\"first_date_exists\":%s,\"grid_cells\":%u}\n",(unsigned long)days.length,[calendar dateFromComponents:parts]?"true":"false",grid);fflush(stdout);
  check("native-November-calendar-exposes-all-thirty-days",grid==30);
  NXSSize preferred=nxs_control_size(control);config.width=ceil(preferred.width);config.height=ceil(preferred.height);
  assert(nxs_control_sync(control,&config));
  NSRect hit=NSZeroRect;
  for(unsigned i=0;i<42;i++)if([[observed cell] _dayAtRow:i/7 column:i%7]==10)
    hit=[[observed cell] _dayCellRectAtRow:i/7 column:i%7 inFrame:[observed bounds] ofView:observed];
  check("native-calendar-provides-clickable-day-box",NSWidth(hit)>0&&NSHeight(hit)>0);
  double x=NSMidX(hit),y=[observed isFlipped]?NSMidY(hit):NSHeight([observed bounds])-NSMidY(hit);
  prior=actions;nxs_control_track(control,x,y,0);nxs_control_send(control,NXS_RELEASE,x,y,0);
  check("original-native-calendar-pointer-produces-target-action",[[calendar components:NSCalendarUnitDay fromDate:[observed dateValue]] day]==10&&actions==prior+1);
  config.enabled=0;assert(nxs_control_sync(control,&config));before=value(control);prior=actions;
  key(control,NXS_KEY_DOWN_ARROW,"");
  check("disabled-native-date-rejects-keyboard-action",value(control)==before&&actions==prior);
  config.enabled=1;assert(nxs_control_sync(control,&config));
  prior=actions;
  [observed setDateValue:nil];
  check("original-date-picker-can-display-no-value",[observed dateValue]==nil&&[[observed stringValue] length]==0);
  NXSDateModel empty={.size=sizeof(empty)};
  check("legacy-date-model-rejects-unopted-native-nil",!nxs_control_date_get(control,&empty));
  nxs_control_key(control,&event);
  check("original-empty-picker-does-not-invent-a-user-date",[observed dateValue]==nil&&actions==prior);
  if(nxs_control_specialized_capabilities()&NXS_SPECIAL_DATE_NULLABLE) {
    model.flags=NXS_DATE_UTC|NXS_DATE_ALLOW_EMPTY|NXS_DATE_EMPTY;model.value=0;
    model.elements=NXS_DATE_YEAR_MONTH_DAY;model.style=NXS_DATE_TEXT_AND_STEPPER;
    prior=actions;assert(nxs_control_date_sync(control,&model));
    NXSDateModel nullable={.size=sizeof(nullable)};assert(nxs_control_date_get(control,&nullable));
    check("nullable-date-model-preserves-empty-without-action",(nullable.flags&NXS_DATE_EMPTY)&&nullable.value==0&&actions==prior);
    NXSControlState state=nxs_control_state(control);
    check("native-action-state-distinguishes-empty-from-epoch",state.state==-1&&state.value==0);
    assert(nxs_control_focus(control,1));
    check("native-empty-focus-does-not-create-a-date",[observed dateValue]==nil&&actions==prior);
    key(control,NXS_KEY_UP_ARROW,"");
    assert(nxs_control_date_get(control,&nullable));
    check("first-native-empty-edit-creates-one-real-date-action",!(nullable.flags&NXS_DATE_EMPTY)&&actions==prior+1);
    NSCalendar *cal=[observed calendar];if(!cal)cal=[NSCalendar currentCalendar];
    [cal setTimeZone:[NSTimeZone timeZoneForSecondsFromGMT:0]];
    NSDateComponents *time=[cal components:NSCalendarUnitHour|NSCalendarUnitMinute|NSCalendarUnitSecond fromDate:[observed dateValue]];
    check("native-date-only-initial-edit-has-no-hidden-time",[time hour]==0&&[time minute]==0&&[time second]==0);
    prior=actions;key(control,NXS_KEY_BACKSPACE,"");assert(nxs_control_date_get(control,&nullable));
    check("native-date-clear-retains-nullable-model-and-action",(nullable.flags&NXS_DATE_EMPTY)&&actions==prior+1);
    prior=actions;key(control,NXS_KEY_BACKSPACE,"");
    check("repeated-native-empty-clear-is-not-another-edit",[observed dateValue]==nil&&actions==prior);
    key(control,NXS_KEY_TEXT,"1");assert(nxs_control_date_get(control,&nullable));
    check("native-digit-can-start-an-empty-date",!(nullable.flags&NXS_DATE_EMPTY)&&actions==prior+1);
    model.flags=NXS_DATE_UTC|NXS_DATE_ALLOW_EMPTY;model.value=0;
    assert(nxs_control_date_sync(control,&model));state=nxs_control_state(control);
    check("real-epoch-is-not-native-empty",state.state==0&&state.value==0);
    NXSDateModel invalid=model;invalid.flags=NXS_DATE_EMPTY;
    check("empty-model-requires-explicit-nullable-policy",!nxs_control_date_sync(control,&invalid)&&value(control)==0);
  }
  assert(argc>2);double scale=atof(argv[2]);
  model.flags=NXS_DATE_UTC;model.elements=NXS_DATE_YEAR_MONTH_DAY;model.style=NXS_DATE_TEXT_AND_STEPPER;
  compare(control,&model,argv[1],"date-editor",scale);
  model.elements=NXS_DATE_HOUR_MINUTE_SECOND;model.style=NXS_DATE_TEXT;
  compare(control,&model,argv[1],"time-editor",scale);
  model.elements=NXS_DATE_YEAR_MONTH_DAY;model.style=NXS_DATE_CALENDAR;
  compare(control,&model,argv[1],"calendar",scale);
  model.elements=NXS_DATE_DATE_AND_TIME;
  compare(control,&model,argv[1],"calendar-and-clock",scale);
  assert(nxs_control_destroy(control));
  printf("{\"passed\":%u,\"images\":%u,\"api_bytes\":%zu}\n",checks,images,sizeof(NXSNativeUIAPI));
  [pool drain];return 0;
}
