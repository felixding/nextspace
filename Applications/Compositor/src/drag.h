/* Serial-authorized pointer drags; wlroots owns negotiation and transfer.
   SPDX-License-Identifier: MIT */
struct nextspace_drag_context {
  struct nextspace_server *server;
  struct wlr_drag *drag;
  struct wlr_surface *origin;
  uint32_t id;
  bool prepared;
  uint32_t local_actions, external_actions;
  struct wl_listener focus, drop, destroy, origin_destroy;
};

static void cancel_pointer_drag(struct nextspace_server *server)
{
  struct wlr_drag *drag = server->seat->drag;
  if (!drag) return;
  if (drag->source) wlr_data_source_destroy(drag->source);
  else wlr_seat_keyboard_end_grab(server->seat);
}

static void drag_cancel_origin(struct nextspace_toplevel *view)
{
  struct nextspace_drag_context *context = view->server->drag_context;
  if (context && context->origin && view_for_surface(view->server, context->origin) == view)
    cancel_pointer_drag(view->server);
}

static void drag_context_send(struct nextspace_drag_context *context,
    struct wlr_surface *surface, uint32_t phase)
{
  struct nextspace_server *server = context->server;
  struct nextspace_toplevel *view = view_for_surface(server, surface);
  struct nextspace_application_window *window = view ? view->application_window : NULL;
  if (!window || wl_resource_get_version(window->resource) < 4 ||
      wl_resource_get_client(window->resource) != wl_resource_get_client(surface->resource)) return;
  bool local = context->drag->focus_client && context->drag->seat_client &&
    context->drag->focus_client == context->drag->seat_client;
  nextspace_window_v1_send_drag_context(window->resource, surface->resource,
    context->id, phase, local, wl_fixed_from_double(server->cursor->x), wl_fixed_from_double(server->cursor->y));
}

static void drag_context_focus(struct wl_listener *listener, void *data)
{
  struct nextspace_drag_context *context = wl_container_of(listener, context, focus);
  if (context->origin) drag_context_send(context, context->origin, NEXTSPACE_WINDOW_V1_DRAG_PHASE_MOTION);
  if (context->drag->focus) drag_context_send(context, context->drag->focus, NEXTSPACE_WINDOW_V1_DRAG_PHASE_ENTER);
}

static void drag_pointer_moved(struct nextspace_server *server)
{
  struct nextspace_drag_context *context = server->drag_context;
  if (!context) return;
  if (context->origin) drag_context_send(context, context->origin, NEXTSPACE_WINDOW_V1_DRAG_PHASE_MOTION);
}

static void drag_target_actions(struct nextspace_server *server, struct wlr_surface *surface)
{
  struct nextspace_drag_context *context = server->drag_context;
  if (!context || !context->prepared || !context->drag->source) return;
  bool local = surface && context->drag->seat_client &&
    wl_resource_get_client(surface->resource) == context->drag->seat_client->client;
  /* Choose before wlroots creates the destination's offer. An existing offer
     never changes connection identity while it retains pointer focus. */
  context->drag->source->actions = local ? context->local_actions : context->external_actions;
}

static void drag_context_drop(struct wl_listener *listener, void *data)
{
  struct nextspace_drag_context *context = wl_container_of(listener, context, drop);
  if (context->origin) drag_context_send(context, context->origin, NEXTSPACE_WINDOW_V1_DRAG_PHASE_DROP);
}

static void drag_context_destroy(struct wl_listener *listener, void *data)
{
  struct nextspace_drag_context *context = wl_container_of(listener, context, destroy);
  if (context->origin) {
    if (!context->drag->dropped) drag_context_send(context, context->origin, NEXTSPACE_WINDOW_V1_DRAG_PHASE_CANCEL);
    wl_list_remove(&context->origin_destroy.link);
  }
  wl_list_remove(&context->focus.link);
  wl_list_remove(&context->drop.link); wl_list_remove(&context->destroy.link);
  context->server->drag_context = NULL;
  free(context);
}

static void drag_context_origin_destroy(struct wl_listener *listener, void *data)
{
  struct nextspace_drag_context *context = wl_container_of(listener, context, origin_destroy);
  wl_list_remove(&context->origin_destroy.link); context->origin = NULL;
  /* Closing the source window cancels its gesture even if the process lives. */
  cancel_pointer_drag(context->server);
}

