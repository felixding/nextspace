/* Owned fake logind session for lock tests; never opens the system bus. MIT. */
#include <gio/gio.h>
#include <glib-unix.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static GDBusConnection *connection;
static gboolean deny_hints;
static gboolean preparing_sleep;
static unsigned next_inhibitor;
static const char *session_path = "/org/freedesktop/login1/session/fixture";

struct inhibitor { int fd; unsigned id; };
static gboolean inhibitor_released(gint fd,GIOCondition condition,gpointer data)
{
  struct inhibitor *item=data;
  printf("{\"event\":\"inhibitor-released\",\"id\":%u,\"monotonic_ms\":%lld}\n",item->id,(long long)(g_get_monotonic_time()/1000));fflush(stdout);
  close(fd);free(item);return G_SOURCE_REMOVE;
}

static void call(GDBusConnection *bus, const char *sender, const char *path,
    const char *interface, const char *method, GVariant *parameters,
    GDBusMethodInvocation *invocation, void *data)
{
  if (!strcmp(method, "GetSessionByPID")) {
    guint32 pid; g_variant_get(parameters, "(u)", &pid);
    printf("{\"event\":\"lookup\",\"pid\":%u}\n", pid); fflush(stdout);
    g_dbus_method_invocation_return_value(invocation, g_variant_new("(o)", session_path));
  } else if (!strcmp(method,"Inhibit")) {
    const char *what,*who,*why,*mode;
    g_variant_get(parameters,"(&s&s&s&s)",&what,&who,&why,&mode);
    if(strcmp(what,"sleep") || strcmp(mode,"delay")) {
      g_dbus_method_invocation_return_dbus_error(invocation,"org.freedesktop.DBus.Error.InvalidArgs","Expected sleep delay");return;
    }
    int descriptors[2];if(pipe(descriptors))_exit(4);
    GUnixFDList *list=g_unix_fd_list_new();
    int index=g_unix_fd_list_append(list,descriptors[1],NULL);close(descriptors[1]);if(index<0)_exit(4);
    struct inhibitor *item=calloc(1,sizeof(*item));if(!item)_exit(4);
    item->fd=descriptors[0];item->id=++next_inhibitor;
    g_unix_fd_add(item->fd,G_IO_HUP|G_IO_ERR,inhibitor_released,item);
    printf("{\"event\":\"inhibitor\",\"id\":%u}\n",item->id);fflush(stdout);
    g_dbus_method_invocation_return_value_with_unix_fd_list(invocation,g_variant_new("(h)",index),list);g_object_unref(list);
  } else if (!strcmp(method, "SetLockedHint")) {
    gboolean locked; g_variant_get(parameters, "(b)", &locked);
    printf("{\"event\":\"hint\",\"locked\":%s}\n", locked ? "true" : "false"); fflush(stdout);
    if (deny_hints) g_dbus_method_invocation_return_dbus_error(invocation,
      "org.freedesktop.DBus.Error.AccessDenied", "Hint denied 100% %@ %s");
    else g_dbus_method_invocation_return_value(invocation, NULL);
  }
}
static gboolean input(gint fd, GIOCondition condition, gpointer data)
{
  char line[64];
  if (!fgets(line, sizeof(line), stdin)) _exit(0);
  line[strcspn(line,"\n")] = 0;
  if (!strcmp(line,"resume-prepare")) {
    for (int active=0;active<=1;active++)
      g_dbus_connection_emit_signal(connection,NULL,"/org/freedesktop/login1","org.freedesktop.login1.Manager",
        "PrepareForSleep",g_variant_new("(b)",active),NULL);
    preparing_sleep=TRUE;
    g_dbus_connection_flush_sync(connection,NULL,NULL);
    puts("{\"event\":\"sent\",\"command\":\"resume-prepare\"}");fflush(stdout);return G_SOURCE_CONTINUE;
  }
  if (!strcmp(line,"prepare") || !strcmp(line,"resume")) {
    preparing_sleep=!strcmp(line,"prepare");
    g_dbus_connection_emit_signal(connection,NULL,"/org/freedesktop/login1","org.freedesktop.login1.Manager",
      "PrepareForSleep",g_variant_new("(b)",!strcmp(line,"prepare")),NULL);
    g_dbus_connection_flush_sync(connection,NULL,NULL);
    printf("{\"event\":\"sent\",\"command\":\"%s\"}\n",line);fflush(stdout);return G_SOURCE_CONTINUE;
  }
  if (!strcmp(line,"deny") || !strcmp(line,"allow")) {
    deny_hints=!strcmp(line,"deny");
    printf("{\"event\":\"configured\",\"deny_hints\":%s}\n",deny_hints?"true":"false");fflush(stdout);
    return G_SOURCE_CONTINUE;
  }
  const char *path = !strcmp(line, "other") ? "/org/freedesktop/login1/session/other" : session_path;
  const char *member = !strcmp(line, "unlock") ? "Unlock" : "Lock";
  if (strcmp(line,"lock") && strcmp(line,"other") && strcmp(line,"unlock")) _exit(2);
  g_dbus_connection_emit_signal(connection,NULL,path,"org.freedesktop.login1.Session",member,NULL,NULL);
  g_dbus_connection_flush_sync(connection,NULL,NULL);
  printf("{\"event\":\"sent\",\"command\":\"%s\"}\n",line);fflush(stdout);
  return G_SOURCE_CONTINUE;
}
static GVariant *property(GDBusConnection *bus,const char *sender,const char *path,
    const char *interface,const char *name,GError **error,void *data)
{ return !strcmp(name,"PreparingForSleep") ? g_variant_new_boolean(preparing_sleep) : NULL; }
static void ready(GDBusConnection *bus,const char *name,void *data)
{ puts("{\"event\":\"ready\"}");fflush(stdout); }
int main(int argc,char **argv)
{
  setvbuf(stdin,NULL,_IONBF,0);
  gboolean spoof=argc==2 && !strcmp(argv[1],"spoof");
  GError *error=NULL;
  connection=g_bus_get_sync(G_BUS_TYPE_SESSION,NULL,&error);if(!connection)return 1;
  g_dbus_connection_set_exit_on_close(connection,FALSE);
  GDBusNodeInfo *manager=g_dbus_node_info_new_for_xml(
    "<node><interface name='org.freedesktop.login1.Manager'>"
    "<method name='GetSessionByPID'><arg type='u' direction='in'/><arg type='o' direction='out'/></method>"
    "<method name='Inhibit'><arg type='s' direction='in'/><arg type='s' direction='in'/><arg type='s' direction='in'/><arg type='s' direction='in'/><arg type='h' direction='out'/></method>"
    "<signal name='PrepareForSleep'><arg type='b'/></signal>"
    "<property name='PreparingForSleep' type='b' access='read'/>"
    "</interface></node>",&error);
  GDBusNodeInfo *session=g_dbus_node_info_new_for_xml(
    "<node><interface name='org.freedesktop.login1.Session'>"
    "<method name='SetLockedHint'><arg type='b' direction='in'/></method>"
    "<signal name='Lock'/><signal name='Unlock'/>"
    "</interface></node>",&error);
  const GDBusInterfaceVTable methods={.method_call=call,.get_property=property};
  if(!manager||!session)return 2;
  if(!g_dbus_connection_register_object(connection,"/org/freedesktop/login1",manager->interfaces[0],&methods,NULL,NULL,&error))return 3;
  if(!g_dbus_connection_register_object(connection,session_path,session->interfaces[0],&methods,NULL,NULL,&error))return 3;
  g_bus_own_name_on_connection(connection,spoof?"org.nextspace.LockProbe":"org.freedesktop.login1",G_BUS_NAME_OWNER_FLAGS_NONE,ready,NULL,NULL,NULL);
  g_unix_fd_add(STDIN_FILENO,G_IO_IN|G_IO_HUP,input,NULL);
  g_main_loop_run(g_main_loop_new(NULL,FALSE));return 0;
}
