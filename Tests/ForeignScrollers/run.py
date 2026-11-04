#!/usr/bin/env python3
"""Exercise unchanged GTK/Qt apps on native Wayland with the shared adapters."""
import argparse
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import tempfile
import time
import math
from PIL import Image, ImageChops


def until(check, message, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(.02)
    raise AssertionError(message)


def run(build, artifacts, compositor, adapters=None, selected=None):
    adapters=adapters or build
    artifacts.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix='nextspace-scrollers-') as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS='headless', WLR_RENDERER='pixman',
                   QT_QPA_PLATFORM='wayland', GDK_BACKEND='wayland', GSK_RENDERER='cairo')
        for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET', 'LD_PRELOAD', 'QT_QPA_GENERIC_PLUGINS'):
            env.pop(key, None)
        parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        parent.settimeout(5)
        with (artifacts/'compositor.log').open('w') as errors:
            server = subprocess.Popen([compositor, '-c', str(child.fileno())], pass_fds=[child.fileno()],
                                      env=env, stdout=subprocess.PIPE, stderr=errors, text=True)
        child.close()
        def command(text):
            parent.sendall(text.encode())
            return json.loads(parent.recv(65536))
        try:
            assert select.select([server.stdout], [], [], 10)[0], 'compositor startup'
            line = server.stdout.readline().strip()
            assert line.startswith('WAYLAND_DISPLAY='), line
            env['WAYLAND_DISPLAY'] = line.split('=', 1)[1]
            output_name=command('outputs')[0]['name']
            assert command(f'resize-output {output_name} 2400 1800')['ok']
            variants=[('qt','area',{}),('qt','table',{'PROBE_KIND':'table'}),('qt','tree',{'PROBE_KIND':'tree'}),('qt','text',{'PROBE_KIND':'text'}),
                      ('qt','overlap',{'PROBE_STYLE':'overlap'}),
                      ('gtk4','plain',{}),('gtk4','application',{'PROBE_APPLICATION':'1'}),('gtk3','plain',{})]
            for toolkit,kind,extra in variants:
                for enabled,density in [(False,120)]+[(True,scale) for scale in (120,150,180,210,240)]:
                    label = f'{toolkit}-{kind}-{"native" if enabled else "baseline"}-{density}'
                    if selected and label!=selected: continue
                    assert command(f'test-scale {output_name} {density} 10000')['ok']
                    assert command('confirm')['ok']
                    client_env = dict(env,**extra)
                    if enabled:
                        client_env.update(QT_PLUGIN_PATH=str(adapters/'qt6'), QT_QPA_GENERIC_PLUGINS='nextspace-scrollbars',
                                          LD_PRELOAD=str(adapters/'libnextspace-gtk-bootstrap.so'))
                    events = artifacts/(label+'.jsonl')
                    arguments=[str(build/(toolkit+'-scroller-probe'))]
                    if os.environ.get('SCROLLER_GDB'):
                        arguments=['gdb','-q','-batch','-ex','run','-ex','thread apply all bt','--args']+arguments
                    with events.open('w') as output, (artifacts/(label+'.stderr')).open('w') as errors:
                        process = subprocess.Popen(arguments, env=client_env,
                                                   stdin=subprocess.PIPE, stdout=output, stderr=errors, text=True)
                    def records():
                        # The client may be halfway through writing its next
                        # record while the observer polls the output file.
                        return [json.loads(line) for line in events.read_text().split('\n')[:-1] if line.startswith('{')]
                    def states():
                        return [row for row in records() if row['event']=='state']
                    def state():
                        assert process.poll() is None, (label, process.returncode)
                        rows = states()
                        return rows[-1] if rows else None
                    def send(text):
                        count = sum(row['event']=='done' for row in records())
                        process.stdin.write(text+'\n'); process.stdin.flush()
                        return until(lambda: state() if sum(row['event']=='done' for row in records()) > count else None, (label, text))
                    try:
                        initial = until(lambda: state() if state() and state()['ready'] else None, label)
                        wanted=math.ceil(density/120) if toolkit=='gtk3' else density/120
                        deadline=time.monotonic()+10
                        while initial['scale']!=wanted and time.monotonic()<deadline:
                            initial=send('state')
                        assert initial['scale']==wanted,(label,'client backing scale',initial)
                        starting=initial['value']
                        assert initial['native'] == enabled, initial
                        if enabled:
                            assert 0 <= initial['bar'][0] <= 2 and initial['bar'][2] == 18, initial
                            if toolkit == 'qt':
                                assert initial['viewport'][0] >= 18 and initial['direction'] == 0, initial
                                if kind=='overlap':assert initial['viewport'][0]==19,initial
                            else:
                                assert initial['direction'] == 1, initial  # GTK_TEXT_DIR_LTR
                        else:
                            assert initial['bar'][0] > 400, initial
                        send('capture '+str(artifacts/(label+'.png')))
                        if enabled:
                            reference=artifacts/(label+'.argb')
                            dimensions=json.loads(subprocess.check_output([str(build/'native-scroller-probe'),'--render',
                                str(initial['bar'][3]),str(initial['maximum']+initial['page']),str(initial['page']),
                                str(initial['value']),str(initial['scale']),str(reference)],env=env,text=True))
                            expected=Image.frombytes('RGBA',(dimensions['width'],dimensions['height']),reference.read_bytes(),'raw','BGRA')
                            actual=Image.open(artifacts/(label+'.png.bar.png')).convert('RGBA')
                            expected.save(artifacts/(label+'-reference.png'))
                            difference=ImageChops.difference(expected,actual)
                            # Foreign widget clipping composites the fractional
                            # outer edge against its own application background.
                            if initial['scale'] % 1:
                                difference=difference.crop((0,0,expected.width-1,expected.height-1))
                            assert not difference.convert('RGB').getbbox(), (label,'native pixel mismatch',difference.getbbox())
                            window = until(lambda: next((w for w in command('windows')
                                if w['title'].startswith('ForeignScroller')), None), label+' window')
                            # Use the actual window and actual widget coordinates, not guessed placement.
                            x = window['x'] + initial['bar'][0] + 9
                            y = window['y'] + initial['bar'][1] + initial['bar'][3] - 9
                            assert command(f'pointer {x} {y}')['ok']
                            assert command('button 272 1')['ok']
                            time.sleep(.08)
                            assert command('button 272 0')['ok']
                            after = until(lambda: state() if state()['value'] > starting else None, label+' native arrow')
                            assert abs(after['value'] - starting - initial['step']) < .001, (initial, after)
                            repeat_start=send(f'value {starting}')
                            (artifacts/(label+'-repeat-state.json')).write_text(json.dumps(dict(windows=command('windows'),
                              focus=command('pointer-focus'),hit=command(f'hit {x} {y}')),indent=2)+'\n')
                            assert command('button 272 1')['ok']
                            until(lambda:state()['value']>starting,label+' held-button dispatch')
                            held=send('capture '+str(artifacts/(label+'-pressed.png')))
                            if toolkit!='qt': assert held['ticks']>repeat_start['ticks'],(label,'frame clock stopped during tracking')
                            time.sleep(.65)
                            assert command('button 272 0')['ok']
                            until(lambda:state()['value']>=starting+2*initial['step'],label+' native arrow repeat')
                            pressed=Image.open(artifacts/(label+'-pressed.png.bar.png')).convert('RGBA')
                            edge=(0,max(0,actual.height-round(17*initial['scale'])),actual.width,actual.height-1)
                            assert ImageChops.difference(actual.crop(edge),pressed.crop(edge)).convert('RGB').getbbox(),(label,'pressed arrow artwork')
                            send(f'value {starting}')
                            resized = send('resize 520 400')
                            assert 0 <= resized['bar'][0] <= 2 and resized['bar'][2] == 18, resized
                            assert resized['bar'][3] > initial['bar'][3], resized
                            if toolkit=='qt' and kind=='table':
                                assert resized['vertical_header'] >= 18 and resized['horizontal_header'] == resized['viewport'][0],resized
                            if toolkit=='qt' and kind=='tree': assert resized['horizontal_header']==resized['viewport'][0],resized
                            # Drag well outside the bar to test real pointer ownership.
                            send(f'resize 480 360')
                            before=send(f'value {starting}')
                            geometry=json.loads(subprocess.check_output([str(build/'native-scroller-probe'),'--render',
                                str(before['bar'][3]),str(before['maximum']+before['page']),str(before['page']),
                                str(before['value']),'1',str(reference)],env=env,text=True))
                            knob=geometry['knob']
                            window=next(w for w in command('windows') if w['title'].startswith('ForeignScroller'))
                            x=window['x']+before['bar'][0]+9
                            y=window['y']+before['bar'][1]+knob[1]+knob[3]/2
                            assert command(f'pointer {round(x)} {round(y)}')['ok']
                            assert command('button 272 1')['ok']
                            time.sleep(.08)
                            assert abs(state()['value']-starting)<.001,(label,'thumb press moved content')
                            assert command(f'pointer {round(x+120)} {round(y+30)}')['ok']
                            time.sleep(.08)
                            assert command('button 272 0')['ok']
                            dragged=until(lambda:state() if state()['value']>starting else None,label+' native drag')
                            send('capture '+str(artifacts/(label+'-dragged.png')))
                            # A second gesture proves release ended native tracking.
                            reset=send(f'value {starting}')
                            assert command(f'pointer {round(x)} {round(window["y"]+reset["bar"][1]+reset["bar"][3]-9)}')['ok']
                            assert command('button 272')['ok']
                            until(lambda:state()['value']>starting,label+' second gesture')
                            windows=command('windows')
                            (artifacts/(label+'-windows.json')).write_text(json.dumps(windows,indent=2)+'\n')
                            assert len([w for w in windows if w['buffer_width']>0])==1,(label,'extra mapped native backing window',windows)
                            if (toolkit,kind) in [('qt','area'),('gtk4','plain')]:
                                next_density=180 if density==150 else 150
                                assert command(f'test-scale {output_name} {next_density} 10000')['ok']
                                assert command('confirm')['ok']
                                live=send('state');deadline=time.monotonic()+10
                                while live['scale']!=next_density/120 and time.monotonic()<deadline:live=send('state')
                                assert live['scale']==next_density/120,(label,'live density',live)
                                path=artifacts/(label+'-live.png');live=send('capture '+str(path))
                                native=artifacts/(label+'-live.argb')
                                size=json.loads(subprocess.check_output([str(build/'native-scroller-probe'),'--render',
                                    str(live['bar'][3]),str(live['maximum']+live['page']),str(live['page']),str(live['value']),
                                    str(live['scale']),str(native)],env=env,text=True))
                                expected_live=Image.frombytes('RGBA',(size['width'],size['height']),native.read_bytes(),'raw','BGRA')
                                actual_live=Image.open(str(path)+'.bar.png').convert('RGBA')
                                assert actual_live.size==expected_live.size,(label,'live bitmap size')
                                difference=ImageChops.difference(actual_live,expected_live).convert('RGB')
                                if live['scale']%1:difference=difference.crop((0,0,actual_live.width-1,actual_live.height-1))
                                assert not difference.getbbox(),(label,'live native pixels',difference.getbbox())
                        results.append(dict(toolkit=toolkit,kind=kind,density=density,enabled=enabled,state=initial,passed=True))
                        print(label+' PASS',flush=True)
                        process.stdin.write('quit\n');process.stdin.flush()
                        code=process.wait(timeout=5)
                        assert code==0,(label,'normal shutdown',code)
                    finally:
                        process.terminate()
                        try: process.wait(timeout=5)
                        except subprocess.TimeoutExpired: process.kill(); process.wait()
                        process.stdin.close()
            (artifacts/'results.json').write_text(json.dumps(results, indent=2)+'\n')
        finally:
            if server.poll() is None:
                command('quit')
            server.wait(timeout=5)
            parent.close()
    print(f'{len(results)} baseline/native toolkit cases PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--compositor', default='/usr/NextSpace/bin/nextspace-compositor')
    parser.add_argument('--adapters',type=Path)
    parser.add_argument('--case')
    args = parser.parse_args()
    run(args.build.resolve(), args.artifacts.resolve(), args.compositor,args.adapters.resolve() if args.adapters else None,args.case)
