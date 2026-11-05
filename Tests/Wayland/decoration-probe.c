/* Independent xdg-decoration negotiation and input fixture. MIT license. */
#define _GNU_SOURCE
#include <wayland-client.h>
#include "xdg-shell-client-protocol.h"
#include "xdg-decoration-unstable-v1-client-protocol.h"
#include "nextspace-application-v1-client-protocol.h"
#include <poll.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

struct probe {
  struct wl_compositor *compositor;
  struct wl_shm *shm;
  struct xdg_wm_base *shell;
  struct zxdg_decoration_manager_v1 *manager;
  struct wl_surface *surface;
  struct xdg_surface *xdg;
  struct xdg_toplevel *top;
  struct zxdg_toplevel_decoration_v1 *decoration;
  struct wl_seat *seat;
  struct wl_pointer *pointer;
  struct nextspace_application_v1 *application;
  struct nextspace_window_v1 *owned;
  int width, height;
  uint32_t mode;
  bool closed, fullscreen;
};

struct buffer {
  struct wl_buffer *object;
  void *pixels;
  size_t length;
};

static void released(void *data, struct wl_buffer *object)
{
  struct buffer *buffer = data;
  wl_buffer_destroy(object);
  munmap(buffer->pixels, buffer->length);
  free(buffer);
}
static const struct wl_buffer_listener buffer_listener = {.release = released};

