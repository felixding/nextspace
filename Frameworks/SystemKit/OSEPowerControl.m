/* Shared session power requests; logind retains authorization and inhibitors.
   SPDX-License-Identifier: GPL-2.0-or-later */
#import "OSEPower.h"
#include <errno.h>
#ifdef __linux__
#include <dbus/dbus.h>
#endif

@implementation OSEPower (Session)
+ (BOOL)requestAction:(OSEPowerAction)action error:(NSError **)error
{
  int code = ENOTSUP;
  NSString *description = @"System power requests are unavailable on this platform.";
  if (action != OSEPowerOff && action != OSEPowerReboot) {
    code = EINVAL; description = @"The requested power action is invalid.";
  }
#ifdef __linux__
  else {
    DBusError failure;
    dbus_error_init(&failure);
    DBusConnection *connection = dbus_threads_init_default() ? dbus_bus_get_private(DBUS_BUS_SYSTEM, &failure) : NULL;
    DBusMessage *request = NULL, *reply = NULL;
    if (connection) {
      dbus_connection_set_exit_on_disconnect(connection, FALSE);
      request = dbus_message_new_method_call("org.freedesktop.login1", "/org/freedesktop/login1",
        "org.freedesktop.login1.Manager", action == OSEPowerReboot ? "Reboot" : "PowerOff");
      dbus_bool_t interactive = TRUE;
      if (request && dbus_message_append_args(request, DBUS_TYPE_BOOLEAN, &interactive, DBUS_TYPE_INVALID))
        reply = dbus_connection_send_with_reply_and_block(connection, request, 5000, &failure);
    }
    BOOL accepted = reply && dbus_message_get_type(reply) == DBUS_MESSAGE_TYPE_METHOD_RETURN &&
      dbus_message_has_signature(reply, "");
    if (!accepted) {
      code = EIO;
      description = failure.message ? [NSString stringWithUTF8String:failure.message] :
        @"The system did not accept the power request.";
    }
    if (reply) dbus_message_unref(reply);
    if (request) dbus_message_unref(request);
    if (connection) { dbus_connection_close(connection); dbus_connection_unref(connection); }
    dbus_error_free(&failure);
    if (accepted) return YES;
  }
#endif
  if (error) *error = [NSError errorWithDomain:@"OSESystemPower" code:code
    userInfo:[NSDictionary dictionaryWithObject:description forKey:NSLocalizedDescriptionKey]];
  return NO;
}
@end
