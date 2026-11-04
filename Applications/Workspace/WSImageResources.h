#import <AppKit/AppKit.h>

static inline NSImage *WSImageFromDirectory(NSString *directory, NSString *name)
{
  if (!directory || !name) return nil;
  return [[[NSImage alloc] initWithContentsOfFile:[directory stringByAppendingPathComponent:
    [name stringByAppendingPathExtension:@"tiff"]]] autorelease];
}

// Gorm can embed image copies. Load both states from the external resources.
static inline void WSSetButtonImages(NSButton *button, NSString *directory,
                                     NSString *imageName, NSString *alternateName)
{
  NSImage *image = WSImageFromDirectory(directory, imageName);
  NSImage *alternate = WSImageFromDirectory(directory, alternateName);
  if (image) [button setImage:image];
  if (alternate) [button setAlternateImage:alternate];
}

static inline void WSSetViewImage(NSImageView *view, NSString *directory, NSString *name)
{
  NSImage *image = WSImageFromDirectory(directory, name);
  if (image) [view setImage:image];
}
