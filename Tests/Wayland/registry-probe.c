/* Check that ordinary clients cannot see privileged compositor globals. MIT license. */
#define _GNU_SOURCE
#include <wayland-client.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include "nextspace-application-v1-client-protocol.h"
#include "xdg-shell-client-protocol.h"
#include "xdg-activation-v1-client-protocol.h"
#include "primary-selection-unstable-v1-client-protocol.h"
#include "text-input-unstable-v3-client-protocol.h"
#include "input-method-unstable-v2-client-protocol.h"
#include "virtual-keyboard-unstable-v1-client-protocol.h"
#include <sys/mman.h>
#include <unistd.h>
#include <stdlib.h>
#include <fcntl.h>
#include <poll.h>

struct globals {
  bool color_pick_mode;
  bool text_mode, method_mode, method_daemon;
  uint32_t method_global;
  struct zwp_text_input_manager_v3 *text_manager;
  struct zwp_input_method_manager_v2 *method_manager;
  struct zwp_virtual_keyboard_manager_v1 *virtual_manager;
  bool forbidden;
  bool clipboard_mode, primary_mode, invalid_primary;
  struct wl_display *display;
  struct zwp_primary_selection_device_manager_v1 *primary_manager;
  bool focus_mode;
  bool policy_mode;
  bool activation_mode;
  struct xdg_activation_v1 *activation;
  uint32_t activation_serial;
  struct wl_surface *activation_source;
  char *activation_token;
  struct wl_seat *seat;
  struct wl_data_device_manager *data_manager;
  struct wl_compositor *compositor;
  struct nextspace_application_v1 *application;
  struct wl_shm *shm;
  struct xdg_wm_base *shell;
};

static void shm_format(void *data, struct wl_shm *shm, uint32_t format) {}
static const struct wl_shm_listener shm_listener = {.format = shm_format};
static void ping(void *data, struct xdg_wm_base *shell, uint32_t serial) { xdg_wm_base_pong(shell, serial); }
static const struct xdg_wm_base_listener shell_listener = {.ping = ping};

static void global(void *data, struct wl_registry *registry, uint32_t name,
    const char *interface, uint32_t version)
{
  struct globals *globals = data;
  if (strcmp(interface, "zwp_input_method_manager_v2") == 0) {
    globals->method_global = name;
    if (globals->method_mode)
      globals->method_manager = wl_registry_bind(registry, name, &zwp_input_method_manager_v2_interface, 1);
  }
  if (globals->method_mode && strcmp(interface, "zwp_virtual_keyboard_manager_v1") == 0)
    globals->virtual_manager = wl_registry_bind(registry, name, &zwp_virtual_keyboard_manager_v1_interface, 1);
  if (globals->text_mode && strcmp(interface, "zwp_text_input_manager_v3") == 0)
    globals->text_manager = wl_registry_bind(registry, name, &zwp_text_input_manager_v3_interface, 1);
  if (strcmp(interface, "xwayland_shell_v1") == 0 || strcmp(interface, "nextspace_shell_v1") == 0 ||
      strcmp(interface, "zwp_input_method_manager_v2") == 0 ||
      strcmp(interface, "zwp_virtual_keyboard_manager_v1") == 0 ||
      strcmp(interface, "zwlr_screencopy_manager_v1") == 0 ||
      strcmp(interface, "ext_session_lock_manager_v1") == 0)
    globals->forbidden = true;
  if ((globals->color_pick_mode || globals->clipboard_mode || globals->primary_mode || globals->activation_mode || globals->text_mode || globals->method_mode) && strcmp(interface, "wl_seat") == 0)
    globals->seat = wl_registry_bind(registry, name, &wl_seat_interface, 1);
  if (strcmp(interface, "zwp_primary_selection_device_manager_v1") == 0)
    globals->primary_manager = wl_registry_bind(registry, name, &zwp_primary_selection_device_manager_v1_interface, 1);
  if (strcmp(interface, "wl_data_device_manager") == 0)
    globals->data_manager = wl_registry_bind(registry, name, &wl_data_device_manager_interface, 1);
  if (strcmp(interface, "wl_compositor") == 0)
    globals->compositor = wl_registry_bind(registry, name, &wl_compositor_interface, 1);
  if (strcmp(interface, "nextspace_application_v1") == 0)
    globals->application = wl_registry_bind(registry, name, &nextspace_application_v1_interface,
      globals->color_pick_mode && version >= 8 ? 8 : globals->policy_mode && version >= 3 ? 3 : globals->focus_mode && version >= 2 ? 2 : 1);
  if (strcmp(interface, "wl_shm") == 0) {
    globals->shm = wl_registry_bind(registry, name, &wl_shm_interface, 1);
    wl_shm_add_listener(globals->shm, &shm_listener, NULL);
  }
  if (strcmp(interface, "xdg_activation_v1") == 0)
    globals->activation = wl_registry_bind(registry, name, &xdg_activation_v1_interface, 1);
  if (strcmp(interface, "xdg_wm_base") == 0) {
    globals->shell = wl_registry_bind(registry, name, &xdg_wm_base_interface, 1);
    xdg_wm_base_add_listener(globals->shell, &shell_listener, NULL);
  }
}
static void removed(void *data, struct wl_registry *registry, uint32_t name) {}
static const struct wl_registry_listener listener = {.global = global, .global_remove = removed};

