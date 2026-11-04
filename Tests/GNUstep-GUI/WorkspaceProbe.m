/* Workspace's existing distributed API, on either backend. LGPL-2.0-or-later. */
#import <AppKit/AppKit.h>
#import <GNUstepGUI/GSDisplayServer.h>
#import <GNUstepGUI/GSPasteboardServer.h>
#import "OSESessionSettings.h"
#include <unistd.h>
#include <math.h>

@protocol PreferenceFixturePopup <NSObject>
- (NSInteger)numberOfItems;
- (id)itemAtIndex:(NSInteger)index;
- (void)selectItemAtIndex:(NSInteger)index;
@end
@protocol MediaArtworkFixture
- (void)mediaOperationDidStart:(bycopy NSNotification *)notification;
- (void)mediaOperationDidEnd:(bycopy NSNotification *)notification;
@end

static NSString *serverName = @"NextSpaceWorkspaceSessionServer";
// DockPrefs retains its original int row signature across the message port.
@protocol DockCheckMarkSource
- (id)tableView:(id)table objectValueForTableColumn:(id)column row:(int)row;
@end

@protocol InfoArtwork
- (void)showInfoPanel:(id)sender;
@end
@protocol OpenUpInfoArtwork
- (id)showInfoPanel:(id)sender;
@end
@protocol MouseArtwork
- (void)setMenuButtonHand:(id)sender;
@end
@protocol TimeMonArtwork
- (void)togglePause:(id)sender;
@end
@protocol SoundArtwork
- (void)showMixer:(id)sender;
@end
@protocol MixerArtwork
- (void)setMode:(id)sender;
@end
@protocol FolderArtwork
- (id)newViewerRootedAt:(NSString *)path viewer:(NSString *)type isRoot:(BOOL)root;
- (void)selectIcons:(NSSet *)icons;
- (void)displayPath:(NSString *)path selection:(NSArray *)selection sender:(id)sender;
@end
@protocol ProcessesArtwork
- (void)showProcesses:(id)sender;
- (void)showApp:(id)sender;
@end
@protocol SelectionViewer
- (void)displayPath:(bycopy NSString *)path selection:(bycopy NSArray *)selection sender:(id)sender;
@end
@protocol PermissionInspector
- (void)showPermissionsInspector:(id)sender;
@end
@protocol BGFixtureManager
- (id)startOperationWithType:(int)type source:(bycopy NSString *)source target:(bycopy NSString *)target files:(bycopy NSArray *)files;
@end
@protocol FinderFixtureIcon
- (void)setPaths:(bycopy NSArray *)paths;
@end
@protocol FinderFixtureField
- (void)setStringValue:(bycopy NSString *)value;
@end
@protocol EmbeddedImages
- (void)showFinder:(id)sender;
- (void)finishFind;
@end
@protocol SelectionArtwork
- (void)showAttributesInspector:(id)sender;
@end
@protocol ReviewWorkflow
- (void)saveImageAs:(id)sender;
- (void)openImage:(id)sender;
@end
@protocol TerminalArtwork
- (void)openInfoPanel:(id)sender;
- (void)setIsAnimates:(BOOL)flag;
- (void)animate;
- (void)animateAppIcon;
- (void)updateTitleBar:(id)sender;
- (BOOL)isUserProgramRunning;
@end
@protocol ClockArtwork
- (void)setTracksDefaultsDatabase:(BOOL)flag;
- (void)setAlive:(BOOL)flag;
- (BOOL)isAlive;
- (void)set24HourFormat:(BOOL)flag;
- (BOOL)is24HourFormat;
- (void)setCalendarDate:(NSCalendarDate *)date;
- (void)setLanguage:(NSString *)language;
@end

static NSArray *bitmapSizes(id object, NSString *key)
{
  id widths = [object valueForKeyPath:[key stringByAppendingString:@".representations.pixelsWide"]];
  id heights = [object valueForKeyPath:[key stringByAppendingString:@".representations.pixelsHigh"]];
  id classes = [object valueForKeyPath:[key stringByAppendingString:@".representations.className"]];
  NSMutableArray *sizes = [NSMutableArray array];
  for (NSUInteger index = 0; index < [widths count]; index++)
    if ([[classes objectAtIndex:index] isEqual:@"NSBitmapImageRep"])
      [sizes addObject:[NSArray arrayWithObjects:
        [NSNumber numberWithInteger:[[widths objectAtIndex:index] integerValue]],
        [NSNumber numberWithInteger:[[heights objectAtIndex:index] integerValue]], nil]];
  return sizes;
}

static NSRect focusedImageRect(id view, NSRect frame, NSSize logical, NSImageScaling scaling, NSImageAlignment alignment);

static void infoImages(id view, NSMutableArray *images)
{
  if ([view isKindOfClass:[NSImageView class]]) {
    id image = [view image];
    NSSize size = [image size];
    NSRect rect = [view convertRect:[view bounds] toView:nil];
    NSRect drawing = focusedImageRect(view,[[view cell] drawingRectForBounds:[view bounds]],size,
      [view imageScaling],[view imageAlignment]);
    NSMutableArray *representations = [NSMutableArray array];
    id reps = [image representations];
    for (NSUInteger index = 0; index < [reps count]; index++) {
      id rep = [reps objectAtIndex:index];
      if (![rep isKindOfClass:[NSBitmapImageRep class]]) continue;
      [representations addObject:[NSArray arrayWithObjects:
        [NSNumber numberWithInteger:[rep pixelsWide]], [NSNumber numberWithInteger:[rep pixelsHigh]], nil]];
    }
    [images addObject:[NSDictionary dictionaryWithObjectsAndKeys:
      [NSNumber numberWithDouble:size.width], @"width", [NSNumber numberWithDouble:size.height], @"height",
      [NSArray arrayWithObjects:[NSNumber numberWithDouble:rect.origin.x], [NSNumber numberWithDouble:rect.origin.y],
        [NSNumber numberWithDouble:rect.size.width], [NSNumber numberWithDouble:rect.size.height], nil], @"base",
      [NSArray arrayWithObjects:@(drawing.origin.x),@(drawing.origin.y),@(drawing.size.width),@(drawing.size.height),nil],@"drawing_base",
      @([view imageScaling]),@"scaling",@([view imageAlignment]),@"alignment",
      representations, @"representations", nil]];
  }
  id children = [view subviews];
  for (NSUInteger index = 0; index < [children count]; index++) infoImages([children objectAtIndex:index], images);
}

static NSMutableDictionary *timeMonImage(id view, id cell, NSRect frame)
{
  NSArray *sizes = bitmapSizes(cell,@"image");
  if (![sizes count]) return nil;
  NSSize size = [[cell valueForKeyPath:@"image.size"] sizeValue];
  NSRect drawing = focusedImageRect(view,[cell drawingRectForBounds:frame],size,[cell imageScaling],NSImageAlignCenter);
  NSRect base = [view convertRect:frame toView:nil];
  NSString *resource = [NSString stringWithString:[cell valueForKeyPath:@"image.fileName"] ?: @""];
  return [NSMutableDictionary dictionaryWithDictionary:@{
    @"name":[[resource lastPathComponent] stringByDeletingPathExtension],@"resource":resource,
    @"representations":sizes,@"logical":@[@(size.width),@(size.height)],
    @"base":@[@(base.origin.x),@(base.origin.y),@(base.size.width),@(base.size.height)],
    @"drawing_base":@[@(drawing.origin.x),@(drawing.origin.y),@(drawing.size.width),@(drawing.size.height)]}];
}

static void timeMonControls(id view, NSMutableDictionary *controls, NSString *wheelOutput)
{
  NSRect rect = [view convertRect:[view bounds] toView:nil];
  NSArray *base = @[@(rect.origin.x),@(rect.origin.y),@(rect.size.width),@(rect.size.height)];
  if ([view isKindOfClass:[NSTextField class]] && [view isEditable]) {
    id delegate = [view delegate];
    [controls[@"fields"] addObject:@{@"value":[NSString stringWithString:[view stringValue]],
      @"action":NSStringFromSelector([view action]) ?: @"",@"base":base,@"has_delegate":@(delegate!=nil),
      @"legacy_editing_delegate":@([delegate respondsToSelector:@selector(textShouldEndEditing:)]),
      @"control_editing_delegate":@([delegate respondsToSelector:@selector(controlTextDidEndEditing:)])}];
  }
  if ([view isKindOfClass:[NSButton class]])
    [controls[@"buttons"] addObject:@{@"title":[NSString stringWithString:[view title]],
      @"action":NSStringFromSelector([view action]) ?: @"",@"base":base,
      @"representations":bitmapSizes(view,@"image")}];
  if ([view isKindOfClass:[NSSlider class]])
    [controls[@"sliders"] addObject:@{@"base":base,@"value":@([view doubleValue]),
      @"minimum":@([view minValue]),@"maximum":@([view maxValue])}];
  if ([view isKindOfClass:[NSButton class]]) {
    NSDictionary *image = timeMonImage(view,[view cell],[view bounds]);
    if (image) [controls[@"image_cells"] addObject:image];
  }
  if ([view isKindOfClass:[NSMatrix class]])
    for (NSInteger row=0; row<[view numberOfRows]; row++)
      for (NSInteger column=0; column<[view numberOfColumns]; column++) {
        NSMutableDictionary *image = timeMonImage(view,[view cellAtRow:row column:column],
          [view cellFrameAtRow:row column:column]);
        if (image) {
          image[@"row"]=@(row);image[@"column"]=@(column);
          image[@"matrix_columns"]=@([view numberOfColumns]);
          image[@"selected"]=@([[[view cellAtRow:row column:column] valueForKey:@"state"] integerValue]!=NSOffState);
          [controls[@"image_cells"] addObject:image];
        }
      }
  if ([[view className] isEqual:@"GSColorWheel"]) {
    [controls[@"wheels"] addObject:@{@"base":base,@"representations":bitmapSizes(view,@"image"),
      @"hue":[view valueForKey:@"hue"],@"saturation":[view valueForKey:@"saturation"],
      @"brightness":[view valueForKey:@"brightness"]}];
    if (wheelOutput) {
      NSData *data = [view valueForKeyPath:@"image.TIFFRepresentation"];
      NSCAssert([data writeToFile:wheelOutput atomically:YES], @"Export the color wheel bitmap");
    }
  }
  if ([view isKindOfClass:[NSImageView class]]) {
    NSImage *image = [view image]; NSSize size = [image size];
    [controls[@"images"] addObject:@{@"width":@(size.width),@"height":@(size.height),@"base":base,
      @"representations":bitmapSizes(view,@"image")}];
  }
  if ([view isKindOfClass:[NSScrollView class]]) {
    NSRect clip = [[view contentView] bounds], document = [[view documentView] frame];
    [controls[@"scroll_views"] addObject:@{@"base":base,
      @"clip":@[@(clip.origin.x),@(clip.origin.y),@(clip.size.width),@(clip.size.height)],
      @"document":@[@(document.origin.x),@(document.origin.y),@(document.size.width),@(document.size.height)]}];
  }
  if ([view isKindOfClass:[NSMatrix class]] && [view numberOfRows]==1 && [view numberOfColumns]==5) {
    NSMutableArray *cells = [NSMutableArray array];
    for (NSInteger column=0; column<5; column++) {
      id cell = [view cellAtRow:0 column:column];
      NSColor *color = [[cell backgroundColor] colorUsingColorSpaceName:NSCalibratedRGBColorSpace];
      CGFloat r=0,g=0,b=0,a=0; [color getRed:&r green:&g blue:&b alpha:&a];
      NSRect cellRect = [view convertRect:[view cellFrameAtRow:0 column:column] toView:nil];
      [cells addObject:@{@"title":[NSString stringWithString:[cell stringValue]],@"rgba":@[@(r),@(g),@(b),@(a)],
        @"base":@[@(cellRect.origin.x),@(cellRect.origin.y),@(cellRect.size.width),@(cellRect.size.height)]}];
    }
    NSMutableArray *types = [NSMutableArray array];
    // Remote fast-enumeration state points into the other process. Copy by index.
    id registered = [view registeredDraggedTypes];
    for (NSUInteger index=0; index<[registered count]; index++)
      [types addObject:[NSString stringWithString:[registered objectAtIndex:index]]];
    [controls[@"colors"] addObject:@{@"base":base,@"dragged_types":types,@"cells":cells}];
  }
  id children = [view subviews];
  for (NSUInteger index=0; index<[children count]; index++) timeMonControls([children objectAtIndex:index],controls,wheelOutput);
}

static NSRect focusedImageRect(id view, NSRect frame, NSSize logical, NSImageScaling scaling, NSImageAlignment alignment)
{
  NSSize size = logical;
  if (scaling == NSImageScaleAxesIndependently) size = frame.size;
  else if (scaling != NSImageScaleNone) {
    CGFloat factor = MIN(frame.size.width/logical.width,frame.size.height/logical.height);
    if (scaling == NSImageScaleProportionallyDown) factor = MIN(1,factor);
    size = NSMakeSize(logical.width*factor,logical.height*factor);
  }
  NSPoint position = NSMakePoint(MAX(NSMidX(frame)-size.width/2,0),MAX(NSMidY(frame)-size.height/2,0));
  if (alignment==NSImageAlignLeft || alignment==NSImageAlignTopLeft || alignment==NSImageAlignBottomLeft)
    position.x = NSMinX(frame);
  else if (alignment==NSImageAlignRight || alignment==NSImageAlignTopRight || alignment==NSImageAlignBottomRight)
    position.x = MAX(NSMaxX(frame)-size.width,0);
  if (alignment==NSImageAlignTop || alignment==NSImageAlignTopLeft || alignment==NSImageAlignTopRight)
    position.y = [view isFlipped] ? NSMinY(frame) : MAX(NSMaxY(frame)-size.height,0);
  else if (alignment==NSImageAlignBottom || alignment==NSImageAlignBottomLeft || alignment==NSImageAlignBottomRight)
    position.y = [view isFlipped] ? MAX(NSMaxY(frame)-size.height,0) : NSMinY(frame);
  NSRect rect;
  [view lockFocus];
  @try { rect = [view centerScanRect:NSMakeRect(position.x,position.y,size.width,size.height)]; }
  @finally { [view unlockFocus]; }
  return [view convertRect:rect toView:nil];
}

static void reviewArtwork(id view, BOOL highlighted, NSMutableArray *images)
{
  if ([view isKindOfClass:[NSButton class]]) {
    NSString *action = NSStringFromSelector([view action]);
    BOOL previous = [action isEqual:@"displayPrevRepresentation:"];
    if (previous || [action isEqual:@"displayNextRepresentation:"]) {
      [view highlight:highlighted];
      id cell = [view cell];
      NSString *key = highlighted ? @"alternateImage" : @"image";
      NSImage *image = [view valueForKey:key]; NSSize size = [image size];
      NSRect rect = focusedImageRect(view,[cell drawingRectForBounds:[view bounds]],
        size,[cell imageScaling],NSImageAlignCenter);
      NSRect bounds = [view convertRect:[view bounds] toView:nil];
      [images addObject:[NSDictionary dictionaryWithObjectsAndKeys:
        [NSString stringWithFormat:@"Page%@%@",previous ? @"Up" : @"Down",highlighted ? @"H" : @""],@"name",
        bitmapSizes(view,key),@"representations",@[@(size.width),@(size.height)],@"logical",
        @[@(rect.origin.x),@(rect.origin.y),@(rect.size.width),@(rect.size.height)],@"drawing_base",
        @[@(bounds.origin.x),@(bounds.origin.y),@(bounds.size.width),@(bounds.size.height)],@"base",
        @([cell isHighlighted]),@"highlighted",@([view isEnabled]),@"enabled",
        [NSString stringWithString:[image valueForKey:@"fileName"] ?: @""],@"resource",nil]];
      [view display];
    }
  }
  id children = [view subviews];
  for (NSUInteger index=0; index<[children count]; index++)
    reviewArtwork([children objectAtIndex:index],highlighted,images);
}

