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

#import "Controller.h"
#include <unistd.h>
#include <stdlib.h>

static NSImage *LoginImage(NSString *name, NSImage *fallback)
{
  NSString *directory = [[NSBundle mainBundle] pathForResource:@"Login" ofType:@"gorm"];
  NSString *path = [directory stringByAppendingPathComponent:[name stringByAppendingPathExtension:@"tiff"]];
  NSImage *image = [[[NSImage alloc] initWithContentsOfFile:path] autorelease];
  return image ?: fallback;
}

@implementation Controller
- (void)awakeFromNib
{
  NSRect rect;
  NSString *user;

  if (didLoadPanel) return;
  didLoadPanel = YES;

  NSLog(@"awakeFromNib");

  [panelImageView setImage:LoginImage(@"Panel", [panelImageView image])];
  [fieldsImage setImage:LoginImage(@"Fields", [fieldsImage image])];
  [fieldsLabelImage setImage:LoginImage(@"FieldNames", [fieldsLabelImage image])];
  // The archived panel uses gray normal images and white/red highlighted images.
  [shutDownBtn setImage:LoginImage(@"powerbuttonup", [shutDownBtn image])];
  [shutDownBtn setAlternateImage:LoginImage(@"powerbuttondown", [shutDownBtn alternateImage])];
  [restartBtn setImage:LoginImage(@"restartbuttonup", [restartBtn image])];
  [restartBtn setAlternateImage:LoginImage(@"restartbuttondown", [restartBtn alternateImage])];

  // Adjust window size to background image size
  rect = [window frame];
  rect.size = [[panelImageView image] size];
  [window setFrame:rect display:NO];

  [shutDownBtn setRefusesFirstResponder:YES];
  [restartBtn setRefusesFirstResponder:YES];
  [fieldsImage setRefusesFirstResponder:YES];
  [fieldsLabelImage setRefusesFirstResponder:YES];
  [panelImageView setRefusesFirstResponder:YES];

  // Open preferences
  prefs = [[OSEDefaults alloc] initWithSystemDefaults];

  [hostnameField retain];
  [self displayHostname];

  user = [self lastLoggedInUser];
  if (user && [user length] > 0) {
    [userName setStringValue:user];
  }

  [password setEchosBullets:NO];

  NSLog(@"awakeFromNib: end");
}

- (void)displayHostname
{
  char hostname[256], displayname[256];
  int namelen = 256, index = 0;
  NSString *host_name = nil;

  // Initialize hostname
  gethostname(hostname, namelen);
  for (index = 0; index < 256 && hostname[index] != '.'; index++) {
    displayname[index] = hostname[index];
  }
  displayname[index] = 0;
  host_name = [NSString stringWithCString:displayname];
  [hostnameField setStringValue:host_name];

  if ([[self loginPreference:@"DisplayHostName"] integerValue] == 0) {
    if ([hostnameField superview] != nil) {
      [hostnameField removeFromSuperview];
    }
  } else if ([hostnameField superview] == nil) {
    [panelImageView addSubview:hostnameField];
  }
}

- (void)defaultsDidChange:(NSNotification *)notif
{
  [prefs reload];
  [self displayHostname];
}

- (void)clearFields
{
  NSString *user = [self lastLoggedInUser];

  [password setStringValue:@""];

  if (user && [user length] > 0) {
    [userName setStringValue:user];
    [window makeFirstResponder:password];
  } else {
    [userName setStringValue:@""];
    [window makeFirstResponder:userName];
  }
}

- (void)applicationDidFinishLaunching:(NSNotification *)notification
{
  [self startNativeLogin];
}

- (NSString *)lastLoggedInUser
{
  return [[self loginPreference:@"RememberLastLoggedInUser"] integerValue] == 1 ?
    [[NSUserDefaults standardUserDefaults] stringForKey:@"NativeLastLoggedInUser"] : nil;
}

- (void)setLastLoggedInUser:(NSString *)user
{
  [[NSUserDefaults standardUserDefaults] setObject:user ?: @"" forKey:@"NativeLastLoggedInUser"];
  [[NSUserDefaults standardUserDefaults] synchronize];
}

- (void)setWindowVisible:(BOOL)visible
{
  [self clearFields];
  if (visible) { [window center]; [window makeKeyAndOrderFront:self]; }
  else [window orderOut:self];
}

- (void)restart:(id)sender
{
  if (NXTRunAlertPanel(_(@"Restart"), _(@"Do you really want to restart the computer?"),
      _(@"Restart"), _(@"Cancel"), nil) == NSAlertDefaultReturn)
    [self requestNativePower:OSEPowerReboot];
}

- (void)shutDown:(id)sender
{
  if (NXTRunAlertPanel(_(@"Power"), _(@"Do you really want to turn off the computer?"),
      _(@"Turn it off"), _(@"Cancel"), nil) == NSAlertDefaultReturn)
    [self requestNativePower:OSEPowerOff];
}


