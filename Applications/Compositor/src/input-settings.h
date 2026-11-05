/* Seat settings on the private shell connection. SPDX-License-Identifier: MIT */
struct nextspace_pointer {
  struct wl_list link;
  struct nextspace_server *server;
  struct wlr_input_device *device;
  struct wl_listener destroy;
};

static void input_apply_numlock(struct wlr_keyboard *keyboard, bool enabled)
{
  xkb_mod_index_t index = xkb_keymap_mod_get_index(keyboard->keymap, XKB_MOD_NAME_NUM);
  if (index == XKB_MOD_INVALID || index >= 32) return;
  xkb_mod_mask_t locked = keyboard->modifiers.locked;
  if (enabled) locked |= (1u << index); else locked &= ~(1u << index);
  wlr_keyboard_notify_modifiers(keyboard, keyboard->modifiers.depressed,
    keyboard->modifiers.latched, locked, keyboard->modifiers.group);
}

static bool input_numlock(struct nextspace_server *server)
{
  struct wlr_keyboard *keyboard = wlr_seat_get_keyboard(server->seat);
  if (!keyboard || !keyboard->keymap) return server->input_numlock;
  xkb_mod_index_t index = xkb_keymap_mod_get_index(keyboard->keymap, XKB_MOD_NAME_NUM);
  return index != XKB_MOD_INVALID && index < 32 && (keyboard->modifiers.locked & (1u << index));
}

static struct libinput_device *input_pointer_device(struct nextspace_pointer *pointer)
{
  if (!wlr_input_device_is_libinput(pointer->device)) return NULL;
  struct libinput_device *device = wlr_libinput_get_device_handle(pointer->device);
  return libinput_device_config_accel_is_available(device) ? device : NULL;
}

static void input_snapshot(struct nextspace_server *server)
{
  struct wl_resource *resource = server->shell_resource;
  if (!resource || wl_resource_get_version(resource) < 8) return;
  unsigned count = 0;
  struct nextspace_pointer *pointer;
  wl_list_for_each(pointer, &server->pointers, link) count += input_pointer_device(pointer) != NULL;
  nextspace_shell_v1_send_input_settings(resource, server->input_model, server->input_layout,
    server->input_variant, server->input_options, server->input_delay, server->input_rate,
    input_numlock(server), wl_fixed_from_double(server->pointer_speed), server->pointer_profile, count);
}

static bool input_set_pointer_device(struct libinput_device *device, double speed, uint32_t profile)
{
  enum libinput_config_accel_profile value = profile == 1 ? LIBINPUT_CONFIG_ACCEL_PROFILE_FLAT :
    LIBINPUT_CONFIG_ACCEL_PROFILE_ADAPTIVE;
  return (libinput_device_config_accel_get_profiles(device) & value) &&
    libinput_device_config_accel_set_profile(device, value) == LIBINPUT_CONFIG_STATUS_SUCCESS &&
    libinput_device_config_accel_set_speed(device, speed) == LIBINPUT_CONFIG_STATUS_SUCCESS;
}

static void input_pointer_destroy(struct wl_listener *listener, void *data)
{
  struct nextspace_pointer *pointer = wl_container_of(listener, pointer, destroy);
  struct nextspace_server *server = pointer->server;
  wl_list_remove(&pointer->link); wl_list_remove(&pointer->destroy.link);
  free(pointer);
  input_snapshot(server);
}

static void input_attach_pointer(struct nextspace_server *server, struct wlr_input_device *device)
{
  struct nextspace_pointer *pointer = calloc(1, sizeof(*pointer));
  if (!pointer) return;
  pointer->device = device; pointer->server = server;
  pointer->destroy.notify = input_pointer_destroy;
  wl_signal_add(&device->events.destroy, &pointer->destroy);
  wl_list_insert(&server->pointers, &pointer->link);
  struct libinput_device *physical = input_pointer_device(pointer);
  if (physical && !input_set_pointer_device(physical, server->pointer_speed, server->pointer_profile))
    wlr_log(WLR_ERROR, "Pointer %s cannot apply the requested acceleration profile", device->name);
  input_snapshot(server);
}

