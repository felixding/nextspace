/* Managed rootless Xwayland. SPDX-License-Identifier: MIT */
static void xwayland_output_position(struct wl_client *client, int32_t *x, int32_t *y, void *data)
{
  struct nextspace_server *server = data;
  if (server->xwayland && client == server->xwayland->server->client) {
    *x -= server->xwayland_origin_x; *y -= server->xwayland_origin_y;
  }
}

static void xwayland_outputs_changed(struct nextspace_server *server)
{
  if (!server->xwayland) return;
  struct wlr_box bounds;
  wlr_output_layout_get_box(server->output_layout, NULL, &bounds);
  int x = bounds.x < 0 ? bounds.x : 0, y = bounds.y < 0 ? bounds.y : 0;
  if (x == server->xwayland_origin_x && y == server->xwayland_origin_y) return;
  server->xwayland_origin_x = x; server->xwayland_origin_y = y;
  struct nextspace_toplevel *view;
  wl_list_for_each(view, &server->toplevels, link) {
    if (view->xsurface && view->scene_tree)
      xwayland_configure(view, view->scene_tree->node.x, view->scene_tree->node.y,
        view->xsurface->width, view->xsurface->height);
  }
  wlr_xdg_output_manager_v1_refresh(server->xdg_output_manager);
}

static void xsurface_buffer_input(struct wlr_scene_buffer *buffer, int x, int y, void *data)
{
  struct nextspace_toplevel *view = data;
  if (!view->x_accepts_input) view->x_accepts_input = buffer->point_accepts_input;
  buffer->point_accepts_input = view->x_drag_icon ? drag_icon_accepts_input : view->x_accepts_input;
}

static void xsurface_update_type(struct nextspace_toplevel *view)
{
  view->x_drag_icon = wlr_xwayland_surface_is_drag_icon(view->xsurface);
  if (!view->scene_tree) return;
  view->level = view->x_drag_icon ? 1001 : 0;
  wlr_scene_node_reparent(&view->scene_tree->node,
    policy_layer(view->server, policy_effective_level(view,
      view_for_surface(view->server, view->server->seat->keyboard_state.focused_surface))));
  wlr_scene_node_for_each_buffer(&view->scene_tree->node, xsurface_buffer_input, view);
}

static void xsurface_type(struct wl_listener *listener, void *data)
{
  struct nextspace_toplevel *view = wl_container_of(listener, view, set_window_type);
  xsurface_update_type(view);
}

static void xsurface_update_drag_icons(struct nextspace_server *server)
{
  struct nextspace_toplevel *view;
  wl_list_for_each(view, &server->toplevels, link)
    if (view->xsurface && view->x_drag_icon != wlr_xwayland_surface_is_drag_icon(view->xsurface))
      xsurface_update_type(view);
}

static void xsurface_scene_destroy(struct wl_listener *listener, void *data)
{
  struct nextspace_toplevel *view = wl_container_of(listener, view, commit);
  wl_list_remove(&view->commit.link);
  view->scene_tree = NULL;
  view->fullscreen_background = NULL;
}

static void xsurface_geometry(struct wl_listener *listener, void *data)
{
  struct nextspace_toplevel *view = wl_container_of(listener, view, set_geometry);
  if (view->scene_tree)
    wlr_scene_node_set_position(&view->scene_tree->node, view->xsurface->x + view->server->xwayland_origin_x,
      view->xsurface->y + view->server->xwayland_origin_y);
  shell_window_changed(view);
}

static void xsurface_map(struct wl_listener *listener, void *data)
{
  struct nextspace_toplevel *view = wl_container_of(listener, view, map);
  if (view->mapped) return;
  wlr_scene_node_set_position(&view->scene_tree->node, view->xsurface->x + view->server->xwayland_origin_x,
      view->xsurface->y + view->server->xwayland_origin_y);
  view->mapped = true;
  xsurface_type(&view->set_window_type, NULL);
  if (view->xsurface->parent && view->xsurface->parent->data)
    view->desktop = ((struct nextspace_toplevel *)view->xsurface->parent->data)->desktop;
  wl_list_insert(&view->server->toplevels, &view->link);
  policy_set_size_state(view, view->xsurface->maximized_vert && view->xsurface->maximized_horz ? MAXIMIZE_BOTH : 0,
    view->xsurface->fullscreen, NULL);
  wlr_scene_node_set_enabled(&view->scene_tree->node, policy_visible(view));
  if (!view->x_drag_icon && (!view->xsurface->override_redirect ||
      wlr_xwayland_or_surface_wants_focus(view->xsurface)))
    focus_toplevel(view, view_surface(view));
}

