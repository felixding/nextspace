/* 
   WaylandServer - Keyboard Handling

   Copyright (C) 2020 Free Software Foundation, Inc.

   Author: Riccardo Canalicchio <riccardo.canalicchio(at)gmail.com>
   Date: November 2021

   This file is part of the GNU Objective C Backend Library.

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

#include "wayland/WaylandServer.h"
#include <AppKit/NSEvent.h>
#include <AppKit/NSApplication.h>
#include <AppKit/NSText.h>
#include <sys/mman.h>
#include <unistd.h>
#include <AppKit/NSWindow.h>
#include <Foundation/NSTimer.h>
#include <Foundation/NSRunLoop.h>
#include <Foundation/NSUserDefaults.h>
#include <time.h>

void WaylandCancelRepeat(WaylandConfig *config)
{
  [config->repeat_timer invalidate];
  [config->repeat_timer release];
  config->repeat_timer = nil;
  [config->composed_text release]; config->composed_text = nil;
}

void WaylandApplicationFocusChanged(WaylandConfig *config)
{
  WaylandServer *server = (WaylandServer *)GSCurrentServer();
  [NSObject cancelPreviousPerformRequestsWithTarget:server selector:@selector(deactivateIfUnfocused:) object:nil];
  if (!config->keyboard_focus)
    [server performSelector:@selector(deactivateIfUnfocused:) withObject:nil afterDelay:0
      inModes:[NSArray arrayWithObjects:NSDefaultRunLoopMode, NSConnectionReplyMode,
        NSModalPanelRunLoopMode, NSEventTrackingRunLoopMode, nil]];
}

static void load_modifier_keys(WaylandConfig *config)
{
  const char *keys[3][2] = {{"GSFirstControlKey", "GSSecondControlKey"},
    {"GSFirstCommandKey", "GSSecondCommandKey"}, {"GSFirstAlternateKey", "GSSecondAlternateKey"}};
  const char *fallback[3][2] = {{"Control_L", "Control_R"}, {"Alt_L", "Alt_R"}, {"Super_L", "Super_R"}};
  NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
  int i, j;
  for (i = 0; i < 3; i++) for (j = 0; j < 2; j++) {
    NSString *name = [defaults stringForKey:[NSString stringWithUTF8String:keys[i][j]]];
    config->xkb.modifier_syms[i][j] = xkb_keysym_from_name(name ? [name UTF8String] : fallback[i][j], 0);
  }
}

static unsigned modifier_for_symbol(WaylandConfig *config, xkb_keysym_t sym)
{
  const unsigned flags[] = {NSControlKeyMask, NSCommandKeyMask, NSAlternateKeyMask};
  int i, j;
  if (sym == XKB_KEY_NoSymbol) return 0;
  for (i = 0; i < 3; i++) for (j = 0; j < 2; j++)
    if (sym == config->xkb.modifier_syms[i][j]) return flags[i];
  return 0;
}

static void update_modifiers(WaylandConfig *config)
{
  config->modifiers = 0;
  if (!config->xkb.state) return;
  if (xkb_state_mod_name_is_active(config->xkb.state, XKB_MOD_NAME_SHIFT,
      XKB_STATE_MODS_LATCHED | XKB_STATE_MODS_LOCKED) > 0)
    config->modifiers |= NSShiftKeyMask;
  if (xkb_state_mod_name_is_active(config->xkb.state, XKB_MOD_NAME_CAPS, XKB_STATE_MODS_EFFECTIVE) > 0)
    config->modifiers |= NSAlphaShiftKeyMask;
  unsigned key;
  BOOL controlKey = NO;
  for (key = 0; key < sizeof(config->xkb.keys_down); key++) {
    if (!config->xkb.keys_down[key]) continue;
    const xkb_keysym_t *symbols;
    if (xkb_keymap_key_get_syms_by_level(config->xkb.keymap, key + 8, 0, 0, &symbols) == 1) {
      config->modifiers |= modifier_for_symbol(config, symbols[0]);
      if (symbols[0] == XKB_KEY_Control_L || symbols[0] == XKB_KEY_Control_R) controlKey = YES;
      if (symbols[0] == XKB_KEY_Shift_L || symbols[0] == XKB_KEY_Shift_R) config->modifiers |= NSShiftKeyMask;
    }
  }
  /* caps:ctrl_modifier changes the XKB modifier without changing Caps_Lock's
     keysym. Honor that effective Control state while retaining side-specific
     application mappings for actual Control keys. */
  if (!controlKey && xkb_state_mod_name_is_active(config->xkb.state, XKB_MOD_NAME_CTRL,
      XKB_STATE_MODS_EFFECTIVE) > 0)
    config->modifiers |= modifier_for_symbol(config, XKB_KEY_Control_L);
}

