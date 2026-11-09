/* Original Foundation/ICU cutover, copy, formatting and coding witnesses.
 * No calendar rules are implemented here. GPL-2.0-or-later. */
#define _GNU_SOURCE
#import <Foundation/Foundation.h>
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <dlfcn.h>
@interface NSCalendar (NXSGregorianWitness)
- (NSDate *)gregorianStartDate;
- (void)setGregorianStartDate:(NSDate *)date;
@end
static unsigned checks;
static void check(const char *name,BOOL passed)
{printf("{\"case\":\"%s\",\"passed\":%s}\n",name,passed?"true":"false");fflush(stdout);checks++;assert(passed);}
static NSCalendar *calendar(void)
{
  NSCalendar *result=[[[NSCalendar alloc] initWithCalendarIdentifier:NSCalendarIdentifierGregorian] autorelease];
  [result setLocale:[[[NSLocale alloc] initWithLocaleIdentifier:@"en_US_POSIX"] autorelease]];
  [result setTimeZone:[NSTimeZone timeZoneForSecondsFromGMT:0]];return result;
}
static NSDateFormatter *formatter(void)
{
  NSDateFormatter *result=[[[NSDateFormatter alloc] init] autorelease];
  [result setLocale:[[[NSLocale alloc] initWithLocaleIdentifier:@"en_US_POSIX"] autorelease]];
  [result setTimeZone:[NSTimeZone timeZoneForSecondsFromGMT:0]];[result setDateFormat:@"yyyy-MM-dd"];return result;
}
int main(int argc,char **argv)
{
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  [NSTimeZone setDefaultTimeZone:[NSTimeZone timeZoneForSecondsFromGMT:0]];
  if(argc==3&&!strcmp(argv[1],"--write-legacy")) {
    NSData *data=[NSKeyedArchiver archivedDataWithRootObject:@[calendar(),formatter()]];
    assert([data writeToFile:[NSString stringWithUTF8String:argv[2]] atomically:YES]);
    printf("{\"legacy_archive_written\":true}\n");[pool drain];return 0;
  }
  check("native-calendar-cutover-policy-is-available",[NSCalendar instancesRespondToSelector:@selector(setGregorianStartDate:)]);
  NSDate *first=[NSDate dateWithTimeIntervalSince1970:-62135596800.];
  NSDate *early=[NSDate dateWithTimeIntervalSince1970:-8640000000000.];
  NSDate *year1500=[NSDate dateWithTimeIntervalSince1970:-14831769600.];
  NSCalendar *c=calendar();NSDateFormatter *f=formatter();
  check("legacy-calendar-keeps-historical-cutover",[[c components:NSCalendarUnitDay fromDate:first] day]==3);
  check("legacy-formatter-keeps-historical-cutover",[[f stringFromDate:year1500] isEqual:@"1499-12-23"]);
  [c setGregorianStartDate:early];[c setFirstWeekday:2];[c setMinimumDaysInFirstWeek:4];[f setCalendar:c];
  check("native-calendar-retains-explicit-cutover",[[c gregorianStartDate] isEqual:early]);
  check("formatter-retains-calendar-instance-cutover",[[[f calendar] gregorianStartDate] isEqual:early]);
  const struct {double seconds;NSInteger year,month,day;const char *text;} cases[]={
    {-62135596800.,1,1,1,"0001-01-01"}, {-14831769600.,1500,1,1,"1500-01-01"},
    {-12220502400.,1582,10,1,"1582-10-01"}, {-12219292800.,1582,10,15,"1582-10-15"},
    {-2203891200.,1900,3,1,"1900-03-01"}, {951868800.,2000,3,1,"2000-03-01"}};
  for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);i++) {
    NSDate *date=[NSDate dateWithTimeIntervalSince1970:cases[i].seconds];
    NSDateComponents *parts=[c components:NSCalendarUnitEra|NSCalendarUnitYear|NSCalendarUnitMonth|NSCalendarUnitDay fromDate:date];
    check("ICU-proleptic-calendar-extracts-civil-components",[parts era]==1&&[parts year]==cases[i].year&&[parts month]==cases[i].month&&[parts day]==cases[i].day);
    [parts setHour:0];[parts setMinute:0];[parts setSecond:0];[parts setNanosecond:0];
    check("ICU-proleptic-calendar-constructs-original-instant",[[c dateFromComponents:parts] isEqual:date]);
    check("native-formatter-uses-same-proleptic-calendar",[[f stringFromDate:date] isEqual:[NSString stringWithUTF8String:cases[i].text]]);
  }
  NSCalendar *copy=[c copy];
  check("mutable-calendar-copy-is-independent",copy!=c&&[copy isEqual:c]&&[copy hash]==[c hash]);
  [copy setTimeZone:[NSTimeZone timeZoneForSecondsFromGMT:43200]];
  check("calendar-copy-does-not-change-original-zone",[[c timeZone] secondsFromGMT]==0&&[[copy timeZone] secondsFromGMT]==43200);
  check("calendar-copy-keeps-cutover-and-week-policy",[[copy gregorianStartDate] isEqual:early]&&[copy firstWeekday]==2&&[copy minimumDaysInFirstWeek]==4);
  [copy setLocale:[[[NSLocale alloc] initWithLocaleIdentifier:@"fr_FR"] autorelease]];
  check("calendar-reconfiguration-keeps-cutover",[[copy gregorianStartDate] isEqual:early]);[copy release];
  NSDateFormatter *fc=[f copy];[fc setCalendar:nil];
  check("formatter-copy-keeps-original-calendar-owned",[[f stringFromDate:first] isEqual:@"0001-01-01"]&&[[fc stringFromDate:year1500] isEqual:@"1499-12-23"]);[fc release];
  [f setDateFormat:@"yyyy-MM-dd HH:mm"];
  [f setTimeZone:[NSTimeZone timeZoneForSecondsFromGMT:-28800]];
  check("formatter-zone-still-overrides-calendar-zone",[[f stringFromDate:year1500] isEqual:@"1499-12-31 16:00"]);
  [f setTimeZone:[NSTimeZone timeZoneForSecondsFromGMT:0]];[f setDateFormat:@"yyyy-MM-dd"];
  check("formatter-reset-keeps-calendar-cutover",[[f stringFromDate:first] isEqual:@"0001-01-01"]);
  NSDateFormatter *direct=formatter();[direct setGregorianStartDate:early];
  check("existing-formatter-cutover-setter-is-functional",[[direct stringFromDate:first] isEqual:@"0001-01-01"]&&[[direct gregorianStartDate] isEqual:early]);
  [direct setDateFormat:@"yyyy-MM-dd"];[direct setTimeZone:[NSTimeZone timeZoneForSecondsFromGMT:0]];
  check("formatter-cutover-survives-reconfiguration",[[direct stringFromDate:first] isEqual:@"0001-01-01"]);
  [direct setGregorianStartDate:nil];
  check("nil-formatter-cutover-restores-legacy-policy",[[direct stringFromDate:year1500] isEqual:@"1499-12-23"]);
  for(unsigned keyed=0;keyed<2;keyed++) {
    id objects=@[c,f];NSData *data=keyed?[NSKeyedArchiver archivedDataWithRootObject:objects]:[NSArchiver archivedDataWithRootObject:objects];
    NSArray *decoded=keyed?[NSKeyedUnarchiver unarchiveObjectWithData:data]:[NSUnarchiver unarchiveObjectWithData:data];
    NSCalendar *cc=[decoded objectAtIndex:0];NSDateFormatter *ff=[decoded objectAtIndex:1];
    check("calendar-archive-keeps-cutover-and-week-policy",[[cc gregorianStartDate] isEqual:early]&&[cc firstWeekday]==2&&[cc minimumDaysInFirstWeek]==4);
    check("formatter-archive-keeps-native-proleptic-behavior",[[ff stringFromDate:first] isEqual:@"0001-01-01"]);
  }
  if(argc==2) {
    NSArray *old=[NSKeyedUnarchiver unarchiveObjectWithData:[NSData dataWithContentsOfFile:[NSString stringWithUTF8String:argv[1]]]];
    check("old-calendar-archive-retains-legacy-default",[[[old objectAtIndex:0] components:NSCalendarUnitDay fromDate:first] day]==3);
    check("old-formatter-archive-is-initialized-and-readable",[[[old objectAtIndex:1] stringFromDate:year1500] isEqual:@"1499-12-23"]);
  }
  [c setGregorianStartDate:nil];
  check("nil-calendar-cutover-restores-legacy-policy",[[c components:NSCalendarUnitDay fromDate:first] day]==3);
  printf("{\"passed\":%u}\n",checks);[pool drain];return 0;
}