static void xsurface_dissociate(struct wl_listener *listener, void *data)
{
  struct nextspace_toplevel *view = wl_container_of(listener, view, dissociate);
  if (!view->associated) return;
  view->associated = false;
  if (view->mapped) xdg_toplevel_unmap(&view->unmap, NULL);
  wl_list_remove(&view->map.link);
  wl_list_remove(&view->unmap.link);
  if (view->scene_tree) wlr_scene_node_destroy(&view->scene_tree->node);
}

static void xsurface_associate(struct wl_listener *listener, void *data)
{
  struct nextspace_toplevel *view = wl_container_of(listener, view, associate);
  view->associated = true;
  view->scene_tree = wlr_scene_subsurface_tree_create(policy_layer(view->server, 0), view_surface(view));
  view->scene_tree->node.data = view;
  wlr_scene_node_set_enabled(&view->scene_tree->node, policy_visible(view));
  view->commit.notify = xsurface_scene_destroy;
  wl_signal_add(&view->scene_tree->node.events.destroy, &view->commit);
  view->map.notify = xsurface_map;
  wl_signal_add(&view_surface(view)->events.map, &view->map);
  view->unmap.notify = xdg_toplevel_unmap;
  wl_signal_add(&view_surface(view)->events.unmap, &view->unmap);
  /* Association may follow the first buffer commit or an existing map. */
  if (wlr_surface_has_buffer(view_surface(view))) {
    wlr_surface_map(view_surface(view));
    if (!view->mapped) xsurface_map(&view->map, NULL);
  }
}

static void xsurface_configure(struct wl_listener *listener, void *data)
{
  struct nextspace_toplevel *view = wl_container_of(listener, view, request_configure);
  struct wlr_xwayland_surface_configure_event *event = data;
  wlr_log(WLR_DEBUG, "Window %u requested geometry %dx%d at %d,%d (mask %u)", view->id,
    event->width, event->height, event->x, event->y, event->mask);
  if (policy_size_geometry(view)) return;
  struct nextspace_server *server = view->server;
  if (server->grabbed_toplevel == view && server->cursor_mode == NEXTSPACE_CURSOR_MOVE &&
      server->grab_maximized && view->normal_geometry.width > 0 && view->normal_geometry.height > 0) {
    /* GTK can request its old normal size after receiving the unmaximize
       notification. The compositor owns geometry throughout this drag. */
    xwayland_configure(view, view->scene_tree->node.x,
      view->scene_tree->node.y, view->normal_geometry.width, view->normal_geometry.height);
    return;
  }
  xwayland_configure(view, event->x + server->xwayland_origin_x, event->y + server->xwayland_origin_y,
    event->width, event->height);
}

static void xsurface_move(struct wl_listener *listener, void *data)
{
  struct nextspace_toplevel *view = wl_container_of(listener, view, request_move);
  if (view->mapped) begin_interactive(view, NEXTSPACE_CURSOR_MOVE, 0, false);
}

static void xsurface_resize(struct wl_listener *listener, void *data)
{
  struct nextspace_toplevel *view = wl_container_of(listener, view, request_resize);
  struct wlr_xwayland_resize_event *event = data;
  if (view->mapped) begin_interactive(view, NEXTSPACE_CURSOR_RESIZE, event->edges, false);
}

static void xsurface_minimize(struct wl_listener *listener, void *data)
{
  struct nextspace_toplevel *view = wl_container_of(listener, view, request_minimize);
  struct wlr_xwayland_minimize_event *event = data;
  if (view->scene_tree) policy_set_minimized(view, event->minimize);
}

static void xsurface_maximize(struct wl_listener *listener, void *data)
{
  struct nextspace_toplevel *view = wl_container_of(listener, view, request_maximize);
  policy_set_size_state(view, view->xsurface->maximized_vert && view->xsurface->maximized_horz ? MAXIMIZE_BOTH : 0,
    view->fullscreen, NULL);
}

static void xsurface_fullscreen(struct wl_listener *listener, void *data)
{
  struct nextspace_toplevel *view = wl_container_of(listener, view, request_fullscreen);
  policy_set_fullscreen(view, view->xsurface->fullscreen, NULL);
}

