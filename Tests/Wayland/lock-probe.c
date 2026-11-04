/* Real session-lock client for private-capability integration tests. MIT. */
#define _GNU_SOURCE
#include <wayland-client.h>
#include "ext-session-lock-v1-client-protocol.h"
#include "fractional-scale-v1-client-protocol.h"
#include "viewporter-client-protocol.h"
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

struct probe;
struct output {
  struct probe *probe;
  struct wl_output *output;
  struct wl_surface *surface;
  struct ext_session_lock_surface_v1 *lock_surface;
  struct wp_fractional_scale_v1 *fractional;
  struct wp_viewport *viewport;
  struct wl_buffer *buffer;
  uint32_t global, width, height, scale, integer_scale;
  char name[128];
  struct wl_list link;
};
struct probe {
  struct wl_display *display;
  struct wl_registry *registry;
  struct wl_compositor *compositor;
  struct wl_shm *shm;
  struct wl_seat *seat;
  struct wl_keyboard *keyboard;
  struct wl_pointer *pointer;
  struct ext_session_lock_manager_v1 *manager;
  struct ext_session_lock_v1 *lock;
  struct wp_fractional_scale_manager_v1 *fractional;
  struct wp_viewporter *viewporter;
  struct wl_list outputs;
  uint32_t manager_global, color;
  unsigned keys, buttons;
  bool registry_only, locked, finished, paint, running;
};

static void draw(struct output *output)
{
  struct probe *probe = output->probe;
  if (!probe->paint || !output->width || !output->height || !output->surface) return;
  uint32_t scale = output->fractional ? output->scale : output->integer_scale * 120;
  uint32_t width = (output->width * scale + 60) / 120, height = (output->height * scale + 60) / 120;
  size_t size = (size_t)width * height * 4;
  if (!width || !height || width > 16384 || height > 16384 || size > INT32_MAX) exit(1);
  int fd = memfd_create("nextspace-lock-probe", MFD_CLOEXEC);
  if (fd < 0 || ftruncate(fd, size)) exit(1);
  uint32_t *pixels = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
  if (pixels == MAP_FAILED) exit(1);
  for (size_t i = 0; i < size / 4; i++) pixels[i] = probe->color;
  struct wl_shm_pool *pool = wl_shm_create_pool(probe->shm, fd, size);
  struct wl_buffer *buffer = wl_shm_pool_create_buffer(pool, 0, width, height, width * 4, WL_SHM_FORMAT_ARGB8888);
  wl_shm_pool_destroy(pool); close(fd); munmap(pixels, size);
  if (output->buffer) wl_buffer_destroy(output->buffer);
  output->buffer = buffer;
  if (output->viewport) {
    wl_surface_set_buffer_scale(output->surface, 1);
    wp_viewport_set_destination(output->viewport, output->width, output->height);
  } else wl_surface_set_buffer_scale(output->surface, output->integer_scale);
  wl_surface_attach(output->surface, buffer, 0, 0);
  wl_surface_damage(output->surface, 0, 0, INT32_MAX, INT32_MAX);
  wl_surface_commit(output->surface);
  printf("{\"event\":\"surface\",\"output\":\"%s\",\"width\":%u,\"height\":%u,\"buffer_width\":%u,\"buffer_height\":%u,\"scale\":%u}\n",
    output->name, output->width, output->height, width, height, scale); fflush(stdout);
}

static void preferred_scale(void *data, struct wp_fractional_scale_v1 *object, uint32_t scale)
{
  struct output *output = data;
  if (output->scale == scale) return;
  output->scale = scale; draw(output);
}
static const struct wp_fractional_scale_v1_listener fractional_listener = {.preferred_scale = preferred_scale};
static void configure(void *data, struct ext_session_lock_surface_v1 *object, uint32_t serial, uint32_t width, uint32_t height)
{
  struct output *output = data;
  ext_session_lock_surface_v1_ack_configure(object, serial);
  output->width = width; output->height = height; draw(output);
}
static const struct ext_session_lock_surface_v1_listener surface_listener = {.configure = configure};

