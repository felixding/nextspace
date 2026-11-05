/* Private native session/model contracts. GPL-2.0-or-later. */
#import "OSEScreen.h"
#import "OSEDisplay.h"
#import "OSESessionSettings.h"

BOOL OSEUsesWaylandDisplay(void);

@interface OSEDisplay (NativeModel)
- (id)initWithDescriptor:(NSDictionary *)descriptor screen:(OSEScreen *)screen duplicateIdentity:(BOOL)duplicate;
- (NSDictionary *)descriptor;
- (BOOL)applyGammaDescription:(NSDictionary *)description;
@end
@interface OSEScreen (NativeModel)
- (void)setDisplay:(OSEDisplay *)display resolution:(NSDictionary *)mode position:(NSPoint)position;
@end
