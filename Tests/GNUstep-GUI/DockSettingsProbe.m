/* Dock migration/persistence contract. SPDX-License-Identifier: MIT */
#import <Foundation/Foundation.h>
#import "WSDockSettings.h"

static void require(BOOL condition, NSString *message)
{
  if (!condition) [NSException raise:NSInternalInconsistencyException format:@"%@", message];
}

static NSArray *expectedInsets(int dock, int yard)
{
  return [NSArray arrayWithObjects:[NSNumber numberWithInt:0], [NSNumber numberWithInt:0],
    [NSNumber numberWithInt:dock], [NSNumber numberWithInt:yard], nil];
}

int main(int argc, char **argv)
{
  if (argc != 2) return 1;
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  NSString *directory = [NSString stringWithUTF8String:argv[1]];
  NSString *domain = [@"NextSpaceDockTest-" stringByAppendingString:[[NSProcessInfo processInfo] globallyUniqueString]];
  NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
  int result = 0;
  @try {
    NSDictionary *terminal = [NSDictionary dictionaryWithObjectsAndKeys:@"Terminal.GNUstep", @"Name",
      @"0,1", @"Position", @"Terminal", @"Command", @"Yes", @"AutoLaunch", @"Keep", @"UnknownAppKey", nil];
    NSDictionary *textedit = [NSDictionary dictionaryWithObjectsAndKeys:@"TextEdit.GNUstep", @"Name",
      @"0,2", @"Position", @"TextEdit", @"Command", nil];
    NSDictionary *dock = [NSDictionary dictionaryWithObjectsAndKeys:[NSArray arrayWithObject:terminal], @"Applications",
      [NSArray arrayWithObject:textedit], @"Applications600", @"Untouched", @"UnknownDockKey", nil];
    NSString *statePath = [directory stringByAppendingPathComponent:@"WMState.plist"];
    require([[NSDictionary dictionaryWithObjectsAndKeys:dock, @"Dock", @"Keep", @"OtherRootKey", nil]
      writeToFile:statePath atomically:YES], @"Create legacy fixture");
    NSString *attributesPath = [directory stringByAppendingPathComponent:@"WMWindowAttributes.plist"];
    [[NSDictionary dictionaryWithObject:[NSDictionary dictionaryWithObject:@"legacy.tiff" forKey:@"Icon"]
      forKey:@"Terminal.GNUstep"] writeToFile:attributesPath atomically:YES];
    NSData *stateBefore = [NSData dataWithContentsOfFile:statePath];
    NSData *attributesBefore = [NSData dataWithContentsOfFile:attributesPath];
    [defaults setPersistentDomain:[NSDictionary dictionaryWithObject:@"Keep" forKey:@"Unrelated"] forName:domain];
    WSDockSettings *settings = [[WSDockSettings alloc] initWithDefaults:defaults domain:domain legacyDirectory:directory];
    require([[[[settings applicationsForHeight:1200] objectAtIndex:0] objectForKey:@"Name"] isEqual:@"Terminal.GNUstep"], @"Import current legacy applications");
    require([[[[settings applicationsForHeight:600] objectAtIndex:0] objectForKey:@"Name"] isEqual:@"TextEdit.GNUstep"], @"Keep height-specific layouts");
    require([[settings iconPathForApplication:@"Terminal.GNUstep"] isEqual:@"legacy.tiff"], @"Import image override");
    require([settings setValue:@"No" forKey:@"AutoLaunch" application:@"Terminal.GNUstep" height:1200], @"Save autolaunch");
    require([settings delayForRaising:YES] == 0.6 && [settings delayForRaising:NO] == 1.0, @"Keep default Dock delays");
    require([[settings windowInsetsWithDock:YES iconYard:YES] isEqual:expectedInsets(67, 64)], @"Default logical Dock and IconYard clearances");
    require([[settings windowInsetsWithDock:NO iconYard:NO] isEqual:expectedInsets(0, 0)], @"Hidden desktop components release their reservations");
    NSString *timingPath = [directory stringByAppendingPathComponent:@"WM.plist"];
    NSDictionary *appearance = [settings titleAppearance];
    require([[appearance objectForKey:@"font"] isEqual:@"Helvetica:bold:pixelsize=12"] &&
      ![[appearance objectForKey:@"antialiased"] boolValue] && [[appearance objectForKey:@"justification"] isEqual:@"center"],
      @"Keep existing default title appearance");
    NSDictionary *customAppearance = [NSDictionary dictionaryWithObjectsAndKeys:
      @"DejaVu Sans:postscriptname=DejaVuSans-Bold:pixelsize=14:antialias=false:embeddedbitmap=true", @"WindowTitleFont",
      @"YES", @"UseAntialiasedText", @"LEFT", @"TitleJustify", @"Keep", @"Unknown", nil];
    require([customAppearance writeToFile:timingPath atomically:YES], @"Create existing Font-panel preference format");
    NSData *appearanceBefore = [NSData dataWithContentsOfFile:timingPath];
    appearance = [settings titleAppearance];
    require([[appearance objectForKey:@"font"] isEqual:[customAppearance objectForKey:@"WindowTitleFont"]] &&
      [[appearance objectForKey:@"antialiased"] boolValue] && [[appearance objectForKey:@"justification"] isEqual:@"left"],
      @"Read live legacy title appearance without losing explicit Fontconfig properties");
    require([appearanceBefore isEqual:[NSData dataWithContentsOfFile:timingPath]], @"Title import leaves X11 settings intact");
    [[NSDictionary dictionaryWithObjectsAndKeys:[NSNumber numberWithInt:42], @"WindowTitleFont",
      [NSArray array], @"UseAntialiasedText", @"invalid", @"TitleJustify", nil] writeToFile:timingPath atomically:YES];
    appearance = [settings titleAppearance];
    require([[appearance objectForKey:@"font"] isEqual:@"Helvetica:bold:pixelsize=12"] &&
      ![[appearance objectForKey:@"antialiased"] boolValue] && [[appearance objectForKey:@"justification"] isEqual:@"center"],
      @"Malformed title preferences retain existing defaults");
    [[NSFileManager defaultManager] removeItemAtPath:timingPath error:NULL];
    require([settings maximizedDragMode] == 0, @"Keep default maximized drag behavior");
    NSArray *dragModes = [NSArray arrayWithObjects:@"Move", @"restoregeometry", @"Unmaximize", @"NoMove", @"Invalid",
      [NSNumber numberWithInt:42], nil];
    for (NSUInteger index = 0; index < [dragModes count]; index++) {
      [[NSDictionary dictionaryWithObject:[dragModes objectAtIndex:index] forKey:@"DragMaximizedWindow"] writeToFile:timingPath atomically:YES];
      require([settings maximizedDragMode] == (index < 4 ? index : 0), @"Import validated maximized drag preference");
    }
    [[NSDictionary dictionaryWithObjectsAndKeys:@"80", @"ClipAutoraiseDelay", @"150", @"ClipAutolowerDelay", nil]
      writeToFile:timingPath atomically:YES];
    require([settings delayForRaising:YES] == 0.08 && [settings delayForRaising:NO] == 0.15, @"Import configured Dock delays");
    [[NSDictionary dictionaryWithObjectsAndKeys:@"No", @"NoWindowOverDock", [NSNumber numberWithBool:NO], @"NoWindowOverIcons", nil]
      writeToFile:timingPath atomically:YES];
    require([[settings windowInsetsWithDock:YES iconYard:YES] isEqual:expectedInsets(0, 0)], @"Preserve configured window-overlap preferences");
    [[NSFileManager defaultManager] removeItemAtPath:timingPath error:NULL];
    require([settings setDockValue:@"Yes" forKey:@"Collapsed"], @"Save collapse state");
    require(![settings setDockLevel:123], @"Reject unknown Dock level");
    require([settings setDockLevel:-1000] && [[[settings dock] objectForKey:@"AutoRaiseLower"] boolValue], @"Preserve automatic raising preference");
    require([settings setDockLevel:5] && ![[[settings dock] objectForKey:@"Lowered"] boolValue] &&
      ![[[settings dock] objectForKey:@"AutoRaiseLower"] boolValue], @"Store Dock level as one settings update");
    require([settings setIconPath:@"native.svg" forApplication:@"Terminal.GNUstep"], @"Save native image override");
    [settings release];
    settings = [[WSDockSettings alloc] initWithDefaults:defaults domain:domain legacyDirectory:directory];
    require([[[settings dock] objectForKey:@"UnknownDockKey"] isEqual:@"Untouched"], @"Preserve unknown Dock keys");
    NSDictionary *imported = [[settings applicationsForHeight:1200] objectAtIndex:0];
    require([[imported objectForKey:@"UnknownAppKey"] isEqual:@"Keep"] && ![[imported objectForKey:@"AutoLaunch"] boolValue], @"Reload changed and unknown application values");
    require([[[[settings applicationsForHeight:600] objectAtIndex:0] objectForKey:@"Name"] isEqual:@"TextEdit.GNUstep"], @"Preserve other layouts during edits");
    require([[settings iconPathForApplication:@"Terminal.GNUstep"] isEqual:@"native.svg"], @"Reload native image override");
    NSDictionary *review = [NSDictionary dictionaryWithObjectsAndKeys:@"Review.GNUstep", @"Name", @"Review", @"Command", @"Yes", @"Lock", nil];
    require([settings addApplication:review atSlot:3 height:1200], @"Pin application");
    require(![settings addApplication:review atSlot:4 height:1200] && ![settings addApplication:textedit atSlot:1 height:1200], @"Reject duplicates and occupied slots");
    require(![settings removeApplication:@"Review.GNUstep" height:1200], @"Locked pin stays present");
    require(![settings moveApplication:@"Review.GNUstep" toSlot:4 height:1200], @"Locked pin cannot move");
    require(![settings moveApplication:@"Terminal.GNUstep" toSlot:3 height:1200], @"Locked destination cannot be displaced");
    require([settings setValue:@"No" forKey:@"Lock" application:@"Review.GNUstep" height:1200] &&
      [settings removeApplication:@"Review.GNUstep" height:1200], @"Unlock and remove pin");
    require(![settings removeApplication:@"Workspace.GNUstep" height:1200], @"Protect Workspace slot");
    require([settings addApplication:textedit atSlot:2 height:1200], @"Add swap target");
    require([settings moveApplication:@"Terminal.GNUstep" toSlot:2 height:1200], @"Swap occupied Dock slots atomically");
    for (NSDictionary *entry in [settings applicationsForHeight:1200]) {
      NSString *expected = [[entry objectForKey:@"Name"] isEqual:@"Terminal.GNUstep"] ? @"0,2" : @"0,1";
      require([[entry objectForKey:@"Position"] isEqual:expected], @"Both swapped positions persisted");
    }
    require(![settings moveApplication:@"Terminal.GNUstep" toSlot:0 height:1200], @"Protect top slot");
    require([settings setIconYardPosition:NSMakePoint(125, 200) forApplication:@"Terminal"], @"Save logical IconYard position");
    require([[[settings iconYardPositionForApplication:@"Terminal"] objectForKey:@"X"] intValue] == 125 &&
      [[[settings iconYardPositionForApplication:@"Terminal"] objectForKey:@"Y"] intValue] == 200, @"Reload free icon placement");
    require([settings setIconPath:nil forApplication:@"Terminal.GNUstep"] && ![settings iconPathForApplication:@"Terminal.GNUstep"], @"Clear override without restoring legacy image");
    require([stateBefore isEqual:[NSData dataWithContentsOfFile:statePath]] &&
      [attributesBefore isEqual:[NSData dataWithContentsOfFile:attributesPath]], @"Leave X11 configuration intact");
    require([[[defaults persistentDomainForName:domain] objectForKey:@"Unrelated"] isEqual:@"Keep"], @"Preserve other application preferences");
    [settings release];
    puts("Dock settings migration, persistence and X11 data preservation: PASS");
  } @catch (NSException *exception) {
    fprintf(stderr, "%s\n", [[exception description] UTF8String]); result = 1;
  }
  [defaults removePersistentDomainForName:domain]; [defaults synchronize];
  [pool drain]; return result;
}
