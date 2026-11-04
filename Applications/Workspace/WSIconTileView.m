/* Copyright (C) 2014-2021 Sergii Stoian; 2026 NEXTSPACE contributors.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import "WSIconTileView.h"
#import <GNUstepGUI/GSDisplayServer.h>

@implementation WSIconTileView
- (id)initWithFrame:(NSRect)frame
{
  if (!(self = [super initWithFrame:frame])) return nil;
  _imageCell = [[NSCell alloc] initImageCell:nil];
  [_imageCell setBordered:NO];
  NSImage *tile = [[GSCurrentServer() iconTileImage] copy];
  [tile setScalesWhenResized:NO];
  [tile setSize:frame.size];
  _tileCell = [[NSCell alloc] initImageCell:tile];
  [_tileCell setBordered:NO];
  [tile release];
  return self;
}
- (void)dealloc
{
  [_imageCell release]; [_tileCell release];
  [super dealloc];
}
- (void)setImage:(NSImage *)image
{
  [_imageCell setImage:image];
  [self setNeedsDisplay:YES];
}
- (void)drawRect:(NSRect)rect
{
  [_tileCell drawWithFrame:[self bounds] inView:self];
  [_imageCell drawWithFrame:[self bounds] inView:self];
}
@end
