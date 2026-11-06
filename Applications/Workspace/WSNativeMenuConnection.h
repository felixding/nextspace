/* Private menu-role handoff. No native widget implementation lives here.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import <Foundation/Foundation.h>
@class WSShellConnection;
extern NSString * const WSNativeMenuSelectionDidChangeNotification;

/* Optional inherited SEQPACKET endpoint; consume before starting AppKit/helpers. */
int WSConsumeNativeMenuDescriptor(void);

@interface WSNativeMenuConnection : NSObject <RunLoopEvents>
{
  WSShellConnection *_shell;
  NSRunLoop *_runLoop;
  NSArray *_modes;
  NSDictionary *_desired, *_sent, *_rejected;
  int _descriptor;
  pid_t _hostPID;
  BOOL _waiting, _watchingWrite;
}
/* Takes ownership, including on failure. All calls belong to the shell thread. */
- (id)initWithShell:(WSShellConnection *)shell fileDescriptor:(int)descriptor;
/* The acknowledged session host for the current foreign application's menu. */
- (pid_t)selectedHostPID;
- (void)invalidate;
@end
