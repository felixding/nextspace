/* Derived from wlroots 0.18.2 tinywl; see LICENSE.wlroots. */
#define _GNU_SOURCE
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <errno.h>
#include <drm_fourcc.h>
#include <fcntl.h>
#include <signal.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <wlr/types/wlr_fractional_scale_v1.h>
#include <wlr/types/wlr_viewporter.h>
#include <wlr/types/wlr_xdg_output_v1.h>
#include <wlr/types/wlr_xdg_activation_v1.h>
#include <wlr/types/wlr_xdg_decoration_v1.h>
#include <wlr/types/wlr_session_lock_v1.h>
#include <wlr/types/wlr_screencopy_v1.h>
#include "nextspace-geometry.h"
#include "nextspace-application-v1-server-protocol.h"
#include "nextspace-shell-v1-server-protocol.h"
#include <getopt.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <time.h>
#include <unistd.h>
#include <wayland-server-core.h>
#include <wlr/backend.h>
#include <wlr/backend/headless.h>
#include <wlr/backend/libinput.h>
#include <wlr/backend/multi.h>
#include <wlr/backend/session.h>
#include <wlr/interfaces/wlr_keyboard.h>
#include <wlr/render/allocator.h>
#include <wlr/render/wlr_renderer.h>
#include <wlr/types/wlr_cursor.h>
#include <wlr/types/wlr_compositor.h>
#include <wlr/types/wlr_data_device.h>
#include <wlr/types/wlr_input_device.h>
#include <wlr/types/wlr_keyboard.h>
#include <wlr/types/wlr_output.h>
#include "output-gamma.h"
#include <wlr/types/wlr_output_layout.h>
#include <wlr/types/wlr_output_swapchain_manager.h>
#include <wlr/types/wlr_pointer.h>
#include <wlr/types/wlr_primary_selection.h>
#include <wlr/types/wlr_primary_selection_v1.h>
#include <wlr/types/wlr_text_input_v3.h>
#include <wlr/types/wlr_input_method_v2.h>
#include <wlr/types/wlr_virtual_keyboard_v1.h>
#include <wlr/types/wlr_scene.h>
#include <wlr/types/wlr_seat.h>
#include <wlr/types/wlr_subcompositor.h>
#include <wlr/types/wlr_xcursor_manager.h>
#include <wlr/types/wlr_xdg_shell.h>
#include <wlr/util/log.h>
#include <xkbcommon/xkbcommon.h>

/* For brevity's sake, struct members are annotated where they are used. */
enum nextspace_cursor_mode {
	NEXTSPACE_CURSOR_PASSTHROUGH,
	NEXTSPACE_CURSOR_MOVE,
	NEXTSPACE_CURSOR_RESIZE,
};

enum { DECORATION_BORDER_WIDTH = 1, DECORATION_TITLE_HEIGHT = 22,
  DECORATION_RESIZE_HEIGHT = 9, DECORATION_MOVE_THRESHOLD = 5 };

struct nextspace_application_window;
struct nextspace_drag_context;
struct output_configuration;
struct nextspace_decoration;
enum maximize_axis { MAXIMIZE_HORIZONTAL = 1, MAXIMIZE_VERTICAL = 2, MAXIMIZE_BOTH = 3 };

struct nextspace_server {
  struct wlr_screencopy_manager_v1 *screencopy_manager;
  struct wl_client *capture_client;
  struct wl_listener capture_client_destroy;
  struct wlr_session_lock_manager_v1 *lock_manager;
  struct wlr_session_lock_v1 *session_lock;
  struct wl_client *lock_client;
  struct wl_listener lock_client_destroy, new_lock, lock_new_surface, lock_unlock, lock_destroy;
  struct wlr_scene_tree *desktop_tree, *lock_tree;
  struct wl_list lock_surfaces;
  bool locked;
  bool sleep_guard, sleep_acknowledged;
  uint64_t sleep_protected_ms;
  uint32_t lock_epoch, lock_previous_focus;
  bool lock_pixel_check;
  struct wlr_text_input_manager_v3 *text_input_manager;
  struct wlr_input_method_manager_v2 *input_method_manager;
  struct wlr_virtual_keyboard_manager_v1 *virtual_keyboard_manager;
  struct wl_client *input_method_client;
  struct wl_listener input_method_client_destroy;
  struct wlr_input_method_v2 *input_method;
  struct nextspace_text_input *active_text_input;
  struct wl_list text_inputs, input_popups;
  struct wl_listener new_text_input, new_input_method, new_virtual_keyboard, text_focus;
  struct wl_listener input_method_commit, input_method_destroy, input_method_popup, input_method_grab;
  unsigned desktop, desktop_count;
  int shell_broker_fd;
  struct wl_event_source *shell_broker_source;
  struct wl_global *shell_global;
  struct wl_client *shell_client;
  struct wl_resource *shell_resource;
  struct wl_listener shell_client_destroy;
  struct wlr_keyboard control_keyboard;
  struct wl_listener layout_change;
  struct wlr_compositor *compositor;
  struct wlr_xdg_output_manager_v1 *xdg_output_manager;
	int control_fd;
	struct wl_event_source *control_source, *rollback_timer;
	struct nextspace_output *pending_output;
	float previous_scale;
	unsigned next_window_id;
  uint32_t shell_pointer_id;
  uint32_t output_revision, next_output_id, primary_output_id;
  bool output_applying;
  unsigned output_fail_after; /* Private development fault injection only. */
  struct wl_event_source *output_idle, *output_timer;
  struct output_configuration *output_pending;
  struct xkb_context *input_context;
  struct xkb_keymap *input_keymap;
  char *input_model, *input_layout, *input_variant, *input_options;
  unsigned input_delay, input_rate;
  uint32_t shortcuts[18][2];
  bool input_numlock;
  double pointer_speed;
  uint32_t pointer_profile;
  struct wl_list pointers;
  struct wl_listener request_start_drag, drag_icon_destroy, drag_icon_commit;
  struct wlr_scene_tree *drag_icon;
  struct nextspace_drag_context *drag_context;
  uint32_t next_drag_id;
	struct wl_display *wl_display;
	struct wlr_backend *backend;
  struct wlr_session *session;
	struct wlr_renderer *renderer;
	struct wlr_allocator *allocator;
  struct wlr_buffer *color_sample_buffer;
  struct nextspace_application_window *color_pick_window;
  struct wlr_buffer *color_pick_cursor_buffer;
  uint32_t color_pick_id, color_pick_buttons;
  int color_pick_density;
  bool color_pick_dirty, color_pick_selecting;
  double color_pick_x, color_pick_y;
  struct { uint32_t serial, view; uint64_t time; bool keyboard; } color_pick_gesture;
	struct wlr_scene *scene;
  struct wlr_scene_rect *background;
	struct wlr_scene_output_layout *scene_layout;

	struct wlr_xdg_shell *xdg_shell;
  struct wl_listener new_decoration;
  struct nextspace_toplevel *decoration_pressed;
  unsigned decoration_button;
  uint32_t decoration_press_button;
  uint32_t decoration_buttons;
  uint32_t decoration_click_view, decoration_click_button, decoration_click_time;
  uint32_t decoration_scroll_view;
  int decoration_scroll_remainder;
  uint32_t double_click_time;
  struct title_font *title_font;
  uint32_t title_justification, title_revision;
  struct wl_listener request_activate;
	struct wl_listener new_xdg_toplevel;
	struct wl_listener new_xdg_popup;
	struct wl_list toplevels;
	struct wl_list popups;
  struct wl_list layers;

	struct wlr_cursor *cursor;
	struct wlr_xcursor_manager *cursor_mgr;
	struct wl_listener cursor_motion;
	struct wl_listener cursor_motion_absolute;
	struct wl_listener cursor_button;
	struct wl_listener cursor_axis;
	struct wl_listener cursor_frame;

	struct wlr_seat *seat;
	struct wl_listener new_input;
	struct wl_listener request_cursor;
  struct wlr_surface *client_cursor;
  struct wl_listener client_cursor_destroy;
  int cursor_hotspot_x, cursor_hotspot_y;
	struct wl_listener request_set_selection;
  struct wl_listener request_set_primary_selection;
  struct wl_listener clipboard_selection;
  struct clipboard_snapshot *clipboard_copy;
  struct wl_list clipboard_writes;
  size_t clipboard_bytes;
	struct wl_list keyboards;
	enum nextspace_cursor_mode cursor_mode;
	struct nextspace_toplevel *grabbed_toplevel;
	double grab_x, grab_y;
	struct wlr_box grab_geobox;
	uint32_t resize_edges;
  uint32_t maximized_drag_mode;
  unsigned grab_maximized;
  bool grab_pending;
  double grab_start_x, grab_start_y;
  struct wlr_box grab_normal_geometry;
  int grab_maximized_dx, grab_maximized_dy;

	struct wlr_output_layout *output_layout;
	struct wl_list outputs;
  struct wl_list application_resources;
	struct wl_listener new_output;
};

struct nextspace_output {
  struct output_gamma gamma;
  bool gamma_set;
  bool pixels_valid;
  uint64_t pixel_counts[3]; /* Private fixture: black, locker color, other. */
  int pixel_width, pixel_height;
  uint32_t pixel_epoch;
  struct wlr_scene_rect *lock_background;
  struct wl_listener lock_present;
  uint32_t lock_epoch, lock_commit_seq;
  bool lock_pending_frame;
  bool samples_valid;
  uint32_t samples[5]; /* Last presented pixels, only for the private test controller. */
  uint32_t id;
  int x, y;
  int insets[4]; /* left, top, right, bottom in logical desktop units */
  struct wl_listener commit;
	struct wl_list link;
	struct nextspace_server *server;
	struct wlr_output *wlr_output;
	struct wl_listener frame;
	struct wl_listener request_state;
	struct wl_listener destroy;
};

struct nextspace_toplevel {
  struct nextspace_decoration *decoration;
  struct wlr_scene_tree *content_tree;
  bool server_decorated;
  struct ns_frame_extents frame, pending_frame;
  bool frame_pending;
  bool has_metadata;
  bool document_edited;
  unsigned client_title_height;
  unsigned maximized;
  bool fullscreen;
  uint32_t maximized_output, fullscreen_output;
  int maximized_dx, maximized_dy;
  struct wlr_box normal_geometry;
  struct wlr_scene_rect *fullscreen_background;
  unsigned desktop;
  bool sticky;
  int level;
  uint32_t client_id, style, title_height;
  bool shaded;
  bool selected;
  bool minimized;
  bool shell_hidden, client_hidden;
  struct wl_listener request_minimize;
  struct wl_listener set_title, set_app_id;
  struct {
    char *app_id, *title;
    struct wlr_box box;
    pid_t pid;
    uint32_t flags;
    uint32_t client_id, style, title_height;
    int level;
    unsigned desktop;
    bool sticky;
    bool valid;
  } shell_state;
  struct nextspace_application_window *application_window;
  bool mapped;
	unsigned id;
	struct wl_list link;
	struct nextspace_server *server;
	struct wlr_xdg_toplevel *xdg_toplevel;
	struct wlr_scene_tree *scene_tree;
	struct wl_listener map;
	struct wl_listener unmap;
	struct wl_listener commit;
	struct wl_listener destroy;
	struct wl_listener request_move;
	struct wl_listener request_resize;
	struct wl_listener request_maximize;
	struct wl_listener request_fullscreen;
};

struct nextspace_popup {
  struct wlr_scene_tree *holder;
	struct nextspace_server *server;
	struct wl_list link;
	struct wlr_xdg_popup *xdg_popup;
	struct wl_listener commit;
	struct wl_listener destroy;
};

struct nextspace_keyboard {
  bool consumed_keys[768];
	struct wl_list link;
	struct nextspace_server *server;
	struct wlr_keyboard *wlr_keyboard;

