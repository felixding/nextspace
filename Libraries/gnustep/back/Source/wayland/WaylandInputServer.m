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

#include "config.h"
#include <math.h>
#include <time.h>
#include <AppKit/AppKit.h>
#include <GNUstepGUI/GSDisplayServer.h>
#include "wayland/WaylandServer.h"
#include "wayland/WaylandInputServer.h"

@interface WaylandInputServer (Protocol)
- (void)entered:(struct wl_surface *)surface;
- (void)record:(NSString *)key value:(id)value;
- (void)done:(uint32_t)serial;
@end

static NSArray *inputModes(void)
{
  return [NSArray arrayWithObjects:NSDefaultRunLoopMode, NSModalPanelRunLoopMode,
    NSEventTrackingRunLoopMode, NSConnectionReplyMode, nil];
}
static void inputEnter(void *data, struct zwp_text_input_v3 *text, struct wl_surface *surface)
{ [(WaylandInputServer *)data entered:surface]; }
static void inputLeave(void *data, struct zwp_text_input_v3 *text, struct wl_surface *surface)
{ [(WaylandInputServer *)data entered:NULL]; }
static void inputPreedit(void *data, struct zwp_text_input_v3 *text, const char *value, int32_t begin, int32_t end)
{
  NSString *string = value ? [NSString stringWithUTF8String:value] : @"";
  if (!string) return;
  [(WaylandInputServer *)data record:@"preedit" value:string];
  [(WaylandInputServer *)data record:@"begin" value:[NSNumber numberWithInt:begin]];
  [(WaylandInputServer *)data record:@"end" value:[NSNumber numberWithInt:end]];
}
static void inputCommit(void *data, struct zwp_text_input_v3 *text, const char *value)
{
  NSString *string = value ? [NSString stringWithUTF8String:value] : @"";
  if (string) [(WaylandInputServer *)data record:@"commit" value:string];
}
static void inputDelete(void *data, struct zwp_text_input_v3 *text, uint32_t before, uint32_t after)
{
  [(WaylandInputServer *)data record:@"before" value:[NSNumber numberWithUnsignedInt:before]];
  [(WaylandInputServer *)data record:@"after" value:[NSNumber numberWithUnsignedInt:after]];
}
static void inputDone(void *data, struct zwp_text_input_v3 *text, uint32_t serial)
{ [(WaylandInputServer *)data done:serial]; }
static const struct zwp_text_input_v3_listener inputListener = {
  .enter = inputEnter, .leave = inputLeave, .preedit_string = inputPreedit,
  .commit_string = inputCommit, .delete_surrounding_text = inputDelete, .done = inputDone
};

/* Wayland offsets are UTF-8 bytes, while NSTextInput ranges are UTF-16 units.
   Reject offsets in the middle of an encoded character, including surrogates. */
static NSUInteger inputUTF16Offset(NSString *string, NSInteger bytes)
{
  NSData *data = [string dataUsingEncoding:NSUTF8StringEncoding];
  if (bytes < 0 || (NSUInteger)bytes > [data length]) return NSNotFound;
  NSString *prefix = [[NSString alloc] initWithBytes:[data bytes] length:bytes encoding:NSUTF8StringEncoding];
  NSUInteger result = prefix ? [prefix length] : NSNotFound;
  [prefix release]; return result;
}
static NSUInteger inputUTF8Offset(NSString *string, NSUInteger offset)
{
  if (offset > [string length]) return NSNotFound;
  NSData *bytes = [[string substringToIndex:offset] dataUsingEncoding:NSUTF8StringEncoding];
  return bytes ? [bytes length] : NSNotFound;
}

