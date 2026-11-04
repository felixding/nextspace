/* -*- mode: objc -*- */
//
// Project: Preferences
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

#import <Foundation/NSDebug.h>
#import <Foundation/NSInvocation.h>
#import <Foundation/NSObjCRuntime.h>
#import <Foundation/NSDictionary.h>
#import <Foundation/NSValue.h>

#import <AppKit/NSApplication.h>
#import <AppKit/NSNibLoading.h>
#import <AppKit/NSScrollView.h>
#import <AppKit/NSScroller.h>
#import <AppKit/NSButton.h>

#import <SystemKit/OSEDefaults.h>
#import <DesktopKit/NXTBundle.h>

#import "PrefsController.h"
#include <math.h>

@implementation PrefsController

- (id)init
{
  self = [super init];
  prefsViews = [[NSMutableDictionary alloc] init];
  moduleSizes = [NSMutableDictionary new];
  return self;
}

//
// Initialize stuff that can't be set in the nib/gorm file.
// 
- (void)awakeFromNib
{
  // Let the system keep track of where it belongs
  [window setFrameAutosaveName:@"PreferencesMainWindow"];
  [window setFrameUsingName:@"PreferencesMainWindow"];

  if (iconList)	{ // stop processing if we already have an icon list
    return;
  }

  iconList = [[NSMatrix alloc] initWithFrame:NSMakeRect(0,0,64*30,70)
                                        mode:NSRadioModeMatrix
                                   cellClass:[NSButtonCell class]
                                numberOfRows:1
                             numberOfColumns:0];
  [iconList setCellSize:NSMakeSize(70, 70)];
  [iconList setIntercellSpacing:NSZeroSize];
  [iconList setAllowsEmptySelection:NO];

  [iconScrollView setDocumentView:iconList];
  [iconScrollView setHasHorizontalScroller:YES];
  [iconScrollView setHasVerticalScroller:NO];
  [iconScrollView setBorderType:NSBezelBorder];
  [[iconScrollView horizontalScroller] setArrowsPosition:NSScrollerArrowsNone];

  [self loadBundles];

  [iconList selectCellAtRow:0 column:0];
  [iconList sendAction];
  [window makeKeyAndOrderFront:self];
}

- (void)dealloc
{
  NSLog(@"PrefsController: dealloc");

  [prefsViews release]; [moduleSizes release];
  [window close];
  [window release];

  [super dealloc];
}

- (id)currentModule
{
  return currentModule;
}

- (NSWindow *)window
{
  return window;
}

//
// Button matrix
//
- (void)buttonClicked:(id)sender
{
  NSString        *buttonCaption = [[sender selectedCell] title];
  id<PrefsModule> module;
  NSView          *view;
  NSRect          buttonRect;

  module = [prefsViews objectForKey:buttonCaption];
  view = [module view];
  if (!view) return;

  buttonRect = [sender cellFrameAtRow:0 column:[sender selectedColumn]];
  [iconList scrollRectToVisible:buttonRect];
  
  NSValue *savedSize = [moduleSizes objectForKey:buttonCaption];
  if (!savedSize) {
    savedSize = [NSValue valueWithSize:[view frame].size]; [moduleSizes setObject:savedSize forKey:buttonCaption];
  }
  NSSize desired = [savedSize sizeValue];
  CGFloat delta = moduleHeight > 0 ? desired.height - moduleHeight : 0;
  moduleHeight = desired.height;
  if (fabs(delta) > 0.1) {
    NSRect boxFrame = [prefsViewBox frame];
    NSView *content = [window contentView];
    BOOL autoresize = [content autoresizesSubviews]; [content setAutoresizesSubviews:NO];
    NSRect frame = [window frame]; frame.origin.y -= delta; frame.size.height += delta;
    [window setFrame:frame display:NO];
    /* Move the icon browser and its separate divider together. */
    for (NSView *sibling in [content subviews]) {
      NSRect siblingFrame = [sibling frame];
      if (sibling != prefsViewBox && siblingFrame.origin.y >= NSMaxY(boxFrame) - 1) {
        siblingFrame.origin.y += delta; [sibling setFrame:siblingFrame];
      }
    }
    boxFrame.size.height += delta;
    [prefsViewBox setFrame:boxFrame];
    [content setAutoresizesSubviews:autoresize];
  }
  [view setFrameSize:desired];
  [prefsViewBox setContentView:view];
  /* Resizing/replacing a module also exposes its parent's retained pixels. */
  [[window contentView] setNeedsDisplay:YES];
  [window setTitle:buttonCaption];
       
  currentModule = module;
}

//
// Modules
//
- (BOOL)registerPrefsModule:(id)aPrefsModule
{
  NSButtonCell	*button;
  NSString	*caption;

  caption = [aPrefsModule buttonCaption];
  if (!caption) {
    return NO;
  }
  
  if ([prefsViews objectForKey:caption] != aPrefsModule) {
    [prefsViews setObject:aPrefsModule forKey:caption];
  }

  button = [[NSButtonCell alloc] init];
  [button setTitle:caption];
  [button setFont:[NSFont systemFontOfSize:9]];
  [button setImage:[aPrefsModule buttonImage]];
  [button setImagePosition:NSImageOnly];
  [button setButtonType:NSOnOffButton];
  [button setRefusesFirstResponder:YES];

  [button setTarget:self];
  [button setAction:@selector(buttonClicked:)];

  [iconList addColumnWithCells:[NSArray arrayWithObject:button]];
  [iconList sizeToCells];
  [button release];

  return YES;
}

- (void)loadBundles
{
  NSDictionary *bRegistry;
  NSArray      *modules;

  bRegistry = [[NXTBundle shared] registerBundlesOfType:@"preferences"
                                                atPath:nil];
  modules = [[NXTBundle shared] loadRegisteredBundles:bRegistry
                                                type:@"Preferences"
                                            protocol:@protocol(PrefsModule)];
  for (id b in modules) {
    [self registerPrefsModule:b];
  }
}

@end
