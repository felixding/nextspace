/* Independent shell protocol driver. SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include <wayland-client.h>
#include "nextspace-shell-v1-client-protocol.h"
#include <errno.h>
#include <poll.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct probe { struct nextspace_shell_v1 *shell; uint32_t global, version;
  struct nextspace_output_configuration_v1 *configuration; uint32_t input_serial; };
static void quoted(const char *value)
{
  putchar('"');
  for (const unsigned char *p = (const unsigned char *)value; *p; p++) {
    if (*p == '"' || *p == '\\') { putchar('\\'); putchar(*p); }
    else if (*p < 32) printf("\\u%04x", *p);
    else putchar(*p);
  }
  putchar('"');
}
static void reset(void *data, struct nextspace_shell_v1 *shell) { puts("{\"event\":\"reset\"}"); }
static void window(void *data, struct nextspace_shell_v1 *shell, uint32_t id,
    const char *app_id, const char *title, int32_t pid, uint32_t flags,
    int32_t x, int32_t y, int32_t width, int32_t height)
{
  printf("{\"event\":\"window\",\"id\":%u,\"app_id\":", id); quoted(app_id);
  printf(",\"title\":"); quoted(title);
  printf(",\"pid\":%d,\"flags\":%u,\"x\":%d,\"y\":%d,\"width\":%d,\"height\":%d}\n",
    pid, flags, x, y, width, height);
}
static void closed(void *data, struct nextspace_shell_v1 *shell, uint32_t id)
{ printf("{\"event\":\"closed\",\"id\":%u}\n", id); }
static void done(void *data, struct nextspace_shell_v1 *shell) { puts("{\"event\":\"done\"}"); }
static void window_info(void *data, struct nextspace_shell_v1 *shell, uint32_t id,
    uint32_t client_id, uint32_t style, uint32_t title_height, int32_t level)
{
  printf("{\"event\":\"window-info\",\"id\":%u,\"client_id\":%u,\"style\":%u,\"title_height\":%u,\"level\":%d}\n",
    id, client_id, style, title_height, level);
}
static void pointer_focus(void *data, struct nextspace_shell_v1 *shell, uint32_t id)
{ printf("{\"event\":\"pointer-focus\",\"id\":%u}\n", id); }
static void outputs_reset(void *data, struct nextspace_shell_v1 *shell, uint32_t revision)
{ printf("{\"event\":\"outputs-reset\",\"revision\":%u}\n", revision); }
static void output(void *data, struct nextspace_shell_v1 *shell, uint32_t id, const char *name,
    uint32_t enabled, uint32_t primary, int32_t width, int32_t height, int32_t refresh,
    uint32_t scale, uint32_t transform, int32_t x, int32_t y, int32_t logical_width, int32_t logical_height)
{
  printf("{\"event\":\"output\",\"id\":%u,\"name\":", id); quoted(name);
  printf(",\"enabled\":%u,\"primary\":%u,\"width\":%d,\"height\":%d,\"refresh\":%d,"
    "\"scale\":%u,\"transform\":%u,\"x\":%d,\"y\":%d,\"logical_width\":%d,\"logical_height\":%d}\n",
    enabled, primary, width, height, refresh, scale, transform, x, y, logical_width, logical_height);
}
static void output_identity(void *data, struct nextspace_shell_v1 *shell, uint32_t id,
    const char *make, const char *model, const char *serial, int32_t width_mm, int32_t height_mm)
{
  printf("{\"event\":\"output-identity\",\"id\":%u,\"make\":", id); quoted(make);
  printf(",\"model\":"); quoted(model); printf(",\"serial\":"); quoted(serial);
  printf(",\"width_mm\":%d,\"height_mm\":%d}\n", width_mm, height_mm);
}
static void output_mode(void *data, struct nextspace_shell_v1 *shell, uint32_t id,
    int32_t width, int32_t height, int32_t refresh, uint32_t preferred)
{
  printf("{\"event\":\"output-mode\",\"id\":%u,\"width\":%d,\"height\":%d,\"refresh\":%d,\"preferred\":%u}\n",
    id, width, height, refresh, preferred);
}
static void outputs_done(void *data, struct nextspace_shell_v1 *shell)
{ puts("{\"event\":\"outputs-done\"}"); }
static void configuration_result(void *data, struct nextspace_output_configuration_v1 *config,
    uint32_t status, const char *reason)
{
  printf("{\"event\":\"configuration-result\",\"status\":%u,\"reason\":", status);
  quoted(reason); puts("}");
}
static const struct nextspace_output_configuration_v1_listener configuration_listener = {
  .result = configuration_result
};
static void input_settings(void *data, struct nextspace_shell_v1 *shell, const char *model,
    const char *layout, const char *variant, const char *options, uint32_t delay, uint32_t rate,
    uint32_t numlock, wl_fixed_t speed, uint32_t profile, uint32_t devices)
{
  printf("{\"event\":\"input-settings\",\"model\":"); quoted(model);
  printf(",\"layout\":"); quoted(layout); printf(",\"variant\":"); quoted(variant);
  printf(",\"options\":"); quoted(options);
  printf(",\"delay\":%u,\"rate\":%u,\"numlock\":%u,\"speed\":%.6f,\"profile\":%u,\"accelerated_devices\":%u}\n",
    delay, rate, numlock, wl_fixed_to_double(speed), profile, devices);
}
static void input_result(void *data, struct nextspace_shell_v1 *shell, uint32_t serial,
    uint32_t success, const char *reason)
{
  printf("{\"event\":\"input-result\",\"serial\":%u,\"success\":%s,\"reason\":", serial, success ? "true" : "false");
  quoted(reason); puts("}");
}
static void background(void *data, struct nextspace_shell_v1 *shell, wl_fixed_t red, wl_fixed_t green, wl_fixed_t blue)
{
  printf("{\"event\":\"background\",\"Red\":%.8f,\"Green\":%.8f,\"Blue\":%.8f}\n",
    wl_fixed_to_double(red), wl_fixed_to_double(green), wl_fixed_to_double(blue));
}
static void desktops(void *data, struct nextspace_shell_v1 *shell, uint32_t current, uint32_t count)
{ printf("{\"event\":\"desktops\",\"current\":%u,\"count\":%u}\n", current, count); }
static void window_desktop(void *data, struct nextspace_shell_v1 *shell, uint32_t id, uint32_t index, uint32_t sticky)
{ printf("{\"event\":\"window-desktop\",\"id\":%u,\"desktop\":%u,\"sticky\":%s}\n", id, index, sticky ? "true" : "false"); }
static void interactive_move(void *data, struct nextspace_shell_v1 *shell, uint32_t id,
    uint32_t phase, int32_t x, int32_t y, int32_t screen_x, int32_t screen_y, int32_t width, int32_t height)
{
  printf("{\"event\":\"interactive-move\",\"id\":%u,\"phase\":%u,\"x\":%d,\"y\":%d,"
    "\"screen_x\":%d,\"screen_y\":%d,\"screen_width\":%d,\"screen_height\":%d}\n",
    id, phase, x, y, screen_x, screen_y, width, height);
}
static void output_work_area(void *data, struct nextspace_shell_v1 *shell, uint32_t id,
    int32_t x, int32_t y, int32_t width, int32_t height)
{
  printf("{\"event\":\"output-work-area\",\"id\":%u,\"work_x\":%d,\"work_y\":%d,\"work_width\":%d,\"work_height\":%d}\n",
    id, x, y, width, height);
}
static void output_gamma(void *data, struct nextspace_shell_v1 *shell, uint32_t id, uint32_t size,
    wl_fixed_t red, wl_fixed_t green, wl_fixed_t blue, wl_fixed_t brightness)
{
  printf("{\"event\":\"output-gamma\",\"id\":%u,\"size\":%u,\"red\":%.8f,\"green\":%.8f,\"blue\":%.8f,\"brightness\":%.8f}\n",
    id, size, wl_fixed_to_double(red), wl_fixed_to_double(green), wl_fixed_to_double(blue), wl_fixed_to_double(brightness));
}
static void output_gamma_result(void *data, struct nextspace_shell_v1 *shell,
    uint32_t serial, uint32_t success, const char *reason)
{
  printf("{\"event\":\"gamma-result\",\"serial\":%u,\"success\":%u,\"reason\":\"%s\"}\n", serial, success, reason);
}
static const struct nextspace_shell_v1_listener shell_listener = {
  .reset = reset, .window = window, .closed = closed, .done = done, .window_info = window_info, .pointer_focus = pointer_focus,
  .outputs_reset = outputs_reset, .output = output, .output_identity = output_identity,
  .output_mode = output_mode, .outputs_done = outputs_done,
  .input_settings = input_settings, .input_result = input_result, .background = background,
  .desktops = desktops, .window_desktop = window_desktop, .interactive_move = interactive_move,
  .output_work_area = output_work_area, .output_gamma = output_gamma,
  .output_gamma_result = output_gamma_result
};
static void global(void *data, struct wl_registry *registry, uint32_t name,
    const char *interface, uint32_t version)
{
  struct probe *probe = data;
  if (strcmp(interface, "nextspace_shell_v1") != 0) return;
  probe->global = name;
  probe->shell = wl_registry_bind(registry, name, &nextspace_shell_v1_interface,
    version < probe->version ? version : probe->version);
  nextspace_shell_v1_add_listener(probe->shell, &shell_listener, probe);
}
static void removed(void *data, struct wl_registry *registry, uint32_t name) {}
static const struct wl_registry_listener registry_listener = {.global = global, .global_remove = removed};

int main(int argc, char **argv)
{
  setvbuf(stdout, NULL, _IOLBF, 0);
  setvbuf(stdin, NULL, _IONBF, 0);
  struct wl_display *display = wl_display_connect(NULL);
  if (!display) return 1;
  unsigned version = argc == 2 && strncmp(argv[1], "--version", 9) == 0 ? atoi(argv[1] + 9) : 4;
  if (version < 1 || version > 18) return 1;
  struct probe probe = {.version = version};
  struct wl_registry *registry = wl_display_get_registry(display);
  wl_registry_add_listener(registry, &registry_listener, &probe);
  if (wl_display_roundtrip(display) < 0) return 1;
  if (argc == 3 && strcmp(argv[1], "--guess") == 0) {
    struct nextspace_shell_v1 *object = wl_registry_bind(registry,
      strtoul(argv[2], NULL, 10), &nextspace_shell_v1_interface, 1);
    bool rejected = wl_display_roundtrip(display) < 0 && wl_display_get_error(display) == EPROTO;
    wl_proxy_destroy((struct wl_proxy *)object);
    wl_display_disconnect(display);
    return rejected ? 0 : 1;
  }
  if (!probe.shell) { wl_display_disconnect(display); return 2; }
  if (wl_display_roundtrip(display) < 0) return 1;
  printf("{\"event\":\"ready\",\"global\":%u}\n", probe.global);
  char *line = NULL; size_t capacity = 0;
  int result = 0;
  while (wl_display_dispatch_pending(display) >= 0) {
    if (wl_display_flush(display) < 0 && errno != EAGAIN) { result = 3; break; }
    struct pollfd fds[] = {{wl_display_get_fd(display), POLLIN, 0}, {0, POLLIN, 0}};
    if (poll(fds, 2, -1) < 0) { if (errno == EINTR) continue; result = 1; break; }
    if (fds[0].revents && wl_display_dispatch(display) < 0) { result = 3; break; }
    if (fds[1].revents) {
      if (getline(&line, &capacity, stdin) < 0) break;
      unsigned id, enabled, primary, scale, transform; int x, y, width, height, refresh;
      char model[1025], layout[1025], variant[1025], options[1025], title_font[4097]; double speed, red, green, blue, brightness;
      if (strcmp(line, "snapshot\n") == 0) nextspace_shell_v1_snapshot(probe.shell);
      else if (sscanf(line, "gamma %u %u %lf %lf %lf %lf", &primary, &id, &red, &green, &blue, &brightness) == 6 && version >= 18)
        nextspace_shell_v1_set_output_gamma(probe.shell, primary, id, wl_fixed_from_double(red),
          wl_fixed_from_double(green), wl_fixed_from_double(blue), wl_fixed_from_double(brightness));
      else if (strcmp(line, "lock\n") == 0 && version >= 17) nextspace_shell_v1_lock(probe.shell);
      else if (sscanf(line, "insets %u %d %d %d %d", &id, &x, &y, &width, &height) == 5 && version >= 13)
        nextspace_shell_v1_set_output_insets(probe.shell, id, x, y, width, height);
      else if (sscanf(line, "maximized-drag %u", &id) == 1 && version >= 14)
        nextspace_shell_v1_set_maximized_drag_mode(probe.shell, id);
      else if (sscanf(line, "double-click-time %u", &id) == 1 && version >= 15)
        nextspace_shell_v1_set_double_click_time(probe.shell, id);
      else if (sscanf(line, "title-appearance %u %u %4096[^\n]", &id, &primary, title_font) == 3 && version >= 16)
        nextspace_shell_v1_set_title_appearance(probe.shell, title_font, id, primary);
      else if (sscanf(line, "cancel-move %u", &id) == 1 && version >= 11) nextspace_shell_v1_cancel_move(probe.shell, id);
      else if (sscanf(line, "activate %u", &id) == 1) nextspace_shell_v1_activate(probe.shell, id);
      else if (sscanf(line, "close %u", &id) == 1) nextspace_shell_v1_close(probe.shell, id);
      else if (sscanf(line, "move %u %d %d", &id, &x, &y) == 3)
        nextspace_shell_v1_move(probe.shell, id, x, y);
      else if (sscanf(line, "minimize %u %d", &id, &x) == 2)
        nextspace_shell_v1_set_minimized(probe.shell, id, x != 0);
      else if (sscanf(line, "shade %u %d", &id, &x) == 2)
        nextspace_shell_v1_set_shaded(probe.shell, id, x != 0);
      else if (sscanf(line, "present %u %d", &id, &x) == 2)
        nextspace_shell_v1_set_presented(probe.shell, id, x != 0);
      else if (sscanf(line, "level %u %d", &id, &x) == 2)
        nextspace_shell_v1_set_level(probe.shell, id, x);
      else if (sscanf(line, "order %u %d", &id, &x) == 2)
        nextspace_shell_v1_order(probe.shell, id, x != 0);
      else if (strcmp(line, "input\n") == 0) nextspace_shell_v1_input_snapshot(probe.shell);
      else if (sscanf(line, "desktop-count %u", &id) == 1) nextspace_shell_v1_configure_desktops(probe.shell, id);
      else if (sscanf(line, "desktop %u", &id) == 1) nextspace_shell_v1_switch_desktop(probe.shell, id);
      else if (sscanf(line, "window-desktop %u %u %u", &id, &enabled, &primary) == 3)
        nextspace_shell_v1_move_to_desktop(probe.shell, id, enabled, primary);
      else if (strcmp(line, "background\n") == 0) nextspace_shell_v1_background_snapshot(probe.shell);
      else if (sscanf(line, "background %d %d %d", &x, &y, &width) == 3)
        nextspace_shell_v1_set_background(probe.shell, wl_fixed_from_double(x / 1000.0),
          wl_fixed_from_double(y / 1000.0), wl_fixed_from_double(width / 1000.0));
      else if (sscanf(line, "pointer %lf %u", &speed, &id) == 2)
        nextspace_shell_v1_set_pointer(probe.shell, ++probe.input_serial, wl_fixed_from_double(speed), id);
      else if (sscanf(line, "keyboard %1024s %1024s %1024s %1024s %u %u %u", model, layout, variant,
          options, &scale, &enabled, &primary) == 7)
        nextspace_shell_v1_set_keyboard(probe.shell, ++probe.input_serial, model, layout,
          strcmp(variant, "_") == 0 ? "" : variant, strcmp(options, "_") == 0 ? "" : options, scale, enabled, primary);
      else if (strcmp(line, "outputs\n") == 0) nextspace_shell_v1_output_snapshot(probe.shell);
      else if (sscanf(line, "configure %u", &id) == 1) {
        if (probe.configuration) nextspace_output_configuration_v1_destroy(probe.configuration);
        probe.configuration = nextspace_shell_v1_configure_outputs(probe.shell, id);
        nextspace_output_configuration_v1_add_listener(probe.configuration, &configuration_listener, &probe);
      } else if (sscanf(line, "head %u %u %u %d %d %d %u %u %d %d", &id, &enabled, &primary,
          &width, &height, &refresh, &scale, &transform, &x, &y) == 10 && probe.configuration)
        nextspace_output_configuration_v1_set_head(probe.configuration, id, enabled, primary,
          width, height, refresh, scale, transform, x, y);
      else if (strcmp(line, "test\n") == 0 && probe.configuration)
        nextspace_output_configuration_v1_test(probe.configuration);
      else if (sscanf(line, "apply %u", &id) == 1 && probe.configuration)
        nextspace_output_configuration_v1_apply(probe.configuration, id);
      else if (strcmp(line, "confirm\n") == 0 && probe.configuration)
        nextspace_output_configuration_v1_confirm(probe.configuration);
      else if (strcmp(line, "cancel\n") == 0 && probe.configuration)
        nextspace_output_configuration_v1_cancel(probe.configuration);
      else if (strcmp(line, "destroy-config\n") == 0 && probe.configuration) {
        nextspace_output_configuration_v1_destroy(probe.configuration); probe.configuration = NULL;
      } else { result = 1; break; }
    }
  }
  free(line);
  wl_display_disconnect(display);
  return result;
}
