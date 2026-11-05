/* -*- mode: objc -*- */
//
// Project: Workspace
//
// Copyright (C) 2018 Sergii Stoian
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

#import "DockPrefs.h"
#import <SystemKit/OSEDefaults.h>
#import "Processes/ProcessManager.h"
#import "WindowManager.h"


static NSString *dockValue(NSInteger slot, NSString *key)
{
  return [[WSCurrentWindowManager() dockApplicationAtSlot:slot] objectForKey:key] ?: @"";
}

@implementation DockPrefsAppicon
- (void)setCursor:(NSCursor *)c
{
  _cursor = c;
}
// NSView override
- (void)resetCursorRects
{
  if (!_cursor)
    _cursor = [NSCursor arrowCursor];

  [[self superview] addCursorRect:[self frame] cursor:_cursor];
}
@end

@implementation DockPrefs

- (void)dealloc
{
  NSDebugLLog(@"DockPrefs", @"DockPrefs: dealloc");

  TEST_RELEASE(box);

  [super dealloc];
}

- (void)awakeFromNib
{
  // get the box and destroy the bogus window
  [box retain];
  [box removeFromSuperview];
  DESTROY(window);

  [showOnHiddenDockBtn setRefusesFirstResponder:YES];
  [autostartBtn setRefusesFirstResponder:YES];
  [iconBtn setRefusesFirstResponder:YES];
  [iconBtn setButtonType:NSMomentaryLightButton];
  [iconBtn setCursor:[NSCursor pointingHandCursor]];

  [appList setHeaderView:nil];
  [appList setDelegate:self];
  [appList setDataSource:self];
  [appList deselectAll:self];
  [appList setTarget:self];
  [appList setDoubleAction:@selector(appListDoubleClicked:)];
  [appList setRefusesFirstResponder:YES];

  [appList reloadData];
  [appList selectRow:0 byExtendingSelection:NO];

  [appIconBtn setRefusesFirstResponder:YES];
  [appLockedBtn setRefusesFirstResponder:YES];

  [[[NSApp delegate] notificationCenter]
      addObserver:self
         selector:@selector(revert:)
             name:[WSCurrentWindowManager() dockChangeNotification]
           object:nil];
}

- (NSString *)moduleName
{
  return _(@"Dock");
}

- (NSView *)view
{
  if (box == nil) {
    [NSBundle loadNibNamed:@"DockPrefs" owner:self];
  }

  return box;
}

//
// Table delegate methods
//
- (int)numberOfRowsInTableView:(NSTableView *)tv
{
  return [WSCurrentWindowManager() dockSlotCount];
}

- (id)tableView:(NSTableView *)tv objectValueForTableColumn:(NSTableColumn *)tc row:(int)row
{
  NSString *appName = ([dockValue(row, @"Name") length] ? dockValue(row, @"Name") : @".NoApplication");

  if (tc == [appList tableColumnWithIdentifier:@"autostart"]) {
    if ([dockValue(row, @"AutoLaunch") boolValue])
      return [NSImage imageNamed:@"CheckMark"];
    else
      return nil;
  } else {
    if ([[appName pathExtension] isEqualToString:@"GNUstep"])
      appName = [appName stringByDeletingPathExtension];
    else
      appName = [appName pathExtension];

    if ([appName isEqualToString:@"Workspace"] || [appName isEqualToString:@"Recycler"]) {
      [[tc dataCellForRow:row] setEnabled:NO];
    } else {
      [[tc dataCellForRow:row] setEnabled:YES];
    }

    return appName;
  }
}

- (void)tableViewSelectionDidChange:(NSNotification *)aNotification
{
  NSTableView *tv = [aNotification object];
  NSInteger selRow = [tv selectedRow];
  NSString *appName = ([dockValue(selRow, @"Name") length] ? dockValue(selRow, @"Name") : @".NoApplication");

  if ([[appName pathExtension] isEqualToString:@"GNUstep"])
    appName = [appName stringByDeletingPathExtension];
  else
    appName = [appName pathExtension];

  [nameField setStringValue:appName];
  [autostartBtn setEnabled:YES];

  if ([appName isEqualToString:@"Workspace"]) {
    [iconBtn setImage:[NSApp applicationIconImage]];
    [pathField setStringValue:@""];
  } else {
    [iconBtn setImage:[WSCurrentWindowManager() dockImageAtSlot:selRow]];
    [pathField setStringValue:dockValue(selRow, @"Command")];
  }
  [autostartBtn setState:[dockValue(selRow, @"AutoLaunch") boolValue] ? NSOnState : NSOffState];

  if ([appPanel isVisible]) {
    [self appSettingsPanelUpdate];
  }
}

- (BOOL)tableView:(NSTableView *)tv shouldSelectRow:(NSInteger)row
{
  NSString *value = ([dockValue(row, @"Name") length] ? dockValue(row, @"Name") : @".NoApplication");

  if (!value || [value isEqualToString:@".NoApplication"] ||
      [value isEqualToString:@"Recycler.GNUstep"])
    return NO;

  return YES;
}

