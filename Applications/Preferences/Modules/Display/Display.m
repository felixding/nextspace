/* -*- mode: objc -*- */
//
// Project: Preferences
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

#import <AppKit/NSApplication.h>
#import <AppKit/NSNibLoading.h>
#import <AppKit/NSView.h>
#import <AppKit/NSBox.h>
#import <AppKit/NSImage.h>
#import <AppKit/NSPopUpButton.h>
#import <AppKit/NSBrowser.h>
#import <AppKit/NSBrowserCell.h>
#import <AppKit/NSMatrix.h>
#import <AppKit/NSSlider.h>
#import <AppKit/NSTextField.h>
#import <DesktopKit/NXTDisplayConfiguration.h>

#import <SystemKit/OSEDefaults.h>
#import <DesktopKit/NXTNumericField.h>
#import <DesktopKit/NXTCountdownAlert.h>

#import <SystemKit/OSEScreen.h>
#import <SystemKit/OSEDisplay.h>

#import <dispatch/dispatch.h>

#import "AppController.h"
#import "Display.h"

@implementation DisplayPrefs

//
#pragma mark - Init & protocol
//

- (id)init
{
  NSBundle *bundle;
  NSString *imagePath;

  self = [super init];

  bundle = [NSBundle bundleForClass:[self class]];
  imagePath = [bundle pathForResource:@"Monitor" ofType:@"tiff"];
  image = [[NSImage alloc] initWithContentsOfFile:imagePath];

  lastGoodResolution = [NSMutableDictionary new];

  return self;
}

- (void)dealloc
{
  NSLog(@"DisplayPrefs -dealloc");

  [[NSNotificationCenter defaultCenter] removeObserver:self];
  [[NSDistributedNotificationCenter notificationCenterForType:GSPublicNotificationCenterType] removeObserver:self];

  [image release];

  [view release];
  [systemScreen release];
  if (saveConfigTimer) {
    [saveConfigTimer release];
  }
  [lastGoodResolution release];
  [selectedDisplay release]; [selectedDisplayName release];
  [super dealloc];
}

- (void)awakeFromNib
{
  [view retain];
  [window release];

  systemScreen = [OSEScreen sharedScreen];
  [systemScreen retain];
  [systemScreen setUseAutosave:YES];

  // Setup NXNumericField float constraints
  [gammaField setMinimumValue:0.1];
  [gammaField setMaximumValue:2.0];
  [[gammaField formatter] setMinimumIntegerDigits:1];
  [[gammaField formatter] setMinimumFractionDigits:2];

  // Setup NXNumericField integer constraints
  [brightnessField setMinimumValue:0.5];
  [brightnessField setMaximumValue:100.0];

  if ([systemScreen isNativeDisplay]) [self setupNativeControls];

  [monitorsList loadColumnZero];
  [self selectFirstEnabledMonitor];

  if (![systemScreen isNativeDisplay]) {
    [rotationBtn setEnabled:NO]; [reflectionBtn setEnabled:NO];
  }

  // Desktop background
  CGFloat red, green, blue;
  if ([systemScreen backgroundColorRed:&red green:&green blue:&blue] == YES) {
    desktopBackground = [NSColor colorWithDeviceRed:red green:green blue:blue alpha:1.0];
    [colorBtn setColor:desktopBackground];
    [systemScreen setBackgroundColorRed:red green:green blue:blue];
    [colorBtn setEnabled:YES];
  }

  [[NSNotificationCenter defaultCenter] addObserver:self
                                           selector:@selector(screenDidUpdate:)
                                               name:OSEScreenDidUpdateNotification
                                             object:systemScreen];
  if (![systemScreen isNativeDisplay]) [[NSDistributedNotificationCenter notificationCenterForType:GSPublicNotificationCenterType]
      addObserver:self
         selector:@selector(screenDidChange:)
             name:OSEScreenDidChangeNotification
           object:nil];
}

- (NSView *)view
{
  if (view == nil) {
    if (![NSBundle loadNibNamed:@"Display" owner:self]) {
      NSLog(@"Display.preferences: Could not load NIB, aborting.");
      return nil;
    }
  }

  return view;
}

- (NSString *)buttonCaption
{
  return @"Display Preferences";
}

- (NSImage *)buttonImage
{
  return image;
}

