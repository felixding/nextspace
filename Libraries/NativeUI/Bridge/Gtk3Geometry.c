/* Owned GTK3/Wayland geometry. No widget rendering or toolkit layout here. */
#include "Gtk3Geometry.h"
#include <dlfcn.h>
#include <glib-object.h>
#include <gio/gio.h>
#include <stdlib.h>
#include <wayland-client.h>

struct GeometryDisplay;
struct GeometryWindow {
  struct GeometryWindow *next;
  struct GeometryDisplay *display;
  void *gdk;
  struct wl_surface *surface;
  NXSGeometrySurface *observation;
  NXSGtk3GeometryChanged changed;
  guint idle;
};
struct GeometryDisplay {
  struct GeometryDisplay *next;
  void *gdk;
  struct wl_display *wayland;
  NXSGeometryDisplay *transport;
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
static void notify(void *context)
{
  struct GeometryWindow *window = context;
  if (!window->idle && window->changed)
    window->idle = g_idle_add(notify_idle, window);
}
static void attach(struct GeometryWindow *window)
{
  struct GeometryDisplay *display = window->display;
  if (!display->alive || window_destroyed(window->gdk) ||
      !window_viewable(window->gdk)) return;
  struct wl_surface *surface = wayland_surface(window->gdk);
  if (surface == window->surface && window->observation) return;
  window->surface = surface;
  if (window->observation) nxs_wayland_geometry_rebind(window->observation, surface);
  else if (surface) window->observation = nxs_wayland_geometry_observe(display->transport, surface, notify, window);
}
static void window_finalized(gpointer data, GObject *object)
{
  struct GeometryWindow *window = data, **link = &window->display->windows;
  while (*link && *link != window) link = &(*link)->next;
  if (*link) *link = window->next;
  if (window->idle) g_source_remove(window->idle);
  if (window->observation) nxs_wayland_geometry_unobserve(window->observation);
  free(window);
}
static void display_closed(void *object, int is_error, gpointer data)
{
  struct GeometryDisplay *display = data;
  /* GDK owns connection teardown. Do not touch its proxies after close. */
  display->alive = 0;
  nxs_wayland_geometry_disconnect(display->transport, 0); display->transport = NULL;
  for (struct GeometryWindow *window = display->windows; window; window = window->next) {
    window->observation = NULL; window->surface = NULL;
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
  nxs_wayland_geometry_disconnect(display->transport, display->alive);
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
    display->transport = nxs_wayland_geometry_connect(wayland, wayland);
    if (!display->transport) { free(display); return 0; }
    display->gdk = gdk_display; display->wayland = wayland; display->alive = 1;
    display->next = displays; displays = display;
    g_object_weak_ref(gdk_display, display_finalized, display);
    g_signal_connect(gdk_display, "closed", G_CALLBACK(display_closed), display);
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
  return nxs_wayland_geometry_read(window->observation, geometry);
}

/* The public GTK event signal and GDK launch-context API retain GTK's actual
 * implicit-grab serial and focused surface. No private toolkit offsets, input
 * implementation or independent activation protocol producer is needed. */
static NXSGtk3ActivationToken activation_callback;
static void *activation_context;
static gulong activation_hook;
static guint activation_signal;
static int activation_busy;
static void *(*activation_event_window)(const void *), *(*activation_toplevel)(void *);
static guint32 (*activation_event_time)(const void *);
static GAppLaunchContext *(*activation_launch_context)(void *);
static void (*activation_timestamp)(void *,guint32);
static gboolean activation_event(GSignalInvocationHint *hint, guint count,
                                const GValue *values, gpointer data)
{
  if(!activation_callback || activation_busy || count<2)return TRUE;
  /* Public GdkEventAny prefix. Synthetic events do not create new grants. */
  const struct {int type;void *window;gint8 send_event;} *event=g_value_get_boxed(values+1);
  if(!event || event->send_event || (event->type!=4 && event->type!=8))return TRUE;
  void *gdk=activation_event_window(event);
  if(!gdk || !(gdk=activation_toplevel(gdk)))return TRUE;
  /* Keep the existing geometry subscription/callback unchanged. */
  if(!load_gdk() || !g_type_check_instance_is_a(gdk,wayland_window_type()) ||
     window_destroyed(gdk) || !window_viewable(gdk))return TRUE;
  void *display=window_display(gdk);
  GAppLaunchContext *context=activation_launch_context(display);
  if(!context)return TRUE;
  activation_busy=1;
  activation_timestamp(context,activation_event_time(event));
  GAppInfo *info=g_app_info_create_from_commandline("nextspace-native-ui",NULL,0,NULL);
  char *token=info?g_app_launch_context_get_startup_notify_id(context,info,NULL):NULL;
  if(token && *token && activation_callback)
    activation_callback((uintptr_t)wayland_surface(gdk),token,activation_context);
  g_free(token);if(info)g_object_unref(info);g_object_unref(context);
  activation_busy=0;return TRUE;
}
int nxs_gtk3_activation_observe(NXSGtk3ActivationToken callback,void *context)
{
  if(!callback) {
    if(activation_hook)g_signal_remove_emission_hook(activation_signal,activation_hook);
    activation_hook=0;activation_callback=NULL;activation_context=NULL;return 1;
  }
  if(activation_callback)return activation_callback==callback && activation_context==context;
  GType (*widget_type)(void)=dlsym(RTLD_DEFAULT,"gtk_widget_get_type");
  activation_event_window=dlsym(RTLD_DEFAULT,"gdk_event_get_window");
  activation_toplevel=dlsym(RTLD_DEFAULT,"gdk_window_get_toplevel");
  activation_event_time=dlsym(RTLD_DEFAULT,"gdk_event_get_time");
  activation_launch_context=dlsym(RTLD_DEFAULT,"gdk_display_get_app_launch_context");
  activation_timestamp=dlsym(RTLD_DEFAULT,"gdk_app_launch_context_set_timestamp");
  if(!load_gdk() || !widget_type || !activation_event_window || !activation_toplevel ||
     !activation_event_time || !activation_launch_context || !activation_timestamp)return 0;
  gpointer klass=g_type_class_ref(widget_type());
  activation_signal=g_signal_lookup("event",widget_type());
  GSignalQuery query={0};g_signal_query(activation_signal,&query);
  if(query.signal_id && !(query.signal_flags&G_SIGNAL_NO_HOOKS))
    activation_hook=g_signal_add_emission_hook(activation_signal,0,activation_event,NULL,NULL);
  g_type_class_unref(klass);
  if(!activation_hook)return 0;
  activation_callback=callback;activation_context=context;return 1;
}
