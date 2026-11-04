/* SPDX-License-Identifier: GPL-2.0-or-later */
#import "NXTDisplayConfiguration.h"
#import "NXTCountdownAlert.h"
#import <SystemKit/OSEScreen.h>

BOOL NXTConfirmDisplayLayout(OSEScreen *screen, NSArray *layout)
{
  if (![screen supportsDisplayTransactions]) return [screen applyDisplayLayout:layout];
  NSDictionary *result = [screen beginDisplayLayout:layout timeout:5000];
  if (!result || [[result objectForKey:@"status"] intValue] != 1) {
    NXTAlert *failure = [[NXTAlert alloc] initWithTitle:@"Display settings"
      message:@"The display settings could not be applied." defaultButton:@"OK" alternateButton:nil otherButton:nil];
    [failure runModal]; [failure release];
    return NO;
  }
  NXTCountdownAlert *alert = [[NXTCountdownAlert alloc] initWithTitle:@"Display settings"
    message:@"Do you want to keep these display settings?\nSettings will revert in %i seconds."
    defaultButton:@"Revert" alternateButton:@"Keep" otherButton:nil];
  [alert setCountDownPeriod:5];
  NSInteger choice = [alert runModal];
  [alert release];
  BOOL kept = choice == NSAlertAlternateReturn && [screen confirmDisplayLayout];
  if (kept) [screen saveCurrentDisplayLayout];
  else [screen cancelDisplayLayout];
  [screen refreshDisplays];
  return kept;
}