//
#pragma mark - Helper methods
//
- (void)setupNativeControls
{
  NSView *original = view;
  NSSize size = [original frame].size;
  view = [[NSView alloc] initWithFrame:NSMakeRect(0, 0, size.width, size.height + 54)];
  [original setFrameOrigin:NSMakePoint(0, 54)];
  [original setAutoresizingMask:NSViewWidthSizable | NSViewMinYMargin];
  [view addSubview:original]; [original release];
  NSBox *scaleBox = [[[NSBox alloc] initWithFrame:NSMakeRect(7, 4, 121, 50)] autorelease];
  [scaleBox setTitle:@"Scale"];
  scaleBtn = [[[NSPopUpButton alloc] initWithFrame:NSMakeRect(4, 0, 105, 22) pullsDown:NO] autorelease];
  for (NSInteger numerator = 120; numerator <= 240; numerator += 30) {
    [scaleBtn addItemWithTitle:[NSString stringWithFormat:@"%ld%%", (long)(numerator * 100 / 120)]];
    [[scaleBtn lastItem] setTag:numerator];
  }
  [scaleBtn setTarget:self]; [scaleBtn setAction:@selector(nativeDisplayChanged:)];
  [[scaleBox contentView] addSubview:scaleBtn]; [view addSubview:scaleBox];
  NSBox *effectiveBox = [[[NSBox alloc] initWithFrame:NSMakeRect(139, 4, 243, 50)] autorelease];
  [effectiveBox setTitle:@"Effective size"];
  effectiveSize = [[[NSTextField alloc] initWithFrame:NSMakeRect(4, 0, 227, 22)] autorelease];
  [effectiveSize setEditable:NO]; [effectiveSize setSelectable:NO]; [effectiveSize setBezeled:NO];
  [effectiveSize setDrawsBackground:NO]; [effectiveSize setAlignment:NSCenterTextAlignment];
  [[effectiveBox contentView] addSubview:effectiveSize]; [view addSubview:effectiveBox];
  [rotationBtn removeAllItems];
  for (NSInteger turn = 0; turn < 4; turn++) {
    [rotationBtn addItemWithTitle:[NSString stringWithFormat:@"%ld degrees", (long)turn * 90]];
    [[rotationBtn lastItem] setTag:turn];
  }
  [reflectionBtn removeAllItems]; [reflectionBtn addItemWithTitle:@"None"]; [[reflectionBtn lastItem] setTag:0];
  [reflectionBtn addItemWithTitle:@"Mirrored"]; [[reflectionBtn lastItem] setTag:4];
  for (id button in [NSArray arrayWithObjects:rotationBtn, reflectionBtn, nil]) {
    [button setTarget:self]; [button setAction:@selector(nativeDisplayChanged:)];
  }
  [colorBtn setEnabled:NO]; /* Native background control has a separate compositor contract. */
}
- (void)updateNativeControls
{
  BOOL configurable = [systemScreen supportsDisplayTransactions] && [selectedDisplay isActive];
  [resolutionBtn setEnabled:configurable];
  [rateBtn setEnabled:configurable && [[rateBtn itemArray] count] > 1];
  [scaleBtn setEnabled:configurable]; [rotationBtn setEnabled:configurable]; [reflectionBtn setEnabled:configurable];
  NSUInteger scale = [selectedDisplay scaleNumerator];
  if (scale && ![[scaleBtn menu] itemWithTag:scale]) {
    [scaleBtn addItemWithTitle:[NSString stringWithFormat:@"%g%%", scale * 100.0 / 120]];
    [[scaleBtn lastItem] setTag:scale];
  }
  if (scale) [scaleBtn selectItemWithTag:scale];
  else { [scaleBtn addItemWithTitle:@"Unavailable"]; [scaleBtn selectItemWithTitle:@"Unavailable"]; }
  [rotationBtn selectItemWithTag:[selectedDisplay transform] & 3];
  [reflectionBtn selectItemWithTag:[selectedDisplay transform] & 4];
  NSSize logical = [selectedDisplay frame].size;
  [effectiveSize setStringValue:[NSString stringWithFormat:@"%g x %g points", logical.width, logical.height]];
}
- (void)nativeDisplayChanged:(id)sender
{
  if (![systemScreen supportsDisplayTransactions] || ![selectedDisplay isActive]) return;
  NSDictionary *mode = [[rateBtn selectedItem] representedObject];
  if (!mode) return;
  NSMutableArray *layout = [NSMutableArray array];
  for (NSDictionary *entry in [systemScreen currentLayout]) {
    NSMutableDictionary *changed = [[entry mutableCopy] autorelease];
    if ([[entry objectForKey:OSEDisplayIDKey] isEqual:[selectedDisplay uniqueID]]) {
      [changed setObject:mode forKey:OSEDisplayModeKey];
      [changed setObject:[NSNumber numberWithInteger:[[scaleBtn selectedItem] tag]] forKey:OSEDisplayScaleKey];
      [changed setObject:[NSNumber numberWithInteger:[[rotationBtn selectedItem] tag] |
        [[reflectionBtn selectedItem] tag]] forKey:OSEDisplayTransformKey];
    }
    [layout addObject:changed];
  }
  NXTConfirmDisplayLayout(systemScreen, layout);
}

