/* -*- mode: objc -*- */
//
// Project: Workspace
//
// Copyright (C) 2015 Sergii Stoian
//
// This application is free software; you can redistribute it and/or
// modify it under the terms of the GNU General Public
// License as published by the Free Software Foundation; either
// version 2 of the License, or (at your option) any later version.
//
// This application is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
// Library General Public License for more details.
//
// You should have received a copy of the GNU General Public
// License along with this library; if not, write to the Free
// Software Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111 USA.
//

/* X11 application metadata bridge. SPDX-License-Identifier: GPL-2.0-or-later */
#import "ProcessManager.h"
#import "ProcessManager+WindowManager.h"
#import "Processes.h"
#import "Controller.h"
#import "Workspace+WM.h"
#import "WMNotificationCenter.h"
#import "CoreFoundationBridge.h"
#import <SystemKit/OSEFileManager.h>
#include <signal.h>
#include <errno.h>

@implementation ProcessManager (WindowManager)

- (NSDictionary *)_applicationInfoForWindow:(WWindow *)wwin
{
  NSMutableDictionary *appInfo = [NSMutableDictionary dictionary];
  NSString *appName = nil;
  NSString *appPath = nil;
  int app_pid;
  char *app_command = NULL;

  // Gather NSApplicationName and NSApplicationPath
  if (!strcmp(wwin->wm_class, "GNUstep")) {
    [appInfo setObject:@"NO" forKey:@"IsXWindowApplication"];
    appName = [NSString stringWithCString:wwin->wm_instance];
    appPath = [[NSWorkspace sharedWorkspace] fullPathForApplication:appName];
  } else {
    [appInfo setObject:@"YES" forKey:@"IsXWindowApplication"];
    appName = [NSString stringWithCString:wwin->wm_class];
    app_command = wGetCommandForWindow(wwin->client_win);
    if (app_command) {
      appPath = [[OSEFileManager defaultManager]
          absolutePathForCommand:[NSString stringWithCString:app_command]];
    }
  }
  // NSApplicationName = NSString*
  [appInfo setObject:appName forKey:@"NSApplicationName"];
  // NSApplicationPath = NSString*
  if (appPath) {
    [appInfo setObject:appPath forKey:@"NSApplicationPath"];
  } else if (app_command) {
    [appInfo setObject:[NSString stringWithCString:app_command] forKey:@"NSApplicationPath"];
  } else {
    [appInfo setObject:@"--" forKey:@"NSApplicationPath"];
  }

  // NSApplicationProcessIdentifier = NSNumber*
  if ((app_pid = wNETWMGetPidForWindow(wwin->client_win)) > 0) {
    [appInfo setObject:[NSNumber numberWithInt:app_pid] forKey:@"NSApplicationProcessIdentifier"];
  } else if ((app_pid = wNETWMGetPidForWindow(wwin->main_window)) > 0) {
    [appInfo setObject:[NSNumber numberWithInt:app_pid] forKey:@"NSApplicationProcessIdentifier"];
  } else {
    [appInfo setObject:[NSNumber numberWithInt:-1] forKey:@"NSApplicationProcessIdentifier"];
  }

  return (NSDictionary *)appInfo;
}

- (NSDictionary *)_applicationInfoForApp:(WApplication *)wapp window:(WWindow *)wwin
{
  NSMutableDictionary *appInfo = [[self _applicationInfoForWindow:wwin] mutableCopy];
  NSImage *iconImage = nil;

  // Get icon image from windowmaker app structure(WApplication)
  // NSApplicationIcon=NSImage*
  NSDebugLLog(@"Processes", @"%@ icon filename: %s", appInfo[@"NSApplicationName"],
              wapp->app_icon->icon->file);
  if (wapp->app_icon->icon->file_image) {
    iconImage = WSImageForRasterImage(wapp->app_icon->icon->file_image);
  } else if (wapp->app_icon->icon->file) {
    iconImage = [[NSImage alloc]
        initByReferencingFile:[NSString stringWithCString:wapp->app_icon->icon->file]];
  }
  if (iconImage) {
    [appInfo setObject:WSImageForRasterImage(wapp->app_icon->icon->file_image)
                forKey:@"NSApplicationIcon"];
  }

  return (NSDictionary *)[appInfo autorelease];
}

