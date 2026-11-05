/* Apply the greeter's display profile before starting its UI.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import "WSShellConnection.h"
#import <SystemKit/OSEScreen.h>
#include <stdio.h>

int main(int argc, char **argv)
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  WSShellConnection *connection = [[WSShellConnection alloc]
    initWithFileDescriptor:WSConsumeShellDescriptor()];
  if (!connection) { [pool drain]; return 1; }
  OSERegisterSessionSettings(connection);
  OSEScreen *screen = [OSEScreen sharedScreen];
  BOOL save = [[[NSProcessInfo processInfo] arguments] containsObject:@"--save"];
  BOOL success = save ? [screen saveCurrentDisplayLayout] : [screen applySavedDisplayLayout];
  if (save && success) {
    NSDictionary *profile = [NSDictionary dictionaryWithObjectsAndKeys:[NSNumber numberWithInt:2], @"Schema",
      [screen savedDisplayLayout], @"Layout", nil];
    NSData *xml = [NSPropertyListSerialization dataWithPropertyList:profile
      format:NSPropertyListXMLFormat_v1_0 options:0 error:NULL];
    fwrite([xml bytes], 1, [xml length], stdout);
  }
  fprintf(stderr, "[display-profile] %s\n", success ? (save ? "saved" : "restored") : "unchanged");
  OSERegisterSessionSettings(nil);
  [connection release];
  [pool drain];
  return save && !success ? 1 : 0;
}
