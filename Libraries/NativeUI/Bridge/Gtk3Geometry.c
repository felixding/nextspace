/* Owned GTK3/Wayland geometry. No widget rendering or toolkit layout here. */
#include "Gtk3Geometry.h"
#include "nextspace-application-v1-client-protocol.h"
#include <dlfcn.h>
#include <glib-object.h>
#include <stdlib.h>
#include <string.h>
#include <wayland-client.h>

struct GeometryDisplay;
struct GeometryWindow {
  struct GeometryWindow *next;
  struct GeometryDisplay *display;
  void *gdk;
  struct wl_surface *surface;
  struct nextspace_surface_geometry_v1 *observer;
  NXSGtk3SurfaceGeometry geometry;
  NXSGtk3GeometryChanged changed;
  guint idle;
  int received;
};
struct GeometryDisplay {
  struct GeometryDisplay *next;
  void *gdk;
  struct wl_display *wayland;
  struct wl_registry *registry;
  struct nextspace_application_v1 *manager;
  struct GeometryWindow *windows;
  int alive;
};
static struct GeometryDisplay *displays;
static GType (*wayland_window_type)(void);
static void *(*window_display)(void *);
static struct wl_display *(*wayland_display)(void *);
static struct wl_surface *(*wayland_surface)(void *);
static int (*window_destroyed)(void *),(*window_viewable)(void *),(*window_type)(void *);
static int load_gdk(void)
{
  if (wayland_window_type) return 1;
  void *type = dlsym(RTLD_DEFAULT, "gdk_wayland_window_get_type");
  window_display = dlsym(RTLD_DEFAULT, "gdk_window_get_display");
  wayland_display = dlsym(RTLD_DEFAULT, "gdk_wayland_display_get_wl_display");
  wayland_surface = dlsym(RTLD_DEFAULT, "gdk_wayland_window_get_wl_surface");
  window_type = dlsym(RTLD_DEFAULT, "gdk_window_get_window_type");
  window_destroyed = dlsym(RTLD_DEFAULT, "gdk_window_is_destroyed");
  window_viewable = dlsym(RTLD_DEFAULT, "gdk_window_is_viewable");
  if (!type || !window_display || !wayland_display || !wayland_surface ||
      !window_destroyed || !window_viewable || !window_type) return 0;
  wayland_window_type = type; return 1;
}
static gboolean notify_idle(gpointer data)
{
  struct GeometryWindow *window = data;
  window->idle = 0;
  if (window->display->alive && !window_destroyed(window->gdk) && window->changed)
    window->changed(window->gdk);
  return G_SOURCE_REMOVE;
}
static void notify(struct GeometryWindow *window)
{
  if (!window->idle && window->changed)
    window->idle = g_idle_add(notify_idle, window);
}
static void geometry_event(void *data, struct nextspace_surface_geometry_v1 *observer,
    int32_t x, int32_t y, int32_t width, int32_t height, uint32_t mapped)
{
  struct GeometryWindow *window = data;
  NXSGtk3SurfaceGeometry value = {x, y, width, height, mapped};
  if (window->received && !memcmp(&window->geometry, &value, sizeof(value))) return;
  window->geometry = value; window->received = 1; notify(window);
}
static void geometry_closed(void *data, struct nextspace_surface_geometry_v1 *observer)
{
  struct GeometryWindow *window = data;
  window->observer = NULL; window->surface = NULL;
  window->geometry.mapped = 0; window->received = 0;
  nextspace_surface_geometry_v1_destroy(observer); notify(window);
}
static const struct nextspace_surface_geometry_v1_listener geometry_listener = {
  .geometry = geometry_event, .closed = geometry_closed
};
static void attach(struct GeometryWindow *window)
{
  struct GeometryDisplay *display = window->display;
  if (!display->alive || !display->manager || window_destroyed(window->gdk) ||
      !window_viewable(window->gdk)) return;
  struct wl_surface *surface = wayland_surface(window->gdk);
  if (surface == window->surface && window->observer) return;
  if (window->observer) nextspace_surface_geometry_v1_destroy(window->observer);
  window->observer = NULL; window->surface = surface; window->received = 0;
  if (!surface) return;
  window->observer = nextspace_application_v1_get_surface_geometry(display->manager, surface);
  if (window->observer) nextspace_surface_geometry_v1_add_listener(window->observer, &geometry_listener, window);
  wl_display_flush(display->wayland);
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
  struct GeometryDisplay *display = data;
  if (display->manager || version < 10 || strcmp(interface, "nextspace_application_v1")) return;
  display->manager = wl_registry_bind(registry, name, &nextspace_application_v1_interface, 10);
  nextspace_application_v1_add_listener(display->manager, &manager_listener, display);
  for (struct GeometryWindow *window = display->windows; window; window = window->next) attach(window);
}
static void global_removed(void *data, struct wl_registry *registry, uint32_t name) {}
static const struct wl_registry_listener registry_listener = {.global = global, .global_remove = global_removed};
static void window_finalized(gpointer data, GObject *object)
{
  struct GeometryWindow *window = data, **link = &window->display->windows;
  while (*link && *link != window) link = &(*link)->next;
  if (*link) *link = window->next;
  if (window->idle) g_source_remove(window->idle);
  if (window->display->alive && window->observer) nextspace_surface_geometry_v1_destroy(window->observer);
  free(window);
}
static void display_closed(void *object, int is_error, gpointer data)
{
  struct GeometryDisplay *display = data;
  /* GDK owns connection teardown. Do not touch its proxies after close. */
  display->alive = 0; display->manager = NULL; display->registry = NULL;
  for (struct GeometryWindow *window = display->windows; window; window = window->next) {
    window->observer = NULL; window->surface = NULL; window->received = 0;
    if (window->idle) { g_source_remove(window->idle); window->idle = 0; }
  }
}
static void display_finalized(gpointer data, GObject *object)
{
  struct GeometryDisplay *display = data, **link = &displays;
  while (*link && *link != display) link = &(*link)->next;
  if (*link) *link = display->next;
  while (display->windows) {
    struct GeometryWindow *window = display->windows;
    g_object_weak_unref(window->gdk, window_finalized, window);
    window_finalized(window, window->gdk);
  }
  free(display);
}
int nxs_gtk3_surface_geometry(void *gdk, NXSGtk3SurfaceGeometry *geometry, NXSGtk3GeometryChanged changed)
{
  if (!gdk || !geometry || !load_gdk() ||
      !g_type_check_instance_is_a(gdk, wayland_window_type()) || window_destroyed(gdk) ||
      window_type(gdk) != 1 /* public GDK_WINDOW_TOPLEVEL */) return 0;
  void *gdk_display = window_display(gdk);
  struct GeometryDisplay *display;
  for (display = displays; display; display = display->next) if (display->gdk == gdk_display) break;
  if (!display) {
    struct wl_display *wayland = wayland_display(gdk_display); if (!wayland) return 0;
    display = calloc(1, sizeof(*display)); if (!display) return 0;
    display->gdk = gdk_display; display->wayland = wayland; display->alive = 1;
    display->next = displays; displays = display;
    g_object_weak_ref(gdk_display, display_finalized, display);
    g_signal_connect(gdk_display, "closed", G_CALLBACK(display_closed), display);
    display->registry = wl_display_get_registry(wayland);
    wl_registry_add_listener(display->registry, &registry_listener, display);
    wl_display_flush(wayland);
  }
  if (!display->alive) return 0;
  struct GeometryWindow *window;
  for (window = display->windows; window; window = window->next) if (window->gdk == gdk) break;
  if (!window) {
    window = calloc(1, sizeof(*window)); if (!window) return 0;
    window->display = display; window->gdk = gdk;
    window->next = display->windows; display->windows = window;
    g_object_weak_ref(gdk, window_finalized, window);
  }
  window->changed = changed; attach(window);
  if (!window->received) return 0;
  *geometry = window->geometry; return 1;
}
