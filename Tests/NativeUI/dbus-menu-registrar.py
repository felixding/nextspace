#!/usr/bin/env python3
"""Hold the registrar name on a private Wayland test bus, without X11 methods.

Firefox's Wayland exporter checks name ownership and sends its address through
org_kde_kwin_appmenu. This fixture is not a desktop registrar implementation.
"""
import json
import signal
from gi.repository import Gio, GLib
loop = GLib.MainLoop()
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
def acquired(connection, name):
    print(json.dumps(dict(event='ready', name=name)), flush=True)
def lost(connection, name):
    loop.quit()
name = Gio.bus_own_name_on_connection(bus, 'com.canonical.AppMenu.Registrar',
    Gio.BusNameOwnerFlags.NONE, acquired, lost)
signal.signal(signal.SIGTERM, lambda *unused: loop.quit())
try:
    loop.run()
finally:
    Gio.bus_unown_name(name)
