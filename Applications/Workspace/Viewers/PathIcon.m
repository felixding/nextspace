/* -*- mode: objc -*- */
//
// Project: Workspace
//
// Copyright (C) 2015-2019 Sergii Stoian
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

#import <AppKit/AppKit.h>
#include "Foundation/NSObjCRuntime.h"
#import <SystemKit/OSESystemInfo.h>
#import <SystemKit/OSEMouse.h>


#import "Controller+NSWorkspace.h"
#import "FileViewer.h"
#import <Processes/ProcessManager.h>
#import "PathIcon.h"


@implementation PathIcon

//============================================================================
// Init and destroy
//============================================================================

- init
{
  // Size of hilite.tiff 66x52
  [super initWithFrame:NSMakeRect(0, 0, 66, 52)];

  // registerForDraggedTypes: must call view that holds icon (Shelf, Path).
  // Calling it here make shelf icons continuosly added and removed
  // while dragged.

  doubleClickPassesClick = YES;
  return self;
}

- (void)dealloc
{
  TEST_RELEASE(paths);
  TEST_RELEASE(info);

  [super dealloc];
}

// Overriding
- (void)mouseDown:(NSEvent *)ev
{
  NSInteger clickCount;
  NSDate *evDate = [NSDate date];
  id superView;

  if (target == nil || isSelectable == NO || [ev type] != NSLeftMouseDown) {
    return;
  }
  NSDebugLLog(@"PathIcon", @"PathIcon: mouseDown: %@", paths);

  clickCount = [ev clickCount];
  modifierFlags = [ev modifierFlags];

  superView = [self superview];
  if ([superView isKindOfClass:[NXTIconView class]]) {
    [superView selectIcons:[NSSet setWithObject:self] withModifiers:modifierFlags];
  }

  // Dragging
  if ([target respondsToSelector:dragAction]) {
    NSDebugLLog(@"PathIcon", @"[PathIcon-mouseDown]: DRAGGING");
    NSPoint startPoint = [ev locationInWindow];
    NSInteger eventMask = NSLeftMouseDraggedMask | NSLeftMouseUpMask;
    NSInteger moveThreshold = [OSEMouse dragThreshold];

    while ([(ev = [_window nextEventMatchingMask:eventMask]) type] != NSLeftMouseUp) {
      NSPoint endPoint = [ev locationInWindow];
      if (absolute_value(startPoint.x - endPoint.x) > moveThreshold ||
          absolute_value(startPoint.y - endPoint.y) > moveThreshold) {
        [target performSelector:dragAction withObject:self withObject:ev];
        return;
      }
    }
  }
  [_window makeFirstResponder:[longLabel nextKeyView]];
  // Clicking
  if (clickCount == 2) {
    NSDebugLLog(@"PathIcon", @"PathIcon: 2 mouseDown: %@", paths);
    if ([target respondsToSelector:doubleAction]) {
      [target performSelector:doubleAction withObject:self];
    }
  } else if (clickCount == 1 || clickCount > 2) {
    NSDebugLLog(@"PathIcon", @"PathIcon: 1 || >2 mouseDown: %@", paths);
    // if (!doubleClickPassesClick && [self _waitForSecondMouseClick] != nil) {
    if (!doubleClickPassesClick) {
      NSEvent *e;
      CGFloat waitTime = [OSEMouse doubleClickInterval];
      NSDate *waitDate = [evDate dateByAddingTimeInterval:waitTime];
      unsigned mask =
          (NSLeftMouseDownMask | NSLeftMouseUpMask | NSRightMouseDown | NSRightMouseUpMask);
      e = [_window nextEventMatchingMask:mask
                               untilDate:waitDate
                                  inMode:NSEventTrackingRunLoopMode
                                 dequeue:NO];
      if (e) {
        return;
      }
    }
    [_window makeKeyAndOrderFront:self];
    if ([target respondsToSelector:action]) {
      [target performSelector:action withObject:self];
    }
  }
}

// Addons
- (void)setPaths:(NSArray *)newPaths
{
  ASSIGN(paths, newPaths);

  if ([paths count] > 1) {
    [self setLabelString:[NSString stringWithFormat:_(@"%lu items"), [paths count]]];
  } else {
    NSString *path = [paths objectAtIndex:0];

    if ([[path pathComponents] count] == 1) {
      [self setLabelString:[OSESystemInfo hostName]];
    } else {
      [self setLabelString:[path lastPathComponent]];
    }
  }
}

- (NSArray *)paths
{
  return paths;
}

- (void)setInfo:(NSDictionary *)anInfo
{
  ASSIGN(info, [anInfo copy]);
}

- (NSDictionary *)info
{
  return info;
}

- (void)setDoubleClickPassesClick:(BOOL)isPass
{
  doubleClickPassesClick = isPass;
}

- (BOOL)wEventIsDoubleClickPassesClick
{
  return doubleClickPassesClick;
}

- (BOOL)becomeFirstResponder
{
  return NO;
}

//============================================================================
// Drag and drop
//============================================================================

// --- NSDraggingSource must have 'draggingSourceOperationMaskForLocal:'
// catched by enclosing view (PathView, ShelfView) and dispathed to
// 'delegate' - FileViewer 'draggingSourceOperationMaskForLocal:iconView:'
// method.