- (void)fillRateButton
{
  NSString *resBtnTitle;
  NSString *rateTitle;
  NSString *resolutionTitle;
  NSDictionary *res;
  double rateValue = 0.0;
  NSString *rateFormat = @"%.2f Hz";

  [rateBtn removeAllItems];

  // Fill the buttion with items
  resBtnTitle = [resolutionBtn titleOfSelectedItem];
  for (res in [selectedDisplay allResolutions]) {
    resolutionTitle = [res objectForKey:OSEDisplayResolutionNameKey];
    if ([resolutionTitle isEqualToString:resBtnTitle]) {
      rateValue = [[res objectForKey:OSEDisplayResolutionRateKey] doubleValue];
      rateTitle = [NSString stringWithFormat:rateFormat, rateValue];
      [rateBtn addItemWithTitle:rateTitle];
      [[rateBtn itemWithTitle:rateTitle] setRepresentedObject:res];
    }
  }
}

- (void)updateRateButton
{
  NSString *rateTitle;

  if ([[rateBtn itemArray] count] == 1) {
    [rateBtn setEnabled:NO];
  } else {
    rateTitle = [NSString stringWithFormat:@"%.2f Hz", selectedDisplay.activeRate];
    [rateBtn selectItemWithTitle:rateTitle];
    [rateBtn setEnabled:YES];
  }  
}

- (void)setResolution
{
  NSDictionary *activeResolution;
  // NSString *resolutionTitle;
  NSDictionary *targetResolution = [[rateBtn selectedCell] representedObject];
  NSString *targetResolutionTitle = nil;
  NSString *lastGoodResolutionTitle = nil;

  if (targetResolution == nil) {
    NSLog(@"%s - resolution dictionary is nil! Resolution button is %@", __func__,
          [resolutionBtn title]);
    return;
  }

  targetResolutionTitle = [targetResolution objectForKey:OSEDisplayResolutionNameKey];
  if (lastGoodResolution) {
    lastGoodResolutionTitle = [lastGoodResolution objectForKey:OSEDisplayResolutionNameKey];
  }
  if (lastGoodResolution && [lastGoodResolutionTitle isEqualToString:targetResolutionTitle] &&
      [lastGoodResolution objectForKey:OSEDisplayResolutionRateKey] ==
          [targetResolution objectForKey:OSEDisplayResolutionRateKey]) {
    return;
  }

  // Save current resolution
  // activeResolution = [selectedDisplay activeResolution];
  // NSLog(@"%s: saving last good resolution - %@", __func__,
  //       [activeResolution objectForKey:OSEDisplayResolutionNameKey]);
  // [lastGoodResolution setObject:[selectedDisplay activeResolution]
  //                        forKey:[selectedDisplay outputName]];

  // Set resolution only to active display.
  // Display activating implemented in 'Screen' Preferences' module.
  if ([selectedDisplay isActive]) {
    // NSLog(@"%s - %@", __func__, [[rateBtn selectedCell] representedObject]);
    [systemScreen setDisplay:selectedDisplay resolution:[[rateBtn selectedCell] representedObject]];
  }
}

- (void)selectFirstEnabledMonitor
{
  NSArray *cells = [[monitorsList matrixInColumn:0] cells];

  for (int i = 0; i < [cells count]; i++) {
    if ([[cells objectAtIndex:i] isEnabled] == YES) {
      [monitorsList selectRow:i inColumn:0];
      break;
    }
  }

  [self monitorsListClicked:monitorsList];
}

- (void)saveDisplayConfig
{
  NSLog(@"Display: save current Display.confg");
  [systemScreen saveCurrentDisplayLayout];
}

