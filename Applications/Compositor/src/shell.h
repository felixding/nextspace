/* Session capability and restartable shell connection. SPDX-License-Identifier: MIT */
static struct nextspace_toplevel *shell_view(struct nextspace_server *server, uint32_t id)
{
  struct nextspace_toplevel *view;
  wl_list_for_each(view, &server->toplevels, link)
    if (view->id == id && view->mapped) return view;
  return NULL;
}

static void shell_interactive_move(struct nextspace_toplevel *view, uint32_t phase)
{
  struct wl_resource *resource = view->server->shell_resource;
  if (!resource || wl_resource_get_version(resource) < 11 || !(view->style & (64 | 128))) return;
  struct nextspace_output *output = output_by_id(view->server, view->server->primary_output_id);
  struct wlr_box box;
  wlr_output_layout_get_box(view->server->output_layout, output ? output->wlr_output : NULL, &box);
  nextspace_shell_v1_send_interactive_move(resource, view->id, phase,
    view->scene_tree->node.x, view->scene_tree->node.y, box.x, box.y, box.width, box.height);
}

static void shell_cancel_move(struct wl_client *client, struct wl_resource *resource, uint32_t id)
{
  struct nextspace_server *server = wl_resource_get_user_data(resource);
  if (server->grabbed_toplevel && server->grabbed_toplevel->id == id &&
      (server->grabbed_toplevel->style & (64 | 128))) reset_cursor_mode(server);
}

static bool shell_send_window(struct nextspace_toplevel *view, bool force)
{
  struct nextspace_server *server = view->server;
  if (!server->shell_resource || !view->mapped) return false;
  const char *app_id = view_app_id(view);
  const char *title = view_title(view);
  if (!title) title = "";
  pid_t pid = view_pid(view);
  struct wlr_box geometry;
  view_geometry(view, &geometry);
  uint32_t flags = (server->seat->keyboard_state.focused_surface == view_surface(view) ?
    NEXTSPACE_SHELL_V1_FLAGS_FOCUSED : 0) |
    (!view->application_window || view->application_window->accepts_focus ?
      NEXTSPACE_SHELL_V1_FLAGS_ACCEPTS_FOCUS : 0);
  if (wl_resource_get_version(server->shell_resource) >= 2 && view->minimized)
    flags |= NEXTSPACE_SHELL_V1_FLAGS_MINIMIZED;
  if (wl_resource_get_version(server->shell_resource) >= 3 && view->shaded)
    flags |= NEXTSPACE_SHELL_V1_FLAGS_SHADED;
  if (wl_resource_get_version(server->shell_resource) >= 4 && view->shell_hidden)
    flags |= NEXTSPACE_SHELL_V1_FLAGS_NOT_PRESENTED;
  geometry.x = view->scene_tree->node.x; geometry.y = view->scene_tree->node.y;
  if (!force && view->shell_state.valid && view->shell_state.flags == flags &&
      view->shell_state.pid == pid && view->shell_state.client_id == view->client_id &&
      view->shell_state.style == view->style && view->shell_state.title_height == view->title_height &&
      view->shell_state.level == view->level && view->shell_state.desktop == view->desktop &&
      view->shell_state.sticky == view->sticky && view->shell_state.box.x == geometry.x &&
      view->shell_state.box.y == geometry.y && view->shell_state.box.width == geometry.width &&
      view->shell_state.box.height == geometry.height && strcmp(view->shell_state.app_id, app_id) == 0 &&
      strcmp(view->shell_state.title, title) == 0) return false;
  char *app_copy = strdup(app_id), *title_copy = strdup(title);
  free(view->shell_state.app_id); free(view->shell_state.title);
  view->shell_state.app_id = app_copy; view->shell_state.title = title_copy;
  view->shell_state.box = geometry; view->shell_state.flags = flags; view->shell_state.pid = pid;
  view->shell_state.client_id = view->client_id; view->shell_state.style = view->style;
  view->shell_state.title_height = view->title_height; view->shell_state.level = view->level;
  view->shell_state.desktop = view->desktop; view->shell_state.sticky = view->sticky;
  view->shell_state.valid = app_copy && title_copy;
  nextspace_shell_v1_send_window(server->shell_resource, view->id, app_id, title, pid, flags,
    geometry.x, geometry.y, geometry.width, geometry.height);
  if (wl_resource_get_version(server->shell_resource) >= 3)
    nextspace_shell_v1_send_window_info(server->shell_resource, view->id, view->client_id,
      view->style, view->title_height, view->level);
  if (wl_resource_get_version(server->shell_resource) >= 10)
    nextspace_shell_v1_send_window_desktop(server->shell_resource, view->id, view->desktop, view->sticky);
  return true;
}