- (id)loginPreference:(NSString *)key
{
  id value = [prefs objectForKey:key];
  if (value) return value;
  static NSDictionary *bundled;
  if (!bundled) bundled = [[NSDictionary dictionaryWithContentsOfFile:
    [[NSBundle mainBundle] pathForResource:@"Login" ofType:nil]] retain];
  return [bundled objectForKey:key];
}
- (void)setNativeControlsEnabled:(BOOL)enabled
{
  [userName setEnabled:enabled]; [password setEnabled:enabled];
  [shutDownBtn setEnabled:enabled]; [restartBtn setEnabled:enabled];
}
- (void)nativeScreensChanged:(NSNotification *)notification
{
  if (isWindowActive && [window isVisible]) [window center];
}
- (void)startNativeLogin
{
  if (getuid()==0 || geteuid()==0) return;
  if (![GSCurrentServer() respondsToSelector:@selector(logicalDesktopBounds)]) {
    fprintf(stderr, "Login: greetd requires the native Wayland backend.\n");
    exit(1);
  }
  NSString *path = [[[NSProcessInfo processInfo] environment] objectForKey:@"GREETD_SOCK"];
  nativeLogin = [[GreetdSession alloc] initWithSocketPath:path delegate:self];
  [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(nativeScreensChanged:)
    name:NSApplicationDidChangeScreenParametersNotification object:nil];
  [self setWindowVisible:YES];
  isWindowActive = YES;
}
- (void)authenticate:(id)sender
{
  if ([nativeLogin isActive] || nativePowerPending) return;
  if (sender == userName) { [window makeFirstResponder:password]; return; }
  NSString *user = [userName stringValue];
  if (![user length]) { [window makeFirstResponder:userName]; return; }
  NSArray *arguments = [self loginPreference:@"NativeSessionCommand"];
  if (!arguments) arguments = [NSArray arrayWithObject:@"/usr/NextSpace/bin/nextspace-wayland-session"];
  [self setNativeControlsEnabled:NO];
  [nativeLogin authenticateUser:user password:[password stringValue] arguments:arguments];
  [password setStringValue:@""];
}
- (void)loginServicePrompt:(NSMutableDictionary *)message
{
  NSString *kind = [message objectForKey:@"auth_message_type"];
  BOOL input = [kind isEqual:@"secret"] || [kind isEqual:@"visible"];
  NXTAlert *prompt = [[NXTAlert alloc] initWithTitle:_(@"Login")
    message:[message objectForKey:@"auth_message"] defaultButton:_(@"Continue")
    alternateButton:_(@"Cancel") otherButton:nil];
  NSTextField *field = nil;
  if (input) {
    field = [kind isEqual:@"secret"] ? [[NSSecureTextField alloc] initWithFrame:NSMakeRect(0,0,320,24)] :
      [[NSTextField alloc] initWithFrame:NSMakeRect(0,0,320,24)];
    [field setTarget:prompt];
    [field setAction:@selector(buttonPressed:)];
    [field setTag:NSAlertDefaultReturn];
    [prompt setAccessoryView:field];
    [[prompt panel] makeFirstResponder:field];
  }
  NSInteger result = [prompt runModal];
  if (result != NSAlertDefaultReturn) [message setObject:[NSNumber numberWithBool:YES] forKey:@"cancelled"];
  else if (input) [message setObject:[[[field stringValue] copy] autorelease] forKey:@"response"];
  [field setStringValue:@""];
  [field release]; [prompt release];
}
- (void)loginServiceWillStart:(NSString *)user
{
  [self setLastLoggedInUser:user];
  [window shrinkPanel];
  [self setWindowVisible:NO];
  isWindowActive = NO;
}
- (void)loginServiceFinished:(NSDictionary *)result
{
  if ([[result objectForKey:@"success"] boolValue]) { [NSApp stop:self]; return; }
  [self setNativeControlsEnabled:YES];
  [self setWindowVisible:YES];
  isWindowActive = YES;
  if (![[result objectForKey:@"cancelled"] boolValue]) {
    [window shakePanel];
    if (![[result objectForKey:@"authentication_error"] boolValue])
      NXTRunAlertPanel(_(@"Login"), @"%@", _(@"OK"), nil, nil,
        [result objectForKey:@"message"] ?: _(@"Unable to start the session."));
  }
}
- (void)requestNativePower:(OSEPowerAction)action
{
  if ([nativeLogin isActive] || nativePowerPending) return;
  nativePowerPending = YES;
  [self setNativeControlsEnabled:NO];
  [password setStringValue:@""];
  [NSThread detachNewThreadSelector:@selector(nativePower:) toTarget:self
    withObject:[NSNumber numberWithUnsignedInteger:action]];
}
- (void)nativePower:(NSNumber *)action
{
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  NSError *error = nil;
  BOOL accepted = [OSEPower requestAction:[action unsignedIntegerValue] error:&error];
  NSMutableDictionary *result = [NSMutableDictionary dictionaryWithObject:[NSNumber numberWithBool:accepted] forKey:@"accepted"];
  if (error) [result setObject:[error localizedDescription] forKey:@"message"];
  [self performSelectorOnMainThread:@selector(nativePowerFinished:) withObject:result waitUntilDone:YES];
  [pool drain];
}
- (void)nativePowerFinished:(NSDictionary *)result
{
  if ([[result objectForKey:@"accepted"] boolValue]) return;
  nativePowerPending = NO;
  [self setNativeControlsEnabled:YES];
  NXTRunAlertPanel(_(@"Power"), @"%@", _(@"OK"), nil, nil,
    [result objectForKey:@"message"] ?: _(@"The power request was not accepted."));
}
@end