//
#pragma mark - Action methods
//
- (IBAction)monitorsListClicked:(id)sender
{
  NSString *resolutionTitle;
  NSDictionary *activeResolution;

  ASSIGN(selectedDisplay, [[sender selectedCell] representedObject]);
  ASSIGNCOPY(selectedDisplayName, [selectedDisplay outputName]);
  if (!selectedDisplay) return;
  NSLog(@"%s: selected monitor with title: %@", __func__, [selectedDisplay outputName]);

  // Resolution
  [resolutionBtn removeAllItems];
  for (NSDictionary *res in [selectedDisplay allResolutions]) {
    resolutionTitle = [res objectForKey:OSEDisplayResolutionNameKey];
    [resolutionBtn addItemWithTitle:resolutionTitle];
  }
  activeResolution = [selectedDisplay activeResolution];
  resolutionTitle = [activeResolution objectForKey:OSEDisplayResolutionNameKey];
  [resolutionBtn selectItemWithTitle:resolutionTitle];
  [lastGoodResolution setObject:activeResolution forKey:selectedDisplayName];
  NSLog(@"%s: last good reolution: %@", __func__, resolutionTitle);

  // Rate button filled here. Items tagged with resolution description object
  [self fillRateButton];
  [self updateRateButton];
  if ([systemScreen isNativeDisplay]) [self updateNativeControls];

  if ([selectedDisplay isGammaSupported] == YES) {
    [gammaSlider setEnabled:YES];
    [gammaField setEnabled:YES];
    [brightnessSlider setEnabled:YES];
    [brightnessField setEnabled:YES];
    [self updateGammaValues];
  } else {
    [gammaSlider setEnabled:NO];
    [gammaField setEnabled:NO];
    [brightnessSlider setEnabled:NO];
    [brightnessField setEnabled:NO];
  }
}

- (void)updateGammaValues
{
  NSString *gamma = [NSString stringWithFormat:@"%.2f", [selectedDisplay gamma]];
  [gammaSlider setFloatValue:[gamma floatValue]]; [gammaField setStringValue:gamma];
  CGFloat brightness = [selectedDisplay gammaBrightness] * 100;
  [brightnessSlider setFloatValue:brightness];
  [brightnessField setStringValue:[NSString stringWithFormat:@"%.0f", brightness]];
}

- (IBAction)resolutionClicked:(id)sender
{
  [self fillRateButton];
  if ([systemScreen isNativeDisplay]) [self nativeDisplayChanged:sender];
  else [self setResolution];
  [self updateRateButton];
}

- (IBAction)rateClicked:(id)sender
{
  if ([systemScreen isNativeDisplay]) [self nativeDisplayChanged:sender];
  else [self setResolution];
}

- (IBAction)sliderMoved:(id)sender
{
  CGFloat value = [sender floatValue];

  if (saveConfigTimer && [saveConfigTimer isValid]) {
    [saveConfigTimer invalidate];
  }
  saveConfigTimer = [NSTimer scheduledTimerWithTimeInterval:2
                                                     target:self
                                                   selector:@selector(saveDisplayConfig)
                                                   userInfo:nil
                                                    repeats:NO];
  [saveConfigTimer retain];

  if (sender == gammaSlider) {
    // NSLog(@"Gamma slider moved");
    [gammaField setStringValue:[NSString stringWithFormat:@"%.2f", value]];

    if ([systemScreen isNativeDisplay]) { [selectedDisplay setGamma:value]; [self updateGammaValues]; }
    else dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_HIGH, 0), ^{
      [selectedDisplay setGamma:value];
    });
  } else if (sender == brightnessSlider) {
    // NSLog(@"Brightness slider moved");
    // if (value > 1.0) value = 1.0;
    [brightnessField setIntValue:[sender intValue]];
    if ([systemScreen isNativeDisplay]) { [selectedDisplay setGammaBrightness:value / 100]; [self updateGammaValues]; }
    else dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_HIGH, 0), ^{
      [selectedDisplay setGammaBrightness:value / 100];
    });
  } else {
    NSLog(@"Unknown slider moved");
  }
}

- (IBAction)backgroundChanged:(id)sender
{
  NSColor *color = [sender color];
  NSColor *rgbColor = [color colorUsingColorSpaceName:NSDeviceRGBColorSpace];

  // NSLog(@"Display: backgroundChanged: %@", [sender className]);
  if ([systemScreen setBackgroundColorRed:[rgbColor redComponent]
                                    green:[rgbColor greenComponent]
                                     blue:[rgbColor blueComponent]] == YES) {
    OSEDefaults *defs = [OSEDefaults globalUserDefaults];
    NSDictionary *dBack;

    dBack = @{
      @"Red" : [NSNumber numberWithFloat:[color redComponent]],
      @"Green" : [NSNumber numberWithFloat:[color greenComponent]],
      @"Blue" : [NSNumber numberWithFloat:[color blueComponent]],
      @"Alpha" : [NSNumber numberWithFloat:1.0]
    };
    [defs setObject:dBack forKey:OSEDesktopBackgroundColor];
  }
}

