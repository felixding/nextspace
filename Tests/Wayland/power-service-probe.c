/* Fake logind for isolated API validation; never contacts the system bus. MIT. */
#include <gio/gio.h>
#include <stdio.h>
#include <string.h>

static const char *behavior;
static void call(GDBusConnection *connection,const gchar *sender,const gchar *path,
    const gchar *interface,const gchar *method,GVariant *parameters,
    GDBusMethodInvocation *invocation,gpointer data)
{
  gboolean interactive=FALSE;
  g_variant_get(parameters,"(b)",&interactive);
  printf("{\"method\":\"%s\",\"interactive\":%s}\n",method,interactive?"true":"false");fflush(stdout);
  if (strcmp(behavior,"deny")==0)
    g_dbus_method_invocation_return_dbus_error(invocation,"org.freedesktop.DBus.Error.AccessDenied","Denied 100% %@ %s");
  else if (strcmp(behavior,"timeout")==0) g_object_ref(invocation);
  else g_dbus_method_invocation_return_value(invocation,NULL);
}
static void ready(GDBusConnection *connection,const gchar *name,gpointer data)
{ puts("{\"ready\":true}");fflush(stdout); }
int main(int argc,char **argv)
{
  if (argc!=2) return 2;
  behavior=argv[1];
  GError *error=NULL;
  GDBusConnection *connection=g_bus_get_sync(G_BUS_TYPE_SESSION,NULL,&error);
  if (!connection) return 3;
  GDBusNodeInfo *info=g_dbus_node_info_new_for_xml(
    "<node><interface name='org.freedesktop.login1.Manager'>"
    "<method name='PowerOff'><arg type='b' direction='in'/></method>"
    "<method name='Reboot'><arg type='b' direction='in'/></method>"
    "</interface></node>",&error);
  const GDBusInterfaceVTable methods={.method_call=call};
  if (!g_dbus_connection_register_object(connection,"/org/freedesktop/login1",info->interfaces[0],&methods,NULL,NULL,&error)) return 4;
  g_bus_own_name_on_connection(connection,"org.freedesktop.login1",G_BUS_NAME_OWNER_FLAGS_NONE,ready,NULL,NULL,NULL);
  g_main_loop_run(g_main_loop_new(NULL,FALSE));return 0;
}