static void imageViewsOfSize(id view, NSSize size, NSMutableArray *views)
{
  if ([view isKindOfClass:[NSImageView class]] && NSEqualSizes([[view image] size],size))
    [views addObject:view];
  id children = [view subviews];
  for (NSUInteger index=0; index<[children count]; index++)
    imageViewsOfSize([children objectAtIndex:index],size,views);
}

static NSDictionary *imageArtwork(id source, NSString *imageKey, id view, NSRect rect, NSString *name,
  BOOL selected, BOOL dimmed)
{
  NSImage *image = [source valueForKeyPath:imageKey];
  NSSize logical = [image size];
  NSRect visible = [view convertRect:[view visibleRect] toView:nil];
  return [NSDictionary dictionaryWithObjectsAndKeys:name,@"name",
    [NSString stringWithString:[image valueForKey:@"fileName"] ?: @""],@"resource",
    bitmapSizes(source,imageKey),@"representations",
    [NSArray arrayWithObjects:@(logical.width),@(logical.height),nil],@"logical",
    [NSArray arrayWithObjects:@(rect.origin.x),@(rect.origin.y),@(rect.size.width),@(rect.size.height),nil],@"base",
    [NSArray arrayWithObjects:@(visible.origin.x),@(visible.origin.y),@(visible.size.width),@(visible.size.height),nil],@"visible",
    @([imageKey isEqual:@"iconImage"]),@"native_composite",
    @(dimmed),@"dimmed",@(selected),@"selected",nil];
}

static NSDictionary *iconArtwork(id view, NSString *imageKey, NSRect rect, NSString *name,
                                  BOOL selected, BOOL dimmed)
{
  return imageArtwork(view,imageKey,view,rect,name,selected,dimmed);
}

static NSDictionary *buttonImageArtwork(id button, NSString *name)
{
  id cell=[button cell];
  NSString *key=@"cell._cell_image";
  NSSize logical=[[button valueForKeyPath:@"cell._cell_image.size"] sizeValue];
  NSRect frame=[cell drawingRectForBounds:[button bounds]];
  NSCellImagePosition position=[cell imagePosition];
  NSCAssert(position==NSImageAbove || position==NSImageOnly,@"Expected artwork button layout");
  if (position==NSImageAbove) {
    NSSize title=[[cell valueForKeyPath:@"attributedTitle.size"] sizeValue];
    CGFloat margin=([cell isBordered] || [cell isBezeled]) ? 3 : 0;
    CGFloat titleSpace=title.height+GSCellTextImageYDist;
    frame.origin.y += [button isFlipped] ? margin : titleSpace+margin;
    frame.size.height -= titleSpace+2*margin;
  }
  NSRect rect=focusedImageRect(button,frame,logical,[cell imageScaling],NSImageAlignCenter);
  NSMutableDictionary *result=[NSMutableDictionary dictionaryWithDictionary:
    iconArtwork(button,key,rect,name,NO,NO)];
  [result setObject:key forKey:@"image_key"];
  return result;
}

static void loginInputRects(id view, NSRect target, NSMutableArray *rects)
{
  if ([view isKindOfClass:[NSTextField class]]) {
    NSRect bounds = [view convertRect:[view bounds] toView:nil];
    if (NSIntersectsRect(bounds,target))
      [rects addObject:[NSArray arrayWithObjects:[NSNumber numberWithDouble:bounds.origin.x],[NSNumber numberWithDouble:bounds.origin.y],
        [NSNumber numberWithDouble:bounds.size.width],[NSNumber numberWithDouble:bounds.size.height],nil]];
  }
  id children = [view subviews];
  for (NSUInteger index=0; index<[children count]; index++) loginInputRects([children objectAtIndex:index],target,rects);
}

static BOOL saveWorkspaceDefault(NSString *key, id value)
{
  NSString *session = [[[NSProcessInfo processInfo] environment] objectForKey:@"NEXTSPACE_SESSION_ID"];
  if (![session hasPrefix:@"test-"]) return NO;
  NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
  NSMutableDictionary *domain = [[[defaults persistentDomainForName:@"Workspace"] mutableCopy] autorelease];
  if (!domain) domain = [NSMutableDictionary dictionary];
  [domain setObject:value forKey:key];
  [defaults setPersistentDomain:domain forName:@"Workspace"];
  return [defaults synchronize];
}

@interface SessionObserver : NSObject { BOOL observed; }
- (void)notification:(NSNotification *)notification;
- (BOOL)observed;
@end
@implementation SessionObserver
- (void)notification:(NSNotification *)notification
{
  if ([[[notification userInfo] objectForKey:@"NSApplicationName"] isEqual:@"NextSpaceSessionProbe"])
    observed = YES;
}
- (BOOL)observed { return observed; }
@end

@interface SessionServer : NSObject
@end
@implementation SessionServer
- (void)applicationDidFinishLaunching:(NSNotification *)notification
{ puts("{\"ready\":true}"); fflush(stdout); }
- (NSArray *)launchedApplications
{
  return [NSArray arrayWithObject:[NSDictionary dictionaryWithObjectsAndKeys:
    serverName, @"NSApplicationName", [NSNumber numberWithInt:getpid()], @"NSApplicationProcessIdentifier", nil]];
}
@end

/* Exercise the existing menu actions through Workspace's normal application
   connection, without introducing a test endpoint in the desktop. */
@interface DockAction : NSObject { NSString *_title; }
- (id)initWithTitle:(NSString *)title;
- (NSString *)title;
- (void)setTitle:(NSString *)title;
@end
@implementation DockAction
- (id)initWithTitle:(NSString *)title
{ if ((self = [super init])) _title = [title copy]; return self; }
- (void)dealloc { [_title release]; [super dealloc]; }
- (NSString *)title { return _title; }
- (void)setTitle:(NSString *)title { ASSIGNCOPY(_title, title); }
@end
@interface NSObject (WorkspaceMenuActions)
- (void)setDockCollapse:(id)sender;
- (void)setDockVisibility:(id)sender;
- (void)setIconYardVisibility:(id)sender;
- (void)showPrefsPanel:(id)sender;
- (void)switchModule:(id)sender;
- (void)setDockLevel:(id)sender;
- (void)setAppCommand:(id)sender;
- (void)setAppLocked:(id)sender;
- (NSArray *)_undockedApplicationsList;
- (void)showPreferencesWindow;
- (void)buttonClicked:(id)sender;
- (void)hideOtherApplications;
- (void)openArchive:(id)sender;
- (void)decompressFile:(NSString *)path;
- (void)sectionButtonClicked:(id)sender;
- (void)swapCAMtrxClicked:(id)sender;
- (void)capsLockBtnClicked:(id)sender;
- (void)composeBtnClicked:(id)sender;
- (void)setWorkspaceQuantity:(id)sender;
- (void)setSwitchShortcut:(id)sender;
- (void)setDirectSwitchShortcut:(id)sender;
- (void)changeName:(id)sender;
- (id)printInfo;
- (BOOL)hasMultiplePages;
- (void)setHasMultiplePages:(BOOL)flag;
- (void)printDocumentUsingPrintPanel:(BOOL)flag;
- (void)displayNextRepresentation:(id)sender;
- (void)displayPrevRepresentation:(id)sender;
- (void)zoomIn:(id)sender;
- (void)zoomOut:(id)sender;
- (BOOL)openImageAtPath:(NSString *)path;
@end

static NSDictionary *applicationSummary(NSDictionary *info)
{
  NSMutableDictionary *summary = [NSMutableDictionary dictionary];
  for (NSString *key in [NSArray arrayWithObjects:@"NSApplicationName", @"NSApplicationPath",
      @"IsXWindowApplication", nil]) {
    id value = [info objectForKey:key];
    if (value) [summary setObject:value forKey:key];
  }
  id distributed = [info objectForKey:@"NSApplicationUsesDistributedObjects"];
  if (distributed) [summary setObject:[NSNumber numberWithBool:[distributed boolValue]]
    forKey:@"uses_distributed_objects"];
  id pids = [info objectForKey:@"NSApplicationProcessIdentifier"];
  if (pids) {
    NSMutableArray *values = [NSMutableArray array];
    if ([pids respondsToSelector:@selector(objectAtIndex:)]) {
      NSUInteger i;
      for (i = 0; i < [pids count]; i++)
        [values addObject:[NSNumber numberWithLongLong:[[pids objectAtIndex:i] longLongValue]]];
    } else [values addObject:[NSNumber numberWithLongLong:[pids longLongValue]]];
    [summary setObject:values forKey:@"pids"];
  }
  return summary;
}

