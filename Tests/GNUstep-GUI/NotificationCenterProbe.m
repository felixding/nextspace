/* Reentrant distributed-notification connection regression. SPDX-License-Identifier: MIT */
#import <Foundation/Foundation.h>
#include <objc/runtime.h>

@interface NotificationReceiver : NSObject
{
@public
  NSUInteger received;
}
- (void)notification:(NSNotification *)notification;
@end
@implementation NotificationReceiver
- (void)notification:(NSNotification *)notification { received++; }
@end

static NSDistributedNotificationCenter *center;
static NotificationReceiver *nestedReceiver;
static NSString *notificationName, *notificationObject;
static IMP originalLookup;
static BOOL reenter;
static NSUInteger nestedLookups;

static id lookup(id cls, SEL selector, id name, id host, id nameServer)
{
  if (reenter) {
    reenter = NO;
    nestedLookups++;
    /* A DO lookup can run a nested loop before _connect publishes its proxy. */
    [center addObserver:nestedReceiver selector:@selector(notification:)
      name:notificationName object:notificationObject];
  }
  return ((id (*)(id, SEL, id, id, id))originalLookup)(cls, selector, name, host, nameServer);
}

int main(void)
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  center = [NSDistributedNotificationCenter defaultCenter];
  nestedReceiver = [NotificationReceiver new];
  NotificationReceiver *receiver = [NotificationReceiver new];
  notificationName = @"NextSpaceReentrantNotification";
  notificationObject = [[[NSProcessInfo processInfo] globallyUniqueString] copy];
  Method method = class_getClassMethod([NSConnection class],
    @selector(rootProxyForConnectionWithRegisteredName:host:usingNameServer:));
  originalLookup = method_setImplementation(method, (IMP)lookup);
  reenter = YES;
  int result = 1;
  @try {
    [center addObserver:receiver selector:@selector(notification:)
      name:notificationName object:notificationObject];
    method_setImplementation(method, originalLookup);
    [center postNotificationName:notificationName object:notificationObject
      userInfo:nil deliverImmediately:YES];
    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:5];
    while ((receiver->received < 1 || nestedReceiver->received < 1) && [deadline timeIntervalSinceNow] > 0)
      [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.01]];
    if (nestedLookups == 1 && receiver->received == 1 && nestedReceiver->received == 1) {
      puts("Reentrant notification connection registers once and delivers to both observers: PASS");
      result = 0;
    } else fprintf(stderr, "Unexpected registration/delivery counts: %lu %lu %lu\n",
      (unsigned long)nestedLookups, (unsigned long)receiver->received, (unsigned long)nestedReceiver->received);
  } @catch (NSException *exception) {
    fprintf(stderr, "%s: %s\n", [[exception name] UTF8String], [[exception reason] UTF8String]);
  } @finally {
    method_setImplementation(method, originalLookup);
    [center removeObserver:receiver];
    [center removeObserver:nestedReceiver];
  }
  [notificationObject release];
  [receiver release]; [nestedReceiver release];
  [pool drain]; return result;
}
