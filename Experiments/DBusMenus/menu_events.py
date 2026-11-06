"""Deliver application events without repeating an uncertain command."""
import re
from gi.repository import Gio, GLib


def application_event(model, token, name, send, refresh, rejected):
    for attempt in range(3):
        node = model.nodes.get(token)
        if node is None:return None
        if name=='clicked' and not (node.properties.get('enabled',True) and node.properties.get('visible',True)):
            return None
        try:
            send(node.remote,name)
            return node.remote
        except GLib.Error as error:
            # libdbusmenu rejects this ID before queueing any application event.
            # A timeout, disconnect or other error must never repeat a click.
            missing=(Gio.DBusError.get_remote_error(error)==
                'org.gtk.GDBus.UnmappedGError.Quark._LIBDBUSMENU_2dGLIB.Code0' and
                re.search(r'The ID supplied '+str(node.remote)+r' does not refer to a menu item we have$',error.message))
            if not missing or attempt==2:raise
            rejected(name,token,node.remote)
            refresh()