int main(int argc, char **argv)
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  NSString *mode = argc > 1 ? [NSString stringWithUTF8String:argv[1]] : @"--list";
  int result = 0;
  @try {
    if ([mode isEqual:@"--serve"]) {
      [[NSProcessInfo processInfo] setProcessName:serverName];
      [NSApplication sharedApplication];
      SessionServer *server = [SessionServer new];
      [NSApp setDelegate:server];
      [NSApp run];
      [server release]; [pool drain]; return 0;
    }
    NSWorkspace *workspace = [NSWorkspace sharedWorkspace];
    id output = nil;
    if ([mode isEqual:@"--watch"] || [mode isEqual:@"--watch-empty"]) {
      BOOL empty = [mode isEqual:@"--watch-empty"];
      SessionObserver *observer = [SessionObserver new];
      [[workspace notificationCenter] addObserver:observer selector:@selector(notification:)
        name:NSWorkspaceDidLaunchApplicationNotification object:nil];
      puts("{\"ready\":true}"); fflush(stdout);
      NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:empty ? 1.5 : 5];
      while (![observer observed] && [deadline timeIntervalSinceNow] > 0)
        [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.02]];
      result = empty ? [observer observed] : ![observer observed];
      output = [NSDictionary dictionaryWithObject:[NSNumber numberWithBool:[observer observed]] forKey:@"observed"];
      [[workspace notificationCenter] removeObserver:observer]; [observer release];
    } else if ([mode isEqual:@"--notify"] || [mode isEqual:@"--notify-hold"]) {
      NSDictionary *info = [NSDictionary dictionaryWithObjectsAndKeys:@"NextSpaceSessionProbe", @"NSApplicationName",
        [NSNumber numberWithInt:getpid()], @"NSApplicationProcessIdentifier", nil];
      [[workspace notificationCenter] postNotificationName:NSWorkspaceDidLaunchApplicationNotification
        object:workspace userInfo:info];
      if ([mode isEqual:@"--notify-hold"]) {
        puts("{\"ready\":true}"); fflush(stdout);
        [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:10]];
      }
      output = [NSDictionary dictionaryWithObject:[NSNumber numberWithBool:YES] forKey:@"posted"];
    } else if ([mode isEqual:@"--cleanup-registry"]) {
      NSString *session = [[[NSProcessInfo processInfo] environment] objectForKey:@"NEXTSPACE_SESSION_ID"];
      if (![session hasPrefix:@"test-"]) { [pool drain]; return 1; }
      NSString *path = [NSTemporaryDirectory() stringByAppendingPathComponent:GSSessionServiceName(@"GSLaunchedApplications")];
      [[NSFileManager defaultManager] removeItemAtPath:path error:NULL];
      [[NSFileManager defaultManager] removeItemAtPath:[path stringByAppendingPathExtension:@"lock"] error:NULL];
      output = [NSDictionary dictionaryWithObject:[NSNumber numberWithBool:YES] forKey:@"cleaned"];
    } else if ([mode isEqual:@"--write-desktops"] && argc > 2) {
      NSUInteger count = atoi(argv[2]);
      if (!count || count > 32) { [pool drain]; return 1; }
      NSMutableArray *names = [NSMutableArray array];
      NSUInteger index;
      for (index = 1; index <= count; index++)
        [names addObject:[NSString stringWithFormat:@"Workspace %lu", (unsigned long)index]];
      BOOL saved = saveWorkspaceDefault(@"WaylandDesktops", names);
      output = [NSDictionary dictionaryWithObject:[NSNumber numberWithBool:saved] forKey:@"saved"];
      if (!saved) result = 1;
    } else if ([mode isEqual:@"--post-appearance"]) {
      [[NSDistributedNotificationCenter defaultCenter] postNotificationName:@"WMDidChangeAppearanceSettingsNotification"
        object:@"GSWorkspaceNotification"];
      output = [NSDictionary dictionaryWithObject:[NSNumber numberWithBool:YES] forKey:@"posted"];
    } else if ([mode isEqual:@"--read-dock"]) {
      NSDictionary *domain = [[NSUserDefaults standardUserDefaults] persistentDomainForName:@"Workspace"];
      output = [NSDictionary dictionaryWithObjectsAndKeys:
        [domain objectForKey:@"WaylandDock"] ?: [NSDictionary dictionary], @"dock",
        [domain objectForKey:@"WaylandIconYardPositions"] ?: [NSDictionary dictionary], @"positions", nil];
    } else if ([mode isEqual:@"--write-dock"] && argc > 2) {
      NSDictionary *dock = [NSDictionary dictionaryWithContentsOfFile:[NSString stringWithUTF8String:argv[2]]];
      if (!dock) { [pool drain]; return 1; }
      BOOL saved = saveWorkspaceDefault(@"WaylandDock", dock);
      output = [NSDictionary dictionaryWithObject:[NSNumber numberWithBool:saved] forKey:@"saved"];
      if (!saved) result = 1;
    } else if ([mode isEqual:@"--preferences-mixer"]) {
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(@"Preferences") host:@""];
      [connection setRequestTimeout:10]; [connection setReplyTimeout:10];
      id controller = [(id)[connection rootProxy] delegate];
      [controller showPreferencesWindow];
      id preferences = [controller valueForKey:@"prefsController"];
      id sound = [[preferences valueForKey:@"prefsViews"] objectForKey:@"Sound Preferences"];
      if (!sound) { [pool drain]; return 1; }
      [sound view]; [(id<SoundArtwork>)sound showMixer:nil];
      id mixer = [sound valueForKey:@"mixer"];
      if (argc > 2) {
        int tag = atoi(argv[2]); if (tag < 0 || tag > 1) { [pool drain]; return 1; }
        id button = [mixer valueForKey:@"modeButton"];
        [button selectItemWithTag:tag]; [(id<MixerArtwork>)mixer setMode:button];
      }
      NSMutableArray *images = [NSMutableArray array];
      for (NSString *key in [NSArray arrayWithObjects:@"appVolumeMuteImg",@"appVolumeLoudImg",@"deviceVolumeMuteImg",@"deviceVolumeLoudImg",nil]) {
        id view = [mixer valueForKey:key];
        NSSize logical = [[view valueForKeyPath:@"image.size"] sizeValue];
        NSRect rect = [view convertRect:[view bounds] toView:nil];
        NSRect visible = [view convertRect:[view visibleRect] toView:nil];
        [images addObject:[NSDictionary dictionaryWithObjectsAndKeys:key,@"key",bitmapSizes(view,@"image"),@"representations",
          [NSArray arrayWithObjects:[NSNumber numberWithDouble:logical.width],[NSNumber numberWithDouble:logical.height],nil],@"logical",
          [NSArray arrayWithObjects:[NSNumber numberWithDouble:rect.origin.x],[NSNumber numberWithDouble:rect.origin.y],
            [NSNumber numberWithDouble:rect.size.width],[NSNumber numberWithDouble:rect.size.height],nil],@"base",
          [NSNumber numberWithInteger:[view imageScaling]],@"scaling",[NSNumber numberWithInteger:[view imageAlignment]],@"alignment",
          [NSNumber numberWithBool:[view isEnabled]],@"enabled",[NSNumber numberWithInteger:[view imageFrameStyle]],@"frame_style",
          [NSArray arrayWithObjects:[NSNumber numberWithDouble:visible.origin.x],[NSNumber numberWithDouble:visible.origin.y],
            [NSNumber numberWithDouble:visible.size.width],[NSNumber numberWithDouble:visible.size.height],nil],@"visible",nil]];
      }
      [[mixer window] display]; [[mixer window] flushWindow];
      output = [NSDictionary dictionaryWithObjectsAndKeys:images,@"images",[NSNumber numberWithInteger:[[mixer window] windowNumber]],@"window",
        [NSNumber numberWithInteger:[[[mixer valueForKey:@"modeButton"] selectedItem] tag]],@"mode",
        [NSNumber numberWithInteger:[[[sound valueForKey:@"soundServer"] valueForKey:@"status"] integerValue]],@"server_status",nil];
    } else if ([mode isEqual:@"--login-artwork"] && argc > 2) {
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(@"Login") host:@""];
      [connection setRequestTimeout:10]; [connection setReplyTimeout:10];
      id controller = [(id)[connection rootProxy] delegate];
      if (!controller) { fprintf(stderr,"Login application connection unavailable\n"); [pool drain]; return 1; }
      NSString *directory = [NSString stringWithUTF8String:argv[2]];
      NSMutableDictionary *buttons = [NSMutableDictionary dictionary];
      for (NSString *key in [NSArray arrayWithObjects:@"shutDownBtn",@"restartBtn",nil]) {
        id button = [controller valueForKey:key];
        NSString *name = [key isEqual:@"shutDownBtn"] ? @"power" : @"restart";
        if (argc > 4) {
          NSString *selected = [NSString stringWithUTF8String:argv[3]];
          [button highlight:([selected isEqual:name] || [selected isEqual:@"all"]) && atoi(argv[4]) != 0];
        }
        id cell = [button cell];
        NSImage *shown = [cell isHighlighted] ? [button alternateImage] : [button image];
        NSSize buttonSize = [shown size];
        NSRect buttonRect = focusedImageRect(button,[cell drawingRectForBounds:[button bounds]],buttonSize,[cell imageScaling],NSImageAlignCenter);
        for (NSString *imageKey in [NSArray arrayWithObjects:@"image",@"alternateImage",nil]) {
          NSString *file = [NSString stringWithFormat:@"%@-%@.tiff",name,imageKey];
          NSData *data = [[button valueForKey:imageKey] TIFFRepresentation];
          if (![data writeToFile:[directory stringByAppendingPathComponent:file] atomically:YES]) { fprintf(stderr,"Cannot export Login %s\n",[file UTF8String]); [pool drain]; return 1; }
        }
        [buttons setObject:[NSDictionary dictionaryWithObjectsAndKeys:bitmapSizes(button,@"image"),@"image",
          bitmapSizes(button,@"alternateImage"),@"alternateImage",
          [NSArray arrayWithObjects:[NSNumber numberWithDouble:buttonRect.origin.x],[NSNumber numberWithDouble:buttonRect.origin.y],
            [NSNumber numberWithDouble:buttonRect.size.width],[NSNumber numberWithDouble:buttonRect.size.height],nil],@"base",
          [NSArray arrayWithObjects:[NSNumber numberWithDouble:buttonSize.width],[NSNumber numberWithDouble:buttonSize.height],nil],@"logical",
          [NSNumber numberWithBool:[cell isHighlighted]],@"highlighted",[NSNumber numberWithBool:[cell isEnabled]],@"enabled",
          [NSNumber numberWithBool:[cell imageDimsWhenDisabled]],@"dims_when_disabled",[NSNumber numberWithBool:[cell isBordered]],@"bordered",
          [NSNumber numberWithInteger:[cell highlightsBy]],@"highlights_by",[NSNumber numberWithInteger:[cell imagePosition]],@"image_position",
          [NSNumber numberWithInteger:[cell imageScaling]],@"scaling",nil] forKey:name];
      }
      id view = [controller valueForKey:@"fieldsImage"];
      NSSize logical = [[view valueForKeyPath:@"image.size"] sizeValue];
      NSRect frame = [[view cell] drawingRectForBounds:[view bounds]];
      NSRect rect = focusedImageRect(view,frame,logical,[view imageScaling],[view imageAlignment]);
      [[view window] display]; [[view window] flushWindow];
      NSMutableArray *inputs = [NSMutableArray array];
      loginInputRects([[view window] contentView],rect,inputs);
      id panel = [controller valueForKey:@"panelImageView"];
      NSSize panelSize = [[panel valueForKeyPath:@"image.size"] sizeValue];
      NSRect panelRect = focusedImageRect(panel,[[panel cell] drawingRectForBounds:[panel bounds]],panelSize,[panel imageScaling],[panel imageAlignment]);
      NSArray *panelBase = [NSArray arrayWithObjects:[NSNumber numberWithDouble:panelRect.origin.x],[NSNumber numberWithDouble:panelRect.origin.y],
        [NSNumber numberWithDouble:panelRect.size.width],[NSNumber numberWithDouble:panelRect.size.height],nil];
      id labels = [controller valueForKey:@"fieldsLabelImage"];
      NSSize labelSize = [[labels valueForKeyPath:@"image.size"] sizeValue];
      NSRect labelRect = focusedImageRect(labels,[[labels cell] drawingRectForBounds:[labels bounds]],labelSize,[labels imageScaling],[labels imageAlignment]);
      NSDictionary *labelInfo = [NSDictionary dictionaryWithObjectsAndKeys:bitmapSizes(labels,@"image"),@"representations",
        [NSArray arrayWithObjects:[NSNumber numberWithDouble:labelRect.origin.x],[NSNumber numberWithDouble:labelRect.origin.y],
          [NSNumber numberWithDouble:labelRect.size.width],[NSNumber numberWithDouble:labelRect.size.height],nil],@"base",
        [NSArray arrayWithObjects:[NSNumber numberWithDouble:labelSize.width],[NSNumber numberWithDouble:labelSize.height],nil],@"logical",
        [NSNumber numberWithBool:[labels isEnabled]],@"enabled",[NSNumber numberWithInteger:[labels imageFrameStyle]],@"frame_style",nil];
      output = [NSDictionary dictionaryWithObjectsAndKeys:labelInfo,@"labels",panelBase,@"panel_base",buttons,@"buttons",inputs,@"inputs",[NSNumber numberWithInteger:[view imageScaling]],@"scaling",bitmapSizes(view,@"image"),@"representations",
        [NSArray arrayWithObjects:[NSNumber numberWithDouble:logical.width],[NSNumber numberWithDouble:logical.height],nil],@"logical",
        [NSArray arrayWithObjects:[NSNumber numberWithDouble:rect.origin.x],[NSNumber numberWithDouble:rect.origin.y],
          [NSNumber numberWithDouble:rect.size.width],[NSNumber numberWithDouble:rect.size.height],nil],@"base",
        [NSNumber numberWithInteger:[[view window] windowNumber]],@"window",
        [NSNumber numberWithBool:[view isEnabled]],@"enabled",[NSNumber numberWithInteger:[view imageFrameStyle]],@"frame_style",nil];
    } else if ([mode isEqual:@"--preferences-icon"] && argc > 2) {
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(@"Preferences") host:@""];
      [connection setRequestTimeout:10]; [connection setReplyTimeout:10];
      id controller = [(id)[connection rootProxy] delegate];
      [controller showPreferencesWindow];
      id preferences = [controller valueForKey:@"prefsController"];
      id icons = [preferences valueForKey:@"iconList"];
      NSString *caption = [[NSString stringWithUTF8String:argv[2]] stringByAppendingString:@" Preferences"];
      NSInteger column;
      for (column = 0; column < [icons numberOfColumns]; column++)
        if ([[[icons cellAtRow:0 column:column] title] isEqual:caption]) break;
      if (column == [icons numberOfColumns]) { [pool drain]; return 1; }
      [icons scrollCellToVisibleAtRow:0 column:column];
      id cell = [icons cellAtRow:0 column:column];
      NSSize logical = [[cell valueForKeyPath:@"image.size"] sizeValue];
      NSRect frame = [cell drawingRectForBounds:[icons cellFrameAtRow:0 column:column]];
      NSRect rect = focusedImageRect(icons,frame,logical,[cell imageScaling],NSImageAlignCenter);
      [[icons window] display]; [[icons window] flushWindow];
      output = [NSDictionary dictionaryWithObjectsAndKeys:caption,@"caption",bitmapSizes(cell,@"image"),@"representations",
        [NSArray arrayWithObjects:[NSNumber numberWithDouble:logical.width],[NSNumber numberWithDouble:logical.height],nil],@"logical",
        [NSArray arrayWithObjects:[NSNumber numberWithDouble:rect.origin.x],[NSNumber numberWithDouble:rect.origin.y],
          [NSNumber numberWithDouble:rect.size.width],[NSNumber numberWithDouble:rect.size.height],nil],@"base",
        [NSNumber numberWithInteger:[[icons window] windowNumber]],@"window",nil];
    } else if ([mode isEqual:@"--preferences-metadata"] || [mode isEqual:@"--preferences-action"]) {
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(@"Preferences") host:@""];
      [connection setRequestTimeout:15]; [connection setReplyTimeout:15];
      id controller = [(id)[connection rootProxy] delegate];
      if (!controller || argc < 3) { [pool drain]; return 1; }
      [controller showPreferencesWindow];
      id preferences = [controller valueForKey:@"prefsController"];
      id icons = [preferences valueForKey:@"iconList"];
      NSString *caption = [[NSString stringWithUTF8String:argv[2]] stringByAppendingString:@" Preferences"];
      NSInteger column;
      for (column = 0; column < [icons numberOfColumns]; column++)
        if ([[[icons cellAtRow:0 column:column] title] isEqual:caption]) break;
      if (column == [icons numberOfColumns]) {
        fprintf(stderr, "Preferences module missing: %s (%ld columns)\n", [caption UTF8String], (long)[icons numberOfColumns]);
        [pool drain]; return 1;
      }
      [icons selectCellAtRow:0 column:column]; [preferences buttonClicked:icons];
      id module = [preferences valueForKey:@"currentModule"];
      if ([mode isEqual:@"--preferences-action"]) {
        if (argc < 5) { [pool drain]; return 1; }
        NSString *key = [NSString stringWithUTF8String:argv[3]];
        if ([caption isEqual:@"Display Preferences"]) {
          id control = [module valueForKey:key];
          [control selectItemWithTag:atoi(argv[4])];
          [module performSelector:@selector(nativeDisplayChanged:) withObject:control];
        } else if ([caption isEqual:@"Screen Preferences"]) {
          if ([key isEqual:@"select"]) {
            id box = [[module valueForKey:@"displayBoxList"] objectAtIndex:atoi(argv[4])];
            [module performSelector:@selector(displayBoxClicked:) withObject:box];
          } else [[module valueForKey:key] performClick:nil];
        } else if ([caption isEqual:@"Keyboard Preferences"]) {
          id control = [module valueForKey:key];
          if ([key isEqual:@"sectionsBtn"]) {
            [control selectItemWithTag:atoi(argv[4])]; [module sectionButtonClicked:control];
          } else if ([key isEqual:@"swapCAMtrx"]) {
            [control selectCellWithTag:atoi(argv[4])]; [module swapCAMtrxClicked:control];
          } else {
            [control selectItemWithTitle:[NSString stringWithUTF8String:argv[4]]];
            if ([key isEqual:@"capsLockBtn"]) [module capsLockBtnClicked:control];
            else if ([key isEqual:@"composeKeyBtn"]) [module composeBtnClicked:control];
            else { [pool drain]; return 1; }
          }
        } else if ([caption isEqual:@"Font Preferences"]) {
          if (![key isEqual:@"enableAntiAliasingButton"]) { [pool drain]; return 1; }
          id control = [module valueForKey:key];
          [control setIntValue:atoi(argv[4])];
          [module performSelector:@selector(enableAntiAliasingChanged:) withObject:control];
        } else if ([caption isEqual:@"Mouse Preferences"]) {
          id mouse = [module valueForKey:@"mouse"];
          if ([key isEqual:@"doubleClickMtrx"]) {
            id control = [module valueForKey:key];
            [control selectCellWithTag:atoi(argv[4])];
            [module performSelector:@selector(doubleClickMtrxClicked:) withObject:control];
          } else if ([key isEqual:@"menuHand"]) {
            NSString *side = [NSString stringWithUTF8String:argv[4]];
            if (![side isEqual:@"left"] && ![side isEqual:@"right"]) { [pool drain]; return 1; }
            id button = [module valueForKey:[side isEqual:@"left"] ? @"menuLeftBtn" : @"menuRightBtn"];
            [button setState:NSOnState]; [(id<MouseArtwork>)module setMenuButtonHand:button];
          } else if ([key isEqual:@"doubleClickTime"]) {
            [mouse setValue:[NSNumber numberWithInt:atoi(argv[4])] forKey:key];
            [mouse performSelector:@selector(saveToDefaults)];
          } else { [pool drain]; return 1; }
        } else { [pool drain]; return 1; }
      }
      NSArray *keys = [NSArray arrayWithObjects:@"view", @"resolutionBtn", @"rateBtn", @"rotationBtn", @"reflectionBtn",
        @"brightnessBox", @"monitorsScroll", @"colorBtn", @"scaleBtn", @"effectiveSize", nil];
      if (![caption isEqual:@"Display Preferences"]) keys = [NSArray arrayWithObject:@"view"];
      if ([caption isEqual:@"Screen Preferences"]) keys = [NSArray arrayWithObjects:@"view", @"canvas",
        @"setMainBtn", @"setStateBtn", @"applyBtn", @"revertBtn", nil];
      NSMutableDictionary *controls = [NSMutableDictionary dictionary];
      if ([caption isEqual:@"Font Preferences"]) {
        id subpixel = [module valueForKey:@"subpixelModeButton"];
        [controls setObject:[NSDictionary dictionaryWithObjectsAndKeys:
          [NSNumber numberWithBool:subpixel != nil],@"connected",
          [NSNumber numberWithBool:[subpixel superview] != nil],@"attached",
          [NSNumber numberWithBool:[subpixel isHidden]],@"hidden",
          bitmapSizes(subpixel,@"image"),@"image_representations",
          bitmapSizes(subpixel,@"alternateImage"),@"alternate_representations",nil]
          forKey:@"subpixel_button_artwork"];
        [controls setObject:[NSNumber numberWithInt:[[module valueForKey:@"enableAntiAliasingButton"] intValue]]
                     forKey:@"antialiased"];
        NSString *path = [GSDefaultsRootForUser(NSUserName()) stringByAppendingPathComponent:@".NextSpace/WM.plist"];
        [controls setObject:path forKey:@"wm_defaults_path"];
        [controls setObject:[NSDictionary dictionaryWithContentsOfFile:path] ?: [NSDictionary dictionary]
                     forKey:@"wm_preferences"];
      }
      if ([caption isEqual:@"Mouse Preferences"]) {
        id hand = [module valueForKey:@"handImageView"];
        NSSize logical = [[hand valueForKeyPath:@"image.size"] sizeValue];
        NSRect rect = [hand convertRect:[hand bounds] toView:nil];
        NSRect visible = [hand convertRect:[hand visibleRect] toView:nil];
        id remoteClasses = [hand valueForKeyPath:@"image.representations.className"];
        NSMutableArray *classes = [NSMutableArray array];
        for (NSUInteger index = 0; index < [remoteClasses count]; index++) {
          id name = [remoteClasses objectAtIndex:index];
          [classes addObject:[name isEqual:@"NSBitmapImageRep"] ? @"NSBitmapImageRep" :
            [name isEqual:@"NSCachedImageRep"] ? @"NSCachedImageRep" : @"other"];
        }
        [controls setObject:[NSDictionary dictionaryWithObjectsAndKeys:
          [NSArray arrayWithObjects:[NSNumber numberWithDouble:logical.width],[NSNumber numberWithDouble:logical.height],nil],@"logical",
          bitmapSizes(hand,@"image"),@"representations",classes,@"representation_classes",
          [NSNumber numberWithInteger:[hand imageScaling]],@"scaling",[NSNumber numberWithInteger:[hand imageAlignment]],@"alignment",
          [NSArray arrayWithObjects:[NSNumber numberWithDouble:rect.origin.x],[NSNumber numberWithDouble:rect.origin.y],
            [NSNumber numberWithDouble:rect.size.width],[NSNumber numberWithDouble:rect.size.height],nil],@"base",
          [NSArray arrayWithObjects:[NSNumber numberWithDouble:visible.origin.x],[NSNumber numberWithDouble:visible.origin.y],
            [NSNumber numberWithDouble:visible.size.width],[NSNumber numberWithDouble:visible.size.height],nil],@"visible",
          [NSNumber numberWithBool:[hand isEnabled]],@"enabled",[NSNumber numberWithInteger:[hand imageFrameStyle]],@"frame_style",
          [NSNumber numberWithInteger:[[hand window] windowNumber]],@"window",
          [NSNumber numberWithInteger:[[[module valueForKey:@"mouse"] valueForKey:@"menuButton"] integerValue]],@"menu_button",nil]
          forKey:@"hand_artwork"];
        [hand display]; [[hand window] flushWindow];
        id matrix = [module valueForKey:@"doubleClickMtrx"];
        NSMutableArray *choices = [NSMutableArray array];
        id cells = [matrix cells];
        for (NSUInteger index = 0; index < [cells count]; index++)
          [choices addObject:[NSNumber numberWithInteger:[[cells objectAtIndex:index] tag]]];
        [controls setObject:choices forKey:@"double_click_choices"];
        [controls setObject:[NSNumber numberWithInteger:[[[module valueForKey:@"mouse"] valueForKey:@"doubleClickTime"] integerValue]]
                     forKey:@"double_click_time"];
      }
      if ([caption isEqual:@"Keyboard Preferences"]) {
        [controls setObject:[NSNumber numberWithInteger:[[[module valueForKey:@"swapCAMtrx"] selectedCell] tag]]
                     forKey:@"swap"];
        for (NSString *key in [NSArray arrayWithObjects:@"capsLockBtn", @"composeKeyBtn", nil]) {
          NSString *title = [[[module valueForKey:key] selectedItem] title];
          if (title) [controls setObject:title forKey:key];
        }
      }
      for (NSString *key in keys) {
        @try {
          id control = [module valueForKey:key];
          if (control) {
            NSMutableDictionary *value = [NSMutableDictionary dictionaryWithObjectsAndKeys:
              NSStringFromRect([control frame]), @"frame", NSStringFromRect([[control superview] frame]), @"parent",
              NSStringFromRect([control convertRect:[control bounds] toView:nil]), @"base", nil];
            if ([control respondsToSelector:@selector(isEnabled)])
              [value setObject:[NSNumber numberWithBool:[control isEnabled]] forKey:@"enabled"];
            [controls setObject:value forKey:key];
          }
        } @catch (NSException *exception) {}
      }
      if ([caption isEqual:@"Screen Preferences"]) {
        NSMutableArray *boxes = [NSMutableArray array];
        id list = [module valueForKey:@"displayBoxList"];
        NSUInteger index;
        for (index = 0; index < [list count]; index++) {
          id box = [list objectAtIndex:index];
          [boxes addObject:[NSDictionary dictionaryWithObjectsAndKeys:[box valueForKey:@"displayName"], @"name",
            NSStringFromRect([box convertRect:[box bounds] toView:nil]), @"base", nil]];
        }
        [controls setObject:boxes forKey:@"displays"];
      }
      output = [NSDictionary dictionaryWithObjectsAndKeys:caption, @"caption", controls, @"controls",
        NSStringFromRect([[preferences valueForKey:@"prefsViewBox"] frame]), @"box",
        NSStringFromRect([[preferences valueForKey:@"iconScrollView"] frame]), @"icons",
        NSStringFromRect([[preferences valueForKey:@"window"] frame]), @"window", nil];
    } else if ([mode isEqual:@"--preferences-clock"]) {
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(@"Preferences") host:@""];
      [connection setRequestTimeout:10]; [connection setReplyTimeout:10];
      id controller = [(id)[connection rootProxy] delegate];
      id clock = [controller valueForKey:@"clockView"];
      if (!clock) { fprintf(stderr, "Preferences clock is unavailable\n"); [pool drain]; return 1; }
      [(id<ClockArtwork>)clock setTracksDefaultsDatabase:NO];
      [(id<ClockArtwork>)clock setAlive:NO];
      if (argc > 2) [(id<ClockArtwork>)clock setLanguage:[NSString stringWithUTF8String:argv[2]]];
      [(id<ClockArtwork>)clock set24HourFormat:YES];
      [(id<ClockArtwork>)clock setCalendarDate:[NSCalendarDate dateWithString:@"2026-10-31 13:47:00 +0000"
        calendarFormat:@"%Y-%m-%d %H:%M:%S %z"]];
      [clock display]; [[clock window] flushWindow];
      // Read metadata on the application side; copying a live NSImage can
      // require a drawing context in this command-line inspection process.
      NSArray *representations = bitmapSizes(clock, @"clockBits");
      output = [NSDictionary dictionaryWithObjectsAndKeys:representations, @"representations",
        [NSNumber numberWithBool:[(id<ClockArtwork>)clock is24HourFormat]], @"format24",
        [NSNumber numberWithInteger:[[clock window] windowNumber]], @"window",
        [NSNumber numberWithInteger:[[clock valueForKey:@"hourOfDay"] integerValue]], @"hour",
        [NSNumber numberWithInteger:[[clock valueForKey:@"minuteOfHour"] integerValue]], @"minute",
        [NSNumber numberWithInteger:[[clock valueForKey:@"dayOfMonth"] integerValue]], @"day",
        [NSNumber numberWithInteger:[[clock valueForKey:@"monthOfYear"] integerValue]], @"month", nil];
    } else if ([mode isEqual:@"--info-artwork"] && argc > 2) {
      NSString *name = [NSString stringWithUTF8String:argv[2]];
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(name) host:@""];
      [connection setRequestTimeout:10]; [connection setReplyTimeout:10];
      id app = [connection rootProxy];
      if (argc <= 4 || strcmp(argv[4], "--existing") != 0) {
        if ([name isEqual:@"OpenUp"]) [(id<OpenUpInfoArtwork>)app showInfoPanel:nil];
        else [(id<InfoArtwork>)app showInfoPanel:nil];
      }
      id panel = nil;
      id windows = [app windows];
      for (NSUInteger index = 0; index < [windows count]; index++) {
        id window = [windows objectAtIndex:index];
        if ([[window title] isEqual:argc > 3 ? [NSString stringWithUTF8String:argv[3]] : @"Info"])
          { panel = window; break; }
      }
      if (!panel) { [pool drain]; return 1; }
      [panel displayIfNeeded]; [panel flushWindow];
      NSMutableArray *images = [NSMutableArray array];
      infoImages([panel contentView], images);
      output = [NSDictionary dictionaryWithObjectsAndKeys:images, @"images",
        [NSNumber numberWithInteger:[panel windowNumber]], @"window", nil];
    } else if ([mode isEqual:@"--timemon"] && argc > 2) {
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(@"TimeMon") host:@""];
      [connection setRequestTimeout:10]; [connection setReplyTimeout:10];
      id app = [connection rootProxy];
      id delegate = [app delegate];
      if (!delegate) { [pool drain]; return 1; }
      NSString *action = [NSString stringWithUTF8String:argv[2]];
      if ([action isEqual:@"toggle"]) [(id<TimeMonArtwork>)delegate togglePause:nil];
      else if ([action isEqual:@"seed-alpha"] && argc==4) {
        CGFloat alpha = [[NSString stringWithUTF8String:argv[3]] doubleValue];
        if (alpha<0 || alpha>1) { [pool drain]; return 1; }
        id windows = [app windows];
        for (NSUInteger index=0; index<[windows count]; index++) {
          id panel = [windows objectAtIndex:index];
          if ([panel isKindOfClass:[NSColorPanel class]])
            [panel setColor:[[panel color] colorWithAlphaComponent:alpha]];
        }
      }
      else if (![action isEqual:@"state"] && ![action isEqual:@"controls"]) { [pool drain]; return 1; }
      NSMutableDictionary *state = [NSMutableDictionary dictionaryWithObjectsAndKeys:
        [NSNumber numberWithBool:[app isRunning]], @"running", nil];
      if ([action isEqual:@"controls"]) {
        NSMutableArray *windows = [NSMutableArray array];
        id applicationWindows = [app windows];
        for (NSUInteger index=0; index<[applicationWindows count]; index++) {
          id window = [applicationWindows objectAtIndex:index];
          if ([window styleMask] & NSIconWindowMask || [[window title] isEqual:@"TimeMon"]) continue;
          NSMutableDictionary *controls = [NSMutableDictionary dictionaryWithDictionary:@{
            @"title":[NSString stringWithString:[window title]],@"window":@([window windowNumber]),@"visible":@([window isVisible])}];
          if ([window isKindOfClass:[NSColorPanel class]]) {
            controls[@"color_mode"]=@([window mode]);
            id responder = [window firstResponder];
            controls[@"first_responder_class"] = [NSString stringWithString:[responder className]];
            if ([responder respondsToSelector:@selector(action)])
              controls[@"first_responder_action"] = NSStringFromSelector([responder action]) ?: @"";
            NSColor *color = [[window color] colorUsingColorSpaceName:NSDeviceRGBColorSpace];
            if (color) controls[@"color_rgba"]=@[@([color redComponent]),@([color greenComponent]),
              @([color blueComponent]),@([color alphaComponent])];
          }
          for (NSString *key in @[@"fields",@"colors",@"images",@"buttons",@"scroll_views",@"wheels",@"sliders",@"image_cells"])
            [controls setObject:[NSMutableArray array] forKey:key];
          timeMonControls([window contentView], controls,argc>3 ? [NSString stringWithUTF8String:argv[3]] : nil);
          [windows addObject:controls];
        }
        [state setObject:windows forKey:@"windows"];
        [state setObject:[[NSUserDefaults standardUserDefaults] persistentDomainForName:@"TimeMon"] ?: @{}
                  forKey:@"saved_defaults"];
      }
      output = state;
    } else if ([mode isEqual:@"--openup"] && argc > 2) {
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(@"OpenUp") host:@""];
      [connection setRequestTimeout:15]; [connection setReplyTimeout:15];
      id app = [connection rootProxy];
      id delegate = [app delegate];
      if (!delegate) { [pool drain]; return 1; }
      NSString *action = [NSString stringWithUTF8String:argv[2]];
      if ([action isEqual:@"info"]) [(id<OpenUpInfoArtwork>)delegate showInfoPanel:nil];
      else if ([action isEqual:@"panel"]) [delegate openArchive:nil];
      else if ([action isEqual:@"extract"] && argc > 3)
        [delegate decompressFile:[NSString stringWithUTF8String:argv[3]]];
      else if (![action isEqual:@"state"]) { [pool drain]; return 1; }
      NSString *directory = [NSString stringWithString:[delegate valueForKey:@"appWorkingDirectory"]];
      output = [NSDictionary dictionaryWithObjectsAndKeys:directory, @"directory",
        [NSNumber numberWithUnsignedInteger:[[delegate valueForKey:@"fileTypeConfigArray"] count]], @"formats", nil];
    } else if ([mode isEqual:@"--review"] && argc > 2) {
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(@"Review") host:@""];
      [connection setRequestTimeout:10]; [connection setReplyTimeout:10];
      id app = [connection rootProxy];
      id delegate = [app delegate];
      NSString *action = [NSString stringWithUTF8String:argv[2]];
      if ([action isEqual:@"ready"]) {
        output = [NSDictionary dictionaryWithObject:@(delegate != nil) forKey:@"ready"];
      } else {
      if (!delegate) { fprintf(stderr, "Review application connection is not ready\n"); [pool drain]; return 1; }
      if ([action isEqual:@"save"] || [action isEqual:@"open-panel"]) [connection setReplyTimeout:60];
      if ([action isEqual:@"save"]) [(id<ReviewWorkflow>)delegate saveImageAs:nil];
      else if ([action isEqual:@"open-panel"]) [(id<ReviewWorkflow>)delegate openImage:nil];
      if ([action isEqual:@"open"] && argc > 3) {
        if (![delegate openImageAtPath:[NSString stringWithUTF8String:argv[3]]]) { [pool drain]; return 1; }
      }
      id windows = [delegate valueForKey:@"imageWindows"];
      if (![windows count]) { [pool drain]; return 1; }
      id viewer = [windows objectAtIndex:0];
      NSInteger main = [[app mainWindow] windowNumber];
      NSString *document = argc > 3 && ([action isEqual:@"open"] || [action isEqual:@"close"]) ?
        [NSString stringWithUTF8String:argv[3]] : nil;
      BOOL found = NO;
      for (NSUInteger i=0; i<[windows count]; i++) {
        id candidate = [windows objectAtIndex:i];
        if (document ? [[candidate valueForKey:@"path"] isEqual:document] :
            [[candidate valueForKey:@"window"] windowNumber]==main) {
          viewer=candidate; found=YES; break;
        }
      }
      if (document && !found) { [pool drain]; return 1; }
      if ([action isEqual:@"next"]) [viewer displayNextRepresentation:nil];
      else if ([action isEqual:@"previous"]) [viewer displayPrevRepresentation:nil];
      else if ([action isEqual:@"zoom-in"]) [delegate zoomIn:nil];
      else if ([action isEqual:@"zoom-out"]) [delegate zoomOut:nil];
      else if (![action isEqual:@"state"] && ![action isEqual:@"open"] && ![action isEqual:@"close"] &&
               ![action isEqual:@"artwork"] && ![action isEqual:@"save"] && ![action isEqual:@"open-panel"]) { [pool drain]; return 1; }
      id window = [viewer valueForKey:@"window"];
      if ([action isEqual:@"close"]) {
        [window performClose:nil];
        output = [NSDictionary dictionaryWithObject:[NSNumber numberWithBool:![window isVisible]] forKey:@"closed"];
      } else if ([action isEqual:@"artwork"]) {
        if (![[[[NSProcessInfo processInfo] environment] objectForKey:@"NEXTSPACE_SESSION_ID"] hasPrefix:@"test-"]) { [pool drain]; return 1; }
        NSMutableArray *images = [NSMutableArray array];
        reviewArtwork([window contentView],argc > 3 && atoi(argv[3]) != 0,images);
        [window displayIfNeeded]; [window flushWindow];
        output = [NSDictionary dictionaryWithObjectsAndKeys:images,@"images",@([window windowNumber]),@"window",nil];
      } else {
      [window displayIfNeeded]; [window flushWindow];
      id imageView = [viewer valueForKey:@"imageView"];
      output = [NSDictionary dictionaryWithObjectsAndKeys:
        [viewer valueForKey:@"path"], @"image_path",
        [NSNumber numberWithDouble:[window backingScaleFactor]], @"backing_scale",
        [NSNumber numberWithUnsignedInteger:[[viewer valueForKey:@"representations"] count]], @"frames",
        [NSNumber numberWithUnsignedInteger:[[viewer valueForKey:@"visibleRepIndex"] unsignedIntegerValue]], @"index",
        [NSString stringWithString:[[viewer valueForKey:@"scalePopup"] titleOfSelectedItem]], @"zoom",
        NSStringFromSize([[imageView image] size]), @"image_size",
        NSStringFromRect([imageView frame]), @"view_frame",
        NSStringFromRect([[viewer valueForKey:@"scrollView"] documentVisibleRect]), @"visible", nil];
      }
      }
    } else if ([mode isEqual:@"--textedit-panel"] && argc > 2) {
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(@"TextEdit") host:@""];
      [connection setRequestTimeout:10];[connection setReplyTimeout:10];
      id app = [connection rootProxy];id document = [[app mainWindow] delegate];
      NSString *action = [NSString stringWithUTF8String:argv[2]];
      NSMutableArray *rulerMarkers = [NSMutableArray array];
      if ([action isEqual:@"font"]) [app orderFrontFontPanel:nil];
      else if ([action isEqual:@"ruler"]) {
        [document setRichText:YES];
        id textView = [document firstTextView];
        NSMutableParagraphStyle *style = [[NSParagraphStyle defaultParagraphStyle] mutableCopy];
        NSMutableArray *tabs = [NSMutableArray array];
        for (NSInteger i=0;i<4;i++) {
          NSTextTab *tab = [[NSTextTab alloc] initWithType:(NSTextTabType)i location:60+60*i];
          [tabs addObject:tab];[tab release];
        }
        [style setTabStops:tabs];
        [[document textStorage] addAttribute:NSParagraphStyleAttributeName value:style range:NSMakeRange(0,[[document textStorage] length])];
        [textView setDefaultParagraphStyle:style];
        [textView setSelectedRange:NSMakeRange(0,0)];
        [textView setTypingAttributes:@{NSParagraphStyleAttributeName:style}];[style release];
        id scroll = [document valueForKey:@"scrollView"];
        [scroll setHasHorizontalRuler:YES];
        if (![scroll rulersVisible]) [textView toggleRuler:nil];
        [textView updateRuler];
        id markers = [[scroll horizontalRulerView] markers];
        for (NSUInteger index=0;index<[markers count];index++) {
          id marker = [markers objectAtIndex:index];
          id tab = [marker representedObject];
          [rulerMarkers addObject:@{@"image":[[marker image] name] ?: @"",
            @"location":@([marker markerLocation]), @"type":@([tab tabStopType])}];
        }
      }
      NSMutableArray *titles = [NSMutableArray array];
      id appWindows = [app windows];
      for (NSUInteger index=0;index<[appWindows count];index++) {
        id window = [appWindows objectAtIndex:index];
        if ([window isVisible]) [titles addObject:[window title]];
      }
      output = @{@"action":action,@"windows":titles,@"ruler_markers":rulerMarkers};
    } else if ([mode isEqual:@"--textedit-print"] && argc > 4) {
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(@"TextEdit") host:@""];
      [connection setRequestTimeout:15]; [connection setReplyTimeout:15];
      id app = [connection rootProxy];
      id document = [[app mainWindow] delegate];
      if (![document respondsToSelector:@selector(printDocumentUsingPrintPanel:)]) { [pool drain]; return 1; }
      NSString *path = [NSString stringWithUTF8String:argv[2]];
      if (![path isAbsolutePath]) { [pool drain]; return 1; }
      id info = [document printInfo];
      NSSize oldPaper = [info paperSize];
      [info setPaperSize:NSMakeSize(257,313)];
      [info setOrientation:strcmp(argv[4],"landscape")==0 ? NSLandscapeOrientation : NSPortraitOrientation];
      [[info dictionary] setObject:NSPrintSaveJob forKey:NSPrintJobDisposition];
      [[info dictionary] setObject:path forKey:NSPrintSavePath];
      BOOL paged = strcmp(argv[3],"paged")==0;
      /* Reflow an existing paged document only when paper geometry changes.
         Repeatedly enabling page mode would leave old layout containers. */
      if ([document hasMultiplePages] && !NSEqualSizes(oldPaper, [info paperSize]))
        [document setHasMultiplePages:NO];
      if ([document hasMultiplePages] != paged) [document setHasMultiplePages:paged];
      id printView = [[document valueForKey:@"scrollView"] documentView];
      fprintf(stderr, "Print view frame=%s bounds=%s paper=%s\n",
        [NSStringFromRect([printView frame]) UTF8String], [NSStringFromRect([printView bounds]) UTF8String],
        [NSStringFromSize([info paperSize]) UTF8String]);
      [document printDocumentUsingPrintPanel:NO];
      output = [NSDictionary dictionaryWithObjectsAndKeys:
        [NSNumber numberWithBool:[[NSData dataWithContentsOfFile:path] length]>0], @"saved",
        NSStringFromSize([info paperSize]), @"paper", nil];
    } else if ([mode isEqual:@"--terminal-input"]) {
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(@"Terminal") host:@""];
      [connection setRequestTimeout:5]; [connection setReplyTimeout:5];
      id app = [connection rootProxy];
      id responder = [[app mainWindow] firstResponder];
      if (!responder || ![responder respondsToSelector:@selector(markedRange)]) { [pool drain]; return 1; }
      NSAttributedString *text = [responder valueForKey:@"markedText"];
      NSString *marked = [NSString stringWithString:[text string] ?: @""];
      BOOL covered = YES;
      NSMutableArray *fonts = [NSMutableArray array];
      for (NSUInteger i = 0; i < [marked length]; i++) {
        NSFont *font = [text attribute:NSFontAttributeName atIndex:i effectiveRange:NULL];
        NSString *name = [font fontName];
        if (name && ![fonts containsObject:name]) [fonts addObject:name];
        if (![[font coveredCharacterSet] characterIsMember:[marked characterAtIndex:i]]) covered = NO;
      }
      output = [NSDictionary dictionaryWithObjectsAndKeys:marked, @"preedit",
        [NSNumber numberWithBool:covered], @"glyphs_covered",
        fonts, @"fonts",
        [NSNumber numberWithBool:[responder hasMarkedText]], @"marked",
        NSStringFromRect([responder firstRectForCharacterRange:NSMakeRange(0, 0)]), @"caret", nil];
    } else if ([mode isEqual:@"--terminal-animation"] && argc > 2) {
      if (![[[[NSProcessInfo processInfo] environment] objectForKey:@"NEXTSPACE_SESSION_ID"] hasPrefix:@"test-"]) { [pool drain]; return 1; }
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(@"Terminal") host:@""];
      [connection setRequestTimeout:10]; [connection setReplyTimeout:10];
      id controller = [[connection rootProxy] delegate];
      id windows = [[controller valueForKey:@"windows"] allValues];
      if ([windows count] != 1) { [pool drain]; return 1; }
      id terminal = [windows objectAtIndex:0], text = [terminal valueForKey:@"tView"];
      NSString *kind = [NSString stringWithUTF8String:argv[2]];
      if ([kind isEqual:@"start"]) {
        [text insertText:@"sleep 600\n"];
        output = [NSDictionary dictionaryWithObject:@YES forKey:@"started"];
      } else if ([kind isEqual:@"program"]) {
        output = [NSDictionary dictionaryWithObject:@([(id<TerminalArtwork>)text isUserProgramRunning]) forKey:@"running"];
      } else {
        id view = nil; NSWindow *panel = nil;
        BOOL mini = [kind isEqual:@"output"];
        if (mini) {
          if (![[terminal window] isMiniaturized]) [[terminal window] miniaturize:nil];
          if (![terminal valueForKey:@"miniIconView"]) [(id<TerminalArtwork>)terminal updateTitleBar:nil];
          view = [terminal valueForKey:@"miniIconView"]; panel = [view window];
        } else if ([kind isEqual:@"mach"]) {
          id info = [controller valueForKey:@"infoPanel"];
          if (!info || ![[info valueForKey:@"panel"] isVisible]) {
            [(id<TerminalArtwork>)controller openInfoPanel:nil];
            info = [controller valueForKey:@"infoPanel"];
          }
          [[info valueForKey:@"iconTimer"] setFireDate:[NSDate distantFuture]];
          if (![info valueForKey:@"animationTimer"]) [(id<TerminalArtwork>)info animateAppIcon];
          [[info valueForKey:@"animationTimer"] setFireDate:[NSDate distantFuture]];
          view = [info valueForKey:@"machView"]; panel = [info valueForKey:@"panel"];
        }
        if (!view || !panel) { [pool drain]; return 1; }
        NSInteger position = argc > 3 ? atoi(argv[3]) : -1;
        if (position < -1 || position > 12) { [pool drain]; return 1; }
        [(id<TerminalArtwork>)view setIsAnimates:position != -1];
        if (position >= 0) [view setValue:@(position) forKey:@"yPosition"];
        CGFloat before = [[view valueForKey:@"yPosition"] doubleValue];
        [(id<TerminalArtwork>)view animate]; [panel flushWindow];
        NSSize size = [[view valueForKey:@"iconImage"] size], frame = [view bounds].size;
        NSRect scroll = [[view valueForKey:@"scrollingRect"] rectValue];
        NSPoint origin = NSMakePoint((frame.width-size.width)/2,(frame.width-size.height)/2-(mini ? 5.5 : 0));
        NSRect destination = [view convertRect:NSOffsetRect(scroll,origin.x,origin.y) toView:nil];
        NSImage *image = [view valueForKey:@"scrollingImage"];
        CGFloat after = [[view valueForKey:@"yPosition"] doubleValue];
        CGFloat drawn = (before == 0 || before == 5) ? [image size].height-scroll.size.height : before;
        output = [NSDictionary dictionaryWithObjectsAndKeys:kind,@"kind",@(mini),@"mini",@(panel.windowNumber),@"window",
          @(position),@"requested_position",@(drawn),@"source_y",@(after),@"next_position",
          [view valueForKey:@"isAnimates"],@"animates",bitmapSizes(view,@"scrollingImage"),@"representations",
          [NSArray arrayWithObjects:@([image size].width),@([image size].height),nil],@"logical",
          [NSArray arrayWithObjects:@(destination.origin.x),@(destination.origin.y),@(destination.size.width),@(destination.size.height),nil],@"destination",
          [NSString stringWithString:[image valueForKey:@"fileName"] ?: @""],@"resource",
          @([(id<TerminalArtwork>)text isUserProgramRunning]),@"program_running",nil];
      }
    } else if (([mode isEqual:@"--application-logo"] || [mode isEqual:@"--application-footer"]) && argc > 2) {
      if (![[[[NSProcessInfo processInfo] environment] objectForKey:@"NEXTSPACE_SESSION_ID"] hasPrefix:@"test-"]) { [pool drain]; return 1; }
      NSString *name = [NSString stringWithUTF8String:argv[2]];
      if (![name isEqual:@"Terminal"] && ![name isEqual:@"Preferences"]) { [pool drain]; return 1; }
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(name) host:@""];
      [connection setRequestTimeout:10]; [connection setReplyTimeout:10];
      id app = [connection rootProxy], controller = [app delegate], view = nil;
      NSWindow *panel = nil;
      NSString *imageKey = @"image";
      BOOL terminal = [name isEqual:@"Terminal"];
      BOOL footer = [mode isEqual:@"--application-footer"];
      if (footer && !terminal) { [pool drain]; return 1; }
      if (terminal) {
        [(id<TerminalArtwork>)controller openInfoPanel:nil];
        id info = [controller valueForKey:@"infoPanel"];
        panel = [info valueForKey:@"panel"]; view = [info valueForKey:@"machView"];
        [[info valueForKey:@"iconTimer"] setFireDate:[NSDate distantFuture]];
        [[info valueForKey:@"animationTimer"] setFireDate:[NSDate distantFuture]];
        [(id<TerminalArtwork>)view setIsAnimates:NO];
        imageKey = @"iconImage";
      } else {
        [(id<InfoArtwork>)controller showInfoPanel:nil];
        panel = [controller valueForKey:@"infoPanel"];
        NSMutableArray *logos = [NSMutableArray array];
        imageViewsOfSize([panel contentView],NSMakeSize(48,48),logos);
        if ([logos count] != 1) { [pool drain]; return 1; }
        view = [logos objectAtIndex:0];
      }
      if (footer) {
        NSMutableArray *views = [NSMutableArray array];
        imageViewsOfSize([panel contentView],NSMakeSize(128,10),views);
        if ([views count] != 1) { [pool drain]; return 1; }
        view = [views objectAtIndex:0]; imageKey = @"image";
      }
      if (!view || !panel) { [pool drain]; return 1; }
      NSImage *image = [view valueForKey:imageKey]; NSSize size = [image size];
      NSRect bounds = [view bounds], rect;
      if (terminal && !footer) {
        rect = [view convertRect:NSMakeRect((bounds.size.width-size.width)/2,
          (bounds.size.width-size.height)/2,size.width,size.height) toView:nil];
      } else rect = focusedImageRect(view,bounds,size,[view imageScaling],[view imageAlignment]);
      NSRect visible = [view convertRect:[view visibleRect] toView:nil];
      [panel display]; [panel flushWindow];
      NSMutableDictionary *result = [NSMutableDictionary dictionaryWithObjectsAndKeys:
        name,@"name",@(panel.windowNumber),@"window",bitmapSizes(view,imageKey),@"representations",
        [NSArray arrayWithObjects:@(size.width),@(size.height),nil],@"logical",
        [NSArray arrayWithObjects:@(rect.origin.x),@(rect.origin.y),@(rect.size.width),@(rect.size.height),nil],@"base",
        [NSArray arrayWithObjects:@(visible.origin.x),@(visible.origin.y),@(visible.size.width),@(visible.size.height),nil],@"visible",
        [NSString stringWithString:[image valueForKey:@"fileName"] ?: @""],@"resource",
        @NO,@"selected",@NO,@"dimmed",
        @(terminal),@"animation_frozen_for_capture",nil];
      if (!terminal) {
        id clock = [controller valueForKey:@"clockView"]; NSRect frame = [clock frame];
        [result setObject:[NSString stringWithString:[clock className]] forKey:@"clock_class"];
        [result setObject:@([(id<ClockArtwork>)clock isAlive]) forKey:@"clock_alive"];
        [result setObject:@([[clock window] windowNumber]) forKey:@"clock_window"];
        [result setObject:[NSArray arrayWithObjects:@(frame.size.width),@(frame.size.height),nil] forKey:@"clock_logical"];
      }
      output = result;
    } else if ([mode isEqual:@"--workspace-recycler"]) {
      if (![[[[NSProcessInfo processInfo] environment] objectForKey:@"NEXTSPACE_SESSION_ID"] hasPrefix:@"test-"]) { [pool drain]; return 1; }
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(@"Workspace") host:@""];
      [connection setRequestTimeout:10]; [connection setReplyTimeout:10];
      id controller = [(id)[connection rootProxy] delegate];
      id recycler = [controller valueForKey:@"recycler"];
      NSWindow *window = [recycler valueForKey:@"appIcon"];
      id view = [recycler valueForKey:@"appIconView"];
      id cell = [view valueForKey:@"_imageCell"];
      NSSize logical = [[cell image] size];
      if (!view || logical.width <= 0 || logical.height <= 0) { [pool drain]; return 1; }
      NSRect rect = focusedImageRect(view,[cell drawingRectForBounds:[view bounds]],logical,
        NSImageScaleNone,NSImageAlignCenter);
      NSInteger count = [[recycler valueForKey:@"itemsCount"] integerValue];
      [window display]; [window flushWindow];
      output = [NSDictionary dictionaryWithObjectsAndKeys:
        iconArtwork(view,@"_imageCell.image",rect,count ? @"RecyclerFull" : @"RecyclerEmpty",NO,NO),@"image",
        @(window.windowNumber),@"window",@(count),@"items_count",
        [NSString stringWithString:[[recycler valueForKey:@"badge"] stringValue]],@"badge",
        [NSString stringWithString:[recycler valueForKey:@"path"]],@"storage",nil];
    } else if (([mode isEqual:@"--workspace-folders"] && argc > 2) || [mode isEqual:@"--workspace-home"] || [mode isEqual:@"--workspace-root"]) {
      if (![[[[NSProcessInfo processInfo] environment] objectForKey:@"NEXTSPACE_SESSION_ID"] hasPrefix:@"test-"]) { [pool drain]; return 1; }
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(@"Workspace") host:@""];
      [connection setRequestTimeout:10]; [connection setReplyTimeout:10];
      id proxy = [connection rootProxy];
      id controller = [proxy delegate];
      if (!controller) { fprintf(stderr,"Directory probe has no controller: connection=%p valid=%d proxy=%p\n",connection,[connection isValid],proxy); [pool drain]; return 1; }
      BOOL home = [mode isEqual:@"--workspace-home"];
      BOOL root = [mode isEqual:@"--workspace-root"];
      NSString *path = root ? @"/" : home ? [NSHomeDirectory() stringByDeletingLastPathComponent] : [NSString stringWithUTF8String:argv[2]];
      id viewer = nil;
      NSArray *viewers = [controller valueForKey:@"fileViewers"];
      for (NSUInteger index = 0; index < [viewers count]; index++) {
        id candidate = [viewers objectAtIndex:index];
        if ([[candidate valueForKey:@"rootPath"] isEqual:path] &&
            [[candidate valueForKeyPath:@"viewer.className"] isEqual:@"IconViewer"]) { viewer = candidate; break; }
      }
      if (!viewer) {
        viewer = [(id<FolderArtwork>)controller newViewerRootedAt:path viewer:@"Icon" isRoot:NO];
        [(id<FolderArtwork>)viewer displayPath:path selection:nil sender:controller];
      }
      if (!viewer) { fprintf(stderr,"Directory probe has no viewer: path=%s count=%lu\n",[path UTF8String],(unsigned long)[viewers count]); for (NSUInteger i=0;i<[viewers count];i++) { id v=[viewers objectAtIndex:i]; fprintf(stderr,"Viewer %lu root=%s type=%s\n",(unsigned long)i,[[v valueForKey:@"rootPath"] UTF8String],[[v valueForKeyPath:@"viewer.className"] UTF8String]); } [pool drain]; return 1; }
      NSWindow *window = [viewer valueForKey:@"window"];
      [window makeKeyAndOrderFront:nil];
      id icons = root ? [viewer valueForKey:@"pathView"] : [[viewer valueForKey:@"viewer"] valueForKey:@"iconView"];
      [(id<FolderArtwork>)icons selectIcons:nil];
      NSMutableArray *images = [NSMutableArray array];
      NSArray *entries = [icons valueForKey:@"icons"];
      NSString *phase = argc > 3 ? [NSString stringWithUTF8String:argv[3]] : @"closed";
      NSString *focusName = argc > 4 ? [NSString stringWithUTF8String:argv[4]] : nil;
      NSDragOperation dragMask = NSDragOperationNone;
      for (NSUInteger index = 0; index < [entries count]; index++) {
        NSView *icon = [entries objectAtIndex:index];
        if (![icon respondsToSelector:@selector(iconImage)]) continue;
        if (focusName && ![[icon valueForKey:@"labelString"] isEqual:focusName]) continue;
        if (root) {
          id paths = [icon valueForKey:@"paths"];
          if ([paths count] != 1 || ![[paths objectAtIndex:0] isEqual:@"/"]) continue;
        }
        if (home && ![[icon valueForKey:@"labelString"] isEqual:[NSHomeDirectory() lastPathComponent]]) continue;
        if (home || root || focusName) [icon scrollRectToVisible:[icon bounds]];
        if ([[icon valueForKey:@"labelString"] isEqual:@"ClosedFolder"]) {
          dragMask = [[icon valueForKey:@"draggingMask"] unsignedIntegerValue];
        }
        NSImage *image = [icon valueForKey:@"iconImage"];
        if (!image) continue;
        NSSize logical = [image size], frame = [icon frame].size;
        NSRect rect = [icon convertRect:NSMakeRect(roundf((frame.width-logical.width)/2),
          roundf((frame.height-logical.height)/2),logical.width,logical.height) toView:nil];
        [images addObject:iconArtwork(icon,@"iconImage",rect,
          root ? @"Root" : [NSString stringWithString:[icon valueForKey:@"labelString"]],
          [[icon valueForKey:@"selected"] boolValue],[[icon valueForKey:@"dimmed"] boolValue])];
      }
      [window display]; [window flushWindow];
      output = [NSDictionary dictionaryWithObjectsAndKeys:images,@"images",@(window.windowNumber),@"window",path,@"root",phase,@"phase",@(dragMask),@"drag_mask",nil];
    } else if ([mode isEqual:@"--workspace-preference-images"] && argc>2) {
      if (![[[[NSProcessInfo processInfo] environment] objectForKey:@"NEXTSPACE_SESSION_ID"] hasPrefix:@"test-"]) { [pool drain];return 1; }
      NSConnection *connection=[NSConnection connectionWithRegisteredName:GSSessionServiceName(@"Workspace") host:@""];
      [connection setRequestTimeout:10];[connection setReplyTimeout:10];
      id app=[connection rootProxy], controller=[app delegate];
      NSString *name=[NSString stringWithUTF8String:argv[2]];
      [controller showPrefsPanel:nil];id prefs=[controller valueForKey:@"preferences"];
      id<PreferenceFixturePopup> popup=[prefs valueForKey:@"popup"];id module=nil;
      id previous=[[popup valueForKey:@"selectedItem"] representedObject];
      [(NSDistantObject *)popup setProtocolForProxy:@protocol(PreferenceFixturePopup)];
      NSMutableArray *modules=[NSMutableArray array];
      for (NSInteger i=0;i<[popup numberOfItems];i++) {
        id item=[popup itemAtIndex:i], candidate=[item representedObject];
        NSString *kind=[NSString stringWithString:[candidate className]];
        [modules addObject:kind];
        if ([kind isEqual:name]) { [popup selectItemAtIndex:i];module=candidate; }
      }
      [(NSDistantObject *)popup setProtocolForProxy:nil];
      if (!module) { output=@{@"modules":modules}; }
      else {
        if (![previous isEqual:module]) [prefs switchModule:popup];
        NSView *view=[module view];NSWindow *window=[prefs valueForKey:@"panel"];
        [app activateIgnoringOtherApps:YES];[window makeKeyAndOrderFront:nil];
        NSMutableArray *pending=[NSMutableArray arrayWithObject:view], *images=[NSMutableArray array];
        while ([pending count]) {
          id candidate=[[[pending lastObject] retain] autorelease];[pending removeLastObject];
          if ([candidate isKindOfClass:[NSImageView class]] && [candidate image]) {
            NSImage *image=[candidate image];NSSize logical=[image size];id cell=[candidate cell];
            NSRect rect=focusedImageRect(candidate,[cell drawingRectForBounds:[candidate bounds]],logical,
              [cell imageScaling],[cell imageAlignment]);
            NSMutableDictionary *entry=[NSMutableDictionary dictionaryWithDictionary:
              imageArtwork(candidate,@"image",candidate,rect,[NSString stringWithString:[candidate className]],NO,NO)];
            NSRect frame=[candidate convertRect:[candidate bounds] toView:nil];
            [entry setObject:@[@(frame.origin.x),@(frame.origin.y),@(frame.size.width),@(frame.size.height)] forKey:@"view_base"];
            if ([[NSString stringWithString:[candidate className]] isEqual:@"NXTSizer"]) {
              for (NSString *key in @[@"leftArr",@"rightArr"]) {
                if ([name isEqual:@"BrowserPrefs"] && [key isEqual:@"leftArr"]) continue;
                if ([candidate isEqual:[module valueForKey:key]]) [entry setObject:key forKey:@"outlet"];
              }
            }
            [images addObject:entry];
          }
          id children=[candidate subviews];
          for (NSUInteger i=0;i<[children count];i++) [pending addObject:[children objectAtIndex:i]];
        }
        [window display];[window flushWindow];
        NSMutableDictionary *state=[NSMutableDictionary dictionaryWithDictionary:
          @{@"modules":modules,@"module":name,@"window":@([window windowNumber]),@"images":images}];
        if (![name isEqual:@"FileCopyPrefs"]) {
          id button=[module valueForKey:@"button"];NSRect frame=[button convertRect:[button bounds] toView:nil];
          [state setObject:@[@(frame.origin.x),@(frame.origin.y),@(frame.size.width),@(frame.size.height)] forKey:@"revert_button"];
          [state setObject:@([button isEnabled]) forKey:@"revert_enabled"];
        }
        output=state;
      }
    } else if ([mode isEqual:@"--workspace-bg-mini"] && argc>3) {
      if (![[[[NSProcessInfo processInfo] environment] objectForKey:@"NEXTSPACE_SESSION_ID"] hasPrefix:@"test-"]) { [pool drain];return 1; }
      NSConnection *connection=[NSConnection connectionWithRegisteredName:GSSessionServiceName(@"Workspace") host:@""];
      [connection setRequestTimeout:10];[connection setReplyTimeout:10];
      id app=[connection rootProxy], controller=[app delegate];
      NSString *path=[NSString stringWithUTF8String:argv[2]], *action=[NSString stringWithUTF8String:argv[3]];
      NSString *kind=argc>4 ? [NSString stringWithUTF8String:argv[4]] : @"Copy";
      BOOL media=[@[@"Mount",@"Unmount",@"Eject"] containsObject:kind];
      int operationType=[kind isEqual:@"Copy"] ? 1 : [kind isEqual:@"Move"] ? 3 : [kind isEqual:@"Link"] ? 4 : media ? 7 : 0;
      if (!operationType) { [pool drain];return 1; }
      [controller showProcesses:nil];id panel=[controller processesPanel], manager=[panel valueForKey:@"manager"];
      if ([action isEqual:@"start"]) {
        if ([[manager operations] count]) { [pool drain];return 1; }
        if (!media) {
          [(NSDistantObject *)manager setProtocolForProxy:@protocol(BGFixtureManager)];
          [(id<BGFixtureManager>)manager startOperationWithType:operationType source:[path stringByAppendingPathComponent:@"source"] target:[path stringByAppendingPathComponent:@"target"] files:@[@"first.txt"]];
          [(NSDistantObject *)manager setProtocolForProxy:nil];
        }
      }
      if (media && ([action isEqual:@"start"] || [action isEqual:@"cancel"])) {
        // Exercise the notification consumer and Mounter view without a device operation.
        NSNotification *notification=[NSNotification notificationWithName:@"NextSpaceArtworkMediaFixture" object:nil
          userInfo:@{@"Operation":kind,@"ID":@"artwork-owned",@"Success":@"true",
            @"UNIXDevice":@"/dev/nextspace-artwork-fixture",@"Title":@"Owned media artwork fixture",@"Message":@""}];
        [(NSDistantObject *)controller setProtocolForProxy:@protocol(MediaArtworkFixture)];
        if ([action isEqual:@"start"]) [(id<MediaArtworkFixture>)controller mediaOperationDidStart:notification];
        else [(id<MediaArtworkFixture>)controller mediaOperationDidEnd:notification];
        [(NSDistantObject *)controller setProtocolForProxy:nil];
      }
      id operations=[manager operations], operation=[operations firstObject];
      if (!media && [action isEqual:@"cancel"] && operation) [operation stop:nil];
      // KVC preserves operation enum types across the distributed connection.
      NSMutableDictionary *state=[NSMutableDictionary dictionaryWithDictionary:@{@"operation_count":@([operations count]),@"state":@([[operation valueForKey:@"state"] intValue])}];
      if (operation && ![action isEqual:@"cancel"]) {
        [panel setView:operation];id table=[panel valueForKey:@"backList"], columns=[table tableColumns], cell=nil;NSUInteger column=0;
        for (;column<[columns count];column++) {
          cell=[[columns objectAtIndex:column] dataCell];
          if ([cell isKindOfClass:[NSImageCell class]]) break;
        }
        NSCAssert(column<[columns count],@"Real background operation image column");
        NSWindow *window=[panel window];[app activateIgnoringOtherApps:YES];[window makeKeyAndOrderFront:nil];[table display];[window display];[window flushWindow];
        NSImage *image=[cell image];NSSize logical=[[image valueForKey:@"size"] sizeValue];
        NSRect frame=[cell drawingRectForBounds:[table frameOfCellAtColumn:column row:0]];
        NSRect rect=focusedImageRect(table,frame,logical,[cell imageScaling],[cell imageAlignment]);
        NSDictionary *view=imageArtwork(cell,@"image",table,rect,media ? @"MiniDisk" : [@"Mini" stringByAppendingString:kind],NO,NO);
        id ui=[operation valueForKey:@"userInterface"], alertView=[ui valueForKey:@"alertBox"];
        NSMutableArray *pending=[NSMutableArray array];
        if (alertView) [pending addObject:alertView];
        while ([pending count]) {
          id candidate=[[[pending lastObject] retain] autorelease];[pending removeLastObject];
          if ([candidate isKindOfClass:[NSButton class]] && [[NSString stringWithString:[candidate title]] isEqual:@"Stop"]) {
            NSRect frame=[candidate convertRect:[candidate bounds] toView:nil];
            [state setObject:@[@(frame.origin.x),@(frame.origin.y),@(frame.size.width),@(frame.size.height)] forKey:@"stop_button"];
          }
          id children=[candidate subviews];
          for (NSUInteger i=0;i<[children count];i++) [pending addObject:[children objectAtIndex:i]];
        }
        [state addEntriesFromDictionary:@{@"window":@([window windowNumber]),@"image":view,@"type":@([[operation valueForKey:@"type"] intValue]),@"title":[NSString stringWithString:[operation titleString]],@"class":[NSString stringWithString:[operation className]]}];
      }
      if (media) {
        [state setObject:@NO forKey:@"kernel_device_operation_requested"];
        if (operation) [state setObject:[NSString stringWithString:[operation valueForKey:@"source"]] forKey:@"source"];
      } else if (operation) [state setObject:@([[operation valueForKey:@"fileMoverTask"] processIdentifier]) forKey:@"worker_pid"];
      output=state;
    } else if ([mode isEqual:@"--workspace-embedded-images"] && argc > 3) {
      if (![[[[NSProcessInfo processInfo] environment] objectForKey:@"NEXTSPACE_SESSION_ID"] hasPrefix:@"test-"]) { [pool drain]; return 1; }
      NSConnection *connection=[NSConnection connectionWithRegisteredName:GSSessionServiceName(@"Workspace") host:@""];
      [connection setRequestTimeout:10];[connection setReplyTimeout:10];
      id app=[connection rootProxy]; id controller=[app delegate];
      NSString *path=[NSString stringWithUTF8String:argv[2]], *kind=[NSString stringWithUTF8String:argv[3]];
      id button=nil, finderState=nil, attributesState=nil;
      if ([kind hasPrefix:@"finder"]) {
        if ([kind isEqual:@"finder-setup"]) { [[[controller valueForKey:@"inspectorPanel"] valueForKey:@"window"] orderOut:nil]; [app activateIgnoringOtherApps:YES]; [(id<EmbeddedImages>)controller showFinder:nil]; }
        id finder=finderState=[controller valueForKey:@"finder"];
        if ([kind isEqual:@"finder-setup"]) {
          [(id<EmbeddedImages>)finder finishFind];
          id shelf=[finder valueForKey:@"shelf"];
          id icons=[[shelf selectedIcons] allObjects];
          if (![icons count]) { [pool drain];return 1; }
          id icon=[icons objectAtIndex:0];
          [(NSDistantObject *)icon setProtocolForProxy:@protocol(FinderFixtureIcon)];
          [(id<FinderFixtureIcon>)icon setPaths:@[path]];
          [(NSDistantObject *)icon setProtocolForProxy:nil];
          [[finder valueForKey:@"window"] makeFirstResponder:nil];
          id field=[finder valueForKey:@"findField"];
          [(NSDistantObject *)field setProtocolForProxy:@protocol(FinderFixtureField)];
          [(id<FinderFixtureField>)field setStringValue:@"^first[.]txt$"];
          [(NSDistantObject *)field setProtocolForProxy:nil];
          [[finder valueForKey:@"findScopeButton"] selectItemWithTag:0];
        }
        id queue=[finder valueForKey:@"operationQ"];
        if ([kind isEqual:@"finder-pause"] || [kind isEqual:@"finder-resume"]) {
          if (!queue) { [pool drain];return 1; }
          [queue setSuspended:[kind isEqual:@"finder-pause"]];
        }
        button=[finder valueForKey:@"findButton"];
      } else {
        if (![kind isEqual:@"compute-state"]) {
        id viewer=nil;
        id viewers=[controller valueForKey:@"fileViewers"];
        for (NSUInteger i=0;i<[viewers count];i++) {
          id candidate=[viewers objectAtIndex:i];
          if ([[candidate valueForKey:@"rootPath"] isEqual:path]) { viewer=candidate;break; }
        }
        if (!viewer) viewer=[(id<FolderArtwork>)controller newViewerRootedAt:path viewer:@"Icon" isRoot:NO];
        [[viewer valueForKey:@"window"] makeKeyAndOrderFront:nil];
        [(NSDistantObject *)viewer setProtocolForProxy:@protocol(SelectionViewer)];
        [(id<SelectionViewer>)viewer displayPath:@"/" selection:@[[kind isEqual:@"compute-folder"] ? @"Folder" : @"first.txt"] sender:controller];
        [(NSDistantObject *)viewer setProtocolForProxy:nil];
        [(id<SelectionArtwork>)controller showAttributesInspector:nil];
        }
        id panel=[controller valueForKey:@"inspectorPanel"];
        attributesState=[panel valueForKey:@"currentInspector"];
        button=[attributesState valueForKey:@"computeSizeBtn"];
      }
      NSWindow *window=[button window];[window makeKeyAndOrderFront:nil];[window display];[window flushWindow];
      NSSize logical=[[button valueForKeyPath:@"cell._cell_image.size"] sizeValue];
      NSRect buttonBase=[button convertRect:[button bounds] toView:nil];
      if (argc>4) {
        NSData *pixels=[button valueForKeyPath:@"cell._cell_image.TIFFRepresentation"];
        NSCAssert([pixels writeToFile:[NSString stringWithUTF8String:argv[4]] atomically:YES],@"Export live image");
      }
      NSMutableArray *results=[NSMutableArray array], *scope=[NSMutableArray array];
      if (finderState) {
        id items=[finderState valueForKey:@"variantList"];
        for (NSUInteger i=0;i<[items count];i++) [results addObject:[NSString stringWithString:[items objectAtIndex:i]]];
        id icons=[[[finderState valueForKey:@"shelf"] selectedIcons] allObjects];
        for (NSUInteger i=0;i<[icons count];i++) {
          id paths=[[icons objectAtIndex:i] valueForKey:@"paths"];
          for (NSUInteger j=0;j<[paths count];j++) [scope addObject:[NSString stringWithString:[paths objectAtIndex:j]]];
        }
      }
      output=@{@"kind":kind,@"application_active":@([app isActive]),@"button_action":NSStringFromSelector([button action]) ?: @"",@"button_target_class":[button target] ? [NSString stringWithString:[[button target] className]] : @"",@"window_key":@([window isKeyWindow]),@"window_main":@([window isMainWindow]),@"window":@([window windowNumber]),@"enabled":@([button isEnabled]),
        @"logical":@[@(logical.width),@(logical.height)],@"representations":bitmapSizes(button,@"cell._cell_image"),
        @"alternate_representations":bitmapSizes(button,@"alternateImage"),
        @"resource":[NSString stringWithString:[button valueForKeyPath:@"cell._cell_image.fileName"] ?: @""],
        @"button_base":@[@(buttonBase.origin.x),@(buttonBase.origin.y),@(buttonBase.size.width),@(buttonBase.size.height)],
        @"image":buttonImageArtwork(button,kind),
        @"size_text":attributesState ? [NSString stringWithString:[attributesState valueForKeyPath:@"fileSizeField.stringValue"]] : @"",
        @"size_pending":@(attributesState && [attributesState valueForKey:@"sizer"]!=nil),
        @"find_text":finderState ? [NSString stringWithString:[finderState valueForKeyPath:@"findField.stringValue"]] : @"",
        @"search_scope":@([[[finderState valueForKey:@"findScopeButton"] selectedItem] tag]),
        @"queue_exists":@([finderState valueForKey:@"operationQ"]!=nil),
        @"queue_count":@([[finderState valueForKey:@"operationQ"] operationCount]),
        @"queue_suspended":@([[finderState valueForKey:@"operationQ"] isSuspended]),
        @"results":results,@"scope_paths":scope,@"image_position":@([[button cell] imagePosition]),@"image_only":@([[button cell] imagePosition]==NSImageOnly),@"image_above":@([[button cell] imagePosition]==NSImageAbove)};
    } else if ([mode isEqual:@"--workspace-permissions"] && argc > 3) {
      if (![[[[NSProcessInfo processInfo] environment] objectForKey:@"NEXTSPACE_SESSION_ID"] hasPrefix:@"test-"]) { [pool drain]; return 1; }
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(@"Workspace") host:@""];
      [connection setRequestTimeout:10]; [connection setReplyTimeout:10];
      id controller = [(id)[connection rootProxy] delegate];
      NSString *path = [NSString stringWithUTF8String:argv[2]];
      if ([[NSString stringWithUTF8String:argv[3]] isEqual:@"init"]) {
        id viewer = nil, viewers = [controller valueForKey:@"fileViewers"];
        for (NSUInteger i=0; i<[viewers count]; i++) {
          id candidate = [viewers objectAtIndex:i];
          if ([[candidate valueForKey:@"rootPath"] isEqual:path]) { viewer=candidate; break; }
        }
        if (!viewer) viewer = [(id<FolderArtwork>)controller newViewerRootedAt:path viewer:@"Icon" isRoot:NO];
        if (!viewer) { [pool drain]; return 1; }
        [[viewer valueForKey:@"window"] makeKeyAndOrderFront:nil];
        [(NSDistantObject *)viewer setProtocolForProxy:@protocol(SelectionViewer)];
        [(id<SelectionViewer>)viewer displayPath:@"/" selection:@[@"first.txt",@"second.txt"] sender:controller];
        [(NSDistantObject *)viewer setProtocolForProxy:nil];
        [(id<PermissionInspector>)controller showPermissionsInspector:nil];
      }
      id panel = [controller valueForKey:@"inspectorPanel"];
      id inspector = [panel valueForKey:@"currentInspector"];
      id view = [inspector valueForKey:@"permissionsView"];
      NSWindow *window = [view window];
      NSRect bounds = [view bounds], base = [view convertRect:bounds toView:nil];
      NSMutableArray *images = [NSMutableArray array];
      for (NSString *key in @[@"check",@"cross",@"dash"]) {
        id image = [view valueForKey:key];NSSize logical=[image size];
        [images addObject:@{@"key":key,@"resource":[NSString stringWithString:[image valueForKey:@"fileName"] ?: @""],
          @"representations":bitmapSizes(view,key),@"logical":@[@(logical.width),@(logical.height)]}];
      }
      [window makeKeyAndOrderFront:nil];[view setNeedsDisplay:YES];[window display];[window flushWindow];
      output = @{@"window":@([window windowNumber]),@"view_class":[NSString stringWithString:[view className]],
        @"view":@[@(base.origin.x),@(base.origin.y),@(base.size.width),@(base.size.height)],
        @"mode":[view valueForKey:@"mode"],@"nochange":[view valueForKey:@"noChangeMask"],
        @"displays_execute":[view valueForKey:@"displaysExecute"],@"editable":[view valueForKey:@"isEditable"],@"images":images};
    } else if ([mode isEqual:@"--workspace-selection"] && argc > 3) {
      if (![[[[NSProcessInfo processInfo] environment] objectForKey:@"NEXTSPACE_SESSION_ID"] hasPrefix:@"test-"]) { [pool drain]; return 1; }
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(@"Workspace") host:@""];
      [connection setRequestTimeout:10]; [connection setReplyTimeout:10];
      id controller = [(id)[connection rootProxy] delegate];
      NSString *path = [NSString stringWithUTF8String:argv[2]];
      BOOL inspector = [[NSString stringWithUTF8String:argv[3]] isEqual:@"inspector"];
      id viewer = nil, viewers = [controller valueForKey:@"fileViewers"];
      for (NSUInteger i=0; i<[viewers count]; i++) {
        id candidate = [viewers objectAtIndex:i];
        if ([[candidate valueForKey:@"rootPath"] isEqual:path]) { viewer=candidate; break; }
      }
      if (!viewer) viewer = [(id<FolderArtwork>)controller newViewerRootedAt:path viewer:@"Icon" isRoot:NO];
      if (!viewer) { [pool drain]; return 1; }
      NSWindow *window = [viewer valueForKey:@"window"];
      [window makeKeyAndOrderFront:nil];
      [(NSDistantObject *)viewer setProtocolForProxy:@protocol(SelectionViewer)];
      [(id<SelectionViewer>)viewer displayPath:@"/" selection:@[@"first.txt",@"second.txt"] sender:controller];
      [(NSDistantObject *)viewer setProtocolForProxy:nil];
      if ([[viewer valueForKey:@"selection"] count] != 2) { [pool drain]; return 1; }
      NSDictionary *image = nil, *highlight = nil;
      if (inspector) {
        [(id<SelectionArtwork>)controller showAttributesInspector:nil];
        id panel = [controller valueForKey:@"inspectorPanel"];
        id button = [panel valueForKey:@"fileIconButton"], cell = [button cell];
        window = [panel valueForKey:@"window"];
        NSSize size = [[cell valueForKeyPath:@"_cell_image.size"] sizeValue];
        NSRect rect = focusedImageRect(button,[cell drawingRectForBounds:[button bounds]],size,
          [cell imageScaling],NSImageAlignCenter);
        NSRect visible = [button convertRect:[button visibleRect] toView:nil];
        image = @{ @"name":@"MultipleSelection", @"logical":@[@(size.width),@(size.height)],
          @"resource":[NSString stringWithString:[cell valueForKeyPath:@"_cell_image.fileName"] ?: @""],
          @"representations":bitmapSizes(cell,@"_cell_image"),
          @"base":@[@(rect.origin.x),@(rect.origin.y),@(rect.size.width),@(rect.size.height)],
          @"visible":@[@(visible.origin.x),@(visible.origin.y),@(visible.size.width),@(visible.size.height)],
          @"selected":@NO,@"dimmed":@NO,@"pixel_aligned_destination_clip":@NO };
      } else {
        id icon = [viewer valueForKeyPath:@"pathView._multiIcon"];
        [icon scrollRectToVisible:[icon bounds]];
        NSSize size = [[icon valueForKeyPath:@"iconImage.size"] sizeValue], frame = [icon frame].size;
        NSRect rect = [icon convertRect:NSMakeRect(roundf((frame.width-size.width)/2),
          roundf((frame.height-size.height)/2),size.width,size.height) toView:nil];
        image = iconArtwork(icon,@"iconImage",rect,@"MultipleSelection",[[icon valueForKey:@"selected"] boolValue],[[icon valueForKey:@"dimmed"] boolValue]);
        rect = [icon convertRect:NSMakeRect(roundf((frame.width-66)/2),roundf((frame.height-52)/2),66,52) toView:nil];
        highlight = @{ @"base":@[@(rect.origin.x),@(rect.origin.y),@(rect.size.width),@(rect.size.height)] };
      }
      [window display]; [window flushWindow];
      output = @{ @"window":@(window.windowNumber), @"selection_count":@2, @"image":image,
        @"phase":inspector ? @"inspector" : @"path", @"highlight":highlight ?: @{} };
    } else if ([mode isEqual:@"--workspace-processes"] && argc > 2) {
      if (![[[[NSProcessInfo processInfo] environment] objectForKey:@"NEXTSPACE_SESSION_ID"] hasPrefix:@"test-"]) { [pool drain]; return 1; }
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(@"Workspace") host:@""];
      [connection setRequestTimeout:10]; [connection setReplyTimeout:10];
      id controller = [(id)[connection rootProxy] delegate];
      [(id<ProcessesArtwork>)controller showProcesses:nil];
      id panel = [controller valueForKey:@"procPanel"];
      id applications = [[controller valueForKey:@"procManager"] valueForKey:@"applications"];
      NSString *name = [NSString stringWithUTF8String:argv[2]];
      NSInteger row = -1;
      for (NSUInteger index=0; index<[applications count]; index++)
        if ([[[applications objectAtIndex:index] objectForKey:@"NSApplicationName"] isEqual:name]) { row=index; break; }
      if (row < 0) { [pool drain]; return 1; }
      [[panel valueForKey:@"appList"] selectRow:row byExtendingSelection:NO];
      [(id<ProcessesArtwork>)panel showApp:nil];
      id button = [panel valueForKey:@"appKillBtn"], cell = [button cell];
      NSWindow *window = [panel valueForKey:@"procWindow"];
      // NSButtonCell draws _cell_image even when its title keeps NSTextCellType;
      // NSCell's public image getter returns nil in that case.
      NSString *imageKey = @"_cell_image";
      if (argc > 3) {
        NSData *pixels = [cell valueForKeyPath:@"_cell_image.TIFFRepresentation"];
        NSCAssert([pixels writeToFile:[NSString stringWithUTF8String:argv[3]] atomically:YES], @"Export the live button image");
      }
      NSSize titleSize = [[cell valueForKeyPath:@"attributedTitle.size"] sizeValue];
      NSDictionary *image = buttonImageArtwork(button,@"KillApplication");
      [window makeKeyAndOrderFront:nil]; [window display]; [window flushWindow];
      output = @{ @"window":@(window.windowNumber), @"application":name,
        @"enabled":@([button isEnabled]), @"hidden":@([button isHidden]),
        @"title_height":@(titleSize.height), @"flipped":@([button isFlipped]), @"image":image };
    } else if ([mode isEqual:@"--workspace-hide-others"]) {
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(@"Workspace") host:@""];
      [connection setRequestTimeout:10]; [connection setReplyTimeout:10];
      id controller = [(id)[connection rootProxy] delegate];
      if (!controller) { [pool drain]; return 1; }
      [controller hideOtherApplications];
      output = [NSDictionary dictionaryWithObject:[NSNumber numberWithBool:YES] forKey:@"requested"];
    } else if ([mode isEqual:@"--application-state"] || [mode isEqual:@"--application-action"]) {
      if (argc < 3) { [pool drain]; return 1; }
      NSConnection *connection = [NSConnection connectionWithRegisteredName:
        GSSessionServiceName([NSString stringWithUTF8String:argv[2]]) host:@""];
      [connection setRequestTimeout:5]; [connection setReplyTimeout:5];
      id app = [connection rootProxy];
      if (!app) { [pool drain]; return 1; }
      NSInteger windowNumber = 0;
      BOOL modalWindow = NO;
      for (int index = 3; index + 1 < argc; index++)
        if (strcmp(argv[index], "--window-number") == 0) windowNumber = atoi(argv[index + 1]);
      for (int index = 3; index < argc; index++)
        if (strcmp(argv[index], "--modal-window") == 0) modalWindow = YES;
      id window = windowNumber ? [app windowWithWindowNumber:windowNumber] :
        (modalWindow ? [app modalWindow] : [app mainWindow]);
      if ([mode isEqual:@"--application-action"]) {
        if (argc < 4) { [pool drain]; return 1; }
        NSString *action = [NSString stringWithUTF8String:argv[3]];
        if ([action isEqual:@"hide"]) [app hide:nil];
        else if ([action isEqual:@"activate"]) [app activateIgnoringOtherApps:YES];
        else if ([action isEqual:@"deactivate"]) [app deactivate];
        else if ([action isEqual:@"normal-title"]) {
          // Non-keyable styles never receive the ordinary main-window transition.
          [window becomeMainWindow];
          [window resignMainWindow];
        }
        else if ([action isEqual:@"unhide"]) [app unhide:nil];
        else if ([action isEqual:@"zoom"]) [window zoom:nil];
        else if ([action isEqual:@"fullscreen"]) [window toggleFullScreen:nil];
        else if ([action isEqual:@"miniaturize"]) [window miniaturize:nil];
        else if ([action isEqual:@"deminiaturize"]) [window deminiaturize:nil];
        else if ([action isEqual:@"order-out"]) [window orderOut:nil];
        else if ([action isEqual:@"order-front"]) [window orderFront:nil];
        else if ([action isEqual:@"edited"]) [window setDocumentEdited:YES];
        else if ([action isEqual:@"clean"]) [window setDocumentEdited:NO];
        else if ([action isEqual:@"close-highlight"] || [action isEqual:@"close-unhighlight"] ||
                 [action isEqual:@"miniaturize-highlight"] || [action isEqual:@"miniaturize-unhighlight"]) {
          id button = [window standardWindowButton:[action hasPrefix:@"close-"] ?
            NSWindowCloseButton : NSWindowMiniaturizeButton];
          [button highlight:[action hasSuffix:@"-highlight"]];
          [button display];
        }
        else { [pool drain]; return 1; }
        [window displayIfNeeded];
        [window flushWindow];
      }
      output = [NSDictionary dictionaryWithObjectsAndKeys:[NSNumber numberWithBool:[app isActive]], @"active",
        windowNumber ? @"numbered" : (modalWindow ? @"modal" : @"main"), @"window_role",
        [NSNumber numberWithBool:[app isHidden]], @"hidden",
        [NSNumber numberWithBool:window ? [window isKeyWindow] : NO], @"key",
        [NSNumber numberWithBool:window ? [window isMainWindow] : NO], @"main",
        [NSNumber numberWithBool:[[[app mainMenu] window] isVisible]], @"menu_visible",
        [NSNumber numberWithInteger:window ? [window windowNumber] : 0], @"window_number",
        [NSNumber numberWithBool:window ? [window isZoomed] : NO], @"zoomed",
        [NSNumber numberWithBool:window ? [window isDocumentEdited] : NO], @"document_edited",
        window ? NSStringFromRect([window frame]) : @"", @"frame",
        window ? NSStringFromRect([window contentRectForFrameRect:[window frame]]) : @"", @"content_rect",
        window ? NSStringFromRect([[window contentView] frame]) : @"", @"content_view_frame",
        window ? NSStringFromRect([[window contentView] bounds]) : @"", @"content_view_bounds",
        window ? NSStringFromRect([[window screen] frame]) : @"", @"screen_frame",
        [NSNumber numberWithUnsignedInteger:window ? [window styleMask] : 0], @"style_mask",
        [NSNumber numberWithDouble:window ? [window backingScaleFactor] : 1], @"backing_scale",
        window ? NSStringFromRect([[window screen] visibleFrame]) : @"", @"visible_frame", nil];
    } else if ([mode isEqual:@"--display-state"] || [mode isEqual:@"--display-request"]) {
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(@"Workspace") host:@""];
      [connection setRequestTimeout:10]; [connection setReplyTimeout:10];
      id controller = [(id)[connection rootProxy] delegate];
      if (!controller) { [pool drain]; return 1; }
      id<OSESessionSettings> service = controller;
      NSDictionary *request = [NSDictionary dictionaryWithObject:@"state" forKey:@"action"];
      if ([mode isEqual:@"--display-request"]) {
        if (argc < 3) { [pool drain]; return 1; }
        NSData *bytes = [NSData dataWithContentsOfFile:[NSString stringWithUTF8String:argv[2]]];
        request = [NSJSONSerialization JSONObjectWithData:bytes options:0 error:NULL];
      }
      output = OSESessionSettingsRequest(service, request);
      if (!output) { [pool drain]; return 1; }
    } else if ([mode isEqual:@"--undocked"]) {
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(@"Workspace") host:@""];
      [connection setRequestTimeout:5]; [connection setReplyTimeout:5];
      id controller = [(id)[connection rootProxy] delegate];
      if (!controller) { [pool drain]; return 1; }
      NSArray *applications = [controller _undockedApplicationsList];
      NSMutableArray *values = [NSMutableArray array];
      NSUInteger index;
      for (index = 0; index < [applications count]; index++) {
        id entry = [applications objectAtIndex:index];
        [values addObject:[NSDictionary dictionaryWithObjectsAndKeys:[entry objectForKey:@"Name"], @"Name",
          [entry objectForKey:@"Command"], @"Command", nil]];
      }
      output = values;
    } else if ([mode isEqual:@"--desktop-preferences"]) {
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(@"Workspace") host:@""];
      [connection setRequestTimeout:10]; [connection setReplyTimeout:10];
      id controller = [(id)[connection rootProxy] delegate];
      if (!controller) { [pool drain]; return 1; }
      [controller showPrefsPanel:nil];
      id preferences = [controller valueForKey:@"preferences"];
      id popup = [preferences valueForKey:@"popup"];
      [popup selectItemWithTitle:@"Desktops"]; [preferences switchModule:popup];
      id module = [[popup selectedItem] representedObject];
      if (argc > 3 && strcmp(argv[2], "-GSWorkspaceApplication") != 0) {
        NSString *action = [NSString stringWithUTF8String:argv[2]];
        NSString *value = [NSString stringWithUTF8String:argv[3]];
        if ([action isEqual:@"name"]) {
          [[module valueForKey:@"nameField"] setStringValue:value]; [module changeName:nil];
        } else {
          id control = [module valueForKey:action];
          [control selectItemWithTag:[value integerValue]];
          if ([action isEqual:@"desktopsNumber"]) [module setWorkspaceQuantity:control];
          else if ([action isEqual:@"switchKey"]) [module setSwitchShortcut:control];
          else if ([action isEqual:@"directSwitchKey"]) [module setDirectSwitchShortcut:control];
          else { [pool drain]; return 1; }
        }
      }
      output = OSESessionSettingsRequest(controller, [NSDictionary dictionaryWithObject:@"desktop-settings" forKey:@"action"]);
    } else if ([mode isEqual:@"--dock-preferences"] || [mode isEqual:@"--dock-level"] || [mode isEqual:@"--dock-checkmark"]) {
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(@"Workspace") host:@""];
      [connection setRequestTimeout:5]; [connection setReplyTimeout:5];
      id controller = [(id)[connection rootProxy] delegate];
      if (!controller) { [pool drain]; return 1; }
      [controller showPrefsPanel:nil];
      id preferences = [controller valueForKey:@"preferences"];
      id popup = [preferences valueForKey:@"popup"];
      BOOL level = [mode isEqual:@"--dock-level"];
      BOOL hasValue = argc > 2 && strcmp(argv[2], "-GSWorkspaceApplication") != 0;
      [popup selectItemWithTitle:level ? @"Advanced" : @"Dock"];
      [preferences switchModule:popup];
      id module = [[popup selectedItem] representedObject];
      if (level) {
        id button = [module valueForKey:@"dockLevelBtn"];
        if (hasValue) {
          [button selectItemWithTag:atoi(argv[2])];
          [module setDockLevel:button];
        }
        output = [NSDictionary dictionaryWithObjectsAndKeys:
          [NSNumber numberWithInteger:[[button selectedItem] tag]], @"level",
          [NSNumber numberWithBool:[[[button menu] itemWithTag:-1000] isEnabled]], @"automatic_enabled", nil];
      } else if ([mode isEqual:@"--dock-checkmark"]) {
        NSTableView *table = [module valueForKey:@"appList"];
        NSArray *columns = [table tableColumns];
        NSInteger index = 0;
        while (index < [columns count] && ![[[columns objectAtIndex:index] identifier] isEqual:@"autostart"]) index++;
        NSCAssert(index < [columns count], @"The actual Dock autostart column exists");
        NSImage *image = [(id<DockCheckMarkSource>)module tableView:table objectValueForTableColumn:[columns objectAtIndex:index] row:0];
        NSCAssert(image != nil, @"Workspace's autostart image is present");
        NSSize size = [[image valueForKey:@"size"] sizeValue];
        NSRect rect = [table convertRect:[table frameOfCellAtColumn:index row:0] toView:nil];
        NSWindow *window = [table window];
        [window display]; [window flushWindow];
        output = @{@"window": @([window windowNumber]), @"name": [image name],
          @"logical_size": @[@(size.width), @(size.height)], @"scale": @([window backingScaleFactor]),
          @"cell": @[@(rect.origin.x), @(rect.origin.y), @(rect.size.width), @(rect.size.height)],
          @"content_height": @([[window contentView] frame].size.height)};
      } else {
        id table = [module valueForKey:@"appList"];
        [table selectRow:1 byExtendingSelection:NO];
        [module performSelector:@selector(appSettingsPanelUpdate)];
        id command = [module valueForKey:@"appCommandField"];
        id locked = [module valueForKey:@"appLockedBtn"];
        if (hasValue) {
          [command setStringValue:[NSString stringWithUTF8String:argv[2]]];
          [module setAppCommand:command];
          [locked setValue:[NSNumber numberWithInteger:NSOnState] forKey:@"state"];
          [module setAppLocked:locked];
        }
        output = [NSDictionary dictionaryWithObjectsAndKeys:
          [[module valueForKey:@"appNameField"] stringValue], @"name", [command stringValue], @"command",
          [NSNumber numberWithBool:[[locked valueForKey:@"state"] integerValue] == NSOnState], @"locked", nil];
      }
    } else if ([mode isEqual:@"--dock-action"] && argc > 2) {
      NSString *action = [NSString stringWithUTF8String:argv[2]];
      BOOL collapse = [action isEqual:@"collapse"] || [action isEqual:@"expand"];
      BOOL yard = [action hasSuffix:@"-yard"];
      NSString *title = collapse ? ([action isEqual:@"collapse"] ? @"Collapse" : @"Uncollapse") :
        ([action hasPrefix:@"hide"] ? @"Hide" : @"Show");
      DockAction *sender = [[DockAction alloc] initWithTitle:title];
      NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(@"Workspace") host:@""];
      [connection setRequestTimeout:5]; [connection setReplyTimeout:5];
      id controller = [(id)[connection rootProxy] delegate];
      if (!controller) { [sender release]; [pool drain]; return 1; }
      if (collapse) [controller setDockCollapse:sender];
      else if (yard) [controller setIconYardVisibility:sender];
      else [controller setDockVisibility:sender];
      output = [NSDictionary dictionaryWithObject:[sender title] forKey:@"title"];
      [sender release];
    } else if ([mode isEqual:@"--backend"]) {
      output = [NSDictionary dictionaryWithObject:GSDisplayBackendName() ?: @"" forKey:@"backend"];
    } else if ([mode isEqual:@"--open"] && argc > 2) {
      BOOL opened = [workspace openFile:[NSString stringWithUTF8String:argv[2]] fromImage:nil
        at:NSMakePoint(100, 100) inView:nil];
      output = [NSDictionary dictionaryWithObject:[NSNumber numberWithBool:opened] forKey:@"opened"];
      if (!opened) result = 1;
    } else if ([mode isEqual:@"--active"]) {
      output = applicationSummary([workspace activeApplication]);
    } else {
      NSMutableArray *summaries = [NSMutableArray array];
      NSArray *applications;
      if ([mode isEqual:@"--managed-applications"]) {
        NSConnection *connection = [NSConnection connectionWithRegisteredName:GSSessionServiceName(@"Workspace") host:@""];
        [connection setRequestTimeout:5]; [connection setReplyTimeout:5];
        id controller = [(id)[connection rootProxy] delegate];
        if (!controller) { [pool drain]; return 1; }
        applications = [controller launchedApplications];
      } else applications = [workspace launchedApplications];
      /* A remote mutable collection may be a DO proxy. */
      NSUInteger i;
      for (i = 0; i < [applications count]; i++)
        [summaries addObject:applicationSummary([applications objectAtIndex:i])];
      output = summaries;
    }
    NSError *jsonError = nil;
    NSData *data = [NSJSONSerialization dataWithJSONObject:output options:NSJSONWritingPrettyPrinted error:&jsonError];
    if (!data) { fprintf(stderr, "Cannot encode probe result: %s\n", [[jsonError description] UTF8String]); result = 1; }
    else { fwrite([data bytes], 1, [data length], stdout); putchar('\n'); }
  } @catch (NSException *exception) {
    fprintf(stderr, "%s\n", [[exception description] UTF8String]); result = 1;
  }
  [pool drain];
  return result;
}
