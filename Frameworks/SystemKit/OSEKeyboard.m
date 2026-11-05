/* -*- mode: objc -*- */
//
// Project: NEXTSPACE - SystemKit framework
//
// Copyright (C) 2014-2019 Sergii Stoian
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

#import "OSEDefaults.h"
#import "OSEKeyboard.h"
#import "OSEWaylandInput.h"
#include <math.h>

NSString *OSEKeyboardInitialRepeat = @"KeyboardInitialKeyRepeat";
NSString *OSEKeyboardRepeatRate = @"KeyboardRepeatRate";
NSString *OSEKeyboardLayouts = @"KeyboardLayouts";
NSString *OSEKeyboardVariants = @"KeyboardVariants";
NSString *OSEKeyboardModel = @"KeyboardModel";
NSString *OSEKeyboardOptions = @"KeyboardOptions";
NSString *OSEKeyboardNumLockState = @"KeyboardNumLockState";

@implementation OSEKeyboard : NSObject

+ (void)configureWithDefaults:(OSEDefaults *)defs
{
  NSInteger	initialRepeat, repeatRate;
  OSEKeyboard	*keyb;
  NSArray	*layouts, *variants;

  keyb = [OSEKeyboard new];

  // Model
  [keyb setModel:[defs objectForKey:OSEKeyboardModel]];

  // Key Repeat
  if ((initialRepeat = [defs integerForKey:OSEKeyboardInitialRepeat]) < 0)
    initialRepeat = 0;
  if ((repeatRate = [defs integerForKey:OSEKeyboardRepeatRate]) < 0)
    repeatRate = 0;
  if ([defs objectForKey:OSEKeyboardInitialRepeat] || [defs objectForKey:OSEKeyboardRepeatRate])
    [keyb setInitialRepeat:initialRepeat rate:repeatRate];

  // Layouts and Modifiers
  layouts = [defs objectForKey:OSEKeyboardLayouts];
  if (!layouts || [layouts count] == 0) {
    layouts = [keyb layouts];
    variants = [keyb variants];
  }
  else {
    variants = [defs objectForKey:OSEKeyboardVariants];
  }
  [keyb setLayouts:layouts
          variants:variants
           options:[defs objectForKey:OSEKeyboardOptions]];

  // Numeric Keypad
  if ([[defs objectForKey:OSEKeyboardOptions] containsObject:@"numpad:mac"] == NO) {
    [keyb setNumLockState:[defs integerForKey:OSEKeyboardNumLockState]];
  }
  else {
    [keyb setNumLockState:0];
  }
  
  [keyb release];
}

// Converts string like
// "us: English (US, alternative international)" into dictionary:
// {
//   Layout = us;
//   Language = English;
//   Description = "US, alternative international";
// }
- (NSDictionary *)_parseVariantString:(NSString *)value
{
  NSArray *comps;
  NSArray *layout;
  NSArray *language;
  NSArray *keys;
  NSMutableDictionary *dictionary;

  layout = [value componentsSeparatedByString:@": "];
  language = [[layout objectAtIndex:1] componentsSeparatedByString:@" ("];

  comps = [[NSArray arrayWithObject:[layout objectAtIndex:0]]
            arrayByAddingObjectsFromArray:language];

  // NSLog(@"Variant array: %@", comps);

  dictionary = [NSMutableDictionary dictionary];
  [dictionary setObject:[comps objectAtIndex:0] forKey:@"Layout"];
  if ([comps count] > 1)
    [dictionary setObject:[comps objectAtIndex:1] forKey:@"Language"];
  if ([comps count] > 2)
    [dictionary setObject:[[[comps objectAtIndex:2] componentsSeparatedByString:@")"] objectAtIndex:0]
                   forKey:@"Description"];
    
  return dictionary;
}

// Reading XKB_BASE_LST. Default is '/usr/share/X11/xkb/rules/base.lst'.
- (NSDictionary *)_xkbBaseListDictionary
{
  NSMutableDictionary	*dict = [[NSMutableDictionary alloc] init];
  NSMutableDictionary	*modeDict = [[NSMutableDictionary alloc] init];
  NSString		*baseLst;
  NSScanner		*scanner;
  NSString		*lineString = @" ";
  NSString		*sectionName;
  // NSString		*fileName;

  baseLst = [NSString stringWithContentsOfFile:XKB_BASE_LST];
  scanner = [NSScanner scannerWithString:baseLst];

  while ([scanner scanUpToString:@"\n" intoString:&lineString] == YES) {
    // New section start encountered
    if ([lineString characterAtIndex:0] == '!') {
      if ([[modeDict allKeys] count] > 0) {
        [dict setObject:[modeDict copy] forKey:sectionName];
        [modeDict removeAllObjects];
        [modeDict release];
        modeDict = [[NSMutableDictionary alloc] init];
      }
          
      sectionName = [lineString substringFromIndex:2];
    }
    else { // Parse line and add into 'modeDict' dictionary
      NSMutableArray	*lineComponents;
      NSString		*key;
      NSMutableString	*value = [[NSMutableString alloc] init];
      BOOL			add = NO;
          
      lineComponents = [[lineString componentsSeparatedByString:@" "]
                         mutableCopy];
      key = [lineComponents objectAtIndex:0];

      for (NSUInteger i = 1; i < [lineComponents count]; i++) {
        if (add == NO &&
            ![[lineComponents objectAtIndex:i] isEqualToString:@""]) {
          add = YES;
          [value appendFormat:@"%@", [lineComponents objectAtIndex:i]];
        }
        else if (add == YES) {
          [value appendFormat:@" %@", [lineComponents objectAtIndex:i]];
        }
      }

      if ([sectionName isEqualToString:@"variant"]) {
        [modeDict setObject:[self _parseVariantString:value] forKey:key];
      }
      else {
        [modeDict setObject:value forKey:key];
        [value release];
      }
      [lineComponents release];
    }
  }
  
  [dict setObject:[modeDict copy] forKey:sectionName];
  [modeDict removeAllObjects];
  [modeDict release];
  
  return [dict autorelease];
}

