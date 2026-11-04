/* Independent ordinary client for the interactive color-pick extension. MIT. */
struct color_pick_probe {
  struct wl_pointer *pointer;
  struct wl_keyboard *keyboard;
  uint32_t enter_serial, release_serial;
};

static void pick_result(void *data, struct nextspace_window_v1 *window,
    uint32_t id, uint32_t phase, uint32_t red, uint32_t green, uint32_t blue)
{
  printf("{\"event\":\"pick\",\"id\":%u,\"phase\":%u,\"rgb\":[%u,%u,%u]}\n",
    id, phase, red, green, blue); fflush(stdout);
}
static const struct nextspace_window_v1_listener pick_window_listener = {
  .position = position, .preferred_output = preferred, .closed = closed,
  .minimized = minimized, .color_pick = pick_result
};

static void pick_enter(void *data, struct wl_pointer *pointer, uint32_t serial,
    struct wl_surface *surface, wl_fixed_t x, wl_fixed_t y)
{ ((struct color_pick_probe *)data)->enter_serial = serial; }
static void pick_button(void *data, struct wl_pointer *pointer, uint32_t serial,
    uint32_t time, uint32_t button, uint32_t state)
{
  if (button == 0x110 && state == WL_POINTER_BUTTON_STATE_RELEASED)
    ((struct color_pick_probe *)data)->release_serial = serial;
  printf("{\"event\":\"button\",\"serial\":%u,\"button\":%u,\"state\":%u}\n", serial, button, state);
  fflush(stdout);
}
static const struct wl_pointer_listener pick_pointer_listener = {
  .enter = pick_enter, .leave = empty_leave, .motion = empty_motion,
  .button = pick_button, .axis = empty_axis
};
static void pick_keymap(void *data, struct wl_keyboard *keyboard, uint32_t format, int fd, uint32_t size)
{ close(fd); }
static void pick_keyboard_enter(void *data, struct wl_keyboard *keyboard, uint32_t serial,
    struct wl_surface *surface, struct wl_array *keys) {}
static void pick_keyboard_leave(void *data, struct wl_keyboard *keyboard, uint32_t serial, struct wl_surface *surface) {}
static void pick_key(void *data, struct wl_keyboard *keyboard, uint32_t serial,
    uint32_t time, uint32_t key, uint32_t state)
{
  printf("{\"event\":\"key\",\"serial\":%u,\"key\":%u,\"state\":%u}\n",serial,key,state); fflush(stdout);
}
static void pick_modifiers(void *data, struct wl_keyboard *keyboard, uint32_t serial,
    uint32_t depressed, uint32_t latched, uint32_t locked, uint32_t group) {}
static const struct wl_keyboard_listener pick_keyboard_listener = {
  .keymap=pick_keymap, .enter=pick_keyboard_enter, .leave=pick_keyboard_leave,
  .key=pick_key, .modifiers=pick_modifiers
};
static void pick_capabilities(void *data, struct wl_seat *seat, uint32_t capabilities)
{
  struct color_pick_probe *probe = data;
  if ((capabilities & WL_SEAT_CAPABILITY_POINTER) && !probe->pointer) {
    probe->pointer = wl_seat_get_pointer(seat);
    wl_pointer_add_listener(probe->pointer, &pick_pointer_listener, probe);
  }
  if ((capabilities & WL_SEAT_CAPABILITY_KEYBOARD) && !probe->keyboard) {
    probe->keyboard = wl_seat_get_keyboard(seat);
    wl_keyboard_add_listener(probe->keyboard,&pick_keyboard_listener,probe);
  }
}
static const struct wl_seat_listener pick_seat_listener = {.capabilities = pick_capabilities};

static int test_color_pick(struct globals *globals)
{
  if (!globals->seat || !globals->application || nextspace_application_v1_get_version(globals->application) < 8) return 1;
  struct wl_display *display = globals->display;
  struct color_pick_probe probe = {0};
  wl_seat_add_listener(globals->seat, &pick_seat_listener, &probe);
  struct test_window window = {0};
  if (!create_window(globals, &window, "ColorPickProbe")) return 1;
  struct nextspace_window_v1 *object = nextspace_application_v1_get_window(globals->application, window.surface);
  nextspace_window_v1_add_listener(object, &pick_window_listener, &window);
  if (globals->focus_mode) nextspace_window_v1_set_accepts_focus(object, 0);
  nextspace_window_v1_set_position(object, 40, 40);
  wl_surface_commit(window.surface);
  while (!window.positioned || !probe.pointer)
    if (wl_display_dispatch(display) < 0) return 1;
  puts("{\"event\":\"ready\"}"); fflush(stdout);
  setvbuf(stdin, NULL, _IONBF, 0);
  bool running = true;
  while (running && wl_display_dispatch_pending(display) >= 0) {
    wl_display_flush(display);
    struct pollfd fds[] = {{.fd = wl_display_get_fd(display), .events = POLLIN},
      {.fd = STDIN_FILENO, .events = POLLIN}};
    if (poll(fds, 2, -1) < 0) break;
    if (fds[0].revents && wl_display_dispatch(display) < 0) break;
    if (!(fds[1].revents & (POLLIN | POLLHUP))) continue;
    char command[256], extra; unsigned id, serial, argb;
    if (!fgets(command, sizeof(command), stdin)) break;
    if (sscanf(command, "begin %u %u %c", &id, &serial, &extra) == 2 && object)
      nextspace_window_v1_begin_color_pick(object, id, serial);
    else if (sscanf(command, "begin-last %u %c", &id, &extra) == 1 && object)
      nextspace_window_v1_begin_color_pick(object, id, probe.release_serial);
    else if (sscanf(command, "cancel %u %c", &id, &extra) == 1 && object)
      nextspace_window_v1_cancel_color_pick(object, id);
    else if (sscanf(command, "color %x %c", &argb, &extra) == 1) {
      for (int i = 0; i < 64 * 64; i++) ((uint32_t *)window.pixels)[i] = argb;
      wl_surface_damage(window.surface, 0, 0, 64, 64); wl_surface_commit(window.surface);
    } else if (strcmp(command, "hide-cursor\n") == 0)
      wl_pointer_set_cursor(probe.pointer, probe.enter_serial, NULL, 0, 0);
    else if (strcmp(command, "unmap\n") == 0) {
      wl_surface_attach(window.surface, NULL, 0, 0); wl_surface_commit(window.surface);
    } else if (strcmp(command, "destroy\n") == 0 && object) {
      nextspace_window_v1_destroy(object); object = NULL;
    } else if (strcmp(command, "sync\n") == 0) {
      if (wl_display_roundtrip(display) < 0) break;
      puts("{\"event\":\"sync\"}"); fflush(stdout);
    } else if (strcmp(command, "quit\n") == 0) running = false;
    else { fprintf(stderr, "Unknown color-pick command: %s", command); return 1; }
  }
  if (object) nextspace_window_v1_destroy(object);
  destroy_window(&window);
  wl_display_roundtrip(display);
  return 0;
}