// WMDidCreateApplicationNotification
- (void)windowManagerDidCreateApplication:(NSNotification *)notif
{
  WApplication *wapp = (WApplication *)[(CFObject *)[notif object] object];
  NSNotification *localNotif = nil;
  NSDictionary *appInfo = nil;
  WAppIcon *appIcon;
  WWindow *wwin;

  if ([self workspaceIsQuitting] || !wapp) {
    return;
  }

  appIcon = wLaunchingAppIconForInstance(wapp->main_wwin->screen, wapp->main_wwin->wm_instance,
                                         wapp->main_wwin->wm_class);
  if (appIcon) {
    wLaunchingAppIconFinish(wapp->main_wwin->screen, appIcon);
    appIcon->main_window = wapp->main_window;
  }

  // GNUstep application will register itself in ProcessManager with AppKit notification.
  if (!strcmp(wapp->main_wwin->wm_class, "GNUstep")) {
    return;
  }

  if (CFArrayGetCount(wapp->windows) <= 0) {
    wwin = wapp->main_wwin;
  } else {
    wwin = (WWindow *)CFArrayGetValueAtIndex(wapp->windows, 0);
  }
  appInfo = [self _applicationInfoForApp:wapp window:wwin];
  NSDebugLLog(@"Processes", @"ProcessManager-windowManagerDidCreateApplication: %@", appInfo);

  localNotif = [NSNotification notificationWithName:NSWorkspaceDidLaunchApplicationNotification
                                             object:appInfo
                                           userInfo:appInfo];
  [self applicationDidLaunch:localNotif];
}

// WMDidDestroyApplicationNotification
// Application could be terminate in 2 ways:
// 1. normal - AppKit notfication mechanism works
// 2. crash - no AppKit involved so we should use this code to inform ProcessManager
// [ProcessManager applicationDidTerminate:] should expect 2 calls for option #1.
- (void)windowManagerDidDestroyApplication:(NSNotification *)notif
{
  WApplication *wapp = (WApplication *)[(CFObject *)[notif object] object];
  NSNotification *localNotif = nil;
  NSDictionary *appInfo = nil;

  if ([self workspaceIsQuitting] || !wapp) {
    return;
  }

  appInfo = [self _applicationInfoForApp:wapp window:wapp->main_wwin];
  localNotif = [NSNotification notificationWithName:NSWorkspaceDidTerminateApplicationNotification
                                             object:@"WindowManager"
                                           userInfo:appInfo];
  [self applicationDidTerminate:localNotif];
}

- (void)windowManagerDidActivateApplication:(NSNotification *)notif
{
  WApplication *wapp = (WApplication *)[(CFObject *)[notif object] object];
  WWindow *wwin = NULL;

  if (wapp == NULL) {
    return;
  }

  if (CFArrayGetCount(wapp->windows) <= 0) {
    wwin = wapp->main_wwin;
  } else {
    wwin = wapp->last_focused ? wapp->last_focused : (WWindow *)CFArrayGetValueAtIndex(wapp->windows, 0);
  }

  [self setActiveApplicationInfo:[self _applicationInfoForWindow:wwin]];

  WMLogWarning("Window Manager Did Activate Application: %@", convertNStoCFDictionary([self activeApplication]));
}

// WMDidManageWindowNotification
- (void)windowManagerDidManageWindow:(NSNotification *)notif
{
  WWindow *wwin = (WWindow *)[(CFObject *)[notif object] object];
  NSDictionary *windowAppInfo, *appInfo;
  NSMutableOrderedSet *pidList = nil;

  if ([self workspaceIsQuitting] || !wwin || !strcmp(wwin->wm_class, "GNUstep")) {
    return;
  }

  windowAppInfo = [self _applicationInfoForWindow:wwin];
  if (!windowAppInfo) {
    return;
  }

  if ((appInfo = [self _applicationWithName:windowAppInfo[@"NSApplicationName"]]) != nil) {
    pidList = appInfo[@"NSApplicationProcessIdentifier"];
  }
  if (!pidList) {
    return;
  }

  [pidList addObject:windowAppInfo[@"NSApplicationProcessIdentifier"]];
  if ([[NSApp delegate] processesPanel]) {
    [[[NSApp delegate] processesPanel] updateAppList];
  }
}

// WMDidUnmanageWindowNotification
// 1. Determine application which owns subprocess
// 2. Check if processes still exists from application PID list with
//    kill (pid, 0).
- (void)windowManagerDidUnmanageWindow:(NSNotification *)notif
{
  WWindow *wwin = (WWindow *)[(CFObject *)[notif object] object];
  NSDictionary *wwinAppInfo, *appInfo;
  NSString *appName;
  NSMutableOrderedSet *appPIDList;
  NSArray *_appPIDList;
  int pid;

  if ([self workspaceIsQuitting] || !wwin || !strcmp(wwin->wm_class, "GNUstep")) {
    return;
  }

  wwinAppInfo = [self _applicationInfoForWindow:wwin];
  appName = [wwinAppInfo objectForKey:@"NSApplicationName"];
  if (!(appInfo = [self _applicationWithName:appName])) {
    return;
  }
  appPIDList = [appInfo objectForKey:@"NSApplicationProcessIdentifier"];
  _appPIDList = [appPIDList array];
  for (NSString *pidString in _appPIDList) {
    pid = [pidString integerValue];
    if ((kill(pid, 0) == -1) && (errno == ESRCH)) {  // process doesn't exist
      [appPIDList removeObject:pidString];
    }
  }

  if ([[NSApp delegate] processesPanel]) {
    [[[NSApp delegate] processesPanel] updateAppList];
  }
}

@end
