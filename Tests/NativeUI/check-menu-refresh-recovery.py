#!/usr/bin/env python3
"""Exercise real D-Bus refresh timeout, recovery and owner loss; no UI fixture."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
from gi.repository import Gio, GLib

repo = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(repo/'Experiments/DBusMenus'), str(repo/'Experiments/ChromiumScrollers')]
from binding import MenuBinding
from native_menus import MenuState

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--queued-commands', action='store_true')
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=False)
rows, events, items = [], [], []
revision, delay, cancellations = 1, False, 0
delay_click, clicks = False, []
disable_after_click = False


def check(case, passed):
    rows.append(dict(case=case, passed=bool(passed)))
    (a.output/'results.json').write_text(json.dumps(dict(complete=False, checks=rows), indent=2)+'\n')
    assert passed, case


class Function:
    def __init__(self, call): self.call = call
    def __call__(self, *args): return self.call(*args)


class Sink:
    """Record transport projection/cancellation without implementing controls."""
    def __init__(self):
        def create(title, command, *unused):
            self.command = command
            return 1
        def cancel(*unused):
            global cancellations
            cancellations += 1
            return 1
        def project(menu, array, count):
            items.append([(array[i].command, array[i].title.decode()) for i in range(count)])
            return 1
        for name, call in dict(
            nxs_native_ui_menu_capabilities=lambda:7,
            nxs_menu_create=create, nxs_menu_items=project,
            nxs_menu_lifecycle=lambda *unused:1,
            nxs_menu_branch_items=lambda *unused:1,
            nxs_menu_show=lambda *unused:1, nxs_menu_cancel=cancel,
            nxs_menu_destroy=lambda *unused:1,
            nxs_menu_state=lambda *unused:MenuState(),
            nxs_native_ui_dispatch_events=lambda *unused:0,
        ).items(): setattr(self, name, Function(call))


service = Gio.DBusConnection.new_for_address_sync(
    os.environ['DBUS_SESSION_BUS_ADDRESS'],
    Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
    None, None)
xml = '''<node><interface name="com.canonical.dbusmenu">
<method name="GetLayout"><arg type="i" direction="in"/><arg type="i" direction="in"/>
<arg type="as" direction="in"/><arg type="u" direction="out"/>
<arg type="(ia{sv}av)" direction="out"/></method>
<method name="Event"><arg type="i" direction="in"/><arg type="s" direction="in"/>
<arg type="v" direction="in"/><arg type="u" direction="in"/></method>
<signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
</interface></node>'''


def reply(invocation, version):
    item = GLib.Variant('(ia{sv}av)', (version, {
        'label':GLib.Variant('s', 'Original command'),
        'enabled':GLib.Variant('b', version%2==1)}, []))
    invocation.return_value(GLib.Variant('(u(ia{sv}av))', (version, (0, {}, [item]))))
    return GLib.SOURCE_REMOVE


def method(connection, sender, path, interface, name, parameters, invocation):
    global revision
    if name == 'Event':
        identifier, event, *unused = parameters.unpack()
        if event == 'clicked':
            clicks.append(identifier)
            if disable_after_click:
                revision += 1
                service.emit_signal(None, '/menu', 'com.canonical.dbusmenu',
                    'LayoutUpdated', GLib.Variant('(ui)', (revision, 0)))
        def acknowledge():
            invocation.return_value(GLib.Variant('()', ()))
            return GLib.SOURCE_REMOVE
        if delay_click and event == 'clicked': GLib.timeout_add(3500, acknowledge)
        else: acknowledge()
        return
    if delay: GLib.timeout_add(3500, reply, invocation, revision)
    else: reply(invocation, revision)


registration = service.register_object('/menu', Gio.DBusNodeInfo.new_for_xml(xml).interfaces[0], method, None, None)
sink = Sink()
binding = MenuBinding(lambda:sink, service=service.get_unique_name(), path='/menu',
    owner=os.getpid(), title='Refresh recovery', output=a.output/'binding',
    lifecycle=a.queued_commands, deferred=a.queued_commands,
    logger=lambda event, **values:events.append(dict(event=event, **values)))


def until(predicate, seconds=6):
    end = time.monotonic()+seconds
    while not predicate():
        binding.tick()
        assert time.monotonic()<end, events
        time.sleep(.005)


try:
    until(lambda:len(items)==1)
    original = items[0][0][0]
    check('initial-original-model-projected', bool(original))
    delay = True
    service.emit_signal(None, '/menu', 'com.canonical.dbusmenu', 'LayoutUpdated', GLib.Variant('(ui)', (1, 0)))
    until(lambda:any(e['event']=='layout-retry' for e in events))
    check('real-three-second-timeout-retries', binding.is_alive())
    check('timeout-keeps-original-native-menu', cancellations==0 and len(items)==1)
    delay = False
    revision = 2
    until(lambda:len(items)>1)
    check('retry-refreshes-from-same-owner', binding.is_alive() and items[-1][0][0]==original)
    check('no-fatal-layout-error-on-recovery', not any(e['event']=='layout-error' for e in events))
    if a.queued_commands:
        revision = 3
        service.emit_signal(None, '/menu', 'com.canonical.dbusmenu', 'LayoutUpdated', GLib.Variant('(ui)', (revision, 0)))
        until(lambda:len(items)>=3)
        delay = True
        start = len(events)
        check('queued-action-admitted', sink.command(None, original, 1)==1)
        until(lambda:any(e['event'] in ('layout-retry','callback-error') for e in events[start:]))
        check('refresh-timeout-before-action-observed', binding.is_alive())
        check('unvalidated-command-not-dispatched', not clicks)
        delay = False
        until(lambda:len(clicks)==1)
        check('accepted-command-recovers-without-another-key', len(clicks)==1)
        check('recovered-command-uses-original-current-id', clicks==[revision])
        delay_click = True
        start = len(events)
        check('uncertain-action-admitted', sink.command(None, original, 1)==1)
        until(lambda:any(e['event']=='callback-error' for e in events[start:]))
        check('uncertain-action-timeout-observed', len(clicks)==2)
        end = time.monotonic()+1
        while time.monotonic()<end:
            binding.tick();time.sleep(.005)
        check('uncertain-action-is-never-repeated', len(clicks)==2)
        delay_click = False
        revision = 5
        service.emit_signal(None, '/menu', 'com.canonical.dbusmenu',
            'LayoutUpdated', GLib.Variant('(ui)', (revision, 0)))
        until(lambda:json.loads((a.output/'binding/layout.json').read_text())['revision']==5)
        disable_after_click = True
        check('consecutive-actions-admitted',
            sink.command(None, original, 1)==1 and sink.command(None, original, 1)==1)
        until(lambda:len(clicks)>=3)
        until(lambda:json.loads((a.output/'binding/layout.json').read_text())['revision']>=6)
        end = time.monotonic()+.2
        while time.monotonic()<end:
            binding.tick();time.sleep(.005)
        check('next-action-revalidates-after-first-changes-availability', clicks==[3,3,5])
    service.close_sync(None)
    until(lambda:not binding.is_alive())
    check('actual-owner-loss-still-cancels-menu', cancellations>0 and any(e['event']=='owner-lost' for e in events))
    assert binding.close()
    (a.output/'results.json').write_text(json.dumps(dict(complete=True, checks=rows, events=events), indent=2)+'\n')
    print(json.dumps(dict(complete=True, checks=len(rows))))
finally:
    binding.close()
    if not service.is_closed(): service.close_sync(None)
    (a.output/'transport-events.json').write_text(json.dumps(dict(events=events,clicked=clicks),indent=2)+'\n')
