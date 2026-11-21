/* GTK menu models and ownership for Wayland. GPL-2.0-or-later. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <gtk/gtk.h>
#include <gdk/gdkwayland.h>
#include <libdbusmenu-gtk/parser.h>
#include <libdbusmenu-gtk/menuitem.h>
#include <libdbusmenu-glib/server.h>
#include "appmenu-client-protocol.h"

typedef struct {
  GtkWidget *bar;
  GtkWidget *window;
  DbusmenuServer *server;
  struct org_kde_kwin_appmenu *surface_menu;
  char *path;
  gboolean detached;
  gboolean no_show_all;
} AppMenu;

static GList *menus;
static struct org_kde_kwin_appmenu_manager *manager;
static guint32 manager_name;
static GDBusConnection *bus;
static gboolean registrar;
static gboolean requested;
static unsigned next_menu;

static void update_shortcut(GtkWidget *widget, GParamSpec *property, DbusmenuMenuitem *item)
{
  g_autofree char *accelerator = NULL;
  g_object_get(widget, "accel", &accelerator, NULL);
  if (accelerator && *accelerator)
    dbusmenu_menuitem_property_set_shortcut_string(item, accelerator);
  else
    dbusmenu_menuitem_property_remove(item, DBUSMENU_MENUITEM_PROP_SHORTCUT);
}

static void export_shortcuts(GtkWidget *widget, gpointer unused)
{
  if (GTK_IS_MENU_ITEM(widget)) {
    GParamSpec *accel = g_object_class_find_property(G_OBJECT_GET_CLASS(widget), "accel");
    DbusmenuMenuitem *item = dbusmenu_gtk_parse_get_cached_item(widget);
    if (item && accel && G_PARAM_SPEC_VALUE_TYPE(accel) == G_TYPE_STRING) {
      update_shortcut(widget, accel, item);
      g_signal_connect_object(widget, "notify::accel", G_CALLBACK(update_shortcut), item, 0);
    }
    GtkWidget *submenu = gtk_menu_item_get_submenu(GTK_MENU_ITEM(widget));
    if (submenu)
      export_shortcuts(submenu, NULL);
  } else if (GTK_IS_MENU_SHELL(widget)) {
    gtk_container_foreach(GTK_CONTAINER(widget), export_shortcuts, NULL);
  }
}

static void restore(AppMenu *menu)
{
  if (menu->surface_menu) {
    org_kde_kwin_appmenu_release(menu->surface_menu);
    menu->surface_menu = NULL;
  }
  if (menu->detached) {
    menu->detached = FALSE;
    gtk_widget_set_no_show_all(menu->bar, menu->no_show_all);
    gtk_widget_show(menu->bar);
  }
}

static void publish(AppMenu *menu)
{
  if (menu->surface_menu || !manager || !registrar || !menu->window ||
      !gtk_widget_get_mapped(menu->window) || !gtk_widget_get_visible(menu->bar))
    return;
  GdkWindow *window = gtk_widget_get_window(menu->window);
  if (!window || !GDK_IS_WAYLAND_WINDOW(window))
    return;
  struct wl_surface *surface = gdk_wayland_window_get_wl_surface(window);
  if (!surface)
    return;
  if (!menu->server) {
    DbusmenuMenuitem *root = dbusmenu_gtk_parse_menu_structure(menu->bar);
    if (!root)
      return;
    export_shortcuts(menu->bar, NULL);
    menu->server = dbusmenu_server_new(menu->path);
    dbusmenu_server_set_root(menu->server, root);
    g_object_unref(root);
  }
  menu->surface_menu = org_kde_kwin_appmenu_manager_create(manager, surface);
  if (!menu->surface_menu)
    return;
  org_kde_kwin_appmenu_set_address(menu->surface_menu,
      g_dbus_connection_get_unique_name(bus), menu->path);
  wl_display_flush(gdk_wayland_display_get_wl_display(gdk_window_get_display(window)));
  menu->detached = TRUE;
  menu->no_show_all = gtk_widget_get_no_show_all(menu->bar);
  gtk_widget_set_no_show_all(menu->bar, TRUE);
  gtk_widget_hide(menu->bar);
}

static void update_menus(void)
{
  for (GList *entry = menus; entry; entry = entry->next)
    if (manager && registrar)
      publish(entry->data);
    else
      restore(entry->data);
}

static void registry_global(void *unused, struct wl_registry *registry, uint32_t name,
                            const char *interface, uint32_t version)
{
  if (!manager && version >= 2 && g_str_equal(interface, org_kde_kwin_appmenu_manager_interface.name)) {
    manager = wl_registry_bind(registry, name, &org_kde_kwin_appmenu_manager_interface, 2);
    manager_name = name;
    update_menus();
  }
}

static void registry_removed(void *unused, struct wl_registry *registry, uint32_t name)
{
  if (manager && manager_name == name) {
    org_kde_kwin_appmenu_manager_release(manager);
    manager = NULL;
    update_menus();
  }
}

static const struct wl_registry_listener registry_listener = { registry_global, registry_removed };

static void registrar_arrived(GDBusConnection *connection, const char *name,
                              const char *owner, gpointer unused)
{
  g_set_object(&bus, connection);
  registrar = TRUE;
  update_menus();
}

static void registrar_left(GDBusConnection *connection, const char *name, gpointer unused)
{
  registrar = FALSE;
  update_menus();
  g_clear_object(&bus);
}

static void window_mapped(GtkWidget *window, AppMenu *menu)
{
  publish(menu);
}

static void window_unmapped(GtkWidget *window, AppMenu *menu)
{
  restore(menu);
}

static void remove_menu(GtkWidget *bar, AppMenu *menu)
{
  menus = g_list_remove(menus, menu);
  /* The bar is being destroyed, so only release its export. */
  menu->detached = FALSE;
  restore(menu);
  if (menu->window) {
    g_signal_handlers_disconnect_by_data(menu->window, menu);
    g_object_remove_weak_pointer(G_OBJECT(menu->window), (gpointer *)&menu->window);
  }
  g_signal_handlers_disconnect_by_data(bar, menu);
  g_clear_object(&menu->server);
  g_free(menu->path);
  g_free(menu);
}

