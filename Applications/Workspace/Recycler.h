/* -*- mode: objc -*- */
//
// Project: Workspace
//
// Copyright (C) 2014-2021 Sergii Stoian
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

#include <AppKit/AppKit.h>

#import <DesktopKit/NXTIconView.h>
#import <DesktopKit/NXTIconBadge.h>
#import <SystemKit/OSEFileSystemMonitor.h>

#import "RecyclerIconView.h"

@class PathIcon;

@interface ItemsLoader : NSOperation
{
  NXTIconView *iconView;
  NSTextField *statusField;
  NSString *directoryPath;
  NSArray *selectedFiles;
}

@property (atomic, readonly) NSInteger itemsCount;

- (id)initWithIconView:(NXTIconView *)view
                status:(NSTextField *)status
                  path:(NSString *)dirPath
             selection:(NSArray *)filenames;

@end

@interface Recycler : NSObject
{
  RecyclerIconView *appIconView;
  NXTIconBadge *badge;

  NSImage *iconImage;
  NSString *recyclerDBPath;

  OSEFileSystemMonitor *fileSystemMonitor;

  // Panel
  NSPanel *panel;
  NSImageView *panelIcon;
  NSTextField *panelItems;
  NSScrollView *panelView;
  NXTIconView *filesView;
  NSButton *restoreBtn;

  // Items loader
  NSOperationQueue *operationQ;
  ItemsLoader *itemsLoader;

  // Dragging
  id draggedSource;
  PathIcon *draggedIcon;
  NSDragOperation draggingSourceMask;
}

@property (atomic, readonly) NSWindow *appIcon;
@property (atomic, readonly) NSString *path;
@property (atomic, readonly) NSInteger itemsCount;

- (id)init;

- (void)setIconImage:(NSImage *)image;
- (void)updateIconImage;
- (void)updatePanel;
- (void)mouseDown:(NSEvent *)event;

- (void)empty;

@end