static void create_surface(struct output *output)
{
  struct probe *probe = output->probe;
  if (!probe->lock || output->surface) return;
  output->surface = wl_compositor_create_surface(probe->compositor);
  wl_surface_set_user_data(output->surface, output);
  if (probe->fractional && probe->viewporter) {
    output->fractional = wp_fractional_scale_manager_v1_get_fractional_scale(probe->fractional, output->surface);
    wp_fractional_scale_v1_add_listener(output->fractional, &fractional_listener, output);
    output->viewport = wp_viewporter_get_viewport(probe->viewporter, output->surface);
  }
  output->lock_surface = ext_session_lock_v1_get_lock_surface(probe->lock, output->surface, output->output);
  ext_session_lock_surface_v1_add_listener(output->lock_surface, &surface_listener, output);
}
static void destroy_surface(struct output *output)
{
  if (output->lock_surface) ext_session_lock_surface_v1_destroy(output->lock_surface);
  if (output->fractional) wp_fractional_scale_v1_destroy(output->fractional);
  if (output->viewport) wp_viewport_destroy(output->viewport);
  if (output->buffer) wl_buffer_destroy(output->buffer);
  if (output->surface) wl_surface_destroy(output->surface);
  output->lock_surface = NULL; output->fractional = NULL; output->viewport = NULL;
  output->buffer = NULL; output->surface = NULL; output->width = output->height = 0;
}
static void locked(void *data, struct ext_session_lock_v1 *lock)
{ ((struct probe *)data)->locked = true; puts("{\"event\":\"locked\"}"); fflush(stdout); }
static void finished(void *data, struct ext_session_lock_v1 *lock)
{ ((struct probe *)data)->finished = true; puts("{\"event\":\"finished\"}"); fflush(stdout); }
static const struct ext_session_lock_v1_listener lock_listener = {.locked = locked, .finished = finished};

static void geometry(void *data, struct wl_output *object, int32_t x, int32_t y, int32_t pw, int32_t ph,
                     int32_t subpixel, const char *make, const char *model, int32_t transform) {}
static void mode(void *data, struct wl_output *object, uint32_t flags, int32_t width, int32_t height, int32_t refresh) {}
static void done(void *data, struct wl_output *object) { create_surface(data); }
static void scale(void *data, struct wl_output *object, int32_t scale)
{ struct output *output = data; output->integer_scale = scale > 0 ? scale : 1; if (!output->fractional) draw(output); }
static void name(void *data, struct wl_output *object, const char *name)
{ snprintf(((struct output *)data)->name, sizeof(((struct output *)data)->name), "%s", name); }
static void description(void *data, struct wl_output *object, const char *description) {}
static const struct wl_output_listener output_listener = {
  .geometry = geometry, .mode = mode, .done = done, .scale = scale, .name = name, .description = description};

static void keymap(void *data, struct wl_keyboard *keyboard, uint32_t format, int fd, uint32_t size) { close(fd); }
static void enter(void *data, struct wl_keyboard *keyboard, uint32_t serial, struct wl_surface *surface, struct wl_array *keys) {}
static void leave(void *data, struct wl_keyboard *keyboard, uint32_t serial, struct wl_surface *surface) {}
static void key(void *data, struct wl_keyboard *keyboard, uint32_t serial, uint32_t time, uint32_t key, uint32_t state)
{ struct probe *probe = data; printf("{\"event\":\"key\",\"count\":%u}\n", ++probe->keys); fflush(stdout); }
static void modifiers(void *data, struct wl_keyboard *keyboard, uint32_t serial, uint32_t depressed,
                      uint32_t latched, uint32_t locked, uint32_t group) {}
static void repeat(void *data, struct wl_keyboard *keyboard, int32_t rate, int32_t delay) {}
static const struct wl_keyboard_listener keyboard_listener = {
  .keymap = keymap, .enter = enter, .leave = leave, .key = key, .modifiers = modifiers, .repeat_info = repeat};
