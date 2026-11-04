/* Legacy Dock integration. SPDX-License-Identifier: GPL-2.0-or-later */
#import "RecyclerIcon.h"
#import "Workspace+WM.h"

@interface RecyclerIcon (X11Integration)
+ (WAppIcon *)createAppIconForDock:(WDock *)dock;
+ (WAppIcon *)recyclerAppIconForDock:(WDock *)dock;
+ (void)updatePositionInDock:(WDock *)dock;
- (id)initWithWindowRef:(void *)window recycler:(Recycler *)recycler;
@end