static void post_modifiers(WaylandConfig *config)
{
  if (!config->keyboard_focus) return;
  NSEvent *event = [NSEvent keyEventWithType:NSFlagsChanged location:NSZeroPoint
    modifierFlags:config->modifiers timestamp:0 windowNumber:config->keyboard_focus->window_id
    context:GSCurrentContext() characters:@"" charactersIgnoringModifiers:@"" isARepeat:NO keyCode:0];
  [config->keyboard_focus->instance postEvent:event atStart:NO];
}

static void
keyboard_handle_keymap(void *data, struct wl_keyboard *keyboard,
		       uint32_t format, int fd, uint32_t size)
{
  NSDebugLog(@"keyboard_handle_keymap");
  WaylandConfig	*wlconfig = data;
  struct xkb_keymap *keymap;
  struct xkb_state  *state;
  char	       *map_str;

  if (!data)
    {
      close(fd);
      return;
    }

  if (format != WL_KEYBOARD_KEYMAP_FORMAT_XKB_V1)
    {
      close(fd);
      return;
    }

  map_str = mmap(NULL, size, PROT_READ, MAP_SHARED, fd, 0);
  if (map_str == MAP_FAILED)
    {
      close(fd);
      return;
    }

  if (!wlconfig->xkb_context) wlconfig->xkb_context = xkb_context_new(0);
  if (wlconfig->xkb_context == NULL)
    {
      munmap(map_str, size); close(fd);
      fprintf(stderr, "Failed to create XKB context\n");
      return;
    }

  keymap = xkb_keymap_new_from_string(wlconfig->xkb_context, map_str,
				      XKB_KEYMAP_FORMAT_TEXT_V1, 0);
  munmap(map_str, size);
  close(fd);

  if (!keymap)
    {
      fprintf(stderr, "failed to compile keymap\n");
      return;
    }

  state = xkb_state_new(keymap);
  if (!state)
    {
      fprintf(stderr, "failed to create XKB state\n");
      xkb_keymap_unref(keymap);
      return;
    }

  xkb_keymap_unref(wlconfig->xkb.keymap);
  xkb_state_unref(wlconfig->xkb.state);
  wlconfig->xkb.keymap = keymap;
  wlconfig->xkb.state = state;

  if (!wlconfig->compose_table) {
    const char *locale = getenv("LC_ALL");
    if (!locale || !*locale) locale = getenv("LC_CTYPE");
    if (!locale || !*locale) locale = getenv("LANG");
    wlconfig->compose_table = xkb_compose_table_new_from_locale(wlconfig->xkb_context,
      locale && *locale ? locale : "C.UTF-8", XKB_COMPOSE_COMPILE_NO_FLAGS);
    if (wlconfig->compose_table)
      wlconfig->compose_state = xkb_compose_state_new(wlconfig->compose_table, XKB_COMPOSE_STATE_NO_FLAGS);
  }
  if (wlconfig->compose_state) xkb_compose_state_reset(wlconfig->compose_state);
  memset(wlconfig->composed_keys, 0, sizeof(wlconfig->composed_keys));

  WaylandCancelRepeat(wlconfig);
  load_modifier_keys(wlconfig);
  update_modifiers(wlconfig);
  [[NSNotificationCenter defaultCenter] postNotificationName:@"GSKeyboardLayoutDidChangeNotification" object:nil];
}