static void pointer_enter(void *data, struct wl_pointer *pointer, uint32_t serial, struct wl_surface *surface, wl_fixed_t x, wl_fixed_t y) {}
static void pointer_leave(void *data, struct wl_pointer *pointer, uint32_t serial, struct wl_surface *surface) {}
static void motion(void *data, struct wl_pointer *pointer, uint32_t time, wl_fixed_t x, wl_fixed_t y) {}
static void button(void *data, struct wl_pointer *pointer, uint32_t serial, uint32_t time, uint32_t button, uint32_t state)
{ struct probe *probe = data; printf("{\"event\":\"button\",\"count\":%u}\n", ++probe->buttons); fflush(stdout); }
static void axis(void *data, struct wl_pointer *pointer, uint32_t time, uint32_t axis, wl_fixed_t value) {}
static const struct wl_pointer_listener pointer_listener = {
  .enter = pointer_enter, .leave = pointer_leave, .motion = motion, .button = button, .axis = axis};
static void capabilities(void *data, struct wl_seat *seat, uint32_t caps)
{
  struct probe *probe = data;
  if ((caps & WL_SEAT_CAPABILITY_KEYBOARD) && !probe->keyboard) {
    probe->keyboard = wl_seat_get_keyboard(seat); wl_keyboard_add_listener(probe->keyboard, &keyboard_listener, probe);
  }
  if ((caps & WL_SEAT_CAPABILITY_POINTER) && !probe->pointer) {
    probe->pointer = wl_seat_get_pointer(seat); wl_pointer_add_listener(probe->pointer, &pointer_listener, probe);
  }
}
static void seat_name(void *data, struct wl_seat *seat, const char *name) {}
static const struct wl_seat_listener seat_listener = {.capabilities = capabilities, .name = seat_name};

static void global(void *data, struct wl_registry *registry, uint32_t name, const char *interface, uint32_t version)
{
  struct probe *probe = data;
  if (!strcmp(interface, "wl_compositor")) probe->compositor = wl_registry_bind(registry, name, &wl_compositor_interface, 4);
  else if (!strcmp(interface, "wl_shm")) probe->shm = wl_registry_bind(registry, name, &wl_shm_interface, 1);
  else if (!strcmp(interface, "wl_seat")) {
    probe->seat = wl_registry_bind(registry, name, &wl_seat_interface, 1);
    wl_seat_add_listener(probe->seat, &seat_listener, probe);
  } else if (!strcmp(interface, "ext_session_lock_manager_v1")) {
    probe->manager_global = name;
    probe->manager = wl_registry_bind(registry, name, &ext_session_lock_manager_v1_interface, 1);
  } else if (!strcmp(interface, "wp_fractional_scale_manager_v1"))
    probe->fractional = wl_registry_bind(registry, name, &wp_fractional_scale_manager_v1_interface, 1);
  else if (!strcmp(interface, "wp_viewporter")) probe->viewporter = wl_registry_bind(registry, name, &wp_viewporter_interface, 1);
  else if (!strcmp(interface, "wl_output")) {
    struct output *output = calloc(1, sizeof(*output));
    output->probe = probe; output->global = name; output->scale = 120; output->integer_scale = 1;
    output->output = wl_registry_bind(registry, name, &wl_output_interface, version >= 4 ? 4 : 2);
    snprintf(output->name, sizeof(output->name), "global-%u", name);
    wl_output_add_listener(output->output, &output_listener, output);
    wl_list_insert(&probe->outputs, &output->link);
  }
}
static void global_remove(void *data, struct wl_registry *registry, uint32_t name)
{
  struct probe *probe = data; struct output *output, *temporary;
  wl_list_for_each_safe(output, temporary, &probe->outputs, link) if (output->global == name) {
    destroy_surface(output); wl_output_destroy(output->output); wl_list_remove(&output->link); free(output);
  }
}
static const struct wl_registry_listener registry_listener = {.global = global, .global_remove = global_remove};

