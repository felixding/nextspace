/* Shared display confirmation for Preferences modules.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import <Foundation/Foundation.h>
@class OSEScreen;

/* Returns YES only for a confirmed layout. The compositor owns rollback if the
   application stops, its modal loop stalls, or the confirmation arrives late. */
BOOL NXTConfirmDisplayLayout(OSEScreen *screen, NSArray *layout);
