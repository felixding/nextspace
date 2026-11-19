/* Typed application data for original native controls. No control drawing,
 * parsing, calendar arithmetic or stepping algorithm is implemented here.
 * GPL-2.0-or-later. */
@interface NSDatePickerCell (NXSNullableDate)
- (BOOL) allowsEmptyDate;
- (BOOL) displaysWeekOfYear;
- (void) setAllowsEmptyDate:(BOOL)flag;
@end
@interface NSCalendar (NXSDateCutover)
- (void) setGregorianStartDate:(NSDate *)date;
@end
static int nullable_date_available(void)
{return [NSDatePickerCell instancesRespondToSelector:@selector(setAllowsEmptyDate:)];}
static int proleptic_date_available(void)
{return [NSCalendar instancesRespondToSelector:@selector(setGregorianStartDate:)];}
static int week_date_available(void)
{
  if(!proleptic_date_available()||![NSDatePickerCell instancesRespondToSelector:@selector(displaysWeekOfYear)])return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSCalendar *calendar=[[[NSCalendar alloc] initWithCalendarIdentifier:NSGregorianCalendar] autorelease];
  NSRange weeks=[calendar rangeOfUnit:NSCalendarUnitWeekOfYear inUnit:NSCalendarUnitYearForWeekOfYear
    forDate:[NSDate dateWithTimeIntervalSinceReferenceDate:0]];
  int available=weeks.location==1&&weeks.length>=52;[pool drain];return available;
}
unsigned nxs_gnustep_control_specialized_capabilities(void)
{return NXS_SPECIAL_STEPPER|NXS_SPECIAL_COLOR|NXS_SPECIAL_DATE|NXS_SPECIAL_TIME_OF_DAY|
  (proleptic_date_available()?NXS_SPECIAL_MONTH_START|NXS_SPECIAL_DATE_PROLEPTIC:0)|
  (nullable_date_available()?NXS_SPECIAL_DATE_NULLABLE|NXS_SPECIAL_DATE_PANEL:0)|(week_date_available()?NXS_SPECIAL_WEEK_START:0);}
static int specialized_idle(NXSControl *control,int kind)
{return control&&control->kind==kind&&!control->destroying&&!control->specialized_callback&&!nxs_host_tracking(control->host);}
/* Preserve the original NSColorPanel and delegate. An embedding with an
 * asynchronous application callback can complete that callback before the
 * original panel disappears and the next input reaches its owner. */