// Read the session compositor's keyboard configuration.
- (NSDictionary *)_serverConfig
{
  NSDictionary *state = OSEWaylandInputSettings();
  return [NSDictionary dictionaryWithObjectsAndKeys:[state objectForKey:@"model"] ?: @"pc105", OSEKeyboardModel,
    [state objectForKey:@"layout"] ?: @"us", OSEKeyboardLayouts,
    [state objectForKey:@"variant"] ?: @"", OSEKeyboardVariants,
    [state objectForKey:@"options"] ?: @"", OSEKeyboardOptions, nil];
}

- (void)dealloc
{
  if (layoutDict)  [layoutDict release];
  if (modelDict)   [modelDict release];
  if (variantDict) [variantDict release];
  if (optionDict)  [optionDict release];

  [super dealloc];
}

//------------------------------------------------------------------------------
// Model
//------------------------------------------------------------------------------
- (NSDictionary *)modelList
{
  if (!modelDict) {
    modelDict = [[NSDictionary alloc]
                    initWithDictionary:[[self _xkbBaseListDictionary]
                                         objectForKey:@"model"]];
  }

  return modelDict;
}

- (NSString *)model
{
  return [[self _serverConfig] objectForKey:OSEKeyboardModel];
}

- (BOOL)setModel:(NSString *)name
{
  return name && OSEChangeWaylandInputSettings(@"keyboard",
    [NSDictionary dictionaryWithObject:name forKey:@"model"]);
}

- (void)setNumLockState:(NSInteger)state
{
  OSEChangeWaylandInputSettings(@"keyboard", [NSDictionary dictionaryWithObject:
    [NSNumber numberWithBool:state > 0] forKey:@"numlock"]);
}

//------------------------------------------------------------------------------
// Layouts and options
//------------------------------------------------------------------------------

- (NSDictionary *)availableLayouts
{
  if (!layoutDict) {
    layoutDict = [[NSDictionary alloc]
                     initWithDictionary:[[self _xkbBaseListDictionary]
                                          objectForKey:@"layout"]];
  }

  return layoutDict;
}

- (NSString *)nameForLayout:(NSString *)layoutCode
{
  if (!layoutDict) {
    layoutDict = [[NSDictionary alloc]
                     initWithDictionary:[[self _xkbBaseListDictionary]
                                          objectForKey:@"layout"]];
  }

  return [layoutDict objectForKey:layoutCode];
}

- (NSString *)nameForVariant:(NSString *)variantCode
{
  NSDictionary	*variant;
  NSString	*title;
  
  if (!variantDict) {
    variantDict = [[NSDictionary alloc]
                      initWithDictionary:[[self _xkbBaseListDictionary]
                                           objectForKey:@"variant"]];
  }

  variant = [variantDict objectForKey:variantCode];
  title = [variant objectForKey:@"Description"];
  if (!title) {
    title = [variant objectForKey:@"Language"];
  }

  return title;
}

// Return list of dictionaries with keys: Layout, Desc.
- (NSDictionary *)_variantListForKey:(NSString *)field
                              value:(NSString *)value
{
  NSMutableDictionary	*layoutVariants;
  NSDictionary		*variant;
    
  if (!variantDict) {
    variantDict = [[NSDictionary alloc]
                      initWithDictionary:[[self _xkbBaseListDictionary]
                                           objectForKey:@"variant"]];
  }

  layoutVariants = [[NSMutableDictionary alloc] init];
  for (NSString *key in [variantDict allKeys]) {
    variant = [variantDict objectForKey:key];
    if ([[variant objectForKey:field] isEqualToString:value]) {
      [layoutVariants setObject:[self nameForVariant:key]
                         forKey:key];
    }
  }

  return [layoutVariants autorelease];
}

- (NSDictionary *)variantListForLayout:(NSString *)layout
{
  return [self _variantListForKey:@"Layout" value:layout];
}