static void command(struct probe *probe, const char *line)
{
  struct output *output;
  if (!strcmp(line, "sync")) {
    if (wl_display_roundtrip(probe->display) < 0) exit(1);
    puts("{\"event\":\"sync\"}"); fflush(stdout);
  } else if (!strcmp(line, "lock") && !probe->lock) {
    probe->lock = ext_session_lock_manager_v1_lock(probe->manager);
    probe->locked = probe->finished = false;
    ext_session_lock_v1_add_listener(probe->lock, &lock_listener, probe);
    wl_list_for_each(output, &probe->outputs, link) create_surface(output);
  } else if (!strcmp(line, "paint")) {
    probe->paint = true; wl_list_for_each(output, &probe->outputs, link) draw(output);
  } else if (!strcmp(line, "unlock") && probe->locked) {
    ext_session_lock_v1_unlock_and_destroy(probe->lock); probe->lock = NULL; probe->locked = false;
    wl_list_for_each(output, &probe->outputs, link) destroy_surface(output);
    puts("{\"event\":\"unlocked\"}"); fflush(stdout);
  } else if (!strcmp(line, "quit")) probe->running = false;
}

int main(int argc, char **argv)
{
  struct probe probe = {.color = 0xff204080, .running = true}; wl_list_init(&probe.outputs);
  probe.display = wl_display_connect(NULL); if (!probe.display) return 1;
  probe.registry = wl_display_get_registry(probe.display);
  wl_registry_add_listener(probe.registry, &registry_listener, &probe);
  if (wl_display_roundtrip(probe.display) < 0 || wl_display_roundtrip(probe.display) < 0) return 1;
  if (argc == 2 && !strcmp(argv[1], "--registry")) {
    printf("{\"manager_visible\":%s}\n", probe.manager ? "true" : "false");
    wl_display_disconnect(probe.display); return probe.manager ? 1 : 0;
  }
  if (argc == 3 && !strcmp(argv[1], "--guess")) {
    probe.manager = wl_registry_bind(probe.registry, strtoul(argv[2], NULL, 10), &ext_session_lock_manager_v1_interface, 1);
    probe.lock = ext_session_lock_manager_v1_lock(probe.manager);
    ext_session_lock_v1_add_listener(probe.lock, &lock_listener, &probe);
    int status = wl_display_roundtrip(probe.display);
    if (status >= 0 && !probe.finished) status = wl_display_roundtrip(probe.display);
    bool denied = probe.finished || (status < 0 && wl_display_get_error(probe.display) == EPROTO);
    wl_display_disconnect(probe.display); return denied && !probe.locked ? 0 : 1;
  }
  if (!probe.manager || !probe.compositor || !probe.shm) return 1;
  printf("{\"event\":\"ready\",\"manager\":%u}\n", probe.manager_global); fflush(stdout);
  char input[128]; size_t used = 0;
  while (probe.running) {
    while (wl_display_prepare_read(probe.display) != 0)
      if (wl_display_dispatch_pending(probe.display) < 0) goto failed;
    wl_display_flush(probe.display);
    struct pollfd fds[] = {{wl_display_get_fd(probe.display), POLLIN, 0}, {STDIN_FILENO, POLLIN, 0}};
    if (poll(fds, 2, -1) < 0) { wl_display_cancel_read(probe.display); if (errno == EINTR) continue; goto failed; }
    if (fds[0].revents & POLLIN) {
      if (wl_display_read_events(probe.display) < 0 || wl_display_dispatch_pending(probe.display) < 0) goto failed;
    } else wl_display_cancel_read(probe.display);
    if (fds[0].revents & (POLLERR | POLLHUP)) goto failed;
    if (fds[1].revents & (POLLIN | POLLHUP)) {
      char bytes[128]; ssize_t count = read(STDIN_FILENO, bytes, sizeof(bytes));
      if (count <= 0) break;
      for (ssize_t i = 0; i < count; i++) {
        if (bytes[i] == '\n') { input[used] = 0; command(&probe, input); used = 0; }
        else if (used + 1 < sizeof(input)) input[used++] = bytes[i];
        else goto failed;
      }
    }
  }
  wl_display_disconnect(probe.display); return 0;
failed:
  wl_display_disconnect(probe.display); return 1;
}
