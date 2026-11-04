/* Exercise Workspace's actual run-loop shell client. SPDX-License-Identifier: MIT */
#import <Foundation/Foundation.h>
#import <AppKit/NSApplication.h>
#import "WSShellConnection.h"
#include <fcntl.h>
#include <signal.h>
#include <unistd.h>

static void output(NSDictionary *value)
{
  NSData *data = [NSJSONSerialization dataWithJSONObject:value options:0 error:NULL];
  fwrite([data bytes], 1, [data length], stdout); putchar('\n'); fflush(stdout);
}
static void outputEvent(NSString *event, WSShellConnection *connection)
{
  NSMutableDictionary *value = [NSMutableDictionary dictionaryWithObject:event forKey:@"event"];
  if (connection) [value setObject:[connection windows] forKey:@"windows"];
  if ([event isEqual:@"ready"]) [value setObject:[NSNumber numberWithBool:
    [[[NSProcessInfo processInfo] arguments] containsObject:@"--nextspace-restore-settings"]] forKey:@"restore_settings"];
  output(value);
}
static void outputScreens(WSShellConnection *connection)
{
  output([NSDictionary dictionaryWithObjectsAndKeys:@"outputs", @"event", [connection outputs], @"outputs",
    [NSNumber numberWithUnsignedInteger:[connection outputRevision]], @"revision", nil]);
}
static NSNumber *number(unsigned identifier) { return [NSNumber numberWithUnsignedInt:identifier]; }
static void outputDesktops(WSShellConnection *connection, NSString *event)
{
  output([NSDictionary dictionaryWithObjectsAndKeys:event, @"event",
    [NSNumber numberWithUnsignedInteger:[connection desktopIndex]], @"current",
    [NSNumber numberWithUnsignedInteger:[connection desktopCount]], @"count", nil]);
}

@interface ShellObserver : NSObject
@end
@implementation ShellObserver
- (void)changed:(NSNotification *)notification
{ outputEvent(@"windows", [notification object]); }
- (void)closed:(NSNotification *)notification { outputEvent(@"closed", nil); }
- (void)outputs:(NSNotification *)notification { outputScreens([notification object]); }
- (void)desktops:(NSNotification *)notification { outputDesktops([notification object], @"desktops"); }
- (void)inputs:(NSNotification *)notification
{
  NSMutableDictionary *value = [[[[notification object] inputSettings] mutableCopy] autorelease];
  [value setObject:@"input-settings" forKey:@"event"]; output(value);
}
- (void)result:(NSNotification *)notification
{
  NSMutableDictionary *result = [[[[notification object] outputResult] mutableCopy] autorelease];
  [result setObject:@"configuration-result" forKey:@"event"]; output(result);
}
@end