// --- NSDraggingDestination

#define PASTEBOARD [sender draggingPasteboard]

- (NSDragOperation)_draggingDestinationMaskForPaths:(NSArray *)sourcePaths
                                           intoPath:(NSString *)destPath
{
  NSFileManager *fileManager = [NSFileManager defaultManager];
  NSString *realPath;
  unsigned int mask =
      (NSDragOperationCopy | NSDragOperationMove | NSDragOperationLink | NSDragOperationDelete);

  if ([fileManager isWritableFileAtPath:destPath] == NO) {
    NSDebugLLog(@"PathIcon", @"[PathIcon] %@ is not writable!", destPath);
    return NSDragOperationNone;
  }

  if ([[[fileManager fileAttributesAtPath:destPath traverseLink:YES] fileType]
          isEqualToString:NSFileTypeDirectory] == NO) {
    NSDebugLLog(@"PathIcon", @"[PathIcon] destination path `%@` is not a directory!", destPath);
    return NSDragOperationNone;
  }

  for (NSString *path in sourcePaths) {
    NSRange r;

    if ([fileManager isDeletableFileAtPath:path] == NO) {
      NSDebugLLog(@"PathIcon",
                  @"[PathIcon] path %@ can not be deleted."
                  @"Disabling Move and Delete operation.",
                  path);
      mask ^= (NSDragOperationMove | NSDragOperationDelete);
    }

    if ([path isEqualToString:destPath]) {
      NSDebugLLog(@"PathIcon",
                  @"[PathIcon] source and destination paths are equal "
                  @"(%@ == %@)",
                  path, destPath);
      return NSDragOperationNone;
    }

    if ([[path stringByDeletingLastPathComponent] isEqualToString:destPath]) {
      NSDebugLLog(@"PathIcon", @"[PathIcon] `%@` already exists in `%@`", path, destPath);
      return NSDragOperationNone;
    }
  }

  return mask;
}

// - Before the Image is Released
- (NSDragOperation)draggingEntered:(id<NSDraggingInfo>)sender
{
  NSString *destPath;
  NSArray *sourcePaths;

  sourcePaths = [PASTEBOARD propertyListForType:NSFilenamesPboardType];
  destPath = [paths objectAtIndex:0];

  NSDebugLLog(@"PathIcon", @"[PathIcon] draggingEntered: %@(%@) -> %@",
              [[sender draggingSource] className], [delegate className], destPath);

  if ([sender draggingSource] == self) {
    draggingMask = NSDragOperationNone;
  } else if (![sourcePaths isKindOfClass:[NSArray class]] || [sourcePaths count] == 0) {
    NSDebugLLog(@"PathIcon", @"[PathIcon] source path list is not NSArray or NSArray is empty!");
    draggingMask = NSDragOperationNone;
  } else {
    draggingMask = [self _draggingDestinationMaskForPaths:sourcePaths intoPath:destPath];
  }

  if (draggingMask != NSDragOperationNone) {
    NSImage *openedDir = [[NSApp delegate] iconForOpenedDirectory:destPath];
    if (openedDir) {
      [self setIconImage:openedDir];
    }
  }

  return draggingMask;
}

- (NSDragOperation)draggingUpdated:(id<NSDraggingInfo>)sender
{
  NSDebugLLog(@"PathIcon", @"[PathIcon] draggingUpdated: mask - %i", draggingMask);
  return draggingMask;
}

- (void)draggingExited:(id<NSDraggingInfo>)sender
{
  Controller *wsDelegate = [NSApp delegate];

  NSDebugLLog(@"PathIcon", @"[PathIcon] draggingExited");
  if (draggingMask != NSDragOperationNone) {
    [self setIconImage:[wsDelegate iconForFile:[paths objectAtIndex:0]]];
  }
}

// - After the Image is Released
- (BOOL)prepareForDragOperation:(id<NSDraggingInfo>)sender
{
  return YES;
}

- (BOOL)performDragOperation:(id<NSDraggingInfo>)sender
{
  NSMutableArray *filenames = [NSMutableArray array];
  NSArray *sourcePaths;
  NSString *sourceDir;
  unsigned int mask;
  unsigned int opType = NSDragOperationNone;

  sourcePaths = [PASTEBOARD propertyListForType:NSFilenamesPboardType];
  // construct an array holding only the trailing filenames
  for (NSString *path in sourcePaths) {
    [filenames addObject:[path lastPathComponent]];
  }

  mask = [sender draggingSourceOperationMask];

  if (mask & NSDragOperationMove) {
    opType = MoveOperation;
  } else if (mask & NSDragOperationCopy) {
    opType = CopyOperation;
  } else if (mask & NSDragOperationLink) {
    opType = LinkOperation;
  } else {
    return NO;
  }

  sourceDir = [[sourcePaths objectAtIndex:0] stringByDeletingLastPathComponent];
  [[ProcessManager shared] startOperationWithType:opType
                                           source:sourceDir
                                           target:[paths objectAtIndex:0]
                                            files:filenames];

  return YES;
}

- (void)concludeDragOperation:(id<NSDraggingInfo>)sender
{
  [self draggingExited:sender];
}

@end
