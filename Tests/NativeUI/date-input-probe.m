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
static double last_action_value;
static int last_action_state;
static IMP original_init;
static NSDatePicker *observed;
@interface NSDatePickerCell (NXSDateInputWitness)
- (NSArray *)_editableFields;
- (void)_setSelectedFieldIndex:(NSInteger)index;
- (BOOL)displaysWeekOfYear;
- (NSInteger)_dayAtRow:(NSInteger)row column:(NSInteger)column;
- (NSRect)_dayCellRectAtRow:(NSInteger)row column:(NSInteger)column inFrame:(NSRect)frame ofView:(NSView *)view;
@end
@interface NSCalendar (NXSDateCutoverWitness)
- (void)setGregorianStartDate:(NSDate *)date;
@end
static void select_week_field(NSDatePicker *picker,unichar token)
{
  NSArray *fields=[(NSDatePickerCell *)[picker cell] _editableFields];BOOL found=NO;
  for(NSUInteger i=0;i<[fields count];i++)if([[fields objectAtIndex:i] characterAtIndex:0]==token) {
    [(NSDatePickerCell *)[picker cell] _setSelectedFieldIndex:i];found=YES;break;
  }
  assert(found);
}
static id witness_init(id self,SEL selector,NSRect frame)
{id result=((id (*)(id,SEL,NSRect))original_init)(self,selector,frame);observed=result;return result;}
static void check(const char *name,BOOL passed)
{printf("{\"case\":\"%s\",\"passed\":%s}\n",name,passed?"true":"false");fflush(stdout);checks++;assert(passed);}
static void changed(void *context,int event,const NXSControlState *state)
{assert(event==NXS_VALUE_CHANGED);actions++;last_action_value=state->value;last_action_state=state->state;}
static void key(NXSControl *control,unsigned code,const char *text)
{NXSKeyEvent event={.size=sizeof(event),.type=NXS_KEY_DOWN,.key=code,.text=text};nxs_control_key(control,&event);}
static double value(NXSControl *control)
{NXSDateModel model={.size=sizeof(model)};assert(nxs_control_date_get(control,&model));return model.value;}
static void compare(NXSControl *control,NXSDateModel *model,const char *directory,const char *name,double scale)
{
  assert(nxs_control_focus(control,0)&&nxs_control_date_sync(control,model));
  NSDatePicker *reference=[[NSDatePicker alloc] initWithFrame:NSMakeRect(0,0,260,30)];
  NSDatePickerElementFlags flags=model->elements==NXS_DATE_YEAR_WEEK?0x0200:model->elements==NXS_DATE_YEAR_MONTH?NSYearMonthDatePickerElementFlag:
    model->elements==NXS_DATE_HOUR_MINUTE_SECOND?NSHourMinuteSecondDatePickerElementFlag:
    model->elements==NXS_DATE_DATE_AND_TIME?(NSYearMonthDayDatePickerElementFlag|NSHourMinuteSecondDatePickerElementFlag):NSYearMonthDayDatePickerElementFlag;
  [reference setDatePickerElements:flags];[reference setDatePickerStyle:model->style];
  if(model->flags&(NXS_DATE_MONTH_START|NXS_DATE_PROLEPTIC_GREGORIAN|NXS_DATE_WEEK_START)) {
    NSCalendar *calendar=[[[NSCalendar alloc] initWithCalendarIdentifier:NSGregorianCalendar] autorelease];
    [calendar setGregorianStartDate:[NSDate dateWithTimeIntervalSince1970:-8640000000000.]];
    if(model->flags&NXS_DATE_WEEK_START){[calendar setFirstWeekday:2];[calendar setMinimumDaysInFirstWeek:4];}
    [reference setCalendar:calendar];
  }
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
  check("time-of-day-projection-capability-is-explicit",nxs_control_specialized_capabilities()&NXS_SPECIAL_TIME_OF_DAY);
  model=(NXSDateModel){.size=sizeof(model),.flags=NXS_DATE_UTC|NXS_DATE_ALLOW_EMPTY|NXS_DATE_TIME_OF_DAY,
    .elements=NXS_DATE_HOUR_MINUTE_SECOND,.style=NXS_DATE_TEXT_AND_STEPPER,.value=86399.875};
  prior=actions;assert(nxs_control_date_sync(control,&model));
  check("clock-model-sync-preserves-fraction-without-action",value(control)==86399.875&&actions==prior);
  key(control,NXS_KEY_UP_ARROW,"");
  check("original-native-clock-carries-through-midnight",[[observed dateValue] timeIntervalSince1970]>86400&&value(control)==3599.875&&actions==prior+1);
  check("clock-callback-uses-same-lossless-projected-model",last_action_state==0&&last_action_value==value(control));
  model.value=12.123;assert(nxs_control_date_sync(control,&model));
  check("clock-model-echo-preserves-nonbinary-milliseconds",value(control)==12.123);
  key(control,NXS_KEY_UP_ARROW,"");
  check("clock-action-echo-preserves-nonbinary-milliseconds",value(control)==3612.123&&last_action_value==3612.123);
  model.value=.123;assert(nxs_control_date_sync(control,&model));key(control,NXS_KEY_DOWN_ARROW,"");
  check("clock-pre-epoch-carry-preserves-nonbinary-milliseconds",value(control)==82800.123&&last_action_value==82800.123);
  model.value=.125;assert(nxs_control_date_sync(control,&model));prior=actions;key(control,NXS_KEY_DOWN_ARROW,"");
  check("original-native-clock-carries-back-before-epoch",[[observed dateValue] timeIntervalSince1970]<0&&value(control)==82800.125&&actions==prior+1);
  model.flags|=NXS_DATE_EMPTY;model.value=0;assert(nxs_control_date_sync(control,&model));prior=actions;
  check("empty-clock-model-and-focus-stay-empty",nxs_control_focus(control,1)&&nxs_control_state(control).state==-1&&actions==prior);
  key(control,NXS_KEY_UP_ARROW,"");
  check("first-empty-clock-edit-exports-time-without-hidden-date",value(control)>=0&&value(control)<86400&&actions==prior+1&&last_action_value==value(control));
  key(control,NXS_KEY_BACKSPACE,"");
  check("clock-clear-keeps-distinct-native-empty-state",nxs_control_state(control).state==-1&&last_action_state==-1&&last_action_value==0);
  NXSDateModel invalidClock=model;invalidClock.flags&=~NXS_DATE_UTC;
  check("clock-domain-requires-explicit-utc",!nxs_control_date_sync(control,&invalidClock));
  invalidClock=model;invalidClock.elements=NXS_DATE_YEAR_MONTH_DAY;
  check("clock-domain-rejects-date-elements",!nxs_control_date_sync(control,&invalidClock));
  invalidClock=model;invalidClock.flags&=~NXS_DATE_EMPTY;invalidClock.value=86400;
  check("clock-domain-rejects-noncanonical-day-value",!nxs_control_date_sync(control,&invalidClock));
  invalidClock=model;invalidClock.flags|=NXS_DATE_MINIMUM;invalidClock.minimum=-1;
  check("clock-domain-rejects-noncanonical-minimum",!nxs_control_date_sync(control,&invalidClock));
  invalidClock=model;invalidClock.flags|=NXS_DATE_MAXIMUM;invalidClock.maximum=86400;
  check("clock-domain-rejects-noncanonical-maximum",!nxs_control_date_sync(control,&invalidClock));
  model.flags=NXS_DATE_UTC;model.value=1794054600;assert(nxs_control_date_sync(control,&model));
  check("legacy-time-model-retains-complete-date-value",value(control)==model.value);
  check("month-start-projection-capability-is-explicit",nxs_control_specialized_capabilities()&NXS_SPECIAL_MONTH_START);
  model=(NXSDateModel){.size=sizeof(model),.flags=NXS_DATE_UTC|NXS_DATE_ALLOW_EMPTY|NXS_DATE_MONTH_START,
    .elements=NXS_DATE_YEAR_MONTH,.style=NXS_DATE_TEXT_AND_STEPPER,.value=1793491200};
  prior=actions;assert(nxs_control_date_sync(control,&model));
  NXSDateModel month={.size=sizeof(month)};assert(nxs_control_date_get(control,&month));
  check("month-model-round-trip-is-silent",month.flags==model.flags&&month.value==model.value&&actions==prior);
  [observed setDateValue:[NSDate dateWithTimeIntervalSince1970:1794095999.875]];
  check("month-model-projects-hidden-day-and-time-through-foundation",value(control)==1793491200);
  key(control,NXS_KEY_UP_ARROW,"");
  check("native-month-action-exports-canonical-first-day",value(control)==1796083200&&last_action_value==1796083200&&actions==prior+1);
  check("month-projection-does-not-replace-original-picker-date",[[observed dateValue] timeIntervalSince1970]!=value(control));
  model.value=-2678400;assert(nxs_control_date_sync(control,&model));key(control,NXS_KEY_DOWN_ARROW,"");
  check("native-month-action-retains-pre-epoch-domain",value(control)==-5270400&&last_action_value==-5270400);
  model.flags|=NXS_DATE_EMPTY;model.value=0;prior=actions;assert(nxs_control_date_sync(control,&model));
  check("native-month-empty-focus-is-silent",nxs_control_focus(control,1)&&nxs_control_state(control).state==-1&&actions==prior);
  key(control,NXS_KEY_UP_ARROW,"");assert(nxs_control_date_get(control,&month));
  NSCalendar *monthCalendar=[[[NSCalendar alloc] initWithCalendarIdentifier:NSGregorianCalendar] autorelease];
  [monthCalendar setTimeZone:[NSTimeZone timeZoneForSecondsFromGMT:0]];
  NSDateComponents *monthParts=[monthCalendar components:NSCalendarUnitDay|NSCalendarUnitHour|NSCalendarUnitMinute|NSCalendarUnitSecond
    fromDate:[NSDate dateWithTimeIntervalSince1970:month.value]];
  check("first-empty-month-edit-exports-no-hidden-day-or-time",!(month.flags&NXS_DATE_EMPTY)&&[monthParts day]==1&&
    [monthParts hour]==0&&[monthParts minute]==0&&[monthParts second]==0&&actions==prior+1);
  key(control,NXS_KEY_BACKSPACE,"");
  check("native-month-clear-preserves-empty-action",nxs_control_state(control).state==-1&&last_action_state==-1&&last_action_value==0);
  NXSDateModel invalidMonth=model;invalidMonth.flags&=~NXS_DATE_UTC;
  check("month-start-policy-requires-utc",!nxs_control_date_sync(control,&invalidMonth));
  invalidMonth=model;invalidMonth.flags|=NXS_DATE_TIME_OF_DAY;
  check("month-start-policy-rejects-clock-domain",!nxs_control_date_sync(control,&invalidMonth));
  invalidMonth=model;invalidMonth.elements=NXS_DATE_YEAR_MONTH_DAY;
  check("month-start-policy-requires-year-month-elements",!nxs_control_date_sync(control,&invalidMonth));
  invalidMonth=model;invalidMonth.flags&=~NXS_DATE_EMPTY;invalidMonth.value=1794095999.875;
  check("month-model-rejects-noncanonical-filled-value",!nxs_control_date_sync(control,&invalidMonth));
  invalidMonth=model;invalidMonth.flags|=NXS_DATE_MINIMUM;invalidMonth.minimum=1794095999.875;
  check("month-model-rejects-noncanonical-minimum",!nxs_control_date_sync(control,&invalidMonth));
  invalidMonth=model;invalidMonth.flags|=NXS_DATE_MAXIMUM;invalidMonth.maximum=1794095999.875;
  check("month-model-rejects-noncanonical-maximum",!nxs_control_date_sync(control,&invalidMonth));
  model.flags=NXS_DATE_UTC;model.value=1794095999.875;assert(nxs_control_date_sync(control,&model));
  check("legacy-year-month-retains-complete-date-value",value(control)==model.value);
  check("week-start-capability-is-explicit",nxs_control_specialized_capabilities()&NXS_SPECIAL_WEEK_START);
  model=(NXSDateModel){.size=sizeof(model),.flags=NXS_DATE_UTC|NXS_DATE_ALLOW_EMPTY|NXS_DATE_WEEK_START,
    .elements=NXS_DATE_YEAR_WEEK,.style=NXS_DATE_TEXT_AND_STEPPER,.value=1798416000};
  prior=actions;assert(nxs_control_date_sync(control,&model));
  NXSDateModel week={.size=sizeof(week)};assert(nxs_control_date_get(control,&week));
  check("week-model-round-trip-is-silent",week.value==model.value&&week.flags==model.flags&&actions==prior);
  check("week-editor-is-the-original-picker-extension",[(NSDatePickerCell *)[observed cell] displaysWeekOfYear]&&[[(NSDatePickerCell *)[observed cell] _editableFields] count]==2);
  [observed setDateValue:[NSDate dateWithTimeIntervalSince1970:1798761600]];
  check("week-projection-keeps-week-year-across-civil-year",value(control)==1798416000);
  assert(nxs_control_focus(control,1));select_week_field(observed,'w');key(control,NXS_KEY_UP_ARROW,"");
  check("native-week-step-carries-week-53-to-next-week-year",value(control)==1799020800&&last_action_value==1799020800&&actions==prior+1);
  model.value=1766966400;assert(nxs_control_date_sync(control,&model));select_week_field(observed,'Y');key(control,NXS_KEY_UP_ARROW,"");
  check("native-week-year-step-is-not-a-civil-year-step",value(control)==1799020800&&last_action_value==1799020800);
  model.value=-259200;assert(nxs_control_date_sync(control,&model));select_week_field(observed,'w');key(control,NXS_KEY_DOWN_ARROW,"");
  check("native-week-step-retains-pre-epoch-domain",value(control)==-864000&&last_action_value==-864000);
  model.value=-62135596800.;assert(nxs_control_date_sync(control,&model));select_week_field(observed,'w');key(control,NXS_KEY_UP_ARROW,"");
  check("native-week-step-retains-first-year-domain",value(control)==-62134992000.&&last_action_value==-62134992000.);
  model.value=1798416000;assert(nxs_control_date_sync(control,&model));select_week_field(observed,'w');key(control,0,"5");key(control,0,"2");
  check("native-week-digit-entry-uses-existing-field-editor",value(control)==1797811200&&last_action_value==1797811200);
  model.flags|=NXS_DATE_EMPTY;model.value=0;prior=actions;assert(nxs_control_date_sync(control,&model));
  check("native-empty-week-focus-is-silent",nxs_control_focus(control,1)&&nxs_control_state(control).state==-1&&actions==prior);
  select_week_field(observed,'w');key(control,NXS_KEY_UP_ARROW,"");assert(nxs_control_date_get(control,&week));
  NSCalendar *weekCalendar=[[[NSCalendar alloc] initWithCalendarIdentifier:NSGregorianCalendar] autorelease];
  [weekCalendar setGregorianStartDate:[NSDate dateWithTimeIntervalSince1970:-8640000000000.]];
  [weekCalendar setTimeZone:[NSTimeZone timeZoneForSecondsFromGMT:0]];[weekCalendar setFirstWeekday:2];[weekCalendar setMinimumDaysInFirstWeek:4];
  NSDateComponents *weekParts=[weekCalendar components:NSCalendarUnitWeekday|NSCalendarUnitHour|NSCalendarUnitMinute|NSCalendarUnitSecond
    fromDate:[NSDate dateWithTimeIntervalSince1970:week.value]];
  check("first-empty-week-edit-exports-monday-midnight",!(week.flags&NXS_DATE_EMPTY)&&[weekParts weekday]==2&&[weekParts hour]==0&&[weekParts minute]==0&&[weekParts second]==0&&actions==prior+1);
  key(control,NXS_KEY_BACKSPACE,"");
  check("native-week-clear-preserves-empty-action",nxs_control_state(control).state==-1&&last_action_state==-1&&last_action_value==0);
  NXSDateModel invalidWeek=model;invalidWeek.flags&=~NXS_DATE_UTC;
  check("week-policy-requires-utc",!nxs_control_date_sync(control,&invalidWeek));
  invalidWeek=model;invalidWeek.flags|=NXS_DATE_TIME_OF_DAY;
  check("week-policy-rejects-clock-domain",!nxs_control_date_sync(control,&invalidWeek));
  invalidWeek=model;invalidWeek.flags|=NXS_DATE_MONTH_START;
  check("week-policy-rejects-month-domain",!nxs_control_date_sync(control,&invalidWeek));
  invalidWeek=model;invalidWeek.elements=NXS_DATE_YEAR_MONTH_DAY;
  check("week-policy-requires-week-elements",!nxs_control_date_sync(control,&invalidWeek));
  invalidWeek=model;invalidWeek.flags&=~NXS_DATE_EMPTY;invalidWeek.value=0;
  check("week-model-rejects-non-monday-value",!nxs_control_date_sync(control,&invalidWeek));
  invalidWeek=model;invalidWeek.flags|=NXS_DATE_MINIMUM;invalidWeek.minimum=1798416001;
  check("week-model-rejects-noncanonical-minimum",!nxs_control_date_sync(control,&invalidWeek));
  invalidWeek=model;invalidWeek.flags|=NXS_DATE_MAXIMUM;invalidWeek.maximum=1798416001;
  check("week-model-rejects-noncanonical-maximum",!nxs_control_date_sync(control,&invalidWeek));
  model.flags=NXS_DATE_UTC|NXS_DATE_WEEK_START;model.value=1798416000;
  assert(argc>2);double scale=atof(argv[2]);
  compare(control,&model,argv[1],"week-editor",scale);
  model.elements=NXS_DATE_YEAR_MONTH;

  model.flags=NXS_DATE_UTC|NXS_DATE_MONTH_START;model.value=1793491200;
  compare(control,&model,argv[1],"month-editor",scale);
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
