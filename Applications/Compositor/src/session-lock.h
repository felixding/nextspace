/* Capability-scoped session locking. SPDX-License-Identifier: MIT */
struct nextspace_lock_surface {
  struct nextspace_server *server;
  struct wlr_session_lock_surface_v1 *surface;
  struct wlr_scene_tree *tree;
  struct wl_list link;
  struct wl_listener map, unmap, destroy, scene_destroy;
  int width, height;
};

static void session_lock_notify(struct nextspace_server *server, char event)
{
  if (server->shell_broker_fd >= 0 &&
      send(server->shell_broker_fd, &event, 1, MSG_NOSIGNAL | MSG_DONTWAIT) != 1)
    wl_display_terminate(server->wl_display);
}

static void session_lock_state_json(FILE *stream, struct nextspace_server *server)
{
  unsigned pending = 0;
  struct nextspace_output *output;
  wl_list_for_each(output, &server->outputs, link)
    if (output->wlr_output->enabled && output->lock_pending_frame) pending++;
  fprintf(stream, "{\"locked\":%s,\"active\":%s,\"acknowledged\":%s,\"pending_outputs\":%u,\"surfaces\":%d,\"epoch\":%u,\"sleep_guard\":%s,\"sleep_protected_ms\":%llu,\"desktop_visible\":%s}",
    server->locked ? "true" : "false", server->session_lock ? "true" : "false",
    server->session_lock && server->session_lock->locked_sent ? "true" : "false", pending,
    wl_list_length(&server->lock_surfaces), server->lock_epoch, server->sleep_guard ? "true" : "false",
    (unsigned long long)server->sleep_protected_ms,
    server->desktop_tree->node.enabled ? "true" : "false");
}

static void session_lock_surfaces_json(FILE *stream, struct nextspace_server *server)
{
  bool first = true; fputc('[', stream);
  struct nextspace_lock_surface *item;
  wl_list_for_each(item, &server->lock_surfaces, link) {
    struct wlr_surface *surface = item->surface->surface;
    fprintf(stream, "%s{\"output\":", first ? "" : ","); first = false;
    json_string(stream, item->surface->output->name);
    fprintf(stream, ",\"mapped\":%s,\"width\":%d,\"height\":%d,\"buffer_width\":%d,\"buffer_height\":%d}",
      surface->mapped ? "true" : "false", surface->current.width, surface->current.height,
      surface->current.buffer_width, surface->current.buffer_height);
  }
  fputc(']', stream);
}

static bool session_lock_surface(struct nextspace_server *server, struct wlr_surface *surface)
{
  if (!server->locked || !surface || wl_resource_get_client(surface->resource) != server->lock_client) return false;
  return wlr_session_lock_surface_v1_try_from_wlr_surface(wlr_surface_get_root_surface(surface)) != NULL;
}

static void session_lock_focus(struct nextspace_server *server, struct wlr_surface *surface)
{
  if (!server->locked) return;
  if (!surface) {
    struct nextspace_lock_surface *item;
    wl_list_for_each(item, &server->lock_surfaces, link)
      if (item->tree && item->tree->node.enabled && item->surface->surface->mapped) {
        surface = item->surface->surface; break;
      }
  }
  if (!session_lock_surface(server, surface)) { wlr_seat_keyboard_notify_clear_focus(server->seat); return; }
  struct nextspace_keyboard *keyboard;
  wl_list_for_each(keyboard, &server->keyboards, link) {
    if (wlr_input_device_get_virtual_keyboard(&keyboard->wlr_keyboard->base)) continue;
    wlr_seat_set_keyboard(server->seat, keyboard->wlr_keyboard);
    wlr_seat_keyboard_notify_enter(server->seat, surface, keyboard->wlr_keyboard->keycodes,
      keyboard->wlr_keyboard->num_keycodes, &keyboard->wlr_keyboard->modifiers);
    return;
  }
}