//
#pragma mark - Browser delegate (monitors list)
//
- (NSString *)browser:(NSBrowser *)sender titleOfColumn:(NSInteger)column
{
  if (column > 0)
    return @"";

  return @"Monitors";
}

- (void)browser:(NSBrowser *)sender
    createRowsForColumn:(NSInteger)column
               inMatrix:(NSMatrix *)matrix
{
  NSBrowserCell *bc;

  if (column > 0)
    return;

  for (OSEDisplay *d in [systemScreen connectedDisplays]) {
    [matrix addRow];
    bc = [matrix cellAtRow:[matrix numberOfRows] - 1 column:0];
    [bc setTitle:[d outputName]];
    [bc setRepresentedObject:d];
    [bc setLeaf:YES];
    [bc setRefusesFirstResponder:YES];
    [bc setEnabled:[d isActive]];
  }
}

//
#pragma mark - TextField Delegate
//
- (void)controlTextDidEndEditing:(NSNotification *)aNotification
{
  id tf = [aNotification object];
  CGFloat value = [tf floatValue];

  NSLog(@"Display set gamma: %f", value);

  if (tf == gammaField) {
    [gammaSlider setFloatValue:value];
    [selectedDisplay setGamma:value];
    [tf setFloatValue:value];
  } else if (tf == brightnessField) {
    [selectedDisplay setGammaBrightness:value / 100];
    value = [selectedDisplay gammaBrightness] * 100;
    [brightnessSlider setFloatValue:value];
    // [tf setIntValue:[strVal intValue]];
    [tf setFloatValue:value];
  }

  if ([systemScreen isNativeDisplay]) [self updateGammaValues];
  // Gamma changes also need to reach the saved display profile.
  // That's why saving display configuration is here.
  [systemScreen saveCurrentDisplayLayout];
}

// Notifications
- (void)screenDidUpdate:(NSNotification *)aNotif
{
  NSString *name = [[selectedDisplayName copy] autorelease];
  [monitorsList reloadColumn:0];
  NSArray *cells = [[monitorsList matrixInColumn:0] cells];
  NSUInteger index;
  for (index = 0; index < [cells count]; index++) {
    id cell = [cells objectAtIndex:index];
    if ([cell isEnabled] && [[cell title] isEqual:name]) {
      [monitorsList selectRow:index inColumn:0]; [self monitorsListClicked:monitorsList]; return;
    }
  }
  [self selectFirstEnabledMonitor];
}

- (void)screenDidChange:(NSNotification *)aNotif
{
  if ([systemScreen isNativeDisplay]) return;
  NXTCountdownAlert *alert;
  NSDictionary *oldResolution = [lastGoodResolution objectForKey:[selectedDisplay outputName]];
  NSDictionary *activeResolution = [selectedDisplay activeResolution];

  NSLog(@"%s: Received ScreenDidChange notification", __func__);

  if ([[activeResolution objectForKey:OSEDisplayResolutionNameKey]
          isEqualToString:[oldResolution objectForKey:OSEDisplayResolutionNameKey]] != NO) {
    NSLog(@"%s: Resolution has been reverted to last good. Keep it!", __func__);
    return;
  }

    alert = [[NXTCountdownAlert alloc]
          initWithTitle:@"Display resolution"
                message:@"Do you want to keep current display resolution?\n"
                         "Resolution will be reverted in %i seconds."
          defaultButton:@"Revert"
        alternateButton:@"Keep"
            otherButton:nil];
  [alert setCountDownPeriod:5];

  if ([alert runModal] == NSAlertDefaultReturn) {
    NSDictionary *goodResolution = [lastGoodResolution objectForKey:[selectedDisplay outputName]];
    NSLog(@"%s: %@ goodResolution: %@", __func__, [selectedDisplay outputName], lastGoodResolution);
    if (goodResolution) {
      NSLog(@"Revert resoltuion to previous - %@.", goodResolution);
      [systemScreen setDisplay:selectedDisplay resolution:goodResolution];
    } else {
      NSLog(@"%s: PROBLEM: can't revert to previous resolution - it's nil", __func__);
    }
  } else {
    NSLog(@"Keep current resoltuion.");
  }
  [alert release];
}


@end
