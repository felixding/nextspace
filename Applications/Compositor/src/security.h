/* Private native session capabilities. MIT license. */
static void capture_client_destroy(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, capture_client_destroy);
  wl_list_remove(&server->capture_client_destroy.link);
  server->capture_client = NULL;
}

static void capture_revoke(struct nextspace_server *server)
{
  if (server->capture_client) wl_client_destroy(server->capture_client);
}

static bool filter_global(const struct wl_client *client, const struct wl_global *global, void *data)
{
  struct nextspace_server *server = data;
  if (global == server->shell_global) return client == server->shell_client;
  if (server->screencopy_manager && global == server->screencopy_manager->global)
    return client == server->capture_client && !server->locked;
  if (server->lock_manager && global == server->lock_manager->global) return client == server->lock_client;
  if ((server->input_method_manager && global == server->input_method_manager->global) ||
      (server->virtual_keyboard_manager && global == server->virtual_keyboard_manager->global))
    return client == server->input_method_client;
  return true;
}
