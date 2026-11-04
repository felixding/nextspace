/* -*- mode: objc -*- */
//
// Project: Workspace
//
// Copyright (C) 2014-2019 Sergii Stoian
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

#import <AppKit/AppKit.h>
#import "Application.h"
#import "Session.h"
#ifdef NEXTSPACE_BUILD_WAYLAND
#import "WSShellConnection.h"
#endif
#include <unistd.h>
#include <stdlib.h>
#include <string.h>

CFRunLoopRef wm_runloop = NULL;
dispatch_queue_t workspace_q;
WorkspaceExitCode ws_quit_code = WSLogoutOnQuit;
static BOOL usesX11Session = YES;
int ws_shell_descriptor = -1;

void WSUncaughtExceptionHandler(NSException *e)
{
  NSLog(@"*** EXCEPTION *** NAME: %@ REASON: %@", [e name], [e reason]);
}

int WSApplicationMain(int argc, const char **argv)
{
  NSDictionary *infoDict;
  NSString *mainModelFile;

  CREATE_AUTORELEASE_POOL(pool);

  infoDict = [[NSBundle mainBundle] infoDictionary];

  [WSApplication sharedApplication];

  mainModelFile = [infoDict objectForKey:@"NSMainNibFile"];
  if (mainModelFile != nil && [mainModelFile isEqual:@""] == NO) {
    if ([NSBundle loadNibNamed:mainModelFile owner:NSApp] == NO) {
      NSLog(NSLocalizedString(@"Cannot load the main model file '%@'", nil), mainModelFile);
    }
  }

  RECREATE_AUTORELEASE_POOL(pool);

#ifndef NEXTSPACE_BUILD_WAYLAND
  if (usesX11Session) WSPrepareX11Application();
#endif

  [NSApp run];

  [pool drain];

  return 0;
}

int main(int argc, const char **argv)
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  NSString *backend = WSSessionBackendName();
  usesX11Session = !([backend length] &&
    [backend rangeOfString:@"wayland" options:NSCaseInsensitiveSearch].location != NSNotFound);
  const char *sessionType = getenv("XDG_SESSION_TYPE");
  if (usesX11Session && sessionType && strcmp(sessionType, "wayland") == 0) {
    fprintf(stderr, "[Workspace] The embedded X11 window manager cannot run inside a Wayland session.\n");
    [pool drain]; return 1;
  }
  if (!usesX11Session && !NSClassFromString(@"WSWaylandWindowManager")) {
    fprintf(stderr, "[Workspace] Native Wayland shell support is not built.\n");
    [pool drain]; return 1;
  }
  fprintf(stderr, "=== Starting Workspace ===\n");
#ifdef NEXTSPACE_BUILD_WAYLAND
  if (usesX11Session) {
    fprintf(stderr, "[Workspace] This build requires the native Wayland backend.\n");
    [pool drain]; return 1;
  }
  if ((ws_shell_descriptor = WSConsumeShellDescriptor()) < 0) {
    fprintf(stderr, "[Workspace] A private session shell connection is required.\n");
    [pool drain]; return 1;
  }
#endif
  workspace_q = dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_HIGH, 0);
#ifndef NEXTSPACE_BUILD_WAYLAND
  if (usesX11Session && !WSStartX11Session(argc, argv)) {
    [pool drain]; return 1;
  }
#endif
  fprintf(stderr, "=== Workspace initialized! ===\n");
  dispatch_sync(workspace_q, ^{
    NSSetUncaughtExceptionHandler(WSUncaughtExceptionHandler);
    @try { WSApplicationMain(argc, argv); }
    @catch (NSException *exception) {
      WSUncaughtExceptionHandler(exception);
      ws_quit_code = (WorkspaceExitCode)1;
    }
  });
  fprintf(stderr, "=== Workspace finished with exit code: %i ===\n", ws_quit_code);
#ifndef NEXTSPACE_BUILD_WAYLAND
  if (usesX11Session) WSFinishX11Session();
#endif
  if (ws_shell_descriptor >= 0) close(ws_shell_descriptor);
  [pool drain];
  return ws_quit_code;
}
