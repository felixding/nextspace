/* Private, session-authorized compositor connection.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import <Foundation/Foundation.h>
#import <SystemKit/OSESessionSettings.h>
#include <stdint.h>

extern NSString *WSShellWindowsDidChangeNotification;
extern NSString *WSShellConnectionDidCloseNotification;
extern NSString *WSShellOutputsDidChangeNotification;
extern NSString *WSShellOutputResultNotification;
extern NSString *WSShellInputSettingsDidChangeNotification;
extern NSString *WSShellDesktopsDidChangeNotification;
extern NSString *WSShellInteractiveMoveNotification;

/* Consume --nextspace-shell-fd before NSApplication can start helpers. Private
   arguments are not part of NSTask's cached inherited environment. The descriptor
   is private to Workspace and must never survive helper exec. */
int WSConsumeShellDescriptor(void);

@interface WSShellConnection : NSObject <RunLoopEvents, OSESessionSettings>
{
@private
  struct wl_display *_display;
  struct wl_registry *_registry;
  struct nextspace_shell_v1 *_shell;
  struct nextspace_output_configuration_v1 *_configuration;
  NSMutableDictionary *_pendingOutputs;
  NSDictionary *_outputs, *_outputResult;
  NSDictionary *_outputReply;
  BOOL _waitingForOutputResult;
  NSString *_outputToken;
  NSDictionary *_outputLeaseResult;
  uint32_t _outputRevision, _pendingOutputRevision;
  NSUInteger _outputResultSequence, _outputBatchSequence;
  BOOL _outputsChanged, _outputResultChanged, _inputsChanged;
  NSDictionary *_inputs, *_inputResult;
  NSUInteger _inputBatchSequence, _inputResultSequence;
  uint32_t _inputSerial;
  NSDictionary *_gammaResult;
  NSUInteger _gammaResultSequence;
  uint32_t _gammaSerial;
  NSDictionary *_background;
  NSUInteger _backgroundSequence;
  NSUInteger _desktopSequence, _desktop, _desktopCount;
  BOOL _desktopsChanged;
  NSMutableArray *_moveEvents;
  NSNumber *_movingWindow;
  NSMutableDictionary *_windows;
  NSRunLoop *_runLoop;
  NSArray *_modes;
  BOOL _watchingWrite;
  BOOL _ready;
  BOOL _dispatching;
  BOOL _invalidated;
  BOOL _changed;
  uint32_t _global, _pointerWindow;
}
/* Takes ownership of descriptor, including on failure. Requires shell v7.
   All use, notifications and destruction belong to the creating thread. */
- (id)initWithFileDescriptor:(int)descriptor;
- (BOOL)isConnected;
- (NSArray *)windows;
- (NSNumber *)pointerWindow;
- (NSDictionary *)windowForID:(NSNumber *)identifier;
- (void)activateWindow:(NSNumber *)identifier;
- (void)closeWindow:(NSNumber *)identifier;
- (void)moveWindow:(NSNumber *)identifier toPoint:(NSPoint)point;
- (void)setWindow:(NSNumber *)identifier minimized:(BOOL)minimized;
- (void)setWindow:(NSNumber *)identifier shaded:(BOOL)shaded;
- (void)setWindow:(NSNumber *)identifier presented:(BOOL)presented;
- (void)setWindow:(NSNumber *)identifier level:(NSInteger)level;
- (void)orderWindow:(NSNumber *)identifier above:(BOOL)above;
- (NSNumber *)movingWindow;
- (void)cancelMove:(NSNumber *)identifier;
- (BOOL)setMaximizedDragMode:(NSUInteger)mode;
- (BOOL)setDoubleClickTime:(NSUInteger)milliseconds;
- (BOOL)setTitleAppearance:(NSDictionary *)appearance;
/* Output layouts use the compositor dictionaries and current revision. Calls
   return a bounded test/apply result; notifications report asynchronous rollback.
   Coordinates are logical top-left; modes are untransformed physical pixels. */
- (BOOL)refreshOutputs;
- (NSArray *)outputs;
- (NSUInteger)outputRevision;
- (BOOL)setOutput:(NSNumber *)identifier insets:(NSArray *)insets;
- (NSDictionary *)setOutput:(NSNumber *)identifier gamma:(NSDictionary *)settings;
- (NSDictionary *)outputResult;
- (NSDictionary *)testOutputLayout:(NSArray *)layout revision:(NSUInteger)revision;
- (NSDictionary *)applyOutputLayout:(NSArray *)layout revision:(NSUInteger)revision timeout:(NSUInteger)milliseconds;
- (NSDictionary *)confirmOutputLayout;
- (NSDictionary *)cancelOutputLayout;
- (void)discardOutputLayout;
- (BOOL)refreshInputSettings;
- (NSDictionary *)inputSettings;
- (NSDictionary *)setKeyboardSettings:(NSDictionary *)settings;
- (NSDictionary *)setPointerSettings:(NSDictionary *)settings;
- (NSDictionary *)setShortcuts:(NSArray *)accelerators;
- (NSDictionary *)backgroundColor;
- (NSDictionary *)setBackgroundColor:(NSDictionary *)color;
- (NSUInteger)desktopIndex;
- (NSUInteger)desktopCount;
- (BOOL)configureDesktops:(NSUInteger)count;
- (BOOL)switchDesktop:(NSUInteger)index;
- (void)setWindow:(NSNumber *)identifier desktop:(NSUInteger)index sticky:(BOOL)sticky;
- (void)invalidate;
@end
