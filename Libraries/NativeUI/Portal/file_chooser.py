"""Standard FileChooser portal transport over the shared native file panels.

The portal frontend owns caller identity and document access. This backend
accepts only that frontend's unique bus owner. GPL-2.0-or-later.
"""
from collections import deque
from dataclasses import dataclass
import ctypes as C
import json
import os
import queue
import threading
from gi.repository import Gio, GLib
from native_files import ALLOWS, PUMP, Model

NAME = 'org.freedesktop.impl.portal.desktop.nextspace'
FRONTEND = 'org.freedesktop.portal.Desktop'
PATH = '/org/freedesktop/portal/desktop'
INTERFACE = 'org.freedesktop.impl.portal.FileChooser'
REQUEST = 'org.freedesktop.impl.portal.Request'
XML = '<node><interface name="' + INTERFACE + '">' + ''.join(
    '<method name="' + method + '"><arg type="o" direction="in"/>'
    '<arg type="s" direction="in"/><arg type="s" direction="in"/>'
    '<arg type="s" direction="in"/><arg type="a{sv}" direction="in"/>'
    '<arg type="u" direction="out"/><arg type="a{sv}" direction="out"/></method>'
    for method in ('OpenFile', 'SaveFile', 'SaveFiles')) + '</interface></node>'
REQUEST_XML = '<node><interface name="' + REQUEST + '"><method name="Close"/></interface></node>'


@dataclass
class Request:
    handle: str
    sender: str
    model: Model
    invocation: object
    registration: int = 0
    cancelled: bool = False


