/* Toolkit-independent owned-surface protocol transport. MIT license. */
#include "WaylandGeometry.h"
#include "nextspace-application-v1-client-protocol.h"
#include "xdg-activation-v1-client-protocol.h"
#include "xdg-foreign-v2-client-protocol.h"
#include <stdlib.h>
#include <string.h>
#include <wayland-client.h>

struct NXSActivationRequest;
struct NXSGeometrySurface {
  struct NXSGeometrySurface *next;
  NXSGeometryDisplay *display;
  struct wl_surface *surface;
  struct nextspace_surface_geometry_v1 *observer;
  NXSWaylandSurfaceGeometry value;
  NXSGeometryChanged changed;
  void *context;
  int received;
  struct NXSActivationRequest *tokens;
  struct zxdg_exported_v2 *exported;
  char *parent_handle;
};
struct NXSGeometryDisplay {
  NXSWaylandClientAPI api;
  struct wl_display *wayland;
  struct wl_registry *registry;
  struct nextspace_application_v1 *manager;
  struct xdg_activation_v1 *activation;
  struct zxdg_exporter_v2 *exporter;
  struct wl_seat *seat;
  uint32_t seat_name,seat_count;
  NXSGeometrySurface *surfaces;
};
#include "WaylandActivation.inc"
#include "WaylandParent.inc"
/* Same scanner-defined requests, dispatched through the owning client's C
 * API. These helpers contain no knowledge of toolkit objects or geometry. */
static void destroy_resource(NXSGeometryDisplay *display, void *resource, uint32_t opcode)
{
  struct wl_proxy *proxy = resource;
  /* Both extension resources inherit the version 10 manager bound below. */
  display->api.marshal_flags(proxy, opcode, NULL, 10, WL_MARSHAL_FLAG_DESTROY);
}
static void destroy_observer(NXSGeometrySurface *surface)
{
  destroy_resource(surface->display, surface->observer, NEXTSPACE_SURFACE_GEOMETRY_V1_DESTROY);
}
static void geometry_event(void *data, struct nextspace_surface_geometry_v1 *observer,
    int32_t x, int32_t y, int32_t width, int32_t height, uint32_t mapped)
{
  NXSGeometrySurface *surface = data;
  NXSWaylandSurfaceGeometry value = {x, y, width, height, mapped};
  if (surface->received && !memcmp(&surface->value, &value, sizeof(value))) return;
  surface->value = value; surface->received = 1;
  /* The callback may release this object and its display. */
  if (surface->changed) surface->changed(surface->context);
}
static void geometry_closed(void *data, struct nextspace_surface_geometry_v1 *observer)
{
  NXSGeometrySurface *surface = data;
  activation_cancel(surface, 1);
  parent_cancel(surface, 1);
  surface->observer = NULL; surface->surface = NULL;
  surface->value.mapped = 0; surface->received = 1;
  destroy_resource(surface->display, observer, NEXTSPACE_SURFACE_GEOMETRY_V1_DESTROY);
  if (surface->changed) surface->changed(surface->context);
}
static const struct nextspace_surface_geometry_v1_listener geometry_listener = {
  .geometry = geometry_event, .closed = geometry_closed
};
static void attach(NXSGeometrySurface *surface)
{
  NXSGeometryDisplay *display = surface->display;
  if (!display->manager || !surface->surface || surface->observer) return;
  parent_attach(surface);
  struct wl_proxy *manager = (struct wl_proxy *)display->manager;
  surface->observer = (void *)display->api.marshal_flags(manager,
      NEXTSPACE_APPLICATION_V1_GET_SURFACE_GEOMETRY, &nextspace_surface_geometry_v1_interface,
      10, 0, NULL, surface->surface);
  if (surface->observer)
    display->api.add_listener((struct wl_proxy *)surface->observer, (void (**)(void))&geometry_listener, surface);
}
static void areas_reset(void *data, struct nextspace_application_v1 *manager) {}
static void area(void *data, struct nextspace_application_v1 *manager, const char *name,
    int32_t x, int32_t y, int32_t width, int32_t height) {}