	struct wl_listener modifiers;
	struct wl_listener key;
	struct wl_listener destroy;
};

static void outputs_changed(struct nextspace_server *server);
static void session_lock_layout_changed(struct nextspace_server *server);
static void session_lock_request(struct nextspace_server *server, bool notify);
static void session_lock_prepare_for_sleep(struct nextspace_server *server);
static void session_lock_output_present(struct wl_listener *listener, void *data);
static void session_lock_output_destroy(struct nextspace_output *output);
static void session_lock_pointer_motion(struct nextspace_server *server, uint32_t time);
static void session_lock_pointer_button(struct nextspace_server *server,
  struct wlr_pointer_button_event *event);
static bool session_lock_surface(struct nextspace_server *server, struct wlr_surface *surface);
static void session_lock_client_destroy(struct wl_listener *listener, void *data);
static void session_lock_focus(struct nextspace_server *server, struct wlr_surface *surface);
static void session_lock_state_json(FILE *stream, struct nextspace_server *server);
static void session_lock_surfaces_json(FILE *stream, struct nextspace_server *server);
static void output_revert(struct nextspace_server *server, const char *reason);
static void application_position(struct nextspace_toplevel *view);
static void application_detach(struct nextspace_toplevel *view);
static void color_pick_begin(struct wl_client *client, struct wl_resource *resource,
  uint32_t request_id, uint32_t serial);
static void color_pick_cancel(struct wl_client *client, struct wl_resource *resource,
  uint32_t request_id);
static void color_pick_finish(struct nextspace_server *server, uint32_t phase, uint32_t argb);
static void focus_toplevel(struct nextspace_toplevel *view, struct wlr_surface *surface);
static void shell_window_changed(struct nextspace_toplevel *view);
static void shell_window_closed(struct nextspace_toplevel *view);
static void shell_focus_changed(struct nextspace_server *server);
static void policy_update_popups(struct nextspace_server *server);
static struct wlr_scene_tree *policy_layer(struct nextspace_server *server, int level);
static void policy_set_level(struct nextspace_toplevel *view, int level);
static void policy_order(struct nextspace_toplevel *view, bool above, struct nextspace_toplevel *relative);
static void policy_set_minimized(struct nextspace_toplevel *view, bool minimized);
static void policy_set_shaded(struct nextspace_toplevel *view, bool shaded);
static void policy_set_presented(struct nextspace_toplevel *view, bool presented);
static void policy_set_client_presented(struct nextspace_toplevel *view, bool presented);
static void policy_update_clip(struct nextspace_toplevel *view);
static bool policy_size_geometry(struct nextspace_toplevel *view);
static void output_work_area(struct nextspace_output *output, struct wlr_box *bounds);
static void application_work_areas(struct nextspace_server *server);
static bool read_buffer_samples(struct wlr_buffer *buffer, uint32_t samples[5]);
static bool read_buffer_pixels(struct wlr_buffer *buffer, uint32_t samples[5], uint64_t counts[3], uint64_t *hash);
static void reset_cursor_mode(struct nextspace_server *server);
static void finish_cursor_mode(struct nextspace_server *server, bool cancelled);
static void shell_interactive_move(struct nextspace_toplevel *view, uint32_t phase);
static void process_cursor_motion(struct nextspace_server *server, uint32_t time);
static void cancel_pointer_drag(struct nextspace_server *server);
static void drag_cancel_origin(struct nextspace_toplevel *view);
static void policy_apply_visibility(struct nextspace_toplevel *view);
static void input_popup_update_all(struct nextspace_server *server);
static void server_new_keyboard(struct nextspace_server *server, struct wlr_input_device *device);
static void decoration_update(struct nextspace_toplevel *view);
static void decoration_set_title_appearance(struct nextspace_server *server,
  const char *font, uint32_t antialiased, uint32_t justification);
static void decoration_update_all(struct nextspace_server *server);
static void decoration_commit(struct nextspace_toplevel *view);
static void decoration_finish(struct nextspace_toplevel *view);
static bool decoration_pointer_button(struct nextspace_server *server,
  struct nextspace_toplevel *view, uint32_t button, uint32_t state, uint32_t time);
static void begin_interactive(struct nextspace_toplevel *toplevel,
  enum nextspace_cursor_mode mode, uint32_t edges, bool server_frame);

static bool decoration_visible(struct nextspace_toplevel *view) {
  return view->server_decorated && !view->fullscreen;
}

/* Native Wayland window policy. */
static struct wlr_surface *view_surface(struct nextspace_toplevel *view) {
  return view->xdg_toplevel->base->surface;
}
static struct nextspace_toplevel *view_for_surface(struct nextspace_server *server, struct wlr_surface *surface) {
  if (!surface) return NULL;
  surface = wlr_surface_get_root_surface(surface);
  struct wlr_xdg_surface *xdg = wlr_xdg_surface_try_from_wlr_surface(surface);
  while (xdg && xdg->role == WLR_XDG_SURFACE_ROLE_POPUP) {
    surface = xdg->popup->parent;
    xdg = wlr_xdg_surface_try_from_wlr_surface(surface);
  }
  struct nextspace_toplevel *view;
  wl_list_for_each(view, &server->toplevels, link)
    if (view_surface(view) == surface) return view;
  return NULL;
}
static const char *view_title(struct nextspace_toplevel *view) {
  return view->xdg_toplevel->title;
}
static const char *view_app_id(struct nextspace_toplevel *view) {
  const char *name = view->xdg_toplevel->app_id;
  return name ? name : "";
}
static pid_t view_pid(struct nextspace_toplevel *view) {
  pid_t pid = 0;
  wl_client_get_credentials(wl_resource_get_client(view_surface(view)->resource), &pid, NULL, NULL);
  return pid;
}
static void view_geometry(struct nextspace_toplevel *view, struct wlr_box *box) {
  wlr_xdg_surface_get_geometry(view->xdg_toplevel->base, box);
  if (decoration_visible(view)) {
    box->x = box->y = 0;
    box->width += ns_frame_horizontal(view->frame);
    box->height += ns_frame_vertical(view->frame);
  }
}
static void view_move(struct nextspace_toplevel *view, int x, int y) {
  wlr_scene_node_set_position(&view->scene_tree->node, x, y);
  decoration_update(view);
  policy_update_popups(view->server);
  application_position(view);
}
static void view_resize(struct nextspace_toplevel *view, int width, int height) {
  if (decoration_visible(view)) {
    int horizontal = ns_frame_horizontal(view->frame), vertical = ns_frame_vertical(view->frame);
    width = width > horizontal ? width - horizontal : 1;
    height = height > vertical ? height - vertical : 1;
  }
  wlr_xdg_toplevel_set_size(view->xdg_toplevel, width, height);
}
static void view_activate(struct nextspace_toplevel *view, bool active) {
  wlr_xdg_toplevel_set_activated(view->xdg_toplevel, active);
  decoration_update(view);
}

struct view_buffer_search { struct wlr_surface *surface; struct wlr_scene_buffer *buffer; };
static void find_view_buffer(struct wlr_scene_buffer *buffer, int x, int y, void *data) {
  struct view_buffer_search *search = data;
  struct wlr_scene_surface *surface = wlr_scene_surface_try_from_buffer(buffer);
  if (surface && surface->surface == search->surface) search->buffer = buffer;
}
static struct wlr_scene_buffer *view_buffer(struct nextspace_toplevel *view) {
  struct view_buffer_search search = {.surface = view_surface(view)};
  wlr_scene_node_for_each_buffer(&view->scene_tree->node, find_view_buffer, &search);
  return search.buffer;
}

#include "application.h"
#include "policy.h"
#include "desktops.h"
#include "clipboard.h"
#include "outputs.h"
#include "input-settings.h"
#include "text-input.h"
#include "security.h"
#include "shell.h"
#include "drag.h"
#include "decorations.h"
#include "scene-color.h"
#include "color-pick.h"

static void request_activate(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, request_activate);
  struct wlr_xdg_activation_v1_request_activate_event *event = data;
  /* wlroots validates the requesting client's serial and focused source at
     token creation. Tokens without that input provenance cannot steal focus. */
  if (event->token->seat != server->seat || !event->token->surface) return;
  struct nextspace_toplevel *view = view_for_surface(server, event->surface);
  if (!view || !view->mapped || (view->application_window && !view->application_window->accepts_focus)) return;
  wlr_log(WLR_DEBUG, "Activation request for window %u", view->id);
  if (!view->sticky) desktop_switch(server, view->desktop);
  focus_toplevel(view, event->surface);
}

static void focus_toplevel(struct nextspace_toplevel *toplevel, struct wlr_surface *surface) {
	/* Note: this function only deals with keyboard focus. */
	if (toplevel == NULL || !policy_visible(toplevel)) {
		return;
	}
	struct nextspace_server *server = toplevel->server;
	if (server->locked) return;
	struct wlr_seat *seat = server->seat;
	struct nextspace_toplevel *requested = toplevel;
	if (toplevel->application_window && !toplevel->application_window->accepts_focus) {
		/* Menus take pointer input while the application's document keeps keys. */
		struct wl_client *client = wl_resource_get_client(view_surface(toplevel)->resource);
		struct nextspace_toplevel *candidate;
		toplevel = NULL;
		wl_list_for_each(candidate, &server->toplevels, link) {
			if (candidate == requested || !candidate->mapped || !policy_visible(candidate) ||
			    (candidate->application_window && !candidate->application_window->accepts_focus)) continue;
			if (wl_resource_get_client(view_surface(candidate)->resource) == client) {
				toplevel = candidate; surface = view_surface(candidate); break;
			}
		}
		wlr_scene_node_raise_to_top(&requested->scene_tree->node);
		if (!toplevel) {
			if (seat->keyboard_state.focused_surface == view_surface(requested)) {
				view_activate(requested, false);
				wlr_seat_keyboard_notify_clear_focus(seat);
				decoration_update_all(server);
			}
			return;
		}
	}
	struct wlr_surface *prev_surface = seat->keyboard_state.focused_surface;
	if (prev_surface == surface) {
		/* Don't re-focus an already focused surface. */
    policy_focus_layers(server, toplevel);
    policy_order(toplevel, true, NULL);
		return;
	}
	wlr_log(WLR_DEBUG, "Keyboard focus -> window %u", toplevel->id);
	if (prev_surface) {
		/*
		 * Deactivate the previously focused surface. This lets the client know
		 * it no longer has focus and the client will repaint accordingly, e.g.
		 * stop displaying a caret.
		 */
		struct wlr_xdg_toplevel *prev_toplevel =
			wlr_xdg_toplevel_try_from_wlr_surface(prev_surface);
		if (prev_toplevel != NULL) {
			wlr_xdg_toplevel_set_activated(prev_toplevel, false);
		}
	}
	struct wlr_keyboard *keyboard = wlr_seat_get_keyboard(seat);
  policy_focus_layers(server, toplevel);
	/* Move the toplevel to the front */
	wlr_scene_node_raise_to_top(&toplevel->scene_tree->node);
	wl_list_remove(&toplevel->link);
  policy_update_popups(toplevel->server);
	wl_list_insert(&server->toplevels, &toplevel->link);
	/* Activate the new surface */
	view_activate(toplevel, true);
	/*
	 * Tell the seat to have the keyboard enter this surface. wlroots will keep
	 * track of this and automatically send key events to the appropriate
	 * clients without additional work on your part.
	 */
	if (keyboard != NULL) {
		wlr_seat_keyboard_notify_enter(seat, view_surface(toplevel),
			keyboard->keycodes, keyboard->num_keycodes, &keyboard->modifiers);
	}
	if (requested != toplevel) wlr_scene_node_raise_to_top(&requested->scene_tree->node);
  shell_focus_changed(server);
  decoration_update_all(server);
}

