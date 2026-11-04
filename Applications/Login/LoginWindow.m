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
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#import <GNUstepGUI/GSDisplayServer.h>

#import <SystemKit/OSEScreen.h>
#import <SystemKit/OSEDisplay.h>

#import "LoginWindow.h"

@interface NSObject (LoginDisplayModel)
- (OSEScreen *)systemScreen;
@end

#define ANIMATION_DELAY 250
#define NATIVE_ANIMATION_DURATION 0.2

static BOOL nativeWindowPlacement(void)
{ return [GSCurrentServer() respondsToSelector:@selector(logicalDesktopBounds)]; }

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

static void movePanel(Display *display, Window native, int x, int y)
{
  XMoveWindow(display, native, x, y);
  XSync(display, False);
  usleep(ANIMATION_DELAY);
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

/*
   This method is a temporary solution. GNUstep doesn't count screen size and
   display laying out to each other on multi-display setups. For example, if 2
   displays stacked side-by-side with top edges aligned by the Y axis
   (deafult layout) we need to add bottom side offset to point.y because GNUstep
   coordinate system starts at bottom left corner. If displays aligned by bottom
   edge - no offset have to be added.
   The worst case is when displays are not aligned along some edge(s).
   In this case XRandR screen dimensions increase while GNUstep is not aware of
   such changes. We need to adjust `point` to be correct in GNUstep coordinate
   system and screen dimensions.
*/
- (void)center
{
  if (nativeWindowPlacement()) {
    NSScreen *screen = [self screen] ?: [NSScreen mainScreen];
    if (!screen) return;
    NSRect bounds = [screen frame], frame = [self frame];
    [self setFrameOrigin:NSMakePoint(floor(NSMidX(bounds) - NSWidth(frame) / 2),
                                    floor(NSMidY(bounds) - NSHeight(frame) / 2))];
    return;
  }
  OSEScreen *screen = [[NSApp delegate] systemScreen];
  if (!screen) { [super center]; return; }
  OSEDisplay *display = nil;
  NSSize screenSize;
  NSRect displayRect;
  NSRect windowRect = [self frame];
  NSPoint newOrigin;

  NSDebugLLog(@"Screen", @"center");

  // Get NEXTSPACE display rect
  if (screen != nil) {
    [screen refreshDisplays];
    if ([[screen activeDisplays] count] > 0) {
      display = [screen mainDisplay];
      if (!display) {
        NSDebugLLog(@"Screen", @"No main display - using first active.");
        display = [[screen activeDisplays] objectAtIndex:0];
      }
    } else if ([[screen connectedDisplays] count] > 0) {
      NSDebugLLog(@"Screen", @"No active displays left - activating first connected.");
      display = [[screen connectedDisplays] objectAtIndex:0];
      [screen activateDisplay:display];
    }
    screenSize = [screen sizeInPixels];
    displayRect = [display frame];

    NSDebugLLog(@"Screen", @"Screen size   : %4.0f x %4.0f", screenSize.width, screenSize.height);
  }

  NSDebugLLog(@"Screen", @"Display frame : %4.0f x %4.0f  (%4.0f, %4.0f)", displayRect.size.width,
              displayRect.size.height, displayRect.origin.x, displayRect.origin.y);

  NSDebugLLog(@"Screen", @"Window frame  : %4.0f x %4.0f  (%4.0f, %4.0f)", windowRect.size.width,
              windowRect.size.height, windowRect.origin.x, windowRect.origin.y);

  // Calculate the new position of the window on display.
  newOrigin.x = displayRect.size.width / 2 - windowRect.size.width / 2;
  newOrigin.x += displayRect.origin.x;
  newOrigin.y = displayRect.size.height / 2 - windowRect.size.height / 2;
  newOrigin.y += displayRect.origin.y;
  // displayRect is presented system(Xlib) coordiante system.
  // Convert newOrigin into OpenStep coordinate system (non-flipped).
  newOrigin.y = screenSize.height - (newOrigin.y + windowRect.size.height);
  NSDebugLLog(@"Screen", @"New origin    :              (%4.0f, %4.0f)", newOrigin.x, newOrigin.y);

  [self setFrameOrigin:newOrigin];
}

- (NSPoint)windowScreenOrigin
{
  NSRect allScreensFrame = NSZeroRect;
  NSRect frame = [self frame];
  NSPoint origin = frame.origin;

  for (NSScreen *scr in [NSScreen screens]) {
    allScreensFrame = NSUnionRect(allScreensFrame, [scr frame]);
  }

  origin.y = NSMaxY(allScreensFrame) - NSMaxY(frame);

  NSLog(@"[screen origin] Y -> Xlib: %.0f Max: %.0f Screen: %.0f (Max: %.0f)", origin.y,
        NSMaxY(frame), allScreensFrame.origin.y, NSMaxY(allScreensFrame));

  return origin;
}

- (void)shakePanel
{
  BOOL native = nativeWindowPlacement();
  Display *dpy = native ? NULL : [GSCurrentServer() serverDevice];
  Window panel = native ? 0 : (Window)[GSCurrentServer() windowDevice:[self windowNumber]];
  NSRect original = [self frame];
  NSPoint origin = native ? original.origin : [self windowScreenOrigin];
  int x, initial_x, y;
  int i, j, num_steps, num_shakes;

  initial_x = x = (int)origin.x;
  y = (int)origin.y;

  num_steps = 4;
  num_shakes = 14;
  if (native) {
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
    return;
  }
  for (i = 0; i < num_shakes; i++) {
    for (j = 0; j < num_steps; j++) {
      x += 10;
      movePanel(dpy, panel, x, y);
    }
    for (j = 0; j < num_steps * 2; j++) {
      x -= 10;
      movePanel(dpy, panel, x, y);
    }
    for (j = 0; j < num_steps; j++) {
      x += 10;
      movePanel(dpy, panel, x, y);
    }
  }
  XMoveWindow(dpy, panel, initial_x, y);
  XSync(dpy, False);
}

#define SHRINK_FACTOR 2

- (void)shrinkPanel
{
  NSRect windowRect = [self frame];
  if (nativeWindowPlacement()) {
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
    return;
  }
  Display *dpy = [GSCurrentServer() serverDevice];
  Window panel = (Window)[GSCurrentServer() windowDevice:[self windowNumber]];
  NSPoint origin = [self windowScreenOrigin];
  GC gc;
  Pixmap pixmap;
  XImage *windowSnap;
  int x, y, width, height, initial_x, initial_width;

  initial_x = x = (int)origin.x;
  y = (int)origin.y;
  initial_width = width = (int)windowRect.size.width;
  height = (int)windowRect.size.height;

  pixmap = XCreatePixmap(dpy, panel, width, height, 24);
  gc = XCreateGC(dpy, pixmap, 0, NULL);

  windowSnap = XGetImage(dpy, panel, 0, 0, width, height, AllPlanes, XYPixmap);
  XPutImage(dpy, pixmap, gc, windowSnap, 0, 0, 0, 0, width, height);

  while ((width - SHRINK_FACTOR) > 0) {
    x += SHRINK_FACTOR / 2;
    width -= SHRINK_FACTOR;

    XMoveResizeWindow(dpy, panel, x, y, width, height);
    XCopyArea(dpy, pixmap, pixmap, gc, SHRINK_FACTOR / 2, 0, width, height, 0, 0);
    XSetWindowBackgroundPixmap(dpy, panel, pixmap);
    XSync(dpy, False);
    usleep(ANIMATION_DELAY);
  }

  // Restore original window size. Don't call XSync and let Controller hide
  // panel before XMoveResizeWindow results will  made visible.
  XMoveResizeWindow(dpy, panel, initial_x, y, initial_width, height);
  XSync(dpy, False);

  XFree(windowSnap);
  XFreeGC(dpy, gc);
  XFreePixmap(dpy, pixmap);
}

@end
