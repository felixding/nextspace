/* WaylandInputServer - Keyboard input handling for Wayland backend

   Copyright (C) 2024 Free Software Foundation, Inc.

   This file is part of the GNUstep Backend.

   This library is free software; you can redistribute it and/or
   modify it under the terms of the GNU Lesser General Public
   License as published by the Free Software Foundation; either
   version 2 of the License, or (at your option) any later version.

   This library is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
   Lesser General Public License for more details.

   You should have received a copy of the GNU Lesser General Public
   License along with this library; see the file COPYING.LIB.
   If not, see <http://www.gnu.org/licenses/> or write to the
   Free Software Foundation, 51 Franklin Street, Fifth Floor,
   Boston, MA 02110-1301, USA.
*/

#ifndef _WaylandInputServer_h_INCLUDE
#define _WaylandInputServer_h_INCLUDE

#include <AppKit/NSInputServer.h>
#include <AppKit/NSEvent.h>
#include <stdint.h>

/* Text edits share AppKit's keyboard queue with forwarded keys. */
@interface WaylandTextInputEvent : NSEvent
{
  NSDictionary *_transaction;
}
+ (id)eventWithTransaction:(NSDictionary *)transaction window:(NSInteger)window;
- (NSDictionary *)transaction;
@end

@interface WaylandInputServer : NSInputServer
{
  int       focused_window_id;
  struct _WaylandConfig *_config;
  struct zwp_text_input_v3 *_textInput;
  struct wl_surface *_entered;
  id _client;
  NSMutableDictionary *_pending;
  NSDictionary *_snapshot;
  NSUInteger _generation;
  uint32_t _serial;
  BOOL _enabled, _scheduled, _applying, _canSend, _reset, _changedByMethod;
}

- (id)initWithConfig:(struct _WaylandConfig *)config;
- (void)scheduleUpdate;
- (void)synchronize;
- (BOOL)canHandleEvent:(WaylandTextInputEvent *)event;
- (void)handleEvent:(WaylandTextInputEvent *)event;
- (void) setFocusedWindowId: (int)windowId;
- (int) focusedWindowId;

@end

@interface WaylandInputServer (InputMethod)
- (NSString *) inputMethodStyle;
- (NSString *) fontSize: (int *)size;
- (BOOL) clientWindowRect: (NSRect *)rect;
- (BOOL) statusArea: (NSRect *)rect;
- (BOOL) preeditArea: (NSRect *)rect;
- (BOOL) preeditSpot: (NSPoint *)p;
- (BOOL) setStatusArea: (NSRect *)rect;
- (BOOL) setPreeditArea: (NSRect *)rect;
- (BOOL) setPreeditSpot: (NSPoint *)p;
@end

#endif /* _WaylandInputServer_h_INCLUDE */
