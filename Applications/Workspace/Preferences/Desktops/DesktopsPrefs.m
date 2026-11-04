/*
   "Workspaces" preferences.
   Manipulates with options of on-screen Workspaces and saves its state.

   Copyright (C) 2018 Sergii Stoian

   This library is free software; you can redistribute it and/or
   modify it under the terms of the GNU Library General Public
   License as published by the Free Software Foundation; either
   version 2 of the License, or (at your option) any later version.

   This library is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPXSE.  See the GNU
   Library General Public License for more details.

   You should have received a copy of the GNU Library General Public
   License along with this library; if not, write to the Free
   Software Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
*/

#import "DesktopsPrefs.h"

#import <SystemKit/OSEDefaults.h>
#import <WindowManager.h>
#import <Controller.h>


@interface DesktopsPrefs (Private)
- (NSDictionary *)_wmState;
- (NSDictionary *)_wmDefaults;
- (BOOL)_saveShortcuts:(NSDictionary *)settings;
@end

@implementation DesktopsPrefs (Private)
- (NSDictionary *)_wmState
{
  NSMutableArray *desktops = [NSMutableArray array];
  for (NSString *name in [[WSCurrentWindowManager() desktopSettings:nil] objectForKey:@"names"])
    [desktops addObject:@{@"Name": name}];
  return @{@"Desktops": desktops};
}
- (NSDictionary *)_wmDefaults
{ return [[WSCurrentWindowManager() desktopSettings:nil] objectForKey:@"shortcuts"]; }
- (BOOL)_saveShortcuts:(NSDictionary *)settings
{ return [WSCurrentWindowManager() desktopSettings:@{@"shortcuts": settings}] != nil; }
@end

@implementation DesktopsPrefs

- (void)dealloc
{
  NSDebugLLog(@"DesktopsPrefs", @"DesktopsPrefs: dealloc");

  [box release];
  [desktopReps release];
  [wmStateDesktops release];

  [super dealloc];
}

- (void)awakeFromNib
{
  // get the box and destroy the bogus window
  [box retain];
  [box removeFromSuperview];

  // Names and Numbers
  desktopReps = [[NSMutableArray alloc]
      initWithObjects:dt1, dt2, dt3, dt4, dt5, dt6, dt7, dt8, dt9, dt10, nil];

  wmStateDesktops =
      [[NSMutableArray alloc] initWithArray:[[self _wmState] objectForKey:@"Desktops"]];
  desktopsCount = (wmStateDesktops && [wmStateDesktops count] > 0) ? MIN(10, [wmStateDesktops count]) : 1;
  [self arrangeDesktopReps];

  [desktopsNumber selectItemWithTag:desktopsCount];
  [nameField setStringValue:@""];

  // Show In Dock button
  [showInDockBtn setRefusesFirstResponder:YES];
  [showInDockBtn setState:[[OSEDefaults userDefaults] boolForKey:@"ShowDesktopInDock"]];

  DESTROY(window);
}

// --- Protocol
- (NSString *)moduleName
{
  return _(@"Desktops");
}

- (NSView *)view
{
  if (box == nil) {
    [NSBundle loadNibNamed:@"Desktops" owner:self];
  }

  return box;
}

