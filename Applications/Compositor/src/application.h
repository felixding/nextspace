/* Client-owned placement; privileged shell control stays separate. MIT license. */
struct nextspace_application_window {
  struct wl_resource *resource;
  struct nextspace_toplevel *view;
  struct wlr_scene_buffer *buffer;
  struct wl_listener outputs_update, buffer_destroy;
  char *output_name;
  int x, y, width, height;
  bool positioned, accepts_focus;
  uint32_t title_state;
  bool drag_prepared;
  uint32_t local_drag_actions, external_drag_actions;
};

static void application_preferred(struct nextspace_application_window *window)
{
  const char *name = window->buffer && window->buffer->primary_output ?
    window->buffer->primary_output->output->name : "";
  if (window->output_name && strcmp(name, window->output_name) == 0) return;
  free(window->output_name);
  window->output_name = strdup(name);
  nextspace_window_v1_send_preferred_output(window->resource, name);
}

static void application_outputs_update(struct wl_listener *listener, void *data)
{
  struct nextspace_application_window *window = wl_container_of(listener, window, outputs_update);
  application_preferred(window);
}

static void application_unwatch(struct nextspace_application_window *window)
{
  if (!window->buffer) return;
  wl_list_remove(&window->outputs_update.link);
  wl_list_remove(&window->buffer_destroy.link);
  window->buffer = NULL;
}

static void application_buffer_destroy(struct wl_listener *listener, void *data)
{
  struct nextspace_application_window *window = wl_container_of(listener, window, buffer_destroy);
  application_unwatch(window);
}

static void application_watch(struct nextspace_application_window *window)
{
  if (window->buffer || !window->view || !window->view->mapped) return;
  window->buffer = view_buffer(window->view);
  if (!window->buffer) return;
  window->outputs_update.notify = application_outputs_update;
  wl_signal_add(&window->buffer->events.outputs_update, &window->outputs_update);
  window->buffer_destroy.notify = application_buffer_destroy;
  wl_signal_add(&window->buffer->node.events.destroy, &window->buffer_destroy);
  application_preferred(window);
}

static void application_position(struct nextspace_toplevel *view)
{
  struct nextspace_application_window *window = view->application_window;
  shell_window_changed(view);
  if (!window || !view->mapped) return;
  application_watch(window);
  struct wlr_surface_state *state = &view_surface(view)->current;
  int x = view->scene_tree->node.x, y = view->scene_tree->node.y;
  if (!window->positioned || window->x != x || window->y != y ||
      window->width != state->width || window->height != state->height) {
    nextspace_window_v1_send_position(window->resource, x, y);
    window->x = x; window->y = y;
    window->width = state->width; window->height = state->height;
    window->positioned = true;
  }
}

static void application_detach(struct nextspace_toplevel *view)
{
  struct nextspace_application_window *window = view->application_window;
  if (!window) return;
  if (view->server->color_pick_window == window)
    color_pick_finish(view->server, NEXTSPACE_WINDOW_V1_COLOR_PICK_PHASE_CANCELLED, 0);
  application_unwatch(window);
  nextspace_window_v1_send_closed(window->resource);
  view->application_window = NULL;
  window->view = NULL;
}

static void application_resource_destroy(struct wl_resource *resource)
{
  struct nextspace_application_window *window = wl_resource_get_user_data(resource);
  if (window->view && window->view->server->color_pick_window == window)
    color_pick_finish(window->view->server, NEXTSPACE_WINDOW_V1_COLOR_PICK_PHASE_CANCELLED, 0);
  application_unwatch(window);
  if (window->view) {
    window->view->application_window = NULL;
    decoration_update(window->view);
  }
  free(window->output_name);
  free(window);
}

static void destroy_application_object(struct wl_client *client, struct wl_resource *resource)
{
  wl_resource_destroy(resource);
}

static void constrain_position(struct nextspace_toplevel *view, int *x, int *y)
{
  if (*x < -1000000 || *x > 1000000 || *y < -1000000 || *y > 1000000) { *x = 0; *y = 0; }
  struct wlr_box geometry;
  view_geometry(view, &geometry);
  struct wlr_box title = {*x, *y, geometry.width > 32 ? geometry.width : 32, 22};
  struct nextspace_output *output, *fallback = NULL;
  wl_list_for_each(output, &view->server->outputs, link) {
    if (!output->wlr_output->enabled) continue;
    if (!fallback) fallback = output;
    struct wlr_box box, visible;
    wlr_output_layout_get_box(view->server->output_layout, output->wlr_output, &box);
    if (wlr_box_intersection(&visible, &title, &box) && visible.width >= 32 && visible.height >= 16)
      return;
  }
  if (fallback) {
    struct wlr_box box;
    wlr_output_layout_get_box(view->server->output_layout, fallback->wlr_output, &box);
    *x = box.x; *y = box.y;
  }
}