int main(int argc, char **argv)
{
  if (argc == 3 && strcmp(argv[1], "--fd-is-closed") == 0)
    return fcntl(atoi(argv[2]), F_GETFD) < 0 && errno == EBADF ? 0 : 1;
  if (argc == 2 && strcmp(argv[1], "--stubborn") == 0) {
    if (getenv("NEXTSPACE_SHELL_SOCKET")) return 8;
    signal(SIGTERM, SIG_IGN);
    printf("{\"event\":\"stubborn-ready\",\"pid\":%d}\n", getpid()); fflush(stdout);
    for (;;) pause();
  }
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  int descriptor = WSConsumeShellDescriptor();
  if (descriptor < 0) { [pool drain]; return 2; }
  if (getenv("NEXTSPACE_SHELL_SOCKET") || !(fcntl(descriptor, F_GETFD) & FD_CLOEXEC)) return 4;
  NSTask *helper = [NSTask launchedTaskWithLaunchPath:[[[NSProcessInfo processInfo] arguments] objectAtIndex:0]
    arguments:[NSArray arrayWithObjects:@"--fd-is-closed", [NSString stringWithFormat:@"%d", descriptor], nil]];
  [helper waitUntilExit];
  if ([helper terminationStatus]) return 7;
  WSShellConnection *connection = [[WSShellConnection alloc] initWithFileDescriptor:descriptor];
  if (!connection) { [pool drain]; return 3; }
  ShellObserver *observer = [ShellObserver new];
  [[NSNotificationCenter defaultCenter] addObserver:observer selector:@selector(changed:)
    name:WSShellWindowsDidChangeNotification object:connection];
  [[NSNotificationCenter defaultCenter] addObserver:observer selector:@selector(closed:)
    name:WSShellConnectionDidCloseNotification object:connection];
  [[NSNotificationCenter defaultCenter] addObserver:observer selector:@selector(outputs:)
    name:WSShellOutputsDidChangeNotification object:connection];
  [[NSNotificationCenter defaultCenter] addObserver:observer selector:@selector(result:)
    name:WSShellOutputResultNotification object:connection];
  [[NSNotificationCenter defaultCenter] addObserver:observer selector:@selector(inputs:)
    name:WSShellInputSettingsDidChangeNotification object:connection];
  [[NSNotificationCenter defaultCenter] addObserver:observer selector:@selector(desktops:)
    name:WSShellDesktopsDidChangeNotification object:connection];
  outputEvent(@"ready", connection);
  outputScreens(connection);
  fcntl(STDIN_FILENO, F_SETFL, fcntl(STDIN_FILENO, F_GETFL) | O_NONBLOCK);
  NSMutableData *input = [NSMutableData data];
  NSArray *modes = [NSArray arrayWithObjects:NSDefaultRunLoopMode, NSConnectionReplyMode,
                    NSModalPanelRunLoopMode, NSEventTrackingRunLoopMode, nil];
  NSString *mode = [modes objectAtIndex:argc > 1 ? atoi(argv[1]) : 0];
  BOOL finished = NO;
  while (!finished && [connection isConnected]) {
    NSAutoreleasePool *iteration = [NSAutoreleasePool new];
    [[NSRunLoop currentRunLoop] runMode:mode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.02]];
    char bytes[1024];
    ssize_t count = read(STDIN_FILENO, bytes, sizeof(bytes));
    if (count == 0) finished = YES;
    if (count > 0) [input appendBytes:bytes length:count];
    if ([input length] > 4096) return 5;
    for (;;) {
      const char *start = [input bytes];
      const char *newline = memchr(start, '\n', [input length]);
      if (!newline) break;
      NSString *line = [[[NSString alloc] initWithBytes:start length:newline - start
        encoding:NSUTF8StringEncoding] autorelease];
      unsigned identifier, desktop, sticky; int x, y, right, bottom;
      if ([line hasPrefix:@"desktop "] || [line hasPrefix:@"desktop-count "]) {
        NSArray *words = [line componentsSeparatedByString:@" "];
        BOOL count = [[words objectAtIndex:0] isEqualToString:@"desktop-count"];
        NSUInteger value = [[words lastObject] integerValue];
        if (count) [connection configureDesktops:value]; else [connection switchDesktop:value];
        outputDesktops(connection, @"desktops");
        outputDesktops(connection, @"desktop-result");
      } else if (sscanf([line UTF8String], "window-desktop %u %u %u", &identifier, &desktop, &sticky) == 3) {
        [connection setWindow:[NSNumber numberWithUnsignedInt:identifier] desktop:desktop sticky:sticky != 0];
      } else if (sscanf([line UTF8String], "insets %u %d %d %d %d", &identifier, &x, &y, &right, &bottom) == 5) {
        [connection setOutput:number(identifier) insets:[NSArray arrayWithObjects:[NSNumber numberWithInt:x],
          [NSNumber numberWithInt:y], [NSNumber numberWithInt:right], [NSNumber numberWithInt:bottom], nil]];
      } else if ([line hasPrefix:@"{"]) {
        NSDictionary *request = [NSJSONSerialization JSONObjectWithData:[line dataUsingEncoding:NSUTF8StringEncoding]
          options:0 error:NULL];
        NSString *action = [request objectForKey:@"action"];
        if ([action isEqualToString:@"title-appearance"]) {
          BOOL queued = [connection setTitleAppearance:[request objectForKey:@"settings"]];
          output([NSDictionary dictionaryWithObjectsAndKeys:@"title-appearance", @"event",
            [NSNumber numberWithBool:queued], @"queued",
            [NSNumber numberWithBool:!queued || [connection refreshOutputs]], @"synchronized", nil]);
        } else if ([action isEqualToString:@"background"]) {
          NSDictionary *color = [request objectForKey:@"color"] ?
            [connection setBackgroundColor:[request objectForKey:@"color"]] : [connection backgroundColor];
          NSMutableDictionary *value = [[color mutableCopy] autorelease];
          if (!value) value = [NSMutableDictionary dictionaryWithObject:[NSNumber numberWithBool:NO] forKey:@"success"];
          [value setObject:@"background" forKey:@"event"]; output(value);
        } else if ([action isEqualToString:@"gamma"]) {
          NSDictionary *result = [connection setOutput:[request objectForKey:@"id"] gamma:[request objectForKey:@"settings"]];
          NSMutableDictionary *value = [[result mutableCopy] autorelease];
          if (!value) value = [NSMutableDictionary dictionaryWithObject:[NSNumber numberWithBool:NO] forKey:@"success"];
          [value setObject:@"gamma-result" forKey:@"event"]; output(value);
        } else if ([action isEqualToString:@"input-state"]) {
          [connection refreshInputSettings];
          NSMutableDictionary *value = [[[connection inputSettings] mutableCopy] autorelease];
          [value setObject:@"input-settings" forKey:@"event"]; output(value);
        } else if ([action isEqualToString:@"keyboard"] || [action isEqualToString:@"pointer"] ||
                   [action isEqualToString:@"shortcuts"]) {
          NSDictionary *result;
          if ([action isEqualToString:@"keyboard"]) result = [connection setKeyboardSettings:[request objectForKey:@"settings"]];
          else if ([action isEqualToString:@"pointer"]) result = [connection setPointerSettings:[request objectForKey:@"settings"]];
          else result = [connection setShortcuts:[request objectForKey:@"bindings"]];
          NSMutableDictionary *value = [[result mutableCopy] autorelease];
          if (!value) value = [NSMutableDictionary dictionaryWithObject:[NSNumber numberWithBool:NO] forKey:@"success"];
          [value setObject:@"input-result" forKey:@"event"]; output(value);
        } else if ([action isEqualToString:@"test"])
          [connection testOutputLayout:[request objectForKey:@"layout"]
            revision:[[request objectForKey:@"revision"] unsignedIntegerValue]];
        else if ([action isEqualToString:@"apply"])
          [connection applyOutputLayout:[request objectForKey:@"layout"]
            revision:[[request objectForKey:@"revision"] unsignedIntegerValue]
            timeout:[[request objectForKey:@"timeout"] unsignedIntegerValue]];
        else if ([action isEqualToString:@"confirm"]) [connection confirmOutputLayout];
        else if ([action isEqualToString:@"cancel"]) [connection cancelOutputLayout];
        else return 6;
      }
      else if ([line isEqualToString:@"outputs"]) { [connection refreshOutputs]; outputScreens(connection); }
      else if ([line isEqualToString:@"destroy-config"]) [connection discardOutputLayout];
      else if (sscanf([line UTF8String], "activate %u", &identifier) == 1) [connection activateWindow:number(identifier)];
      else if (sscanf([line UTF8String], "close %u", &identifier) == 1) [connection closeWindow:number(identifier)];
      else if (sscanf([line UTF8String], "snapshot-move %u %d %d", &identifier, &x, &y) == 3) {
        NSDictionary *snapshot = [connection windowForID:number(identifier)];
        [connection moveWindow:number(identifier) toPoint:NSMakePoint(x, y)];
        [connection refreshOutputs]; // Dispatch replacement metadata in a nested round trip.
        output([NSDictionary dictionaryWithObjectsAndKeys:@"window-snapshot", @"event",
          snapshot, @"before", [connection windowForID:number(identifier)], @"after", nil]);
      }
      else if (sscanf([line UTF8String], "move %u %d %d", &identifier, &x, &y) == 3)
        [connection moveWindow:number(identifier) toPoint:NSMakePoint(x, y)];
      else if (sscanf([line UTF8String], "minimize %u %d", &identifier, &x) == 2)
        [connection setWindow:number(identifier) minimized:x != 0];
      else if (sscanf([line UTF8String], "shade %u %d", &identifier, &x) == 2)
        [connection setWindow:number(identifier) shaded:x != 0];
      else if (sscanf([line UTF8String], "present %u %d", &identifier, &x) == 2)
        [connection setWindow:number(identifier) presented:x != 0];
      else if ([line isEqualToString:@"snapshot"])
        outputEvent(@"windows", connection);
      else if ([line hasPrefix:@"launch "] || [line isEqualToString:@"stubborn"]) {
        BOOL stubborn = [line isEqualToString:@"stubborn"];
        NSString *executable = stubborn ? [[[NSProcessInfo processInfo] arguments] objectAtIndex:0] :
          [line substringFromIndex:7];
        NSArray *arguments = stubborn ? [NSArray arrayWithObject:@"--stubborn"] : [NSArray array];
        NSTask *task = [NSTask launchedTaskWithLaunchPath:executable arguments:arguments];
        output([NSDictionary dictionaryWithObjectsAndKeys:@"launched", @"event",
          number([task processIdentifier]), @"pid", nil]);
      }
      else if ([line isEqualToString:@"quit"]) finished = YES;
      else return 6;
      [input replaceBytesInRange:NSMakeRange(0, newline - start + 1) withBytes:NULL length:0];
    }
    [iteration drain];
  }
  [[NSNotificationCenter defaultCenter] removeObserver:observer];
  BOOL disconnected = ![connection isConnected];
  [observer release]; [connection release]; [pool drain];
  return disconnected ? 3 : 0;
}