static void configured(void *data, struct xdg_surface *surface, uint32_t serial)
{
  struct probe *probe = data;
  struct buffer *buffer = calloc(1, sizeof(*buffer));
  buffer->length = (size_t)probe->width * probe->height * 4;
  int fd = memfd_create("nextspace-decoration-probe", MFD_CLOEXEC);
  if (fd < 0 || ftruncate(fd, buffer->length)) exit(1);
  buffer->pixels = mmap(NULL, buffer->length, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
  if (buffer->pixels == MAP_FAILED) exit(1);
  uint32_t *pixels = buffer->pixels;
  for (size_t i = 0; i < buffer->length / 4; i++) pixels[i] = 0xff55aa77;
  struct wl_shm_pool *pool = wl_shm_create_pool(probe->shm, fd, buffer->length);
  buffer->object = wl_shm_pool_create_buffer(pool, 0, probe->width, probe->height,
    probe->width * 4, WL_SHM_FORMAT_ARGB8888);
  wl_buffer_add_listener(buffer->object, &buffer_listener, buffer);
  wl_shm_pool_destroy(pool); close(fd);
  xdg_surface_ack_configure(surface, serial);
  wl_surface_attach(probe->surface, buffer->object, 0, 0);
  wl_surface_damage(probe->surface, 0, 0, probe->width, probe->height);
  wl_surface_commit(probe->surface);
  printf("{\"event\":\"configure\",\"mode\":%u,\"width\":%d,\"height\":%d,\"fullscreen\":%s}\n",
    probe->mode, probe->width, probe->height, probe->fullscreen ? "true" : "false");
  fflush(stdout);
}
static const struct xdg_surface_listener surface_listener = {.configure = configured};

static void size_configured(void *data, struct xdg_toplevel *top, int32_t width,
    int32_t height, struct wl_array *states)
{
  struct probe *probe = data;
  if (width > 0) probe->width = width;
  if (height > 0) probe->height = height;
  probe->fullscreen = false;
  uint32_t *state;
  wl_array_for_each(state, states) if (*state == XDG_TOPLEVEL_STATE_FULLSCREEN) probe->fullscreen = true;
}
static void closed(void *data, struct xdg_toplevel *top)
{ ((struct probe *)data)->closed = true; puts("{\"event\":\"close\"}"); fflush(stdout); }
static const struct xdg_toplevel_listener top_listener = {.configure = size_configured, .close = closed};
static void mode_configured(void *data, struct zxdg_toplevel_decoration_v1 *decoration, uint32_t mode)
{ ((struct probe *)data)->mode = mode; }
static const struct zxdg_toplevel_decoration_v1_listener decoration_listener = {.configure = mode_configured};

static void pointer_enter(void *data, struct wl_pointer *pointer, uint32_t serial,
    struct wl_surface *surface, wl_fixed_t x, wl_fixed_t y)
{ printf("{\"event\":\"enter\",\"x\":%.3f,\"y\":%.3f}\n", wl_fixed_to_double(x), wl_fixed_to_double(y)); fflush(stdout); }
static void pointer_leave(void *data, struct wl_pointer *pointer, uint32_t serial, struct wl_surface *surface) {}
static void pointer_motion(void *data, struct wl_pointer *pointer, uint32_t time, wl_fixed_t x, wl_fixed_t y)
{
  printf("{\"event\":\"motion\",\"x\":%.3f,\"y\":%.3f}\n", wl_fixed_to_double(x), wl_fixed_to_double(y)); fflush(stdout);
}
static void pointer_button(void *data, struct wl_pointer *pointer, uint32_t serial,
    uint32_t time, uint32_t button, uint32_t state)
{ printf("{\"event\":\"button\",\"state\":%u}\n", state); fflush(stdout); }
static void pointer_axis(void *data, struct wl_pointer *pointer, uint32_t time, uint32_t axis, wl_fixed_t value) {}
static const struct wl_pointer_listener pointer_listener = {.enter = pointer_enter, .leave = pointer_leave,
  .motion = pointer_motion, .button = pointer_button, .axis = pointer_axis};
static void seat_capabilities(void *data, struct wl_seat *seat, uint32_t capabilities)
{
  struct probe *probe = data;
  if ((capabilities & WL_SEAT_CAPABILITY_POINTER) && !probe->pointer) {
    probe->pointer = wl_seat_get_pointer(seat);
    wl_pointer_add_listener(probe->pointer, &pointer_listener, probe);
  }
}
static const struct wl_seat_listener seat_listener = {.capabilities = seat_capabilities};
static void ping(void *data, struct xdg_wm_base *shell, uint32_t serial) { xdg_wm_base_pong(shell, serial); }
static const struct xdg_wm_base_listener shell_listener = {.ping = ping};
static void areas_reset(void *data, struct nextspace_application_v1 *object) {}
static void area(void *data, struct nextspace_application_v1 *object, const char *name,
    int32_t x, int32_t y, int32_t width, int32_t height) {}
static const struct nextspace_application_v1_listener application_listener = {
  .work_areas_reset = areas_reset, .work_area = area, .work_areas_done = areas_reset
};
static void position(void *data, struct nextspace_window_v1 *object, int32_t x, int32_t y) {}
static void preferred_output(void *data, struct nextspace_window_v1 *object, const char *name) {}
static void owned_closed(void *data, struct nextspace_window_v1 *object) {}
static void minimized(void *data, struct nextspace_window_v1 *object, uint32_t value) {}
static void drag_context(void *data, struct nextspace_window_v1 *object, struct wl_surface *surface,
    uint32_t id, uint32_t phase, uint32_t local, wl_fixed_t x, wl_fixed_t y) {}
static const struct nextspace_window_v1_listener owned_listener = {.position = position,
  .preferred_output = preferred_output, .closed = owned_closed, .minimized = minimized,
  .drag_context = drag_context};
static void global(void *data, struct wl_registry *registry, uint32_t name, const char *interface, uint32_t version)
{
  struct probe *probe = data;
  if (!strcmp(interface, "wl_compositor")) probe->compositor = wl_registry_bind(registry, name, &wl_compositor_interface, 1);
  if (!strcmp(interface, "wl_shm")) probe->shm = wl_registry_bind(registry, name, &wl_shm_interface, 1);
  if (!strcmp(interface, "wl_seat")) {
    probe->seat = wl_registry_bind(registry, name, &wl_seat_interface, 1);
    wl_seat_add_listener(probe->seat, &seat_listener, probe);
  }
  if (!strcmp(interface, "zxdg_decoration_manager_v1"))
    probe->manager = wl_registry_bind(registry, name, &zxdg_decoration_manager_v1_interface, 1);
  if (!strcmp(interface, "nextspace_application_v1")) {
    probe->application = wl_registry_bind(registry, name, &nextspace_application_v1_interface, version < 7 ? version : 7);
    if (version >= 6) nextspace_application_v1_add_listener(probe->application, &application_listener, probe);
  }
  if (!strcmp(interface, "xdg_wm_base")) {
    probe->shell = wl_registry_bind(registry, name, &xdg_wm_base_interface, 1);
    xdg_wm_base_add_listener(probe->shell, &shell_listener, probe);
  }
}
static void removed(void *data, struct wl_registry *registry, uint32_t name) {}
static const struct wl_registry_listener registry_listener = {.global = global, .global_remove = removed};

static void create_decoration(struct probe *probe)
{
  probe->decoration = zxdg_decoration_manager_v1_get_toplevel_decoration(probe->manager, probe->top);
  zxdg_toplevel_decoration_v1_add_listener(probe->decoration, &decoration_listener, probe);
}

int main(int argc, char **argv)
{
  setvbuf(stdin, NULL, _IONBF, 0);
  struct probe probe = {.width = 321, .height = 241};
  struct wl_display *display = wl_display_connect(NULL);
  if (!display) return 1;
  struct wl_registry *registry = wl_display_get_registry(display);
  wl_registry_add_listener(registry, &registry_listener, &probe);
  if (wl_display_roundtrip(display) < 0 || !probe.compositor || !probe.shm || !probe.shell || !probe.manager) return 1;
  probe.surface = wl_compositor_create_surface(probe.compositor);
  probe.xdg = xdg_wm_base_get_xdg_surface(probe.shell, probe.surface);
  probe.top = xdg_surface_get_toplevel(probe.xdg);
  xdg_toplevel_add_listener(probe.top, &top_listener, &probe);
  xdg_surface_add_listener(probe.xdg, &surface_listener, &probe);
  xdg_toplevel_set_title(probe.top, "DecorationProbe");
  bool metrics = argc > 1 && !strcmp(argv[1], "--metrics");
  if (metrics) {
    if (!probe.application || nextspace_application_v1_get_version(probe.application) < 7) return 1;
    probe.owned = nextspace_application_v1_get_window(probe.application, probe.surface);
    nextspace_window_v1_add_listener(probe.owned, &owned_listener, &probe);
    nextspace_window_v1_set_metadata(probe.owned, 1, 15, 23);
    nextspace_window_v1_set_frame_extents(probe.owned, 1, 23, 1, 9);
  }
  create_decoration(&probe);
  if (argc > 1 && !metrics) zxdg_toplevel_decoration_v1_set_mode(probe.decoration, strtoul(argv[1], NULL, 10));
  wl_surface_commit(probe.surface);
  char line[128];
  while (!probe.closed && wl_display_dispatch_pending(display) >= 0) {
    if (wl_display_flush(display) < 0) break;
    struct pollfd fds[] = {{.fd = wl_display_get_fd(display), .events = POLLIN}, {.fd = STDIN_FILENO, .events = POLLIN}};
    if (poll(fds, 2, -1) < 0) break;
    if (fds[0].revents && wl_display_dispatch(display) < 0) break;
    if (fds[1].revents) {
      if (!fgets(line, sizeof(line), stdin)) break;
      unsigned mode, left, top, right, bottom;
      char action[32];
      if (sscanf(line, "%31s %u %u %u %u", action, &left, &top, &right, &bottom) == 5 &&
          probe.owned && (!strcmp(action, "metrics") || !strcmp(action, "pending-metrics"))) {
        nextspace_window_v1_set_frame_extents(probe.owned, left, top, right, bottom);
        if (!strcmp(action, "metrics")) wl_surface_commit(probe.surface);
      } else if (sscanf(line, "style %u", &mode) == 1 && probe.owned)
        nextspace_window_v1_set_metadata(probe.owned, 1, mode, mode & 1 ? 23 : 0);
      else if (sscanf(line, "edited %u", &mode) == 1 && probe.owned)
        nextspace_window_v1_set_document_edited(probe.owned, mode);
      else if (sscanf(line, "title-state %u", &mode) == 1 && probe.owned)
        nextspace_window_v1_set_title_state(probe.owned, mode);
      else if (!strncmp(line, "forget-window", 13) && probe.owned) {
        nextspace_window_v1_destroy(probe.owned); probe.owned = NULL;
      }
      else if (!strncmp(line, "commit", 6)) wl_surface_commit(probe.surface);
      else if (sscanf(line, "mode %u", &mode) == 1 && probe.decoration)
        zxdg_toplevel_decoration_v1_set_mode(probe.decoration, mode);
      else if (!strncmp(line, "unset", 5) && probe.decoration) zxdg_toplevel_decoration_v1_unset_mode(probe.decoration);
      else if (!strncmp(line, "destroy", 7) && probe.decoration) {
        zxdg_toplevel_decoration_v1_destroy(probe.decoration); probe.decoration = NULL; probe.mode = 1;
        wl_surface_commit(probe.surface);
      } else if (!strncmp(line, "maximize", 8)) xdg_toplevel_set_maximized(probe.top);
      else if (!strncmp(line, "restore", 7)) xdg_toplevel_unset_maximized(probe.top);
      else if (!strncmp(line, "fullscreen", 10)) xdg_toplevel_set_fullscreen(probe.top, NULL);
      else if (!strncmp(line, "unfullscreen", 12)) xdg_toplevel_unset_fullscreen(probe.top);
      else if (!strncmp(line, "title", 5)) xdg_toplevel_set_title(probe.top, "Unicode title: \316\251");
      else if (!strncmp(line, "sync", 4)) {
        if (wl_display_roundtrip(display) < 0) break;
        puts("{\"event\":\"sync\"}"); fflush(stdout);
      }
      else if (!strncmp(line, "quit", 4)) break;
    }
  }
  bool failed = wl_display_get_error(display) != 0;
  if (!failed) {
    if (probe.owned) nextspace_window_v1_destroy(probe.owned);
    if (probe.decoration) zxdg_toplevel_decoration_v1_destroy(probe.decoration);
    xdg_toplevel_destroy(probe.top); xdg_surface_destroy(probe.xdg); wl_surface_destroy(probe.surface);
    wl_display_flush(display);
  }
  wl_display_disconnect(display);
  return failed;
}
