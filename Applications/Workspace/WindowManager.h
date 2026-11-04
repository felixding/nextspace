/* Workspace window/application policy boundary. SPDX-License-Identifier: GPL-2.0-or-later */
#import <Foundation/Foundation.h>
#include <sys/types.h>

@class NSWindow, NSImage, Recycler, ProcessManager;

@protocol WSWindowManager <NSObject>
- (NSString *)serverVersion;
- (NSString *)stateForWindow:(NSWindow *)window;
- (void)setWindow:(NSWindow *)window shaded:(BOOL)shaded;
- (NSArray *)undockedApplications;
- (BOOL)isApplicationRunning:(NSString *)name;
- (pid_t)executeCommand:(NSString *)command;
- (void)unhideWorkspace;
- (void)hideOtherApplications;
- (void)beginApplicationLaunch:(NSDictionary *)info fromPoint:(NSPoint)point;
- (void)endApplicationLaunch:(NSString *)command;
- (void)observeApplicationEventsFor:(ProcessManager *)manager;
/* Quiesce callbacks before controllers destroy their models. */
- (void)prepareForTermination;
- (BOOL)terminateApplication:(NSDictionary *)info;
- (NSString *)keyboardLayoutBadgeForNotification:(NSNotification *)notification;
/* Existing Dock preference tags, independent of AppKit's backend level values. */
- (NSInteger)dockLevel;
- (NSArray *)supportedDockLevels;
- (void)setDockLevel:(NSInteger)level;
- (NSInteger)dockSlotCount;
- (NSDictionary *)dockApplicationAtSlot:(NSInteger)slot;
- (NSImage *)dockImageAtSlot:(NSInteger)slot;
- (void)setDockValue:(NSString *)value forKey:(NSString *)key atSlot:(NSInteger)slot;
- (void)setDockImageAtPath:(NSString *)path atSlot:(NSInteger)slot;
- (NSString *)dockChangeNotification;
- (BOOL)isDockVisible;
- (void)setDockVisible:(BOOL)visible;
- (BOOL)isDockCollapsed;
- (void)setDockCollapsed:(BOOL)collapsed;
- (BOOL)isIconYardVisible;
- (void)setIconYardVisible:(BOOL)visible;
- (void)updateUsableArea;
- (NSInteger)desktopIndex;
- (NSDictionary *)desktopSettings:(NSDictionary *)changes;
- (BOOL)shouldRestoreWorkspaceWindows;
- (NSWindow *)newRecyclerIconForRecycler:(Recycler *)recycler;
- (void)finishStartup;
- (void)setFocusEventsEnabled:(BOOL)enabled;
- (void)updateScreenParameters;
- (NSNotificationCenter *)notificationCenter;
- (NSString *)desktopChangeNotification;
- (NSString *)keyboardLayoutChangeNotification;
@end

id<WSWindowManager> WSCurrentWindowManager(void);
NSArray *WSDesktopShortcutNames(void);
NSDictionary *WSDefaultDesktopShortcuts(void);
