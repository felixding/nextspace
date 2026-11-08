/* Typed application data for original native controls. No control drawing,
 * parsing, calendar arithmetic or stepping algorithm is implemented here.
 * GPL-2.0-or-later. */
@interface NSDatePickerCell (NXSNullableDate)
- (BOOL) allowsEmptyDate;
- (void) setAllowsEmptyDate:(BOOL)flag;
@end
static int nullable_date_available(void)
{return [NSDatePickerCell instancesRespondToSelector:@selector(setAllowsEmptyDate:)];}
unsigned nxs_gnustep_control_specialized_capabilities(void)
{return NXS_SPECIAL_STEPPER|NXS_SPECIAL_COLOR|NXS_SPECIAL_DATE|
  (nullable_date_available()?NXS_SPECIAL_DATE_NULLABLE:0);}
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
    case NXS_DATE_YEAR_MONTH_DAY:return NSYearMonthDayDatePickerElementFlag;
    case NXS_DATE_HOUR_MINUTE:return NSHourMinuteDatePickerElementFlag;
    case NXS_DATE_HOUR_MINUTE_SECOND:return NSHourMinuteSecondDatePickerElementFlag;
    case NXS_DATE_DATE_AND_TIME:return NSYearMonthDayDatePickerElementFlag|NSHourMinuteSecondDatePickerElementFlag;
    default:return 0;
  }
}
int nxs_gnustep_control_date_sync(NXSControl *control,const NXSDateModel *model)
{
  if(!specialized_idle(control,NXS_DATEPICKER)||!model||model->size<sizeof(*model)||
     model->flags&~(NXS_DATE_MINIMUM|NXS_DATE_MAXIMUM|NXS_DATE_UTC|NXS_DATE_EMPTY|NXS_DATE_ALLOW_EMPTY)||!date_elements(model->elements)||
     ((model->flags&NXS_DATE_EMPTY)&&!(model->flags&NXS_DATE_ALLOW_EMPTY))||
     ((model->flags&NXS_DATE_ALLOW_EMPTY)&&!nullable_date_available())||
     model->style>NXS_DATE_TEXT||!isfinite(model->value)||
     ((model->flags&NXS_DATE_MINIMUM)&&!isfinite(model->minimum))||
     ((model->flags&NXS_DATE_MAXIMUM)&&!isfinite(model->maximum))||
     ((model->flags&3)==3&&model->minimum>model->maximum))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSDatePicker *view=(NSDatePicker *)control->view;
  if(nullable_date_available())[(NSDatePickerCell *)[view cell] setAllowsEmptyDate:!!(model->flags&NXS_DATE_ALLOW_EMPTY)];
  [view setDatePickerElements:date_elements(model->elements)];
  [view setDatePickerStyle:(NSDatePickerStyle)model->style];
  [view setTimeZone:model->flags&NXS_DATE_UTC?[NSTimeZone timeZoneForSecondsFromGMT:0]:[NSTimeZone localTimeZone]];
  [view setMinDate:model->flags&NXS_DATE_MINIMUM?[NSDate dateWithTimeIntervalSince1970:model->minimum]:nil];
  [view setMaxDate:model->flags&NXS_DATE_MAXIMUM?[NSDate dateWithTimeIntervalSince1970:model->maximum]:nil];
  [view setDateValue:model->flags&NXS_DATE_EMPTY?nil:[NSDate dateWithTimeIntervalSince1970:model->value]];
  [control->view setNeedsDisplay:YES];[pool drain];return 1;
}
int nxs_gnustep_control_date_get(NXSControl *control,NXSDateModel *model)
{
  if(!control||control->kind!=NXS_DATEPICKER||control->destroying||!model||model->size<sizeof(*model))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];NSDatePicker *view=(NSDatePicker *)control->view;
  NSDate *value=[view dateValue],*minimum=[view minDate],*maximum=[view maxDate];
  unsigned elements=0;for(unsigned i=NXS_DATE_YEAR_MONTH;i<=NXS_DATE_DATE_AND_TIME;i++)
    if(date_elements(i)==[view datePickerElements]){elements=i;break;}
  BOOL nullable=nullable_date_available()&&[(NSDatePickerCell *)[view cell] allowsEmptyDate];
  if((!value&&!nullable)||!elements){[pool drain];return 0;}
  *model=(NXSDateModel){.size=sizeof(*model),.elements=elements,.style=[view datePickerStyle],
    .flags=(minimum?NXS_DATE_MINIMUM:0)|(maximum?NXS_DATE_MAXIMUM:0)|
      ([[view timeZone] secondsFromGMTForDate:value?:[NSDate date]]==0?NXS_DATE_UTC:0)|
      (nullable?NXS_DATE_ALLOW_EMPTY:0)|(!value?NXS_DATE_EMPTY:0),
    .value=[value timeIntervalSince1970],.minimum=minimum?[minimum timeIntervalSince1970]:0,
    .maximum=maximum?[maximum timeIntervalSince1970]:0};
  [pool drain];return 1;
}