static void keyboard_handle_modifiers(
		struct wl_listener *listener, void *data) {
	/* This event is raised when a modifier key, such as shift or alt, is
	 * pressed. We simply communicate this to the client. */
	struct nextspace_keyboard *keyboard =
		wl_container_of(listener, keyboard, modifiers);
  if (keyboard->server->locked && wlr_input_device_get_virtual_keyboard(&keyboard->wlr_keyboard->base)) return;
	/*
	 * A seat can only have one keyboard, but this is a limitation of the
	 * Wayland protocol - not wlroots. We assign all connected keyboards to the
	 * same seat. You can swap out the underlying wlr_keyboard like this and
	 * wlr_seat handles this transparently.
	 */
	wlr_seat_set_keyboard(keyboard->server->seat, keyboard->wlr_keyboard);

  struct wlr_input_method_keyboard_grab_v2 *grab = input_method_keyboard_grab(keyboard);
  if (grab) {
    wlr_input_method_keyboard_grab_v2_send_modifiers(grab, &keyboard->wlr_keyboard->modifiers);
    return;
  }
	/* Send modifiers to the client. */
	wlr_seat_keyboard_notify_modifiers(keyboard->server->seat,
		&keyboard->wlr_keyboard->modifiers);
}

static bool handle_keybinding(struct nextspace_server *server, xkb_keysym_t sym, uint32_t modifiers) {
  modifiers &= WLR_MODIFIER_CTRL | WLR_MODIFIER_ALT | WLR_MODIFIER_SHIFT | WLR_MODIFIER_LOGO;
  if (sym == XKB_KEY_l && modifiers == (WLR_MODIFIER_CTRL | WLR_MODIFIER_ALT) && server->shell_broker_fd >= 0) {
    session_lock_request(server, true); return true;
  }
  unsigned action;
  for (action = 0; action < 18; action++)
    if (server->shortcuts[action][0] && server->shortcuts[action][0] == sym &&
        server->shortcuts[action][1] == modifiers) break;
  if (action == 18) return false;
  if (action >= NEXTSPACE_SHELL_V1_SHORTCUT_ACTION_DESKTOP_1) {
    desktop_switch(server, action - NEXTSPACE_SHELL_V1_SHORTCUT_ACTION_DESKTOP_1);
    return true;
  }
  if (action == NEXTSPACE_SHELL_V1_SHORTCUT_ACTION_NEXT_DESKTOP ||
      action == NEXTSPACE_SHELL_V1_SHORTCUT_ACTION_PREVIOUS_DESKTOP) {
    int next = (int)server->desktop + (action == NEXTSPACE_SHELL_V1_SHORTCUT_ACTION_NEXT_DESKTOP ? 1 : -1);
    if (next >= 0) desktop_switch(server, next);
    return true;
  }
  struct nextspace_toplevel *focused = view_for_surface(server, server->seat->keyboard_state.focused_surface);
  if (action == NEXTSPACE_SHELL_V1_SHORTCUT_ACTION_RAISE || action == NEXTSPACE_SHELL_V1_SHORTCUT_ACTION_LOWER) {
    if (focused) { policy_order(focused, action == NEXTSPACE_SHELL_V1_SHORTCUT_ACTION_RAISE, NULL); policy_refresh_pointer(server); }
    return true;
  }
  bool reverse = action == NEXTSPACE_SHELL_V1_SHORTCUT_ACTION_PREVIOUS_APPLICATION ||
    action == NEXTSPACE_SHELL_V1_SHORTCUT_ACTION_PREVIOUS_WINDOW;
  bool same_application = action == NEXTSPACE_SHELL_V1_SHORTCUT_ACTION_NEXT_WINDOW ||
    action == NEXTSPACE_SHELL_V1_SHORTCUT_ACTION_PREVIOUS_WINDOW;
  struct wl_list *head = &server->toplevels;
  for (struct wl_list *link = reverse ? head->next : head->prev; link != head;
       link = reverse ? link->next : link->prev) {
    struct nextspace_toplevel *view = wl_container_of(link, view, link);
    if (view == focused || !view->mapped || !policy_visible(view) ||
        (view->application_window && !view->application_window->accepts_focus)) continue;
    if (focused && ((view_pid(view) == view_pid(focused)) != same_application)) continue;
    focus_toplevel(view, view_surface(view)); break;
  }
  return true;
}

static void keyboard_handle_key(
		struct wl_listener *listener, void *data) {
	/* This event is raised when a key is pressed or released. */
	struct nextspace_keyboard *keyboard =
		wl_container_of(listener, keyboard, key);
	struct nextspace_server *server = keyboard->server;
	struct wlr_keyboard_key_event *event = data;
	struct wlr_seat *seat = server->seat;
	/* Translate libinput keycode -> xkbcommon. */
	uint32_t keycode = event->keycode + 8;
	const xkb_keysym_t *syms;
	int nsyms = xkb_state_key_get_syms(
			keyboard->wlr_keyboard->xkb_state, keycode, &syms);
  if (server->session && event->state == WL_KEYBOARD_KEY_STATE_PRESSED &&
      !wlr_input_device_get_virtual_keyboard(&keyboard->wlr_keyboard->base)) {
    for (int i = 0; i < nsyms; i++) {
      if (syms[i] >= XKB_KEY_XF86Switch_VT_1 && syms[i] <= XKB_KEY_XF86Switch_VT_12 &&
          wlr_session_change_vt(server->session, syms[i] - XKB_KEY_XF86Switch_VT_1 + 1)) {
        if (event->keycode < 768) keyboard->consumed_keys[event->keycode] = true;
        return;
      }
    }
  }
	if (server->locked) {
    if (event->keycode < 768) keyboard->consumed_keys[event->keycode] = false;
    if (!wlr_input_device_get_virtual_keyboard(&keyboard->wlr_keyboard->base) &&
        session_lock_surface(server, seat->keyboard_state.focused_surface)) {
      wlr_seat_set_keyboard(seat, keyboard->wlr_keyboard);
      wlr_seat_keyboard_notify_key(seat, event->time_msec, event->keycode, event->state);
    }
    return;
  }

  if (server->color_pick_window && event->state == WL_KEYBOARD_KEY_STATE_PRESSED) {
    for (int i = 0; i < nsyms; i++) {
      if (syms[i] == XKB_KEY_Escape)
        color_pick_finish(server, NEXTSPACE_WINDOW_V1_COLOR_PICK_PHASE_CANCELLED, 0);
      else if (syms[i] == XKB_KEY_Return || syms[i] == XKB_KEY_KP_Enter)
        color_pick_select(server);
    }
    if (event->keycode < 768) keyboard->consumed_keys[event->keycode] = true;
    return;
  }

	bool handled = event->state == WL_KEYBOARD_KEY_STATE_RELEASED && event->keycode < 768 &&
    keyboard->consumed_keys[event->keycode];
  if (event->keycode < 768) keyboard->consumed_keys[event->keycode] = false;
	uint32_t modifiers = wlr_keyboard_get_modifiers(keyboard->wlr_keyboard);
  if ((seat->drag || server->cursor_mode != NEXTSPACE_CURSOR_PASSTHROUGH) &&
      event->state == WL_KEYBOARD_KEY_STATE_PRESSED) {
    for (int i = 0; i < nsyms; i++) if (syms[i] == XKB_KEY_Escape) {
      if (seat->drag) cancel_pointer_drag(server);
      reset_cursor_mode(server); handled = true; break;
    }
  }
	if (!handled &&
			event->state == WL_KEYBOARD_KEY_STATE_PRESSED) {
    const xkb_keysym_t *base;
    xkb_layout_index_t layout = xkb_state_key_get_layout(keyboard->wlr_keyboard->xkb_state, keycode);
    int count = xkb_keymap_key_get_syms_by_level(keyboard->wlr_keyboard->keymap, keycode, layout, 0, &base);
    for (int i = 0; i < count && !handled; i++) handled = handle_keybinding(server, base[i], modifiers);
	}
  if (handled && event->state == WL_KEYBOARD_KEY_STATE_PRESSED && event->keycode < 768)
    keyboard->consumed_keys[event->keycode] = true;

	if (!handled) {

    struct wlr_input_method_keyboard_grab_v2 *grab = input_method_keyboard_grab(keyboard);
    if (grab) {
      wlr_input_method_keyboard_grab_v2_send_key(grab, event->time_msec, event->keycode, event->state);
      return;
    }
		/* Otherwise, we pass it along to the client. */
		wlr_seat_set_keyboard(seat, keyboard->wlr_keyboard);
		wlr_seat_keyboard_notify_key(seat, event->time_msec,
			event->keycode, event->state);
    if (event->state == WL_KEYBOARD_KEY_STATE_PRESSED && !wlr_seat_keyboard_has_grab(seat)) {
      struct nextspace_toplevel *view = view_for_surface(server, seat->keyboard_state.focused_surface);
      for (int i = 0; view && i < nsyms; i++) {
        if (syms[i] != XKB_KEY_space && syms[i] != XKB_KEY_Return && syms[i] != XKB_KEY_KP_Enter) continue;
        server->color_pick_gesture.serial = wl_display_get_serial(server->wl_display);
        server->color_pick_gesture.view = view->id;
        server->color_pick_gesture.time = color_pick_time();
        server->color_pick_gesture.keyboard = true;
      }
    }
	}
}

static void keyboard_handle_destroy(struct wl_listener *listener, void *data) {
	/* This event is raised by the keyboard base wlr_input_device to signal
	 * the destruction of the wlr_keyboard. It will no longer receive events
	 * and should be destroyed.
	 */
	struct nextspace_keyboard *keyboard =
		wl_container_of(listener, keyboard, destroy);
  struct nextspace_server *server = keyboard->server;
  bool selected = wlr_seat_get_keyboard(server->seat) == keyboard->wlr_keyboard;
	wl_list_remove(&keyboard->modifiers.link);
	wl_list_remove(&keyboard->key.link);
	wl_list_remove(&keyboard->destroy.link);
	wl_list_remove(&keyboard->link);
  if (selected) {
    struct wlr_keyboard *replacement = NULL;
    struct nextspace_keyboard *candidate;
    wl_list_for_each(candidate, &server->keyboards, link) {
      bool virtual = wlr_input_device_get_virtual_keyboard(&candidate->wlr_keyboard->base);
      if (!virtual) { replacement = candidate->wlr_keyboard; break; }
      if (!server->locked && !replacement) replacement = candidate->wlr_keyboard;
    }
    wlr_seat_set_keyboard(server->seat, replacement);
    if (server->locked) session_lock_focus(server, NULL);
  }
	free(keyboard);
}

static void server_new_keyboard(struct nextspace_server *server,
		struct wlr_input_device *device) {
	struct wlr_keyboard *wlr_keyboard = wlr_keyboard_from_input_device(device);

	struct nextspace_keyboard *keyboard = calloc(1, sizeof(*keyboard));
	keyboard->server = server;
	keyboard->wlr_keyboard = wlr_keyboard;

  if (!wlr_input_device_get_virtual_keyboard(device)) {
    wlr_keyboard_set_keymap(wlr_keyboard, server->input_keymap);
    wlr_keyboard_set_repeat_info(wlr_keyboard, server->input_rate, server->input_delay);
    input_apply_numlock(wlr_keyboard, server->input_numlock);
  }

	/* Here we set up listeners for keyboard events. */
	keyboard->modifiers.notify = keyboard_handle_modifiers;
	wl_signal_add(&wlr_keyboard->events.modifiers, &keyboard->modifiers);
	keyboard->key.notify = keyboard_handle_key;
	wl_signal_add(&wlr_keyboard->events.key, &keyboard->key);
	keyboard->destroy.notify = keyboard_handle_destroy;
	wl_signal_add(&device->events.destroy, &keyboard->destroy);

	if (!server->locked || !wlr_input_device_get_virtual_keyboard(device))
    wlr_seat_set_keyboard(server->seat, keyboard->wlr_keyboard);

	/* And add the keyboard to our list of keyboards */
	wl_list_insert(&server->keyboards, &keyboard->link);
  if (server->locked) session_lock_focus(server, NULL);
}

