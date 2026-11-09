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
static void color_open(NSView *view,void *context)
{
  NSColorWell *well=(NSColorWell *)view;
  if(context)[well activate:YES];
  else if([well isActive]){[well deactivate];[[NSColorPanel sharedColorPanel] orderOut:nil];}
}
int nxs_gnustep_control_color_open(NXSControl *control,int open)
{
  if(!specialized_idle(control,NXS_COLORWELL)||(open&&!control->enabled))return 0;
  return nxs_host_action(control->host,color_open,open?(void *)1:NULL);
}
int nxs_gnustep_control_color_sync(NXSControl *control,const NXSColorModel *model)
{
  if(!specialized_idle(control,NXS_COLORWELL)||!model||model->size<sizeof(*model)||
     !isfinite(model->red)||!isfinite(model->green)||!isfinite(model->blue)||!isfinite(model->alpha)||
     model->red<0||model->red>1||model->green<0||model->green>1||
     model->blue<0||model->blue>1||model->alpha<0||model->alpha>1)return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  [(NSColorWell *)control->view setColor:[NSColor colorWithCalibratedRed:model->red
    green:model->green blue:model->blue alpha:model->alpha]];
  [control->view setNeedsDisplay:YES];[pool drain];return 1;
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
  if((model->flags|control->date_flags)&(NXS_DATE_MONTH_START|NXS_DATE_PROLEPTIC_GREGORIAN|NXS_DATE_WEEK_START)) {
    NSCalendar *calendar=nil;
    if(model->flags&(NXS_DATE_MONTH_START|NXS_DATE_PROLEPTIC_GREGORIAN|NXS_DATE_WEEK_START)) {
      calendar=[[[NSCalendar alloc] initWithCalendarIdentifier:NSGregorianCalendar] autorelease];
      [calendar setGregorianStartDate:[NSDate dateWithTimeIntervalSince1970:-8640000000000.]];
      if(model->flags&NXS_DATE_WEEK_START){[calendar setFirstWeekday:2];[calendar setMinimumDaysInFirstWeek:4];}
    }
    [view setCalendar:calendar];
  }
  if(nullable_date_available())[(NSDatePickerCell *)[view cell] setAllowsEmptyDate:!!(model->flags&NXS_DATE_ALLOW_EMPTY)];
  [view setDatePickerElements:date_elements(model->elements)];
  [view setDatePickerStyle:(NSDatePickerStyle)model->style];
  [view setTimeZone:model->flags&NXS_DATE_UTC?[NSTimeZone timeZoneForSecondsFromGMT:0]:[NSTimeZone localTimeZone]];
  [view setMinDate:model->flags&NXS_DATE_MINIMUM?[NSDate dateWithTimeIntervalSince1970:model->minimum]:nil];
  [view setMaxDate:model->flags&NXS_DATE_MAXIMUM?[NSDate dateWithTimeIntervalSince1970:model->maximum]:nil];
  control->date_flags=model->flags&(NXS_DATE_TIME_OF_DAY|NXS_DATE_MONTH_START|NXS_DATE_PROLEPTIC_GREGORIAN|NXS_DATE_WEEK_START);
  [view setDateValue:model->flags&NXS_DATE_EMPTY?nil:[NSDate dateWithTimeIntervalSince1970:model->value]];
  [control->view setNeedsDisplay:YES];date_panel_model_changed(control);[pool drain];return 1;
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
