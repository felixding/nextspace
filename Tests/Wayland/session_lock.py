#!/usr/bin/env python3
"""Exercise lock authority, actual output pixels, input and fail-closed recovery."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import tempfile
import time

from integration import read_json_lines, until
from text_input import Client
from shell import Shell


def run(compositor, probe, artifacts, input_probe, shell_probe, gui_probe=None, greeter=False):
    artifacts.mkdir(parents=True, exist_ok=True)
    clients, processes = [], []
    with tempfile.TemporaryDirectory(prefix='nextspace-lock-') as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS='headless', WLR_HEADLESS_OUTPUTS='2',
                   WLR_RENDERER='pixman', NEXTSPACE_LOCK_PIXEL_CHECK='1',XDG_SESSION_CLASS='greeter' if greeter else 'user')
        for name in ('DISPLAY', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET'): env.pop(name, None)
        control, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        broker, peer = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        control.settimeout(5)
        with (artifacts/'compositor.log').open('w') as log:
            server = subprocess.Popen([compositor, '-c', str(child.fileno()), '-S', str(peer.fileno())],
                pass_fds=[child.fileno(), peer.fileno()], env=env, stdout=subprocess.PIPE, stderr=log, text=True)
        child.close(); peer.close()
        def command(text):
            control.sendall(text.encode()); return json.loads(control.recv(65536))
        def state(): return command('lock-state')
        def pixels(kind, epoch=None):
            heads = [head for head in command('outputs') if head['width'] and head['height']]
            values = {head['name']: command('output-pixels '+head['name']) for head in heads}
            if not values or any(not row or (epoch is not None and row['epoch']!=epoch) for row in values.values()): return None
            if kind == 'black':
                return values if all(row['black']==row['width']*row['height'] for row in values.values()) else None
            surfaces = {row['output']:row for row in command('lock-surfaces') if row['mapped']}
            for head in heads:
                row, surface = values[head['name']], surfaces.get(head['name'])
                width = (head['width']*head['scale']+60)//120
                height = (head['height']*head['scale']+60)//120
                if not surface or (surface['width'],surface['height'],surface['buffer_width'],surface['buffer_height']) != (
                    head['width'],head['height'],width,height): return None
                # Integer logical output extents can leave a physical rounding
                # margin. Require the exact locker area and only black outside it.
                expected = min(width,row['output_width'])*min(height,row['output_height'])
                if row['locker']!=expected or row['other'] or row['black']!=row['width']*row['height']-expected: return None
            return values
        index = 0
        def start_locker():
            nonlocal index
            label = str(index); index += 1
            item = Client(probe, None, env, artifacts, 'locker-'+label, broker, b'L')
            clients.append(item)
            def wait_event(name, count=1):
                def check():
                    item.pump()
                    assert item.process.poll() is None, item.process.returncode
                    return [row for row in item.events if row['event']==name][count-1:count]
                return until(check, 'locker '+name)[0]
            return item, wait_event

        def no_events(item, names, start):
            item.sync()
            assert not any(row['event'] in names for row in item.events[start:]), item.events[start:]

        def configure(shell, proposal):
            shell.pump()
            shell.send(f'configure {shell.output_revision}')
            for head in proposal:
                shell.send('head '+' '.join(str(head[key]) for key in (
                    'id','enabled','primary','width','height','refresh','scale','transform','x','y')))
            for request, status in (('apply 10000',1),('confirm',2)):
                before = len(shell.configuration_results)
                shell.send(request)
                shell.wait(lambda: len(shell.configuration_results)>before, 'locked '+request)
                assert shell.configuration_results[-1]['status']==status, shell.configuration_results[-1]
        records = []
        try:
            assert select.select([server.stdout], [], [], 10)[0]
            line = server.stdout.readline().strip(); assert line.startswith('WAYLAND_DISPLAY='), line
            env['WAYLAND_DISPLAY'] = line.split('=',1)[1]
            public = subprocess.run([probe, '--registry'], env=env, capture_output=True, text=True, timeout=10)
            assert public.returncode==0 and not json.loads(public.stdout)['manager_visible'], public.stderr
            assert not state()['locked'] and state()['desktop_visible']
            shell = Shell(shell_probe, broker, env, artifacts, 'lock', version=17)
            clients.append(shell)
            shell.wait(lambda: shell.output_batches, 'lock output inventory')
            if greeter:
                before=shell.output_batches;shell.send('lock');shell.send('outputs')
                shell.wait(lambda:shell.output_batches>before,'greeter shell request completed')
                for key in (29,56,38):assert command(f'key {key} 1')['ok']
                for key in (38,56,29):assert command(f'key {key} 0')['ok']
                broker.send(b'R')
                broker.send(b'P')
                broker.send(b'W')
                # Processing a subsequent descriptor on this same ordered
                # broker proves the preceding supervisor request was handled.
                replacement=Shell(shell_probe,broker,env,artifacts,'greeter-replaced',version=17)
                clients.append(replacement)
                assert not state()['locked'] and state()['desktop_visible']
                (artifacts/'results.json').write_text('{"greeter_lock_requests_ignored":true}\n')
                print('Greeter ignores user shell, shortcut and supervisor lock requests: PASS')
                return
            text = Client(input_probe, '--text-input', env, artifacts, 'ordinary')
            clients.append(text); text.wait('enter'); text.send('enable'); text.sync()
            method = Client(input_probe, '--input-method', env, artifacts, 'method', broker)
            clients.append(method); method.wait('activate')
            method.send('grab'); method.wait('keymap'); method.sync()
            # Prove these exact clients receive input before testing isolation.
            begin = method.sync()
            for pressed in (1, 0): assert command(f'key 30 {pressed}')['ok']
            method.wait('key', begin); method.sync()
            assert [row['state'] for row in method.events[begin:] if row['event']=='key']==[1,0]
            begin = text.sync()
            method.send('forward 30 1'); method.send('forward 30 0'); method.sync()
            text.wait('key', begin); text.sync()
            assert [row['state'] for row in text.events[begin:] if row['event']=='key']==[1,0]
            window = next(row for row in command('windows') if row['title']=='TextInputProbe')
            assert command(f"pointer {window['x']+32} {window['y']+32}")['ok']
            for pressed in (1, 0): assert command(f'button 272 {pressed}')['ok']
            text.wait('button', begin); text.sync()
            assert [row['state'] for row in text.events[begin:] if row['event']=='button']==[1,0]
            method.send('popup'); method.wait('rectangle')
            for scale in (120, 150, 180, 210, 240):
                for head in command('outputs'):
                    assert command(f"test-scale {head['name']} {scale} 10000")['ok']; assert command('confirm')['ok']
                locker, wait = start_locker()
                process, send = locker.process, locker.send
                ready = locker.wait('ready')
                guessed = subprocess.run([probe, '--guess', str(ready['manager'])], env=env,
                    capture_output=True, text=True, timeout=10)
                (artifacts/f'guess-{scale}.json').write_text(json.dumps(dict(status=guessed.returncode,
                    stdout=guessed.stdout, stderr=guessed.stderr),indent=2)+'\n')
                assert guessed.returncode==0 and not state()['locked']
                send('lock'); wait('locked')
                locked = state(); assert locked['locked'] and locked['acknowledged'] and not locked['desktop_visible']
                assert locked['pending_outputs']==0
                method.wait('deactivate'); method.sync()
                assert command('input-popups')==[]
                blank = until(lambda: pixels('black',locked['epoch']), 'every output fully blank before locked acknowledgement')
                send('paint')
                painted = until(lambda: pixels('locker',locked['epoch']), 'exact locker buffers and opaque output margins')
                text_start, method_start = text.sync(), method.sync()
                assert command('key 30 1')['ok']; assert command('key 30 0')['ok']; wait('key',2)
                head = command('outputs')[0]
                assert command(f"pointer {head['x']+head['width']//2} {head['y']+head['height']//2}")['ok']
                assert command('button 272 1')['ok']; assert command('button 272 0')['ok']; wait('button',2)
                method.send('forward 48 1'); method.send('forward 48 0')
                method.send('commit forbidden'); method.send('done'); method.sync()
                text.send('enable'); text.sync()
                no_events(text, {'key','button','commit','preedit','delete'}, text_start)
                no_events(method, {'key','activate','surrounding'}, method_start)
                locker.sync()
                assert len([row for row in locker.events if row['event']=='key'])==2
                send('unlock')
                until(lambda: not state()['locked'] and state()['desktop_visible'], 'authorized unlock restores desktop')
                until(lambda: all(command('output-pixels '+h['name']).get('other',0)>0 for h in command('outputs')),
                      'ordinary output content restored')
                send('quit'); process.wait(timeout=5); assert process.returncode==0
                text.send('enable'); text.sync(); method.sync()
                records.append(dict(scale=scale, blank=blank, painted=painted, locked=locked))
            while select.select([broker],[],[],0)[0]:broker.recv(1)
            shell.send('lock')
            until(lambda:state()['locked'] and not state()['active'],'shell request blanks before locker startup')
            assert select.select([broker],[],[],5)[0] and broker.recv(1)==b'R'
            until(lambda:pixels('black',state()['epoch']),'shell request blanks all outputs')
            locker,wait=start_locker();send=locker.send
            send('lock');wait('locked');send('paint');until(lambda:pixels('locker'),'shell-requested locker')
            other=Client(input_probe,'--text-input',env,artifacts,'ordinary-opened-while-locked')
            clients.append(other)
            until(lambda:any(row['pid']==other.process.pid for row in command('windows')),'ordinary app maps under lock')
            until(lambda:pixels('locker'),'new ordinary app remains behind lock')
            for pressed in (1,0):assert command(f'key 30 {pressed}')['ok']
            no_events(other,{'enter','key','button','commit'},0)
            other.stop();clients.remove(other)
            send('unlock');until(lambda:not state()['locked'],'shell-requested authorized unlock')
            send('quit');locker.process.wait(timeout=5);assert locker.process.returncode==0
            # Presses can straddle the lock boundary. A release while blank must
            # not reach the old client, and normal input must resume afterward.
            text.send('disable'); text.sync(); method.sync()
            window = next(row for row in command('windows') if row['title']=='TextInputProbe')
            assert command(f"pointer {window['x']+32} {window['y']+32}")['ok']
            start = text.sync()
            assert command('key 30 1')['ok']; assert command('button 272 1')['ok']
            text.wait('key',start); text.wait('button',start)
            locker, wait = start_locker(); send = locker.send
            send('lock'); wait('locked')
            start = text.sync()
            assert command('key 30 0')['ok']; assert command('button 272 0')['ok']
            no_events(text, {'key','button'}, start)
            send('paint'); until(lambda: pixels('locker'), 'held-input lock paint')
            assert command('key 48 1')['ok']; wait('key')
            head = command('outputs')[0]
            assert command(f"pointer {head['x']+32} {head['y']+32}")['ok']
            assert command('button 272 1')['ok']; wait('button')
            send('unlock'); until(lambda: not state()['locked'], 'unlock with held input')
            assert command('key 48 0')['ok']; assert command('button 272 0')['ok']
            assert command(f"pointer {window['x']+32} {window['y']+32}")['ok']
            start = text.sync()
            for pressed in (1,0):
                assert command(f'key 46 {pressed}')['ok']; assert command(f'button 272 {pressed}')['ok']
            text.wait('key',start); text.wait('button',start); text.sync()
            assert [row['state'] for row in text.events[start:] if row['event']=='key']==[1,0]
            assert [row['state'] for row in text.events[start:] if row['event']=='button']==[1,0]
            send('quit'); locker.process.wait(timeout=5); assert locker.process.returncode==0
            native_records, native_runtime = [], {}
            if gui_probe:
                path = artifacts/'native.log'
                with path.open('w') as log:
                    native = subprocess.Popen([gui_probe,'-GSBackend','libgnustep-wayland',
                        '-GSTheme','NextSpace','-NSUseRunningCopy','NO'],env=env,stdout=log,stderr=log)
                processes.append(native)
                def events():
                    assert native.poll() is None, path.read_text()[-3000:]
                    return read_json_lines(path,'{"')
                window = until(lambda: next((row for row in command('windows') if row['pid']==native.pid and
                    row['title']=='WaylandProbe' and row['visible'] and row['width']>200),None), 'native lock victim')
                libraries=sorted({row.split()[-1] for row in Path(f'/proc/{native.pid}/maps').read_text().splitlines()
                    if any(name in row for name in ('libgnustep-base.so.','libgnustep-gui.so.','libgnustep-wayland-',
                        'libobjc.so.','libcairo.so.','libwayland-client.so.'))})
                assert any('libgnustep-wayland-' in path for path in libraries)
                native_runtime={path:hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in libraries}
                for scale in (120,150,180,210,240):
                    for head in command('outputs'):
                        assert command(f"test-scale {head['name']} {scale} 10000")['ok']; assert command('confirm')['ok']
                    head = min(command('outputs'),key=lambda row:row['x'])
                    assert command(f"move {window['id']} {head['x']+10} {head['y']+10}")['ok']
                    assert command(f"raise {window['id']}")['ok']
                    assert command(f"focus {window['id']}")['ok']
                    def ready_native():
                        current = next(row for row in command('windows') if row['id']==window['id'])
                        return current if (current['buffer_width'],current['buffer_height'])==(
                            (801*scale+60)//120,(601*scale+60)//120) else None
                    window = until(ready_native,'native lock victim at current backing scale')
                    x,y=window['x']+30,window['y']+window['height']-230
                    hit=command(f'hit {x} {y}')
                    (artifacts/f'native-target-{scale}.json').write_text(json.dumps(dict(
                        window=window,hit=hit,outputs=command('outputs'),windows=command('windows')),indent=2)+'\n')
                    assert hit['id']==window['id'],hit
                    assert command(f'pointer {x} {y}')['ok']
                    begin=len(events())
                    for pressed in (1,0): assert command(f'button 272 {pressed}')['ok']
                    until(lambda:any(row['event']=='click' for row in events()[begin:]),'native click before lock')
                    begin=len(events()); assert command('key 30 1')['ok']
                    until(lambda:any(row['event']=='key' for row in events()[begin:]),'native held key before lock')
                    locker,wait=start_locker();send=locker.send
                    send('lock');wait('locked');send('paint')
                    until(lambda:pixels('locker'),'native victim hidden by lock')
                    time.sleep(.1);begin=len(events())
                    assert command('key 30 0')['ok']
                    for pressed in (1,0):
                        assert command(f'key 48 {pressed}')['ok'];assert command(f'button 272 {pressed}')['ok']
                    time.sleep(.7)  # Exceed the toolkit's configured repeat delay.
                    assert not any(row['event'] in ('key','key-up-handled','click','mouse-handled')
                        for row in events()[begin:]),events()[begin:]
                    send('unlock');until(lambda:not state()['locked'],'native unlock')
                    assert command(f'pointer {x} {y}')['ok']
                    begin=len(events())
                    for pressed in (1,0):assert command(f'button 272 {pressed}')['ok']
                    until(lambda:any(row['event']=='click' for row in events()[begin:]),'native click after unlock')
                    begin=len(events())
                    for pressed in (1,0):assert command(f'key 45 {pressed}')['ok']
                    until(lambda:any(row['event']=='key' for row in events()[begin:]),'native key after unlock')
                    native_records.append(dict(scale=scale,resumed=events()[begin:]))
                    send('quit');locker.process.wait(timeout=5);assert locker.process.returncode==0
                native.terminate();native.wait(timeout=5)
                until(lambda:all(row['pid']!=native.pid for row in command('windows')),'native victim closed')
            locker, wait = start_locker(); process, send = locker.process, locker.send
            send('lock'); wait('locked'); send('paint'); until(lambda: pixels('locker'), 'locker before crash')
            process.kill(); process.wait(timeout=5)
            failed = until(lambda: state() if state()['locked'] and not state()['active'] else None, 'locker crash stays locked')
            assert not failed['desktop_visible']; until(lambda: pixels('black'), 'locker crash blanks every output')
            locker, wait = start_locker(); process, send = locker.process, locker.send
            send('lock'); wait('locked'); send('paint'); until(lambda: pixels('locker'), 'replacement locker')
            layouts = []
            for turn in range(8):
                shell.send('outputs'); before = shell.output_batches
                shell.wait(lambda: shell.output_batches>before, 'current locked output inventory')
                proposal = [dict(head, scale=(150,180)[i], transform=(turn+i)%8,
                    x=(-1700,100)[i], y=-200, primary=int(i==0))
                    for i,head in enumerate(shell.outputs.values())]
                configure(shell, proposal)
                layouts.append(dict(proposal=proposal,pixels=until(lambda: pixels('locker'), 'rotated mixed-density lock')))
            heads = [dict(head) for head in shell.outputs.values()]
            heads[1].update(enabled=0, primary=0); heads[0]['primary']=1
            configure(shell, heads); until(lambda: pixels('locker'), 'locked output disabled')
            heads[1]['enabled']=1
            configure(shell, heads); until(lambda: pixels('locker'), 'locked output re-enabled')
            previous = {head['name'] for head in command('outputs')}
            assert command('add-output')['ok']
            until(lambda: len(command('outputs'))==len(previous)+1, 'new output under lock')
            until(lambda: pixels('locker'), 'hotplug output receives only locker content')
            added = next(head['name'] for head in command('outputs') if head['name'] not in previous)
            assert command('remove-output '+added)['ok']
            until(lambda: len(command('outputs'))==len(previous), 'locked output removed')
            until(lambda: pixels('locker'), 'remaining locked outputs after removal')
            send('unlock'); until(lambda: not state()['locked'], 'replacement locker unlock')
            send('quit'); process.wait(timeout=5); assert process.returncode==0
            result = dict(scales=records, crash=failed, recovery=True, hotplug=True, layouts=layouts,native=native_records,
                native_runtime=native_runtime,
                passed=['hidden lock authority and guessed binding rejection', 'presented blank frames at five densities',
                        'exact fractional locker buffers and opaque rounding margins', 'exclusive locker keyboard/pointer delivery',
                        'ordinary input, IME composition/grab/popup and virtual-keyboard isolation',
                        'held input across lock/unlock and restored ordinary delivery',
                        'authorized shell request blanks before locker startup',
                        'ordinary apps opened while locked remain hidden and unfocused',
                        'eight transforms, mixed density, negative origins and output disable/enable under lock',
                        'authorized unlock', 'fail-closed crash and capability-based recovery', 'locked hotplug and removal'])
            (artifacts/'results.json').write_text(json.dumps(result,indent=2)+'\n')
            print('Compositor lock protocol/pixels/input/crash/recovery: PASS')
        except BaseException:
            try:
                (artifacts/'failure.json').write_text(json.dumps(dict(state=state(),outputs=command('outputs'),windows=command('windows'),
                    pixels={head['name']:command('output-pixels '+head['name']) for head in command('outputs')}),indent=2)+'\n')
            except (OSError, ValueError): pass
            raise
        finally:
            for process in processes:
                if process.poll() is None:process.terminate();process.wait(timeout=5)
            for item in reversed(clients): item.stop()
            if server.poll() is None: server.terminate(); server.wait(timeout=5)
            server.stdout.close(); control.close(); broker.close()
            assert server.returncode==0, f'Compositor exited with {server.returncode}'


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--compositor',required=True);parser.add_argument('--probe',required=True)
    parser.add_argument('--artifacts',type=Path,required=True)
    parser.add_argument('--input-probe',required=True)
    parser.add_argument('--shell-probe',required=True)
    parser.add_argument('--gui-probe')
    parser.add_argument('--greeter',action='store_true')
    args=parser.parse_args();run(args.compositor,args.probe,args.artifacts,args.input_probe,args.shell_probe,args.gui_probe,args.greeter)
