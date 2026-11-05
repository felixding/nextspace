/* Native output capture and private-capability fixture. MIT license. */
#define _GNU_SOURCE
#include <wayland-client.h>
#include "wlr-screencopy-unstable-v1-client-protocol.h"
#include <fcntl.h>
#include <poll.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

struct output { struct wl_output *object; char name[128]; };
struct probe {
  struct wl_display *display;
  struct wl_shm *shm;
  struct zwlr_screencopy_manager_v1 *manager;
  struct zwlr_screencopy_frame_v1 *frame;
  struct wl_buffer *buffer;
  struct output outputs[32];
  size_t output_count, size;
  void *pixels;
  uint32_t format, width, height, stride, flags, manager_global;
  char path[1024];
};

static void finish_frame(struct probe *probe)
{
  if (probe->buffer) wl_buffer_destroy(probe->buffer);
  if (probe->pixels) munmap(probe->pixels, probe->size);
  if (probe->frame) zwlr_screencopy_frame_v1_destroy(probe->frame);
  probe->buffer = NULL; probe->pixels = NULL; probe->frame = NULL;
}

static void buffer(void *data, struct zwlr_screencopy_frame_v1 *frame,
    uint32_t format, uint32_t width, uint32_t height, uint32_t stride)
{
  struct probe *probe = data;
  if (!width || !height || width > 16384 || height > 16384 || stride > 65536 ||
      stride < width * 4 || (format != WL_SHM_FORMAT_XRGB8888 && format != WL_SHM_FORMAT_ARGB8888)) exit(1);
  probe->format = format; probe->width = width; probe->height = height; probe->stride = stride;
  probe->size = (size_t)stride * height;
  int fd = memfd_create("nextspace-capture-probe", MFD_CLOEXEC);
  if (fd < 0 || ftruncate(fd, probe->size)) exit(1);
  probe->pixels = mmap(NULL, probe->size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
  if (probe->pixels == MAP_FAILED) exit(1);
  struct wl_shm_pool *pool = wl_shm_create_pool(probe->shm, fd, probe->size);
  probe->buffer = wl_shm_pool_create_buffer(pool, 0, width, height, stride, format);
  wl_shm_pool_destroy(pool); close(fd);
}
static void flags(void *data, struct zwlr_screencopy_frame_v1 *frame, uint32_t value)
{ ((struct probe *)data)->flags = value; }
static void ready(void *data, struct zwlr_screencopy_frame_v1 *frame,
    uint32_t seconds_hi, uint32_t seconds_lo, uint32_t nanoseconds)
{
  struct probe *probe = data;
  FILE *file = fopen(probe->path, "wb");
  if (!file || fwrite(probe->pixels, 1, probe->size, file) != probe->size || fclose(file)) exit(1);
  printf("{\"event\":\"frame\",\"width\":%u,\"height\":%u,\"stride\":%u,\"format\":%u,\"flags\":%u}\n",
    probe->width, probe->height, probe->stride, probe->format, probe->flags); fflush(stdout);
  finish_frame(probe);
}
static void failed(void *data, struct zwlr_screencopy_frame_v1 *frame)
{ finish_frame(data); puts("{\"event\":\"failed\"}"); fflush(stdout); }
static void damage(void *data, struct zwlr_screencopy_frame_v1 *frame,
    uint32_t x, uint32_t y, uint32_t width, uint32_t height) {}
static void dmabuf(void *data, struct zwlr_screencopy_frame_v1 *frame,
    uint32_t format, uint32_t width, uint32_t height) {}
static void buffer_done(void *data, struct zwlr_screencopy_frame_v1 *frame)
{
  struct probe *probe = data;
  if (!probe->buffer) { failed(data, frame); return; }
  zwlr_screencopy_frame_v1_copy(frame, probe->buffer);
}
static const struct zwlr_screencopy_frame_v1_listener frame_listener = {
  .buffer = buffer, .flags = flags, .ready = ready, .failed = failed,
  .damage = damage, .linux_dmabuf = dmabuf, .buffer_done = buffer_done
};
static void geometry(void *data, struct wl_output *output, int32_t x, int32_t y,
    int32_t width, int32_t height, int32_t subpixel, const char *make, const char *model, int32_t transform) {}
static void mode(void *data, struct wl_output *output, uint32_t flags, int32_t width, int32_t height, int32_t refresh) {}
static void done(void *data, struct wl_output *output) {}
static void scale(void *data, struct wl_output *output, int32_t factor) {}
static void name(void *data, struct wl_output *output, const char *value)
{ snprintf(((struct output *)data)->name, 128, "%s", value); }
static void description(void *data, struct wl_output *output, const char *value) {}
static const struct wl_output_listener output_listener = {
  .geometry = geometry, .mode = mode, .done = done, .scale = scale, .name = name, .description = description
};
static void global(void *data, struct wl_registry *registry, uint32_t id, const char *interface, uint32_t version)
{
  struct probe *probe = data;
  if (!strcmp(interface, "wl_shm")) probe->shm = wl_registry_bind(registry, id, &wl_shm_interface, 1);
  if (!strcmp(interface, "zwlr_screencopy_manager_v1")) {
    probe->manager_global = id;
    probe->manager = wl_registry_bind(registry, id, &zwlr_screencopy_manager_v1_interface, 3);
  }
  if (!strcmp(interface, "wl_output") && probe->output_count < 32) {
    struct output *output = &probe->outputs[probe->output_count++];
    output->object = wl_registry_bind(registry, id, &wl_output_interface, version < 4 ? version : 4);
    wl_output_add_listener(output->object, &output_listener, output);
  }
}
static void removed(void *data, struct wl_registry *registry, uint32_t id) {}
static const struct wl_registry_listener registry_listener = {.global = global, .global_remove = removed};

int main(int argc, char **argv)
{
  struct probe probe = {0};
  probe.display = wl_display_connect(NULL);
  if (!probe.display) return 1;
  struct wl_registry *registry = wl_display_get_registry(probe.display);
  wl_registry_add_listener(registry, &registry_listener, &probe);
  if (wl_display_roundtrip(probe.display) < 0 || wl_display_roundtrip(probe.display) < 0) return 2;
  if (argc == 3 && !strcmp(argv[1], "--bind")) {
    wl_registry_bind(registry, strtoul(argv[2], NULL, 10), &zwlr_screencopy_manager_v1_interface, 3);
    int result = wl_display_roundtrip(probe.display);
    wl_display_disconnect(probe.display); return result < 0 ? 2 : 0;
  }
  printf("{\"event\":\"ready\",\"pid\":%ld,\"manager_visible\":%s,\"global\":%u,\"fd_cloexec\":%s,\"socket_environment\":%s}\n",
    (long)getpid(), probe.manager ? "true" : "false", probe.manager_global,
    fcntl(wl_display_get_fd(probe.display), F_GETFD) & FD_CLOEXEC ? "true" : "false",
    getenv("WAYLAND_SOCKET") ? "true" : "false"); fflush(stdout);
  if (argc == 2 && !strcmp(argv[1], "--registry")) { wl_display_disconnect(probe.display); return 0; }
  setvbuf(stdin, NULL, _IONBF, 0);
  for (;;) {
    if (wl_display_dispatch_pending(probe.display) < 0 || wl_display_flush(probe.display) < 0) break;
    struct pollfd fds[] = {{wl_display_get_fd(probe.display), POLLIN, 0},
      {argc == 2 && !strcmp(argv[1], "--daemon") ? -1 : STDIN_FILENO, POLLIN, 0}};
    if (poll(fds, 2, -1) < 0) break;
    if (fds[0].revents && wl_display_dispatch(probe.display) < 0) break;
    if (fds[1].revents) {
      char line[1280], output_name[128], extra;
      if (!fgets(line, sizeof(line), stdin) || !strcmp(line, "quit\n")) {
        finish_frame(&probe); wl_display_disconnect(probe.display); return 0;
      }
      if (!strcmp(line, "sync\n")) {
        if (wl_display_roundtrip(probe.display) < 0) break;
        puts("{\"event\":\"sync\"}"); fflush(stdout);
      } else if (!probe.frame && probe.manager &&
          (sscanf(line, "capture %127s %1023s %c", output_name, probe.path, &extra) == 2 ||
           sscanf(line, "capture-cursor %127s %1023s %c", output_name, probe.path, &extra) == 2)) {
        struct wl_output *output = NULL;
        for (size_t i = 0; i < probe.output_count; i++)
          if (!strcmp(probe.outputs[i].name, output_name)) output = probe.outputs[i].object;
        if (!output) return 1;
        probe.flags = 0;
        probe.frame = zwlr_screencopy_manager_v1_capture_output(probe.manager,
          strncmp(line, "capture-cursor ", 15) == 0, output);
        zwlr_screencopy_frame_v1_add_listener(probe.frame, &frame_listener, &probe);
      }
    }
  }
  finish_frame(&probe); wl_display_disconnect(probe.display); return 2;
}
