/* Private, value-based seat settings. SPDX-License-Identifier: GPL-2.0-or-later */
#import <Foundation/Foundation.h>
NSDictionary *OSEWaylandInputSettings(void);
BOOL OSEChangeWaylandInputSettings(NSString *kind, NSDictionary *changes);
