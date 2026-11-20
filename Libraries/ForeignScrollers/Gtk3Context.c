/* GTK 3 integration of the existing native context menu transport.
 * GPL-2.0-or-later. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/eventfd.h>
#include <glib-unix.h>
#include "../NativeUI/Bridge/Gtk3Geometry.h"
#include "../NativeUI/Bridge/Protocol.h"

static int log_fd = -1;
static void note(const char *message)
{
  if (log_fd >= 0)
    dprintf(log_fd, "%d %s\n", getpid(), message);
}
#include "../NativeUI/Bridge/Transport.inc"
#include "../NativeUI/Bridge/AuxiliaryActivation.inc"
#include "../NativeUI/Bridge/Menu.inc"

static int (*gtk_surface_geometry)(void *, NXSGtk3SurfaceGeometry *, NXSGtk3GeometryChanged);
static const char *(*gtk_surface_parent)(uintptr_t);
static int (*gtk_activation_request)(void);
static uint32_t activation_query;
static int activation_descriptor = -1;

static void source_pointer(uintptr_t surface, void *unused)
{
  native_auxiliary_source_pointer(surface);
}

static void activation_token(uintptr_t surface, const char *token, void *unused)
{
  const char *parent = token && gtk_surface_parent ? gtk_surface_parent(surface) : NULL;
  native_auxiliary_token_publish_query(surface, 0, token, parent, token ? activation_query : 0);
  activation_query = 0;
}

static gboolean activation_ready(gint descriptor, GIOCondition condition, gpointer unused)
{
  if (condition & (G_IO_HUP | G_IO_ERR | G_IO_NVAL)) {
    close(descriptor);
    activation_descriptor = -1;
    activation_query = 0;
    return G_SOURCE_REMOVE;
  }
  uint64_t query;
  while (recv(descriptor, &query, sizeof(query), MSG_DONTWAIT | MSG_TRUNC) == sizeof(query)) {
    if (query && query <= UINT32_MAX) {
      activation_query = query;
      if (!gtk_activation_request())
        activation_query = 0;
    }
  }
  return G_SOURCE_CONTINUE;
}

static int prepare_menu(int (*handler)(const struct NXSNativeMenuCommand *))
{
  static int lifetime = -1;
  if (channel < 0)
    return 0;
  if (lifetime < 0) {
    int descriptor = eventfd(0, EFD_CLOEXEC | EFD_NONBLOCK);
    if (descriptor < 0)
      return 0;
    struct NXSControlRequest request = {
      .magic = NXS_CHROMIUM_CONTROL_MAGIC, .operation = 15, .process = identity()
    };
    struct NXSResponse *response = exchange_bytes_descriptor(&request, sizeof(request), descriptor);
    if (!response || response->parts[3].x != 1) {
      close(descriptor);
      return 0;
    }
    lifetime = descriptor;
  }
  return native_menu_filter_register(handler);
}

static void *gtk_symbol(const char *name)
{
  static void *gtk;
  if (!gtk)
    gtk = dlopen("libgtk-3.so.0", RTLD_NOW | RTLD_NOLOAD);
  return gtk ? dlsym(gtk, name) : NULL;
}

#define NXS_GTK_CONTEXT_SYMBOL(name) gtk_symbol(name)
#define NXS_GTK_CONTEXT_PREPARE(handler) prepare_menu(handler)
#define gtk_menu_new_from_model nextspace_gtk3_menu_new_from_model
#define gtk_menu_popup_at_rect nextspace_gtk3_menu_popup_at_rect
#define gtk_menu_popdown nextspace_gtk3_menu_popdown
#include "../NativeUI/Bridge/GtkContextMenus.inc"
#undef gtk_menu_popdown
#undef gtk_menu_popup_at_rect
#undef gtk_menu_new_from_model
#undef NXS_GTK_CONTEXT_PREPARE

void nextspace_gtk3_observe_context_parent(void *window)
{
  if (!window || g_strcmp0(g_getenv("NEXTSPACE_NATIVE_CONTEXT_MENUS"), "off") == 0)
    return;
  if (channel < 0) {
    if (g_strcmp0(g_getenv("NEXTSPACE_TRACE_NATIVE_CONTEXT_MENUS"), "1") == 0)
      log_fd = STDERR_FILENO;
    const char *path = g_getenv("NEXTSPACE_GTK3_GEOMETRY_LIBRARY");
    void *library = dlopen(path && *path ? path : "libnextspace-gtk3-geometry.so.1",
                           RTLD_NOW | RTLD_LOCAL);
    if (!library)
      return;
    gtk_surface_geometry = dlsym(library, "nxs_gtk3_surface_geometry");
    gtk_surface_parent = dlsym(library, "nxs_gtk3_surface_parent");
    gtk_activation_request = dlsym(library, "nxs_gtk3_activation_request");
    int (*observe)(NXSGtk3ActivationToken, void *) =
        dlsym(library, "nxs_gtk3_activation_observe_requests");
    int (*observe_pointer)(NXSGtk3SourcePointer, void *) =
        dlsym(library, "nxs_gtk3_source_pointer_observe");
    if (!gtk_surface_geometry || !gtk_activation_request || !observe ||
        !bridge_connect(g_getenv("NEXTSPACE_NATIVE_UI_SOCKET"))) {
      dlclose(library);
      return;
    }
    if (observe(activation_token, NULL) && observe_pointer)
      observe_pointer(source_pointer, NULL);
  }
  if (activation_descriptor < 0) {
    activation_descriptor = native_auxiliary_source_watch();
    if (activation_descriptor >= 0)
      g_unix_fd_add(activation_descriptor, G_IO_IN | G_IO_HUP | G_IO_ERR | G_IO_NVAL,
                    activation_ready, NULL);
  }
  NXSGtk3SurfaceGeometry snapshot;
  gtk_surface_geometry(window, &snapshot, NULL);
}

int nextspace_gtk3_context_key(const NXSKeyEvent *event)
{
  if (!gtk_context_owns_keys())
    return 0;
  native_application_menu_key(event, 1);
  return 1;
}
