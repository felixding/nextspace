/* Native greeter IPC; the privileged manager owns PAM and the user session.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import <Foundation/Foundation.h>

@interface GreetdClient : NSObject
{
  int _socket;
}
- (id)initWithSocketPath:(NSString *)path error:(NSError **)error;
- (NSDictionary *)beginSessionForUser:(NSString *)user error:(NSError **)error;
/* A nil response acknowledges an informational PAM message. */
- (NSDictionary *)respond:(NSString *)response error:(NSError **)error;
- (NSDictionary *)cancelSession:(NSError **)error;
/* greetd0.10.3 joins cmd entries for /bin/sh; quote each literal argument here. */
- (NSDictionary *)startSessionWithArguments:(NSArray *)arguments
                              environment:(NSArray *)environment
                                    error:(NSError **)error;
@end
