/* The manager retains PAM privileges and launches the authenticated session.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import "GreetdSession.h"
#import "GreetdClient.h"

@implementation GreetdSession
- (id)initWithSocketPath:(NSString *)path delegate:(id<GreetdSessionDelegate>)delegate
{
  if ((self = [super init])) { _path = [path copy]; _delegate = delegate; }
  return self;
}
- (void)dealloc { [_path release]; [super dealloc]; }
- (BOOL)isActive { return _active; }
- (void)finished:(NSDictionary *)result
{
  _active = NO;
  [_delegate loginServiceFinished:result];
}
- (void)authenticateUser:(NSString *)user password:(NSString *)password arguments:(NSArray *)arguments
{
  if (_active) return;
  _active = YES;
  NSMutableDictionary *request = [NSMutableDictionary dictionaryWithObjectsAndKeys:
    [[user copy] autorelease], @"user", [[password copy] autorelease], @"password",
    [[arguments copy] autorelease], @"arguments", nil];
  [NSThread detachNewThreadSelector:@selector(authenticate:) toTarget:self withObject:request];
}
- (void)authenticate:(NSMutableDictionary *)request
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  NSError *error = nil;
  GreetdClient *client = nil;
  NSString *password = [[request objectForKey:@"password"] copy];
  [request removeObjectForKey:@"password"];
  BOOL success = NO, cancelled = NO, authenticationError = NO;
  NSString *message = nil;
  @try {
    client = [[GreetdClient alloc] initWithSocketPath:_path error:&error];
    NSDictionary *reply = nil;
    if (client) {
      /* Reset a conversation left behind by a previous failed connection.
         A dead PAM worker can report an error after clearing that state. */
      [client cancelSession:&error];
      if (!error) reply = [client beginSessionForUser:[request objectForKey:@"user"] error:&error];
    }
    while ([[reply objectForKey:@"type"] isEqual:@"auth_message"]) {
      NSString *kind = [reply objectForKey:@"auth_message_type"];
      if ([kind isEqual:@"secret"] && password) {
        reply = [client respond:password error:&error];
        [password release]; password = nil;
      } else {
        NSMutableDictionary *prompt = [NSMutableDictionary dictionaryWithDictionary:reply];
        [(NSObject *)_delegate performSelectorOnMainThread:@selector(loginServicePrompt:)
          withObject:prompt waitUntilDone:YES];
        if ([[prompt objectForKey:@"cancelled"] boolValue]) { cancelled = YES; break; }
        reply = [client respond:[prompt objectForKey:@"response"] error:&error];
      }
    }
    if (!cancelled && [[reply objectForKey:@"type"] isEqual:@"success"]) {
      [(NSObject *)_delegate performSelectorOnMainThread:@selector(loginServiceWillStart:)
        withObject:[request objectForKey:@"user"] waitUntilDone:YES];
      reply = [client startSessionWithArguments:[request objectForKey:@"arguments"]
        environment:[NSArray arrayWithObjects:@"XDG_SESSION_TYPE=wayland",
          @"XDG_SESSION_DESKTOP=NextSpace", nil] error:&error];
      success = [[reply objectForKey:@"type"] isEqual:@"success"];
    }
    if (!success) {
      authenticationError = [[reply objectForKey:@"error_type"] isEqual:@"auth_error"];
      message = error ? [error localizedDescription] : [reply objectForKey:@"description"];
      [client cancelSession:NULL];
    }
  } @catch (NSException *exception) {
    message = @"The login service could not complete the request.";
    [client cancelSession:NULL];
  }
  NSMutableDictionary *result = [NSMutableDictionary dictionaryWithObjectsAndKeys:
    [NSNumber numberWithBool:success], @"success", [NSNumber numberWithBool:cancelled], @"cancelled",
    [NSNumber numberWithBool:authenticationError], @"authentication_error", nil];
  if (message) [result setObject:message forKey:@"message"];
  [password release]; [client release];
  [self performSelectorOnMainThread:@selector(finished:) withObject:result waitUntilDone:YES];
  [pool drain];
}
@end
