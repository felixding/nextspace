/* -*- mode: objc -*- */
//
// Project: NEXTSPACE - Login application
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

#include <signal.h>
#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>
#import <Foundation/Foundation.h>
#import <AppKit/NSApplication.h>

static volatile sig_atomic_t stopRequested = 0;

static void handleSignal(int sig)
{
  stopRequested = 1;
}

@interface LoginSignalHandler : NSObject
+ (void)handlePendingStop:(NSTimer *)timer;
@end

@implementation LoginSignalHandler
+ (void)handlePendingStop:(NSTimer *)timer
{
  if (stopRequested) {
    // Finish defaults writes on the main run loop, never in a signal handler.
    [[NSUserDefaults standardUserDefaults] synchronize];
    [NSApp stop:nil];
  }
}
@end

static void watchStopRequests(void)
{
  NSTimer *timer = [NSTimer timerWithTimeInterval:0.1 target:[LoginSignalHandler class]
    selector:@selector(handlePendingStop:) userInfo:nil repeats:YES];
  NSRunLoop *loop = [NSRunLoop currentRunLoop];
  for (NSString *mode in [NSArray arrayWithObjects:NSDefaultRunLoopMode,
      NSModalPanelRunLoopMode, NSEventTrackingRunLoopMode, nil])
    [loop addTimer:timer forMode:mode];
}

@interface LoginApplication : NSApplication
@end

@implementation LoginApplication
- (void)_appIconInit
{
  // Do nothing
}
@end

int main(int argc, const char **argv)
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  const char *socket = getenv("GREETD_SOCK");
  if (!socket || !*socket) {
    fprintf(stderr, "Login requires the native greeter session launcher.\n");
    [pool release]; return 1;
  }
  if (getuid() == 0 || geteuid() == 0) {
    fprintf(stderr, "Login: the native greeter must run as an unprivileged account.\n");
    [pool release]; return 1;
  }
  signal(SIGQUIT, handleSignal);
  [LoginApplication sharedApplication];
  watchStopRequests();
  NSApplicationMain(argc, argv);
  [pool release]; return 0;
}