static void server_new_pointer(struct nextspace_server *server,
		struct wlr_input_device *device) {
  input_attach_pointer(server, device);
	wlr_cursor_attach_input_device(server->cursor, device);
}

static void server_new_input(struct wl_listener *listener, void *data) {
	/* This event is raised by the backend when a new input device becomes
	 * available. */
	struct nextspace_server *server =
		wl_container_of(listener, server, new_input);
	struct wlr_input_device *device = data;
	switch (device->type) {
	case WLR_INPUT_DEVICE_KEYBOARD:
		server_new_keyboard(server, device);
		break;
	case WLR_INPUT_DEVICE_POINTER:
		server_new_pointer(server, device);
		break;
	default:
		break;
	}
	/* We need to let the wlr_seat know what our capabilities are, which is
	 * communiciated to the client. In TinyWL we always have a cursor, even if
	 * there are no pointer devices, so we always include that capability. */
	uint32_t caps = WL_SEAT_CAPABILITY_POINTER;
	if (!wl_list_empty(&server->keyboards)) {
		caps |= WL_SEAT_CAPABILITY_KEYBOARD;
	}
	wlr_seat_set_capabilities(server->seat, caps);
}

static void client_cursor_destroy(struct wl_listener *listener, void *data) {
  struct nextspace_server *server = wl_container_of(listener, server, client_cursor_destroy);
  wl_list_remove(&server->client_cursor_destroy.link);
  server->client_cursor = NULL;
}

/* wlroots 0.18 refreshes surface output membership on cursor image commits,
 * but movement alone only updates output_cursor.visible. Refresh the matching
 * protocol state here so a stationary image can change density across outputs. */
static void cursor_outputs_changed(struct nextspace_server *server) {
  struct wlr_surface *surface = server->client_cursor;
  if (!surface) return;
  float scale = 1;
  struct nextspace_output *output;
  wl_list_for_each(output, &server->outputs, link) {
    bool visible = false;
    struct wlr_output_cursor *cursor;
    wl_list_for_each(cursor, &output->wlr_output->cursors, link)
      visible |= cursor->enabled && cursor->visible;
    if (visible) {
      wlr_surface_send_enter(surface, output->wlr_output);
      if (output->wlr_output->scale > scale) scale = output->wlr_output->scale;
    } else wlr_surface_send_leave(surface, output->wlr_output);
  }
  wlr_fractional_scale_v1_notify_scale(surface, scale);
  wlr_surface_set_preferred_buffer_scale(surface, ceilf(scale));
}

static void seat_request_cursor(struct wl_listener *listener, void *data) {
	struct nextspace_server *server = wl_container_of(
			listener, server, request_cursor);
	/* This event is raised by the seat when a client provides a cursor image */
	struct wlr_seat_pointer_request_set_cursor_event *event = data;
	struct wlr_seat_client *focused_client =
		server->seat->pointer_state.focused_client;
	/* This can be sent by any client, so we check to make sure this one is
	 * actually has pointer focus first. */
	if (focused_client == event->seat_client && !server->color_pick_window) {
    if (server->client_cursor) wl_list_remove(&server->client_cursor_destroy.link);
    server->client_cursor = event->surface;
    server->cursor_hotspot_x = event->hotspot_x;
    server->cursor_hotspot_y = event->hotspot_y;
    if (event->surface) {
      server->client_cursor_destroy.notify = client_cursor_destroy;
      wl_signal_add(&event->surface->events.destroy, &server->client_cursor_destroy);
    }
		/* Once we've vetted the client, we can tell the cursor to use the
		 * provided surface as the cursor image. It will set the hardware cursor
		 * on the output that it's currently on and continue to do so as the
		 * cursor moves between outputs. */
		wlr_cursor_set_surface(server->cursor, event->surface,
				event->hotspot_x, event->hotspot_y);
	}
}

static void seat_request_set_selection(struct wl_listener *listener, void *data) {
	/* This event is raised by the seat when a client wants to set the selection,
	 * usually when the user copies something. wlroots allows compositors to
	 * ignore such requests if they so choose, but in nextspace we always honor
	 */
	struct nextspace_server *server = wl_container_of(
			listener, server, request_set_selection);
	struct wlr_seat_request_set_selection_event *event = data;
  if (!event->source) clipboard_cancel_copy(server);
	wlr_seat_set_selection(server->seat, event->source, event->serial);
}

static void seat_request_set_primary_selection(struct wl_listener *listener, void *data) {
  struct nextspace_server *server = wl_container_of(listener, server, request_set_primary_selection);
  struct wlr_seat_request_set_primary_selection_event *event = data;
  wlr_seat_set_primary_selection(server->seat, event->source, event->serial);
}

static struct nextspace_toplevel *desktop_toplevel_at(
		struct nextspace_server *server, double lx, double ly,
		struct wlr_surface **surface, double *sx, double *sy) {
	/* This returns the topmost node in the scene at the given layout coords.
	 * We only care about surface nodes as we are specifically looking for a
	 * surface in the surface tree of a nextspace_toplevel. */
	struct wlr_scene_node *node = wlr_scene_node_at(
		&server->scene->tree.node, lx, ly, sx, sy);
	if (node == NULL) {
		return NULL;
	}
	struct wlr_scene_buffer *scene_buffer = node->type == WLR_SCENE_NODE_BUFFER ?
    wlr_scene_buffer_from_node(node) : NULL;
	struct wlr_scene_surface *scene_surface =
		scene_buffer ? wlr_scene_surface_try_from_buffer(scene_buffer) : NULL;

	*surface = scene_surface ? scene_surface->surface : NULL;
	/* Find the node corresponding to the nextspace_toplevel at the root of this
	 * surface tree, it is the only one for which we set the data field. */
	struct wlr_scene_tree *tree = node->parent;
	while (tree != NULL && tree->node.data == NULL) {
		tree = tree->node.parent;
	}
	struct nextspace_toplevel *view = tree ? tree->node.data : NULL;
  return scene_surface || (view && decoration_visible(view)) ? view : NULL;
}

static void finish_cursor_mode(struct nextspace_server *server, bool cancelled) {
  struct nextspace_toplevel *view = server->grabbed_toplevel;
  bool moving = server->cursor_mode == NEXTSPACE_CURSOR_MOVE;
	server->cursor_mode = NEXTSPACE_CURSOR_PASSTHROUGH;
	server->grabbed_toplevel = NULL;
  server->grab_pending = false;
  if (view && moving && view->mapped) {
    if (cancelled) {
      if (server->grab_maximized) {
        if (view->maximized != server->grab_maximized)
          policy_set_size_state(view, server->grab_maximized, false, NULL);
        view->normal_geometry = server->grab_normal_geometry;
        view->maximized_dx = server->grab_maximized_dx;
        view->maximized_dy = server->grab_maximized_dy;
        policy_size_geometry(view);
      } else {
        int x = server->grab_geobox.x, y = server->grab_geobox.y;
        constrain_position(view, &x, &y);
        view_move(view, x, y);
      }
    }
    shell_interactive_move(view, cancelled ? 2 : 1);
  }
}
static void reset_cursor_mode(struct nextspace_server *server) {
  struct nextspace_toplevel *pressed = server->decoration_pressed;
  server->decoration_pressed = NULL;
  server->decoration_button = 0;
  finish_cursor_mode(server, true);
  if (pressed) decoration_update(pressed);
}

static void prepare_cursor_move(struct nextspace_toplevel *view)
{
  struct nextspace_server *server = view->server;
  if (view->maximized && server->maximized_drag_mode != NEXTSPACE_SHELL_V1_MAXIMIZED_DRAG_MODE_MOVE) {
    if (server->maximized_drag_mode == NEXTSPACE_SHELL_V1_MAXIMIZED_DRAG_MODE_UNMAXIMIZE)
      view->normal_geometry = server->grab_geobox;
    policy_apply_size_state(view, 0, false, NULL, server->grabbed_toplevel == view);
    if (server->maximized_drag_mode == NEXTSPACE_SHELL_V1_MAXIMIZED_DRAG_MODE_RESTORE_GEOMETRY) {
      double ratio = (server->grab_start_x - server->grab_geobox.x) / server->grab_geobox.width;
      view_move(view, server->grab_start_x - ratio * view->normal_geometry.width, server->grab_geobox.y);
    }
  }
  server->grab_x = server->grab_start_x - view->scene_tree->node.x;
  server->grab_y = server->grab_start_y - view->scene_tree->node.y;
}

static void process_cursor_move(struct nextspace_server *server, uint32_t time) {
	/* Move the grabbed toplevel to the new position. */
	struct nextspace_toplevel *toplevel = server->grabbed_toplevel;
  if (server->grab_pending) {
    if (fabs(server->cursor->x - server->grab_start_x) < DECORATION_MOVE_THRESHOLD &&
        fabs(server->cursor->y - server->grab_start_y) < DECORATION_MOVE_THRESHOLD) return;
    server->grab_pending = false;
    prepare_cursor_move(toplevel);
  }
  int x = server->cursor->x - server->grab_x;
  int y = server->cursor->y - server->grab_y;
  if (toplevel->maximized) {
    if (toplevel->maximized & MAXIMIZE_HORIZONTAL)
      toplevel->maximized_dx += x - toplevel->scene_tree->node.x;
    else toplevel->normal_geometry.x = x;
    if (toplevel->maximized & MAXIMIZE_VERTICAL)
      toplevel->maximized_dy += y - toplevel->scene_tree->node.y;
    else toplevel->normal_geometry.y = y;
  }
  view_move(toplevel, x, y);
}

static void process_cursor_resize(struct nextspace_server *server, uint32_t time) {
	/*
	 * Resizing the grabbed toplevel can be a little bit complicated, because we
	 * could be resizing from any corner or edge. This not only resizes the
	 * toplevel on one or two axes, but can also move the toplevel if you resize
	 * from the top or left edges (or top-left corner).
	 *
	 * Note that some shortcuts are taken here. In a more fleshed-out
	 * compositor, you'd wait for the client to prepare a buffer at the new
	 * size, then commit any movement that was prepared.
	 */
	struct nextspace_toplevel *toplevel = server->grabbed_toplevel;
	double border_x = server->cursor->x - server->grab_x;
	double border_y = server->cursor->y - server->grab_y;
	int new_left = server->grab_geobox.x;
	int new_right = server->grab_geobox.x + server->grab_geobox.width;
	int new_top = server->grab_geobox.y;
	int new_bottom = server->grab_geobox.y + server->grab_geobox.height;

	if (server->resize_edges & WLR_EDGE_TOP) {
		new_top = border_y;
		if (new_top >= new_bottom) {
			new_top = new_bottom - 1;
		}
	} else if (server->resize_edges & WLR_EDGE_BOTTOM) {
		new_bottom = border_y;
		if (new_bottom <= new_top) {
			new_bottom = new_top + 1;
		}
	}
	if (server->resize_edges & WLR_EDGE_LEFT) {
		new_left = border_x;
		if (new_left >= new_right) {
			new_left = new_right - 1;
		}
	} else if (server->resize_edges & WLR_EDGE_RIGHT) {
		new_right = border_x;
		if (new_right <= new_left) {
			new_right = new_left + 1;
		}
	}

	struct wlr_box geo_box;
	view_geometry(toplevel, &geo_box);
	view_move(toplevel, new_left - geo_box.x, new_top - geo_box.y);

	int new_width = new_right - new_left;
	int new_height = new_bottom - new_top;
	view_resize(toplevel, new_width, new_height);
}

