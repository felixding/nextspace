/* Unprivileged, asynchronous PAM conversation for the existing Login UI.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import <Foundation/Foundation.h>

@protocol GreetdSessionDelegate
/* Called on the main thread. Set response for visible/secret messages, or
   cancelled to end the conversation. Info/error messages need no response. */
- (void)loginServicePrompt:(NSMutableDictionary *)message;
- (void)loginServiceWillStart:(NSString *)user;
- (void)loginServiceFinished:(NSDictionary *)result;
@end

@interface GreetdSession : NSObject
{
  NSString *_path;
  id<GreetdSessionDelegate> _delegate;
  BOOL _active;
}
- (id)initWithSocketPath:(NSString *)path delegate:(id<GreetdSessionDelegate>)delegate;
- (BOOL)isActive;
- (void)authenticateUser:(NSString *)user password:(NSString *)password arguments:(NSArray *)arguments;
@end