static void
keyboard_handle_enter(void *data, struct wl_keyboard *keyboard, uint32_t serial,
		      struct wl_surface *surface, struct wl_array *keys)
{
  // NSDebugLog(@"keyboard_handle_enter");
  WaylandConfig	*wlconfig = data;
  WaylandCancelRepeat(wlconfig);
  memset(wlconfig->xkb.keys_down, 0, sizeof(wlconfig->xkb.keys_down));
  uint32_t *key;
  wl_array_for_each(key, keys) if (*key < sizeof(wlconfig->xkb.keys_down)) wlconfig->xkb.keys_down[*key] = 1;
  update_modifiers(wlconfig);
  wlconfig->event_serial = serial;
  wlconfig->keyboard_focus = surface ? wl_surface_get_user_data(surface) : NULL;
  WaylandApplicationFocusChanged(wlconfig);
  if (wlconfig->keyboard_focus) {
    NSEvent *event = [NSEvent otherEventWithType:NSAppKitDefined location:NSZeroPoint
      modifierFlags:0 timestamp:0 windowNumber:wlconfig->keyboard_focus->window_id
      context:GSCurrentContext() subtype:GSAppKitWindowFocusIn data1:0 data2:0];
    [wlconfig->keyboard_focus->instance postEvent:event atStart:NO];
  }
}

static void
keyboard_handle_leave(void *data, struct wl_keyboard *keyboard, uint32_t serial,
		      struct wl_surface *surface)
{
  WaylandConfig	*wlconfig = data;
  wlconfig->event_serial = serial;
  WaylandCancelRepeat(wlconfig);
  memset(wlconfig->xkb.keys_down, 0, sizeof(wlconfig->xkb.keys_down));
  wlconfig->keyboard_focus = NULL;
  if (wlconfig->compose_state) xkb_compose_state_reset(wlconfig->compose_state);
  memset(wlconfig->composed_keys, 0, sizeof(wlconfig->composed_keys));
  WaylandApplicationFocusChanged(wlconfig);
  wlconfig->selection_serial = 0;
}

static void
keyboard_handle_modifiers(void *data, struct wl_keyboard *keyboard,
			  uint32_t serial, uint32_t mods_depressed,
			  uint32_t mods_latched, uint32_t mods_locked,
			  uint32_t group)
{
  // NSDebugLog(@"keyboard_handle_modifiers");
  WaylandConfig *wlconfig = data;
  wlconfig->event_serial = serial;

  /* If we're not using a keymap, then we don't handle PC-style modifiers */
  if (!wlconfig->xkb.keymap)
    return;

  int previous = wlconfig->modifiers;

  enum xkb_state_component changed = xkb_state_update_mask(wlconfig->xkb.state, mods_depressed, mods_latched,
			mods_locked, 0, 0, group);
  update_modifiers(wlconfig);
  if (previous != wlconfig->modifiers) post_modifiers(wlconfig);
  if (changed & XKB_STATE_LAYOUT_EFFECTIVE)
    [[NSNotificationCenter defaultCenter] postNotificationName:@"GSKeyboardLayoutDidChangeNotification" object:nil];
}

static unichar special_character(xkb_keysym_t sym)
{
  if (sym >= XKB_KEY_F1 && sym <= XKB_KEY_F35) return NSF1FunctionKey + sym - XKB_KEY_F1;
  switch (sym) {
    case XKB_KEY_Return: case XKB_KEY_KP_Enter: return NSCarriageReturnCharacter;
    case XKB_KEY_BackSpace: return NSDeleteCharacter;
    case XKB_KEY_Tab: case XKB_KEY_ISO_Left_Tab: return NSTabCharacter;
    case XKB_KEY_Escape: return 0x1b;
    case XKB_KEY_Left: return NSLeftArrowFunctionKey;
    case XKB_KEY_Right: return NSRightArrowFunctionKey;
    case XKB_KEY_Up: return NSUpArrowFunctionKey;
    case XKB_KEY_Down: return NSDownArrowFunctionKey;
    case XKB_KEY_Home: return NSHomeFunctionKey;
    case XKB_KEY_End: return NSEndFunctionKey;
    case XKB_KEY_Page_Up: return NSPageUpFunctionKey;
    case XKB_KEY_Page_Down: return NSPageDownFunctionKey;
    case XKB_KEY_Insert: return NSInsertFunctionKey;
    case XKB_KEY_Delete: return NSDeleteFunctionKey;
    default: return 0;
  }
}

