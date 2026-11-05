/* Native display model and session display service adapter.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import "OSEWaylandDisplay.h"
#import <AppKit/AppKit.h>
#import <GNUstepGUI/GSDisplayServer.h>

extern NSString *GSDisplayBackendName(void) __attribute__((weak));
extern NSString *GSSessionServiceName(NSString *) __attribute__((weak));
static id<OSESessionSettings> localSessionSettings, remoteSessionSettings;
static NSConnection *settingsConnection;

void OSERegisterSessionSettings(id<OSESessionSettings> service) { localSessionSettings = service; }
NSDictionary *OSERequestSessionSettings(NSDictionary *request)
{
  if (localSessionSettings) return OSESessionSettingsRequest(localSessionSettings, request);
  @try {
    if (!remoteSessionSettings) {
      NSString *name = GSSessionServiceName ? GSSessionServiceName(@"Workspace") : @"Workspace";
      settingsConnection = [[NSConnection connectionWithRegisteredName:name host:@""] retain];
      [settingsConnection setRequestTimeout:5]; [settingsConnection setReplyTimeout:5];
      remoteSessionSettings = [[(id)[settingsConnection rootProxy] delegate] retain];
    }
    NSDictionary *result = OSESessionSettingsRequest(remoteSessionSettings, request);
    if (result) return result;
  } @catch (NSException *exception) {}
  [remoteSessionSettings release]; remoteSessionSettings = nil;
  [settingsConnection release]; settingsConnection = nil;
  return nil;
}
BOOL OSEUsesWaylandDisplay(void)
{
  NSString *name = GSDisplayBackendName ? GSDisplayBackendName() :
    [[NSUserDefaults standardUserDefaults] stringForKey:@"GSBackend"];
  if (![name length]) name = [[[NSProcessInfo processInfo] environment] objectForKey:@"NEXTSPACE_GS_BACKEND"];
  return [name length] && [[name lowercaseString] rangeOfString:@"wayland"].location != NSNotFound;
}