static void input_result(struct nextspace_server *server, uint32_t serial, bool success)
{
  input_snapshot(server);
  nextspace_shell_v1_send_input_result(server->shell_resource, serial, success,
    success ? "" : "invalid or unsupported input settings");
}

static void shell_input_snapshot(struct wl_client *client, struct wl_resource *resource)
{ input_snapshot(wl_resource_get_user_data(resource)); }

static void shell_set_pointer(struct wl_client *client, struct wl_resource *resource,
    uint32_t serial, wl_fixed_t fixed, uint32_t profile)
{
  struct nextspace_server *server = wl_resource_get_user_data(resource);
  double speed = wl_fixed_to_double(fixed);
  bool ok = speed >= -1 && speed <= 1 && profile <= 1;
  /* Save each device's actual preceding values; startup defaults need not be
   * identical across devices. Unsupported or failed combinations restore all. */
  struct { struct libinput_device *device; double speed; enum libinput_config_accel_profile profile; } previous[64];
  size_t count = 0;
  struct nextspace_pointer *pointer;
  wl_list_for_each(pointer, &server->pointers, link) {
    struct libinput_device *device = input_pointer_device(pointer);
    if (!device) continue;
    if (count == 64) { ok = false; break; }
    previous[count].device = device;
    previous[count].speed = libinput_device_config_accel_get_speed(device);
    previous[count].profile = libinput_device_config_accel_get_profile(device);
    count++;
  }
  for (size_t i = 0; ok && i < count; i++) ok = input_set_pointer_device(previous[i].device, speed, profile);
  if (ok) { server->pointer_speed = speed; server->pointer_profile = profile; }
  else for (size_t i = 0; i < count; i++) {
    libinput_device_config_accel_set_profile(previous[i].device, previous[i].profile);
    libinput_device_config_accel_set_speed(previous[i].device, previous[i].speed);
  }
  input_result(server, serial, ok);
}

static bool input_rule(const char *value) { return strlen(value) <= 1024; }
static void shell_set_keyboard(struct wl_client *client, struct wl_resource *resource,
    uint32_t serial, const char *model, const char *layout, const char *variant, const char *options,
    uint32_t delay, uint32_t rate, uint32_t numlock)
{
  struct nextspace_server *server = wl_resource_get_user_data(resource);
  if (!input_rule(model) || !input_rule(layout) || !input_rule(variant) || !input_rule(options) ||
      !*layout || delay > 10000 || rate > 1000 || numlock > 1) { input_result(server, serial, false); return; }
  struct xkb_rule_names names = {.rules = "evdev", .model = model, .layout = layout,
    .variant = variant, .options = options};
  bool changed = strcmp(model, server->input_model) || strcmp(layout, server->input_layout) ||
    strcmp(variant, server->input_variant) || strcmp(options, server->input_options);
  struct xkb_keymap *map = changed ? xkb_keymap_new_from_names(server->input_context, &names,
    XKB_KEYMAP_COMPILE_NO_FLAGS) : xkb_keymap_ref(server->input_keymap);
  if (!map) { input_result(server, serial, false); return; }
  char *m = strdup(model), *l = strdup(layout), *v = strdup(variant), *o = strdup(options);
  bool ok = m && l && v && o;
  struct nextspace_keyboard *keyboard;
  if (changed) wl_list_for_each(keyboard, &server->keyboards, link)
    if (ok && !wlr_input_device_get_virtual_keyboard(&keyboard->wlr_keyboard->base) &&
        !wlr_keyboard_set_keymap(keyboard->wlr_keyboard, map)) ok = false;
  if (ok) {
    free(server->input_model); free(server->input_layout); free(server->input_variant); free(server->input_options);
    server->input_model = m; server->input_layout = l; server->input_variant = v; server->input_options = o;
    xkb_keymap_unref(server->input_keymap); server->input_keymap = map;
    server->input_delay = delay; server->input_rate = rate; server->input_numlock = numlock;
    wl_list_for_each(keyboard, &server->keyboards, link) {
      if (wlr_input_device_get_virtual_keyboard(&keyboard->wlr_keyboard->base)) continue;
      wlr_keyboard_set_repeat_info(keyboard->wlr_keyboard, rate, delay);
      input_apply_numlock(keyboard->wlr_keyboard, numlock);
    }
  } else {
    wl_list_for_each(keyboard, &server->keyboards, link)
      if (!wlr_input_device_get_virtual_keyboard(&keyboard->wlr_keyboard->base))
        wlr_keyboard_set_keymap(keyboard->wlr_keyboard, server->input_keymap);
    xkb_keymap_unref(map); free(m); free(l); free(v); free(o);
  }
  struct wlr_keyboard *active = wlr_seat_get_keyboard(server->seat);
  if (active) wlr_seat_keyboard_notify_modifiers(server->seat, &active->modifiers);
  input_result(server, serial, ok);
}