static const struct nextspace_application_v1_listener manager_listener = {
  .work_areas_reset = areas_reset, .work_area = area, .work_areas_done = areas_reset
};
static void global(void *data, struct wl_registry *registry, uint32_t name,
    const char *interface, uint32_t version)
{
  NXSGeometryDisplay *display = data;
  if (activation_global(display, registry, name, interface, version)) return;
  if (parent_global(display, registry, name, interface, version)) return;
  if (display->manager || version < 10 || strcmp(interface, "nextspace_application_v1")) return;
  display->manager = (void *)display->api.marshal_flags((struct wl_proxy *)registry,
      WL_REGISTRY_BIND, &nextspace_application_v1_interface, 10, 0,
      name, nextspace_application_v1_interface.name, 10, NULL);
  if (!display->manager) return;
  display->api.add_listener((struct wl_proxy *)display->manager, (void (**)(void))&manager_listener, display);
  for (NXSGeometrySurface *surface = display->surfaces; surface; surface = surface->next) attach(surface);
  display->api.flush(display->wayland);
}
static void global_removed(void *data, struct wl_registry *registry, uint32_t name)
{
  NXSGeometryDisplay *display=data;
  if (name==display->seat_name) {
    display->api.destroy((struct wl_proxy *)display->seat);
    display->seat=NULL;display->seat_name=0;
  }
}
static const struct wl_registry_listener registry_listener = {.global = global, .global_remove = global_removed};
NXSGeometryDisplay *nxs_wayland_geometry_connect(struct wl_display *wayland,
                                               struct wl_display *creation_display)
{
  const NXSWaylandClientAPI api = {sizeof(api), wl_proxy_marshal_flags,
    wl_proxy_add_listener, wl_proxy_destroy, wl_display_flush};
  return nxs_wayland_geometry_connect_with_api(wayland, creation_display, &api);
}
NXSGeometryDisplay *nxs_wayland_geometry_connect_with_api(struct wl_display *wayland,
    struct wl_display *creation_display, const NXSWaylandClientAPI *api)
{
  if (!wayland || !creation_display || !api || api->bytes < sizeof(*api) ||
      !api->marshal_flags || !api->add_listener || !api->destroy || !api->flush) return NULL;
  NXSGeometryDisplay *display = calloc(1, sizeof(*display));
  if (!display) return NULL;
  display->wayland = wayland; display->api = *api;
  struct wl_proxy *proxy = (struct wl_proxy *)creation_display;
  display->registry = (void *)display->api.marshal_flags(proxy, WL_DISPLAY_GET_REGISTRY,
      &wl_registry_interface, 1, 0, NULL);
  if (!display->registry) { free(display); return NULL; }
  display->api.add_listener((struct wl_proxy *)display->registry, (void (**)(void))&registry_listener, display);
  display->api.flush(wayland);
  return display;
}
void nxs_wayland_geometry_disconnect(NXSGeometryDisplay *display, int proxies_valid)
{
  if (!display) return;
  while (display->surfaces) {
    NXSGeometrySurface *surface = display->surfaces;
    display->surfaces = surface->next;
    activation_cancel(surface, proxies_valid);
    parent_cancel(surface, proxies_valid);
    if (proxies_valid && surface->observer) destroy_observer(surface);
    free(surface);
  }
  if (proxies_valid) {
    if (display->activation) activation_destroy(display, display->activation, XDG_ACTIVATION_V1_DESTROY);
    if (display->exporter) activation_destroy(display, display->exporter, ZXDG_EXPORTER_V2_DESTROY);
    if (display->seat) display->api.destroy((struct wl_proxy *)display->seat);
    if (display->manager) destroy_resource(display, display->manager, NEXTSPACE_APPLICATION_V1_DESTROY);
    display->api.destroy((struct wl_proxy *)display->registry);
  }
  free(display);
}
NXSGeometrySurface *nxs_wayland_geometry_observe(NXSGeometryDisplay *display, struct wl_surface *wayland,
                                               NXSGeometryChanged changed, void *context)
{
  if (!display || !wayland) return NULL;
  NXSGeometrySurface *surface = calloc(1, sizeof(*surface));
  if (!surface) return NULL;
  surface->display = display; surface->surface = wayland;
  surface->changed = changed; surface->context = context;
  surface->next = display->surfaces; display->surfaces = surface;
  attach(surface); display->api.flush(display->wayland);
  return surface;
}
void nxs_wayland_geometry_rebind(NXSGeometrySurface *surface, struct wl_surface *wayland)
{
  if (!surface || surface->surface == wayland) return;
  activation_cancel(surface, 1);
  parent_cancel(surface, 1);
  if (surface->observer) destroy_observer(surface);
  surface->observer = NULL; surface->surface = wayland; surface->received = 0;
  surface->value = (NXSWaylandSurfaceGeometry){0};
  attach(surface); surface->display->api.flush(surface->display->wayland);
}
void nxs_wayland_geometry_unobserve(NXSGeometrySurface *surface)
{
  if (!surface) return;
  activation_cancel(surface, 1);
  parent_cancel(surface, 1);
  NXSGeometrySurface **link = &surface->display->surfaces;
  while (*link && *link != surface) link = &(*link)->next;
  if (*link) *link = surface->next;
  if (surface->observer) destroy_observer(surface);
  free(surface);
}
int nxs_wayland_geometry_read(NXSGeometrySurface *surface, NXSWaylandSurfaceGeometry *value)
{
  if (!surface || !value || !surface->received) return 0;
  *value = surface->value; return 1;
}