static void process_cursor_motion(struct nextspace_server *server, uint32_t time) {
	if (server->locked) { session_lock_pointer_motion(server, time); return; }
  if (server->color_pick_window) { color_pick_motion(server); return; }
	cursor_outputs_changed(server);
  drag_icon_update(server);
	/* If the mode is non-passthrough, delegate to those functions. */
	if (server->cursor_mode == NEXTSPACE_CURSOR_MOVE) {
		process_cursor_move(server, time);
		return;
	} else if (server->cursor_mode == NEXTSPACE_CURSOR_RESIZE) {
		process_cursor_resize(server, time);
		return;
	}

	/* Otherwise, find the toplevel under the pointer and send the event along. */
	double sx, sy;
	struct wlr_seat *seat = server->seat;
	struct wlr_surface *surface = NULL;
	struct nextspace_toplevel *toplevel = desktop_toplevel_at(server,
			server->cursor->x, server->cursor->y, &surface, &sx, &sy);
  /* Keep the implicit button grab on its original surface until release.
     In particular, Xwayland must not lose its grab while XDND targets arrive. */
  if (seat->pointer_state.button_count && !wlr_seat_pointer_has_grab(seat) &&
      seat->pointer_state.focused_surface) {
    struct view_buffer_search search = {.surface = seat->pointer_state.focused_surface};
    wlr_scene_node_for_each_buffer(&server->scene->tree.node, find_view_buffer, &search);
    int x, y;
    if (search.buffer && wlr_scene_node_coords(&search.buffer->node, &x, &y)) {
      surface = search.surface;
      toplevel = view_for_surface(server, surface);
      sx = server->cursor->x - x; sy = server->cursor->y - y;
    }
  }
  shell_pointer_changed(server, toplevel);
  drag_target_actions(server, surface);
	if (!surface) {
		/* If there's no toplevel under the cursor, set the cursor image to a
		 * default. This is what makes the cursor image appear when you move it
		 * around the screen, not over any toplevels. */
		wlr_cursor_set_xcursor(server->cursor, server->cursor_mgr, decoration_cursor_name(toplevel));
    if (server->client_cursor) client_cursor_destroy(&server->client_cursor_destroy, NULL);
	}
	if (surface) {
		/*
		 * Send pointer enter and motion events.
		 *
		 * The enter event gives the surface "pointer focus", which is distinct
		 * from keyboard focus. You get pointer focus by moving the pointer over
		 * a window.
		 *
		 * Note that wlroots will avoid sending duplicate enter/motion events if
		 * the surface has already has pointer focus or if the client is already
		 * aware of the coordinates passed.
		 */
		wlr_seat_pointer_notify_enter(seat, surface, sx, sy);
		wlr_seat_pointer_notify_motion(seat, time, sx, sy);
	} else {
		/* Clear pointer focus so future button events and such are not sent to
		 * the last client to have the cursor over it. */
		wlr_seat_pointer_notify_clear_focus(seat);
	}
  drag_pointer_moved(server);
}

static void server_cursor_motion(struct wl_listener *listener, void *data) {
	/* This event is forwarded by the cursor when a pointer emits a _relative_
	 * pointer motion event (i.e. a delta) */
	struct nextspace_server *server =
		wl_container_of(listener, server, cursor_motion);
	struct wlr_pointer_motion_event *event = data;
	/* The cursor doesn't move unless we tell it to. The cursor automatically
	 * handles constraining the motion to the output layout, as well as any
	 * special configuration applied for the specific input device which
	 * generated the event. You can pass NULL for the device if you want to move
	 * the cursor around without any input. */
	wlr_cursor_move(server->cursor, &event->pointer->base,
			event->delta_x, event->delta_y);
	process_cursor_motion(server, event->time_msec);
}

static void server_cursor_motion_absolute(
		struct wl_listener *listener, void *data) {
	/* This event is forwarded by the cursor when a pointer emits an _absolute_
	 * motion event, from 0..1 on each axis. This happens, for example, when
	 * wlroots is running under a Wayland window rather than KMS+DRM, and you
	 * move the mouse over the window. You could enter the window from any edge,
	 * so we have to warp the mouse there. There is also some hardware which
	 * emits these events. */
	struct nextspace_server *server =
		wl_container_of(listener, server, cursor_motion_absolute);
	struct wlr_pointer_motion_absolute_event *event = data;
	wlr_cursor_warp_absolute(server->cursor, &event->pointer->base, event->x,
		event->y);
	process_cursor_motion(server, event->time_msec);
}

static void server_cursor_button(struct wl_listener *listener, void *data) {
	/* This event is forwarded by the cursor when a pointer emits a button
	 * event. */
	struct nextspace_server *server =
		wl_container_of(listener, server, cursor_button);
	struct wlr_pointer_button_event *event = data;
  if (color_pick_button(server, event)) return;
  if (server->locked) { session_lock_pointer_button(server, event); return; }
	double sx, sy;
	struct wlr_surface *surface = NULL;
	struct nextspace_toplevel *toplevel = desktop_toplevel_at(server,
			server->cursor->x, server->cursor->y, &surface, &sx, &sy);
  if (!server->seat->pointer_state.button_count) server->decoration_buttons = 0;
  bool frame_grab = server->decoration_buttons != 0;
  bool client_grab = !frame_grab && server->seat->pointer_state.button_count > 0;
  if (client_grab) {
    /* An implicit content grab keeps its release, even over a server frame. */
    surface = server->seat->pointer_state.focused_surface;
    toplevel = view_for_surface(server, surface);
  }
  /* Keep seat button bookkeeping without leaking frame clicks to a client. */
  bool frame_press = !client_grab && toplevel && !surface && decoration_visible(toplevel);
  if (frame_grab || frame_press)
    wlr_seat_pointer_notify_clear_focus(server->seat);
  uint32_t frame_button = event->button >= 0x110 && event->button < 0x130 ? 1u << (event->button - 0x110) : 0;
  if (event->state == WL_POINTER_BUTTON_STATE_PRESSED && (frame_grab || frame_press))
    server->decoration_buttons |= frame_button;
  if (event->state == WL_POINTER_BUTTON_STATE_RELEASED) server->decoration_buttons &= ~frame_button;
  uint32_t serial = wlr_seat_pointer_notify_button(server->seat,
    event->time_msec, event->button, event->state);
  if (event->button == 0x110 && event->state == WL_POINTER_BUTTON_STATE_RELEASED) {
    server->color_pick_gesture.serial = serial;
    server->color_pick_gesture.view = surface && toplevel ? toplevel->id : 0;
    server->color_pick_gesture.time = color_pick_time();
    server->color_pick_gesture.keyboard = false;
  }
  if (decoration_pointer_button(server, surface || client_grab ? NULL : toplevel,
      event->button, event->state, event->time_msec)) return;
	if (event->state == WL_POINTER_BUTTON_STATE_RELEASED) {
		/* If you released any buttons, we exit interactive move/resize mode. */
		finish_cursor_mode(server, false);
    process_cursor_motion(server, event->time_msec);
	} else {
		/* Focus that client if the button was _pressed_ */
		focus_toplevel(toplevel, surface);
	}
}

static void server_cursor_axis(struct wl_listener *listener, void *data) {
	/* This event is forwarded by the cursor when a pointer emits an axis event,
	 * for example when you move the scroll wheel. */
	struct nextspace_server *server =
		wl_container_of(listener, server, cursor_axis);
	struct wlr_pointer_axis_event *event = data;
  if (server->color_pick_window) return;
  if (server->locked) {
    if (session_lock_surface(server, server->seat->pointer_state.focused_surface))
      wlr_seat_pointer_notify_axis(server->seat, event->time_msec, event->orientation,
        event->delta, event->delta_discrete, event->source, event->relative_direction);
    return;
  }
  if (server->seat->pointer_state.button_count && server->decoration_buttons) return;
  if (!server->seat->pointer_state.button_count) {
    double sx, sy;
    struct wlr_surface *surface = NULL;
    struct nextspace_toplevel *view = desktop_toplevel_at(server,
      server->cursor->x, server->cursor->y, &surface, &sx, &sy);
    if (!surface && decoration_pointer_axis(server, view, event)) return;
  }
	/* Notify the client with pointer focus of the axis event. */
	wlr_seat_pointer_notify_axis(server->seat,
			event->time_msec, event->orientation, event->delta,
			event->delta_discrete, event->source, event->relative_direction);
}

static void server_cursor_frame(struct wl_listener *listener, void *data) {
	/* This event is forwarded by the cursor when a pointer emits an frame
	 * event. Frame events are sent after regular pointer events to group
	 * multiple events together. For instance, two axis events may happen at the
	 * same time, in which case a frame event won't be sent in between. */
	struct nextspace_server *server =
		wl_container_of(listener, server, cursor_frame);
	/* Notify the client with pointer focus of the frame event. */
	wlr_seat_pointer_notify_frame(server->seat);
}

static void output_frame(struct wl_listener *listener, void *data) {
	/* This function is called every time an output is ready to display a frame,
	 * generally at the output's refresh rate (e.g. 60Hz). */
	struct nextspace_output *output = wl_container_of(listener, output, frame);
	struct wlr_scene *scene = output->server->scene;

	struct wlr_scene_output *scene_output = wlr_scene_get_scene_output(
		scene, output->wlr_output);

	/* Render the scene if needed and commit the output */
	if (wlr_scene_output_commit(scene_output, NULL)) color_pick_frame(output);

	struct timespec now;
	clock_gettime(CLOCK_MONOTONIC, &now);
	wlr_scene_output_send_frame_done(scene_output, &now);
}

static void output_request_state(struct wl_listener *listener, void *data) {
	/* This function is called when the backend requests a new state for
	 * the output. For example, Wayland and X11 backends request a new mode
	 * when the output window is resized. */
	struct nextspace_output *output = wl_container_of(listener, output, request_state);
	const struct wlr_output_event_request_state *event = data;
  output_revert(output->server, "backend requested a mode change");
  if (wlr_output_commit_state(output->wlr_output, event->state) && output->gamma_set &&
      output->wlr_output->enabled && !output_apply_gamma(output, output->gamma))
    wlr_log(WLR_ERROR, "Cannot restore gamma for %s after backend mode change", output->wlr_output->name);
}

static int rollback_scale(void *data);

static void output_destroy(struct wl_listener *listener, void *data) {
	struct nextspace_output *output = wl_container_of(listener, output, destroy);
  session_lock_output_destroy(output);

  struct nextspace_server *server = output->server;
  bool was_applying = server->output_applying;
  bool reverting = server->output_pending != NULL;
  server->output_applying = true;
	wl_list_remove(&output->link);
	wlr_output_layout_remove(output->server->output_layout, output->wlr_output);
	if (output->server->pending_output == output) {
		output->server->pending_output = NULL;
		wl_event_source_timer_update(output->server->rollback_timer, 0);
	}
  wl_list_remove(&output->commit.link);
  /* Only surviving heads may be committed during hotplug rollback. */
  output_revert(server, "output disconnected");
  if (server->primary_output_id == output->id) server->primary_output_id = 0;
  server->output_applying = was_applying;
  if (reverting) outputs_changed(server);
  else application_layout_changed(&server->layout_change, NULL);
	wl_list_remove(&output->frame.link);
	wl_list_remove(&output->request_state.link);
	wl_list_remove(&output->destroy.link);
	free(output);
}

