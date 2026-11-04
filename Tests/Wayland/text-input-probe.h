/* Independent text client/input method modes of registry-probe. MIT license. */
struct text_probe {
  struct globals *globals;
  struct zwp_text_input_v3 *text;
  struct zwp_input_method_v2 *method;
  struct zwp_input_method_keyboard_grab_v2 *grab;
  struct zwp_virtual_keyboard_v1 *keyboard;
  struct test_window window, popup;
  struct zwp_input_popup_surface_v2 *popup_role;
  uint32_t serial;
};

static void text_bytes(const char *name, const char *value)
{
  printf("{\"event\":\"%s\",\"hex\":\"", name);
  if (value) for (const unsigned char *p = (const unsigned char *)value; *p; p++) printf("%02x", *p);
  puts("\"}");
}
static void text_enter(void *data, struct zwp_text_input_v3 *text, struct wl_surface *surface)
{ puts("{\"event\":\"enter\"}"); }
static void text_leave(void *data, struct zwp_text_input_v3 *text, struct wl_surface *surface)
{ puts("{\"event\":\"leave\"}"); }
static void text_preedit(void *data, struct zwp_text_input_v3 *text, const char *value, int32_t begin, int32_t end)
{
  text_bytes("preedit", value);
  printf("{\"event\":\"preedit-cursor\",\"begin\":%d,\"end\":%d}\n", begin, end);
}
static void text_commit(void *data, struct zwp_text_input_v3 *text, const char *value)
{ text_bytes("commit", value); }
static void text_delete(void *data, struct zwp_text_input_v3 *text, uint32_t before, uint32_t after)
{ printf("{\"event\":\"delete\",\"before\":%u,\"after\":%u}\n", before, after); }
static void text_done(void *data, struct zwp_text_input_v3 *text, uint32_t serial)
{ printf("{\"event\":\"done\",\"serial\":%u}\n", serial); }
static const struct zwp_text_input_v3_listener text_listener = {
  .enter = text_enter, .leave = text_leave, .preedit_string = text_preedit,
  .commit_string = text_commit, .delete_surrounding_text = text_delete, .done = text_done
};
static void method_activate(void *data, struct zwp_input_method_v2 *method)
{ puts("{\"event\":\"activate\"}"); }
static void method_deactivate(void *data, struct zwp_input_method_v2 *method)
{ puts("{\"event\":\"deactivate\"}"); }
static void method_surrounding(void *data, struct zwp_input_method_v2 *method, const char *text, uint32_t cursor, uint32_t anchor)
{
  text_bytes("surrounding", text);
  printf("{\"event\":\"selection\",\"cursor\":%u,\"anchor\":%u}\n", cursor, anchor);
}
static void method_cause(void *data, struct zwp_input_method_v2 *method, uint32_t cause)
{ printf("{\"event\":\"cause\",\"cause\":%u}\n", cause); }
static void method_content(void *data, struct zwp_input_method_v2 *method, uint32_t hint, uint32_t purpose)
{ printf("{\"event\":\"content\",\"hint\":%u,\"purpose\":%u}\n", hint, purpose); }
static void method_done(void *data, struct zwp_input_method_v2 *method)
{ struct text_probe *probe = data; printf("{\"event\":\"done\",\"serial\":%u}\n", ++probe->serial); }
static void method_unavailable(void *data, struct zwp_input_method_v2 *method)
{ puts("{\"event\":\"unavailable\"}"); }
static const struct zwp_input_method_v2_listener method_listener = {
  .activate = method_activate, .deactivate = method_deactivate, .surrounding_text = method_surrounding,
  .text_change_cause = method_cause, .content_type = method_content, .done = method_done, .unavailable = method_unavailable
};
static void method_keymap(void *data, struct zwp_input_method_keyboard_grab_v2 *grab, uint32_t format, int fd, uint32_t size)
{
  struct text_probe *probe = data;
  zwp_virtual_keyboard_v1_keymap(probe->keyboard, format, fd, size);
  close(fd); puts("{\"event\":\"keymap\"}");
}
static void method_key(void *data, struct zwp_input_method_keyboard_grab_v2 *grab,
    uint32_t serial, uint32_t time, uint32_t key, uint32_t state)
{ printf("{\"event\":\"key\",\"key\":%u,\"state\":%u}\n", key, state); }
static void method_modifiers(void *data, struct zwp_input_method_keyboard_grab_v2 *grab,
    uint32_t serial, uint32_t depressed, uint32_t latched, uint32_t locked, uint32_t group)
{ puts("{\"event\":\"modifiers\"}"); }
static void method_repeat(void *data, struct zwp_input_method_keyboard_grab_v2 *grab, int32_t rate, int32_t delay) {}
static const struct zwp_input_method_keyboard_grab_v2_listener method_keyboard_listener = {
  .keymap = method_keymap, .key = method_key, .modifiers = method_modifiers, .repeat_info = method_repeat
};
static void text_key(void *data, struct wl_keyboard *keyboard, uint32_t serial, uint32_t time, uint32_t key, uint32_t state)
{ printf("{\"event\":\"key\",\"key\":%u,\"state\":%u}\n", key, state); }
static void text_keyboard_enter(void *data, struct wl_keyboard *keyboard, uint32_t serial,
    struct wl_surface *surface, struct wl_array *keys) {}