@implementation WaylandTextInputEvent
+ (id)eventWithTransaction:(NSDictionary *)transaction window:(NSInteger)window
{
  struct timespec now; clock_gettime(CLOCK_MONOTONIC, &now);
  uint32_t milliseconds = (uint64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000;
  WaylandTextInputEvent *event = (WaylandTextInputEvent *)[self keyEventWithType:NSKeyDown location:NSZeroPoint
    modifierFlags:0 timestamp:milliseconds / 1000.0 windowNumber:window context:GSCurrentContext()
    characters:@"" charactersIgnoringModifiers:@"" isARepeat:NO keyCode:0];
  event->_transaction = [transaction copy];
  return event;
}
- (NSDictionary *)transaction { return _transaction; }
- (void)dealloc { [_transaction release]; [super dealloc]; }
@end

@implementation WaylandInputServer
- (id)initWithConfig:(WaylandConfig *)config
{
  self = [super init];
  if (!self) return nil;
  _config = config; _canSend = YES;
  _pending = [NSMutableDictionary new];
  if (config->text_manager && config->seat) {
    _textInput = zwp_text_input_manager_v3_get_text_input(config->text_manager, config->seat);
    zwp_text_input_v3_add_listener(_textInput, &inputListener, self);
    NSNotificationCenter *center = [NSNotificationCenter defaultCenter];
    for (NSString *name in [NSArray arrayWithObjects:NSTextDidChangeNotification,
      NSTextViewDidChangeSelectionNotification, NSWindowDidBecomeKeyNotification,
      NSWindowDidResignKeyNotification, NSWindowDidMoveNotification, NSWindowDidResizeNotification, nil])
      [center addObserver:self selector:@selector(clientChanged:) name:name object:nil];
  }
  return self;
}
- (void)dealloc
{
  [[NSNotificationCenter defaultCenter] removeObserver:self];
  [NSObject cancelPreviousPerformRequestsWithTarget:self];
  if (_textInput) zwp_text_input_v3_destroy(_textInput);
  [_client release]; [_snapshot release]; [_pending release];
  [super dealloc];
}
- (void)setFocusedWindowId:(int)windowId { focused_window_id = windowId; }
- (int)focusedWindowId { return focused_window_id; }
- (void)clientChanged:(NSNotification *)notification { [self scheduleUpdate]; }
- (void)scheduleUpdate
{
  if (!_textInput || _scheduled || _applying) return;
  _scheduled = YES;
  [self performSelector:@selector(synchronize) withObject:nil afterDelay:0 inModes:inputModes()];
}
- (void)entered:(struct wl_surface *)surface
{
  _entered = surface; _generation++; _canSend = YES; _reset = YES;
  [_pending removeAllObjects];
  [self scheduleUpdate];
}
- (void)record:(NSString *)key value:(id)value { [_pending setObject:value forKey:key]; }
- (void)done:(uint32_t)serial
{
  _canSend = serial == _serial;
  if (_enabled && _entered) {
    [_pending setObject:[NSNumber numberWithUnsignedInteger:_generation] forKey:@"generation"];
    [_pending setObject:[NSNumber numberWithUnsignedInt:serial] forKey:@"serial"];
    [GSCurrentServer() postEvent:[WaylandTextInputEvent eventWithTransaction:_pending
      window:focused_window_id] atStart:NO];
  }
  [_pending removeAllObjects]; [self scheduleUpdate];
}
- (NSArray *)transactions
{
  NSMutableArray *pending = [NSMutableArray array];
  for (NSDictionary *transaction in [(WaylandServer *)GSCurrentServer() pendingTextInputTransactions])
    if ([[transaction objectForKey:@"generation"] unsignedIntegerValue] == _generation)
      [pending addObject:transaction];
  return pending;
}
- (BOOL)canHandleEvent:(WaylandTextInputEvent *)event
{
  return !_applying || [[[event transaction] objectForKey:@"generation"] unsignedIntegerValue] != _generation;
}
- (void)handleEvent:(WaylandTextInputEvent *)event
{
  if (_applying) return; /* Only stale events may be consumed during reentry. */
  _applying = YES;
  @try {
    [self refreshClient];
    NSDictionary *transaction = [event transaction];
    if (_enabled && _client && [[transaction objectForKey:@"generation"] unsignedIntegerValue] == _generation) {
      [self applyTransaction:transaction]; _changedByMethod = YES;
    }
  }
  @finally { _applying = NO; }
  [self synchronize];
}
- (void)removePreedit
{
  if ([_client hasMarkedText]) {
    [_client setMarkedText:@"" selectedRange:NSMakeRange(0, 0)];
    [_client unmarkText];
  }
}
- (NSDictionary *)clientState
{
  NSRange selection = [_client selectedRange];
  NSString *string = [_client respondsToSelector:@selector(string)] ? [_client string] : @"";
  BOOL secure = [_client isKindOfClass:NSClassFromString(@"NSSecureTextView")];
  NSRange marked = [_client markedRange];
  if (marked.location != NSNotFound && NSMaxRange(marked) <= [string length]) {
    NSMutableString *plain = [[string mutableCopy] autorelease];
    [plain deleteCharactersInRange:marked]; string = plain;
    selection = NSMakeRange(marked.location, 0);
  }
  NSUInteger offset = 0;
  if (secure || selection.location == NSNotFound || NSMaxRange(selection) > [string length] || selection.length > 512) {
    string = @""; selection = NSMakeRange(0, 0);
  } else {
    offset = selection.location > 256 ? selection.location - 256 : 0;
    NSUInteger end = MIN([string length], NSMaxRange(selection) + 256);
    /* Do not split a UTF-16 surrogate pair at the context boundary. */
    if (offset && [string characterAtIndex:offset] >= 0xdc00 && [string characterAtIndex:offset] <= 0xdfff) offset--;
    if (end < [string length] && [string characterAtIndex:end] >= 0xdc00 && [string characterAtIndex:end] <= 0xdfff) end++;
    string = [string substringWithRange:NSMakeRange(offset, end - offset)];
    selection.location -= offset;
  }
  NSUInteger cursor = inputUTF8Offset(string, NSMaxRange(selection)), anchor = inputUTF8Offset(string, selection.location);
  if (cursor == NSNotFound || anchor == NSNotFound) { string = @""; cursor = anchor = offset = 0; }
  NSRect rect = [_client firstRectForCharacterRange:[_client selectedRange]];
  NSWindow *window = [_client window];
  rect.origin = [window convertScreenToBase:rect.origin];
  struct window *native = _config->keyboard_focus;
  /* Text layout can run a nested loop and lose focus while computing the
     caret. Do not publish or dereference that obsolete client state. */
  if (!native || native->surface != _entered || GSWindowWithNumber(native->window_id) != window ||
      [window firstResponder] != _client) {
    _reset = YES;
    return nil;
  }
  rect.origin.y = native->height - NSMaxY(rect);
  struct ns_frame_extents frame = WaylandFrameInsets(native);
  rect.origin.x -= frame.left; rect.origin.y -= frame.top;
  rect.size.width = MAX(1, rect.size.width); rect.size.height = MAX(1, rect.size.height);
  return [NSDictionary dictionaryWithObjectsAndKeys:string, @"text",
    [NSNumber numberWithUnsignedInteger:cursor], @"cursor", [NSNumber numberWithUnsignedInteger:anchor], @"anchor",
    [NSNumber numberWithUnsignedInteger:offset], @"offset", [NSNumber numberWithBool:secure], @"secure",
    [NSValue valueWithRect:rect], @"rect", nil];
}
- (void)applyTransaction:(NSDictionary *)transaction
{
  [self removePreedit];
  NSUInteger before = [[transaction objectForKey:@"before"] unsignedIntegerValue];
  NSUInteger after = [[transaction objectForKey:@"after"] unsignedIntegerValue];
  NSDictionary *context = [self clientState];
  if (!context) return;
  if ((before || after) && [_client respondsToSelector:@selector(setSelectedRange:)] &&
      [_client respondsToSelector:@selector(string)] && ![[context objectForKey:@"secure"] boolValue]) {
    NSString *text = [context objectForKey:@"text"];
    NSUInteger cursor = [[context objectForKey:@"cursor"] unsignedIntegerValue];
    NSUInteger anchor = [[context objectForKey:@"anchor"] unsignedIntegerValue];
    NSUInteger lower = MIN(cursor, anchor), upper = MAX(cursor, anchor);
    NSData *bytes = [text dataUsingEncoding:NSUTF8StringEncoding];
    if (before <= lower && upper <= [bytes length] && after <= [bytes length] - upper) {
      NSUInteger start = inputUTF16Offset(text, lower - before), end = inputUTF16Offset(text, upper + after);
      if (start != NSNotFound && end != NSNotFound) {
        NSUInteger offset = [[context objectForKey:@"offset"] unsignedIntegerValue];
        NSRange selected = [_client selectedRange];
        NSUInteger length = [[_client string] length];
        NSRange trailing = NSMakeRange(NSMaxRange(selected), offset + end - NSMaxRange(selected));
        [_client setSelectedRange:trailing]; [_client insertText:@""];
        if ([[_client string] length] == length - trailing.length) {
          NSRange leading = NSMakeRange(offset + start, selected.location - offset - start);
          length = [[_client string] length];
          [_client setSelectedRange:leading]; [_client insertText:@""];
          if ([[_client string] length] == length - leading.length) selected.location = leading.location;
        }
        [_client setSelectedRange:selected];
      }
    }
  }
  NSString *commit = [transaction objectForKey:@"commit"];
  if (commit) [_client insertText:commit];
  NSString *preedit = [transaction objectForKey:@"preedit"];
  if ([preedit length]) {
    NSUInteger begin = inputUTF16Offset(preedit, [[transaction objectForKey:@"begin"] integerValue]);
    NSUInteger end = inputUTF16Offset(preedit, [[transaction objectForKey:@"end"] integerValue]);
    NSRange range = begin == NSNotFound || end == NSNotFound ? NSMakeRange(NSNotFound, 0)
      : NSMakeRange(MIN(begin, end), MAX(begin, end) - MIN(begin, end));
    [_client setMarkedText:preedit selectedRange:range];
  }
}
- (void)refreshClient
{
  struct window *native = _config->keyboard_focus;
  NSWindow *window = native && native->surface == _entered ? GSWindowWithNumber(native->window_id) : nil;
  id client = [window firstResponder];
  if (![client respondsToSelector:@selector(setMarkedText:selectedRange:)] ||
      ![client respondsToSelector:@selector(markedRange)] || ![client respondsToSelector:@selector(selectedRange)] ||
      ![client respondsToSelector:@selector(firstRectForCharacterRange:)] ||
      ([client respondsToSelector:@selector(isEditable)] && ![client isEditable])) client = nil;
  if (_reset || client != _client || (!_entered && _enabled)) {
    _reset = NO;
    [self removePreedit];
    if (_enabled) { zwp_text_input_v3_disable(_textInput); zwp_text_input_v3_commit(_textInput); _serial++; }
    _enabled = NO; _canSend = YES; _generation++; _changedByMethod = NO;
    ASSIGN(_client, client);
    [_snapshot release]; _snapshot = nil;
    focused_window_id = window ? [window windowNumber] : 0;
  }
}
- (void)synchronize
{
  if (!_textInput || _applying) return;
  [NSObject cancelPreviousPerformRequestsWithTarget:self selector:@selector(synchronize) object:nil];
  _scheduled = NO; _applying = YES;
  @try {
    [self refreshClient];
    if (_client && _entered) {
      /* Do not publish intermediate context while accepted edits await their
         position in the keyboard queue. Layout can dispatch more edits too. */
      if ([[self transactions] count]) return;
      NSDictionary *state = [self clientState];
      if (!state || [[self transactions] count]) return;
      if (_canSend && (!_enabled || ![state isEqual:_snapshot])) {
        BOOL contextChanged = !_enabled;
        for (NSString *key in [NSArray arrayWithObjects:@"text", @"cursor", @"anchor", @"secure", nil])
          if (![[state objectForKey:key] isEqual:[_snapshot objectForKey:key]]) contextChanged = YES;
        if (!_enabled) { zwp_text_input_v3_enable(_textInput); _enabled = YES; }
        if (contextChanged) {
          zwp_text_input_v3_set_surrounding_text(_textInput, [[state objectForKey:@"text"] UTF8String],
            [[state objectForKey:@"cursor"] unsignedIntValue], [[state objectForKey:@"anchor"] unsignedIntValue]);
          BOOL secure = [[state objectForKey:@"secure"] boolValue];
          zwp_text_input_v3_set_content_type(_textInput, secure ? ZWP_TEXT_INPUT_V3_CONTENT_HINT_HIDDEN_TEXT |
            ZWP_TEXT_INPUT_V3_CONTENT_HINT_SENSITIVE_DATA : ZWP_TEXT_INPUT_V3_CONTENT_HINT_NONE,
            secure ? ZWP_TEXT_INPUT_V3_CONTENT_PURPOSE_PASSWORD : ZWP_TEXT_INPUT_V3_CONTENT_PURPOSE_NORMAL);
          zwp_text_input_v3_set_text_change_cause(_textInput, _changedByMethod ? ZWP_TEXT_INPUT_V3_CHANGE_CAUSE_INPUT_METHOD :
            ZWP_TEXT_INPUT_V3_CHANGE_CAUSE_OTHER);
        }
        NSRect rect = [[state objectForKey:@"rect"] rectValue];
        zwp_text_input_v3_set_cursor_rectangle(_textInput, floor(rect.origin.x), floor(rect.origin.y),
          ceil(rect.size.width), ceil(rect.size.height));
        zwp_text_input_v3_commit(_textInput); _serial++;
        [_snapshot release]; _snapshot = [state copy];
      }
      if (_canSend) _changedByMethod = NO;
    }
    wl_display_flush(_config->display);
  } @finally {
    _applying = NO;
    if (_reset) [self scheduleUpdate];
  }
}
- (void)activeConversationChanged:(id)sender toNewConversation:(long)conversation { [self scheduleUpdate]; }
- (void)activeConversationWillChange:(id)sender fromOldConversation:(long)conversation { [self scheduleUpdate]; }
@end

@implementation WaylandInputServer (InputMethod)

- (NSString *) inputMethodStyle
{
  /* Text-input-v3 updates the NSTextInput client directly; the old XIM status
     and preedit-area UI does not apply. Direct XKB/compose remains the fallback. */
  return nil;
}

- (NSString *) fontSize: (int *)size
{
  NSString *str;

  str = [[NSUserDefaults standardUserDefaults] stringForKey: @"NSFontSize"];
  if (!str)
    str = @"12";
  if (size)
    *size = (int) strtol([str cString], NULL, 10);
  return str;
}

- (BOOL) clientWindowRect: (NSRect *)rect
{
  if (!rect || focused_window_id == 0)
    return NO;
  NSWindow *window = GSWindowWithNumber(focused_window_id);
  if (window == nil)
    return NO;
  *rect = [window frame];
  return YES;
}

- (BOOL) statusArea: (NSRect *)rect
{
  return NO;
}

- (BOOL) preeditArea: (NSRect *)rect
{
  return NO;
}

- (BOOL) preeditSpot: (NSPoint *)p
{
  return NO;
}

- (BOOL) setStatusArea: (NSRect *)rect
{
  return NO;
}

- (BOOL) setPreeditArea: (NSRect *)rect
{
  return NO;
}

- (BOOL) setPreeditSpot: (NSPoint *)p
{
  return NO;
}

@end