static void shell_set_shortcuts(struct wl_client *client, struct wl_resource *resource,
    uint32_t serial, struct wl_array *bindings)
{
  struct nextspace_server *server = wl_resource_get_user_data(resource);
  uint32_t values[18][2];
  bool ok = bindings->size == sizeof(values);
  if (ok) {
    memcpy(values, bindings->data, sizeof(values));
    for (unsigned i = 0; ok && i < 18; i++) {
      if (values[i][1] & ~(1u | 4u | 8u | 64u) || (!values[i][0] && values[i][1])) ok = false;
      for (unsigned j = 0; values[i][0] && j < i; j++)
        if (values[i][0] == values[j][0] && values[i][1] == values[j][1]) ok = false;
    }
  }
  if (ok) memcpy(server->shortcuts, values, sizeof(values));
  input_result(server, serial, ok);
}

static void input_default_shortcuts(struct nextspace_server *server)
{
  const uint32_t bindings[8][2] = {{XKB_KEY_Up, 8}, {XKB_KEY_Down, 8},
    {XKB_KEY_Tab, 8}, {XKB_KEY_Tab, 9}, {XKB_KEY_grave, 8}, {XKB_KEY_grave, 9},
    {XKB_KEY_Right, 4}, {XKB_KEY_Left, 4}};
  memcpy(server->shortcuts, bindings, sizeof(bindings));
  for (unsigned i = 0; i < 10; i++) {
    server->shortcuts[i + 8][0] = i == 9 ? XKB_KEY_0 : XKB_KEY_1 + i;
    server->shortcuts[i + 8][1] = 4;
  }
}

static char *input_environment(const char *name, const char *fallback)
{ const char *value = getenv(name); return strdup(value ? value : fallback); }
static bool input_settings_init(struct nextspace_server *server)
{
  input_default_shortcuts(server);
  wl_list_init(&server->pointers);
  server->input_model = input_environment("XKB_DEFAULT_MODEL", "pc105");
  server->input_layout = input_environment("XKB_DEFAULT_LAYOUT", "us");
  server->input_variant = input_environment("XKB_DEFAULT_VARIANT", "");
  server->input_options = input_environment("XKB_DEFAULT_OPTIONS", "");
  server->input_delay = 600; server->input_rate = 25;
  server->input_context = xkb_context_new(XKB_CONTEXT_NO_FLAGS);
  if (!server->input_model || !server->input_layout || !server->input_variant || !server->input_options ||
      !server->input_context) return false;
  struct xkb_rule_names names = {.rules = "evdev", .model = server->input_model, .layout = server->input_layout,
    .variant = server->input_variant, .options = server->input_options};
  server->input_keymap = xkb_keymap_new_from_names(server->input_context, &names, XKB_KEYMAP_COMPILE_NO_FLAGS);
  return server->input_keymap != NULL;
}
static void input_settings_finish(struct nextspace_server *server)
{
  xkb_keymap_unref(server->input_keymap); xkb_context_unref(server->input_context);
  free(server->input_model); free(server->input_layout); free(server->input_variant); free(server->input_options);
}
