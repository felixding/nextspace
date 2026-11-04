/* SPDX-License-Identifier: GPL-2.0-or-later */
#import "OSEWaylandInput.h"
#import "OSESessionSettings.h"

NSDictionary *OSEWaylandInputSettings(void)
{ return OSERequestSessionSettings([NSDictionary dictionaryWithObject:@"input-state" forKey:@"action"]); }
BOOL OSEChangeWaylandInputSettings(NSString *kind, NSDictionary *changes)
{
  NSDictionary *current = OSEWaylandInputSettings();
  if (!current) return NO;
  NSMutableDictionary *settings = [[current mutableCopy] autorelease];
  [settings addEntriesFromDictionary:changes];
  NSDictionary *result = OSERequestSessionSettings([NSDictionary dictionaryWithObjectsAndKeys:
    kind, @"action", settings, @"settings", nil]);
  return [[result objectForKey:@"success"] boolValue];
}
