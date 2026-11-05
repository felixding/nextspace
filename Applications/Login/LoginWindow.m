/* -*- mode: objc -*- */
//
// Project: NEXTSPACE - Login application
//
// Copyright (C) 2014-2019 Sergii Stoian
//
// Description: borderless window that centers in active display,
//              shakes on user authentication failure and shrinks
//              on success. Other window control functions are
//              placed into Controller.
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

#import <unistd.h>
#include <math.h>
#include <time.h>

#import "LoginWindow.h"

#define NATIVE_ANIMATION_DURATION 0.2

static void flushNativePanel(LoginWindow *window, NSRect expected)
{
  NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:NATIVE_ANIMATION_DURATION];
  // AppKit updates the frame when Wayland acknowledges it. Finish that move
  // before a later request or restoration can be skipped against a stale frame.
  do {
    [window displayIfNeeded];
    [[NSRunLoop currentRunLoop] runMode:NSDefaultRunLoopMode
      beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.001]];
  } while (!NSEqualRects([window frame], expected) && [deadline timeIntervalSinceNow] > 0);
}

static NSTimeInterval animationElapsed(struct timespec started)
{
  struct timespec now;
  clock_gettime(CLOCK_MONOTONIC, &now);
  return now.tv_sec - started.tv_sec + (now.tv_nsec - started.tv_nsec) / 1000000000.0;
}

@implementation LoginWindow

// It was neccesary to override this method to get the borderless
// window since it is not available from InterfaceBuilder.
- (id)initWithContentRect:(NSRect)contentRect
                styleMask:(NSUInteger)styleMask
                  backing:(NSBackingStoreType)bufferingType
                    defer:(BOOL)flag
{
  return [super initWithContentRect:contentRect
                          styleMask:NSBorderlessWindowMask
                            backing:bufferingType
                              defer:flag];
}

- (BOOL)canBecomeKeyWindow
{
  return YES;
}

- (BOOL)canBecomeMainWindow
{
  // If set to YES login window appears regrdless of
  // "Visible at launch time" bit set
  return NO;
}

- (void)center
{
  NSScreen *screen = [self screen] ?: [NSScreen mainScreen];
  if (!screen) return;
  NSRect bounds = [screen frame], frame = [self frame];
  [self setFrameOrigin:NSMakePoint(floor(NSMidX(bounds) - NSWidth(frame) / 2),
                                  floor(NSMidY(bounds) - NSHeight(frame) / 2))];
}

- (void)shakePanel
{
  NSRect original = [self frame];
  int num_steps = 4, num_shakes = 14;
  struct timespec started;
  clock_gettime(CLOCK_MONOTONIC, &started);
  int step = 1;
  @try {
    do {
      int phase = step % (num_steps * 4);
      int offset = phase < num_steps ? phase :
        (phase < num_steps * 3 ? num_steps * 2 - phase : phase - num_steps * 4);
      NSRect frame = original;
      frame.origin.x += offset * 10;
      [self setFrame:frame display:NO];
      flushNativePanel(self, frame);
      usleep(16000);
      step = MAX(step + 1, (int)(animationElapsed(started) / NATIVE_ANIMATION_DURATION * num_steps * 4 * num_shakes));
    } while (step < num_steps * 4 * num_shakes);
  } @finally {
    [self setFrame:original display:YES];
    flushNativePanel(self, original);
  }
}

#define SHRINK_FACTOR 2

- (void)shrinkPanel
{
  NSRect windowRect = [self frame];
  NSView *content = [self contentView];
  NSRect bounds = [content bounds];
  BOOL autoresizes = [content autoresizesSubviews];
  struct timespec started;
  clock_gettime(CLOCK_MONOTONIC, &started);
  [content setAutoresizesSubviews:NO];
  @try {
    CGFloat width = NSWidth(windowRect) - SHRINK_FACTOR;
    while (width > 0) {
      CGFloat inset = (NSWidth(windowRect) - width) / 2;
      NSRect frame = NSMakeRect(NSMinX(windowRect) + inset, NSMinY(windowRect), width, NSHeight(windowRect));
      [self setFrame:frame display:NO];
      [content setBounds:NSMakeRect(NSMinX(bounds) + inset, NSMinY(bounds), width, NSHeight(bounds))];
      [content setNeedsDisplay:YES];
      flushNativePanel(self, frame);
      usleep(16000);
      // Skip obsolete frames instead of extending the animation at higher densities.
      width = MIN(width - SHRINK_FACTOR,
        floor(NSWidth(windowRect) * (1 - animationElapsed(started) / NATIVE_ANIMATION_DURATION) / SHRINK_FACTOR) * SHRINK_FACTOR);
    }
  } @finally {
    [self setFrame:windowRect display:NO];
    [content setBounds:bounds];
    [content setAutoresizesSubviews:autoresizes];
    [content setNeedsDisplay:YES];
    flushNativePanel(self, windowRect);
  }
}

@end
