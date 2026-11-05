/* greetd's length-prefixed JSON protocol; no PAM state lives in the GUI.
   https://manpages.debian.org/trixie/greetd/greetd-ipc.7.en.html
   SPDX-License-Identifier: GPL-2.0-or-later */
#define _GNU_SOURCE
#import "GreetdClient.h"
#include <errno.h>
#include <poll.h>
#include <stdint.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

#ifndef MSG_NOSIGNAL
#define MSG_NOSIGNAL 0
#endif

static const NSUInteger messageLimit = 64 * 1024;
static const int requestTimeout = 30000;

static int64_t nowMilliseconds(void)
{
  struct timespec now;
  clock_gettime(CLOCK_MONOTONIC, &now);
  return (int64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

static void serviceError(NSError **error, int code, NSString *message)
{
  if (error) *error = [NSError errorWithDomain:@"NextSpaceLoginService" code:code
    userInfo:[NSDictionary dictionaryWithObject:message forKey:NSLocalizedDescriptionKey]];
}

static BOOL waitForSocket(int fd, short events, int64_t deadline)
{
  for (;;) {
    int64_t remaining = deadline - nowMilliseconds();
    if (remaining <= 0) { errno = ETIMEDOUT; return NO; }
    struct pollfd descriptor = {fd, events, 0};
    int result = poll(&descriptor, 1, (int)remaining);
    if (result > 0) return YES;
    if (result == 0) { errno = ETIMEDOUT; return NO; }
    if (errno != EINTR) return NO;
  }
}

static BOOL transfer(int fd, void *data, size_t length, BOOL writing, int64_t deadline)
{
  unsigned char *bytes = data;
  while (length) {
    if (!waitForSocket(fd, writing ? POLLOUT : POLLIN, deadline)) return NO;
    ssize_t count = writing ? send(fd, bytes, length, MSG_NOSIGNAL) : recv(fd, bytes, length, 0);
    if (count > 0) { bytes += count; length -= count; }
    else if (count == 0) { errno = ECONNRESET; return NO; }
    else if (errno != EINTR && errno != EAGAIN && errno != EWOULDBLOCK) return NO;
  }
  return YES;
}

static BOOL validString(id value)
{
  if (![value isKindOfClass:[NSString class]]) return NO;
  NSData *data = [value dataUsingEncoding:NSUTF8StringEncoding];
  return data && (![data length] || !memchr([data bytes], 0, [data length]));
}

static BOOL validReply(id reply)
{
  if (![reply isKindOfClass:[NSDictionary class]]) return NO;
  NSString *type = [reply objectForKey:@"type"];
  if (![type isKindOfClass:[NSString class]]) return NO;
  if ([type isEqual:@"success"]) return YES;
  if ([type isEqual:@"error"] && [[reply objectForKey:@"error_type"] isKindOfClass:[NSString class]])
    return [[NSArray arrayWithObjects:@"auth_error", @"error", nil] containsObject:[reply objectForKey:@"error_type"]] &&
      validString([reply objectForKey:@"description"]);
  if ([type isEqual:@"auth_message"] && [[reply objectForKey:@"auth_message_type"] isKindOfClass:[NSString class]])
    return [[NSArray arrayWithObjects:@"visible", @"secret", @"info", @"error", nil]
      containsObject:[reply objectForKey:@"auth_message_type"]] && validString([reply objectForKey:@"auth_message"]);
  return NO;
}

@implementation GreetdClient
- (id)initWithSocketPath:(NSString *)path error:(NSError **)error
{
  if (!(self = [super init])) return nil;
  _socket = -1;
#ifdef __linux__
  struct sockaddr_un address;
  memset(&address, 0, sizeof(address));
  address.sun_family = AF_UNIX;
  NSData *data = validString(path) ? [path dataUsingEncoding:NSUTF8StringEncoding] : nil;
  if (!data || ![path isAbsolutePath] || [data length] >= sizeof(address.sun_path)) {
    serviceError(error, EINVAL, @"The login service address is invalid.");
    [self release]; return nil;
  }
  memcpy(address.sun_path, [data bytes], [data length]);
  _socket = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
  BOOL connected = NO;
  int64_t deadline = nowMilliseconds() + requestTimeout;
  while (_socket >= 0 && nowMilliseconds() < deadline) {
    if (connect(_socket, (struct sockaddr *)&address, sizeof(address)) == 0 || errno == EISCONN) {
      connected = YES; break;
    }
    if (errno == EINTR) continue;
    if (errno == EAGAIN) { poll(NULL, 0, 10); continue; }
    if (errno != EINPROGRESS || !waitForSocket(_socket, POLLOUT, deadline)) break;
    int result = 0;
    socklen_t length = sizeof(result);
    if (getsockopt(_socket, SOL_SOCKET, SO_ERROR, &result, &length) == 0 && result == 0) connected = YES;
    else if (result) errno = result;
    break;
  }
  if (!connected) {
    serviceError(error, errno, @"Unable to connect to the login service.");
    [self release]; return nil;
  }
  struct ucred peer;
  socklen_t length = sizeof(peer);
  if (getsockopt(_socket, SOL_SOCKET, SO_PEERCRED, &peer, &length) < 0 || length != sizeof(peer) || peer.uid != 0 || peer.pid <= 0) {
    serviceError(error, EACCES, @"The login service identity could not be verified.");
    [self release]; return nil;
  }
  return self;
#else
  serviceError(error, ENOTSUP, @"Native login authentication is unavailable on this platform.");
  [self release]; return nil;
#endif
}

- (void)dealloc
{
  if (_socket >= 0) close(_socket);
  [super dealloc];
}

- (NSDictionary *)exchange:(NSDictionary *)request error:(NSError **)error
{
  if (_socket < 0) { serviceError(error, ENOTCONN, @"The login service is disconnected."); return nil; }
  NSData *payload = [NSJSONSerialization dataWithJSONObject:request options:0 error:NULL];
  if (!payload || [payload length] > messageLimit) {
    serviceError(error, EMSGSIZE, @"The login request is too large."); return nil;
  }
  uint32_t length = (uint32_t)[payload length];
  int64_t deadline = nowMilliseconds() + requestTimeout;
  if (!transfer(_socket, &length, sizeof(length), YES, deadline) ||
      !transfer(_socket, (void *)[payload bytes], length, YES, deadline) ||
      !transfer(_socket, &length, sizeof(length), NO, deadline)) goto disconnected;
  if (!length || length > messageLimit) goto invalid;
  NSMutableData *data = [NSMutableData dataWithLength:length];
  if (!transfer(_socket, [data mutableBytes], length, NO, deadline)) goto disconnected;
  id reply = [NSJSONSerialization JSONObjectWithData:data options:0 error:NULL];
  if (!validReply(reply)) goto invalid;
  return reply;
invalid:
  serviceError(error, EPROTO, @"The login service returned an invalid response.");
  close(_socket); _socket = -1; return nil;
disconnected:
  serviceError(error, errno, @"The login service did not complete the request.");
  close(_socket); _socket = -1; return nil;
}

- (NSDictionary *)beginSessionForUser:(NSString *)user error:(NSError **)error
{
  if (!validString(user) || ![user length]) {
    serviceError(error, EINVAL, @"Enter a user name."); return nil;
  }
  return [self exchange:[NSDictionary dictionaryWithObjectsAndKeys:@"create_session", @"type", user, @"username", nil] error:error];
}
- (NSDictionary *)respond:(NSString *)response error:(NSError **)error
{
  if (response && !validString(response)) { serviceError(error, EINVAL, @"The login response is invalid."); return nil; }
  NSMutableDictionary *request = [NSMutableDictionary dictionaryWithObject:@"post_auth_message_response" forKey:@"type"];
  if (response) [request setObject:response forKey:@"response"];
  return [self exchange:request error:error];
}
- (NSDictionary *)cancelSession:(NSError **)error
{ return [self exchange:[NSDictionary dictionaryWithObject:@"cancel_session" forKey:@"type"] error:error]; }
- (NSDictionary *)startSessionWithArguments:(NSArray *)arguments environment:(NSArray *)environment error:(NSError **)error
{
  if (![arguments isKindOfClass:[NSArray class]] || ![arguments count] || ![environment isKindOfClass:[NSArray class]]) goto invalid;
  NSMutableArray *quoted = [NSMutableArray array];
  for (id value in arguments) {
    if (!validString(value)) goto invalid;
    [quoted addObject:[NSString stringWithFormat:@"'%@'", [value stringByReplacingOccurrencesOfString:@"'" withString:@"'\\''"]]];
  }
  if (![[arguments objectAtIndex:0] length]) goto invalid;
  for (id value in environment) {
    if (!validString(value)) goto invalid;
    NSRange separator = [value rangeOfString:@"="];
    if (separator.location == NSNotFound || !separator.location) goto invalid;
  }
  return [self exchange:[NSDictionary dictionaryWithObjectsAndKeys:@"start_session", @"type", quoted, @"cmd", environment, @"env", nil] error:error];
invalid:
  serviceError(error, EINVAL, @"The session command is invalid."); return nil;
}
@end
