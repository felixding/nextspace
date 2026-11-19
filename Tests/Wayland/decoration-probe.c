/* Independent xdg-decoration negotiation and input fixture. MIT license. */
#define _GNU_SOURCE
#include <wayland-client.h>
#include "xdg-shell-client-protocol.h"
#include "xdg-decoration-unstable-v1-client-protocol.h"
#include "server-decoration-client-protocol.h"
#include "nextspace-application-v1-client-protocol.h"
#include "appmenu-client-protocol.h"
#include <poll.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

struct probe {
  struct org_kde_kwin_appmenu_manager *appmenu_manager;
  struct org_kde_kwin_appmenu *appmenu;
  struct org_kde_kwin_appmenu *appmenu_extra;
  struct wl_compositor *compositor;
  struct wl_shm *shm;
  struct xdg_wm_base *shell;
  struct zxdg_decoration_manager_v1 *manager;
  struct wl_surface *surface;
  struct xdg_surface *xdg;
  struct xdg_toplevel *top;
  struct zxdg_toplevel_decoration_v1 *decoration;
  struct org_kde_kwin_server_decoration_manager *legacy_manager;
  struct org_kde_kwin_server_decoration *legacy_decoration;
  struct wl_seat *seat;
  struct wl_pointer *pointer;
  struct nextspace_application_v1 *application;
  struct nextspace_window_v1 *owned;
  struct nextspace_surface_geometry_v1 *geometry[2];
  bool observe_geometry;
  int width, height;
  uint32_t mode;
  bool closed, fullscreen, legacy_mode;
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
  if (serial) xdg_surface_ack_configure(surface, serial);
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
  printf("{\"event\":\"size-hint\",\"width\":%d,\"height\":%d}\n", width, height);
  fflush(stdout);
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
static void legacy_default(void *data, struct org_kde_kwin_server_decoration_manager *manager, uint32_t mode) {}
static const struct org_kde_kwin_server_decoration_manager_listener legacy_manager_listener = {.default_mode = legacy_default};
static void legacy_mode(void *data, struct org_kde_kwin_server_decoration *decoration, uint32_t mode)
{ ((struct probe *)data)->mode = mode; }
static const struct org_kde_kwin_server_decoration_listener legacy_listener = {.mode = legacy_mode};
static void create_legacy_decoration(struct probe *probe)
{
  probe->legacy_decoration = org_kde_kwin_server_decoration_manager_create(probe->legacy_manager, probe->surface);
  org_kde_kwin_server_decoration_add_listener(probe->legacy_decoration, &legacy_listener, probe);
}

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
static void geometry_changed(void *data, struct nextspace_surface_geometry_v1 *object,
    int32_t x, int32_t y, int32_t width, int32_t height, uint32_t mapped)
{
  printf("{\"event\":\"surface-geometry\",\"observer\":%u,\"x\":%d,\"y\":%d,\"width\":%d,\"height\":%d,\"mapped\":%u}\n",
    (unsigned)(uintptr_t)data, x, y, width, height, mapped); fflush(stdout);
}
static void geometry_closed(void *data, struct nextspace_surface_geometry_v1 *object)
{ printf("{\"event\":\"geometry-closed\",\"observer\":%u}\n", (unsigned)(uintptr_t)data); fflush(stdout); }
static const struct nextspace_surface_geometry_v1_listener geometry_listener = {
  .geometry = geometry_changed, .closed = geometry_closed
};
static void watch_geometry(struct probe *probe, unsigned index)
{
  if (index > 1 || probe->geometry[index] || !probe->application ||
      nextspace_application_v1_get_version(probe->application) < 10) return;
  probe->geometry[index] = nextspace_application_v1_get_surface_geometry(probe->application, probe->surface);
  nextspace_surface_geometry_v1_add_listener(probe->geometry[index], &geometry_listener, (void *)(uintptr_t)index);
}
static void global(void *data, struct wl_registry *registry, uint32_t name, const char *interface, uint32_t version)
{
  struct probe *probe = data;
  if (probe->legacy_mode && !strcmp(interface, "org_kde_kwin_server_decoration_manager")) {
    probe->legacy_manager = wl_registry_bind(registry, name, &org_kde_kwin_server_decoration_manager_interface, 1);
    org_kde_kwin_server_decoration_manager_add_listener(probe->legacy_manager, &legacy_manager_listener, probe);
  }
  if (!strcmp(interface, "org_kde_kwin_appmenu_manager"))
    probe->appmenu_manager = wl_registry_bind(registry, name, &org_kde_kwin_appmenu_manager_interface, version < 2 ? version : 2);
  if (!strcmp(interface, "wl_compositor")) probe->compositor = wl_registry_bind(registry, name, &wl_compositor_interface, 1);
  if (!strcmp(interface, "wl_shm")) probe->shm = wl_registry_bind(registry, name, &wl_shm_interface, 1);
  if (!strcmp(interface, "wl_seat")) {
    probe->seat = wl_registry_bind(registry, name, &wl_seat_interface, 1);
    wl_seat_add_listener(probe->seat, &seat_listener, probe);
  }
  if (!strcmp(interface, "zxdg_decoration_manager_v1"))
    probe->manager = wl_registry_bind(registry, name, &zxdg_decoration_manager_v1_interface, 1);
  if (!strcmp(interface, "nextspace_application_v1")) {
    uint32_t requested = probe->observe_geometry ? 10 : 7;
    probe->application = wl_registry_bind(registry, name, &nextspace_application_v1_interface,
      version < requested ? version : requested);
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
  probe.observe_geometry = argc > 1 && (!strcmp(argv[1], "--geometry") || !strcmp(argv[1], "--geometry-metrics"));
  bool legacy_early = argc > 1 && !strcmp(argv[1], "--legacy-early");
  bool legacy_dual = argc > 1 && !strcmp(argv[1], "--legacy-dual");
  probe.legacy_mode = legacy_early || legacy_dual || (argc > 1 && !strcmp(argv[1], "--legacy"));
  struct wl_display *display = wl_display_connect(NULL);
  if (!display) return 1;
  struct wl_registry *registry = wl_display_get_registry(display);
  wl_registry_add_listener(registry, &registry_listener, &probe);
  if (wl_display_roundtrip(display) < 0 || !probe.compositor || !probe.shm || !probe.shell || !probe.manager) return 1;
  probe.surface = wl_compositor_create_surface(probe.compositor);
  if (probe.legacy_mode && !probe.legacy_manager) return 1;
  if (legacy_early) create_legacy_decoration(&probe);
  probe.xdg = xdg_wm_base_get_xdg_surface(probe.shell, probe.surface);
  probe.top = xdg_surface_get_toplevel(probe.xdg);
  xdg_toplevel_add_listener(probe.top, &top_listener, &probe);
  xdg_surface_add_listener(probe.xdg, &surface_listener, &probe);
  xdg_toplevel_set_title(probe.top, "DecorationProbe");
  bool metrics = argc > 1 && (!strcmp(argv[1], "--metrics") || !strcmp(argv[1], "--geometry-metrics"));
  if (metrics) {
    if (!probe.application || nextspace_application_v1_get_version(probe.application) < 7) return 1;
    probe.owned = nextspace_application_v1_get_window(probe.application, probe.surface);
    nextspace_window_v1_add_listener(probe.owned, &owned_listener, &probe);
    nextspace_window_v1_set_metadata(probe.owned, 1, 15, 23);
    nextspace_window_v1_set_frame_extents(probe.owned, 1, 23, 1, 9);
  }
  if (probe.observe_geometry) { watch_geometry(&probe, 0); watch_geometry(&probe, 1); }
  if (probe.legacy_mode) {
    if (!legacy_early) create_legacy_decoration(&probe);
  } else create_decoration(&probe);
  if (legacy_dual) create_decoration(&probe);
  bool appmenu = argc > 1 && !strcmp(argv[1], "--appmenu");
  if (appmenu) {
    if (!probe.appmenu_manager) return 1;
    probe.appmenu = org_kde_kwin_appmenu_manager_create(probe.appmenu_manager, probe.surface);
    org_kde_kwin_appmenu_set_address(probe.appmenu, ":1.42", "/test/menu");
  }
  if (argc > 1 && !metrics && !appmenu && !probe.legacy_mode && !probe.observe_geometry) zxdg_toplevel_decoration_v1_set_mode(probe.decoration, strtoul(argv[1], NULL, 10));
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
      char service[256], path[4097];
      int gx, gy, gw, gh;
      if (sscanf(line, "watch %u", &mode) == 1) { watch_geometry(&probe, mode); continue; }
      if (sscanf(line, "unwatch %u", &mode) == 1 && mode < 2 && probe.geometry[mode]) {
        nextspace_surface_geometry_v1_destroy(probe.geometry[mode]); probe.geometry[mode] = NULL; continue;
      }
      if (sscanf(line, "geometry %d %d %d %d", &gx, &gy, &gw, &gh) == 4 && probe.xdg) {
        xdg_surface_set_window_geometry(probe.xdg, gx, gy, gw, gh); wl_surface_commit(probe.surface); continue;
      }
      if (!strncmp(line, "unmap", 5)) { wl_surface_attach(probe.surface, NULL, 0, 0); wl_surface_commit(probe.surface); continue; }
      if (!strncmp(line, "remap", 5)) { wl_surface_commit(probe.surface); continue; }
      if (!strncmp(line, "close-toplevel", 14) && probe.top) {
        if (probe.decoration) { zxdg_toplevel_decoration_v1_destroy(probe.decoration); probe.decoration = NULL; }
        xdg_toplevel_destroy(probe.top); xdg_surface_destroy(probe.xdg); wl_surface_destroy(probe.surface);
        probe.top = NULL; probe.xdg = NULL; probe.surface = NULL; continue;
      }
      if (!strncmp(line, "invalid-observer", 16)) {
        struct wl_surface *invalid = wl_compositor_create_surface(probe.compositor);
        nextspace_application_v1_get_surface_geometry(probe.application, invalid); continue;
      }
      if (!strncmp(line, "menu ", 5) && sscanf(line, "menu %255s %4096s", service, path) == 2 && probe.appmenu) {
        org_kde_kwin_appmenu_set_address(probe.appmenu, service, path);
      } else if (!strncmp(line, "menu-release", 12) && probe.appmenu) {
        org_kde_kwin_appmenu_release(probe.appmenu); probe.appmenu = NULL;
      } else if (!strncmp(line, "menu-duplicate", 14) && probe.appmenu) {
        probe.appmenu_extra = org_kde_kwin_appmenu_manager_create(probe.appmenu_manager, probe.surface);
        org_kde_kwin_appmenu_set_address(probe.appmenu_extra, ":1.44", "/replacement/menu");
      } else if (!strncmp(line, "menu-promote", 12) && probe.appmenu && probe.appmenu_extra) {
        org_kde_kwin_appmenu_release(probe.appmenu);
        probe.appmenu = probe.appmenu_extra; probe.appmenu_extra = NULL;
      } else if (sscanf(line, "menu-replace %255s %4096s", service, path) == 2 && probe.appmenu) {
        struct org_kde_kwin_appmenu *replacement = org_kde_kwin_appmenu_manager_create(probe.appmenu_manager, probe.surface);
        org_kde_kwin_appmenu_release(probe.appmenu);
        org_kde_kwin_appmenu_set_address(replacement, service, path); probe.appmenu = replacement;
      } else if (!strncmp(line, "menu-orphan", 11) && probe.appmenu_manager) {
        struct wl_surface *surface = wl_compositor_create_surface(probe.compositor);
        struct org_kde_kwin_appmenu *menu = org_kde_kwin_appmenu_manager_create(probe.appmenu_manager, surface);
        wl_surface_destroy(surface);
        org_kde_kwin_appmenu_set_address(menu, ":1.43", "/test/orphan");
        org_kde_kwin_appmenu_release(menu);
      } else if (sscanf(line, "%31s %u %u %u %u", action, &left, &top, &right, &bottom) == 5 &&
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
      else if (sscanf(line, "legacy-mode %u", &mode) == 1 && probe.legacy_decoration) {
        org_kde_kwin_server_decoration_request_mode(probe.legacy_decoration, mode);
        wl_surface_commit(probe.surface);
      } else if (!strncmp(line, "legacy-destroy", 14) && probe.legacy_decoration) {
        org_kde_kwin_server_decoration_release(probe.legacy_decoration); probe.legacy_decoration = NULL;
        wl_surface_commit(probe.surface);
      } else if (!strncmp(line, "legacy-create", 13) && probe.legacy_mode && !probe.legacy_decoration) {
        create_legacy_decoration(&probe); wl_surface_commit(probe.surface);
      }
      else if (sscanf(line, "mode %u", &mode) == 1 && probe.decoration)
        zxdg_toplevel_decoration_v1_set_mode(probe.decoration, mode);
      else if (!strncmp(line, "unset", 5) && probe.decoration) zxdg_toplevel_decoration_v1_unset_mode(probe.decoration);
      else if (!strncmp(line, "destroy", 7) && probe.decoration) {
        zxdg_toplevel_decoration_v1_destroy(probe.decoration); probe.decoration = NULL; probe.mode = 1;
        wl_surface_commit(probe.surface);
      } else if (sscanf(line, "client-size %d %d", &gw, &gh) == 2 && gw > 0 && gh > 0) {
        probe.width = gw; probe.height = gh;
        xdg_surface_set_window_geometry(probe.xdg, 0, 0, gw, gh);
        configured(&probe, probe.xdg, 0);
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
    if (probe.appmenu) org_kde_kwin_appmenu_release(probe.appmenu);
    if (probe.appmenu_manager && org_kde_kwin_appmenu_manager_get_version(probe.appmenu_manager) >= 2)
      org_kde_kwin_appmenu_manager_release(probe.appmenu_manager);
    for (unsigned i = 0; i < 2; i++) if (probe.geometry[i]) nextspace_surface_geometry_v1_destroy(probe.geometry[i]);
    if (probe.owned) nextspace_window_v1_destroy(probe.owned);
    if (probe.decoration) zxdg_toplevel_decoration_v1_destroy(probe.decoration);
    if (probe.legacy_decoration) org_kde_kwin_server_decoration_release(probe.legacy_decoration);
    if (probe.top) xdg_toplevel_destroy(probe.top);
    if (probe.xdg) xdg_surface_destroy(probe.xdg);
    if (probe.surface) wl_surface_destroy(probe.surface);
    wl_display_flush(display);
  }
  wl_display_disconnect(display);
  return failed;
}
