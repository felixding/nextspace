/* Keep display settings RPC independent of the selected window manager.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import "Controller.h"
#import "WindowManager.h"
#import <SystemKit/OSESessionSettings.h>

static id<OSESessionSettings> sessionSettings(void)
{
  id manager = WSCurrentWindowManager();
  return [manager conformsToProtocol:@protocol(OSESessionSettings)] ? manager : nil;
}

@implementation Controller (SessionSettings)
- (bycopy NSData *)nextspaceSettingsRequest:(bycopy NSData *)request
{ return [sessionSettings() nextspaceSettingsRequest:request]; }
@end
