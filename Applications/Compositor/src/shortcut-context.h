/* Read-only focused toplevel for the session's shortcut mapper. MIT license. */
static void shortcut_context_update(struct nextspace_server *server)
{
  if (!server->shortcut_client) return;
  struct nextspace_toplevel *view = server->locked ? NULL :
    view_for_surface(server, server->seat->keyboard_state.focused_surface);
  if (server->shortcut_view != view) {
    if (server->shortcut_handle)
      wlr_foreign_toplevel_handle_v1_destroy(server->shortcut_handle);
    server->shortcut_handle = NULL;
    server->shortcut_view = NULL;
    if (!view) return;
    server->shortcut_handle = wlr_foreign_toplevel_handle_v1_create(server->shortcut_manager);
    if (!server->shortcut_handle) return;
    server->shortcut_view = view;
  }
  if (!view) return;
  /* Modal toplevels may omit their app ID. Resolve through their xdg parent. */
  struct wlr_xdg_toplevel *owner = view->xdg_toplevel;
  while ((!owner->app_id || !*owner->app_id) && owner->parent)
    owner = owner->parent;
  wlr_foreign_toplevel_handle_v1_set_app_id(server->shortcut_handle, owner->app_id ?: "");
  wlr_foreign_toplevel_handle_v1_set_title(server->shortcut_handle, view_title(view) ?: "");
  wlr_foreign_toplevel_handle_v1_set_activated(server->shortcut_handle, true);
}

static void shortcut_focus_changed(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, shortcut_focus);
  shortcut_context_update(server);
}

static void shortcut_client_destroy(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, shortcut_client_destroy);
  wl_list_remove(&listener->link);
  server->shortcut_client = NULL;
  if (server->shortcut_handle)
    wlr_foreign_toplevel_handle_v1_destroy(server->shortcut_handle);
  server->shortcut_handle = NULL;
  server->shortcut_view = NULL;
}