static void application_set_position(struct wl_client *client, struct wl_resource *resource,
    int32_t x, int32_t y)
{
  struct nextspace_application_window *window = wl_resource_get_user_data(resource);
  if (!window->view) return;
  if (window->view->maximized || window->view->fullscreen) {
    window->positioned = false;
    application_position(window->view);
    return;
  }
  constrain_position(window->view, &x, &y);
  view_move(window->view, x, y);
  struct nextspace_server *server = window->view->server;
  if (server->grabbed_toplevel == window->view && server->cursor_mode == NEXTSPACE_CURSOR_MOVE) {
    server->grab_x = server->cursor->x - x;
    server->grab_y = server->cursor->y - y;
  }
}

static void application_set_accepts_focus(struct wl_client *client,
    struct wl_resource *resource, uint32_t accepts_focus)
{
  struct nextspace_application_window *window = wl_resource_get_user_data(resource);
  window->accepts_focus = accepts_focus != 0;
  if (window->view && !window->accepts_focus &&
      window->view->server->seat->keyboard_state.focused_surface == view_surface(window->view))
    focus_toplevel(window->view, view_surface(window->view));
}

static void application_set_level(struct wl_client *client, struct wl_resource *resource, int32_t level)
{
  struct nextspace_application_window *window = wl_resource_get_user_data(resource);
  if (window->view) policy_set_level(window->view, level);
}

static void application_order(struct wl_client *client, struct wl_resource *resource,
    int32_t direction, struct wl_resource *reference)
{
  struct nextspace_application_window *window = wl_resource_get_user_data(resource);
  struct nextspace_application_window *other = reference ? wl_resource_get_user_data(reference) : NULL;
  if (!window->view || !direction || (other && !other->view)) return;
  policy_order(window->view, direction > 0, other ? other->view : NULL);
}

static void application_set_minimized(struct wl_client *client, struct wl_resource *resource, uint32_t minimized)
{
  struct nextspace_application_window *window = wl_resource_get_user_data(resource);
  if (window->view) policy_set_minimized(window->view, minimized != 0);
}

static void application_set_presented(struct wl_client *client, struct wl_resource *resource, uint32_t presented)
{
  struct nextspace_application_window *window = wl_resource_get_user_data(resource);
  if (window->view) policy_set_client_presented(window->view, presented != 0);
}

static void application_set_metadata(struct wl_client *client, struct wl_resource *resource,
    uint32_t client_id, uint32_t style, uint32_t title_height)
{
  struct nextspace_application_window *window = wl_resource_get_user_data(resource);
  struct nextspace_toplevel *view = window->view;
  if (!view) return;
  view->has_metadata = true;
  view->client_id = client_id; view->style = style;
  /* Window Maker's default StickyIcons behavior, including miniwindows. */
  view->sticky = (style & (64 | 128)) != 0;
  if (view->mapped) policy_apply_visibility(view);
  view->client_title_height = title_height > 128 ? 128 : title_height;
  view->title_height = view->server_decorated ? view->frame.top : view->client_title_height;
  if (view->shaded) {
    if (!view->title_height) policy_set_shaded(view, false);
    else policy_update_clip(view);
  }
  shell_window_changed(view);
  decoration_update(view);
}

static void application_set_frame_extents(struct wl_client *client, struct wl_resource *resource,
    uint32_t left, uint32_t top, uint32_t right, uint32_t bottom)
{
  struct nextspace_application_window *window = wl_resource_get_user_data(resource);
  if (!window->view || left > 128 || top > 128 || right > 128 || bottom > 128) return;
  window->view->pending_frame = (struct ns_frame_extents){left, top, right, bottom};
  window->view->frame_pending = true;
}

static void application_prepare_drag(struct wl_client *client, struct wl_resource *resource,
    uint32_t local_actions, uint32_t external_actions)
{
  struct nextspace_application_window *window = wl_resource_get_user_data(resource);
  uint32_t valid = WL_DATA_DEVICE_MANAGER_DND_ACTION_COPY | WL_DATA_DEVICE_MANAGER_DND_ACTION_MOVE;
  window->local_drag_actions = local_actions & valid;
  window->external_drag_actions = external_actions & valid;
  window->drag_prepared = true;
}

static void application_set_document_edited(struct wl_client *client, struct wl_resource *resource,
    uint32_t edited)
{
  struct nextspace_application_window *window = wl_resource_get_user_data(resource);
  if (!window->view || window->view->document_edited == (edited != 0)) return;
  window->view->document_edited = edited != 0;
  decoration_update(window->view);
}

static void application_set_title_state(struct wl_client *client, struct wl_resource *resource, uint32_t state)
{
  struct nextspace_application_window *window = wl_resource_get_user_data(resource);
  if (!window->view || state > NEXTSPACE_WINDOW_V1_TITLE_STATE_MAIN || window->title_state == state) return;
  window->title_state = state;
  decoration_update(window->view);
}