static void shell_window_changed(struct nextspace_toplevel *view)
{
  if (!view->mapped || !view->server->shell_resource) return;
  if (shell_send_window(view, false)) nextspace_shell_v1_send_done(view->server->shell_resource);
}

static void shell_window_closed(struct nextspace_toplevel *view)
{
  view->shell_state.valid = false;
  if (!view->server->shell_resource) return;
  nextspace_shell_v1_send_closed(view->server->shell_resource, view->id);
  nextspace_shell_v1_send_done(view->server->shell_resource);
}

static void shell_focus_changed(struct nextspace_server *server)
{
  if (!server->shell_resource) return;
  struct nextspace_toplevel *view;
  bool changed = false;
  wl_list_for_each(view, &server->toplevels, link) changed |= shell_send_window(view, false);
  if (changed) nextspace_shell_v1_send_done(server->shell_resource);
}

static void shell_metadata_changed(struct wl_listener *listener, void *data)
{
  struct nextspace_toplevel *view = wl_container_of(listener, view, set_title);
  decoration_update(view);
  shell_window_changed(view);
}

static void shell_app_id_changed(struct wl_listener *listener, void *data)
{
  struct nextspace_toplevel *view = wl_container_of(listener, view, set_app_id);
  shell_window_changed(view);
}

static void shell_pointer_changed(struct nextspace_server *server, struct nextspace_toplevel *view)
{
  uint32_t id = view ? view->id : 0;
  if (server->shell_pointer_id == id) return;
  server->shell_pointer_id = id;
  if (server->shell_resource && wl_resource_get_version(server->shell_resource) >= 6)
    nextspace_shell_v1_send_pointer_focus(server->shell_resource, id);
}

static void shell_snapshot(struct wl_client *client, struct wl_resource *resource)
{
  struct nextspace_server *server = wl_resource_get_user_data(resource);
  nextspace_shell_v1_send_reset(resource);
  struct nextspace_toplevel *view;
  wl_list_for_each(view, &server->toplevels, link) shell_send_window(view, true);
  if (server->grabbed_toplevel && server->cursor_mode == NEXTSPACE_CURSOR_MOVE)
    shell_interactive_move(server->grabbed_toplevel, 0);
  nextspace_shell_v1_send_done(resource);
  if (wl_resource_get_version(resource) >= 6)
    nextspace_shell_v1_send_pointer_focus(resource, server->shell_pointer_id);
  output_snapshot(server);
  input_snapshot(server);
  desktop_snapshot(server);
}

static void shell_activate(struct wl_client *client, struct wl_resource *resource, uint32_t id)
{
  struct nextspace_toplevel *view = shell_view(wl_resource_get_user_data(resource), id);
  if (view) {
    if (!view->sticky) desktop_switch(view->server, view->desktop);
    policy_set_presented(view, true);
    policy_set_shaded(view, false); policy_set_minimized(view, false);
    focus_toplevel(view, view_surface(view));
  }
}

static void shell_close(struct wl_client *client, struct wl_resource *resource, uint32_t id)
{
  struct nextspace_toplevel *view = shell_view(wl_resource_get_user_data(resource), id);
  if (!view) return;
  wlr_xdg_toplevel_send_close(view->xdg_toplevel);
}

static void shell_move(struct wl_client *client, struct wl_resource *resource,
    uint32_t id, int32_t x, int32_t y)
{
  struct nextspace_toplevel *view = shell_view(wl_resource_get_user_data(resource), id);
  if (!view) return;
  if (view->maximized || view->fullscreen) return;
  constrain_position(view, &x, &y);
  view_move(view, x, y);
  policy_refresh_pointer(view->server);
}

static void shell_set_minimized(struct wl_client *client, struct wl_resource *resource,
    uint32_t id, uint32_t minimized)
{
  struct nextspace_toplevel *view = shell_view(wl_resource_get_user_data(resource), id);
  if (view) policy_set_minimized(view, minimized != 0);
}

static void shell_set_shaded(struct wl_client *client, struct wl_resource *resource,
    uint32_t id, uint32_t shaded)
{
  struct nextspace_toplevel *view = shell_view(wl_resource_get_user_data(resource), id);
  if (view) policy_set_shaded(view, shaded != 0);
}

