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
#import "WSShellConnection.h"
#include <unistd.h>
#include <stdlib.h>

WorkspaceExitCode ws_quit_code = WSLogoutOnQuit;
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

  [NSApp run];

  [pool drain];

  return 0;
}

int main(int argc, const char **argv)
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  NSString *backend = WSSessionBackendName();
  if (![backend length] ||
      [backend rangeOfString:@"wayland" options:NSCaseInsensitiveSearch].location == NSNotFound) {
    fprintf(stderr, "[Workspace] This build requires the native Wayland backend.\n");
    [pool drain]; return 1;
  }
  fprintf(stderr, "=== Starting Workspace ===\n");
  if ((ws_shell_descriptor = WSConsumeShellDescriptor()) < 0) {
    fprintf(stderr, "[Workspace] A private session shell connection is required.\n");
    [pool drain]; return 1;
  }
  fprintf(stderr, "=== Workspace initialized! ===\n");
  dispatch_sync(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_HIGH, 0), ^{
    NSSetUncaughtExceptionHandler(WSUncaughtExceptionHandler);
    @try { WSApplicationMain(argc, argv); }
    @catch (NSException *exception) {
      WSUncaughtExceptionHandler(exception);
      ws_quit_code = (WorkspaceExitCode)1;
    }
  });
  fprintf(stderr, "=== Workspace finished with exit code: %i ===\n", ws_quit_code);
  if (ws_shell_descriptor >= 0) close(ws_shell_descriptor);
  [pool drain];
  return ws_quit_code;
}
