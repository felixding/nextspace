/* Event-driven active-window metadata to the independent native host.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import "WSNativeMenuConnection.h"
#import "WSShellConnection.h"
#import <AppKit/NSApplication.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

int WSConsumeNativeMenuDescriptor(void)
{
  static BOOL consumed = NO;
  if (consumed) return -1;
  consumed = YES;
  NSArray *arguments = [[NSProcessInfo processInfo] arguments];
  int descriptor = -1;
  for (NSUInteger index = 1; index < [arguments count]; index++) {
    if (![[arguments objectAtIndex:index] isEqual:@"--nextspace-native-menu-fd"]) continue;
    if (descriptor >= 0 || ++index == [arguments count]) return -1;
    const char *value = [[arguments objectAtIndex:index] UTF8String];
    if (!value || !*value) return -1;
    for (const char *p = value; *p; p++) if (*p < '0' || *p > '9') return -1;
    errno = 0; char *end;
    long parsed = strtol(value, &end, 10);
    if (errno || *end || parsed < 3 || parsed > INT_MAX) return -1;
    descriptor = (int)parsed;
    /* Mark immediately so even malformed duplicate arguments cannot leak it. */
    int flags = fcntl(descriptor, F_GETFD);
    if (flags < 0 || fcntl(descriptor, F_SETFD, flags | FD_CLOEXEC) < 0) return -1;
  }
  return descriptor;
}

@implementation WSNativeMenuConnection
- (void)watchWrite:(BOOL)watch
{
  if (_watchingWrite == watch || _descriptor < 0) return;
  _watchingWrite = watch;
  for (NSString *mode in _modes) {
    void *descriptor = (void *)(intptr_t)_descriptor;
    if (watch) [_runLoop addEvent:descriptor type:ET_WDESC watcher:self forMode:mode];
    else [_runLoop removeEvent:descriptor type:ET_WDESC forMode:mode all:NO];
  }
}
- (void)sendDesired
{
  if (_descriptor < 0 || _waiting || [_desired isEqual:_sent]) return;
  NSData *bytes = [NSJSONSerialization dataWithJSONObject:_desired options:0 error:NULL];
  if (!bytes || [bytes length] > 8192) { [self invalidate]; return; }
  ssize_t count = send(_descriptor, [bytes bytes], [bytes length], MSG_DONTWAIT | MSG_NOSIGNAL);
  if (count < 0 && (errno == EAGAIN || errno == EINTR)) { [self watchWrite:YES]; return; }
  if (count != (ssize_t)[bytes length]) { [self invalidate]; return; }
  [self watchWrite:NO];
  [_sent release]; _sent = [_desired copy]; _waiting = YES;
}
- (void)windowsChanged:(NSNotification *)notification
{
  if (![_shell isConnected]) { [self invalidate]; return; }
  NSDictionary *desired = [_shell activeApplicationMenu] ?: @{@"operation": @"clear"};
  if ([_rejected isEqual:desired]) desired = @{@"operation": @"clear"};
  else { [_rejected release]; _rejected = nil; }
  if ([_desired isEqual:desired]) return;
  [_desired release]; _desired = [desired copy];
  [self sendDesired];
}
- (void)shellClosed:(NSNotification *)notification { [self invalidate]; }
- (id)initWithShell:(WSShellConnection *)shell fileDescriptor:(int)descriptor
{
  if (!(self = [super init])) { if (descriptor >= 0) close(descriptor); return nil; }
  _descriptor = descriptor;
  int type = 0, flags = fcntl(descriptor, F_GETFD);
  socklen_t length = sizeof(type), addressLength = sizeof(struct sockaddr_un);
  struct sockaddr_un address;
  if (!shell || ![shell isConnected] || descriptor < 0 || flags < 0 ||
      fcntl(descriptor, F_SETFD, flags | FD_CLOEXEC) < 0 ||
      getsockopt(descriptor, SOL_SOCKET, SO_TYPE, &type, &length) < 0 || type != SOCK_SEQPACKET ||
      getpeername(descriptor, (struct sockaddr *)&address, &addressLength) < 0 || address.sun_family != AF_UNIX) {
    [self release]; return nil;
  }
  _shell = [shell retain]; _runLoop = [[NSRunLoop currentRunLoop] retain];
  _modes = [[NSArray alloc] initWithObjects:NSDefaultRunLoopMode, NSConnectionReplyMode,
    NSModalPanelRunLoopMode, NSEventTrackingRunLoopMode, nil];
  for (NSString *mode in _modes) [_runLoop addEvent:(void *)(intptr_t)_descriptor
    type:ET_RDESC watcher:self forMode:mode];
  NSNotificationCenter *center = [NSNotificationCenter defaultCenter];
  [center addObserver:self selector:@selector(windowsChanged:) name:WSShellWindowsDidChangeNotification object:shell];
  [center addObserver:self selector:@selector(shellClosed:) name:WSShellConnectionDidCloseNotification object:shell];
  [self windowsChanged:nil];
  return self;
}
- (void)receivedEvent:(void *)data type:(RunLoopEventType)type extra:(void *)extra forMode:(NSString *)mode
{
  if (_descriptor < 0) return;
  if (type == ET_WDESC) { [self sendDesired]; return; }
  char buffer[1024];
  ssize_t count = recv(_descriptor, buffer, sizeof(buffer), MSG_DONTWAIT | MSG_TRUNC);
  if (count < 0 && (errno == EAGAIN || errno == EINTR)) return;
  if (count <= 0 || count > sizeof(buffer) || !_waiting) { [self invalidate]; return; }
  NSDictionary *reply = [NSJSONSerialization JSONObjectWithData:
    [NSData dataWithBytes:buffer length:count] options:0 error:NULL];
  if (![reply isKindOfClass:[NSDictionary class]] || ![[reply objectForKey:@"accepted"] isKindOfClass:[NSNumber class]]) {
    [self invalidate]; return;
  }
  _waiting = NO;
  if (![[reply objectForKey:@"accepted"] boolValue]) {
    NSLog(@"[Workspace] Native menu address rejected: %@", _sent);
    if ([[_sent objectForKey:@"operation"] isEqual:@"bind"] && [_desired isEqual:_sent]) {
      [_rejected release]; _rejected = [_sent copy];
      [_desired release]; _desired = [@{@"operation": @"clear"} copy];
    }
  }
  [self sendDesired];
}
- (void)invalidate
{
  [[NSNotificationCenter defaultCenter] removeObserver:self];
  if (_descriptor < 0) return;
  for (NSString *mode in _modes) {
    void *descriptor = (void *)(intptr_t)_descriptor;
    [_runLoop removeEvent:descriptor type:ET_RDESC forMode:mode all:NO];
    if (_watchingWrite) [_runLoop removeEvent:descriptor type:ET_WDESC forMode:mode all:NO];
  }
  close(_descriptor); _descriptor = -1; _watchingWrite = NO;
}
- (void)dealloc
{
  [self invalidate];
  [_shell release]; [_runLoop release]; [_modes release]; [_desired release]; [_sent release]; [_rejected release];
  [super dealloc];
}
@end