@interface NXSColorCloseDelegate : NSObject { @public NXSControl *owner;id original; }
@end
static NXSColorCloseDelegate *color_close_delegate;
static void color_close_request(NXSControl *control)
{
  NSColorPanel *panel=[NSColorPanel sharedColorPanel];
  if(nxs_host_owns_input_window(control->host,panel)) {
    control->color_close_pending=YES;
    [(NSColorWell *)control->view deactivate];
  }
}
@implementation NXSColorCloseDelegate
- (void)dealloc {[original release];[super dealloc];}
- (BOOL)respondsToSelector:(SEL)selector
{return [super respondsToSelector:selector]||[original respondsToSelector:selector];}
- (NSMethodSignature *)methodSignatureForSelector:(SEL)selector
{return [super methodSignatureForSelector:selector]?:[original methodSignatureForSelector:selector];}
- (void)forwardInvocation:(NSInvocation *)invocation {[invocation invokeWithTarget:original];}
- (BOOL)windowShouldClose:(id)window
{
  if([original respondsToSelector:_cmd]&&![original windowShouldClose:window])return NO;
  if(owner&&!owner->destroying&&owner->color_close_deferred) {
    color_close_request(owner);return NO;
  }
  return YES;
}
@end
static void color_close_forget(NXSControl *control)
{
  control->color_close_pending=NO;
  if(color_close_delegate&&color_close_delegate->owner==control) {
    NSColorPanel *panel=[NSColorPanel sharedColorPanel];
    color_close_delegate->owner=NULL;
    if([panel delegate]==color_close_delegate)[panel setDelegate:color_close_delegate->original];
  }
}
static void color_close_bind(NXSControl *control)
{
  control->color_close_pending=NO;
  if(!control->color_close_deferred) {
    if(color_close_delegate&&color_close_delegate->owner)color_close_forget(color_close_delegate->owner);
    return;
  }
  if(!color_close_delegate)color_close_delegate=[NXSColorCloseDelegate new];
  NSColorPanel *panel=[NSColorPanel sharedColorPanel];
  if([panel delegate]!=color_close_delegate) {
    id previous=[[panel delegate] retain];
    [color_close_delegate->original release];color_close_delegate->original=previous;
    [panel setDelegate:color_close_delegate];
  }
  color_close_delegate->owner=control;
}
int nxs_gnustep_control_color_lifecycle(NXSControl *control,unsigned phase)
{
  if(!control||control->kind!=NXS_COLORWELL||control->destroying||phase>NXS_COLOR_CLOSE_REQUEST)return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  if(phase==NXS_COLOR_CLOSE_REQUIRE_ACK)control->color_close_deferred=YES;
  else if(phase==NXS_COLOR_CLOSE_REQUEST)color_close_request(control);
  else {
    if(phase==NXS_COLOR_CLOSE_IMMEDIATE)control->color_close_deferred=NO;
    BOOL pending=control->color_close_pending;
    BOOL owns=nxs_host_owns_input_window(control->host,[NSColorPanel sharedColorPanel]);
    if(pending) {
      color_close_forget(control);
      if(owns) {
        /* This component host does not run NSApplication's window lifecycle. */
        [[NSColorPanel sharedColorPanel] resignKeyWindow];
        [[NSColorPanel sharedColorPanel] close];
        nxs_host_unbind_input_windows(control->host);
      }
    }
  }
  [pool drain];return 1;
}
struct NXSColorAction {NXSControl *control;int open;};
static void color_open(NSView *view,void *context)
{
  struct NXSColorAction *action=context;
  NSColorWell *well=(NSColorWell *)view;
  if(action->open) {
    color_close_bind(action->control);
    [well activate:YES];
    nxs_host_bind_input_window(action->control->host,[NSColorPanel sharedColorPanel]);
  } else if([well isActive]||nxs_host_owns_input_window(action->control->host,[NSColorPanel sharedColorPanel])) {
    /* The native well may already be inactive when its foreign owner is
     * removed. Reuse the existing window association to close its panel,
     * while preserving a panel subsequently adopted by another control. */
    [well deactivate];
    color_close_forget(action->control);
    [[NSColorPanel sharedColorPanel] resignKeyWindow];
    [[NSColorPanel sharedColorPanel] orderOut:nil];
    nxs_host_unbind_input_windows(action->control->host);
  }
}
int nxs_gnustep_control_color_open(NXSControl *control,int open)
{
  if(!specialized_idle(control,NXS_COLORWELL)||(open&&!control->enabled))return 0;
  struct NXSColorAction action={control,!!open};
  return nxs_host_action(control->host,color_open,&action);
}
int nxs_gnustep_control_color_sync(NXSControl *control,const NXSColorModel *model)
{
  if(!specialized_idle(control,NXS_COLORWELL)||!model||model->size<sizeof(*model)||
     !isfinite(model->red)||!isfinite(model->green)||!isfinite(model->blue)||!isfinite(model->alpha)||
     model->red<0||model->red>1||model->green<0||model->green>1||
     model->blue<0||model->blue>1||model->alpha<0||model->alpha>1)return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSColorWell *view=(NSColorWell *)control->view;
  NSColor *color=[NSColor colorWithCalibratedRed:model->red
    green:model->green blue:model->blue alpha:model->alpha];
  /* NSColorWell invalidates itself (and its active panel) in setColor:.
   * Echoing an unchanged model must not create another notification/paint. */
  if(![[view color] isEqual:color])[view setColor:color];
  [pool drain];return 1;
}
int nxs_gnustep_control_color_get(NXSControl *control,NXSColorModel *model)
{
  if(!control||control->kind!=NXS_COLORWELL||control->destroying||!model||model->size<sizeof(*model))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSColor *color=[[(NSColorWell *)control->view color] colorUsingColorSpaceName:NSCalibratedRGBColorSpace];
  if(!color){[pool drain];return 0;}
  CGFloat red,green,blue,alpha;[color getRed:&red green:&green blue:&blue alpha:&alpha];
  *model=(NXSColorModel){.size=sizeof(*model),.red=red,.green=green,.blue=blue,.alpha=alpha};
  [pool drain];return 1;
}
static NSDatePickerElementFlags date_elements(unsigned elements)
{
  switch(elements) {
    case NXS_DATE_YEAR_MONTH:return NSYearMonthDatePickerElementFlag;
    case NXS_DATE_YEAR_WEEK:return 0x0200; /* Original GUI GSYearWeekDatePickerElementFlag. */
    case NXS_DATE_YEAR_MONTH_DAY:return NSYearMonthDayDatePickerElementFlag;
    case NXS_DATE_HOUR_MINUTE:return NSHourMinuteDatePickerElementFlag;
    case NXS_DATE_HOUR_MINUTE_SECOND:return NSHourMinuteSecondDatePickerElementFlag;
    case NXS_DATE_DATE_AND_TIME:return NSYearMonthDayDatePickerElementFlag|NSHourMinuteSecondDatePickerElementFlag;
    default:return 0;
  }
}
static double date_value_for_flags(unsigned flags,NSDate *date)
{
  if(!date)return 0;
  if(!(flags&(NXS_DATE_TIME_OF_DAY|NXS_DATE_MONTH_START|NXS_DATE_WEEK_START)))return [date timeIntervalSince1970];
  /* Data projection only. The original picker retains its complete date and
   * calendar behavior; Foundation supplies its UTC clock components. Preserve
   * milliseconds without another clock/day arithmetic implementation. */
  NSCalendar *calendar=[[[NSCalendar alloc] initWithCalendarIdentifier:NSGregorianCalendar] autorelease];
  [calendar setTimeZone:[NSTimeZone timeZoneForSecondsFromGMT:0]];
  if(flags&(NXS_DATE_MONTH_START|NXS_DATE_PROLEPTIC_GREGORIAN|NXS_DATE_WEEK_START))
    [calendar setGregorianStartDate:[NSDate dateWithTimeIntervalSince1970:-8640000000000.]];
  if(flags&NXS_DATE_WEEK_START) {
    [calendar setFirstWeekday:2];[calendar setMinimumDaysInFirstWeek:4];
    NSDateComponents *parts=[calendar components:NSCalendarUnitEra|NSCalendarUnitYearForWeekOfYear|NSCalendarUnitWeekOfYear fromDate:date];
    [parts setWeekday:2];[parts setHour:0];[parts setMinute:0];[parts setSecond:0];[parts setNanosecond:0];
    NSDate *projected=[calendar dateFromComponents:parts];
    return projected?[projected timeIntervalSince1970]:NAN;
  }
  if(flags&NXS_DATE_MONTH_START) {
    NSDateComponents *parts=[calendar components:NSCalendarUnitEra|NSCalendarUnitYear|NSCalendarUnitMonth fromDate:date];
    [parts setDay:1];[parts setHour:0];[parts setMinute:0];[parts setSecond:0];[parts setNanosecond:0];
    NSDate *projected=[calendar dateFromComponents:parts];
    return projected?[projected timeIntervalSince1970]:NAN;
  }
  NSDateComponents *parts=[calendar components:NSCalendarUnitHour|NSCalendarUnitMinute|
    NSCalendarUnitSecond|NSCalendarUnitNanosecond fromDate:date];
  NSInteger milliseconds=[parts nanosecond]/1000000;
  [parts setNanosecond:0];
  [parts setEra:1];[parts setYear:1970];[parts setMonth:1];[parts setDay:1];
  NSDate *projected=[calendar dateFromComponents:parts];
  /* NSDate's reference-epoch subtraction can perturb small fractional times.
   * Keep Foundation's whole seconds and recompose canonical milliseconds as
   * data units, so a model echo never resets the native selected segment. */
  return projected?([projected timeIntervalSince1970]*1000.+milliseconds)/1000.:NAN;
}
static double date_model_value(NXSControl *control,NSDate *date)
{return date_value_for_flags(control->date_flags,date);}
int nxs_gnustep_control_date_sync(NXSControl *control,const NXSDateModel *model)
{
  if(!specialized_idle(control,NXS_DATEPICKER)||!model||model->size<sizeof(*model)||
     model->flags&~(NXS_DATE_MINIMUM|NXS_DATE_MAXIMUM|NXS_DATE_UTC|NXS_DATE_EMPTY|NXS_DATE_ALLOW_EMPTY|NXS_DATE_TIME_OF_DAY|NXS_DATE_MONTH_START|NXS_DATE_PROLEPTIC_GREGORIAN|NXS_DATE_WEEK_START)||!date_elements(model->elements)||
     ((model->elements==NXS_DATE_YEAR_WEEK)&&!(model->flags&NXS_DATE_WEEK_START))||
     ((model->flags&NXS_DATE_WEEK_START)&&(!week_date_available()||!(model->flags&NXS_DATE_UTC)||
       model->elements!=NXS_DATE_YEAR_WEEK||(model->flags&(NXS_DATE_TIME_OF_DAY|NXS_DATE_MONTH_START))))||
     ((model->flags&NXS_DATE_EMPTY)&&!(model->flags&NXS_DATE_ALLOW_EMPTY))||
     ((model->flags&NXS_DATE_ALLOW_EMPTY)&&!nullable_date_available())||
     ((model->flags&(NXS_DATE_MONTH_START|NXS_DATE_PROLEPTIC_GREGORIAN|NXS_DATE_WEEK_START))&&!proleptic_date_available())||
     ((model->flags&NXS_DATE_MONTH_START)&&(!(model->flags&NXS_DATE_UTC)||
       model->elements!=NXS_DATE_YEAR_MONTH||(model->flags&NXS_DATE_TIME_OF_DAY)))||
     ((model->flags&NXS_DATE_TIME_OF_DAY)&&(!(model->flags&NXS_DATE_UTC)||
       (model->elements!=NXS_DATE_HOUR_MINUTE&&model->elements!=NXS_DATE_HOUR_MINUTE_SECOND)||
       (!(model->flags&NXS_DATE_EMPTY)&&(model->value<0||model->value>=86400))||
       ((model->flags&NXS_DATE_MINIMUM)&&(model->minimum<0||model->minimum>=86400))||
       ((model->flags&NXS_DATE_MAXIMUM)&&(model->maximum<0||model->maximum>=86400))))||
     model->style>NXS_DATE_TEXT||!isfinite(model->value)||
     ((model->flags&NXS_DATE_MINIMUM)&&!isfinite(model->minimum))||
     ((model->flags&NXS_DATE_MAXIMUM)&&!isfinite(model->maximum))||
     ((model->flags&3)==3&&model->minimum>model->maximum))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  if((model->flags&(NXS_DATE_MONTH_START|NXS_DATE_WEEK_START))&&
      ((!(model->flags&NXS_DATE_EMPTY)&&date_value_for_flags(model->flags,[NSDate dateWithTimeIntervalSince1970:model->value])!=model->value)||
       ((model->flags&NXS_DATE_MINIMUM)&&date_value_for_flags(model->flags,[NSDate dateWithTimeIntervalSince1970:model->minimum])!=model->minimum)||
       ((model->flags&NXS_DATE_MAXIMUM)&&date_value_for_flags(model->flags,[NSDate dateWithTimeIntervalSince1970:model->maximum])!=model->maximum))) {
    [pool drain];return 0;
  }
  NSDatePicker *view=(NSDatePicker *)control->view;
  BOOL changed=NO;
  unsigned calendar_flags=NXS_DATE_MONTH_START|NXS_DATE_PROLEPTIC_GREGORIAN|NXS_DATE_WEEK_START;
  if((model->flags&calendar_flags)!=(control->date_flags&calendar_flags)) {
    NSCalendar *calendar=nil;
    if(model->flags&(NXS_DATE_MONTH_START|NXS_DATE_PROLEPTIC_GREGORIAN|NXS_DATE_WEEK_START)) {
      calendar=[[[NSCalendar alloc] initWithCalendarIdentifier:NSGregorianCalendar] autorelease];
      [calendar setGregorianStartDate:[NSDate dateWithTimeIntervalSince1970:-8640000000000.]];
      if(model->flags&NXS_DATE_WEEK_START){[calendar setFirstWeekday:2];[calendar setMinimumDaysInFirstWeek:4];}
    }
    [view setCalendar:calendar];changed=YES;
  }
  if(nullable_date_available()) {
    NSDatePickerCell *cell=(NSDatePickerCell *)[view cell];BOOL empty=!!(model->flags&NXS_DATE_ALLOW_EMPTY);
    if([cell allowsEmptyDate]!=empty){[cell setAllowsEmptyDate:empty];changed=YES;}
  }
  NSDatePickerElementFlags elements=date_elements(model->elements);
  if([view datePickerElements]!=elements){[view setDatePickerElements:elements];changed=YES;}
  if([view datePickerStyle]!=(NSDatePickerStyle)model->style){[view setDatePickerStyle:(NSDatePickerStyle)model->style];changed=YES;}
  NSTimeZone *zone=model->flags&NXS_DATE_UTC?[NSTimeZone timeZoneForSecondsFromGMT:0]:[NSTimeZone localTimeZone];
  if(![[view timeZone] isEqual:zone]){[view setTimeZone:zone];changed=YES;}
  NSDate *minimum=model->flags&NXS_DATE_MINIMUM?[NSDate dateWithTimeIntervalSince1970:model->minimum]:nil;
  NSDate *maximum=model->flags&NXS_DATE_MAXIMUM?[NSDate dateWithTimeIntervalSince1970:model->maximum]:nil;
  if([view minDate]!=minimum&&![[view minDate] isEqual:minimum]){[view setMinDate:minimum];changed=YES;}
  if([view maxDate]!=maximum&&![[view maxDate] isEqual:maximum]){[view setMaxDate:maximum];changed=YES;}
  unsigned flags=model->flags&(NXS_DATE_TIME_OF_DAY|NXS_DATE_MONTH_START|NXS_DATE_PROLEPTIC_GREGORIAN|NXS_DATE_WEEK_START);
  if(control->date_flags!=flags)changed=YES;
  control->date_flags=model->flags&(NXS_DATE_TIME_OF_DAY|NXS_DATE_MONTH_START|NXS_DATE_PROLEPTIC_GREGORIAN|NXS_DATE_WEEK_START);
  NSDate *value=model->flags&NXS_DATE_EMPTY?nil:[NSDate dateWithTimeIntervalSince1970:model->value];
  if([view dateValue]!=value&&![[view dateValue] isEqual:value]){[view setDateValue:value];changed=YES;}
  if(changed){[control->view setNeedsDisplay:YES];date_panel_model_changed(control);}
  [pool drain];return 1;
}
int nxs_gnustep_control_date_get(NXSControl *control,NXSDateModel *model)
{
  if(!control||control->kind!=NXS_DATEPICKER||control->destroying||!model||model->size<sizeof(*model))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];NSDatePicker *view=(NSDatePicker *)control->view;
  NSDate *value=[view dateValue],*minimum=[view minDate],*maximum=[view maxDate];
  unsigned elements=0;for(unsigned i=NXS_DATE_YEAR_MONTH;i<=NXS_DATE_YEAR_WEEK;i++)
    if(date_elements(i)==[view datePickerElements]){elements=i;break;}
  BOOL nullable=nullable_date_available()&&[(NSDatePickerCell *)[view cell] allowsEmptyDate];
  if((!value&&!nullable)||!elements){[pool drain];return 0;}
  *model=(NXSDateModel){.size=sizeof(*model),.elements=elements,.style=[view datePickerStyle],
    .flags=(minimum?NXS_DATE_MINIMUM:0)|(maximum?NXS_DATE_MAXIMUM:0)|
      ([[view timeZone] secondsFromGMTForDate:value?:[NSDate date]]==0?NXS_DATE_UTC:0)|
      (nullable?NXS_DATE_ALLOW_EMPTY:0)|(!value?NXS_DATE_EMPTY:0)|control->date_flags,
    .value=date_model_value(control,value),.minimum=minimum?date_model_value(control,minimum):0,
    .maximum=maximum?date_model_value(control,maximum):0};
  [pool drain];return 1;
}