static void shell_set_presented(struct wl_client *client, struct wl_resource *resource,
    uint32_t id, uint32_t presented)
{
  struct nextspace_toplevel *view = shell_view(wl_resource_get_user_data(resource), id);
  if (view) policy_set_presented(view, presented != 0);
}

static void shell_set_level(struct wl_client *client, struct wl_resource *resource,
    uint32_t id, int32_t level)
{
  struct nextspace_toplevel *view = shell_view(wl_resource_get_user_data(resource), id);
  if (view) { policy_set_level(view, level); policy_refresh_pointer(view->server); }
}

static void shell_order(struct wl_client *client, struct wl_resource *resource,
    uint32_t id, uint32_t above)
{
  struct nextspace_toplevel *view = shell_view(wl_resource_get_user_data(resource), id);
  if (view) {
    policy_order(view, above != 0, NULL);
    policy_refresh_pointer(view->server);
  }
}

static void shell_background_snapshot(struct wl_client *client, struct wl_resource *resource)
{
  struct nextspace_server *server = wl_resource_get_user_data(resource);
  nextspace_shell_v1_send_background(resource, wl_fixed_from_double(server->background->color[0]),
    wl_fixed_from_double(server->background->color[1]), wl_fixed_from_double(server->background->color[2]));
}
static void shell_set_background(struct wl_client *client, struct wl_resource *resource,
    wl_fixed_t red, wl_fixed_t green, wl_fixed_t blue)
{
  struct nextspace_server *server = wl_resource_get_user_data(resource);
  float color[4] = {wl_fixed_to_double(red), wl_fixed_to_double(green), wl_fixed_to_double(blue), 1};
  if (color[0] >= 0 && color[0] <= 1 && color[1] >= 0 && color[1] <= 1 && color[2] >= 0 && color[2] <= 1)
    wlr_scene_rect_set_color(server->background, color);
  shell_background_snapshot(client, resource);
}

static void shell_configure_desktops(struct wl_client *client, struct wl_resource *resource, uint32_t count)
{ desktop_configure(wl_resource_get_user_data(resource), count); }
static void shell_switch_desktop(struct wl_client *client, struct wl_resource *resource, uint32_t index)
{ desktop_switch(wl_resource_get_user_data(resource), index); }
static void shell_move_to_desktop(struct wl_client *client, struct wl_resource *resource,
    uint32_t id, uint32_t index, uint32_t sticky)
{
  struct nextspace_server *server = wl_resource_get_user_data(resource);
  struct nextspace_toplevel *view = shell_view(server, id);
  if (view && sticky <= 1) desktop_move(view, index, sticky != 0);
  desktop_snapshot(server);
}

static void shell_set_output_insets(struct wl_client *client, struct wl_resource *resource,
    uint32_t id, int32_t left, int32_t top, int32_t right, int32_t bottom)
{
  struct nextspace_server *server = wl_resource_get_user_data(resource);
  struct nextspace_output *output = output_by_id(server, id);
  int insets[] = {left, top, right, bottom};
  if (!output) return;
  for (size_t i = 0; i < 4; i++) if (insets[i] < 0 || insets[i] > 4096) return;
  if (!memcmp(insets, output->insets, sizeof(insets))) return;
  memcpy(output->insets, insets, sizeof(insets));
  struct nextspace_toplevel *view;
  wl_list_for_each(view, &server->toplevels, link)
    if (view->maximized && !view->fullscreen) policy_size_geometry(view);
  output_snapshot(server);
  application_work_areas(server);
}

static void shell_set_maximized_drag_mode(struct wl_client *client, struct wl_resource *resource, uint32_t mode)
{
  struct nextspace_server *server = wl_resource_get_user_data(resource);
  if (mode > NEXTSPACE_SHELL_V1_MAXIMIZED_DRAG_MODE_NO_MOVE || mode == server->maximized_drag_mode) return;
  reset_cursor_mode(server);
  server->maximized_drag_mode = mode;
}

static void shell_set_double_click_time(struct wl_client *client, struct wl_resource *resource, uint32_t milliseconds)
{
  struct nextspace_server *server = wl_resource_get_user_data(resource);
  if (milliseconds < 1 || milliseconds > 60000 || milliseconds == server->double_click_time) return;
  server->double_click_time = milliseconds;
  server->decoration_click_view = 0;
}

static void shell_set_title_appearance(struct wl_client *client, struct wl_resource *resource,
    const char *font, uint32_t antialiased, uint32_t justification)
{ decoration_set_title_appearance(wl_resource_get_user_data(resource), font, antialiased, justification); }