static BOOL post_key(WaylandConfig *config, uint32_t key, uint32_t time, BOOL pressed, BOOL repeat)
{
  struct window *window = config->keyboard_focus;
  if (!window || !config->xkb.state) return NO;
  xkb_keysym_t sym = xkb_state_key_get_one_sym(config->xkb.state, key + 8);
  unichar special = special_character(sym);
  char utf8[64] = {0}, plain[64] = {0};
  xkb_state_key_get_utf8(config->xkb.state, key + 8, utf8, sizeof(utf8));
  xkb_keysym_to_utf8(sym, plain, sizeof(plain));
  if (pressed && !repeat && config->compose_state &&
      (config->modifiers & (NSControlKeyMask | NSCommandKeyMask)))
    xkb_compose_state_reset(config->compose_state);
  if (pressed && !repeat && config->compose_state &&
      !(config->modifiers & (NSControlKeyMask | NSCommandKeyMask)) &&
      xkb_compose_state_feed(config->compose_state, sym) == XKB_COMPOSE_FEED_ACCEPTED) {
    enum xkb_compose_status status = xkb_compose_state_get_status(config->compose_state);
    if (status == XKB_COMPOSE_COMPOSING || status == XKB_COMPOSE_CANCELLED) {
      WaylandCancelRepeat(config);
      if (key < sizeof(config->composed_keys)) config->composed_keys[key] = 1;
      if (status == XKB_COMPOSE_CANCELLED) xkb_compose_state_reset(config->compose_state);
      return NO;
    }
    if (status == XKB_COMPOSE_COMPOSED) {
      int length = xkb_compose_state_get_utf8(config->compose_state, utf8, sizeof(utf8));
      xkb_compose_state_reset(config->compose_state);
      if (length <= 0 || length >= sizeof(utf8)) return NO;
      ASSIGNCOPY(config->composed_text, [NSString stringWithUTF8String:utf8]);
      special = 0;
    }
  }
  NSString *characters = special ? [NSString stringWithCharacters:&special length:1] :
    [NSString stringWithUTF8String:utf8];
  NSString *ignoring = special ? characters : [NSString stringWithUTF8String:plain];
  if (pressed && config->composed_text) characters = ignoring = config->composed_text;
  NSEventType type = pressed ? NSKeyDown : NSKeyUp;
  if (modifier_for_symbol(config, sym) || sym == XKB_KEY_Shift_L || sym == XKB_KEY_Shift_R || sym == XKB_KEY_Caps_Lock)
    type = NSFlagsChanged;
  NSEvent *event = [NSEvent keyEventWithType:type location:NSZeroPoint modifierFlags:config->modifiers
    timestamp:time / 1000.0 windowNumber:window->window_id context:GSCurrentContext()
    characters:characters ? characters : @"" charactersIgnoringModifiers:ignoring ? ignoring : @""
    isARepeat:repeat keyCode:key + 8];
  [config->keyboard_focus->instance postEvent:event atStart:NO];
  return YES;
}

