/* <title>WaylandServer</title>

   <abstract>Backend server using Wayland.</abstract>

   Copyright (C) 2020 Free Software Foundation, Inc.

   Author: Sergio L. Pascual <slp@sinrega.org>
   Rewrite: Riccardo Canalicchio <riccardo.canalicchio(at)gmail.com>
   Date: February 2016

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

#ifndef _WaylandServer_h_INCLUDE
#define _WaylandServer_h_INCLUDE

#include "config.h"

#include <GNUstepGUI/GSDisplayServer.h>
#include <wayland-client.h>
#include <wayland-cursor.h>
#include <cairo/cairo.h>
#include <xkbcommon/xkbcommon.h>
#include <xkbcommon/xkbcommon-compose.h>

#include "cairo/CairoSurface.h"
#include "wayland/generated/fractional-scale-v1-client-protocol.h"
#include "wayland/generated/viewporter-client-protocol.h"
#include "wayland/generated/nextspace-application-v1-client-protocol.h"
#include "wayland/generated/xdg-output-unstable-v1-client-protocol.h"
#include "wayland/generated/xdg-activation-v1-client-protocol.h"
#include "wayland/generated/primary-selection-unstable-v1-client-protocol.h"
#include "wayland/generated/text-input-unstable-v3-client-protocol.h"

#include "wayland/generated/xdg-shell-client-protocol.h"
#include "wayland/generated/xdg-decoration-unstable-v1-client-protocol.h"
#include "wayland/nextspace-geometry.h"
#include "wayland/generated/wlr-layer-shell-client-protocol.h"

struct pointer
{
  struct wl_pointer *wlpointer;
  float		     x;
  float		     y;
  uint32_t	     last_click_button;
  uint32_t	     last_click_time;
  float		     last_click_x;
  float		     last_click_y;

  uint32_t		       button;
  NSTimeInterval	   last_timestamp;
  enum wl_pointer_button_state button_state;

  uint32_t axis_source;

  uint32_t	 serial;
  struct window *focus;
  struct window *captured;

};

#define WAYLAND_CURSOR_SIZE 24
#define WAYLAND_CURSOR_MAX_SIZE (WAYLAND_CURSOR_SIZE * 8)

struct cursor
{
  const char *name;
  NSImage *image;
  NSSize size;
  NSPoint hotspot;
  struct pool_buffer *custom;
  uint32_t scale120;
  uint64_t animation_start;
};

typedef struct _WaylandConfig
{
  struct zwp_text_input_manager_v3 *text_manager;
  struct wl_display	    *display;
  struct wl_registry	     *registry;
  struct wl_compositor       *compositor;
  struct wl_shell		  *shell;
  struct wl_shm		*shm;
  struct wl_seat		 *seat;
  struct wl_keyboard	     *keyboard;
  struct xkb_compose_table *compose_table;
  struct xkb_compose_state *compose_state;
  NSString *composed_text;
  unsigned char composed_keys[768];
  struct wl_data_device_manager *data_device_manager;
  struct wl_data_device	     *data_device;
  id pasteboard_bridge;
  id primary_bridge;
  struct zwp_primary_selection_device_manager_v1 *primary_manager;
  struct zwp_primary_selection_device_v1 *primary_device;
  uint32_t selection_serial;
  struct xdg_wm_base	     *wm_base;
  struct zxdg_decoration_manager_v1 *decoration_manager;
  struct zwlr_layer_shell_v1 *layer_shell;
#ifdef HAVE_EGL
  struct wl_subcompositor    *subcompositor;
#endif
  int seat_version;

  struct wp_fractional_scale_manager_v1 *fractional_manager;
  struct wp_viewporter *viewporter;
  struct nextspace_application_v1 *application_manager;
  NSDictionary *work_areas;
  NSMutableDictionary *pending_work_areas;
  struct zxdg_output_manager_v1 *output_manager;
  struct xdg_activation_v1 *activation;
  struct wl_list output_list;
  int		 output_count;
  struct wl_list window_list;
  int		 window_count;
  int		 last_window_id;

// last event serial from pointer or keyboard
  uint32_t	 event_serial;


// cursor
  struct wl_cursor_theme *cursor_themes[WAYLAND_CURSOR_MAX_SIZE + 1];
  struct cursor *cursor;
  struct wl_surface *cursor_surface;
  struct wp_viewport *cursor_viewport;
  struct wp_fractional_scale_v1 *cursor_fractional_scale;
  NSMutableSet *cursor_outputs;
  uint32_t cursor_scale120;
  BOOL cursor_hidden;
  uint32_t cursor_enter_serial;
  NSTimer *cursor_timer;
  id cursor_animator;

// pointer
  struct pointer      pointer;
  float mouse_scroll_multiplier;
  id color_pick_panel, color_pick_original;
  int color_pick_window;
  uint32_t color_pick_id, next_color_pick_id;
  uint32_t color_pick_serial;
  int color_pick_input_window;

// keyboard
  struct xkb_context *xkb_context;
  struct
  {
    struct xkb_keymap *keymap;
    struct xkb_state  *state;
    xkb_keysym_t modifier_syms[3][2];
    unsigned char keys_down[768];
  } xkb;
  int modifiers;
  struct window *keyboard_focus;
  NSTimer *repeat_timer;
  int repeat_rate, repeat_delay;
  uint32_t repeat_key;

} WaylandConfig;

struct output
{
  WaylandConfig	*wlconfig;
  struct wl_output *output;
  uint32_t	    server_output_id;
  struct wl_list    link;
  int		    alloc_x;
  int		    alloc_y;
  int		    width;
  int		    height;
  int		    transform;
  int		    scale;
  int mode_width, mode_height, mode_refresh, physical_width, physical_height;
  BOOL logical_geometry;
  struct zxdg_output_v1 *xdg_output;
  char	       *make;
  char	       *model;
  char *name;

  void *user_data;
};

struct window
{
  WaylandConfig *wlconfig;
  id		 instance;
  int		 window_id;
  struct wl_list link;
  BOOL		 configured; // surface has been configured once
  BOOL buffer_needs_attach;  // there is a new buffer avaialble for the surface
  BOOL terminated;
  BOOL moving;
  BOOL resizing;
  BOOL ignoreMouse;
#ifdef HAVE_EGL
  BOOL usesOpenGL;
#endif

  float pos_x;
  float pos_y;
  float width;
  float height;
  float saved_pos_x;
  float saved_pos_y;
  int	is_out;
  int	level;
  BOOL minimized;
  uint32_t title_state;
  BOOL maximized;
  BOOL fullscreen, pending_fullscreen;
  BOOL bounded;
  BOOL was_bounded;
  BOOL server_frame;
  BOOL wants_server_frame;
  struct ns_frame_extents frame;
  struct zxdg_toplevel_decoration_v1 *decoration;
  uint32_t pending_decoration_mode;
  int normal_width, normal_height;

  struct wl_surface	    *surface;
  struct xdg_surface	     *xdg_surface;
  struct xdg_toplevel	      *toplevel;
  struct xdg_popup		   *popup;
  struct xdg_positioner	*positioner;
  struct zwlr_layer_surface_v1 *layer_surface;
  struct output		*output;
  CairoSurface		       *wcs;
  int parent_id;
  BOOL screen_reported;
  int reported_screen;
  NSRect reported_screen_frame;
  int pending_width, pending_height;
  int pending_x, pending_y;
  BOOL pending_position;
  uint32_t scale120;
  BOOL unscaled;
  unsigned surface_refs;
  struct wp_fractional_scale_v1 *fractional_scale;
  struct wp_viewport *viewport;
  struct nextspace_window_v1 *application_window;
  struct xdg_activation_token_v1 *activation_token;
  char *preferred_output_name;
  struct wl_callback *frame_callback;
};

/* get_window_with_id returns the known window with the passed ID, or NULL.
 *
 * NULL is returned when the passed window is not known; for example, the
 * window has been '->terminated' and was removed from the window_list already,
 * but something has referred to its ID. It is the responsibility of the caller
 * to handle the case where NULL is used.
 */