- (void)revert:sender
{
  NSDictionary *wmState;
  NSDictionary *wmDefaults;
  NSString *shortcut;
  NSArray *modifiers;

  // Desktops
  wmState = [[NSDictionary alloc] initWithDictionary:[self _wmState]];
  if (!wmState) {
    return;
  }
  if (wmStateDesktops) {
    [wmStateDesktops release];
  }
  wmStateDesktops = [[NSMutableArray alloc] initWithArray:[wmState objectForKey:@"Desktops"]];
  desktopsCount = MAX(1, MIN(10, [wmStateDesktops count]));
  [desktopsNumber selectItemWithTag:desktopsCount];
  [self arrangeDesktopReps];
  [[desktopReps objectAtIndex:MIN(desktopsCount - 1, [WSCurrentWindowManager() desktopIndex])] performClick:self];
  [wmState release];

  NSDebugLLog(@"Preferences", @"switchKey = %@ (%li/%li), directSwitchKey = %@ (%li/%li)",
              [switchKey className], [[switchKey selectedItem] tag], [switchKey numberOfItems],
              [directSwitchKey className], [[directSwitchKey selectedItem] tag],
              [directSwitchKey numberOfItems]);

  // Shortcuts
  wmDefaults = [[NSDictionary alloc] initWithDictionary:[self _wmDefaults]];
  if (!wmDefaults) {
    return;
  }
  shortcut = [wmDefaults objectForKey:@"NextWorkspaceKey"];
  modifiers = [shortcut componentsSeparatedByString:@"+"];
  if ([[modifiers objectAtIndex:0] isEqualToString:@"Super"]) {
    [switchKey selectItemWithTag:0];
  } else if ([[modifiers objectAtIndex:0] isEqualToString:@"Alt"]) {
    [switchKey selectItemAtIndex:2];
  } else {
    [switchKey selectItemAtIndex:1];
  }
  //
  shortcut = [wmDefaults objectForKey:@"Desktop1Key"];
  modifiers = [shortcut componentsSeparatedByString:@"+"];
  if ([[modifiers objectAtIndex:0] isEqualToString:@"Super"]) {
    [directSwitchKey selectItemWithTag:0];
  } else if ([[modifiers objectAtIndex:0] isEqualToString:@"Alt"]) {
    [directSwitchKey selectItemWithTag:2];
  } else {
    [directSwitchKey selectItemWithTag:1];
  }
  [wmDefaults release];
}

// --- Utility
- (void)arrangeDesktopReps
{
  NSRect repFrame = [[desktopReps objectAtIndex:0] frame];
  NSUInteger repsWidth = (desktopsCount * repFrame.size.width) + ((desktopsCount - 1) * 4);
  CGFloat boxWidth = [desktopsBox frame].size.width;
  NSPoint repPoint = repFrame.origin;
  NSButton *rep;

  for (NSUInteger i = 0; i < [desktopReps count]; i++) {
    rep = [desktopReps objectAtIndex:i];
    if (i >= desktopsCount) [rep removeFromSuperview];
    else if ([rep superview] != desktopsBox) [desktopsBox addSubview:rep];
  }

  repPoint.x = floorf((boxWidth - repsWidth) / 2);
  repPoint.y = floorf(repPoint.y);
  for (int i = 0; i < desktopsCount; i++) {
    rep = [desktopReps objectAtIndex:i];
    [rep setFrameOrigin:repPoint];
    repPoint.x += [rep frame].size.width + 4;
  }
  [desktopsBox setNeedsDisplay:YES];
}

// --- Names and Numbers
- (void)selectWorkspace:(id)sender
{
  NSButton *button = nil;
  NSString *name = nil;

  for (int i = 0; i < desktopsCount; i++) {
    button = [desktopReps objectAtIndex:i];
    NSDebugLLog(@"Preferences", @"%d - Sender: %@, Button: %@", i, [sender title], [button title]);
    if (sender == button) {
      [sender setState:NSOnState];
      if (wmStateDesktops && [wmStateDesktops count] > i) {
        name = [[wmStateDesktops objectAtIndex:i] objectForKey:@"Name"];
      }
      if (!name) {
        name = [NSString stringWithFormat:@"Desktop %d", i + 1];
      }
      [nameField setStringValue:name];
      selectedDesktopRep = sender;
    } else {
      NSDebugLLog(@"Preferences", @"%d -  Button: %@ set to NSOffState", i, [button title]);
      [button setState:NSOffState];
    }
  }
}

- (void)changeName:(id)sender
{
  NSInteger index = [desktopReps indexOfObject:selectedDesktopRep];
  [wmStateDesktops replaceObjectAtIndex:index withObject:@{@"Name": [nameField stringValue]}];
  if ([WSCurrentWindowManager() desktopSettings:@{@"names": [wmStateDesktops valueForKey:@"Name"]}])
    [changeNameBtn setEnabled:NO];
  else [self revert:nil];
}