static void keyboard_handle_key(void *data, struct wl_keyboard *keyboard, uint32_t serial,
                               uint32_t time, uint32_t key, uint32_t state)
{
  WaylandConfig *config = data;
  config->event_serial = serial;
  BOOL pressed = state == WL_KEYBOARD_KEY_STATE_PRESSED;
  if (pressed) WaylandPasteboardInput(config, serial);
  if (pressed && config->xkb.state && config->keyboard_focus) {
    xkb_keysym_t sym = xkb_state_key_get_one_sym(config->xkb.state, key + 8);
    if (sym == XKB_KEY_space || sym == XKB_KEY_Return || sym == XKB_KEY_KP_Enter) {
      config->color_pick_serial = serial;
      config->color_pick_input_window = config->keyboard_focus->window_id;
    }
  }
  if (key < sizeof(config->xkb.keys_down)) config->xkb.keys_down[key] = pressed;
  update_modifiers(config);
  if (!pressed && key == config->repeat_key) WaylandCancelRepeat(config);
  BOOL repeats = config->xkb.keymap && xkb_keymap_key_repeats(config->xkb.keymap, key + 8);
  if (pressed && repeats) WaylandCancelRepeat(config);
  if (!pressed && key < sizeof(config->composed_keys) && config->composed_keys[key]) {
    config->composed_keys[key] = 0;
    return;
  }
  BOOL posted = post_key(config, key, time, pressed, NO);
  if (pressed && posted && config->keyboard_focus && repeats) {
    if (config->repeat_rate > 0) {
      config->repeat_key = key;
      NSTimeInterval interval = 1.0 / config->repeat_rate;
      config->repeat_timer = [[NSTimer alloc] initWithFireDate:
        [NSDate dateWithTimeIntervalSinceNow:config->repeat_delay / 1000.0] interval:interval
        target:config->keyboard_focus->instance selector:@selector(repeatKey:) userInfo:nil repeats:YES];
      NSRunLoop *loop = [NSRunLoop currentRunLoop];
      for (NSString *mode in [NSArray arrayWithObjects:NSDefaultRunLoopMode, NSConnectionReplyMode,
           NSModalPanelRunLoopMode, NSEventTrackingRunLoopMode, nil])
        [loop addTimer:config->repeat_timer forMode:mode];
    }
  }
}

static void keyboard_handle_repeat_info(void *data, struct wl_keyboard *keyboard, int32_t rate, int32_t delay)
{
  WaylandConfig *config = data;
  WaylandCancelRepeat(config);
  config->repeat_rate = MAX(0, MIN(rate, 1000));
  config->repeat_delay = MAX(0, delay);
}

const struct wl_keyboard_listener keyboard_listener
  = {keyboard_handle_keymap,	keyboard_handle_enter,
     keyboard_handle_leave,	keyboard_handle_key,
     keyboard_handle_modifiers, keyboard_handle_repeat_info};

@implementation WaylandServer (KeyboardOps)
- (void)deactivateIfUnfocused:(id)sender
{
  /* A leave/enter pair within this connection keeps the application active.
     Real application deactivation runs outside protocol callbacks so AppKit
     can resign key/main status and hide its menus or auxiliary panels safely. */
  if (wlconfig && !wlconfig->keyboard_focus) {
    WaylandPasteboardFocusLost(wlconfig);
    if ([NSApp isActive]) [NSApp deactivate];
  }
}
- (NSArray *)keyboardLayoutNames
{
  NSMutableArray *names = [NSMutableArray array];
  if (wlconfig->xkb.keymap) {
    xkb_layout_index_t index, count = xkb_keymap_num_layouts(wlconfig->xkb.keymap);
    for (index = 0; index < count; index++) {
      const char *name = xkb_keymap_layout_get_name(wlconfig->xkb.keymap, index);
      [names addObject:name ? [NSString stringWithUTF8String:name] : @""];
    }
  }
  return names;
}
- (NSInteger)keyboardLayoutIndex
{
  return wlconfig->xkb.state ? xkb_state_serialize_layout(wlconfig->xkb.state, XKB_STATE_LAYOUT_EFFECTIVE) : 0;
}
- (void)keyboardOptionsChanged:(NSNotification *)notification
{
  load_modifier_keys(wlconfig);
  update_modifiers(wlconfig);
  post_modifiers(wlconfig);
}
- (void)repeatKey:(NSTimer *)timer
{
  if (!wlconfig->keyboard_focus || !wlconfig->repeat_rate) { WaylandCancelRepeat(wlconfig); return; }
  struct timespec now;
  clock_gettime(CLOCK_MONOTONIC, &now);
  post_key(wlconfig, wlconfig->repeat_key, now.tv_sec * 1000 + now.tv_nsec / 1000000, YES, YES);
}
@end
