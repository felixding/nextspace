/* Session display and input settings; no display-server handles cross this boundary.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import <Foundation/Foundation.h>

/* Property lists use physical mode pixels/millihertz and logical top-left
   positions. Scale is a numerator over 120; transform is Wayland's 0..7 enum.
   State contains schema, revision and heads. Every proposed head carries id,
   enabled, primary, width, height, refresh, scale, transform, x and y.

   Results contain status (tested=0, applied=1, confirmed=2, reverted=3,
   failed=4) and a diagnostic reason. Apply also returns an opaque token;
   only that token can confirm/cancel/poll its transaction. The compositor
   owns rollback even when Preferences or Workspace stops running. */
/* Encode the complete property list as a value. GNUstep distributed objects
   otherwise return dictionary/number proxies, including pointer-returning APIs
   such as objCType which cannot be used as local model values. */
@protocol OSESessionSettings;
/* Workspace supplies its process-lifetime provider locally; other applications
   use the session-scoped distributed service. This avoids self-RPC at startup. */
void OSERegisterSessionSettings(id<OSESessionSettings> service);
/* Main-thread settings access, reconnecting after Workspace replacement. */
NSDictionary *OSERequestSessionSettings(NSDictionary *request);

@protocol OSESessionSettings <NSObject>
- (bycopy NSData *)nextspaceSettingsRequest:(bycopy NSData *)request;
@end

static inline NSData *OSESessionSettingsEncode(NSDictionary *value)
{
  return [NSPropertyListSerialization dataWithPropertyList:value format:NSPropertyListBinaryFormat_v1_0
    options:0 error:NULL];
}
static inline NSDictionary *OSESessionSettingsDecode(NSData *data)
{
  if (![data isKindOfClass:[NSData class]] || [data length] > 4 * 1024 * 1024) return nil;
  id value = [NSPropertyListSerialization propertyListWithData:data options:NSPropertyListImmutable
    format:NULL error:NULL];
  return [value isKindOfClass:[NSDictionary class]] ? value : nil;
}
static inline NSDictionary *OSESessionSettingsRequest(id<OSESessionSettings> service, NSDictionary *request)
{
  NSMutableDictionary *wire = [[request mutableCopy] autorelease];
  [wire setObject:[NSNumber numberWithInt:1] forKey:@"schema"];
  @try {
    return OSESessionSettingsDecode([service nextspaceSettingsRequest:OSESessionSettingsEncode(wire)]);
  } @catch (NSException *exception) { return nil; }
}
