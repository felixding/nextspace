/* Foundation-only application event boundary. SPDX-License-Identifier: GPL-2.0-or-later */
#import "ProcessManager.h"

@interface ProcessManager (WindowManagerEvents)
- (BOOL)workspaceIsQuitting;
- (void)setActiveApplicationInfo:(NSDictionary *)info;
- (void)applicationDidLaunch:(NSNotification *)notification;
- (void)applicationDidTerminate:(NSNotification *)notification;
- (void)windowManagerDidCreateApplication:(NSNotification *)notification;
- (void)windowManagerDidDestroyApplication:(NSNotification *)notification;
- (void)windowManagerDidActivateApplication:(NSNotification *)notification;
- (void)windowManagerDidManageWindow:(NSNotification *)notification;
- (void)windowManagerDidUnmanageWindow:(NSNotification *)notification;
@end