static void shell_lock(struct wl_client *client, struct wl_resource *resource)
{ session_lock_request(wl_resource_get_user_data(resource), true); }

static void shell_set_output_gamma(struct wl_client *client, struct wl_resource *resource,
    uint32_t serial, uint32_t id, wl_fixed_t red, wl_fixed_t green, wl_fixed_t blue, wl_fixed_t brightness)
{
  struct nextspace_server *server = wl_resource_get_user_data(resource);
  struct nextspace_output *output = output_by_id(server, id);
  struct output_gamma gamma = {wl_fixed_to_double(red), wl_fixed_to_double(green),
    wl_fixed_to_double(blue), wl_fixed_to_double(brightness)};
  bool ok = output && !server->output_pending && !server->pending_output &&
    output_apply_gamma(output, gamma);
  if (ok) outputs_changed(server);
  output_snapshot(server);
  nextspace_shell_v1_send_output_gamma_result(resource, serial, ok,
    ok ? "" : "invalid, unavailable or unsupported output gamma");
}

static const struct nextspace_shell_v1_interface shell_impl = {
  .destroy = destroy_application_object, .snapshot = shell_snapshot,
  .activate = shell_activate, .close = shell_close, .move = shell_move,
  .set_minimized = shell_set_minimized, .set_shaded = shell_set_shaded,
  .set_presented = shell_set_presented, .set_level = shell_set_level, .order = shell_order,
  .output_snapshot = shell_output_snapshot, .configure_outputs = shell_configure_outputs,
  .input_snapshot = shell_input_snapshot, .set_keyboard = shell_set_keyboard, .set_pointer = shell_set_pointer,
  .background_snapshot = shell_background_snapshot, .set_background = shell_set_background,
  .configure_desktops = shell_configure_desktops, .switch_desktop = shell_switch_desktop,
  .set_shortcuts = shell_set_shortcuts,
  .move_to_desktop = shell_move_to_desktop, .cancel_move = shell_cancel_move,
  .set_output_insets = shell_set_output_insets, .set_maximized_drag_mode = shell_set_maximized_drag_mode,
  .set_double_click_time = shell_set_double_click_time,
  .set_title_appearance = shell_set_title_appearance, .lock = shell_lock,
  .set_output_gamma = shell_set_output_gamma
};

static void shell_resource_destroy(struct wl_resource *resource)
{
  struct nextspace_server *server = wl_resource_get_user_data(resource);
  if (server->shell_resource == resource) {
    server->shell_resource = NULL;
    output_revert(server, "shell disconnected");
  }
}

static void bind_shell(struct wl_client *client, void *data, uint32_t version, uint32_t id)
{
  struct nextspace_server *server = data;
  /* Also check here: a guessed global name must not bypass registry filtering. */
  if (client != server->shell_client || server->shell_resource) {
    wl_client_post_implementation_error(client, "Unauthorized or duplicate NEXTSPACE shell binding");
    return;
  }
  struct wl_resource *resource = wl_resource_create(client, &nextspace_shell_v1_interface, version, id);
  if (!resource) { wl_client_post_no_memory(client); return; }
  server->shell_resource = resource;
  wl_resource_set_implementation(resource, &shell_impl, server, shell_resource_destroy);
  shell_snapshot(client, resource);
}

static void shell_client_destroy(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, shell_client_destroy);
  wl_list_remove(&server->shell_client_destroy.link);
  server->shell_client = NULL;
  server->shell_resource = NULL;
}

static void shell_revoke(struct nextspace_server *server)
{
  if (server->shell_client) wl_client_destroy(server->shell_client);
}

static void input_method_client_destroy(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, input_method_client_destroy);
  wl_list_remove(&server->input_method_client_destroy.link);
  server->input_method_client = NULL;
}

