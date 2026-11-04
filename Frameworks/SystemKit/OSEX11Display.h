/* Legacy implementation details, never installed as SystemKit API.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import "OSEScreen.h"
#import "OSEDisplay.h"
#include <X11/extensions/Xrandr.h>

struct OSEX11ScreenState {
  Display *display;
  Window root;
  Pixmap pixmap;
  GC gc;
  XGCValues gcValues;
  id pixmapOwner;
  XRRScreenResources *resources;
};
struct OSEX11DisplayState {
  Display *display;
  XRRScreenResources *resources;
  RROutput output;
  Connection connection;
};
@interface OSEScreen (X11Private)
- (XRRScreenResources *)randrScreenResources;
- (void)randrUpdateScreenResources;
- (RRCrtc)randrFindFreeCRTC;
@end
@interface OSEDisplay (X11Private)
- (id)initWithOutputInfo:(RROutput)output screenResources:(XRRScreenResources *)resources
                 screen:(OSEScreen *)screen xDisplay:(Display *)display;
@end
