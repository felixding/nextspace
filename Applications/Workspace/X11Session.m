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
#import <SystemKit/OSEDefaults.h>
#import <SystemKit/OSEScreen.h>
#import "Workspace+WM.h"
#include "WM/wmcomposer.h"

static int cannotManageScreen;
static int checkError(Display *display, XErrorEvent *error)
{
  cannotManageScreen = 1;
  return -1;
}

BOOL WSStartX11Session(int argc, const char **argv)
{
  if (!XInitThreads()) return NO;
  Display *probe = XOpenDisplay(NULL);
  if (!probe) {
    fprintf(stderr, "[Workspace] X Window server is not ready on display '%s'\n", getenv("DISPLAY"));
    return NO;
  }
  XErrorHandler oldHandler = XSetErrorHandler(checkError);
  XSelectInput(probe, DefaultRootWindow(probe), SubstructureRedirectMask);
  XSync(probe, False);
  XSetErrorHandler(oldHandler);
  if (cannotManageScreen) {
    fprintf(stderr, "[Workspace] Error: other window manager already running. Quitting...\n");
    XCloseDisplay(probe); return NO;
  }
  XSelectInput(probe, DefaultRootWindow(probe), 0);
  XSync(probe, False);
  /* Keep the server connected until the embedded manager has its connection. */
  OSEDefaults *defs;
  defs = [[OSEDefaults alloc] initDefaultsWithPath:NSUserDomainMask domain:@"Workspace"];
  if ([defs boolForKey:@"RestoreDisplayLayout"] != NO) {
    dispatch_sync(workspace_q, ^{
      // Restore display layout
      OSEScreen *screen = [OSEScreen sharedScreen];
      [screen applySavedDisplayLayout];
    });
  }
  {
    // DISPATCH_QUEUE_CONCURRENT is mandatory for CFRunLoop run.
    dispatch_queue_t window_manager_q = dispatch_queue_create("ns.workspace.wm",
                                                              DISPATCH_QUEUE_CONCURRENT);

    //--- Initialize Window Manager
    fprintf(stderr, "=== Initializing Window Manager ===\n");
    dispatch_sync(window_manager_q, ^{
      wInitialize(argc, (char **)argv);
      wStartUp(True);

      WSUpdateScreenInfo(wDefaultScreen());
    });
    fprintf(stderr, "=== Window Manager initialized! ===\n");

    //--- Composer
    if ([defs boolForKey:@"ComposerEnabled"] != NO) {
      dispatch_queue_t composer_q = dispatch_queue_create("ns.workspace.composer", DISPATCH_QUEUE_CONCURRENT);
      dispatch_async(composer_q, ^{
        fprintf(stderr, "=== Initializing Composer ===\n");
        if (wComposerInitialize() == True) {
          fprintf(stderr, "=== Composer initialized ===\n");
          wComposerRunLoop();
          fprintf(stderr, "=== Composer completed it's execution ===\n");
        } else {
          fprintf(stderr, "=== Failed to initialize Composer ===\n");
        }
      });
    }
    [defs release];

    // Start WM run loop V0 to catch events while V1 is warming up.
    dispatch_async(window_manager_q, ^{
      WMRunLoop_V0();
    });
    dispatch_async(window_manager_q, ^{
      WMRunLoop_V1();
    });
  }


  XCloseDisplay(probe);
  return YES;
}

void WSPrepareX11Application(void) { wSetErrorHandler(); }
void WSFinishX11Session(void)
{
  wShutdown(WMExitMode);
  fprintf(stderr, "=== Window Manager execution has been stopped ===\n");
}