static gboolean attach_menu(gpointer data)
{
  GtkWidget *bar = data;
  g_object_set_data(G_OBJECT(bar), "nextspace-app-menu-queued", NULL);
  if (!gtk_widget_get_mapped(bar))
    return G_SOURCE_REMOVE;
  GtkWidget *window = gtk_widget_get_toplevel(bar);
  GdkDisplay *display = gtk_widget_get_display(bar);
  if (!GTK_IS_WINDOW(window) || gtk_window_get_window_type(GTK_WINDOW(window)) != GTK_WINDOW_TOPLEVEL ||
      display != gdk_display_get_default() || !GDK_IS_WAYLAND_DISPLAY(display))
    return G_SOURCE_REMOVE;
  for (GList *entry = menus; entry; entry = entry->next) {
    AppMenu *existing = entry->data;
    if (existing->window == window)
      return G_SOURCE_REMOVE;
  }
  if (!requested) {
    struct wl_display *wayland = gdk_wayland_display_get_wl_display(display);
    struct wl_registry *registry = wl_display_get_registry(wayland);
    if (!registry)
      return G_SOURCE_REMOVE;
    wl_registry_add_listener(registry, &registry_listener, NULL);
    wl_display_flush(wayland);
    g_bus_watch_name(G_BUS_TYPE_SESSION, "com.canonical.AppMenu.Registrar",
        G_BUS_NAME_WATCHER_FLAGS_NONE, registrar_arrived, registrar_left, NULL, NULL);
    requested = TRUE;
  }
  AppMenu *menu = g_new0(AppMenu, 1);
  menu->bar = bar;
  menu->window = window;
  g_object_add_weak_pointer(G_OBJECT(window), (gpointer *)&menu->window);
  menu->path = g_strdup_printf("/org/nextspace/GtkMenu/%u", ++next_menu);
  menus = g_list_prepend(menus, menu);
  g_signal_connect(window, "map", G_CALLBACK(window_mapped), menu);
  g_signal_connect(window, "unmap", G_CALLBACK(window_unmapped), menu);
  g_signal_connect(bar, "destroy", G_CALLBACK(remove_menu), menu);
  publish(menu);
  return G_SOURCE_REMOVE;
}

void nextspace_gtk3_attach_menu(GtkWidget *widget)
{
  if (!GTK_IS_MENU_BAR(widget) ||
      g_strcmp0(g_getenv("NEXTSPACE_NATIVE_MENUS"), "off") == 0 ||
      g_object_get_data(G_OBJECT(widget), "nextspace-original-menu") ||
      g_object_get_data(G_OBJECT(widget), "nextspace-app-menu-queued"))
    return;
  g_object_set_data(G_OBJECT(widget), "nextspace-app-menu-queued", GINT_TO_POINTER(1));
  g_idle_add_full(G_PRIORITY_DEFAULT_IDLE, attach_menu, g_object_ref(widget), g_object_unref);
}

void nextspace_gtk3_menu_popup_at_rect(void *, void *, const void *, int, int, const void *);

void nextspace_gtk3_menu_popup_at_pointer(GtkMenu *menu, const GdkEvent *event)
{
  GdkEvent *current = event ? NULL : gtk_get_current_event();
  const GdkEvent *trigger = event ? event : current;
  guint button;
  gdouble x, y;
  if (!g_object_get_data(G_OBJECT(menu), "nextspace-original-menu") && trigger &&
      gdk_event_get_button(trigger, &button) && button == GDK_BUTTON_SECONDARY &&
      gdk_event_get_coords(trigger, &x, &y) && gdk_event_get_window(trigger)) {
    GdkRectangle rect = { (int)x, (int)y, 1, 1 };
    nextspace_gtk3_menu_popup_at_rect(menu, gdk_event_get_window(trigger), &rect,
        GDK_GRAVITY_SOUTH_EAST, GDK_GRAVITY_NORTH_WEST, trigger);
  } else {
    void *gtk = dlopen("libgtk-3.so.0", RTLD_NOW | RTLD_NOLOAD);
    void (*original)(GtkMenu *, const GdkEvent *) = gtk ? dlsym(gtk, "gtk_menu_popup_at_pointer") : NULL;
    if (original)
      original(menu, event);
    if (gtk)
      dlclose(gtk);
  }
  if (current)
    gdk_event_free(current);
}
