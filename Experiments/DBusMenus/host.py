#!/usr/bin/env python3
"""Experimental D-Bus menu model binding to the independent NativeUI provider.

The caller supplies an owned window's PID and advertised session-bus address.
There is no browser DOM inspection, widget implementation or shortcut table.
Automatic shell association remains open; submenu lifecycle is opt-in.
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
from menu_model import MenuModel, flattened, replace_children

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--library', required=True)
p.add_argument('--service', required=True)
p.add_argument('--path', required=True)
p.add_argument('--owner', type=int, required=True)
p.add_argument('--title', required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--lifecycle', action='store_true', help='Refresh submenus through native lifecycle callbacks')
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
model = MenuModel()
native_root = pending_root = None
menu = None
alive, dirty, fetching = True, True, False
generation = 0
revision = None
opened = {}


def projection(root):
    result = []
    for parent,node in flattened(root):
        values = node.properties
        flags = (1 if values.get('type')=='separator' else 0)
        flags |= 0 if values.get('enabled',True) else 2
        flags |= 4 if values.get('toggle-state')==1 else 8 if values.get('toggle-state')==-1 else 0
        flags |= 16 if values.get('children-display')=='submenu' or node.children else 0
        key,modifiers = shortcut(values.get('shortcut'))
        result.append((parent,0 if flags&1 else node.native,values.get('label','').encode(),key,modifiers,flags))
    return result


def array_for(root):
    values = projection(root)
    return (MenuItem*len(values))(*(MenuItem(C.sizeof(MenuItem),*value) for value in values))


def dump_states(*unused):
    states = []
    for index,(_,node) in enumerate(flattened(native_root)):
        state = native.nxs_menu_state(menu,index)
        states.append(dict(index=index,command=node.native,remote=node.remote,title=node.properties.get('label',''),
            visible=state.visible,tracking=state.tracking,highlighted=state.highlighted,
            frame=[state.item_frame.x,state.item_frame.y,state.item_frame.width,state.item_frame.height]))
    temporary = a.output/'native-items.next'
    temporary.write_text(json.dumps(states,indent=2)+'\n')
    temporary.replace(a.output/'native-items.json')


def shortcut(value):
    """Translate protocol key metadata, never application command names."""
    if not value or len(value)!=1 or not value[0]:
        return b'',0
    sequence = value[0]
    key = sequence[-1]
    if len(key)!=1:
        return b'',0
    modifiers = 0
    for modifier in sequence[:-1]:
        if modifier in ('Control','Super','Meta'):modifiers |= 1
        elif modifier=='Shift':modifiers |= 2
        elif modifier=='Alt':modifiers |= 8
        else:return b'',0
    return (key.upper() if modifiers&2 else key.lower()).encode(),modifiers


def complete_call(connection,result,label):
    try:
        connection.call_finish(result)
        log('application-replied',operation=label)
    except GLib.Error as error:
        log('application-error',operation=label,message=str(error))


def event(identifier,name,callback=complete_call,data=None):
    bus.call(owner,a.path,'com.canonical.dbusmenu','Event',
        GLib.Variant('(isvu)',(identifier,name,GLib.Variant('i',0),0)),
        GLib.VariantType.new('()'),Gio.DBusCallFlags.NONE,3000,None,callback,data or name)


def command(unused,identifier,phase):
    global generation,fetching
    try:
        if phase==1 and a.lifecycle:
            generation += 1;fetching = False
            accept_layout(awaiting('GetLayout',GLib.Variant('(iias)',(0,-1,[]))))
        node = model.nodes.get(identifier)
        enabled = alive and node is not None and node.properties.get('enabled',True) and node.properties.get('visible',True)
        if enabled and phase==1:
            if a.lifecycle:
                awaiting('Event',GLib.Variant('(isvu)',(node.remote,'clicked',GLib.Variant('i',0),0)))
            else:event(node.remote,'clicked')
            log('application-command',identifier=node.remote,native=identifier)
        return int(bool(enabled))
    except Exception as error:
        log('callback-error',message=str(error));return 0


def pump(unused):
    # Native input/tracking stays in GNUstep while descriptor work is serviced.
    while context.pending():context.iteration(False)


def awaiting(method,parameters):
    response = {}
    def completed(connection,result,unused):
        try:response['value'] = connection.call_finish(result).unpack()
        except GLib.Error as error:response['error'] = error
    bus.call(owner,a.path,'com.canonical.dbusmenu',method,parameters,None,
        Gio.DBusCallFlags.NONE,3000,None,completed,None)
    deadline = time.monotonic()+3.2
    while alive and not response and time.monotonic()<deadline:
        pump(None);time.sleep(.001)
    if 'error' in response:raise response['error']
    if not alive or not response:
        raise RuntimeError('Menu owner unavailable or request expired')
    return response['value']


def accept_layout(value):
    global pending_root,revision
    incoming,root = value
    if revision is not None and incoming<revision:return
    revision = incoming
    pending_root = model.reconcile(root)
    (a.output/'layout.json').write_text(json.dumps(dict(revision=revision,root=root),indent=2)+'\n')


def lifecycle(unused,token,phase):
    global native_root,pending_root,generation,fetching,dirty
    try:
        if phase==1:
            if alive:
                generation += 1;fetching = False
                accept_layout(awaiting('GetLayout',GLib.Variant('(iias)',(0,-1,[]))))
            node = model.nodes.get(token)
            previous = opened.pop(token,None)
            remote = node.remote if node is not None else previous
            if alive and remote is not None:
                awaiting('Event',GLib.Variant('(isvu)',(remote,'closed',GLib.Variant('i',0),0)))
            log('native-submenu-closed',native=token,remote=remote)
            return 1
        node = model.nodes.get(token)
        if not alive or node is None:return 0
        opened[token] = node.remote
        # Invalidate earlier asynchronous root reads before this preparation.
        generation += 1;fetching = False
        awaiting('Event',GLib.Variant('(isvu)',(node.remote,'opened',GLib.Variant('i',0),0)))
        accept_layout(awaiting('GetLayout',GLib.Variant('(iias)',(0,-1,[]))))
        node = model.nodes.get(token)
        if node is None:
            log('native-submenu-identity-replaced',native=token)
            return 0
        opened[token] = node.remote
        branch = array_for(node)
        if not native.nxs_menu_branch_items(menu,token,branch,len(branch)):return 0
        native_root = replace_children(native_root,token,node.children)
        dirty = False
        log('native-submenu-prepared',native=token,remote=node.remote,count=len(branch),revision=revision)
        return 1
    except Exception as error:
        log('native-submenu-error',message=str(error));return 0


def fetched(connection,result,epoch):
    global fetching,alive
    try:
        value = connection.call_finish(result).unpack()
        if epoch==generation:
            fetching = False
            accept_layout(value)
    except (GLib.Error,ValueError,TypeError) as error:
        if epoch==generation:
            fetching = False;alive = False
            native.nxs_menu_cancel(menu)
            log('layout-error',message=str(error))


def changed(*unused):
    global dirty
    dirty = True
    request_layout()


def request_layout():
    global dirty,fetching
    if not alive or fetching:return
    dirty,fetching = False,True
    bus.call(owner,a.path,'com.canonical.dbusmenu','GetLayout',
        GLib.Variant('(iias)',(0,-1,[])),None,Gio.DBusCallFlags.NONE,
        3000,None,fetched,generation)


def name_changed(connection,sender,path,interface,member,parameters,unused):
    global alive
    name,old,new = parameters.unpack()
    if name==owner and old and not new:
        alive = False
        native.nxs_menu_cancel(menu)
        log('owner-lost')


command_callback,pump_callback = Command(command),Pump(pump)
menu = native.nxs_menu_create(a.title.encode(),command_callback,pump_callback,None)
if not menu:raise SystemExit('Native menu host initialization failed')
if a.lifecycle:
    if not native.nxs_native_ui_menu_capabilities()&4:
        raise SystemExit('Native submenu lifecycle support is required')
    Lifecycle = C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint64,C.c_uint)
    lifecycle_callback = Lifecycle(lifecycle)
    native.nxs_menu_lifecycle.argtypes = [C.c_void_p,Lifecycle,C.c_void_p]
    native.nxs_menu_lifecycle.restype = C.c_int
    native.nxs_menu_branch_items.argtypes = [C.c_void_p,C.c_uint64,C.POINTER(MenuItem),C.c_uint32]
    native.nxs_menu_branch_items.restype = C.c_int
    assert native.nxs_menu_lifecycle(menu,lifecycle_callback,None)
subscriptions = [bus.signal_subscribe(owner,'com.canonical.dbusmenu',member,a.path,None,
    Gio.DBusSignalFlags.NONE,changed,None) for member in ('LayoutUpdated','ItemsPropertiesUpdated')]
subscriptions.append(bus.signal_subscribe('org.freedesktop.DBus','org.freedesktop.DBus',
    'NameOwnerChanged','/org/freedesktop/DBus',owner,Gio.DBusSignalFlags.NONE,name_changed,None))


def stop(*unused):
    global alive
    alive = False
    native.nxs_menu_cancel(menu)


bus.connect('closed',lambda *unused:stop())
signal.signal(signal.SIGTERM,stop)
signal.signal(signal.SIGINT,stop)
signal.signal(signal.SIGUSR1,dump_states)
try:
    while alive:
        pump(None)
        if not alive:break
        if dirty and not fetching:
            request_layout()
        if pending_root is not None:
            if projection(pending_root)==projection(native_root):pending_root = None
            else:
                array = array_for(pending_root)
                if native.nxs_menu_items(menu,array,len(array)):
                    native_root,pending_root = pending_root,None
                    if not native.nxs_menu_show(menu,1):raise RuntimeError('Native menu could not be shown')
                    dump_states()
                    log('native-menu',owner=owner,pid=actual_pid,count=len(array),revision=revision)
        native.nxs_native_ui_dispatch_events(.005)
        time.sleep(.001)
finally:
    native.nxs_menu_cancel(menu)
    for subscription in subscriptions:bus.signal_unsubscribe(subscription)
    assert native.nxs_menu_destroy(menu)
    log('stopped')