struct test_window {
  struct wl_surface *surface;
  struct wl_buffer *buffer;
  struct xdg_surface *xdg;
  struct xdg_toplevel *top;
  void *pixels;
  int x, y;
  bool positioned, activated, closed;
};
static void configure(void *data, struct xdg_surface *surface, uint32_t serial)
{
  struct test_window *window = data;
  xdg_surface_ack_configure(surface, serial);
  wl_surface_attach(window->surface, window->buffer, 0, 0);
  wl_surface_damage(window->surface, 0, 0, 64, 64);
  wl_surface_commit(window->surface);
}
static const struct xdg_surface_listener surface_listener = {.configure = configure};
static void toplevel_configure(void *data, struct xdg_toplevel *top, int32_t width, int32_t height, struct wl_array *states)
{
  struct test_window *window = data;
  window->activated = false;
  uint32_t *state;
  wl_array_for_each(state, states)
    if (*state == XDG_TOPLEVEL_STATE_ACTIVATED) window->activated = true;
}
static void toplevel_close(void *data, struct xdg_toplevel *top)
{ ((struct test_window *)data)->closed = true; }
static const struct xdg_toplevel_listener top_listener = {.configure = toplevel_configure, .close = toplevel_close};
static void position(void *data, struct nextspace_window_v1 *object, int32_t x, int32_t y)
{
  struct test_window *window = data;
  window->x = x; window->y = y; window->positioned = true;
}
static void preferred(void *data, struct nextspace_window_v1 *object, const char *name) {}
static void closed(void *data, struct nextspace_window_v1 *object) {}
static void minimized(void *data, struct nextspace_window_v1 *object, uint32_t minimized) {}
static const struct nextspace_window_v1_listener window_listener = {
  .position = position, .preferred_output = preferred, .closed = closed, .minimized = minimized
};
static void release(void *data, struct wl_buffer *buffer) {}
static const struct wl_buffer_listener buffer_listener = {.release = release};

