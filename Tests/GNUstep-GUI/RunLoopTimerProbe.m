/* Cancelled timers must stay bounded in modes which are not polled. */
#import <Foundation/Foundation.h>
#include <stdio.h>
#include <string.h>
static NSUInteger alive;
static NSUInteger fires;
@interface CountedTimer : NSTimer @end
@implementation CountedTimer
- (void)dealloc { alive--; [super dealloc]; }
@end
@interface Tick : NSObject
- (void)fire:(NSTimer *)timer;
@end
@implementation Tick
- (void)fire:(NSTimer *)timer { fires++; }
@end
int main(int argc,char **argv)
{
  NSAutoreleasePool *pool=[NSAutoreleasePool new]; Tick *target=[Tick new];
  NSRunLoop *loop=[NSRunLoop currentRunLoop];
  NSArray *modes=@[NSDefaultRunLoopMode,NSConnectionReplyMode,@"NSModalPanelRunLoopMode",@"NSEventTrackingRunLoopMode"];
  BOOL bounded=argc>1 && strcmp(argv[1],"--bounded")==0;NSUInteger peak=0;
  NSTimer *future=[[CountedTimer alloc] initWithFireDate:[NSDate distantFuture] interval:1 target:target selector:@selector(fire:) userInfo:nil repeats:YES];alive++;
  [loop addTimer:future forMode:@"NSModalPanelRunLoopMode"];[future release];
  for (NSUInteger batch=0;batch<10;batch++) {
    NSAutoreleasePool *temporary=[NSAutoreleasePool new];NSTimeInterval began=[NSDate timeIntervalSinceReferenceDate];
    for (NSUInteger n=0;n<1000;n++) {
      NSTimer *timer=[[CountedTimer alloc] initWithFireDate:[NSDate dateWithTimeIntervalSinceNow:.4]
        interval:.033 target:target selector:@selector(fire:) userInfo:nil repeats:YES];alive++;
      for (NSString *mode in modes) [loop addTimer:timer forMode:mode];
      [timer invalidate];[timer release];
      [loop limitDateForMode:NSDefaultRunLoopMode];[loop limitDateForMode:NSConnectionReplyMode];
    }
    if (alive>peak)peak=alive;
    printf("{\"batch\":%lu,\"seconds\":%.6f,\"retained_timers\":%lu}\n",(unsigned long)batch,[NSDate timeIntervalSinceReferenceDate]-began,(unsigned long)alive);fflush(stdout);
    if (bounded && alive>2)return 2;[temporary drain];
  }
  if (fires!=0 || ![future isValid])return 3;
  [future invalidate];for (NSString *mode in modes)[loop limitDateForMode:mode];if(alive!=0)return 4;
  NSTimer *once=[[CountedTimer alloc] initWithFireDate:[NSDate dateWithTimeIntervalSinceNow:-1]
    interval:1 target:target selector:@selector(fire:) userInfo:nil repeats:NO];alive++;
  [loop addTimer:once forMode:@"NativeTimerProbe"];[loop addTimer:once forMode:@"NativeTimerProbe"];
  [loop limitDateForMode:@"NativeTimerProbe"];[loop limitDateForMode:@"NativeTimerProbe"];
  if(fires!=1 || [once isValid])return 5;[once release];if(alive!=0)return 6;
  printf("{\"passed\":true,\"cancelled_timers\":10000,\"peak_retained_timers\":%lu,\"valid_timer_preserved\":true,\"duplicate_timer_fired_once\":true,\"remaining_timers\":%lu}\n",(unsigned long)peak,(unsigned long)alive);
  [target release];[pool drain];return 0;
}