static bool drag_context_create(struct nextspace_server *server, struct wlr_seat_request_start_drag_event *event)
{
  struct nextspace_drag_context *context = calloc(1, sizeof(*context));
  if (!context) return false;
  context->server = server; context->drag = event->drag; context->origin = event->origin;
  struct nextspace_toplevel *view = view_for_surface(server, event->origin);
  struct nextspace_application_window *window = view ? view->application_window : NULL;
  if (window && window->drag_prepared && event->drag->source && event->drag->source->actions >= 0) {
    context->prepared = true;
    context->local_actions = window->local_drag_actions & event->drag->source->actions;
    context->external_actions = window->external_drag_actions & event->drag->source->actions;
    window->drag_prepared = false;
  }
  context->id = ++server->next_drag_id;
  if (!context->id) context->id = ++server->next_drag_id;
  context->focus.notify = drag_context_focus; wl_signal_add(&event->drag->events.focus, &context->focus);
  context->drop.notify = drag_context_drop; wl_signal_add(&event->drag->events.drop, &context->drop);
  context->destroy.notify = drag_context_destroy; wl_signal_add(&event->drag->events.destroy, &context->destroy);
  context->origin_destroy.notify = drag_context_origin_destroy;
  wl_signal_add(&event->origin->events.destroy, &context->origin_destroy);
  server->drag_context = context;
  drag_context_send(context, event->origin, NEXTSPACE_WINDOW_V1_DRAG_PHASE_BEGIN);
  return true;
}

static bool drag_icon_accepts_input(struct wlr_scene_buffer *buffer, double *sx, double *sy)
{ return false; }

static void drag_icon_ignore_input(struct wlr_scene_buffer *buffer, int x, int y, void *data)
{ buffer->point_accepts_input = drag_icon_accepts_input; }

static void drag_icon_update(struct nextspace_server *server)
{
  if (!server->drag_icon) return;
  wlr_scene_node_set_position(&server->drag_icon->node, server->cursor->x, server->cursor->y);
  wlr_scene_node_for_each_buffer(&server->drag_icon->node, drag_icon_ignore_input, NULL);
}

static void drag_icon_committed(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, drag_icon_commit);
  drag_icon_update(server);
}

static void drag_icon_destroy(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, drag_icon_destroy);
  wl_list_remove(&server->drag_icon_destroy.link);
  wl_list_remove(&server->drag_icon_commit.link);
  server->drag_icon = NULL;
}

static void seat_request_start_drag(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, request_start_drag);
  struct wlr_seat_request_start_drag_event *event = data;
  if (server->locked || !wlr_seat_validate_pointer_grab_serial(server->seat, event->origin, event->serial) ||
      !drag_context_create(server, event)) {
    if (event->drag->source) wlr_data_source_destroy(event->drag->source);
    else event->drag->pointer_grab.interface->cancel(&event->drag->pointer_grab);
    return;
  }
  wlr_seat_start_pointer_drag(server->seat, event->drag, event->serial);
  /* The source callback can run while the pointer moves under its button grab.
     Pick the current target now, even if the pointer has since stopped. */
  struct timespec now;
  clock_gettime(CLOCK_MONOTONIC, &now);
  process_cursor_motion(server, now.tv_sec * 1000 + now.tv_nsec / 1000000);
  if (event->drag->icon) {
    /* Ordinary client levels stop at 1000. Drag images never intercept input. */
    struct wlr_scene_tree *layer = policy_layer(server, 1001);
    if (!layer) return;
    server->drag_icon = wlr_scene_drag_icon_create(layer, event->drag->icon);
    if (!server->drag_icon) return;
    server->drag_icon_commit.notify = drag_icon_committed;
    wl_signal_add(&event->drag->icon->surface->events.commit, &server->drag_icon_commit);
    server->drag_icon_destroy.notify = drag_icon_destroy;
    wl_signal_add(&server->drag_icon->node.events.destroy, &server->drag_icon_destroy);
    drag_icon_update(server);
  }
}
