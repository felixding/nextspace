#!/usr/bin/env python3
"""Experimental D-Bus menu model binding to the independent NativeUI provider.

The caller supplies an owned window's PID and advertised session-bus address.
There is no browser DOM inspection, widget implementation or shortcut table.
Automatic shell association and native submenu lifecycle integration remain open.
"""
import argparse
import ctypes as C
import json
from pathlib import Path
import signal
import sys
import time
from gi.repository import Gio, GLib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ChromiumScrollers'))
from native_menus import MenuItem, MenuState

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--library', required=True)
p.add_argument('--service', required=True)
p.add_argument('--path', required=True)
p.add_argument('--owner', type=int, required=True)
p.add_argument('--title', required=True)
p.add_argument('--output', type=Path, required=True)
a, native_args = p.parse_known_args()
a.output.mkdir(parents=True, exist_ok=True)
if not Gio.dbus_is_name(a.service) or not GLib.Variant.is_object_path(a.path) or a.owner <= 0:
    p.error('Invalid advertised menu address or owner')


def log(event, **values):
    print(json.dumps(dict(event=event, **values)), flush=True)


bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)


def bus_method(method, arguments, result_type):
    return bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
        'org.freedesktop.DBus', method, arguments, GLib.VariantType.new(result_type),
        Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]


# Pin all subsequent calls/signals to a unique owner. Re-resolving a well-known
# name after replacement could send an action to a different application.
owner = bus_method('GetNameOwner', GLib.Variant('(s)', (a.service,)), '(s)')
actual_pid = bus_method('GetConnectionUnixProcessID', GLib.Variant('(s)', (owner,)), '(u)')
if actual_pid != a.owner:
    raise SystemExit(f'Menu service PID {actual_pid} does not match window owner {a.owner}')

native = C.CDLL(a.library)
Command = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_uint64, C.c_uint)
Pump = C.CFUNCTYPE(None, C.c_void_p)
native.nxs_menu_create.argtypes = [C.c_char_p, Command, Pump, C.c_void_p]
native.nxs_menu_create.restype = C.c_void_p
native.nxs_menu_items.argtypes = [C.c_void_p, C.POINTER(MenuItem), C.c_uint32]
native.nxs_menu_items.restype = C.c_int
native.nxs_menu_show.argtypes = [C.c_void_p, C.c_int]
native.nxs_menu_show.restype = C.c_int
native.nxs_menu_cancel.argtypes = [C.c_void_p]
native.nxs_menu_cancel.restype = C.c_int
native.nxs_menu_destroy.argtypes = [C.c_void_p]
native.nxs_menu_destroy.restype = C.c_int
native.nxs_menu_state.argtypes = [C.c_void_p, C.c_int]
native.nxs_menu_state.restype = MenuState
native.nxs_native_ui_dispatch_events.argtypes = [C.c_double]
native.nxs_native_ui_dispatch_events.restype = C.c_double
if native.nxs_native_ui_menu_capabilities() & 3 != 3:
    raise SystemExit('Native menu model/cancellation support is required')

context = GLib.MainContext.default()
items, properties, strings = [], {}, []
menu = None
alive, dirty, fetching = True, True, False
pending_model = None
revision = None


def dump_states(*unused):
    states = []
    for index, item in enumerate(items):
        state = native.nxs_menu_state(menu, index)
        states.append(dict(index=index, command=item.command, title=item.title.decode(),
            visible=state.visible, tracking=state.tracking, highlighted=state.highlighted,
            frame=[state.item_frame.x,state.item_frame.y,state.item_frame.width,state.item_frame.height]))
    temporary = a.output / 'native-items.next'
    temporary.write_text(json.dumps(states, indent=2) + '\n')
    temporary.replace(a.output / 'native-items.json')


def shortcut(value):
    """Translate protocol key metadata, never application command names."""
    if not value or len(value[0]) == 0:
        return b'', 0
    sequence = value[0]
    key = sequence[-1]
    if len(key) != 1:
        # Special key names need a shared toolkit/native key conversion.
        return b'', 0
    modifiers = 0
    for modifier in sequence[:-1]:
        if modifier in ('Control', 'Super', 'Meta'):
            modifiers |= 1  # Native primary Command role.
        elif modifier == 'Shift':
            modifiers |= 2
        elif modifier == 'Alt':
            modifiers |= 8
        else:
            return b'', 0
    key = key.upper() if modifiers & 2 else key.lower()
    return key.encode(), modifiers