static void session_lock_check_presented(struct nextspace_server *server)
{
  if (!server->locked) return;
  struct nextspace_output *output;
  wl_list_for_each(output, &server->outputs, link)
    if (output->wlr_output->enabled &&
        (output->lock_epoch != server->lock_epoch || output->lock_pending_frame)) return;
  if (server->sleep_guard && !server->sleep_acknowledged) {
    struct timespec now; clock_gettime(CLOCK_MONOTONIC, &now);
    server->sleep_protected_ms = (uint64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000;
    server->sleep_acknowledged = true;
    session_lock_notify(server, 'S');
  }
  if (server->session_lock && !server->session_lock->locked_sent) {
    wlr_session_lock_v1_send_locked(server->session_lock);
    session_lock_notify(server, 'K');
  }
}

static void session_lock_damage(struct nextspace_output *output)
{
  struct wlr_scene_output *scene = wlr_scene_get_scene_output(output->server->scene, output->wlr_output);
  if (scene) wlr_damage_ring_add_whole(&scene->damage_ring);
  wlr_output_schedule_frame(output->wlr_output);
}

static void session_lock_output_present(struct wl_listener *listener, void *data)
{
  struct nextspace_output *output = wl_container_of(listener, output, lock_present);
  struct wlr_output_event_present *event = data;
  if (!output->server->locked || !output->lock_pending_frame) return;
  if (!event->presented) { session_lock_damage(output); return; }
  if ((int32_t)(event->commit_seq - output->lock_commit_seq) < 0) return;
  output->lock_pending_frame = false;
  session_lock_check_presented(output->server);
}

static void session_lock_layout_changed(struct nextspace_server *server)
{
  if (!server->lock_tree) return;
  struct nextspace_output *output;
  wl_list_for_each(output, &server->outputs, link) {
    struct wlr_box box;
    wlr_output_layout_get_box(server->output_layout, output->wlr_output, &box);
    if (!output->lock_background) {
      const float black[4] = {0, 0, 0, 1};
      output->lock_background = wlr_scene_rect_create(server->lock_tree, 1, 1, black);
      if (!output->lock_background) { wl_display_terminate(server->wl_display); return; }
      wlr_scene_node_lower_to_bottom(&output->lock_background->node);
    }
    wlr_scene_node_set_position(&output->lock_background->node, box.x, box.y);
    int width, height;
    wlr_output_transformed_resolution(output->wlr_output, &width, &height);
    /* The integer logical layout can truncate a fractional pixel. The blank
     * backdrop must still cover the complete physical output opaquely. */
    width = (int)ceil(width / output->wlr_output->scale);
    height = (int)ceil(height / output->wlr_output->scale);
    wlr_scene_rect_set_size(output->lock_background, width > 0 ? width : 1, height > 0 ? height : 1);
    wlr_scene_node_set_enabled(&output->lock_background->node, output->wlr_output->enabled && box.width > 0 && box.height > 0);
    if (server->locked && output->wlr_output->enabled && output->lock_epoch != server->lock_epoch) {
      output->lock_epoch = server->lock_epoch;
      output->lock_commit_seq = output->wlr_output->commit_seq + 1;
      output->lock_pending_frame = true;
      session_lock_damage(output);
    }
  }
  struct nextspace_lock_surface *item;
  wl_list_for_each(item, &server->lock_surfaces, link) {
    struct wlr_box box;
    wlr_output_layout_get_box(server->output_layout, item->surface->output, &box);
    bool enabled = item->surface->output->enabled && box.width > 0 && box.height > 0;
    if (item->tree) {
      wlr_scene_node_set_enabled(&item->tree->node, enabled);
      wlr_scene_node_set_position(&item->tree->node, box.x, box.y);
    }
    if (enabled && (item->width != box.width || item->height != box.height)) {
      item->width = box.width; item->height = box.height;
      wlr_session_lock_surface_v1_configure(item->surface, box.width, box.height);
    }
  }
  if (server->locked) session_lock_check_presented(server);
}

static void session_lock_output_destroy(struct nextspace_output *output)
{
  wl_list_remove(&output->lock_present.link);
  if (output->lock_background) wlr_scene_node_destroy(&output->lock_background->node);
  output->lock_background = NULL;
}

static void session_lock_scene_destroy(struct wl_listener *listener, void *data)
{
  struct nextspace_lock_surface *item = wl_container_of(listener, item, scene_destroy);
  wl_list_remove(&item->scene_destroy.link); item->tree = NULL;
}

static void session_lock_surface_destroy(struct wl_listener *listener, void *data)
{
  struct nextspace_lock_surface *item = wl_container_of(listener, item, destroy);
  struct nextspace_server *server = item->server;
  bool focused = server->seat->keyboard_state.focused_surface &&
    wlr_surface_get_root_surface(server->seat->keyboard_state.focused_surface) == item->surface->surface;
  wl_list_remove(&item->link);
  wl_list_remove(&item->map.link); wl_list_remove(&item->unmap.link); wl_list_remove(&item->destroy.link);
  if (item->tree) wlr_scene_node_destroy(&item->tree->node);
  free(item);
  if (focused) session_lock_focus(server, NULL);
}

static void session_lock_surface_map(struct wl_listener *listener, void *data)
{
  struct nextspace_lock_surface *item = wl_container_of(listener, item, map);
  if (!item->server->seat->keyboard_state.focused_surface) session_lock_focus(item->server, item->surface->surface);
}

static void session_lock_surface_unmap(struct wl_listener *listener, void *data)
{
  struct nextspace_lock_surface *item = wl_container_of(listener, item, unmap);
  if (item->server->seat->keyboard_state.focused_surface == item->surface->surface)
    session_lock_focus(item->server, NULL);
}

static void session_lock_new_surface(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, lock_new_surface);
  struct wlr_session_lock_surface_v1 *surface = data;
  struct nextspace_lock_surface *item = calloc(1, sizeof(*item));
  if (!item) { wl_resource_post_no_memory(surface->resource); return; }
  item->server = server; item->surface = surface;
  item->tree = wlr_scene_subsurface_tree_create(server->lock_tree, surface->surface);
  if (!item->tree) { free(item); wl_resource_post_no_memory(surface->resource); return; }
  item->scene_destroy.notify = session_lock_scene_destroy;
  wl_signal_add(&item->tree->node.events.destroy, &item->scene_destroy);
  item->map.notify = session_lock_surface_map; wl_signal_add(&surface->surface->events.map, &item->map);
  item->unmap.notify = session_lock_surface_unmap; wl_signal_add(&surface->surface->events.unmap, &item->unmap);
  item->destroy.notify = session_lock_surface_destroy; wl_signal_add(&surface->events.destroy, &item->destroy);
  wl_list_insert(&server->lock_surfaces, &item->link);
  session_lock_layout_changed(server);
}

