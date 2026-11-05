/* Shared Workspace icon artwork. SPDX-License-Identifier: GPL-2.0-or-later */
#import <AppKit/AppKit.h>

@interface WSIconTileView : NSView
{
  NSCell *_imageCell;
  NSCell *_tileCell;
}
- (void)setImage:(NSImage *)image;
@end
