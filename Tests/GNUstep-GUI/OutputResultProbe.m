/* Coalesced display replies must preserve request and lease ordering. MIT. */
#import "WSShellConnection.h"

@interface WSShellConnection (OutputResultFixture)
- (void)recordOutputResult:(NSDictionary *)result;
- (NSDictionary *)waitForOutputResultAfter:(NSUInteger)sequence;
- (NSDictionary *)nextspaceApplyDisplayLayout:(NSArray *)layout revision:(NSUInteger)revision timeout:(NSUInteger)milliseconds;
- (NSDictionary *)nextspaceDisplayLayoutStatus:(NSString *)token;
- (NSDictionary *)nextspaceConfirmDisplayLayout:(NSString *)token;
@end

@interface OutputResultFixture : WSShellConnection
@end
@implementation OutputResultFixture
- (BOOL)waitForCounter:(NSUInteger *)counter after:(NSUInteger)sequence
{
  /* Model one Wayland dispatch delivering acceptance followed by expiry. */
  [self recordOutputResult:[NSDictionary dictionaryWithObject:[NSNumber numberWithInt:1] forKey:@"status"]];
  [self recordOutputResult:[NSDictionary dictionaryWithObjectsAndKeys:
    [NSNumber numberWithInt:3], @"status", @"confirmation timed out", @"reason", nil]];
  return YES;
}
- (NSDictionary *)applyOutputLayout:(NSArray *)layout revision:(NSUInteger)revision timeout:(NSUInteger)milliseconds
{ return [self waitForOutputResultAfter:0]; }
@end

int main(void)
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  OutputResultFixture *connection = [OutputResultFixture new];
  NSDictionary *applied = [connection nextspaceApplyDisplayLayout:[NSArray array] revision:0 timeout:1000];
  NSCAssert([[applied objectForKey:@"status"] intValue] == 1, @"Lost the initial apply reply");
  NSString *token = [applied objectForKey:@"token"];
  NSCAssert([token length] > 0, @"Accepted request has no lease token");
  NSCAssert([[[connection nextspaceDisplayLayoutStatus:token] objectForKey:@"status"] intValue] == 3,
    @"Expiry was lost while creating the lease");
  NSCAssert([[[connection nextspaceConfirmDisplayLayout:token] objectForKey:@"status"] intValue] == 4,
    @"Expired lease was confirmed");
  NSCAssert([[[connection outputResult] objectForKey:@"status"] intValue] == 3,
    @"Latest display state is stale");
  puts("Coalesced display apply/expiry replies and lease state: PASS");
  [connection release]; [pool drain];
  return 0;
}