static void server_new_output(struct wl_listener *listener, void *data) {
	/* This event is raised by the backend when a new output (aka a display or
	 * monitor) becomes available. */
	struct nextspace_server *server =
		wl_container_of(listener, server, new_output);
	struct wlr_output *wlr_output = data;
  output_revert(server, "output connected");

	/* Configures the output created by the backend to use our allocator
	 * and our renderer. Must be done once, before commiting the output */
	wlr_output_init_render(wlr_output, server->allocator, server->renderer);

	/* The output may be disabled, switch it on. */
	struct wlr_output_state state;
	wlr_output_state_init(&state);
	wlr_output_state_set_enabled(&state, true);

	/* Some backends don't have modes. DRM+KMS does, and we need to set a mode
	 * before we can use the output. The mode is a tuple of (width, height,
	 * refresh rate), and each monitor supports only a specific set of modes. We
	 * just pick the monitor's preferred mode, a more sophisticated compositor
	 * would let the user configure it. */
	struct wlr_output_mode *mode = wlr_output_preferred_mode(wlr_output);
	if (mode != NULL) {
		wlr_output_state_set_mode(&state, mode);
	}
	if (wlr_output_is_headless(wlr_output))
		wlr_output_state_set_custom_mode(&state, 1600, 1200, 60000);

	/* Atomically applies the new output state. */
	bool committed = wlr_output_commit_state(wlr_output, &state);
	wlr_output_state_finish(&state);
	if (!committed) return;

	/* Allocates and configures our state for this output */
	struct nextspace_output *output = calloc(1, sizeof(*output));
	output->wlr_output = wlr_output;
	output->server = server;
  output->gamma = (struct output_gamma){1, 1, 1, 1};
  output->id = ++server->next_output_id;
  output->commit.notify = output_committed;
  wl_signal_add(&wlr_output->events.commit, &output->commit);
  output->lock_present.notify = session_lock_output_present;
  wl_signal_add(&wlr_output->events.present, &output->lock_present);

	/* Sets up a listener for the frame event. */
	output->frame.notify = output_frame;
	wl_signal_add(&wlr_output->events.frame, &output->frame);

	/* Sets up a listener for the state request event. */
	output->request_state.notify = output_request_state;
	wl_signal_add(&wlr_output->events.request_state, &output->request_state);

	/* Sets up a listener for the destroy event. */
	output->destroy.notify = output_destroy;
	wl_signal_add(&wlr_output->events.destroy, &output->destroy);

	wl_list_insert(&server->outputs, &output->link);

	/* Adds this to the output layout. The add_auto function arranges outputs
	 * from left-to-right in the order they appear. A more sophisticated
	 * compositor would let the user configure the arrangement of outputs in the
	 * layout.
	 *
	 * The output layout utility automatically adds a wl_output global to the
	 * display, which Wayland clients can see to find out information about the
	 * output (such as DPI, scale factor, manufacturer, etc).
	 */
	struct wlr_output_layout_output *l_output = wlr_output_layout_add_auto(server->output_layout,
		wlr_output);
	struct wlr_scene_output *scene_output = wlr_scene_output_create(server->scene, wlr_output);
	wlr_scene_output_layout_add_output(server->scene_layout, l_output, scene_output);
  if (output_gamma_size(output) && !output_apply_gamma(output, output->gamma))
    wlr_log(WLR_ERROR, "Cannot initialize gamma for %s", wlr_output->name);
  outputs_changed(server);
}

static void xdg_toplevel_map(struct wl_listener *listener, void *data) {
	/* Called when the surface is mapped, or ready to display on-screen. */
	struct nextspace_toplevel *toplevel = wl_container_of(listener, toplevel, map);

	toplevel->mapped = true;
	if (toplevel->xdg_toplevel->parent) {
    struct nextspace_toplevel *parent = view_for_surface(toplevel->server,
      toplevel->xdg_toplevel->parent->base->surface);
    if (parent) toplevel->desktop = parent->desktop;
  }
	wl_list_insert(&toplevel->server->toplevels, &toplevel->link);
  wlr_scene_node_set_enabled(&toplevel->scene_tree->node, policy_visible(toplevel));

  /* Mapping a menu or shell icon must not activate its application's document.
     Explicit pointer activation still uses focus_toplevel's document routing. */
  if (!toplevel->application_window || toplevel->application_window->accepts_focus)
    focus_toplevel(toplevel, view_surface(toplevel));
  application_position(toplevel);
}

static void xdg_toplevel_unmap(struct wl_listener *listener, void *data) {
	/* Called when the surface is unmapped, and should no longer be shown. */
	struct nextspace_toplevel *toplevel = wl_container_of(listener, toplevel, unmap);

	if (!toplevel->mapped) return;
  if (toplevel->application_window && toplevel->server->color_pick_window == toplevel->application_window)
    color_pick_finish(toplevel->server, NEXTSPACE_WINDOW_V1_COLOR_PICK_PHASE_CANCELLED, 0);
  toplevel->selected = false;
  if (toplevel->server->decoration_click_view == toplevel->id)
    toplevel->server->decoration_click_view = 0;
  if (toplevel->server->decoration_scroll_view == toplevel->id)
    toplevel->server->decoration_scroll_remainder = 0;
  if (toplevel->server->decoration_pressed == toplevel) {
    toplevel->server->decoration_pressed = NULL;
    toplevel->server->decoration_button = 0;
  }
	bool focused = toplevel->server->seat->keyboard_state.focused_surface == view_surface(toplevel);
	toplevel->mapped = false;
  if (toplevel->xdg_toplevel) {
    if (toplevel->maximized || toplevel->fullscreen)
      wlr_scene_node_set_position(&toplevel->scene_tree->node,
        toplevel->normal_geometry.x, toplevel->normal_geometry.y);
    toplevel->maximized = toplevel->fullscreen = false;
    if (toplevel->fullscreen_background) {
      wlr_scene_node_destroy(&toplevel->fullscreen_background->node);
      toplevel->fullscreen_background = NULL;
    }
    wlr_scene_node_reparent(&toplevel->scene_tree->node, policy_layer(toplevel->server, toplevel->level));
  }
  shell_window_closed(toplevel);
	/* Reset the cursor mode if the grabbed toplevel was unmapped. */
	if (toplevel == toplevel->server->grabbed_toplevel) {
		reset_cursor_mode(toplevel->server);
	}

	wl_list_remove(&toplevel->link);
	if (focused) {
		struct nextspace_toplevel *candidate;
		wl_list_for_each(candidate, &toplevel->server->toplevels, link) {
			if (!candidate->mapped || !policy_visible(candidate) ||
			    (candidate->application_window && !candidate->application_window->accepts_focus)) continue;
			focus_toplevel(candidate, view_surface(candidate));
			break;
		}
	}
  policy_refresh_pointer(toplevel->server);
  if (focused) decoration_update_all(toplevel->server);
}

static void xdg_toplevel_commit(struct wl_listener *listener, void *data) {
	/* Called when a new surface state is committed. */
	struct nextspace_toplevel *toplevel = wl_container_of(listener, toplevel, commit);
  decoration_commit(toplevel);
  if (toplevel->shaded) policy_update_clip(toplevel);
  policy_center_fullscreen(toplevel);

	application_position(toplevel);
	if (toplevel->xdg_toplevel->base->initial_commit) {
		if (toplevel->decoration && toplevel->decoration->protocol)
      decoration_request(&toplevel->decoration->request, NULL);
		/* Honor pre-map size states; ordinary windows choose their own size. */
    struct wlr_xdg_toplevel_requested *requested = &toplevel->xdg_toplevel->requested;
    policy_set_size_state(toplevel, requested->maximized ? MAXIMIZE_BOTH : 0, requested->fullscreen,
      requested->fullscreen_output);
		if (!toplevel->maximized && !toplevel->fullscreen)
      wlr_xdg_toplevel_set_size(toplevel->xdg_toplevel, 0, 0);
	}
}

static void xdg_toplevel_destroy(struct wl_listener *listener, void *data) {
	/* Called when the xdg_toplevel is destroyed. */
	struct nextspace_toplevel *toplevel = wl_container_of(listener, toplevel, destroy);

	decoration_finish(toplevel);
	application_detach(toplevel);
	wl_list_remove(&toplevel->set_title.link);
	wl_list_remove(&toplevel->set_app_id.link);
	wl_list_remove(&toplevel->map.link);
	wl_list_remove(&toplevel->unmap.link);
	wl_list_remove(&toplevel->commit.link);
	wl_list_remove(&toplevel->destroy.link);
	wl_list_remove(&toplevel->request_move.link);
	wl_list_remove(&toplevel->request_resize.link);
	wl_list_remove(&toplevel->request_maximize.link);
	wl_list_remove(&toplevel->request_fullscreen.link);
	wl_list_remove(&toplevel->request_minimize.link);
	free(toplevel->shell_state.app_id);
	free(toplevel->shell_state.title);
	wlr_scene_node_destroy(&toplevel->scene_tree->node);

	free(toplevel);
}

static void begin_interactive(struct nextspace_toplevel *toplevel,
		enum nextspace_cursor_mode mode, uint32_t edges, bool server_frame) {
	/* This function sets up an interactive move or resize operation, where the
	 * compositor stops propegating pointer events to clients and instead
	 * consumes them itself, to move or resize windows. */
	struct nextspace_server *server = toplevel->server;
  if (!toplevel->mapped || !policy_visible(toplevel) || toplevel->fullscreen ||
      server->cursor_mode != NEXTSPACE_CURSOR_PASSTHROUGH ||
      !server->seat->pointer_state.button_count) return;
  if (toplevel->maximized && (mode != NEXTSPACE_CURSOR_MOVE ||
      server->maximized_drag_mode == NEXTSPACE_SHELL_V1_MAXIMIZED_DRAG_MODE_NO_MOVE)) return;
	struct wlr_surface *focused_surface =
		server->seat->pointer_state.focused_surface;
	if (!server_frame && (!focused_surface || view_surface(toplevel) !=
			wlr_surface_get_root_surface(focused_surface))) {
		/* Deny move/resize requests from unfocused clients. */
		return;
	}
	if (mode == NEXTSPACE_CURSOR_MOVE) {
    view_geometry(toplevel, &server->grab_geobox);
    server->grab_geobox.x = toplevel->scene_tree->node.x;
    server->grab_geobox.y = toplevel->scene_tree->node.y;
    server->grab_maximized = toplevel->maximized;
    server->grab_normal_geometry = toplevel->normal_geometry;
    server->grab_maximized_dx = toplevel->maximized_dx;
    server->grab_maximized_dy = toplevel->maximized_dy;
    server->grab_start_x = server->cursor->x; server->grab_start_y = server->cursor->y;
    server->grab_pending = server_frame;
    if (!server_frame) prepare_cursor_move(toplevel);
		server->grab_x = server->cursor->x - toplevel->scene_tree->node.x;
		server->grab_y = server->cursor->y - toplevel->scene_tree->node.y;
    shell_interactive_move(toplevel, 0);
	} else {
		struct wlr_box geo_box;
		view_geometry(toplevel, &geo_box);

		double border_x = (toplevel->scene_tree->node.x + geo_box.x) +
			((edges & WLR_EDGE_RIGHT) ? geo_box.width : 0);
		double border_y = (toplevel->scene_tree->node.y + geo_box.y) +
			((edges & WLR_EDGE_BOTTOM) ? geo_box.height : 0);
		server->grab_x = server->cursor->x - border_x;
		server->grab_y = server->cursor->y - border_y;

		server->grab_geobox = geo_box;
		server->grab_geobox.x += toplevel->scene_tree->node.x;
		server->grab_geobox.y += toplevel->scene_tree->node.y;

		server->resize_edges = edges;
	}
  server->grabbed_toplevel = toplevel;
  server->cursor_mode = mode;
}

static void xdg_toplevel_request_move(
		struct wl_listener *listener, void *data) {
	/* This event is raised when a client would like to begin an interactive
	 * move, typically because the user clicked on their client-side
	 * decorations. Note that a more sophisticated compositor should check the
	 * provided serial against a list of button press serials sent to this
	 * client, to prevent the client from requesting this whenever they want. */
	struct nextspace_toplevel *toplevel = wl_container_of(listener, toplevel, request_move);
	struct wlr_xdg_toplevel_move_event *event = data;
	if (wlr_seat_validate_pointer_grab_serial(toplevel->server->seat,
			toplevel->xdg_toplevel->base->surface, event->serial))
		begin_interactive(toplevel, NEXTSPACE_CURSOR_MOVE, 0, false);
}

