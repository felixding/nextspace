/* Private native display model conversions. GPL-2.0-or-later. */
#import "OSEScreen.h"
#include <math.h>

static NSDictionary *resolution(NSDictionary *mode)
{
  return [NSDictionary dictionaryWithObjectsAndKeys:
    NSStringFromSize(NSMakeSize([[mode objectForKey:@"width"] intValue], [[mode objectForKey:@"height"] intValue])),
    OSEDisplayResolutionSizeKey, [NSNumber numberWithDouble:[[mode objectForKey:@"refresh"] doubleValue] / 1000],
    OSEDisplayResolutionRateKey, [NSString stringWithFormat:@"%dx%d",
      [[mode objectForKey:@"width"] intValue], [[mode objectForKey:@"height"] intValue]],
    OSEDisplayResolutionNameKey, nil];
}
static NSSize logicalSize(NSDictionary *mode, NSUInteger scale, NSUInteger transform)
{
  NSSize size = NSSizeFromString([mode objectForKey:OSEDisplayResolutionSizeKey]);
  if (transform & 1) size = NSMakeSize(size.height, size.width);
  if (!scale) return NSZeroSize;
  return NSMakeSize(floor(size.width * 120 / scale), floor(size.height * 120 / scale));
}
static NSArray *hardwareIdentity(NSDictionary *head, BOOL connector)
{
  return [NSArray arrayWithObjects:[head objectForKey:@"make"] ?: @"", [head objectForKey:@"model"] ?: @"",
    [head objectForKey:@"serial"] ?: @"", connector ? ([head objectForKey:@"name"] ?: @"") : @"", nil];
}

static NSDictionary *nativeGammaSettings(NSDictionary *description)
{
  if (![description isKindOfClass:[NSDictionary class]]) return nil;
  NSArray *legacy = [NSArray arrayWithObjects:OSEDisplayGammaRedKey, OSEDisplayGammaGreenKey,
    OSEDisplayGammaBlueKey, OSEDisplayGammaBrightnessKey, nil];
  NSArray *keys = [NSArray arrayWithObjects:@"red", @"green", @"blue", @"brightness", nil];
  NSMutableDictionary *settings = [NSMutableDictionary dictionary];
  for (NSUInteger i = 0; i < [keys count]; i++) {
    id value = [description objectForKey:[legacy objectAtIndex:i]];
    double number;
    if ([value isKindOfClass:[NSNumber class]]) number = [value doubleValue];
    else if ([value isKindOfClass:[NSString class]]) {
      NSScanner *scanner = [NSScanner scannerWithString:value];
      if (![scanner scanDouble:&number] || ![scanner isAtEnd]) return nil;
    } else return nil;
    if (i < 3 && number == 0) number = 1; /* Existing SystemKit convention. */
    if (!isfinite(number) || number < (i == 3 ? 0 : 0.1) || number > (i == 3 ? 2 : 10)) return nil;
    [settings setObject:[NSNumber numberWithDouble:number] forKey:[keys objectAtIndex:i]];
  }
  return settings;
}
