"""D-Bus availability for the real session-owned Wayland menu consumer."""
from gi.repository import Gio,GLib
import re
import threading

NAME='com.canonical.AppMenu.Registrar'
PATH='/com/canonical/AppMenu/Registrar'
XML='''<node><interface name="com.canonical.AppMenu.Registrar">
<method name="RegisterWindow"><arg type="u" direction="in"/><arg type="o" direction="in"/></method>
<method name="UnregisterWindow"><arg type="u" direction="in"/></method>
<method name="GetMenuForWindow"><arg type="u" direction="in"/><arg type="s" direction="out"/><arg type="o" direction="out"/></method>
<method name="GetMenus"><arg type="a(uso)" direction="out"/></method>
</interface></node>'''


class WaylandMenuService:
    def __init__(self):
        # Availability queries carry no native widget state. Give them an
        # owned GLib context so they remain responsive while AppKit waits or
        # tracks a control. All menu models/widgets stay on the host UI thread.
        self.context=GLib.MainContext.new()
        self.loop=GLib.MainLoop.new(self.context,False)
        self.ready=threading.Event();self.error=None
        self.thread=threading.Thread(target=self.serve,name='native-menu-service',daemon=True)
        self.thread.start()
        if not self.ready.wait(5):
            self.loop.quit();raise RuntimeError('Native menu service startup timed out')
        if self.error:raise RuntimeError('Native menu service startup failed') from self.error

    def serve(self):
        registration=None;owned=False
        self.context.push_thread_default()
        try:
            self.bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
            registration=self.bus.register_object(PATH,Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0],self.call,None,None)
            result=self.bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus',
                'RequestName',GLib.Variant('(su)',(NAME,4)),GLib.VariantType.new('(u)'),Gio.DBusCallFlags.NONE,3000,None).unpack()[0]
            if result not in (1,4):raise RuntimeError('The private session already has an application-menu consumer')
            owned=True;self.ready.set();self.loop.run()
        except Exception as error:self.error=error;self.ready.set()
        finally:
            if registration:self.bus.unregister_object(registration)
            if owned:
                try:
                    self.bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus',
                        'ReleaseName',GLib.Variant('(s)',(NAME,)),GLib.VariantType.new('(u)'),Gio.DBusCallFlags.NONE,1000,None)
                except GLib.Error:pass
            self.context.pop_thread_default()

    def call(self,connection,sender,path,interface,method,parameters,invocation):
        if method == 'GetMenus':
            invocation.return_value(GLib.Variant('(a(uso))', ([],)))
            return
        # Qt 6.8 unregisters its D-Bus object if the legacy registration
        # fails, even when KDE advertises the same object on Wayland.
        # Acknowledge that call without creating an X11 registry entry.
        # Workspace still accepts only a verified Wayland surface owner.
        if method == 'UnregisterWindow' or (
            method == 'RegisterWindow' and re.fullmatch(r'/MenuBar/[0-9]+', parameters.unpack()[1])
        ):
            invocation.return_value(None)
            return
        invocation.return_dbus_error('org.nextspace.NativeUI.WaylandOnly',
            'Native Wayland menus use surface addresses and the private Workspace role; X11 window registration is unavailable')

    def close(self):
        self.loop.quit();self.thread.join(timeout=2)