- (void)controlTextDidChange:(NSNotification *)aNotification
{
  NSDictionary *wsInfo = nil;
  NSString *wsName = nil;

  NSDebugLLog(@"Preferences", @"Text changed in %@", [[aNotification object] className]);
  if ([aNotification object] != nameField) {
    return;
  }

  if ([wmStateDesktops count] > 0) {
    wsInfo = [wmStateDesktops objectAtIndex:[desktopReps indexOfObject:selectedDesktopRep]];
  }
  wsName = [nameField stringValue];

  if ([wsName rangeOfCharacterFromSet:[NSCharacterSet alphanumericCharacterSet]].location !=
          NSNotFound &&
      (!wsInfo || [wsName isEqualTo:[wsInfo objectForKey:@"Name"]] == NO)) {
    [changeNameBtn setEnabled:YES];
  } else {
    [changeNameBtn setEnabled:NO];
  }
}

- (void)setWorkspaceQuantity:(id)sender
{
  NSInteger count = [[sender selectedItem] tag];
  NSMutableArray *names = [[[wmStateDesktops valueForKey:@"Name"] mutableCopy] autorelease];
  while ([names count] > count) [names removeLastObject];
  while ([names count] < count) [names addObject:[NSString stringWithFormat:@"Desktop %lu", (unsigned long)[names count] + 1]];
  if (![WSCurrentWindowManager() desktopSettings:@{@"names": names}]) { [self revert:nil]; return; }
  [wmStateDesktops setArray:[[self _wmState] objectForKey:@"Desktops"]];
  desktopsCount = count;
  if ([desktopReps indexOfObject:selectedDesktopRep] >= count)
    [self selectWorkspace:[desktopReps objectAtIndex:count - 1]];
  [self arrangeDesktopReps];
}

// --- Shortcuts
- (void)setSwitchShortcut:(id)sender
{
  NSInteger selectedItemTag = [[sender selectedItem] tag];
  NSMutableDictionary *wmDefaults;
  NSString *prefix = @"Control";

  wmDefaults = [NSMutableDictionary new];

  switch (selectedItemTag) {
    case 0:  // Alternate + Control + Arrow Keys
      prefix = @"Super+Control";
      break;
    case 1:  // Control + Arrow Keys (default)
      prefix = @"Control";
      break;
    case 2:  // Command + Control + Arrow Keys
      prefix = @"Alt+Control";
      break;
  }

  [wmDefaults setObject:[NSString stringWithFormat:@"%@+Right", prefix] forKey:@"NextWorkspaceKey"];
  [wmDefaults setObject:[NSString stringWithFormat:@"%@+Left", prefix] forKey:@"PrevWorkspaceKey"];
  BOOL saved = [self _saveShortcuts:wmDefaults];
  [wmDefaults release];
  if (!saved) [self revert:nil];
}
- (void)setDirectSwitchShortcut:(id)sender
{
  NSMutableDictionary *wmDefaults;
  NSString *prefix = @"Control";

  wmDefaults = [NSMutableDictionary new];

  switch ([[sender selectedItem] tag]) {
    case 0:  // Alternate + Control + Number Keys
      prefix = @"Super+Control";
      break;
    case 1:  // Control + Number Keys (default)
      prefix = @"Control";
      break;
    case 2:  // Command + Control + Number Keys
      prefix = @"Alt+Control";
      break;
  }

  for (int i = 1; i < 10; i++) {
    [wmDefaults setObject:[NSString stringWithFormat:@"%@+%i", prefix, i]
                   forKey:[NSString stringWithFormat:@"Desktop%iKey", i]];
  }
  [wmDefaults setObject:[NSString stringWithFormat:@"%@+0", prefix] forKey:@"Desktop10Key"];
  BOOL saved = [self _saveShortcuts:wmDefaults];
  [wmDefaults release];
  if (!saved) [self revert:nil];
}

// ---
- (void)setShowInDock:(id)sender
{
  [[OSEDefaults userDefaults] setBool:[sender state] ? YES : NO forKey:@"ShowWorkspaceInDock"];
  if ([sender state]) {
    [[NSApp delegate] createWorkspaceBadge];
  } else {
    [[NSApp delegate] destroyWorkspaceBadge];
  }
}

@end
