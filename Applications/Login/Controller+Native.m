/* Native greeter adaptation of the existing Login panel and alerts.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import "Controller.h"
#include <unistd.h>
#include <stdlib.h>

@implementation Controller (NativeLogin)
- (BOOL)isNativeLogin
{
  return [[[[NSProcessInfo processInfo] environment] objectForKey:@"GREETD_SOCK"] length] > 0;
}
- (id)loginPreference:(NSString *)key
{
  id value = [prefs objectForKey:key];
  if (value || ![self isNativeLogin]) return value;
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
  if (![self isNativeLogin] || getuid()==0 || geteuid()==0) return;
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
- (void)authenticateNative:(id)sender
{
  if (![self isNativeLogin]) return;
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
  if (![self isNativeLogin]) return;
  panelExitCode = 0;
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
