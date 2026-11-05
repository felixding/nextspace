/* -*- mode: objc -*- */
//
// Project: NEXTSPACE - Login application
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

#import <AppKit/AppKit.h>
#import <GNUstepGUI/GSDisplayServer.h>
#import <SystemKit/OSEDefaults.h>
#import <SystemKit/OSEPower.h>
#import <DesktopKit/NXTAlert.h>
#import "LoginWindow.h"
#import "GreetdSession.h"

@interface Controller : NSObject <GreetdSessionDelegate>
{
  IBOutlet LoginWindow *window;
  IBOutlet id hostnameField;
  IBOutlet id fieldsImage;
  IBOutlet id fieldsLabelImage;
  IBOutlet id panelImageView;
  IBOutlet id userName;
  IBOutlet id password;
  IBOutlet id shutDownBtn;
  IBOutlet id restartBtn;
  BOOL didLoadPanel, isWindowActive;
  OSEDefaults *prefs;
  GreetdSession *nativeLogin;
  BOOL nativePowerPending;
}
- (void)displayHostname;
- (void)clearFields;
- (void)setWindowVisible:(BOOL)visible;
- (id)loginPreference:(NSString *)key;
- (NSString *)lastLoggedInUser;
- (void)setLastLoggedInUser:(NSString *)user;
- (void)startNativeLogin;
- (void)authenticate:(id)sender;
- (void)restart:(id)sender;
- (void)shutDown:(id)sender;
- (void)requestNativePower:(OSEPowerAction)action;
@end