static bool create_surface(struct globals *globals, struct test_window *window)
{
  if (!globals->compositor || !globals->shm || !globals->shell) return false;
  int fd = memfd_create("protocol-probe", MFD_CLOEXEC);
  if (fd < 0 || ftruncate(fd, 64 * 64 * 4)) return false;
  window->pixels = mmap(NULL, 64 * 64 * 4, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
  if (window->pixels == MAP_FAILED) { close(fd); return false; }
  memset(window->pixels, 255, 64 * 64 * 4);
  struct wl_shm_pool *pool = wl_shm_create_pool(globals->shm, fd, 64 * 64 * 4);
  window->surface = wl_compositor_create_surface(globals->compositor);
  window->buffer = wl_shm_pool_create_buffer(pool, 0, 64, 64, 64 * 4, WL_SHM_FORMAT_ARGB8888);
  wl_buffer_add_listener(window->buffer, &buffer_listener, NULL);
  wl_shm_pool_destroy(pool); close(fd);
  return true;
}

static bool create_window(struct globals *globals, struct test_window *window, const char *title)
{
  if (!create_surface(globals, window)) return false;
  window->xdg = xdg_wm_base_get_xdg_surface(globals->shell, window->surface);
  window->top = xdg_surface_get_toplevel(window->xdg);
  xdg_toplevel_add_listener(window->top, &top_listener, window);
  xdg_toplevel_set_title(window->top, title);
  xdg_surface_add_listener(window->xdg, &surface_listener, window);
  return true;
}

static void destroy_window(struct test_window *window)
{
  xdg_toplevel_destroy(window->top); xdg_surface_destroy(window->xdg);
  wl_surface_destroy(window->surface); wl_buffer_destroy(window->buffer);
  munmap(window->pixels, 64 * 64 * 4);
}

static int test_placement(struct wl_display *display, struct globals *globals)
{
  if (!globals->application) return 1;
  alarm(10);
  struct test_window window = {0};
  if (!create_window(globals, &window, "PlacementProbe")) return 1;
  struct nextspace_window_v1 *object = nextspace_application_v1_get_window(globals->application, window.surface);
  nextspace_window_v1_add_listener(object, &window_listener, &window);
  nextspace_window_v1_set_position(object, 32, 48);
  wl_surface_commit(window.surface);
  while (!window.positioned) if (wl_display_dispatch(display) < 0) return 1;
  if (window.x != 32 || window.y != 48) return 1;
  window.positioned = false;
  nextspace_window_v1_set_position(object, INT32_MAX, INT32_MIN);
  while (!window.positioned) if (wl_display_dispatch(display) < 0) return 1;
  bool valid = window.x >= 0 && window.x < 3200 && window.y >= 0 && window.y < 1200;
  nextspace_window_v1_destroy(object);
  destroy_window(&window);
  wl_display_roundtrip(display);
  alarm(0);
  if (valid) puts("Owned placement, authoritative position and offscreen recovery: PASS");
  return valid ? 0 : 1;
}

static int test_focus(struct wl_display *display, struct globals *globals)
{
  if (!globals->application || nextspace_application_v1_get_version(globals->application) < 2) return 1;
  alarm(10);
  struct test_window document = {0}, menu = {0};
  if (!create_window(globals, &document, "FocusDocument")) return 1;
  wl_surface_commit(document.surface);
  while (!document.activated) if (wl_display_dispatch(display) < 0) return 1;
  if (!create_window(globals, &menu, "FocusMenu")) return 1;
  struct nextspace_window_v1 *object = nextspace_application_v1_get_window(globals->application, menu.surface);
  nextspace_window_v1_add_listener(object, &window_listener, &menu);
  nextspace_window_v1_set_accepts_focus(object, 0);
  wl_surface_commit(menu.surface);
  while (!menu.positioned) if (wl_display_dispatch(display) < 0) return 1;
  if (wl_display_roundtrip(display) < 0) return 1;
  bool valid = document.activated && !menu.activated;
  nextspace_window_v1_destroy(object);
  destroy_window(&menu);
  /* A Workspace icon can map after a different application's document has
     focus. Mapping that non-focusable window must not reactivate Workspace. */
  struct wl_display *other_display = wl_display_connect(NULL);
  if (!other_display) return 1;
  struct globals other_globals = {.display = other_display};
  struct wl_registry *other_registry = wl_display_get_registry(other_display);
  wl_registry_add_listener(other_registry, &listener, &other_globals);
  if (wl_display_roundtrip(other_display) < 0) return 1;
  struct test_window other = {0};
  if (!create_window(&other_globals, &other, "OtherDocument")) return 1;
  wl_surface_commit(other.surface);
  while (!other.activated) if (wl_display_dispatch(other_display) < 0) return 1;
  if (wl_display_roundtrip(display) < 0) return 1;
  menu = (struct test_window){0};
  if (!create_window(globals, &menu, "BackgroundIcon")) return 1;
  object = nextspace_application_v1_get_window(globals->application, menu.surface);
  nextspace_window_v1_add_listener(object, &window_listener, &menu);
  nextspace_window_v1_set_accepts_focus(object, 0);
  wl_surface_commit(menu.surface);
  while (!menu.positioned) if (wl_display_dispatch(display) < 0) return 1;
  if (wl_display_roundtrip(display) < 0 || wl_display_roundtrip(other_display) < 0) return 1;
  valid = valid && other.activated && !document.activated && !menu.activated;
  nextspace_window_v1_destroy(object);
  destroy_window(&menu); destroy_window(&document);
  destroy_window(&other);
  wl_display_roundtrip(other_display);
  wl_registry_destroy(other_registry);
  wl_display_disconnect(other_display);
  wl_display_roundtrip(display);
  alarm(0);
  if (valid) puts("Auxiliary windows preserve own and foreign document keyboard focus: PASS");
  return valid ? 0 : 1;
}

static void activation_keymap(void *data, struct wl_keyboard *keyboard, uint32_t format, int fd, uint32_t size)
{ close(fd); }
static void activation_enter(void *data, struct wl_keyboard *keyboard, uint32_t serial,
    struct wl_surface *surface, struct wl_array *keys)
{
  struct globals *globals = data;
  globals->activation_serial = serial; globals->activation_source = surface;
}
static void activation_leave(void *data, struct wl_keyboard *keyboard, uint32_t serial, struct wl_surface *surface)
{ ((struct globals *)data)->activation_source = NULL; }
static void activation_key(void *data, struct wl_keyboard *keyboard, uint32_t serial,
    uint32_t time, uint32_t key, uint32_t state) {}
static void activation_modifiers(void *data, struct wl_keyboard *keyboard, uint32_t serial,
    uint32_t depressed, uint32_t latched, uint32_t locked, uint32_t group) {}
static const struct wl_keyboard_listener activation_keyboard = {
  .keymap = activation_keymap, .enter = activation_enter, .leave = activation_leave,
  .key = activation_key, .modifiers = activation_modifiers
};
static void activation_done(void *data, struct xdg_activation_token_v1 *token, const char *name)
{ ((struct globals *)data)->activation_token = strdup(name); }
static const struct xdg_activation_token_v1_listener activation_listener = {.done = activation_done};

static int test_activation(struct wl_display *display, struct globals *globals)
{
  if (!globals->activation || !globals->seat) return 1;
  alarm(15);
  struct wl_keyboard *keyboard = wl_seat_get_keyboard(globals->seat);
  wl_keyboard_add_listener(keyboard, &activation_keyboard, globals);
  struct test_window first = {0}, second = {0};
  if (!create_window(globals, &first, "ActivationFirst")) return 1;
  wl_surface_commit(first.surface);
  while (!first.activated) if (wl_display_dispatch(display) < 0) return 1;
  if (!create_window(globals, &second, "ActivationSecond")) return 1;
  wl_surface_commit(second.surface);
  while (!second.activated || globals->activation_source != second.surface)
    if (wl_display_dispatch(display) < 0) return 1;
  for (int trial = 0; trial < 4; trial++) {
    struct xdg_activation_token_v1 *token = xdg_activation_v1_get_activation_token(globals->activation);
    xdg_activation_token_v1_add_listener(token, &activation_listener, globals);
    if (trial) {
      xdg_activation_token_v1_set_serial(token, trial == 1 ? UINT32_MAX : globals->activation_serial, globals->seat);
      xdg_activation_token_v1_set_surface(token, trial == 2 ? first.surface : second.surface);
    }
    xdg_activation_token_v1_commit(token);
    while (!globals->activation_token) if (wl_display_dispatch(display) < 0) return 1;
    xdg_activation_v1_activate(globals->activation, globals->activation_token, first.surface);
    for (int step = 0; step < 3; step++) if (wl_display_roundtrip(display) < 0) return 1;
    if (first.activated != (trial == 3) || second.activated != (trial != 3)) return 1;
    /* Both unknown and consumed tokens are ignored. */
    xdg_activation_v1_activate(globals->activation, trial == 3 ? globals->activation_token : "unknown", second.surface);
    for (int step = 0; step < 3; step++) if (wl_display_roundtrip(display) < 0) return 1;
    if (first.activated != (trial == 3)) return 1;
    xdg_activation_token_v1_destroy(token); free(globals->activation_token); globals->activation_token = NULL;
  }
  destroy_window(&first); destroy_window(&second); wl_keyboard_destroy(keyboard);
  wl_display_roundtrip(display); alarm(0);
  puts("Activation validates seat, serial, source focus and single-use tokens: PASS");
  return 0;
}

struct clipboard {
  struct globals *globals;
  void *device, *source, *offer;
  struct wl_keyboard *keyboard;
  bool write, has_text, stall;
  int read_fd;
  char *payload;
  size_t length;
  const char *receive_mime;
};
static void mime(void *data, struct wl_data_offer *offer, const char *type) {}
static const struct wl_data_offer_listener clipboard_offer_listener = {.offer = mime};
static void new_offer(void *data, struct wl_data_device *device, struct wl_data_offer *offer)
{ wl_data_offer_add_listener(offer, &clipboard_offer_listener, data); }
static void receive_selection(void *data, void *offer)
{
  struct clipboard *clipboard = data;
  if (clipboard->write || !offer || clipboard->read_fd >= 0) return;
  int fds[2];
  if (pipe(fds)) return;
  clipboard->read_fd = fds[0];
  fcntl(fds[0], F_SETFL, O_NONBLOCK);
  clipboard->offer = offer;
  if (clipboard->globals->primary_mode) zwp_primary_selection_offer_v1_receive(offer, clipboard->receive_mime, fds[1]);
  else wl_data_offer_receive(offer, clipboard->receive_mime, fds[1]);
  close(fds[1]);
}
static void clipboard_selection(void *data, struct wl_data_device *device, struct wl_data_offer *offer)
{ receive_selection(data, offer); }
static void primary_mime(void *data, struct zwp_primary_selection_offer_v1 *offer, const char *type) {}
static const struct zwp_primary_selection_offer_v1_listener primary_offer_listener = {.offer = primary_mime};
static void primary_offer(void *data, struct zwp_primary_selection_device_v1 *device, struct zwp_primary_selection_offer_v1 *offer)
{ zwp_primary_selection_offer_v1_add_listener(offer, &primary_offer_listener, data); }
static void primary_selection(void *data, struct zwp_primary_selection_device_v1 *device, struct zwp_primary_selection_offer_v1 *offer)
{ receive_selection(data, offer); }
static const struct zwp_primary_selection_device_v1_listener primary_device_listener = {
  .data_offer = primary_offer, .selection = primary_selection
};
static void data_enter(void *data, struct wl_data_device *device, uint32_t serial,
  struct wl_surface *surface, wl_fixed_t x, wl_fixed_t y, struct wl_data_offer *offer) {}
static void data_leave(void *data, struct wl_data_device *device) {}
static void data_motion(void *data, struct wl_data_device *device, uint32_t time, wl_fixed_t x, wl_fixed_t y) {}
static void data_drop(void *data, struct wl_data_device *device) {}
static const struct wl_data_device_listener clipboard_device_listener = {
  .data_offer = new_offer, .enter = data_enter, .leave = data_leave,
  .motion = data_motion, .drop = data_drop, .selection = clipboard_selection
};
static void send_payload(void *data, struct wl_data_source *source, const char *type, int32_t fd)
{
  struct clipboard *clipboard = data;
  if (clipboard->stall) return; /* Deliberately hold the pipe open until process exit. */
  size_t sent = 0;
  while (sent < clipboard->length) {
    ssize_t count = write(fd, clipboard->payload + sent, clipboard->length - sent);
    if (count < 0 && errno == EINTR) continue;
    if (count <= 0) break;
    sent += count;
  }
  close(fd);
}
static void target(void *data, struct wl_data_source *source, const char *type) {}
static void cancelled(void *data, struct wl_data_source *source)
{
  struct clipboard *clipboard = data;
  if (clipboard->source == source) clipboard->source = NULL;
  wl_data_source_destroy(source);
}
static const struct wl_data_source_listener clipboard_source_listener = {
  .target = target, .send = send_payload, .cancelled = cancelled
};
static void primary_send(void *data, struct zwp_primary_selection_source_v1 *source, const char *type, int32_t fd)
{ send_payload(data, NULL, type, fd); }
static void primary_cancelled(void *data, struct zwp_primary_selection_source_v1 *source)
{
  struct clipboard *clipboard = data;
  if (clipboard->source == source) clipboard->source = NULL;
  zwp_primary_selection_source_v1_destroy(source);
}
static const struct zwp_primary_selection_source_v1_listener primary_source_listener = {
  .send = primary_send, .cancelled = primary_cancelled
};
static void set_selection(struct clipboard *clipboard, uint32_t serial)
{
  if (clipboard->globals->primary_mode)
    zwp_primary_selection_device_v1_set_selection(clipboard->device, clipboard->source, serial);
  else wl_data_device_set_selection(clipboard->device, clipboard->source, serial);
}
static void checked_selection(void *data, struct wl_callback *callback, uint32_t serial)
{
  puts("Invalid primary request processed"); fflush(stdout);
  wl_callback_destroy(callback);
}
static const struct wl_callback_listener checked_selection_listener = {.done = checked_selection};
static void keymap(void *data, struct wl_keyboard *keyboard, uint32_t format, int fd, uint32_t size) { close(fd); }
static void key_enter(void *data, struct wl_keyboard *keyboard, uint32_t serial, struct wl_surface *surface, struct wl_array *keys) {}
static void key_leave(void *data, struct wl_keyboard *keyboard, uint32_t serial, struct wl_surface *surface) {}
static void key(void *data, struct wl_keyboard *keyboard, uint32_t serial, uint32_t time, uint32_t key, uint32_t state)
{
  struct clipboard *clipboard = data;
  if (state == WL_KEYBOARD_KEY_STATE_PRESSED && clipboard->write && key == 1) {
    void *source = clipboard->source; clipboard->source = NULL;
    set_selection(clipboard, serial); clipboard->source = source;
    puts("Clipboard source cleared"); fflush(stdout);
    return;
  }
  if (state == WL_KEYBOARD_KEY_STATE_PRESSED && clipboard->write && !clipboard->source) {
    if (clipboard->globals->primary_mode) {
      clipboard->source = zwp_primary_selection_device_manager_v1_create_source(clipboard->globals->primary_manager);
      zwp_primary_selection_source_v1_add_listener(clipboard->source, &primary_source_listener, clipboard);
      zwp_primary_selection_source_v1_offer(clipboard->source, "text/plain;charset=utf-8");
    } else {
      clipboard->source = wl_data_device_manager_create_data_source(clipboard->globals->data_manager);
      wl_data_source_add_listener(clipboard->source, &clipboard_source_listener, clipboard);
      wl_data_source_offer(clipboard->source, "text/plain;charset=utf-8");
    }
    set_selection(clipboard, clipboard->globals->invalid_primary ? 0 : serial);
    if (clipboard->globals->invalid_primary) {
      struct wl_callback *callback = wl_display_sync(clipboard->globals->display);
      wl_callback_add_listener(callback, &checked_selection_listener, NULL);
    }
    puts("Clipboard source set"); fflush(stdout);
  }
}
static void modifiers(void *data, struct wl_keyboard *keyboard, uint32_t serial, uint32_t depressed,
  uint32_t latched, uint32_t locked, uint32_t group) {}
static const struct wl_keyboard_listener clipboard_keyboard_listener = {
  .keymap = keymap, .enter = key_enter, .leave = key_leave, .key = key, .modifiers = modifiers
};
static void capabilities(void *data, struct wl_seat *seat, uint32_t caps)
{
  struct clipboard *clipboard = data;
  if ((caps & WL_SEAT_CAPABILITY_KEYBOARD) && !clipboard->keyboard) {
    clipboard->keyboard = wl_seat_get_keyboard(seat);
    wl_keyboard_add_listener(clipboard->keyboard, &clipboard_keyboard_listener, clipboard);
  }
}
static const struct wl_seat_listener clipboard_seat_listener = {.capabilities = capabilities};
static int test_clipboard(struct wl_display *display, struct globals *globals, bool write_mode,
    const char *path, const char *receive_mime, bool stall)
{
  if (!globals->seat || (globals->primary_mode ? !globals->primary_manager : !globals->data_manager)) return 1;
  alarm(20);
  struct clipboard clipboard = {.globals = globals, .write = write_mode, .read_fd = -1,
    .receive_mime = receive_mime, .stall = stall};
  FILE *file = fopen(path, write_mode ? "rb" : "wb");
  if (!file) return 1;
  if (write_mode) {
    fseek(file, 0, SEEK_END); clipboard.length = ftell(file); rewind(file);
    clipboard.payload = malloc(clipboard.length);
    if (fread(clipboard.payload, 1, clipboard.length, file) != clipboard.length) return 1;
    fclose(file); file = NULL;
  }
  if (globals->primary_mode) {
    clipboard.device = zwp_primary_selection_device_manager_v1_get_device(globals->primary_manager, globals->seat);
    zwp_primary_selection_device_v1_add_listener(clipboard.device, &primary_device_listener, &clipboard);
  } else {
    clipboard.device = wl_data_device_manager_get_data_device(globals->data_manager, globals->seat);
    wl_data_device_add_listener(clipboard.device, &clipboard_device_listener, &clipboard);
  }
  wl_seat_add_listener(globals->seat, &clipboard_seat_listener, &clipboard);
  struct test_window window = {0};
  if (!create_window(globals, &window, "ClipboardProbe")) return 1;
  wl_surface_commit(window.surface);
  int result = 1;
  while (wl_display_dispatch_pending(display) >= 0) {
    wl_display_flush(display);
    struct pollfd fds[] = {{.fd = wl_display_get_fd(display), .events = POLLIN},
      {.fd = clipboard.read_fd, .events = POLLIN}};
    if (poll(fds, 2, 10000) < 0) break;
    if (fds[0].revents && wl_display_dispatch(display) < 0) break;
    if (fds[1].revents) {
      char buffer[16384];
      ssize_t count = read(clipboard.read_fd, buffer, sizeof(buffer));
      if (count == 0) { result = 0; break; }
      if (count > 0 && fwrite(buffer, 1, count, file) != (size_t)count) break;
      if (count < 0 && errno != EAGAIN && errno != EINTR) break;
    }
  }
  if (file) fclose(file);
  if (clipboard.read_fd >= 0) close(clipboard.read_fd);
  if (clipboard.source) {
    if (globals->primary_mode) zwp_primary_selection_source_v1_destroy(clipboard.source);
    else wl_data_source_destroy(clipboard.source);
  }
  if (clipboard.offer) {
    if (globals->primary_mode) zwp_primary_selection_offer_v1_destroy(clipboard.offer);
    else wl_data_offer_destroy(clipboard.offer);
  }
  free(clipboard.payload);
  destroy_window(&window);
  alarm(0);
  return result;
}

static int test_invalid_drag(struct wl_display *display, struct globals *globals)
{
  if (!globals->seat || !globals->data_manager) return 1;
  alarm(5);
  struct test_window window = {0};
  struct clipboard clipboard = {.globals = globals, .read_fd = -1};
  clipboard.device = wl_data_device_manager_get_data_device(globals->data_manager, globals->seat);
  wl_data_device_add_listener(clipboard.device, &clipboard_device_listener, &clipboard);
  wl_seat_add_listener(globals->seat, &clipboard_seat_listener, &clipboard);
  if (!create_window(globals, &window, "InvalidDragProbe")) return 1;
  wl_surface_commit(window.surface);
  while (!window.activated) if (wl_display_dispatch(display) < 0) return 1;
  clipboard.source = wl_data_device_manager_create_data_source(globals->data_manager);
  wl_data_source_add_listener(clipboard.source, &clipboard_source_listener, &clipboard);
  wl_data_source_offer(clipboard.source, "text/plain;charset=utf-8");
  /* This client has a mapped window but has never received a button grab. */
  wl_data_device_start_drag(clipboard.device, clipboard.source, window.surface, NULL, 0);
  while (clipboard.source) if (wl_display_dispatch(display) < 0) return 1;
  /* A source-less request must also be released without starting a grab. */
  wl_data_device_start_drag(clipboard.device, NULL, window.surface, NULL, 0);
  if (wl_display_roundtrip(display) < 0) return 1;
  destroy_window(&window);
  wl_display_roundtrip(display);
  alarm(0);
  puts("Drag without an authorized pointer grab is cancelled: PASS");
  return 0;
}

struct empty_drag {
  struct wl_surface *surface;
  struct wl_pointer *pointer;
  struct wl_data_device *device;
  bool started;
};
static void empty_enter(void *data, struct wl_pointer *pointer, uint32_t serial,
    struct wl_surface *surface, wl_fixed_t x, wl_fixed_t y) {}
static void empty_leave(void *data, struct wl_pointer *pointer, uint32_t serial, struct wl_surface *surface) {}
static void empty_motion(void *data, struct wl_pointer *pointer, uint32_t time, wl_fixed_t x, wl_fixed_t y) {}
static void empty_axis(void *data, struct wl_pointer *pointer, uint32_t time, uint32_t axis, wl_fixed_t value) {}
static void empty_button(void *data, struct wl_pointer *pointer, uint32_t serial,
    uint32_t time, uint32_t button, uint32_t state)
{
  struct empty_drag *drag = data;
  if (state == WL_POINTER_BUTTON_STATE_PRESSED && !drag->started) {
    drag->started = true;
    wl_data_device_start_drag(drag->device, NULL, drag->surface, NULL, serial);
    puts("Source-less drag requested"); fflush(stdout);
  }
}
static const struct wl_pointer_listener empty_pointer_listener = {
  .enter = empty_enter, .leave = empty_leave, .motion = empty_motion,
  .button = empty_button, .axis = empty_axis
};
static void empty_capabilities(void *data, struct wl_seat *seat, uint32_t capabilities)
{
  struct empty_drag *drag = data;
  if ((capabilities & WL_SEAT_CAPABILITY_POINTER) && !drag->pointer) {
    drag->pointer = wl_seat_get_pointer(seat);
    wl_pointer_add_listener(drag->pointer, &empty_pointer_listener, drag);
  }
}
static const struct wl_seat_listener empty_seat_listener = {.capabilities = empty_capabilities};
static void empty_selection(void *data, struct wl_data_device *device, struct wl_data_offer *offer) {}
static const struct wl_data_device_listener empty_device_listener = {
  .data_offer = new_offer, .enter = data_enter, .leave = data_leave,
  .motion = data_motion, .drop = data_drop, .selection = empty_selection
};
static int test_empty_drag(struct wl_display *display, struct globals *globals)
{
  if (!globals->seat || !globals->data_manager) return 1;
  alarm(20);
  struct test_window window = {0};
  if (!create_window(globals, &window, "EmptyDragProbe")) return 1;
  struct empty_drag drag = {.surface = window.surface};
  drag.device = wl_data_device_manager_get_data_device(globals->data_manager, globals->seat);
  wl_data_device_add_listener(drag.device, &empty_device_listener, &drag);
  wl_seat_add_listener(globals->seat, &empty_seat_listener, &drag);
  wl_surface_commit(window.surface);
  while (!window.closed) if (wl_display_dispatch(display) < 0) return 1;
  destroy_window(&window);
  wl_display_roundtrip(display);
  alarm(0);
  return drag.started ? 0 : 1;
}

#include "text-input-probe.h"
#include "color-pick-probe.h"

int main(int argc, char **argv)
{
  struct wl_display *display = wl_display_connect(NULL);
  if (!display) return 1;
  bool invalid_drag = argc == 2 && strcmp(argv[1], "--invalid-drag") == 0;
  bool empty_drag = argc == 2 && strcmp(argv[1], "--empty-drag") == 0;
  struct globals globals = {.display = display,
    .color_pick_mode = argc == 2 && (strcmp(argv[1], "--color-pick") == 0 || strcmp(argv[1], "--color-source") == 0),
    .text_mode = argc == 2 && strcmp(argv[1], "--text-input") == 0,
    .method_mode = argc == 2 && (strcmp(argv[1], "--input-method") == 0 || strcmp(argv[1], "--input-method-daemon") == 0),
    .method_daemon = argc == 2 && strcmp(argv[1], "--input-method-daemon") == 0,
    .clipboard_mode = invalid_drag || empty_drag || (argc >= 3 && strncmp(argv[1], "--clipboard-", 12) == 0),
    .primary_mode = argc >= 3 && strncmp(argv[1], "--primary-", 10) == 0,
    .invalid_primary = argc >= 3 && strcmp(argv[1], "--primary-invalid") == 0,
    .activation_mode = argc == 2 && strcmp(argv[1], "--activation") == 0,
    .focus_mode = argc == 2 && (strcmp(argv[1], "--no-focus") == 0 || strcmp(argv[1], "--color-source") == 0),
    .policy_mode = argc == 4 && strcmp(argv[1], "--window") == 0};
  struct wl_registry *registry = wl_display_get_registry(display);
  wl_registry_add_listener(registry, &listener, &globals);
  int result = wl_display_roundtrip(display);
  if (globals.color_pick_mode) {
    int status = test_color_pick(&globals);
    wl_display_disconnect(display); return status;
  }
  if (globals.text_mode || globals.method_mode) {
    int status = test_text_input(&globals);
    wl_display_disconnect(display); return status;
  }
  if (argc == 3 && strcmp(argv[1], "--forbidden-input-method") == 0) {
    wl_registry_bind(registry, (uint32_t)strtoul(argv[2], NULL, 10), &zwp_input_method_manager_v2_interface, 1);
    result = wl_display_roundtrip(display);
    bool rejected = result < 0 && wl_display_get_error(display) == EPROTO;
    wl_display_disconnect(display); return rejected ? 0 : 1;
  }
  if (globals.activation_mode) {
    int status = test_activation(display, &globals);
    wl_display_disconnect(display); return status;
  }
  if (empty_drag) {
    int status = test_empty_drag(display, &globals);
    wl_display_disconnect(display);
    return status;
  }
  if (invalid_drag) {
    int status = test_invalid_drag(display, &globals);
    wl_display_disconnect(display);
    return status;
  }
  if ((argc == 3 || argc == 4) && (strcmp(argv[1], "--window") == 0 || strcmp(argv[1], "--small-fullscreen") == 0)) {
    struct test_window window = {0};
    if (!create_window(&globals, &window, argv[2])) return 1;
    /* A familiar application name must never confer shell authority. */
    xdg_toplevel_set_app_id(window.top, "Workspace");
    if (strcmp(argv[1], "--small-fullscreen") == 0) {
      for (int i = 0; i < 64 * 64; i++) ((uint32_t *)window.pixels)[i] = 0x80808080;
      xdg_toplevel_set_fullscreen(window.top, NULL);
    }
    struct nextspace_window_v1 *object = NULL;
    if (globals.policy_mode) {
      if (!globals.application || nextspace_application_v1_get_version(globals.application) < 3) return 1;
      object = nextspace_application_v1_get_window(globals.application, window.surface);
      nextspace_window_v1_add_listener(object, &window_listener, &window);
      nextspace_window_v1_set_level(object, atoi(argv[3]));
    }
    wl_surface_commit(window.surface);
    while (!window.closed && wl_display_dispatch(display) >= 0) {}
    bool closed = window.closed;
    if (object) nextspace_window_v1_destroy(object);
    destroy_window(&window);
    wl_display_flush(display);
    wl_display_disconnect(display);
    return closed ? 0 : 1;
  }
  if (globals.focus_mode) {
    int status = test_focus(display, &globals);
    wl_display_disconnect(display);
    return status;
  }
  if ((argc == 3 || argc == 4) && (strcmp(argv[1], "--clipboard-read") == 0 ||
      strcmp(argv[1], "--clipboard-write") == 0 || strcmp(argv[1], "--clipboard-stall") == 0 || globals.primary_mode)) {
    int status = test_clipboard(display, &globals, strcmp(argv[1], "--clipboard-read") != 0 && strcmp(argv[1], "--primary-read") != 0,
      argv[2], argc == 4 ? argv[3] : "text/plain;charset=utf-8", (strcmp(argv[1], "--clipboard-stall") == 0 || strcmp(argv[1], "--primary-stall") == 0));
    wl_display_disconnect(display);
    return status;
  }
  if (argc > 1 && strcmp(argv[1], "--placement") == 0) {
    int status = test_placement(display, &globals);
    wl_display_disconnect(display);
    return status;
  }
  if (argc > 1 && strcmp(argv[1], "--invalid-placement") == 0) {
    if (!globals.application || !globals.compositor) return 1;
    struct wl_surface *surface = wl_compositor_create_surface(globals.compositor);
    nextspace_application_v1_get_window(globals.application, surface);
    result = wl_display_roundtrip(display);
    const struct wl_interface *interface = NULL;
    uint32_t code = wl_display_get_protocol_error(display, &interface, NULL);
    bool rejected = result == -1 && wl_display_get_error(display) == EPROTO &&
      interface == &nextspace_application_v1_interface && code == NEXTSPACE_APPLICATION_V1_ERROR_INVALID_SURFACE;
    wl_display_disconnect(display);
    if (rejected) puts("Placement rejects a surface without an owned xdg toplevel: PASS");
    return rejected ? 0 : 1;
  }
  wl_registry_destroy(registry);
  wl_display_disconnect(display);
  if (globals.forbidden || result < 0) return 1;
  puts("Privileged compositor globals are hidden from ordinary clients: PASS");
  return 0;
}