static void text_keyboard_leave(void *data, struct wl_keyboard *keyboard, uint32_t serial, struct wl_surface *surface) {}
static const struct wl_keyboard_listener text_keyboard_listener = {
  .keymap = activation_keymap, .enter = text_keyboard_enter, .leave = text_keyboard_leave,
  .key = text_key, .modifiers = activation_modifiers
};
static void text_pointer_enter(void *data, struct wl_pointer *pointer, uint32_t serial,
    struct wl_surface *surface, wl_fixed_t x, wl_fixed_t y) {}
static void text_pointer_leave(void *data, struct wl_pointer *pointer, uint32_t serial, struct wl_surface *surface) {}
static void text_pointer_motion(void *data, struct wl_pointer *pointer, uint32_t time, wl_fixed_t x, wl_fixed_t y) {}
static void text_pointer_button(void *data, struct wl_pointer *pointer, uint32_t serial,
    uint32_t time, uint32_t button, uint32_t state)
{ printf("{\"event\":\"button\",\"state\":%u}\n", state); }
static void text_pointer_axis(void *data, struct wl_pointer *pointer, uint32_t time, uint32_t axis, wl_fixed_t value) {}
static const struct wl_pointer_listener text_pointer_listener = {
  .enter = text_pointer_enter, .leave = text_pointer_leave, .motion = text_pointer_motion,
  .button = text_pointer_button, .axis = text_pointer_axis
};
static void popup_rectangle(void *data, struct zwp_input_popup_surface_v2 *popup, int32_t x, int32_t y, int32_t width, int32_t height)
{ printf("{\"event\":\"rectangle\",\"x\":%d,\"y\":%d,\"width\":%d,\"height\":%d}\n", x, y, width, height); }
static const struct zwp_input_popup_surface_v2_listener popup_listener = {.text_input_rectangle = popup_rectangle};