void WaylandRefreshCursor(WaylandConfig *config);
struct pool_buffer *WaylandImageBuffer(WaylandConfig *config, NSImage *image, NSSize size, unsigned scale);
double WaylandDesktopBottom(WaylandConfig *config);
void WaylandCursorOutputsChanged(WaylandConfig *config);
void WaylandFinishCursor(WaylandConfig *config);
void WaylandSetScale(struct window *window, uint32_t scale);
void WaylandSetupSurface(struct window *window);
void WaylandDestroySurface(struct window *window);
void WaylandSetupOutput(struct output *output);
void WaylandSetupApplicationWindow(struct window *window);
void WaylandUpdateWindowHints(struct window *window);
void WaylandUpdateFrameMetrics(struct window *window);
void WaylandSetupDecoration(struct window *window);
struct ns_frame_extents WaylandFrameInsets(struct window *window);
void WaylandUpdateTitleState(struct window *window);
NSSize WaylandSurfaceSize(struct window *window);
NSPoint WaylandSurfacePoint(struct window *window, NSPoint point);
NSPoint WaylandSurfaceOrigin(struct window *window);
void WaylandConfigureViewport(struct window *window, int width, int height);
void WaylandOutputsChanged(WaylandConfig *config);
void WaylandSetupApplicationManager(WaylandConfig *config);
void WaylandAbandonColorPick(WaylandConfig *config, int window_id);
void WaylandReportPosition(struct window *window);
void WaylandReportScreen(struct window *window);
void WaylandSetPosition(struct window *window, float x, float y);
void WaylandApplySizeHints(struct window *window);
void WaylandCancelRepeat(WaylandConfig *config);
void WaylandApplicationFocusChanged(WaylandConfig *config);
NSArray *WaylandMimesForType(NSString *type);
NSString *WaylandTypeForMime(const char *mime);
void WaylandSetupPasteboard(WaylandConfig *config);
NSDictionary *WaylandPasteboardRepresentations(NSPasteboard *pasteboard, NSString *type);
id WaylandPasteboardValue(NSString *mime, NSData *data);
BOOL WaylandStorePasteboardValue(NSPasteboard *pasteboard, NSString *type, id value);
NSData *WaylandReadOffer(struct wl_data_offer *offer, NSString *mime, WaylandConfig *config, NSTimeInterval timeout);
NSTimeInterval WaylandMonotonicTime(void);
NSArray *WaylandApplicationModes(void);
NSArray *WaylandOfferMimes(struct wl_data_offer *offer);
uint32_t WaylandOfferActions(struct wl_data_offer *offer);
uint32_t WaylandOfferAction(struct wl_data_offer *offer);
void WaylandRegisterOffer(struct wl_data_offer *offer);
void WaylandDestroyOffer(struct wl_data_offer *offer);
void WaylandSelection(WaylandConfig *config, struct wl_data_offer *offer);
void WaylandPasteboardFocusLost(WaylandConfig *config);
void WaylandDragContext(struct wl_surface *surface, uint32_t identity, uint32_t phase, BOOL local, NSPoint point);
void WaylandPasteboardInput(WaylandConfig *config, uint32_t serial);
void WaylandWriteDataToFD(NSData *data, int fd);
NSArray *WaylandWindowNumbers(WaylandConfig *config);