static void session_lock_destroyed(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, lock_destroy);
  wl_list_remove(&server->lock_new_surface.link); wl_list_remove(&server->lock_unlock.link);
  wl_list_remove(&server->lock_destroy.link); server->session_lock = NULL;
  if (server->locked) {
    wlr_seat_keyboard_notify_clear_focus(server->seat);
    wlr_seat_pointer_notify_clear_focus(server->seat);
  }
  /* Losing the locker never enables the desktop. A new capability holder may recover it. */
}

static void session_lock_unlock(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, lock_unlock);
  if (server->sleep_guard) return;
  server->locked = false;
  session_lock_notify(server, 'U');
  wlr_seat_keyboard_notify_clear_focus(server->seat); wlr_seat_pointer_notify_clear_focus(server->seat);
  wlr_scene_node_set_enabled(&server->lock_tree->node, false);
  wlr_scene_node_set_enabled(&server->desktop_tree->node, true);
  struct nextspace_toplevel *view, *chosen = NULL;
  wl_list_for_each(view, &server->toplevels, link) {
    if (!view->mapped || !policy_visible(view) ||
        (view->application_window && !view->application_window->accepts_focus)) continue;
    if (!chosen) chosen = view;
    if (view->id == server->lock_previous_focus) { chosen = view; break; }
  }
  if (chosen) focus_toplevel(chosen, view_surface(chosen));
  policy_refresh_pointer(server);
}

static void session_lock_begin(struct nextspace_server *server)
{
  color_pick_finish(server, NEXTSPACE_WINDOW_V1_COLOR_PICK_PHASE_CANCELLED, 0);
  struct nextspace_toplevel *previous = view_for_surface(server, server->seat->keyboard_state.focused_surface);
  if (!server->locked) server->lock_previous_focus = previous ? previous->id : 0;
  server->locked = true;
  /* Revoke existing managers and in-flight frames before drawing the lock. */
  capture_revoke(server);
  if (++server->lock_epoch == 0) ++server->lock_epoch;
  wlr_scene_node_set_enabled(&server->desktop_tree->node, false);
  wlr_scene_node_set_enabled(&server->lock_tree->node, true);
  cancel_pointer_drag(server); reset_cursor_mode(server);
  struct nextspace_toplevel *view;
  wl_list_for_each(view, &server->toplevels, link) policy_dismiss_popups(view);
  wlr_seat_keyboard_end_grab(server->seat); wlr_seat_pointer_end_grab(server->seat);
  input_method_deactivate(server);
  if (previous) view_activate(previous, false);
  wlr_seat_keyboard_notify_clear_focus(server->seat); wlr_seat_pointer_notify_clear_focus(server->seat);
  while (server->seat->pointer_state.button_count) {
    uint32_t button = server->seat->pointer_state.buttons[server->seat->pointer_state.button_count - 1];
    wlr_seat_pointer_notify_button(server->seat, 0, button, WL_POINTER_BUTTON_STATE_RELEASED);
  }
  wlr_cursor_set_surface(server->cursor, NULL, 0, 0);
  session_lock_layout_changed(server);
}