static int test_text_input(struct globals *globals)
{
  setvbuf(stdout, NULL, _IOLBF, 0); setvbuf(stdin, NULL, _IONBF, 0);
  struct text_probe probe = {.globals = globals};
  if (!globals->seat) return 1;
  if (globals->text_mode) {
    if (!globals->text_manager || globals->method_global || globals->virtual_manager) return 1;
    probe.text = zwp_text_input_manager_v3_get_text_input(globals->text_manager, globals->seat);
    zwp_text_input_v3_add_listener(probe.text, &text_listener, &probe);
    struct wl_keyboard *keyboard = wl_seat_get_keyboard(globals->seat);
    wl_keyboard_add_listener(keyboard, &text_keyboard_listener, &probe);
    struct wl_pointer *pointer = wl_seat_get_pointer(globals->seat);
    wl_pointer_add_listener(pointer, &text_pointer_listener, &probe);
    if (!create_window(globals, &probe.window, "TextInputProbe")) return 1;
    wl_surface_commit(probe.window.surface);
  } else {
    if (!globals->method_manager || !globals->virtual_manager) return 1;
    probe.method = zwp_input_method_manager_v2_get_input_method(globals->method_manager, globals->seat);
    zwp_input_method_v2_add_listener(probe.method, &method_listener, &probe);
    probe.keyboard = zwp_virtual_keyboard_manager_v1_create_virtual_keyboard(globals->virtual_manager, globals->seat);
  }
  printf("{\"event\":\"ready\",\"global\":%u,\"pid\":%d}\n", globals->method_global, getpid());
  for (;;) {
    if (wl_display_dispatch_pending(globals->display) < 0 || wl_display_flush(globals->display) < 0) return 1;
    struct pollfd descriptors[] = {{wl_display_get_fd(globals->display), POLLIN, 0}, {STDIN_FILENO, POLLIN, 0}};
    if (poll(descriptors, globals->method_daemon ? 1 : 2, -1) < 0) { if (errno == EINTR) continue; return 1; }
    if (descriptors[0].revents && wl_display_dispatch(globals->display) < 0) return 1;
    if (!descriptors[1].revents) continue;
    char line[4096];
    if (!fgets(line, sizeof(line), stdin)) return 0;
    line[strcspn(line, "\n")] = 0;
    if (!strcmp(line, "quit")) return 0;
    if (!strcmp(line, "sync")) {
      if (wl_display_roundtrip(globals->display) < 0) return 1;
      puts("{\"event\":\"sync\"}"); continue;
    }
    if (probe.text) {
      int cursor, anchor, x, y, width, height, offset = 0;
      unsigned hint, purpose;
      if (!strcmp(line, "enable")) {
        zwp_text_input_v3_enable(probe.text);
        zwp_text_input_v3_set_surrounding_text(probe.text, "hello日本", 11, 5);
        zwp_text_input_v3_set_content_type(probe.text, 0, 0);
        zwp_text_input_v3_set_cursor_rectangle(probe.text, 12, 14, 2, 18);
        zwp_text_input_v3_commit(probe.text);
      } else if (!strcmp(line, "disable")) {
        zwp_text_input_v3_disable(probe.text); zwp_text_input_v3_commit(probe.text);
      } else if (sscanf(line, "content %u %u", &hint, &purpose) == 2) {
        zwp_text_input_v3_set_content_type(probe.text, hint, purpose);
        zwp_text_input_v3_commit(probe.text);
      } else if (sscanf(line, "rectangle %d %d %d %d", &x, &y, &width, &height) == 4) {
        zwp_text_input_v3_set_cursor_rectangle(probe.text, x, y, width, height);
        zwp_text_input_v3_commit(probe.text);
      } else if (sscanf(line, "state %d %d %d %d %d %d %n", &cursor, &anchor, &x, &y, &width, &height, &offset) == 6 && offset) {
        zwp_text_input_v3_set_surrounding_text(probe.text, line + offset, cursor, anchor);
        zwp_text_input_v3_set_cursor_rectangle(probe.text, x, y, width, height);
        zwp_text_input_v3_commit(probe.text);
      } else return 2;
    } else {
      int begin, end, offset = 0;
      unsigned before, after, key, state, serial;
      if (!strncmp(line, "commit ", 7)) zwp_input_method_v2_commit_string(probe.method, line + 7);
      else if (sscanf(line, "preedit %d %d %n", &begin, &end, &offset) == 2 && offset)
        zwp_input_method_v2_set_preedit_string(probe.method, line + offset, begin, end);
      else if (sscanf(line, "delete %u %u", &before, &after) == 2)
        zwp_input_method_v2_delete_surrounding_text(probe.method, before, after);
      else if (!strcmp(line, "done")) zwp_input_method_v2_commit(probe.method, probe.serial);
      else if (sscanf(line, "done %u", &serial) == 1) zwp_input_method_v2_commit(probe.method, serial);
      else if (!strcmp(line, "grab")) {
        probe.grab = zwp_input_method_v2_grab_keyboard(probe.method);
        zwp_input_method_keyboard_grab_v2_add_listener(probe.grab, &method_keyboard_listener, &probe);
      } else if (sscanf(line, "forward %u %u", &key, &state) == 2)
        zwp_virtual_keyboard_v1_key(probe.keyboard, 1, key, state);
      else if (!strcmp(line, "popup")) {
        if (!create_surface(globals, &probe.popup)) return 1;
        probe.popup_role = zwp_input_method_v2_get_input_popup_surface(probe.method, probe.popup.surface);
        zwp_input_popup_surface_v2_add_listener(probe.popup_role, &popup_listener, &probe);
        wl_surface_attach(probe.popup.surface, probe.popup.buffer, 0, 0);
        wl_surface_damage(probe.popup.surface, 0, 0, 64, 64); wl_surface_commit(probe.popup.surface);
      } else return 2;
    }
  }
}