def project(root):
    model, props, text = [], {}, []
    seen = set()

    def visit(node, parent, depth):
        identifier, values, children = node
        if depth > 16 or len(model) >= 4096 or identifier < 0 or identifier in seen:
            raise ValueError('Invalid or excessive D-Bus menu hierarchy')
        seen.add(identifier)
        if not values.get('visible', True):
            return
        flags = 0
        if values.get('type') == 'separator':
            flags |= 1
        if not values.get('enabled', True):
            flags |= 2
        if values.get('toggle-state') == 1:
            flags |= 4
        if values.get('toggle-state') == -1:
            flags |= 8
        if values.get('children-display') == 'submenu' or children:
            flags |= 16
        title = values.get('label', '').encode()
        key, modifiers = shortcut(values.get('shortcut'))
        text.extend([title, key])
        index = len(model)
        model.append(MenuItem(C.sizeof(MenuItem), parent, 0 if flags & 17 else identifier + 1,
                              title, key, modifiers, flags))
        props[identifier] = values
        for child in children:
            visit(child, index, depth + 1)

    for child in root[2]:
        visit(child, -1, 0)
    return model, props, text


def complete_call(connection, result, label):
    try:
        connection.call_finish(result)
        log('application-replied', operation=label)
    except GLib.Error as error:
        log('application-error', operation=label, message=str(error))


def command(unused, identifier, phase):
    try:
        identifier -= 1
        values = properties.get(identifier)
        enabled = alive and values is not None and values.get('enabled', True) and values.get('visible', True)
        if enabled and phase == 1:
            bus.call(owner, a.path, 'com.canonical.dbusmenu', 'Event',
                GLib.Variant('(isvu)', (identifier, 'clicked', GLib.Variant('i', 0), 0)),
                GLib.VariantType.new('()'), Gio.DBusCallFlags.NONE, 3000, None,
                complete_call, 'clicked')
            log('application-command', identifier=identifier)
        return int(bool(enabled))
    except Exception as error:
        log('callback-error', message=str(error))
        return 0


def pump(unused):
    # GNUstep keeps native input/tracking. Only descriptor work is nested here;
    # hierarchy replacement waits until dispatch returns to the outer loop.
    while context.pending():
        context.iteration(False)


def fetched(connection, result, unused):
    global fetching, pending_model, revision, alive
    fetching = False
    try:
        revision, root = connection.call_finish(result).unpack()
        pending_model = project(root)
        (a.output / 'layout.json').write_text(json.dumps(dict(revision=revision, root=root), indent=2) + '\n')
    except (GLib.Error, ValueError, TypeError) as error:
        log('layout-error', message=str(error))
        alive = False
        native.nxs_menu_cancel(menu)


def changed(*unused):
    global dirty
    dirty = True


def name_changed(connection, sender, path, interface, member, parameters, unused):
    global alive
    name, old, new = parameters.unpack()
    if name == owner and old and not new:
        alive = False
        native.nxs_menu_cancel(menu)
        log('owner-lost')


command_callback, pump_callback = Command(command), Pump(pump)
menu = native.nxs_menu_create(a.title.encode(), command_callback, pump_callback, None)
if not menu:
    raise SystemExit('Native menu host initialization failed')
subscriptions = [bus.signal_subscribe(owner, 'com.canonical.dbusmenu', member, a.path,
    None, Gio.DBusSignalFlags.NONE, changed, None) for member in ('LayoutUpdated', 'ItemsPropertiesUpdated')]
subscriptions.append(bus.signal_subscribe('org.freedesktop.DBus', 'org.freedesktop.DBus',
    'NameOwnerChanged', '/org/freedesktop/DBus', owner, Gio.DBusSignalFlags.NONE, name_changed, None))


def stop(*unused):
    global alive
    alive = False
    native.nxs_menu_cancel(menu)


bus.connect('closed', lambda *unused: stop())
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGUSR1, dump_states)
try:
    while alive:
        pump(None)
        if not alive:
            break
        if dirty and not fetching:
            dirty, fetching = False, True
            bus.call(owner, a.path, 'com.canonical.dbusmenu', 'GetLayout',
                GLib.Variant('(iias)', (0, -1, [])), None, Gio.DBusCallFlags.NONE,
                3000, None, fetched, None)
        if pending_model is not None:
            model, props, text = pending_model
            array = (MenuItem * len(model))(*model)
            if native.nxs_menu_items(menu, array, len(model)):
                items, properties, strings = model, props, text
                pending_model = None
                if not native.nxs_menu_show(menu, 1):
                    raise RuntimeError('Native menu could not be shown')
                dump_states()
                log('native-menu', owner=owner, pid=actual_pid, count=len(model), revision=revision)
        native.nxs_native_ui_dispatch_events(.005)
        time.sleep(.001)
finally:
    native.nxs_menu_cancel(menu)
    for subscription in subscriptions:
        bus.signal_unsubscribe(subscription)
    assert native.nxs_menu_destroy(menu)
    log('stopped')
