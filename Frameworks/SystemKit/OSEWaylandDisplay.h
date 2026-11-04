/* Private native model. It depends on Foundation contracts, not Wayland/Xlib.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import "OSEScreen.h"
#import "OSEDisplay.h"
#import "OSESessionSettings.h"

BOOL OSEUsesWaylandDisplay(void);

@interface OSEWaylandDisplay : OSEDisplay
{
  NSDictionary *_descriptor;
  NSData *_identity;
  NSRect _logicalFrame, _hiddenLogicalFrame;
}
- (id)initWithDescriptor:(NSDictionary *)descriptor screen:(OSEScreen *)screen duplicateIdentity:(BOOL)duplicate;
- (NSDictionary *)descriptor;
- (BOOL)applyGammaDescription:(NSDictionary *)description;
@end

@interface OSEWaylandScreen : OSEScreen
{
  NSDictionary *_state;
  NSString *_transaction;
  BOOL _refreshing;
}
- (void)setDisplay:(OSEDisplay *)display resolution:(NSDictionary *)mode position:(NSPoint)position;
@end
