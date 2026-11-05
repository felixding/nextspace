/* Copyright (C) 2014-2021 Sergii Stoian; 2026 NEXTSPACE contributors.
   Shared session state. SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef WORKSPACE_SESSION_H
#define WORKSPACE_SESSION_H
#include <dispatch/dispatch.h>

typedef enum WorkspaceExitCode {
  WSLogoutOnQuit = 0,
  WSPowerOffOnQuit = 129
} WorkspaceExitCode;
extern WorkspaceExitCode ws_quit_code;
extern int ws_shell_descriptor;

#ifdef __OBJC__
#import <GNUstepGUI/GSDisplayServer.h>
#import <GNUstepGUI/GSPasteboardServer.h>
static inline NSString *WSSessionServiceName(NSString *name)
{
  return GSSessionServiceName(name);
}
static inline NSString *WSSessionBackendName(void)
{
  return GSDisplayBackendName();
}
#endif
#endif