static int shell_broker_ready(int fd, uint32_t mask, void *data)
{
  struct nextspace_server *server = data;
  char byte;
  struct iovec iov = {&byte, 1};
  union { struct cmsghdr align; char bytes[CMSG_SPACE(8 * sizeof(int))]; } ancillary;
  struct msghdr message = {.msg_iov = &iov, .msg_iovlen = 1,
    .msg_control = ancillary.bytes, .msg_controllen = sizeof(ancillary.bytes)};
  ssize_t count = recvmsg(fd, &message, MSG_DONTWAIT | MSG_CMSG_CLOEXEC);
  if (count < 0 && (errno == EAGAIN || errno == EINTR)) return 0;
  if (count <= 0) {
    if (count < 0) wlr_log(WLR_ERROR, "Session broker receive failed: %s", strerror(errno));
    shell_revoke(server);
    if (server->input_method_client) wl_client_destroy(server->input_method_client);
    if (server->lock_client) wl_client_destroy(server->lock_client);
    capture_revoke(server);
    wl_event_source_remove(server->shell_broker_source);
    server->shell_broker_source = NULL;
    close(server->shell_broker_fd); server->shell_broker_fd = -1;
    return 0;
  }
  int connection = -1, received = 0;
  for (struct cmsghdr *header = CMSG_FIRSTHDR(&message); header; header = CMSG_NXTHDR(&message, header)) {
    if (header->cmsg_level != SOL_SOCKET || header->cmsg_type != SCM_RIGHTS) continue;
    size_t bytes = header->cmsg_len - CMSG_LEN(0);
    int *fds = (int *)CMSG_DATA(header);
    for (size_t i = 0; i < bytes / sizeof(int); i++) {
      if (received++ == 0) connection = fds[i]; else close(fds[i]);
    }
  }
  if (count == 1 && byte == 'R' && received == 0 && !(message.msg_flags & (MSG_TRUNC | MSG_CTRUNC))) {
    session_lock_request(server, false); return 0;
  }
  if (count == 1 && received == 0 && !(message.msg_flags & (MSG_TRUNC | MSG_CTRUNC))) {
    if (byte == 'P') { session_lock_prepare_for_sleep(server); return 0; }
    if (byte == 'W') { server->sleep_guard = false; server->sleep_acknowledged = false; return 0; }
  }
  int type = 0; socklen_t size = sizeof(type);
  struct sockaddr_un address; socklen_t length = sizeof(address);
  bool valid = count == 1 && (byte == 'C' || byte == 'I' || byte == 'L' || byte == 'V') && received == 1 &&
    !(message.msg_flags & (MSG_TRUNC | MSG_CTRUNC)) &&
    getsockopt(connection, SOL_SOCKET, SO_TYPE, &type, &size) == 0 && type == SOCK_STREAM &&
    getpeername(connection, (struct sockaddr *)&address, &length) == 0 && address.sun_family == AF_UNIX;
  if (!valid) { if (connection >= 0) close(connection); return 0; }
  if (byte == 'V' && server->locked) { close(connection); return 0; }
  struct wl_client *replacement = wl_client_create(server->wl_display, connection);
  if (!replacement) { close(connection); return 0; }
  if (byte == 'V') {
    capture_revoke(server);
    server->capture_client = replacement;
    server->capture_client_destroy.notify = capture_client_destroy;
    wl_client_add_destroy_listener(replacement, &server->capture_client_destroy);
    return 0;
  }
  if (byte == 'L') {
    if (server->lock_client) wl_client_destroy(server->lock_client);
    server->lock_client = replacement;
    server->lock_client_destroy.notify = session_lock_client_destroy;
    wl_client_add_destroy_listener(replacement, &server->lock_client_destroy);
    return 0;
  }
  if (byte == 'I') {
    if (server->input_method_client) wl_client_destroy(server->input_method_client);
    server->input_method_client = replacement;
    server->input_method_client_destroy.notify = input_method_client_destroy;
    wl_client_add_destroy_listener(replacement, &server->input_method_client_destroy);
    return 0;
  }
  shell_revoke(server);
  server->shell_client = replacement;
  server->shell_client_destroy.notify = shell_client_destroy;
  wl_client_add_destroy_listener(replacement, &server->shell_client_destroy);
  return 0;
}

static bool shell_init(struct nextspace_server *server, int fd)
{
  server->shell_broker_fd = fd;
  server->shell_global = wl_global_create(server->wl_display, &nextspace_shell_v1_interface,
    18, server, bind_shell);
  if (!server->shell_global) return false;
  if (fd < 0) return true;
  int type; socklen_t size = sizeof(type);
  if (getsockopt(fd, SOL_SOCKET, SO_TYPE, &type, &size) || type != SOCK_SEQPACKET) return false;
  server->shell_broker_source = wl_event_loop_add_fd(wl_display_get_event_loop(server->wl_display),
    fd, WL_EVENT_READABLE, shell_broker_ready, server);
  return server->shell_broker_source != NULL;
}

static void shell_finish(struct nextspace_server *server)
{
  shell_revoke(server);
  if (server->input_method_client) wl_client_destroy(server->input_method_client);
  if (server->shell_broker_source) wl_event_source_remove(server->shell_broker_source);
  if (server->shell_broker_fd >= 0) close(server->shell_broker_fd);
}
