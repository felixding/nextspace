/* Exercise event delivery across nested run loops. LGPL-2.0-or-later. */
#import <AppKit/AppKit.h>
#import <GNUstepGUI/GSDisplayServer.h>
#include <time.h>
#include <stdlib.h>
#include <unistd.h>

static unsigned appMask = 1U << NSApplicationDefined;
static unsigned systemMask = 1U << NSSystemDefined;

static void require(BOOL condition, NSString *message)
{
  if (!condition) [NSException raise:@"EventQueueFailure" format:@"%@", message];
}

static NSEvent *nextEvent(unsigned mask, NSTimeInterval timeout, BOOL dequeue)
{
  return [GSCurrentServer() getEventMatchingMask:mask
    beforeDate:[NSDate dateWithTimeIntervalSinceNow:timeout]
    inMode:NSDefaultRunLoopMode dequeue:dequeue];
}

@interface QueueDriver : NSObject
{
  BOOL nestedMatched;
  NSUInteger posted;
}
- (void)post:(NSTimer *)timer;
- (void)schedule:(NSInteger)tag after:(NSTimeInterval)delay mode:(NSString *)mode;
- (void)nestedReply:(NSTimer *)timer;
- (void)nestedGet:(NSTimer *)timer;
- (NSDictionary *)run;
@end

@implementation QueueDriver
- (void)post:(NSTimer *)timer
{
  posted++;
  NSInteger tag = [[timer userInfo] integerValue];
  NSEventType type = tag < 0 ? NSSystemDefined : NSApplicationDefined;
  NSEvent *event = [NSEvent otherEventWithType:type location:NSZeroPoint
    modifierFlags:0 timestamp:0 windowNumber:0 context:nil subtype:0 data1:labs(tag) data2:0];
  [GSCurrentServer() postEvent:event atStart:NO];
}
- (void)schedule:(NSInteger)tag after:(NSTimeInterval)delay mode:(NSString *)mode
{
  NSTimer *timer = [NSTimer timerWithTimeInterval:delay target:self selector:@selector(post:)
    userInfo:[NSNumber numberWithInteger:tag] repeats:NO];
  [[NSRunLoop currentRunLoop] addTimer:timer forMode:mode];
}
- (void)nestedReply:(NSTimer *)timer
{
  NSUInteger before = posted;
  [self schedule:1 after:0 mode:NSConnectionReplyMode];
  NSDate *limit = [NSDate dateWithTimeIntervalSinceNow:.02];
  while (posted == before && [limit timeIntervalSinceNow] > 0)
    [[NSRunLoop currentRunLoop] runMode:NSConnectionReplyMode beforeDate:limit];
}
- (void)nestedGet:(NSTimer *)timer
{
  [self schedule:4 after:0 mode:NSDefaultRunLoopMode];
  [self schedule:-5 after:.02 mode:NSDefaultRunLoopMode];
  NSEvent *event = nextEvent(systemMask, .5, YES);
  nestedMatched = event && [event data1] == 5;
}
- (NSDictionary *)run
{
  NSMutableArray *cases = [NSMutableArray array];
  while (nextEvent(NSAnyEventMask, 0, YES)) {}
  NSTimer *timer = [NSTimer timerWithTimeInterval:0 target:self
    selector:@selector(nestedReply:) userInfo:nil repeats:NO];
  [[NSRunLoop currentRunLoop] addTimer:timer forMode:NSDefaultRunLoopMode];
  NSEvent *event = nextEvent(appMask, .5, YES);
  require(event && [event data1] == 1, [NSString stringWithFormat:@"Nested reply input: event=%@ posted=%lu",event,(unsigned long)posted]);
  [cases addObject:@"nested-reply"];

  [self schedule:-2 after:0 mode:NSDefaultRunLoopMode];
  [self schedule:3 after:.15 mode:NSDefaultRunLoopMode];
  clock_t cpu = clock();
  event = nextEvent(appMask, .5, YES);
  double selectiveCPU = (double)(clock() - cpu) / CLOCKS_PER_SEC;
  require(event && [event data1] == 3, @"Selective wait returned the wrong event");
  require(selectiveCPU < .075, @"Selective wait spins on an unmatched event");
  [cases addObject:@"selective-wait"];
  event = nextEvent(systemMask, 0, YES);
  require(event && [event data1] == 2, @"Selective wait discarded an unmatched event");
  [cases addObject:@"unmatched-retained"];

  timer = [NSTimer timerWithTimeInterval:0 target:self
    selector:@selector(nestedGet:) userInfo:nil repeats:NO];
  [[NSRunLoop currentRunLoop] addTimer:timer forMode:NSDefaultRunLoopMode];
  event = nextEvent(appMask, .5, YES);
  require(nestedMatched && event && [event data1] == 4, @"Nested wait lost its caller's event");
  [cases addObject:@"nested-selective-wait"];

  [self schedule:6 after:0 mode:NSDefaultRunLoopMode];
  event = nextEvent(appMask, .5, NO);
  require(event && [event data1] == 6 && nextEvent(appMask, 0, NO) == event &&
    nextEvent(appMask, 0, YES) == event, @"Peeking changed or consumed the event");
  require(nextEvent(appMask, 0, YES) == nil, @"Dequeued event was delivered twice");
  [cases addObject:@"peek-and-dequeue"];

  [self schedule:-7 after:0 mode:NSDefaultRunLoopMode];
  cpu = clock();
  require(nextEvent(appMask, .15, YES) == nil, @"A selective timeout returned unmatched input");
  double idleCPU = (double)(clock() - cpu) / CLOCKS_PER_SEC;
  require(idleCPU < .075, @"An unmatched event made an idle wait spin");
  event = nextEvent(systemMask, 0, YES);
  require(event && [event data1] == 7, @"Timed wait discarded unmatched input");
  [cases addObject:@"idle-selective-timeout"];
  require(posted == 7, @"A scheduled input event did not run exactly once");
  return [NSDictionary dictionaryWithObjectsAndKeys:cases,@"cases",@YES,@"passed",
    [NSNumber numberWithDouble:selectiveCPU],@"selective_cpu_seconds",
    [NSNumber numberWithDouble:idleCPU],@"idle_cpu_seconds",
    [NSNumber numberWithUnsignedInteger:posted],@"posted_events",nil];
}
@end

int main(int argc, char **argv)
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  [NSApplication sharedApplication];
  NSWindow *window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0,0,32,32)
    styleMask:NSBorderlessWindowMask backing:NSBackingStoreBuffered defer:NO];
  printf("{\"ready\":true,\"pid\":%ld}\n", (long)getpid()); fflush(stdout);
  getchar();
  @try {
    QueueDriver *driver = [QueueDriver new];
    NSData *json = [NSJSONSerialization dataWithJSONObject:[driver run] options:0 error:NULL];
    fwrite([json bytes],1,[json length],stdout); puts(""); fflush(stdout); [driver release];
  } @catch (NSException *exception) {
    fprintf(stderr,"%s\n",[[exception description] UTF8String]); return 1;
  }
  [window release]; [pool drain]; return 0;
}