static void session_lock_request(struct nextspace_server *server, bool notify)
{
  const char *session_class = getenv("XDG_SESSION_CLASS");
  if (session_class && strcmp(session_class, "greeter") == 0) return;
  if (server->locked) return;
  session_lock_begin(server);
  if (notify) session_lock_notify(server, 'R');
}

static void session_lock_prepare_for_sleep(struct nextspace_server *server)
{
  session_lock_request(server, false);
  if (!server->locked) return; /* Greeters ignore user lock requests. */
  server->sleep_guard = true; server->sleep_acknowledged = false; server->sleep_protected_ms = 0;
  session_lock_check_presented(server);
}

static void session_lock_new(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, new_lock);
  struct wlr_session_lock_v1 *lock = data;
  if (wl_resource_get_client(lock->resource) != server->lock_client || server->session_lock) {
    wlr_session_lock_v1_destroy(lock); return;
  }
  server->session_lock = lock;
  server->lock_new_surface.notify = session_lock_new_surface;
  wl_signal_add(&lock->events.new_surface, &server->lock_new_surface);
  server->lock_unlock.notify = session_lock_unlock; wl_signal_add(&lock->events.unlock, &server->lock_unlock);
  server->lock_destroy.notify = session_lock_destroyed; wl_signal_add(&lock->events.destroy, &server->lock_destroy);
  session_lock_begin(server);
}

static void session_lock_pointer_motion(struct nextspace_server *server, uint32_t time)
{
  double sx, sy;
  struct wlr_scene_node *node = wlr_scene_node_at(&server->lock_tree->node,
    server->cursor->x, server->cursor->y, &sx, &sy);
  struct wlr_scene_surface *scene = node && node->type == WLR_SCENE_NODE_BUFFER ?
    wlr_scene_surface_try_from_buffer(wlr_scene_buffer_from_node(node)) : NULL;
  struct wlr_surface *surface = scene ? scene->surface : NULL;
  if (!session_lock_surface(server, surface)) {
    wlr_seat_pointer_notify_clear_focus(server->seat);
    wlr_cursor_set_surface(server->cursor, NULL, 0, 0); return;
  }
  wlr_seat_pointer_notify_enter(server->seat, surface, sx, sy);
  wlr_seat_pointer_notify_motion(server->seat, time, sx, sy);
}

static void session_lock_pointer_button(struct nextspace_server *server, struct wlr_pointer_button_event *event)
{
  session_lock_pointer_motion(server, event->time_msec);
  if (!session_lock_surface(server, server->seat->pointer_state.focused_surface)) return;
  wlr_seat_pointer_notify_button(server->seat, event->time_msec, event->button, event->state);
  if (event->state == WL_POINTER_BUTTON_STATE_PRESSED)
    session_lock_focus(server, server->seat->pointer_state.focused_surface);
}

static void session_lock_client_destroy(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, lock_client_destroy);
  wl_list_remove(&server->lock_client_destroy.link); server->lock_client = NULL;
}

static bool session_lock_init(struct nextspace_server *server)
{
  wl_list_init(&server->lock_surfaces);
  server->lock_manager = wlr_session_lock_manager_v1_create(server->wl_display);
  if (!server->lock_manager) return false;
  server->new_lock.notify = session_lock_new;
  wl_signal_add(&server->lock_manager->events.new_lock, &server->new_lock);
  return true;
}

static void session_lock_finish(struct nextspace_server *server)
{
  if (server->lock_client) wl_client_destroy(server->lock_client);
  wl_list_remove(&server->new_lock.link);
  struct nextspace_output *output;
  wl_list_for_each(output, &server->outputs, link) {
    if (output->lock_background) wlr_scene_node_destroy(&output->lock_background->node);
    output->lock_background = NULL;
  }
  wlr_scene_node_destroy(&server->lock_tree->node); server->lock_tree = NULL;
}