static const struct nextspace_window_v1_interface application_window_impl = {
  .destroy = destroy_application_object, .set_position = application_set_position,
  .set_accepts_focus = application_set_accepts_focus,
  .set_level = application_set_level, .order = application_order,
  .set_minimized = application_set_minimized, .set_metadata = application_set_metadata,
  .prepare_drag = application_prepare_drag, .set_presented = application_set_presented,
  .set_frame_extents = application_set_frame_extents,
  .set_document_edited = application_set_document_edited,
  .set_title_state = application_set_title_state,
  .begin_color_pick = color_pick_begin, .cancel_color_pick = color_pick_cancel
};

static void application_get_window(struct wl_client *client, struct wl_resource *manager,
    uint32_t id, struct wl_resource *surface_resource)
{
  struct wlr_surface *surface = wlr_surface_from_resource(surface_resource);
  struct wlr_xdg_toplevel *toplevel = wlr_xdg_toplevel_try_from_wlr_surface(surface);
  if (wl_resource_get_client(surface_resource) != client || !toplevel || !toplevel->base->data) {
    wl_resource_post_error(manager, NEXTSPACE_APPLICATION_V1_ERROR_INVALID_SURFACE,
      "Placement requires an owned xdg toplevel");
    return;
  }
  struct wlr_scene_tree *tree = toplevel->base->data;
  struct nextspace_toplevel *view = tree->node.data;
  if (view->application_window) {
    wl_resource_post_error(manager, NEXTSPACE_APPLICATION_V1_ERROR_DUPLICATE_WINDOW,
      "Surface already has a placement object");
    return;
  }
  struct nextspace_application_window *window = calloc(1, sizeof(*window));
  if (!window) { wl_client_post_no_memory(client); return; }
  window->resource = wl_resource_create(client, &nextspace_window_v1_interface,
    wl_resource_get_version(manager), id);
  if (!window->resource) { free(window); wl_client_post_no_memory(client); return; }
  window->view = view;
  window->accepts_focus = true;
  window->title_state = NEXTSPACE_WINDOW_V1_TITLE_STATE_NORMAL;
  view->application_window = window;
  wl_resource_set_implementation(window->resource, &application_window_impl, window, application_resource_destroy);
  application_watch(window);
  application_preferred(window);
  application_position(view);
}

static const struct nextspace_application_v1_interface application_manager_impl = {
  .destroy = destroy_application_object, .get_window = application_get_window
};

static void application_send_work_areas(struct wl_resource *resource)
{
  if (wl_resource_get_version(resource) < 6) return;
  struct nextspace_server *server = wl_resource_get_user_data(resource);
  nextspace_application_v1_send_work_areas_reset(resource);
  struct nextspace_output *output;
  wl_list_for_each(output, &server->outputs, link) {
    struct wlr_box bounds;
    output_work_area(output, &bounds);
    nextspace_application_v1_send_work_area(resource, output->wlr_output->name,
      bounds.x, bounds.y, bounds.width, bounds.height);
  }
  nextspace_application_v1_send_work_areas_done(resource);
}

static void application_work_areas(struct nextspace_server *server)
{
  struct wl_resource *resource;
  wl_resource_for_each(resource, &server->application_resources) application_send_work_areas(resource);
}

static void application_manager_destroy(struct wl_resource *resource)
{ wl_list_remove(wl_resource_get_link(resource)); }

static void bind_application(struct wl_client *client, void *data, uint32_t version, uint32_t id)
{
  struct wl_resource *resource = wl_resource_create(client, &nextspace_application_v1_interface, version, id);
  if (!resource) { wl_client_post_no_memory(client); return; }
  struct nextspace_server *server = data;
  wl_resource_set_implementation(resource, &application_manager_impl, data, application_manager_destroy);
  wl_list_insert(&server->application_resources, wl_resource_get_link(resource));
  application_send_work_areas(resource);
}

static void create_application_global(struct nextspace_server *server)
{
  wl_global_create(server->wl_display, &nextspace_application_v1_interface, 8, server, bind_application);
}

static void application_layout_changed(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, layout_change);
  color_pick_finish(server, NEXTSPACE_WINDOW_V1_COLOR_PICK_PHASE_CANCELLED, 0);
  if (server->output_applying) return;
  if (server->grabbed_toplevel) reset_cursor_mode(server);
  if (server->background) {
    struct wlr_box bounds;
    wlr_output_layout_get_box(server->output_layout, NULL, &bounds);
    wlr_scene_node_set_position(&server->background->node, bounds.x, bounds.y);
    wlr_scene_rect_set_size(server->background, bounds.width, bounds.height);
  }
  outputs_changed(server);
  struct nextspace_toplevel *view;
  wl_list_for_each(view, &server->toplevels, link) {
    if (policy_size_geometry(view)) continue;
    int x = view->scene_tree->node.x, y = view->scene_tree->node.y;
    constrain_position(view, &x, &y);
    view_move(view, x, y);
  }
}
