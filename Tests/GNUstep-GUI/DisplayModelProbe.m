/* Exercise the public SystemKit model against the real session service.
   SPDX-License-Identifier: MIT */
#import <AppKit/AppKit.h>
#import <SystemKit/OSEScreen.h>
#import <SystemKit/OSEDisplay.h>
#import <SystemKit/OSEKeyboard.h>
#import <SystemKit/OSEMouse.h>
#import <SystemKit/OSEDefaults.h>
#include <unistd.h>
#include <math.h>

static void require(BOOL condition, NSString *message)
{ if (!condition) [NSException raise:@"DisplayModelProbe" format:@"%@", message]; }
static BOOL status(NSDictionary *result, int expected)
{ return result && [[result objectForKey:@"status"] intValue] == expected; }
static void output(NSDictionary *value)
{
  NSData *data = [NSJSONSerialization dataWithJSONObject:value options:0 error:NULL];
  fwrite([data bytes], 1, [data length], stdout); putchar('\n'); fflush(stdout);
}

int main(int argc, char **argv)
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  BOOL readonly = argc > 1 && strcmp(argv[1], "--readonly") == 0;
  if (!readonly && access("/.dockerenv", F_OK) != 0) {
    fprintf(stderr, "DisplayModelProbe: profile tests require the disposable Linux container.\n");
    [pool drain]; return 1;
  }
  [NSApplication sharedApplication];
  OSEScreen *screen = [OSEScreen new];
  require([NSStringFromClass([screen class]) isEqual:@"OSEWaylandScreen"], @"native factory selected X11");
  require([[screen connectedDisplays] count] > 0, @"no native outputs");
  if (readonly) {
    require(![screen supportsDisplayConfiguration], @"read-only fixture found a settings service");
    for (OSEDisplay *display in [screen connectedDisplays]) {
      require([display modePixelSize].width > 0 && [display frame].size.width > 0, @"missing bootstrap geometry");
      require([display scaleNumerator] == 0, @"bootstrap invented an exact fractional output scale");
    }
    output([NSDictionary dictionaryWithObject:@"readonly" forKey:@"passed"]);
    [screen release]; [pool drain]; return 0;
  }
  require([screen supportsDisplayTransactions], @"native settings service unavailable");
  if (argc > 1 && strcmp(argv[1], "--save-only") == 0) {
    require([screen saveCurrentDisplayLayout], @"profile save failed");
    output([NSDictionary dictionaryWithObject:@"saved" forKey:@"passed"]);
    [screen release]; [pool drain]; return 0;
  }
  NSArray *original = [[screen currentLayout] retain];
  NSString *profilePath = [@"~/Library/Preferences/.NextSpace/WaylandDisplays.plist" stringByExpandingTildeInPath];
  NSData *previousProfile = [[NSData dataWithContentsOfFile:profilePath] retain];
  NSMutableArray *passed = [NSMutableArray array];
  int result = 0;
  @try {
    CGFloat red, green, blue, r, g, b;
    require([screen backgroundColorRed:&red green:&green blue:&blue], @"native background unavailable");
    require([screen setBackgroundColorRed:0.5 green:0.25 blue:0.75] &&
      [screen backgroundColorRed:&r green:&g blue:&b] && r == 0.5 && g == 0.25 && b == 0.75,
      @"native background did not reach the compositor");
    require(![screen setBackgroundColorRed:NAN green:0 blue:0] && ![screen setBackgroundColorRed:-1 green:0 blue:0],
      @"invalid background accepted");
    require([screen setBackgroundColorRed:red green:green blue:blue], @"native background restore failed");
    [passed addObject:@"native desktop color and rejected invalid components"];
    OSEKeyboard *keyboard = [OSEKeyboard new];
    NSArray *layouts = [[keyboard layouts] copy], *variants = [[keyboard variants] copy], *options = [[keyboard options] copy];
    NSString *model = [[keyboard model] copy];
    NSInteger delay = [keyboard initialRepeat], interval = [keyboard repeatRate];
    require([keyboard setModel:@"pc105"] && [keyboard setLayouts:[NSArray arrayWithObject:@"de"]
      variants:[NSArray arrayWithObject:@""] options:[NSArray array]], @"native keyboard rules failed");
    [keyboard setInitialRepeat:160 rate:50];
    require([keyboard initialRepeat] == 160 && [keyboard repeatRate] == 50, @"repeat interval/hertz conversion failed");
    require(![keyboard setLayouts:[NSArray arrayWithObject:@"nextspace_invalid_layout"] variants:nil options:nil],
      @"invalid native keymap accepted");
    require([[[keyboard layouts] objectAtIndex:0] isEqual:@"de"], @"invalid keymap changed current layout");
    [keyboard setNumLockState:1];
    require([keyboard setLayouts:layouts variants:variants options:options] && [keyboard setModel:model],
      @"native keyboard restore failed");
    [keyboard setInitialRepeat:delay rate:interval]; [keyboard setNumLockState:0];
    [layouts release]; [variants release]; [options release]; [model release]; [keyboard release];
    OSEDefaults *defaults = [OSEDefaults globalUserDefaults];
    id oldRatio = [[defaults objectForKey:OSEMouseAcceleration] retain];
    id oldThreshold = [[defaults objectForKey:OSEMouseThreshold] retain];
    NSString *wmPath = [@"~/Library/Preferences/.WindowMaker/WindowMaker" stringByExpandingTildeInPath];
    NSData *wmBefore = [NSData dataWithContentsOfFile:wmPath];
    OSEMouse *mouse = [OSEMouse new];
    double speed = [mouse normalizedAcceleration]; NSUInteger pointerProfile = [mouse accelerationProfile];
    NSInteger dragThreshold = [mouse accelerationThreshold];
    require([mouse usesNativeInputSettings] && [mouse setNormalizedAcceleration:-0.5 profile:1], @"native pointer settings failed");
    require([mouse normalizedAcceleration] == -0.5 && [mouse accelerationProfile] == 1, @"pointer readback failed");
    [mouse setAcceleration:0 threshold:5]; [mouse saveToDefaults];
    require([OSEMouse dragThreshold] == 5, @"logical drag threshold failed");
    [mouse locationOnScreen];
    require([mouse setNormalizedAcceleration:speed profile:pointerProfile], @"pointer restore failed");
    [mouse setAcceleration:0 threshold:dragThreshold]; [mouse saveToDefaults];
    require((!oldRatio && ![defaults objectForKey:OSEMouseAcceleration]) ||
      [oldRatio isEqual:[defaults objectForKey:OSEMouseAcceleration]], @"native pointer rewrote X11 ratio");
    require((!oldThreshold && ![defaults objectForKey:OSEMouseThreshold]) ||
      [oldThreshold isEqual:[defaults objectForKey:OSEMouseThreshold]], @"native pointer rewrote X11 threshold");
    NSData *wmAfter = [NSData dataWithContentsOfFile:wmPath];
    require((!wmBefore && !wmAfter) || [wmBefore isEqual:wmAfter], @"native settings rewrote Window Maker defaults");
    [oldRatio release]; [oldThreshold release]; [mouse release];
    [passed addObject:@"native keyboard/pointer models and preserved X11 input preferences"];
    NSArray *scales = [NSArray arrayWithObjects:@120, @150, @180, @210, @240, nil];
    NSUInteger turn;
    for (turn = 0; turn < 8; turn++) {
      NSMutableArray *layout = [NSMutableArray array];
      NSUInteger index = 0;
      for (NSDictionary *entry in [screen currentLayout]) {
        NSMutableDictionary *changed = [[entry mutableCopy] autorelease];
        [changed setObject:[scales objectAtIndex:turn % [scales count]] forKey:OSEDisplayScaleKey];
        [changed setObject:[NSNumber numberWithUnsignedInteger:turn] forKey:OSEDisplayTransformKey];
        NSRect frame = NSRectFromString([entry objectForKey:OSEDisplayFrameKey]);
        frame.origin = NSMakePoint((CGFloat)index * 1800 - 1600, -200);
        [changed setObject:NSStringFromRect(frame) forKey:OSEDisplayFrameKey];
        [changed setObject:index == 0 ? @"YES" : @"NO" forKey:OSEDisplayIsMainKey];
        [layout addObject:changed]; index++;
      }
      NSDictionary *tested = [screen testDisplayLayout:layout];
      require(status(tested, 0), [NSString stringWithFormat:@"public model test failed: %@", tested]);
      require(status([screen beginDisplayLayout:layout timeout:15000], 1), @"public model apply failed");
      require(![screen saveCurrentDisplayLayout], @"unconfirmed state was persisted");
      require([screen confirmDisplayLayout], @"public model confirmation failed");
      for (OSEDisplay *display in [screen activeDisplays]) {
        NSUInteger scale = [[scales objectAtIndex:turn % [scales count]] unsignedIntegerValue];
        require([display scaleNumerator] == scale && [display transform] == turn, @"scale/transform lost in model");
        NSSize pixels = [display modePixelSize];
        if (turn & 1) pixels = NSMakeSize(pixels.height, pixels.width);
        NSSize expected = NSMakeSize(floor(pixels.width * 120 / scale), floor(pixels.height * 120 / scale));
        require(NSEqualSizes([display frame].size, expected), @"physical mode was confused with logical bounds");
        require([screen displayWithID:[display uniqueID]] == display, @"hardware identity lookup failed");
      }
      require(NSMinX([screen logicalBounds]) == -1600, @"negative desktop origin was lost");
    }
    [passed addObject:@"physical/logical modes, five densities, all transforms, primary and negative origins"];
    require([screen saveCurrentDisplayLayout], @"confirmed profile save failed");
    NSDictionary *profile = [NSDictionary dictionaryWithContentsOfFile:profilePath];
    require([[profile objectForKey:@"Schema"] intValue] == 2, @"profile has no native schema");
    for (NSDictionary *entry in [profile objectForKey:@"Layout"])
      require(![entry objectForKey:OSEDisplayPropertiesKey], @"compositor-local properties persisted");
    require([screen applySavedDisplayLayout], @"matching hardware profile could not be restored");
    NSMutableDictionary *partial = [[profile mutableCopy] autorelease];
    [partial setObject:[NSArray arrayWithObject:[[profile objectForKey:@"Layout"] objectAtIndex:0]] forKey:@"Layout"];
    require([partial writeToFile:profilePath atomically:YES] && [screen applySavedDisplayLayout],
      @"profile did not preserve a newly connected head");
    NSMutableArray *dark = [NSMutableArray array];
    for (NSDictionary *entry in [profile objectForKey:@"Layout"]) {
      NSMutableDictionary *head = [[entry mutableCopy] autorelease];
      [head setObject:@"NO" forKey:OSEDisplayIsActiveKey]; [dark addObject:head];
    }
    [partial setObject:dark forKey:@"Layout"];
    require([partial writeToFile:profilePath atomically:YES] && ![screen applySavedDisplayLayout],
      @"all-disabled saved profile was accepted");
    require([[screen activeDisplays] count] == [[screen connectedDisplays] count], @"bad profile darkened the desktop");
    require([profile writeToFile:profilePath atomically:YES], @"profile fixture restoration failed");
    [passed addObject:@"separate versioned profile contains durable identities and restores"];
    require(status([screen beginDisplayLayout:original timeout:1000], 1), @"timeout preview failed");
    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:5];
    while (status([screen displayLayoutStatus], 1) && [deadline timeIntervalSinceNow] > 0)
      [[NSRunLoop currentRunLoop] runMode:NSDefaultRunLoopMode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.02]];
    require(status([screen displayLayoutStatus], 3), @"compositor timeout was not visible in public model");
    require([screen applyDisplayLayout:original], @"could not restore original layout");
    [passed addObject:@"compositor timeout observed without a client rollback timer"];
    OSEDisplay *target = [[[screen connectedDisplays] objectAtIndex:0] retain];
    [screen deactivateDisplay:target];
    require([[screen activeDisplays] count] + 1 == [[screen connectedDisplays] count], @"disable failed");
    OSEDisplay *remaining = [[[screen activeDisplays] objectAtIndex:0] retain];
    [screen deactivateDisplay:remaining];
    require([[screen activeDisplays] count] == 1, @"public model allowed a completely dark layout");
    [remaining release];
    [screen activateDisplay:[screen displayWithID:[target uniqueID]]];
    [target release];
    require([[screen activeDisplays] count] == [[screen connectedDisplays] count], @"re-enable failed");
    require([screen applyDisplayLayout:original], @"final layout restoration failed");
    [passed addObject:@"activation, last-output rejection and reactivation"];
    output([NSDictionary dictionaryWithObjectsAndKeys:NSStringFromClass([screen class]), @"class", passed, @"passed", nil]);
  } @catch (NSException *exception) {
    fprintf(stderr, "%s\n", [[exception description] UTF8String]); result = 1;
  } @finally {
    if (previousProfile) [previousProfile writeToFile:profilePath atomically:YES];
    else [[NSFileManager defaultManager] removeItemAtPath:profilePath error:NULL];
  }
  [previousProfile release]; [original release]; [screen release]; [pool drain];
  return result;
}