- (NSDictionary *)variantListForLanguage:(NSString *)language
{
  return [self _variantListForKey:@"Language" value:language];
}

- (NSArray *)layouts
{
  NSString *l = [[self _serverConfig] objectForKey:OSEKeyboardLayouts];

  if (l == nil || [l isEqualToString:@""]) {
    return [NSArray arrayWithObject:@"us"];
  }

  return [l componentsSeparatedByString:@","];
}

- (NSArray *)variants
{
  NSArray  *l = [self layouts];
  NSString *v = [[self _serverConfig] objectForKey:OSEKeyboardVariants];
  NSArray  *va = [v componentsSeparatedByString:@","];

  while ([l count] > [va count]) {
    va = [va arrayByAddingObject:@""];
  }

  return va;
}

- (NSArray *)options
{
  NSString	 *optString = [[self _serverConfig] objectForKey:OSEKeyboardOptions];
  NSMutableArray *optArray;
  NSArray	 *options;

  optArray = [[optString componentsSeparatedByString:@","] mutableCopy];

  for (unsigned int i = 0; i < [optArray count]; i++) {
    if ([[optArray objectAtIndex:i] isEqualToString:@""]) {
      [optArray removeObjectAtIndex:i];
    }
  }

  options = [NSArray arrayWithArray:optArray];
  [optArray release];
  
  return options;
}

- (void)addLayout:(NSString *)lCode variant:(NSString *)vCode
{
  NSMutableArray *layouts = [[self layouts] mutableCopy];
  NSMutableArray *variants = [[self variants] mutableCopy];

  if (vCode) {
    NSInteger lc = [layouts count];
    NSInteger vc = [variants count];
          
    for (int i = 0; i < (lc - vc); i++){
      [variants addObject:@""];
    }
    [variants addObject:vCode];
  }
  else {
    [variants addObject:@""];
  }
  [layouts addObject:lCode];

  // NSLog(@"[OSEKeyboard] addLayout new config: layouts: %@ variants: %@",
  //       layouts, variants);

  [self setLayouts:layouts variants:variants options:nil];
  [layouts release];
  [variants release];
}

- (void)removeLayout:(NSString *)lCode variant:(NSString *)vCode
{
  NSMutableArray *layouts = [[self layouts] mutableCopy];
  NSMutableArray *variants = [[self variants] mutableCopy];
  NSUInteger	 lIndex;

  lIndex = [layouts indexOfObject:lCode];
  for (lIndex = 0; lIndex < [layouts count]; lIndex++) {
    if ([[layouts objectAtIndex:lIndex] isEqualToString:lCode] &&
        (!vCode || [vCode isEqualToString:@""] ||
         [[variants objectAtIndex:lIndex] isEqualToString:vCode])) {
      break;
    }
  }
  [layouts removeObjectAtIndex:lIndex];
  if (lIndex < [variants count]) {
    [variants removeObjectAtIndex:lIndex];
  }
  
  [self setLayouts:layouts variants:variants options:nil];
  [layouts release];
  [variants release];
}

- (BOOL)setLayouts:(NSArray *)layouts
          variants:(NSArray *)variants
           options:(NSArray *)options
{
  NSMutableDictionary *changes = [NSMutableDictionary dictionary];
  if (layouts) [changes setObject:[layouts componentsJoinedByString:@","] forKey:@"layout"];
  if (variants) [changes setObject:[variants componentsJoinedByString:@","] forKey:@"variant"];
  if (options) [changes setObject:[options componentsJoinedByString:@","] forKey:@"options"];
  return OSEChangeWaylandInputSettings(@"keyboard", changes);
}

//------------------------------------------------------------------------------
// Initial Repeat and Repeat Rate
//------------------------------------------------------------------------------

- (void)_setRepeat:(NSInteger)repeat rate:(NSInteger)rate
{
  NSMutableDictionary *changes = [NSMutableDictionary dictionary];
  if (repeat > 0) [changes setObject:[NSNumber numberWithInteger:repeat] forKey:@"delay"];
  if (rate > 0) [changes setObject:[NSNumber numberWithLong:lround(1000.0 / rate)] forKey:@"rate"];
  OSEChangeWaylandInputSettings(@"keyboard", changes);
}

- (NSInteger)initialRepeat
{
  return [[OSEWaylandInputSettings() objectForKey:@"delay"] integerValue];
}
- (void)setInitialRepeat:(NSInteger)delay
{
  [self _setRepeat:delay rate:0];
}
- (NSInteger)repeatRate
{
  NSInteger rate = [[OSEWaylandInputSettings() objectForKey:@"rate"] integerValue];
  return rate > 0 ? lround(1000.0 / rate) : 0;
}
- (void)setRepeatRate:(NSInteger)rate
{
  [self _setRepeat:0 rate:rate];
}
- (void)setInitialRepeat:(NSInteger)delay rate:(NSInteger)rate
{
  [self _setRepeat:delay rate:rate];
}

@end
