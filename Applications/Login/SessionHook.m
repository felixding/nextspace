/* User-owned login/logout hooks for the native session.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import <Foundation/Foundation.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv)
{
  if (argc != 2 || (strcmp(argv[1], "LoginHook") && strcmp(argv[1], "LogoutHook"))) return 2;
  if (getuid() != geteuid()) {
    fprintf(stderr, "Session hooks require matching user credentials.\n");
    return 1;
  }
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  NSString *path = [NSHomeDirectory() stringByAppendingPathComponent:@"Library/Preferences/.NextSpace/Login"];
  NSDictionary *preferences = [NSDictionary dictionaryWithContentsOfFile:path];
  id command = [preferences objectForKey:[NSString stringWithUTF8String:argv[1]]];
  if (!command || ([command isKindOfClass:[NSString class]] && ![command length])) return 0;
  if ([command isKindOfClass:[NSString class]]) {
    // The preferences UI stores an executable path; keep spaces in that path.
    // Retain the old whitespace-separated command form for existing profiles.
    if ([[NSFileManager defaultManager] isExecutableFileAtPath:command]) command = @[command];
    else {
      NSMutableArray *arguments = [NSMutableArray array];
      for (NSString *part in [command componentsSeparatedByCharactersInSet:[NSCharacterSet whitespaceCharacterSet]])
        if ([part length]) [arguments addObject:part];
      command = arguments;
    }
  }
  if (![command isKindOfClass:[NSArray class]]) return 2;
  if (![command count]) return 0;
  for (id part in command)
    if (![part isKindOfClass:[NSString class]]) return 2;
  if (![[command objectAtIndex:0] length]) return 0;
  char **arguments = calloc([command count] + 1, sizeof(char *));
  if (!arguments) return 1;
  for (NSUInteger index = 0; index < [command count]; index++)
    if (!(arguments[index] = strdup([[command objectAtIndex:index] UTF8String]))) return 1;
  execvp(arguments[0], arguments);
  perror("Cannot execute session hook");
  [pool drain];
  return 127;
}