struct window *get_window_with_id(WaylandConfig *wlconfig, int winid);

@interface WaylandServer : GSDisplayServer
{
  WaylandConfig *wlconfig;

  BOOL _mouseInitialized;
  id   inputServer;
  int  event_wakeup_fd;
  unsigned waiting_event_mask;
}
+ (void)initializeBackend;
- (NSRect)logicalDesktopBounds;
- (NSArray *)nativeOutputDescriptions;
- (NSArray *)pendingTextInputTransactions;
@end

@interface WaylandServer (SurfaceRoles)
- (void)destroyWindowShell:(struct window *)window;
- (void)destroySurfaceRole:(struct window *)window;
- (BOOL)windowSurfaceHasRole:(struct window *)window;
- (void)createSurfaceShell:(struct window *)window;
- (void)createTopLevel:(struct window *)window;
- (void)createSubMenuShell:(struct window *)window;
- (void)createPopup:(struct window *)window;
- (void)createPopupShell:(struct window *)child withParentShell:(struct window *)parent;
- (void)createLayerShell:(struct window *)window
         withLayerType:(enum zwlr_layer_shell_v1_layer)type
         withNamespace:(NSString *)name;
@end

@interface WaylandServer (Cursor)
- (void) initializeMouseIfRequired;
- (void) initializeMouse;
- (void) mouseOptionsChanged:(NSNotification *)notification;
@end

@interface WaylandServer (InputMethod)
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

#endif /* _WaylandServer_h_INCLUDE */