class FileChooser:
    def __init__(self, native):
        self.native = native
        self.jobs = queue.SimpleQueue()
        self.pending = deque()
        self.active = None
        self.panel = None
        self.stopping = False
        self.reader, self.writer = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
        self.pump = PUMP(self.drain)
        self.source = native.nxs_native_ui_source_callback(self.reader, self.pump, None)
        if not self.source:
            os.close(self.reader)
            os.close(self.writer)
            raise RuntimeError('Cannot attach the portal mailbox to the native loop')
        self.context = GLib.MainContext.new()
        self.loop = GLib.MainLoop.new(self.context, False)
        self.ready = threading.Event()
        self.error = None
        self.records = {}
        self.thread = threading.Thread(target=self.serve, name='native-file-portal', daemon=True)
        self.thread.start()
        if not self.ready.wait(5) or self.error:
            self.close()
            raise RuntimeError('Native file portal startup failed') from self.error

    def enqueue(self, operation, request=None):
        self.jobs.put((operation, request))
        try:
            os.write(self.writer, b'x')
        except BlockingIOError:
            pass  # A full pipe already wakes the original native modal loop.

    def drain(self, unused=None):
        while True:
            try:
                if not os.read(self.reader, 4096):
                    break
            except BlockingIOError:
                break
        while True:
            try:
                operation, request = self.jobs.get_nowait()
            except queue.Empty:
                break
            if operation == 'open':
                self.pending.append(request)
            elif operation == 'cancel' and request is self.active and self.panel:
                self.native.nxs_file_panel_cancel(self.panel)
            elif operation == 'stop':
                self.stopping = True
                if self.panel:
                    self.native.nxs_file_panel_cancel(self.panel)
        # Never enter a native modal session from its descriptor callback.
        # The outer UI loop starts requests after dispatch_events returns.

    def owner(self):
        try:
            return self.bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                'org.freedesktop.DBus', 'GetNameOwner', GLib.Variant('(s)', (FRONTEND,)),
                GLib.VariantType.new('(s)'), Gio.DBusCallFlags.NONE, 2000, None).unpack()[0]
        except GLib.Error:
            return None

    def call(self, connection, sender, path, interface, method, parameters, invocation):
        if sender != self.owner():
            invocation.return_dbus_error('org.freedesktop.DBus.Error.AccessDenied',
                                         'Only the desktop portal frontend may request native file dialogs')
            return
        handle, app_id, parent, title, options = parameters.unpack()
        try:
            if handle in self.records or len(self.records) >= 64:
                raise ValueError('Duplicate handle or too many pending requests')
            if not handle.startswith('/org/freedesktop/portal/desktop/request/'):
                raise ValueError('Invalid request path')
            model = Model(method, title, options, parent)
            request = Request(handle, sender, model, invocation)
            request.registration = self.bus.register_object(handle,
                Gio.DBusNodeInfo.new_for_xml(REQUEST_XML).interfaces[0], self.close_request, None, None)
            self.records[handle] = request
            self.enqueue('open', request)
            print(json.dumps(dict(event='request', method=method, handle=handle, app_id=app_id,
                                  parent=parent)), flush=True)
        except (ValueError, TypeError, UnicodeError, GLib.Error) as error:
            invocation.return_dbus_error('org.freedesktop.DBus.Error.InvalidArgs', str(error))

    def close_request(self, connection, sender, path, interface, method, parameters, invocation):
        request = self.records.get(path)
        if not request or sender != request.sender:
            invocation.return_dbus_error('org.freedesktop.DBus.Error.AccessDenied', 'Request belongs to another caller')
            return
        request.cancelled = True
        self.enqueue('cancel', request)
        invocation.return_value(GLib.Variant('()', ()))

    def owner_changed(self, connection, sender, path, interface, signal, parameters):
        name, previous, current = parameters.unpack()
        if previous:
            for request in self.records.values():
                if request.sender == previous:
                    request.cancelled = True
                    self.enqueue('cancel', request)

    def reply(self, request, response, results):
        def complete(unused=None):
            if self.records.pop(request.handle, None) is request:
                self.bus.unregister_object(request.registration)
                if request.cancelled:
                    response_value, result_value = 1, {}
                else:
                    response_value, result_value = response, results
                request.invocation.return_value(GLib.Variant('(ua{sv})', (response_value, result_value)))
                print(json.dumps(dict(event='response', handle=request.handle, response=response_value)), flush=True)
            return GLib.SOURCE_REMOVE
        self.context.invoke_full(GLib.PRIORITY_DEFAULT, complete)

    def serve(self):
        registration = subscription = None
        owned = False
        self.context.push_thread_default()
        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            registration = self.bus.register_object(PATH, Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0], self.call, None, None)
            subscription = self.bus.signal_subscribe('org.freedesktop.DBus', 'org.freedesktop.DBus',
                'NameOwnerChanged', '/org/freedesktop/DBus', FRONTEND, Gio.DBusSignalFlags.NONE,
                self.owner_changed)
            result = self.bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                'RequestName', GLib.Variant('(su)', (NAME, 4)), GLib.VariantType.new('(u)'),
                Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
            if result not in (1, 4):
                raise RuntimeError('The session already has a native file portal')
            owned = True
            self.ready.set()
            self.loop.run()
        except Exception as error:
            self.error = error
            self.ready.set()
            self.enqueue('stop')
        finally:
            for request in self.records.values():
                self.bus.unregister_object(request.registration)
                request.invocation.return_value(GLib.Variant('(ua{sv})', (1, {})))
            self.records.clear()
            if subscription:
                self.bus.signal_unsubscribe(subscription)
            if registration:
                self.bus.unregister_object(registration)
            if owned:
                try:
                    self.bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                        'ReleaseName', GLib.Variant('(s)', (NAME,)), GLib.VariantType.new('(u)'),
                        Gio.DBusCallFlags.NONE, 1000, None)
                except GLib.Error:
                    pass
            self.context.pop_thread_default()

    def run(self):
        while not self.stopping:
            self.drain()
            if self.stopping:
                break
            if not self.pending:
                self.native.nxs_native_ui_dispatch_events(0.1)
                continue
            request = self.pending.popleft()
            self.active = request
            response, results = 1, {}
            callback = ALLOWS(request.model.allows)
            try:
                if not request.cancelled:
                    self.panel = self.native.nxs_file_panel_create(request.model.mode, callback, None)
                    if request.model.config.parent_window and not self.native.nxs_file_panel_capabilities() & 2:
                        raise RuntimeError('Native file panels lack cross-client parent support')
                    if not self.panel or not self.native.nxs_file_panel_configure(self.panel, C.byref(request.model.config)):
                        raise RuntimeError('Cannot configure the native file panel')
                    response = self.native.nxs_file_panel_run(self.panel)
                    if response == 0:
                        results = request.model.results(self.native, self.panel)
            except Exception as error:
                response = 2
                print(json.dumps(dict(event='error', handle=request.handle, message=str(error))), flush=True)
            finally:
                if self.panel:
                    self.native.nxs_file_panel_destroy(self.panel)
                self.panel = self.active = None
            self.reply(request, response, results)
        if self.error:
            raise RuntimeError('Native file portal disconnected') from self.error

    def close(self):
        self.loop.quit()
        self.thread.join(timeout=3)
        self.native.nxs_native_ui_source_destroy(self.source)
        os.close(self.reader)
        os.close(self.writer)
