#!/usr/bin/env python3
"""Owned application calling the real public FileChooser portal frontend.

Prints the request address, waits for Response, and accepts 'close' on stdin.
Options are a JSON mapping of names to [D-Bus signature, value].
"""
import argparse
import json
import sys
from gi.repository import Gio, GLib

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('method', choices=['OpenFile', 'SaveFile', 'SaveFiles'])
parser.add_argument('--options', default='{}')
parser.add_argument('--title', default='Native file portal trial')
parser.add_argument('--parent-window', default='')
args = parser.parse_args()
options = {name: GLib.Variant(signature, value)
           for name, (signature, value) in json.loads(args.options).items()}
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
loop = GLib.MainLoop()
def response(connection, sender, path, interface, signal, parameters):
    print(json.dumps(dict(event='response', path=path, result=parameters.unpack())), flush=True)
    loop.quit()
subscription = bus.signal_subscribe('org.freedesktop.portal.Desktop', 'org.freedesktop.portal.Request',
    'Response', None, None, Gio.DBusSignalFlags.NONE, response)
handle = bus.call_sync('org.freedesktop.portal.Desktop', '/org/freedesktop/portal/desktop',
    'org.freedesktop.portal.FileChooser', args.method, GLib.Variant('(ssa{sv})', (args.parent_window, args.title, options)),
    GLib.VariantType.new('(o)'), Gio.DBusCallFlags.NONE, 10000, None).unpack()[0]
print(json.dumps(dict(event='request', handle=handle)), flush=True)
def command(source, condition):
    value = sys.stdin.readline().strip()
    if value == 'close':
        bus.call_sync('org.freedesktop.portal.Desktop', handle, 'org.freedesktop.portal.Request',
            'Close', GLib.Variant('()', ()), GLib.VariantType.new('()'), Gio.DBusCallFlags.NONE, 5000, None)
        print(json.dumps(dict(event='closed')), flush=True)
        loop.quit()
    elif not value:
        return GLib.SOURCE_REMOVE
    return GLib.SOURCE_CONTINUE
watch = GLib.io_add_watch(sys.stdin, GLib.IOCondition.IN | GLib.IOCondition.HUP, command)
try:
    loop.run()
finally:
    bus.signal_unsubscribe(subscription)
