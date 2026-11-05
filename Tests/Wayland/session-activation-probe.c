/* Actual D-Bus activated service used by the session lifetime fixture. MIT. */
#include <gio/gio.h>
#include <signal.h>
#include <unistd.h>
#include <string.h>

static void call(GDBusConnection *connection, const gchar *sender, const gchar *path,
    const gchar *interface, const gchar *method, GVariant *parameters,
    GDBusMethodInvocation *invocation, gpointer data)
{
  GVariantBuilder values;
  g_variant_builder_init(&values, G_VARIANT_TYPE("a{ss}"));
  const char *names[] = {"NEXTSPACE_SESSION_ID", "NEXTSPACE_GS_BACKEND", "WAYLAND_DISPLAY", "DISPLAY",
    "XAUTHORITY", "WAYLAND_SOCKET", "NEXTSPACE_SHELL_SOCKET", "XDG_RUNTIME_DIR", "XDG_SESSION_TYPE", "XDG_SESSION_CLASS", "XDG_SESSION_DESKTOP",
    "XDG_CURRENT_DESKTOP", "DESKTOP_SESSION", "GREETD_SOCK", "DBUS_SESSION_BUS_ADDRESS", "DBUS_STARTER_BUS_TYPE", "XCURSOR_THEME"};
  for (unsigned i = 0; i < G_N_ELEMENTS(names); i++) {
    const char *value = g_getenv(names[i]);
    if (value) g_variant_builder_add(&values, "{ss}", names[i], value);
  }
  char *pid = g_strdup_printf("%d", getpid());
  g_variant_builder_add(&values, "{ss}", "PROBE_PID", pid);
  g_free(pid);
  GString *targets = g_string_new("");
  GDir *directory = g_dir_open("/proc/self/fd", 0, NULL);
  const char *entry;
  while (directory && (entry = g_dir_read_name(directory))) {
    char *name = g_build_filename("/proc/self/fd", entry, NULL);
    char *target = g_file_read_link(name, NULL);
    if (target) { g_string_append(targets, target); g_string_append_c(targets, '\n'); }
    g_free(name); g_free(target);
  }
  if (directory) g_dir_close(directory);
  g_variant_builder_add(&values, "{ss}", "OPEN_FDS", targets->str);
  g_string_free(targets, TRUE);
  g_dbus_method_invocation_return_value(invocation, g_variant_new("(a{ss})", &values));
}

int main(int argc, char **argv)
{
  gboolean stubborn = argc == 2 && strcmp(argv[1], "--stubborn") == 0;
  if (stubborn) signal(SIGTERM, SIG_IGN);
  GError *error = NULL;
  GDBusConnection *connection = g_bus_get_sync(G_BUS_TYPE_SESSION, NULL, &error);
  if (!connection) { g_printerr("%s\n", error->message); return 1; }
  if (stubborn) g_dbus_connection_set_exit_on_close(connection, FALSE);
  GDBusNodeInfo *info = g_dbus_node_info_new_for_xml(
    "<node><interface name='org.nextspace.ValidationEnvironment'><method name='GetEnvironment'>"
    "<arg type='a{ss}' direction='out'/></method></interface></node>", &error);
  if (!info) return 2;
  const GDBusInterfaceVTable methods = {.method_call = call};
  if (!g_dbus_connection_register_object(connection, "/org/nextspace/ValidationEnvironment",
      info->interfaces[0], &methods, NULL, NULL, &error)) return 3;
  g_bus_own_name_on_connection(connection, "org.nextspace.ValidationEnvironment", G_BUS_NAME_OWNER_FLAGS_NONE,
    NULL, NULL, NULL, NULL);
  g_main_loop_run(g_main_loop_new(NULL, FALSE));
  return 0;
}
