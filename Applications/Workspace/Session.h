/* Copyright (C) 2014-2021 Sergii Stoian; 2026 NEXTSPACE contributors.
   Shared session state. SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef WORKSPACE_SESSION_H
#define WORKSPACE_SESSION_H
#include <dispatch/dispatch.h>
#include <CoreFoundation/CFRunLoop.h>

extern dispatch_queue_t workspace_q;
extern CFRunLoopRef wm_runloop;

typedef enum WorkspaceExitCode {
  WSLogoutOnQuit = 0,
  WSPowerOffOnQuit = 129  /* ShutdownExitCode in Login/Controller.h */
} WorkspaceExitCode;
extern WorkspaceExitCode ws_quit_code;
extern int ws_shell_descriptor;

#ifdef __OBJC__
#import <Foundation/NSString.h>
#import <Foundation/NSUserDefaults.h>
/* The X11 build also supports the original, unpatched GUI library. */
extern NSString *GSSessionServiceName(NSString *name) __attribute__((weak));
extern NSString *GSDisplayBackendName(void) __attribute__((weak));
static inline NSString *WSSessionServiceName(NSString *name)
{
  return GSSessionServiceName ? GSSessionServiceName(name) : name;
}
static inline NSString *WSSessionBackendName(void)
{
  return GSDisplayBackendName ? GSDisplayBackendName() : [[NSUserDefaults standardUserDefaults] stringForKey:@"GSBackend"];
}
BOOL WSStartX11Session(int argc, const char **argv);
void WSPrepareX11Application(void);
void WSFinishX11Session(void);
#endif
#endif
