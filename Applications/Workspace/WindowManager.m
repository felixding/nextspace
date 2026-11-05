/* Workspace policy adapter and shared desktop defaults. GPL-2.0-or-later. */
#import "WindowManager.h"
#import "Session.h"
#import <GNUstepGUI/GSDisplayServer.h>

NSArray *WSDesktopShortcutNames(void)
{
  return [NSArray arrayWithObjects:@"RaiseKey", @"LowerKey", @"GroupNextKey", @"GroupPrevKey",
    @"FocusNextKey", @"FocusPrevKey", @"NextWorkspaceKey", @"PrevWorkspaceKey",
    @"Desktop1Key", @"Desktop2Key", @"Desktop3Key", @"Desktop4Key", @"Desktop5Key",
    @"Desktop6Key", @"Desktop7Key", @"Desktop8Key", @"Desktop9Key", @"Desktop10Key", nil];
}
NSDictionary *WSDefaultDesktopShortcuts(void)
{
  NSArray *values = [NSArray arrayWithObjects:@"Command+Up", @"Command+Down", @"Command+Tab", @"Command+Shift+Tab",
    @"Command+grave", @"Command+Shift+grave", @"Control+Right", @"Control+Left",
    @"Control+1", @"Control+2", @"Control+3", @"Control+4", @"Control+5", @"Control+6",
    @"Control+7", @"Control+8", @"Control+9", @"Control+0", nil];
  return [NSDictionary dictionaryWithObjects:values forKeys:WSDesktopShortcutNames()];
}

id<WSWindowManager> WSCurrentWindowManager(void)
{
  Class adapter = [GSCurrentServer() isKindOfClass:NSClassFromString(@"WaylandServer")] ?
    NSClassFromString(@"WSWaylandWindowManager") : Nil;
  if (!adapter) [NSException raise:NSInternalInconsistencyException
    format:@"Workspace has no window-manager adapter for %@", [GSCurrentServer() class]];
  static id<WSWindowManager> manager;
  static dispatch_once_t once;
  dispatch_once(&once, ^{ manager = [adapter new]; });
  return manager;
}