static void xdg_toplevel_request_resize(
		struct wl_listener *listener, void *data) {
	/* This event is raised when a client would like to begin an interactive
	 * resize, typically because the user clicked on their client-side
	 * decorations. Note that a more sophisticated compositor should check the
	 * provided serial against a list of button press serials sent to this
	 * client, to prevent the client from requesting this whenever they want. */
	struct wlr_xdg_toplevel_resize_event *event = data;
	struct nextspace_toplevel *toplevel = wl_container_of(listener, toplevel, request_resize);
	if (wlr_seat_validate_pointer_grab_serial(toplevel->server->seat,
			toplevel->xdg_toplevel->base->surface, event->serial))
		begin_interactive(toplevel, NEXTSPACE_CURSOR_RESIZE, event->edges, false);
}

static void xdg_toplevel_request_maximize(
		struct wl_listener *listener, void *data) {
	struct nextspace_toplevel *toplevel =
		wl_container_of(listener, toplevel, request_maximize);
	if (toplevel->xdg_toplevel->base->initialized) {
    policy_set_size_state(toplevel, toplevel->xdg_toplevel->requested.maximized ? MAXIMIZE_BOTH : 0,
      toplevel->fullscreen, NULL);
	}
}

static void xdg_toplevel_request_fullscreen(
		struct wl_listener *listener, void *data) {
	struct nextspace_toplevel *toplevel =
		wl_container_of(listener, toplevel, request_fullscreen);
	if (toplevel->xdg_toplevel->base->initialized) {
    policy_set_fullscreen(toplevel,
      toplevel->xdg_toplevel->requested.fullscreen,
      toplevel->xdg_toplevel->requested.fullscreen_output);
	}
}

static void server_new_xdg_toplevel(struct wl_listener *listener, void *data) {
	/* This event is raised when a client creates a new toplevel (application window). */
	struct nextspace_server *server = wl_container_of(listener, server, new_xdg_toplevel);
	struct wlr_xdg_toplevel *xdg_toplevel = data;

	/* Allocate a nextspace_toplevel for this surface */
	struct nextspace_toplevel *toplevel = calloc(1, sizeof(*toplevel));
	toplevel->id = ++server->next_window_id;
	toplevel->server = server;
  toplevel->frame = (struct ns_frame_extents){DECORATION_BORDER_WIDTH, DECORATION_TITLE_HEIGHT,
    DECORATION_BORDER_WIDTH, DECORATION_RESIZE_HEIGHT};
	toplevel->desktop = server->desktop;
	toplevel->xdg_toplevel = xdg_toplevel;
	toplevel->scene_tree = wlr_scene_tree_create(policy_layer(server, 0));
  toplevel->content_tree = wlr_scene_xdg_surface_create(toplevel->scene_tree, xdg_toplevel->base);
	toplevel->scene_tree->node.data = toplevel;
  toplevel->content_tree->node.data = toplevel;
	xdg_toplevel->base->data = toplevel->content_tree;

	/* Listen to the various events it can emit */
	toplevel->map.notify = xdg_toplevel_map;
	wl_signal_add(&xdg_toplevel->base->surface->events.map, &toplevel->map);
	toplevel->unmap.notify = xdg_toplevel_unmap;
	wl_signal_add(&xdg_toplevel->base->surface->events.unmap, &toplevel->unmap);
	toplevel->commit.notify = xdg_toplevel_commit;
	wl_signal_add(&xdg_toplevel->base->surface->events.commit, &toplevel->commit);

	toplevel->destroy.notify = xdg_toplevel_destroy;
	wl_signal_add(&xdg_toplevel->events.destroy, &toplevel->destroy);
  toplevel->set_title.notify = shell_metadata_changed;
  wl_signal_add(&xdg_toplevel->events.set_title, &toplevel->set_title);
  toplevel->set_app_id.notify = shell_app_id_changed;
  wl_signal_add(&xdg_toplevel->events.set_app_id, &toplevel->set_app_id);
  toplevel->request_minimize.notify = policy_request_minimize;
  wl_signal_add(&xdg_toplevel->events.request_minimize, &toplevel->request_minimize);

	/* cotd */
	toplevel->request_move.notify = xdg_toplevel_request_move;
	wl_signal_add(&xdg_toplevel->events.request_move, &toplevel->request_move);
	toplevel->request_resize.notify = xdg_toplevel_request_resize;
	wl_signal_add(&xdg_toplevel->events.request_resize, &toplevel->request_resize);
	toplevel->request_maximize.notify = xdg_toplevel_request_maximize;
	wl_signal_add(&xdg_toplevel->events.request_maximize, &toplevel->request_maximize);
	toplevel->request_fullscreen.notify = xdg_toplevel_request_fullscreen;
	wl_signal_add(&xdg_toplevel->events.request_fullscreen, &toplevel->request_fullscreen);
}

static void xdg_popup_commit(struct wl_listener *listener, void *data) {
	/* Called when a new surface state is committed. */
	struct nextspace_popup *popup = wl_container_of(listener, popup, commit);
  policy_update_popups(popup->server);

	if (popup->xdg_popup->base->initial_commit) {
		/* When an xdg_surface performs an initial commit, the compositor must
		 * reply with a configure so the client can map the surface.
		 * nextspace sends an empty configure. A more sophisticated compositor
		 * might change an xdg_popup's geometry to ensure it's not positioned
		 * off-screen, for example. */
		struct wlr_xdg_surface *root = popup->xdg_popup->base;
		while (root && root->role == WLR_XDG_SURFACE_ROLE_POPUP)
			root = wlr_xdg_surface_try_from_wlr_surface(root->popup->parent);
		if (root && root->data) {
			struct wlr_scene_tree *tree = root->data;
			int root_x, root_y;
      wlr_scene_node_coords(&tree->node, &root_x, &root_y);
			struct wlr_box geometry;
			wlr_xdg_surface_get_geometry(root, &geometry);
			struct wlr_output *output = wlr_output_layout_output_at(popup->server->output_layout,
				root_x + geometry.width / 2, root_y + geometry.height / 2);
			if (output) {
				struct wlr_box box;
				wlr_output_layout_get_box(popup->server->output_layout, output, &box);
				box.x -= root_x; box.y -= root_y;
				wlr_xdg_popup_unconstrain_from_box(popup->xdg_popup, &box);
			}
		}
		wlr_xdg_surface_schedule_configure(popup->xdg_popup->base);
	}
}

static void xdg_popup_destroy(struct wl_listener *listener, void *data) {
	/* Called when the xdg_popup is destroyed. */
	struct nextspace_popup *popup = wl_container_of(listener, popup, destroy);

	wl_list_remove(&popup->commit.link);
	wl_list_remove(&popup->destroy.link);
	wl_list_remove(&popup->link);
  if (popup->holder) wlr_scene_node_destroy(&popup->holder->node);

	free(popup);
}

static void server_new_xdg_popup(struct wl_listener *listener, void *data) {
	/* This event is raised when a client creates a new popup. */
	struct wlr_xdg_popup *xdg_popup = data;
	struct wlr_xdg_surface *parent = xdg_popup->parent ?
		wlr_xdg_surface_try_from_wlr_surface(xdg_popup->parent) : NULL;
	if (!parent || !parent->data) {
		wlr_xdg_popup_destroy(xdg_popup);
		return;
	}

	struct nextspace_popup *popup = calloc(1, sizeof(*popup));
	popup->xdg_popup = xdg_popup;
	popup->server = wl_container_of(listener, popup->server, new_xdg_popup);
	wl_list_insert(popup->server->popups.prev, &popup->link);

	/* We must add xdg popups to the scene graph so they get rendered. The
	 * wlroots scene graph provides a helper for this, but to use it we must
	 * provide the proper parent scene node of the xdg popup. To enable this,
	 * we always set the user data field of xdg_surfaces to the corresponding
	 * scene node. */
	popup->holder = wlr_scene_tree_create(policy_layer(popup->server, 101));
	xdg_popup->base->data = wlr_scene_xdg_surface_create(popup->holder, xdg_popup->base);
  policy_update_popups(popup->server);

	popup->commit.notify = xdg_popup_commit;
	wl_signal_add(&xdg_popup->base->surface->events.commit, &popup->commit);

	popup->destroy.notify = xdg_popup_destroy;
	wl_signal_add(&xdg_popup->events.destroy, &popup->destroy);
}

#include "control.h"
#include "session-lock.h"

static int terminate_signal(int signal_number, void *data) {
	wl_display_terminate(data);
	return 0;
}