static void xsurface_destroy(struct wl_listener *listener, void *data)
{
  struct nextspace_toplevel *view = wl_container_of(listener, view, destroy);
  xsurface_dissociate(&view->dissociate, NULL);
  wl_list_remove(&view->associate.link);
  wl_list_remove(&view->dissociate.link);
  wl_list_remove(&view->request_configure.link);
  wl_list_remove(&view->request_move.link);
  wl_list_remove(&view->request_resize.link);
  wl_list_remove(&view->request_minimize.link);
  wl_list_remove(&view->request_maximize.link);
  wl_list_remove(&view->request_fullscreen.link);
  wl_list_remove(&view->set_geometry.link);
  wl_list_remove(&view->set_window_type.link);
  wl_list_remove(&view->set_title.link);
  wl_list_remove(&view->set_app_id.link);
  wl_list_remove(&view->destroy.link);
  free(view->shell_state.app_id);
  free(view->shell_state.title);
  free(view);
}

static void server_new_xsurface(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, new_xsurface);
  struct nextspace_toplevel *view = calloc(1, sizeof(*view));
  view->server = server;
  view->desktop = server->desktop;
  view->id = ++server->next_window_id;
  view->xsurface = data;
  view->xsurface->data = view;
  view->associate.notify = xsurface_associate;
  wl_signal_add(&view->xsurface->events.associate, &view->associate);
  view->dissociate.notify = xsurface_dissociate;
  wl_signal_add(&view->xsurface->events.dissociate, &view->dissociate);
  view->request_configure.notify = xsurface_configure;
  wl_signal_add(&view->xsurface->events.request_configure, &view->request_configure);
  view->request_move.notify = xsurface_move;
  wl_signal_add(&view->xsurface->events.request_move, &view->request_move);
  view->request_resize.notify = xsurface_resize;
  wl_signal_add(&view->xsurface->events.request_resize, &view->request_resize);
  view->request_minimize.notify = xsurface_minimize;
  wl_signal_add(&view->xsurface->events.request_minimize, &view->request_minimize);
  view->request_maximize.notify = xsurface_maximize;
  wl_signal_add(&view->xsurface->events.request_maximize, &view->request_maximize);
  view->request_fullscreen.notify = xsurface_fullscreen;
  wl_signal_add(&view->xsurface->events.request_fullscreen, &view->request_fullscreen);
  view->set_geometry.notify = xsurface_geometry;
  wl_signal_add(&view->xsurface->events.set_geometry, &view->set_geometry);
  view->set_window_type.notify = xsurface_type;
  wl_signal_add(&view->xsurface->events.set_window_type, &view->set_window_type);
  view->set_title.notify = shell_metadata_changed;
  wl_signal_add(&view->xsurface->events.set_title, &view->set_title);
  view->set_app_id.notify = shell_app_id_changed;
  wl_signal_add(&view->xsurface->events.set_class, &view->set_app_id);
  view->destroy.notify = xsurface_destroy;
  wl_signal_add(&view->xsurface->events.destroy, &view->destroy);
}

static void xwayland_ready(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, xwayland_ready);
  setenv("DISPLAY", server->xwayland->display_name, true);
  printf("DISPLAY=%s\n", server->xwayland->display_name);
  fflush(stdout);
}

static bool filter_global(const struct wl_client *client, const struct wl_global *global, void *data)
{
  struct nextspace_server *server = data;
  if (global == server->shell_global) return client == server->shell_client;
  if (server->lock_manager && global == server->lock_manager->global) return client == server->lock_client;
  if ((server->input_method_manager && global == server->input_method_manager->global) ||
      (server->virtual_keyboard_manager && global == server->virtual_keyboard_manager->global))
    return client == server->input_method_client;
  if (server->xwayland && global == server->xwayland->shell_v1->global)
    return client == server->xwayland->server->client;
  return true;
}

static bool start_xwayland(struct nextspace_server *server)
{
  /* wlroots owns the one XWM and native/X selection bridge for this server. */
  unsetenv("DISPLAY");
  server->xwayland = wlr_xwayland_create(server->wl_display, server->compositor, false);
  if (!server->xwayland) return false;
  wlr_xwayland_set_seat(server->xwayland, server->seat);
  server->xdg_output_manager->map_position = xwayland_output_position;
  server->xdg_output_manager->map_position_data = server;
  xwayland_outputs_changed(server);
  server->new_xsurface.notify = server_new_xsurface;
  wl_signal_add(&server->xwayland->events.new_surface, &server->new_xsurface);
  server->xwayland_ready.notify = xwayland_ready;
  wl_signal_add(&server->xwayland->events.ready, &server->xwayland_ready);
  return true;
}