- (void)appListDoubleClicked:(id)sender
{
  [WSCurrentWindowManager() setDockValue:![autostartBtn state] ? @"Yes" : @"No" forKey:@"AutoLaunch" atSlot:[appList selectedRow]];

  [autostartBtn setState:![autostartBtn state]];
  [appList reloadData];
}

// --- Button

- (void)setAppAutostarted:(id)sender
{
  [WSCurrentWindowManager() setDockValue:[autostartBtn state] ? @"Yes" : @"No" forKey:@"AutoLaunch" atSlot:[appList selectedRow]];
  [appList reloadData];
}

- (void)revert:sender
{
  NSInteger selRow = [appList selectedRow];

  [appList reloadData];

  if (selRow > [appList numberOfRows] - 1)
    [appList selectRow:0 byExtendingSelection:NO];
  else
    [appList selectRow:selRow byExtendingSelection:NO];
}

@end

@implementation DockPrefs (AppSettings)

- (void)appSettingsPanelUpdate
{
  NSInteger selRow = [appList selectedRow];
  NSString *appName = ([dockValue(selRow, @"Name") length] ? dockValue(selRow, @"Name") : @".NoApplication");

  [appNameField setStringValue:appName];
  [appIconView setImage:[WSCurrentWindowManager() dockImageAtSlot:selRow]];
  [appCommandField setStringValue:dockValue(selRow, @"Command")];
  [appLockedBtn setState:[dockValue(selRow, @"Lock") boolValue]];

  if ([appName isEqualToString:@"Workspace.GNUstep"] ||
      [appName isEqualToString:@"Recycler.GNUstep"]) {
    [appCommandField setEnabled:NO];
    [appCommandField setStringValue:@"NEXTSPACE internal"];
    [appLockedBtn setEnabled:NO];
  }

  if ([[appName pathExtension] isEqualToString:@"GNUstep"]) {
    [appMiddleClickField setEnabled:NO];
    [appDndCommandField setEnabled:NO];
    [appMiddleClickField setStringValue:@""];
    [appDndCommandField setStringValue:@""];
  } else {
    [appLockedBtn setEnabled:YES];
    [appCommandField setEnabled:YES];
    [appMiddleClickField setEnabled:YES];
    [appDndCommandField setEnabled:YES];
    [appMiddleClickField setStringValue:dockValue(selRow, @"PasteCommand")];
    [appDndCommandField setStringValue:dockValue(selRow, @"DropCommand")];
  }
}

- (void)showAppSettingsPanel:(id)sender
{
  NSString *appName = (dockValue([appList selectedRow], @"Name").length ? dockValue([appList selectedRow], @"Name") : @".NoApplication");

  if (!appName || [appName isEqualToString:@"Workspace.GNUstep"] ||
      [appName isEqualToString:@"Recycler.GNUstep"])
    return;

  [self appSettingsPanelUpdate];

  // [appPanel makeKeyAndOrderFront:[iconBtn window]];
  [appPanel orderFront:[iconBtn window]];
  [appPanel makeFirstResponder:appCommandField];
}

- (void)setAppIcon:(id)sender
{
  NSInteger selRow = [appList selectedRow];
  NSInteger result;
  NSOpenPanel *openPanel;
  NSUserDefaults *defs = [NSUserDefaults standardUserDefaults];

  openPanel = [NSOpenPanel openPanel];
  [openPanel setAllowsMultipleSelection:NO];

  result = [openPanel runModalForDirectory:[defs objectForKey:@"OpenDir"]
                                      file:nil
                                     types:[NSImage imageFileTypes]];
  if (result == NSOKButton) {
    [defs setObject:[openPanel directory] forKey:@"OpenDir"];
    [WSCurrentWindowManager() setDockImageAtPath:[[openPanel filenames] lastObject] atSlot:selRow];
    [appIconView setImage:[WSCurrentWindowManager() dockImageAtSlot:selRow]];
    [iconBtn setImage:[WSCurrentWindowManager() dockImageAtSlot:selRow]];
  }
}

- (void)setAppLocked:(id)sender
{
  [WSCurrentWindowManager() setDockValue:[sender state] ? @"Yes" : @"No" forKey:@"Lock" atSlot:[appList selectedRow]];
}

- (void)setAppCommand:(id)sender
{
  [WSCurrentWindowManager() setDockValue:[sender stringValue] forKey:@"Command" atSlot:[appList selectedRow]];
}

- (void)setAppPasteCommand:(id)sender
{
  [WSCurrentWindowManager() setDockValue:[sender stringValue] forKey:@"PasteCommand" atSlot:[appList selectedRow]];
}

- (void)setAppDndCommand:(id)sender
{
  [WSCurrentWindowManager() setDockValue:[sender stringValue] forKey:@"DropCommand" atSlot:[appList selectedRow]];
}

// NSWindow delegate method
- (void)windowWillClose:(NSNotification *)notif
{
  // if ([notif object] != appPanel)
  //   return;
  [[box window] makeKeyAndOrderFront:self];
}

@end
