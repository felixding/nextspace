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

/* Shared Recycler artwork and file operations. SPDX-License-Identifier: GPL-2.0-or-later */
#import <GNUstepGUI/GSDisplayServer.h>
#import "RecyclerIconView.h"
#import "Recycler.h"
#import "Processes/ProcessManager.h"

@implementation RecyclerIconView

- (id)initWithFrame:(NSRect)frame recycler:(Recycler *)owner
{
  self = [super initWithFrame:frame];
  if (self) {
    recycler = owner;
    [self registerForDraggedTypes:@[ NSFilenamesPboardType ]];
  }
  return self;
}

- (BOOL)acceptsFirstMouse:(NSEvent *)theEvent
{
  return YES;
}
- (void)mouseDown:(NSEvent *)event { [recycler mouseDown:event]; }

// --- Drag and Drop

static int imageNumber;
static NSDate *date = nil;
static NSTimeInterval tInterval = 0;

- (void)animate
{
  NSString *imageName;

  if (([NSDate timeIntervalSinceReferenceDate] - tInterval) < 0.1) {
    return;
  }

  tInterval = [NSDate timeIntervalSinceReferenceDate];

  if (++imageNumber > 4)
    imageNumber = 1;

  imageName = [NSString stringWithFormat:@"recycler-%i", imageNumber];

  [self setImage:[NSImage imageNamed:imageName]];
}

- (NSDragOperation)draggingEntered:(id<NSDraggingInfo>)sender
{
  NSDebugLLog(@"Recycler", @"Recycler: dragging entered!");

  NSArray *sourcePaths;
  BOOL draggedFromRecycler = NO;

  sourcePaths = [[sender draggingPasteboard] propertyListForType:NSFilenamesPboardType];

  for (NSString *path in sourcePaths) {
    if ([path rangeOfString:recycler.path].location != NSNotFound) {
      NSDebugLLog(@"Recycler", @"%@ is in %@", path, recycler.path);
      draggedFromRecycler = YES;
      break;
    }
  }

  if (draggedFromRecycler != NO) {
    draggingMask = NSDragOperationNone;
  } else {
    draggingMask = (NSDragOperationMove | NSDragOperationDelete);
    tInterval = [NSDate timeIntervalSinceReferenceDate];
  }

  return draggingMask;
}

- (void)draggingExited:(id<NSDraggingInfo>)sender
{
  NSDebugLLog(@"Recycler", @"Recycler: dragging exited!");
  [recycler updateIconImage];
}

- (NSDragOperation)draggingUpdated:(id<NSDraggingInfo>)sender
{
  if (draggingMask != NSDragOperationNone) {
    [self animate];
  }

  return draggingMask;
}

- (BOOL)prepareForDragOperation:(id<NSDraggingInfo>)sender
{
  NSDebugLLog(@"Recycler", @"Recycler: prepare fo dragging");
  return ([sender draggingSourceOperationMask] == NSDragOperationNone) ? NO : YES;
}

- (BOOL)performDragOperation:(id<NSDraggingInfo>)sender
{
  BOOL result = NO;
  NSPasteboard *dragPb = [sender draggingPasteboard];
  NSArray *types = [dragPb types];
  NSString *dbPath;
  NSMutableDictionary *db;
  NSFileManager *fm = [NSFileManager defaultManager];
  NSMutableArray *items;
  NSString *sourceDir;

  dbPath = [recycler.path stringByAppendingPathComponent:@".recycler.db"];
  if ([fm fileExistsAtPath:dbPath]) {
    db = [[NSMutableDictionary alloc] initWithContentsOfFile:dbPath];
  } else {
    db = [NSMutableDictionary new];
  }

  NSDebugLLog(@"Recycler", @"Recycler: perform dragging");

  [recycler setIconImage:[NSImage imageNamed:@"recycler"]];

  if ([types containsObject:NSFilenamesPboardType] == YES) {
    NSString *name, *path;

    items = [[dragPb propertyListForType:NSFilenamesPboardType] mutableCopy];
    sourceDir = [[items objectAtIndex:0] stringByDeletingLastPathComponent];

    for (NSUInteger i = 0; i < [items count]; i++) {
      path = [items objectAtIndex:i];
      name = [path lastPathComponent];
      [db setObject:[path stringByDeletingLastPathComponent] forKey:name];
      [items replaceObjectAtIndex:i withObject:name];
    }

    [[ProcessManager shared] startOperationWithType:MoveOperation
                                             source:sourceDir
                                             target:[recycler path]
                                              files:items];
    [items release];
    [db writeToFile:dbPath atomically:YES];
    result = YES;
  }

  [db release];
  [recycler updateIconImage];

  return result;
}

- (void)concludeDragOperation:(id<NSDraggingInfo>)sender
{
  NSDebugLLog(@"Recycler", @"Recycler: conclude dragging");
}

@end
