#!/usr/bin/env python3
"""Real ordinary-client color selection, gesture security and cleanup."""
import argparse
import json
import math
from pathlib import Path
import socket
import sys
import time

from gnustep import headless_session
from cursor_assets import pixels_hash
from integration import until
from shell import Shell
from text_input import Client

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Packaging/Sources'))
from vector_art import Artwork, backing_size, premultiplied_bgra
from PIL import Image


def run(compositor, probe, shell_probe, lock_probe, artifacts, capture_probe=None):
    clients, records = [], []
    shell = None
    broker, peer = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    artwork = Artwork(Path(__file__).resolve().parents[2] / 'Libraries/gnustep/Artwork.svg')
    try:
        with headless_session(compositor, artifacts, shell_broker=peer) as (env, command):
            shell = Shell(shell_probe, broker, env, artifacts, 0, version=18)
            shell.wait(lambda: shell.output_batches, 'color-pick output inventory')
            request_id = 0

            def client(name):
                item = Client(str(probe), '--color-pick', env, artifacts, name)
                clients.append(item)
                until(lambda: any(w['pid'] == item.process.pid for w in command('windows')), 'mapped picker client')
                item.sync()
                return item

            def window(item):
                return next(w for w in command('windows') if w['pid'] == item.process.pid)

            def move(item, x, y):
                assert command(f"move {window(item)['id']} {x} {y}")['ok']
                item.sync()

            def point(item):
                w = window(item)
                return w['x'] + 20, w['y'] + 40

            def pointer(item):
                x, y = point(item)
                assert command(f'pointer {x} {y}')['ok']

            def gesture(item):
                pointer(item)
                before = item.sync()
                assert command('button 272')['ok']
                release = until(lambda: (item.pump() or next((e for e in item.events[before:]
                    if e['event'] == 'button' and e['state'] == 0), None)), 'real left-button release')
                item.sync()
                return release['serial']

            def begin(item, serial, phase):
                nonlocal request_id
                request_id += 1
                before = item.sync()
                item.send(f'begin {request_id} {serial}')
                event = result(item, before, request_id, phase)
                return request_id, event

            def result(item, start, identifier, phase):
                def check():
                    item.pump()
                    assert item.process.poll() is None
                    return next((e for e in item.events[start:] if e['event'] == 'pick'
                        and e['id'] == identifier and e['phase'] == phase), None)
                return until(check, f'pick {identifier}, phase {phase}')

            owner, source = client('owner'), client('source')
            capture = None
            output_cursors = []
            if capture_probe:
                capture = Client(str(capture_probe), None, env, artifacts, 'capture', broker, b'V')
                clients.append(capture)
            source.send('color ff2690d0'); source.sync()
            for transform in range(8):
                for density in (120, 150, 180, 210, 240):
                    heads = sorted(shell.outputs.values(), key=lambda h: h['id'])
                    layout = [dict(zip(('id','enabled','primary','width','height','refresh','scale','transform','x','y'),
                        (h['id'],1,int(i==0),1601,1001,60000,density if i==0 else 180,
                         transform if i==0 else 0,-301 if i==0 else 1501,-101 if i==0 else 0)))
                        for i,h in enumerate(heads)]
                    shell.configure_outputs(layout)
                    move(owner, -261, -61); move(source, 1541, 40)
                    serial = gesture(owner)
                    if transform == 0 and density == 120:
                        begin(owner, 0, 3)
                        begin(owner, serial ^ 0x80000000, 3)
                        begin(source, serial, 3)
                    identifier, first = begin(owner, serial, 0)
                    cursor = command('color-pick-state')
                    size = backing_size(32, density)
                    assert cursor['active'] and cursor['owner'] == window(owner)['id']
                    assert (cursor['density'],cursor['width'],cursor['height'],cursor['hotspot_x'],cursor['hotspot_y']) == (density,size,size,12,13), cursor
                    assert cursor['pixels_hash'] == pixels_hash(premultiplied_bgra(artwork.render('MagnifyGlass', size))), cursor
                    owner.send('hide-cursor'); owner.sync()
                    assert command('color-pick-state') == cursor
                    if transform == 0 and capture:
                        head = next(h for h in command('outputs') if h['x'] == -301)
                        raw_path = artifacts/f'cursor-{density}.raw'
                        before = len(capture.events)
                        capture.send(f"capture-cursor {head['name']} {raw_path.resolve()}")
                        frame = capture.wait('frame',before)
                        raw = raw_path.read_bytes()
                        pixels = Image.frombytes('RGB',(frame['width'],frame['height']),raw,'raw','BGRX',frame['stride'],1)
                        if frame['flags'] & 1:pixels = pixels.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                        x,y = point(owner);factor = density/120
                        left = int((x-head['x'])*factor-math.floor(12*factor+.5))
                        top = int((y-head['y'])*factor-math.floor(13*factor+.5))
                        actual = pixels.crop((left,top,left+size,top+size))
                        expected = Image.alpha_composite(Image.new('RGBA',(size,size),'white'),
                            artwork.render('MagnifyGlass',size)).convert('RGB')
                        maximum = max(abs(a-b) for a,b in zip(actual.tobytes(),expected.tobytes()))
                        assert maximum <= 1, ('Actual visible magnifier differs',density,maximum)
                        actual.save(artifacts/f'cursor-{density}.png')
                        output_cursors.append(dict(density=density,frame=frame,file=raw_path.name,
                            crop=[left,top,size,size],maximum_channel_difference=maximum))
                    if transform == 0 and density == 120:
                        begin(source, serial, 3)
                        source.send(f'cancel {identifier}')
                        owner.send(f'cancel {identifier+1000}'); owner.sync(); source.sync()
                        assert command('color-pick-state')['active']
                    source_before = source.sync()
                    owner_before = owner.sync()
                    pointer(source)
                    preview = result(owner, owner_before, identifier, 0)
                    assert preview['rgb'] == [38,144,208], preview
                    mixed = command('color-pick-state')
                    assert mixed['density'] == 180 and mixed['pixels_hash'] == pixels_hash(
                        premultiplied_bgra(artwork.render('MagnifyGlass', 48)))
                    owner_before = owner.sync()
                    assert command('button 272')['ok']
                    selected = result(owner, owner_before, identifier, 1)
                    assert selected['rgb'] == preview['rgb']
                    assert not command('color-pick-state')['active']
                    source.sync()
                    assert not any(e['event'] == 'button' for e in source.events[source_before:])
                    begin(owner, serial, 3)
                    assert command('color-pick-state')['seat_buttons'] == 0
                    records.append(dict(transform=transform,density=density,initial=first,preview=preview,
                        selected=selected,cursor=cursor,mixed_cursor=mixed,selection_click_suppressed=True))

            # Real clicks must resume after selection; a stale gesture cannot restart it.
            serial = gesture(source)
            move(owner, -261, -61)
            keyboard = []
            assert command(f"focus {window(owner)['id']}")['ok']
            for key in (57,28,96):
                before = owner.sync()
                assert command(f'key {key} 1')['ok']
                event = until(lambda:(owner.pump() or next((e for e in owner.events[before:]
                    if e['event']=='key' and e['key']==key and e['state']==1),None)),'real activation key')
                begin(source,event['serial'],3)
                identifier,_ = begin(owner,event['serial'],0)
                assert command(f'key {key} 0')['ok']
                before=owner.sync();owner.send(f'cancel {identifier}')
                result(owner,before,identifier,2)
                begin(owner,event['serial'],3)
                keyboard.append(dict(key=key,serial=event['serial'],accepted=True,replay_denied=True,foreign_denied=True))
            serial = gesture(owner)
            time.sleep(2.05)
            begin(owner, serial, 3)
            cancellations = []
            for mode in ('explicit', 'escape-held', 'right', 'layout', 'unmap', 'destroy', 'disconnect', 'lock'):
                owner = client('owner-' + mode); move(owner, -261, -61)
                identifier, _ = begin(owner, gesture(owner), 0)
                before = owner.sync()
                pointer(source)
                source_before = source.sync()
                if mode == 'explicit': owner.send(f'cancel {identifier}')
                elif mode == 'escape-held':
                    assert command('button 272 1')['ok']
                    assert command('key 1 1')['ok']; assert command('key 1 0')['ok']
                    assert command('button 272 0')['ok']
                elif mode == 'right': assert command('button 273')['ok']
                elif mode == 'layout': assert command('add-output')['ok']
                elif mode == 'unmap': owner.send('unmap')
                elif mode == 'destroy': owner.send('destroy')
                elif mode == 'disconnect': owner.stop()
                elif mode == 'lock':
                    shell.send('lock')
                    until(lambda: command('lock-state')['locked'], 'picker lock cancellation')
                if mode not in ('destroy','disconnect'):
                    result(owner, before, identifier, 2)
                until(lambda: not command('color-pick-state')['active'], 'picker cleanup')
                assert command('color-pick-state')['buttons'] == 0
                assert command('color-pick-state')['seat_buttons'] == 0
                source.sync()
                assert not any(e['event'] == 'button' for e in source.events[source_before:])
                if mode == 'lock':
                    begin(owner, 1, 3)
                    locker = Client(str(lock_probe), None, env, artifacts, 'locker', broker, b'L')
                    clients.append(locker); locker.send('lock'); locker.wait('locked')
                    locker.send('unlock'); until(lambda: not command('lock-state')['locked'], 'picker test unlock')
                cancellations.append(mode)
                if owner.process.poll() is None:
                    owner.send('quit'); owner.process.wait(timeout=5)
            for item in clients:
                if item.process.poll() is None:
                    item.send('quit'); item.process.wait(timeout=5)
            shell.stop()
            assert not command('windows')
    finally:
        for item in clients:
            if not item.log.closed: item.stop()
        if shell is not None and not shell.log.closed: shell.stop()
        broker.close(); peer.close()
    out = dict(passed=True,cases=records,cancellation_cases=cancellations,
        mixed_output_selections=len(records),trusted_cursor_comparisons=len(records)*2,
        actual_output_cursor_comparisons=output_cursors,
        keyboard_activation_cases=keyboard,
        all_processes_reaped=all(item.process.poll() is not None for item in clients),
        hardware_tested=False,appkit_integration_tested=False,full_plan_complete=False)
    (artifacts/'results.json').write_text(json.dumps(out,indent=2)+'\n')
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('compositor','probe','shell-probe','lock-probe'):
        parser.add_argument('--'+option,type=Path,required=True)
    parser.add_argument('--artifacts',type=Path,required=True)
    parser.add_argument('--capture-probe',type=Path)
    args=parser.parse_args()
    result=run(args.compositor,args.probe,args.shell_probe,args.lock_probe,args.artifacts,args.capture_probe)
    print(json.dumps({key:value for key,value in result.items() if key!='cases'},indent=2))