int main(int argc, char *argv[]) {
	wlr_log_init(WLR_INFO, NULL);
	int control_fd = -1, shell_broker_fd = -1, c;
	unsetenv("DISPLAY"); unsetenv("XAUTHORITY");
	bool fractional = true, viewporter = true, application = true;
	unsigned compositor_version = 5;
	while ((c = getopt(argc, argv, "c:S:hdFVA1")) != -1) {
    if (c == 'd') { wlr_log_init(WLR_DEBUG, NULL); continue; }
		if (c == '1') { compositor_version = 1; continue; }
		if (c == 'A') { application = false; continue; }
		if (c == 'F') { fractional = false; continue; }
		if (c == 'V') { viewporter = false; continue; }
		if (c != 'c' && c != 'S') {
			fprintf(stderr, "Usage: %s [-c test-control-fd] [-S shell-broker-fd] [-d] [-F] [-V] [-A] [-1]\n", argv[0]);
			return c == 'h' ? 0 : 1;
		}
		char *end;
		long fd = strtol(optarg, &end, 10);
		if (*end || fd < 3 || fd > INT32_MAX) return 1;
		if (c == 'S') shell_broker_fd = (int)fd;
    else control_fd = (int)fd;
	}
	if (optind != argc) return 1;
	if (control_fd >= 0) fcntl(control_fd, F_SETFD, FD_CLOEXEC);
  if (shell_broker_fd >= 0) fcntl(shell_broker_fd, F_SETFD, FD_CLOEXEC);
  if (control_fd >= 0 && control_fd == shell_broker_fd) return 1;
	struct nextspace_server server = {.control_fd = control_fd, .shell_broker_fd = -1,
    .desktop_count = 4, .double_click_time = 350};
  server.lock_pixel_check = control_fd >= 0 && getenv("NEXTSPACE_LOCK_PIXEL_CHECK") &&
    strcmp(getenv("NEXTSPACE_LOCK_PIXEL_CHECK"), "1") == 0;
	/* The Wayland display is managed by libwayland. It handles accepting
	 * clients from the Unix socket, manging Wayland globals, and so on. */
	server.wl_display = wl_display_create();
	struct wl_event_loop *loop = wl_display_get_event_loop(server.wl_display);
	struct wl_event_source *sigterm = wl_event_loop_add_signal(loop, SIGTERM, terminate_signal, server.wl_display);
	struct wl_event_source *sigint = wl_event_loop_add_signal(loop, SIGINT, terminate_signal, server.wl_display);
  /* Pango may start a font worker. It must inherit the blocked signals used
   * by the event loop, or process-directed termination can kill that thread. */
  server.title_font = title_font_create("Helvetica:bold:pixelsize=12", false);
  if (!server.title_font) return 1;
	/* The backend is a wlroots feature which abstracts the underlying input and
	 * output hardware. The autocreate option will choose the most suitable
	 * backend based on the current environment, such as opening an X11 window
	 * if an X11 server is running. */
	server.backend = wlr_backend_autocreate(wl_display_get_event_loop(server.wl_display), &server.session);
	if (server.backend == NULL) {
		wlr_log(WLR_ERROR, "failed to create wlr_backend");
		return 1;
	}

	/* Autocreates a renderer, either Pixman, GLES2 or Vulkan for us. The user
	 * can also specify a renderer using the WLR_RENDERER env var.
	 * The renderer is responsible for defining the various pixel formats it
	 * supports for shared memory, this configures that for clients. */
	server.renderer = wlr_renderer_autocreate(server.backend);
	if (server.renderer == NULL) {
		wlr_log(WLR_ERROR, "failed to create wlr_renderer");
		return 1;
	}

	wlr_renderer_init_wl_display(server.renderer, server.wl_display);
  server.screencopy_manager = wlr_screencopy_manager_v1_create(server.wl_display);
  if (!server.screencopy_manager) return 1;

	/* Autocreates an allocator for us.
	 * The allocator is the bridge between the renderer and the backend. It
	 * handles the buffer creation, allowing wlroots to render onto the
	 * screen */
	server.allocator = wlr_allocator_autocreate(server.backend,
		server.renderer);
	if (server.allocator == NULL) {
		wlr_log(WLR_ERROR, "failed to create wlr_allocator");
		return 1;
	}

	/* This creates some hands-off wlroots interfaces. The compositor is
	 * necessary for clients to allocate surfaces, the subcompositor allows to
	 * assign the role of subsurfaces to surfaces and the data device manager
	 * handles the clipboard. Each of these wlroots interfaces has room for you
	 * to dig your fingers in and play with their behavior if you want. Note that
	 * the clients cannot set the selection directly without compositor approval,
	 * see the handling of the request_set_selection event below.*/
	server.compositor = wlr_compositor_create(server.wl_display, compositor_version, server.renderer);
	wlr_subcompositor_create(server.wl_display);
	wlr_data_device_manager_create(server.wl_display);
  wlr_primary_selection_v1_device_manager_create(server.wl_display);
	if (viewporter) wlr_viewporter_create(server.wl_display);
	if (fractional) wlr_fractional_scale_manager_v1_create(server.wl_display, 1);

	/* Creates an output layout, which a wlroots utility for working with an
	 * arrangement of screens in a physical layout. */
	server.output_layout = wlr_output_layout_create(server.wl_display);
	server.xdg_output_manager = wlr_xdg_output_manager_v1_create(server.wl_display, server.output_layout);

	/* Configure a listener to be notified when new outputs are available on the
	 * backend. */
	wl_list_init(&server.outputs);
  wl_list_init(&server.application_resources);
	server.new_output.notify = server_new_output;
	wl_signal_add(&server.backend->events.new_output, &server.new_output);

	/* Create a scene graph. This is a wlroots abstraction that handles all
	 * rendering and damage tracking. All the compositor author needs to do
	 * is add things that should be rendered to the scene graph at the proper
	 * positions and then call wlr_scene_output_commit() to render a frame if
	 * necessary.
	 */
	server.scene = wlr_scene_create();
  server.desktop_tree = wlr_scene_tree_create(&server.scene->tree);
  server.lock_tree = wlr_scene_tree_create(&server.scene->tree);
  if (!server.desktop_tree || !server.lock_tree) return 1;
  wlr_scene_node_set_enabled(&server.lock_tree->node, false);
  const float desktop_color[4] = {83.0f / 255, 83.0f / 255, 116.0f / 255, 1};
  server.background = wlr_scene_rect_create(server.desktop_tree, 1, 1, desktop_color);
  wl_list_init(&server.layers);
	server.scene_layout = wlr_scene_attach_output_layout(server.scene, server.output_layout);

	/* Set up xdg-shell version 3. The xdg-shell is a Wayland protocol which is
	 * used for application windows. For more detail on shells, refer to
	 * https://drewdevault.com/2018/07/29/Wayland-shells.html.
	 */
	wl_list_init(&server.toplevels);
	wl_list_init(&server.popups);
  if (application) create_application_global(&server);
  server.layout_change.notify = application_layout_changed;
  wl_signal_add(&server.output_layout->events.change, &server.layout_change);
	server.xdg_shell = wlr_xdg_shell_create(server.wl_display, 3);
  struct wlr_xdg_activation_v1 *activation = wlr_xdg_activation_v1_create(server.wl_display);
  activation->token_timeout_msec = 5000;
  server.request_activate.notify = request_activate;
  wl_signal_add(&activation->events.request_activate, &server.request_activate);
	server.new_xdg_toplevel.notify = server_new_xdg_toplevel;
	wl_signal_add(&server.xdg_shell->events.new_toplevel, &server.new_xdg_toplevel);
	server.new_xdg_popup.notify = server_new_xdg_popup;
	wl_signal_add(&server.xdg_shell->events.new_popup, &server.new_xdg_popup);
  struct wlr_xdg_decoration_manager_v1 *decorations = wlr_xdg_decoration_manager_v1_create(server.wl_display);
  server.new_decoration.notify = decoration_new;
  wl_signal_add(&decorations->events.new_toplevel_decoration, &server.new_decoration);

	/*
	 * Creates a cursor, which is a wlroots utility for tracking the cursor
	 * image shown on screen.
	 */
	server.cursor = wlr_cursor_create();
	wlr_cursor_attach_output_layout(server.cursor, server.output_layout);

	/* Creates an xcursor manager, another wlroots utility which loads up
	 * Xcursor themes to source cursor images from and makes sure that cursor
	 * images are available at all scale factors on the screen (necessary for
	 * HiDPI support). */
	server.cursor_mgr = wlr_xcursor_manager_create(getenv("XCURSOR_THEME"), 24);

	/*
	 * wlr_cursor *only* displays an image on screen. It does not move around
	 * when the pointer moves. However, we can attach input devices to it, and
	 * it will generate aggregate events for all of them. In these events, we
	 * can choose how we want to process them, forwarding them to clients and
	 * moving the cursor around. More detail on this process is described in
	 * https://drewdevault.com/2018/07/17/Input-handling-in-wlroots.html.
	 *
	 * And more comments are sprinkled throughout the notify functions above.
	 */
	server.cursor_mode = NEXTSPACE_CURSOR_PASSTHROUGH;
	server.cursor_motion.notify = server_cursor_motion;
	wl_signal_add(&server.cursor->events.motion, &server.cursor_motion);
	server.cursor_motion_absolute.notify = server_cursor_motion_absolute;
	wl_signal_add(&server.cursor->events.motion_absolute,
			&server.cursor_motion_absolute);
	server.cursor_button.notify = server_cursor_button;
	wl_signal_add(&server.cursor->events.button, &server.cursor_button);
	server.cursor_axis.notify = server_cursor_axis;
	wl_signal_add(&server.cursor->events.axis, &server.cursor_axis);
	server.cursor_frame.notify = server_cursor_frame;
	wl_signal_add(&server.cursor->events.frame, &server.cursor_frame);

	/*
	 * Configures a seat, which is a single "seat" at which a user sits and
	 * operates the computer. This conceptually includes up to one keyboard,
	 * pointer, touch, and drawing tablet device. We also rig up a listener to
	 * let us know when new input devices are available on the backend.
	 */
	wl_list_init(&server.keyboards);
	server.new_input.notify = server_new_input;
	wl_signal_add(&server.backend->events.new_input, &server.new_input);
	server.seat = wlr_seat_create(server.wl_display, "seat0");
  if (!input_settings_init(&server) || !shell_init(&server, shell_broker_fd)) return 1;
  if (!text_input_init(&server)) return 1;
  if (!session_lock_init(&server)) return 1;
  wl_display_set_global_filter(server.wl_display, filter_global, &server);
  clipboard_init(&server);
	if (control_fd >= 0) {
    /* Only the inherited test capability can inject input. No public global. */
    static const struct wlr_keyboard_impl impl = {.name = "nextspace-control"};
    wlr_keyboard_init(&server.control_keyboard, &impl, "nextspace-control");
    server_new_keyboard(&server, &server.control_keyboard.base);
    wlr_seat_set_capabilities(server.seat, WL_SEAT_CAPABILITY_POINTER | WL_SEAT_CAPABILITY_KEYBOARD);
  }
	server.request_cursor.notify = seat_request_cursor;
	wl_signal_add(&server.seat->events.request_set_cursor,
			&server.request_cursor);
  server.request_start_drag.notify = seat_request_start_drag;
  wl_signal_add(&server.seat->events.request_start_drag, &server.request_start_drag);
	server.request_set_selection.notify = seat_request_set_selection;
	wl_signal_add(&server.seat->events.request_set_selection,
			&server.request_set_selection);
  server.request_set_primary_selection.notify = seat_request_set_primary_selection;
  wl_signal_add(&server.seat->events.request_set_primary_selection, &server.request_set_primary_selection);

	/* Add a Unix socket to the Wayland display. */
	const char *socket = wl_display_add_socket_auto(server.wl_display);
	if (!socket) {
		wlr_backend_destroy(server.backend);
		return 1;
	}

  server.output_timer = wl_event_loop_add_timer(wl_display_get_event_loop(server.wl_display),
    output_timeout, &server);
	/* Start the backend. This will enumerate outputs and inputs, become the DRM
	 * master, etc */
	if (!wlr_backend_start(server.backend)) {
		wlr_backend_destroy(server.backend);
		wl_display_destroy(server.wl_display);
		return 1;
	}

	server.rollback_timer = wl_event_loop_add_timer(
		wl_display_get_event_loop(server.wl_display), rollback_scale, &server);
	if (control_fd >= 0) {
		int type; socklen_t size = sizeof(type);
		if (getsockopt(control_fd, SOL_SOCKET, SO_TYPE, &type, &size) || type != SOCK_SEQPACKET)
			return 1;
		fcntl(control_fd, F_SETFD, FD_CLOEXEC);
		fcntl(control_fd, F_SETFL, fcntl(control_fd, F_GETFL) | O_NONBLOCK);
		server.control_source = wl_event_loop_add_fd(
			wl_display_get_event_loop(server.wl_display), control_fd,
			WL_EVENT_READABLE, control_ready, &server);
	}
	printf("WAYLAND_DISPLAY=%s\n", socket);
	fflush(stdout);
	/* Run the Wayland event loop. This does not return until you exit the
	 * compositor. Starting the backend rigged up all of the necessary event
	 * loop configuration to listen to libinput events, DRM events, generate
	 * frame events at the refresh rate, and so on. */
	wlr_log(WLR_INFO, "Running Wayland compositor on WAYLAND_DISPLAY=%s",
			socket);
	wl_display_run(server.wl_display);

	/* Once wl_display_run returns, we destroy all clients then shut down the
	 * server. */
	if (server.control_source) wl_event_source_remove(server.control_source);
	if (server.control_fd >= 0) close(server.control_fd);
	wl_event_source_remove(server.rollback_timer);
  clipboard_finish(&server);
  shell_finish(&server);
  if (server.output_idle) wl_event_source_remove(server.output_idle);
  server.output_idle = NULL;
  wl_event_source_remove(server.output_timer);
  server.output_timer = NULL;

  color_pick_finish(&server, NEXTSPACE_WINDOW_V1_COLOR_PICK_PHASE_CANCELLED, 0);
	wl_display_destroy_clients(server.wl_display);
  /* Client unmap callbacks still hit-test the locked scene during shutdown. */
  session_lock_finish(&server);
  server.background = NULL; /* Backend output teardown can still notify layout recovery. */
	wlr_scene_node_destroy(&server.scene->tree.node);
  policy_finish(&server);
	wlr_xcursor_manager_destroy(server.cursor_mgr);
	wlr_cursor_destroy(server.cursor);
	if (control_fd >= 0) wlr_keyboard_finish(&server.control_keyboard);
  if (server.color_sample_buffer) wlr_buffer_drop(server.color_sample_buffer);
	wlr_allocator_destroy(server.allocator);
	wlr_renderer_destroy(server.renderer);
	wl_list_remove(&server.layout_change.link);
	wlr_backend_destroy(server.backend);
  input_settings_finish(&server);
	wl_event_source_remove(sigterm);
	wl_event_source_remove(sigint);
	wl_display_destroy(server.wl_display);
  title_font_destroy(server.title_font);
	return 0;
}
