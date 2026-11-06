/* KDE app-menu address metadata for application-owned surfaces. MIT license.
 * Menu interpretation, D-Bus authentication and native controls live elsewhere. */
struct nextspace_appmenu {
  struct wl_resource *resource;
  struct nextspace_server *server;
  struct wlr_surface *surface;
  struct wl_listener surface_destroy;
  struct wl_list link;
  char *service, *path;
};

static struct nextspace_appmenu *appmenu_for_surface(struct nextspace_server *server,
    struct wlr_surface *surface)
{
  struct nextspace_appmenu *menu;
  wl_list_for_each(menu, &server->appmenus, link)
    if (menu->surface == surface) return menu;
  return NULL;
}

static void appmenu_changed(struct nextspace_server *server, struct wlr_surface *surface)
{
  struct nextspace_toplevel *view = view_for_surface(server, surface);
  if (!view || view_surface(view) != surface) return;
  /* The regular window snapshot carries the new address atomically with its
   * owner PID and focus state. No second metadata cache can become stale. */
  view->shell_state.valid = false;
  shell_window_changed(view);
}

static void appmenu_surface_destroy(struct wl_listener *listener, void *data)
{
  struct nextspace_appmenu *menu = wl_container_of(listener, menu, surface_destroy);
  wl_list_remove(&menu->surface_destroy.link);
  menu->surface = NULL;
  /* The protocol object stays inert until its owner releases it. The window's
   * ordinary closed event retires the address from the shell snapshot. */
}

static void appmenu_destroy(struct wl_resource *resource)
{
  struct nextspace_appmenu *menu = wl_resource_get_user_data(resource);
  struct wlr_surface *surface = menu->surface;
  wl_list_remove(&menu->link);
  if (surface) wl_list_remove(&menu->surface_destroy.link);
  if (surface) appmenu_changed(menu->server, surface);
  free(menu->service); free(menu->path); free(menu);
}

static void appmenu_release(struct wl_client *client, struct wl_resource *resource)
{ wl_resource_destroy(resource); }

static void appmenu_set_address(struct wl_client *client, struct wl_resource *resource,
    const char *service, const char *path)
{
  struct nextspace_appmenu *menu = wl_resource_get_user_data(resource);
  if (!menu->surface) return;
  /* Bounded untrusted metadata only. Consumers use their D-Bus implementation
   * to validate names/paths and authenticate the resolved service owner. */
  if (strlen(service) > 255 || strlen(path) > 4096) {
    wl_resource_post_error(resource, 0, "app-menu address exceeds metadata limits"); return;
  }
  char *service_copy = strdup(service), *path_copy = strdup(path);
  if (!service_copy || !path_copy) {
    free(service_copy); free(path_copy); wl_client_post_no_memory(client); return;
  }
  free(menu->service); free(menu->path);
  menu->service = service_copy; menu->path = path_copy;
  appmenu_changed(menu->server, menu->surface);
}

static const struct org_kde_kwin_appmenu_interface appmenu_impl = {
  .set_address = appmenu_set_address, .release = appmenu_release
};

static void appmenu_create(struct wl_client *client, struct wl_resource *resource,
    uint32_t id, struct wl_resource *surface_resource)
{
  struct nextspace_server *server = wl_resource_get_user_data(resource);
  if (wl_resource_get_client(surface_resource) != client) {
    wl_resource_post_error(resource, 0, "app-menu surface belongs to another client"); return;
  }
  struct wlr_surface *surface = wlr_surface_from_resource(surface_resource);
  struct nextspace_appmenu *menu = calloc(1, sizeof(*menu));
  if (!menu) { wl_client_post_no_memory(client); return; }
  menu->resource = wl_resource_create(client, &org_kde_kwin_appmenu_interface,
    wl_resource_get_version(resource), id);
  if (!menu->resource) { free(menu); wl_client_post_no_memory(client); return; }
  menu->server = server; menu->surface = surface;
  /* Clients may create a replacement before releasing the old object. Keep
   * the first surviving object's address until its owner releases it, as in
   * KWin; neither the protocol nor that lifecycle requires uniqueness. */
  wl_list_insert(server->appmenus.prev, &menu->link);
  menu->surface_destroy.notify = appmenu_surface_destroy;
  wl_signal_add(&surface->events.destroy, &menu->surface_destroy);
  wl_resource_set_implementation(menu->resource, &appmenu_impl, menu, appmenu_destroy);
}

static const struct org_kde_kwin_appmenu_manager_interface appmenu_manager_impl = {
  .create = appmenu_create, .release = appmenu_release
};

static void appmenu_bind(struct wl_client *client, void *data, uint32_t version, uint32_t id)
{
  struct wl_resource *resource = wl_resource_create(client,
    &org_kde_kwin_appmenu_manager_interface, version, id);
  if (!resource) { wl_client_post_no_memory(client); return; }
  wl_resource_set_implementation(resource, &appmenu_manager_impl, data, NULL);
}

static bool appmenu_init(struct nextspace_server *server)
{
  return wl_global_create(server->wl_display, &org_kde_kwin_appmenu_manager_interface,
    2, server, appmenu_bind) != NULL;
}
