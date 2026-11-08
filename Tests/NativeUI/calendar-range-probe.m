/* Exercise Foundation calendar ranges used by the original native date picker.
 * ICU owns calendar rules; these are semantic witnesses, not another calendar.
 * GPL-2.0-or-later. */
#import <Foundation/Foundation.h>
#include <assert.h>
#include <stdio.h>
static unsigned checks;
static void check(const char *name,BOOL passed)
{printf("{\"case\":\"%s\",\"passed\":%s}\n",name,passed?"true":"false");fflush(stdout);checks++;assert(passed);}
int main(void)
{
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSCalendar *calendar=[[NSCalendar alloc] initWithCalendarIdentifier:NSCalendarIdentifierGregorian];
  NSTimeZone *utc=[NSTimeZone timeZoneForSecondsFromGMT:0];[calendar setTimeZone:utc];
  const int cases[][3]={{2026,11,30},{2026,4,30},{2026,1,31},{2024,2,29},{2025,2,28},{1900,2,28},{2000,2,29},{1969,12,31}};
  for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);i++) {
    NSDate *date=[NSCalendarDate dateWithYear:cases[i][0] month:cases[i][1] day:15 hour:12 minute:0 second:0 timeZone:utc];
    NSRange days=[calendar rangeOfUnit:NSCalendarUnitDay inUnit:NSCalendarUnitMonth forDate:date];
    char name[80];snprintf(name,sizeof(name),"ICU-calendar-month-length-%d-%02d",cases[i][0],cases[i][1]);
    check(name,days.location==1&&days.length==cases[i][2]);
    NSRange months=[calendar rangeOfUnit:NSCalendarUnitMonth inUnit:NSCalendarUnitYear forDate:date];
    check("native-Gregorian-year-has-twelve-one-based-months",months.location==1&&months.length==12);
  }
  NSDate *boundary=[NSCalendarDate dateWithYear:2026 month:7 day:1 hour:0 minute:30 second:0 timeZone:utc];
  check("UTC-calendar-boundary-is-July",[calendar rangeOfUnit:NSCalendarUnitDay inUnit:NSCalendarUnitMonth forDate:boundary].length==31);
  [calendar setTimeZone:[NSTimeZone timeZoneWithName:@"America/New_York"]];
  check("calendar-range-observes-local-month-at-same-instant",[calendar rangeOfUnit:NSCalendarUnitDay inUnit:NSCalendarUnitMonth forDate:boundary].length==30);
  check("missing-date-range-remains-unavailable",[calendar rangeOfUnit:NSCalendarUnitDay inUnit:NSCalendarUnitMonth forDate:nil].length==0);
  check("unsupported-unit-pair-remains-unavailable",[calendar rangeOfUnit:NSCalendarUnitHour inUnit:NSCalendarUnitYear forDate:boundary].length==0);
  printf("{\"passed\":%u}\n",checks);
  [calendar release];[pool drain];return 0;
}
