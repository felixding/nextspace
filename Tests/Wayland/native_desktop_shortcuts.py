"""Select/copy the full address in ordinary browsers without automation ports."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from desktop_input import Desktop

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('root', type=Path)
parser.add_argument('--probe', type=Path, default=Path('/var/tmp/nextspace-native-ui/context-provider-339/native-ui/native-pasteboard-probe'))
parser.add_argument('--browser', choices=('chromium', 'firefox'), action='append')
args = parser.parse_args()
desktop = Desktop(args.root)
rows = []
activation_attempts = []
report = args.root/('ordinary-shortcut-ux-'+ '-'.join(args.browser)+'.json'
                   if args.browser else 'ordinary-shortcut-ux.json')
base_url = 'file:///workspace/.build/native-ui/desktop-demo/native-controls.html'


def save(complete=False, **extra):
    report.write_text(json.dumps(dict(complete=complete, checks=rows,
        activation_attempts=activation_attempts, **extra), indent=2)+'\n')


def until(read, predicate, label):
    end = time.monotonic()+12
    while True:
        value = read()
        if predicate(value):
            return value
        assert time.monotonic()<end, (label, value)
        time.sleep(.05)


def check(case, passed, **details):
    rows.append(dict(case=case, passed=bool(passed), **details))
    save()
    assert passed, rows[-1]


def chord(code, modifier=56):
    for key, state in ((modifier, 1), (code, 1), (code, 0), (modifier, 0)):
        assert desktop.command(f'key {key} {state}')['ok']


hosts = {w['pid'] for w in desktop.command('windows') if w['level']==20
         and w['title'] in ('Chromium','firefox-esr')}
assert len(hosts)==1, ('shared browser menu host',hosts)
host = next(iter(hosts))
process = Path('/proc')/str(host)
assert process.stat().st_uid == os.getuid()
allowed = {'GNUSTEP_CONFIG_FILE', 'NEXTSPACE_SESSION_ID', 'XDG_RUNTIME_DIR',
           'DBUS_SESSION_BUS_ADDRESS', 'WAYLAND_DISPLAY', 'LD_LIBRARY_PATH'}
environment = dict(os.environ)
for entry in (process/'environ').read_bytes().split(b'\0'):
    if b'=' in entry:
        key, value = entry.split(b'=', 1)
        if key.decode() in allowed:
            environment[key.decode()] = os.fsdecode(value)
assert environment['XDG_RUNTIME_DIR'] == str(args.root/'runtime')


def clipboard(mode):
    try:
        value = subprocess.run([str(args.probe), mode], env=environment,
                               capture_output=True, text=True, timeout=5)
    except subprocess.TimeoutExpired as error:
        (args.root/'ordinary-shortcut-clipboard-failure.json').write_text(json.dumps(
            dict(mode=mode, timeout=5, stdout=str(error.stdout), stderr=str(error.stderr)), indent=2)+'\n')
        raise
    if value.returncode:
        (args.root/'ordinary-shortcut-clipboard-failure.json').write_text(json.dumps(
            dict(mode=mode, exit=value.returncode, stdout=value.stdout, stderr=value.stderr), indent=2)+'\n')
    return value.stdout if value.returncode==0 else None


try:
    applications = {'chromium': ('chromium-browser', 'Chromium'),
                    'firefox': ('firefox-esr', 'firefox-esr')}
    for family in args.browser or ('chromium', 'firefox'):
        app, title = applications[family]
        main = next(w for w in desktop.command('windows') if w['app_id']==app
                    and w['level']==0 and 'NEXTSPACE controls' in w['title'])
        icon = next(w for w in desktop.command('windows') if w['visible']
                    and w['app_id']=='org.nextspace.Workspace' and w['title']==app)
        def activate_browser():
            if any(w['id']==main['id'] and w['focused'] for w in desktop.command('windows')):
                return
            def exposed_point():
                windows=desktop.command('windows')
                current=next(w for w in windows if w['id']==icon['id'] and w['visible'])
                blockers=[w for w in windows if w['visible'] and w['level']==20]
                points=[(current['x']+offset,current['y']+current['height']/2)
                        for offset in (current['width']/2,current['width']-8,8)]
                return next(((x,y) for x,y in points if not any(
                    w['x']<=x<w['x']+w['width'] and w['y']<=y<w['y']+w['height']
                    for w in blockers)),None)
            # An active app's tall menu can cover its own icon at175%.
            # Only activate when switching apps, using the current screen.
            x,y=until(exposed_point,bool,'visible browser application icon')
            attempt=dict(browser=family,icon_id=icon['id'],point=[x,y])
            activation_attempts.append(attempt)
            started=time.monotonic()
            desktop.double_click(x,y)
            attempt['gesture_seconds']=time.monotonic()-started
            attempt['windows_after_gesture']=desktop.command('windows')
            save()
            until(lambda:desktop.command('windows'),
                  lambda ws:any(w['id']==main['id'] and w['focused'] for w in ws),
                  'native app icon activates browser')
        address_tag = None
        def address_focus_events():
            records=[]
            for line in (args.root/'session.stdout').read_text().splitlines():
                try:record=json.loads(line)
                except ValueError:continue
                records.append(record)
            # Switching applications can repaint a content text field before
            # the queued address command completes. Bind the observation to
            # the actual browser parent using its existing authenticated GTK
            # input-owner receipts, rather than accepting any field's focus.
            owners={r['process'] for r in records if r.get('event')=='native-auxiliary-input-reset'
                    and r.get('pid')==main['pid']}
            return [r for r in records if r.get('event')=='native-form-focus' and r.get('kind')==7
                    and r.get('accepted') and r.get('process') in owners]
        def select_address():
            # D-Bus Event acknowledgement can precede Gecko's queued focus.
            # Observe the source's accepted native-field focus notification.
            # Observe the original application's completed action before
            # sending another key; a transport acceptance can precede it.
            def completed():
                if app=='chromium-browser':
                    return (args.root/'chromium-hook.log').read_text().count(' app-menu-execute id=')
                count=0
                for line in (args.root/'session.stdout').read_text().splitlines():
                    try:record=json.loads(line)
                    except ValueError:continue
                    count+=record.get('event')=='application-command'
                return count
            before=completed()
            focus_before=len(address_focus_events())
            chord(38)
            until(completed,lambda count:count>before,'original address command completion')
            if family=='firefox':
                if address_tag is None:
                    events = until(lambda:address_focus_events()[focus_before:],
                                   lambda es:any(e['focused'] for e in es),
                                   'original address focus applied')
                    return next(e for e in reversed(events) if e['focused'])
                return until(lambda:[e for e in address_focus_events()
                             if (e['process'],e['control'])==address_tag],
                             lambda es:bool(es and es[-1]['focused']),
                             'original address focus restored')[-1]
        activate_browser()
        main = next(w for w in desktop.command('windows') if w['id']==main['id'])
        desktop.key(1)
        # Blank visible document space, below the retained browser toolbar.
        desktop.click(main['x']+main['width']-30, main['y']+160)
        until(lambda: desktop.command('windows'),
              lambda ws: any(w['id']==main['id'] and w['focused'] for w in ws), 'ordinary browser focus')
        fragment=''
        for cycle in range(3):
            name=app+'-address-'+str(cycle+1)
            activate_browser()
            # Navigate only the local page's fragment so every copy has a
            # distinct value. Do not rewrite GPBS storage behind its focused
            # Wayland owner: that neither retires its offer nor represents a
            # user copy. The distinct imported value proves each fresh copy.
            focus = select_address()
            if focus:address_tag=(focus['process'],focus['control'])
            # Use the native end-of-line action for setup, independent of
            # selection timing. The subsequent Alt+L/copy must still prove
            # that the complete, distinct URL was selected by that shortcut.
            chord(18, 29)
            for code,state in ((42,1),(4,1),(4,0),(42,0)):
                assert desktop.command(f'key {code} {state}')['ok']
            desktop.key(2+cycle)
            focus_before=len(address_focus_events())
            desktop.key(28)
            if family=='firefox':
                # Finish the setup navigation before selecting again. Its
                # original delayed content-focus restoration can otherwise
                # undo the next address selection and invalidate the copy.
                until(lambda:address_focus_events()[focus_before:],
                      lambda es:any((e['process'],e['control'])==address_tag and not e['focused'] for e in es),
                      name+' setup navigation returned focus to content')
            fragment+='#'+str(cycle+1)
            expected=base_url+fragment
            select_address()
            desktop.capture(name+'-selected')
            before_offer = desktop.command('selection-state')['serial']
            chord(46)
            # A seat-input acknowledgement precedes the browser's Copy.
            # Keep its real focus until the compositor has retained the new
            # original offer; switching earlier can revoke its permission.
            offer = until(lambda: desktop.command('selection-state'),
                          lambda s: s['serial'] != before_offer and s['owned'] and not s['pending'],
                          name+' original clipboard offer completed')
            menus = [w for w in desktop.command('windows') if w['visible'] and w['level']==20]
            check(name+'-one-owning-native-menu', len(menus)==1 and menus[0]['title']==title)
            # GPBS storage alone cannot import an external Wayland offer.
            # Activate the existing native Workspace window, whose original
            # backend imports the current clipboard, then query that storage.
            native = next(w for w in desktop.command('windows') if w['visible']
                          and w['title']=='File Viewer' and w['app_id']=='org.nextspace.Workspace')
            receiver = next(w for w in desktop.command('windows') if w['visible']
                            and w['pid']==native['pid'] and w['title']=='Workspace' and w['style']==64)
            desktop.double_click(receiver['x']+receiver['width']/2, receiver['y']+receiver['height']/2)
            until(lambda: desktop.command('windows'),
                  lambda ws: any(w['pid']==native['pid'] and w['focused'] for w in ws), 'native clipboard receiver focus')
            copied = until(lambda: clipboard('--export-text'), lambda v: v==expected, name+' full address copy')
            check(name+'-native-focus-select-and-copy', copied==expected, clipboard_offer=offer)
            # Return directly from a real native app to the original address
            # controller; no content click or focus assistance settles it.
            activate_browser()
            assert desktop.command('pointer %d %d'%(main['x']+main['width']/2, main['y']+85))['ok']
            for pressed in (1,0):
                assert desktop.command('button 273 %d'%pressed)['ok']
                time.sleep(.12)
            def context_windows():
                return [w for w in desktop.command('windows') if w['visible']
                        and w['level']==101 and w['pid']==host and w['parent_id']==main['id']]
            until(context_windows, bool, name+' first restored address context')
            time.sleep(.4)
            check(name+'-context-survives-host-deactivation', bool(context_windows()))
            desktop.capture(name+'-restored-context')
            desktop.key(1)
            until(context_windows, lambda ws:not ws, name+' first Escape closes context')
            check(name+'-first-escape-closes-context', True)
        desktop.key(1)
        desktop.click(main['x']+main['width']-30, main['y']+160)
    save(True)
    print(json.dumps(dict(complete=True, checks=len(rows))))
except BaseException as error:
    desktop.capture('ordinary-shortcut-failure')
    save(error=repr(error))
    raise
