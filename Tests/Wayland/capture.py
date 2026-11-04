#!/usr/bin/env python3
"""Real screencopy pixels, output geometry and lock-time capability revocation."""
import argparse
import array
import hashlib
import json
import os
from pathlib import Path
import select
import socket
import struct
import subprocess
import tempfile

from integration import until
from shell import Shell
from text_input import Client, stop_process


def run(compositor, probe, shell_probe, registry_probe, lock_probe, client, artifacts, sample_color=False, fullscreen_client=False):
    artifacts.mkdir(parents=True)
    records, clients, processes, shells = [], [], [], []
    transforms = {}
    with tempfile.TemporaryDirectory(prefix='nextspace-capture-') as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS='headless',
            WLR_HEADLESS_OUTPUTS='2', WLR_RENDERER='pixman', XDG_SESSION_CLASS='user')
        for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET'): env.pop(key, None)
        control, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        broker, peer = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        control.settimeout(5)
        with (artifacts/'compositor.log').open('w') as log:
            server = subprocess.Popen([compositor, '-c', str(child.fileno()), '-S', str(peer.fileno())],
                env=env, pass_fds=[child.fileno(), peer.fileno()], stdout=subprocess.PIPE, stderr=log, text=True)
        child.close(); peer.close()

        def command(text):
            control.sendall(text.encode()); return json.loads(control.recv(65536))

        def capture_client(label):
            item = Client(probe, None, env, artifacts, label, broker, b'V'); clients.append(item)
            ready = item.events[0]
            assert ready['manager_visible'] and ready['fd_cloexec'] and not ready['socket_environment'], ready
            return item

        def configure(scale, transform):
            before = shell.output_batches; shell.send('outputs')
            shell.wait(lambda: shell.output_batches > before, 'output inventory')
            heads = sorted(shell.outputs.values(), key=lambda h:h['id'])
            layout=[]
            for index, head in enumerate(heads):
                values = (head['id'],1,int(index==0),801,601,60000,scale if index==0 else 180,
                          transform if index==0 else 0,-301 if index==0 else 501,-101 if index==0 else 0)
                layout.append(dict(zip(('id','enabled','primary','width','height','refresh','scale','transform','x','y'),values)))
                transforms[head['name']]=values[7]
            shell.configure_outputs(layout)
            return command('outputs')

        try:
            assert select.select([server.stdout], [], [], 10)[0]
            line = server.stdout.readline().strip(); assert line.startswith('WAYLAND_DISPLAY=')
            env['WAYLAND_DISPLAY'] = line.split('=',1)[1]
            public = subprocess.run([probe,'--registry'],env=env,capture_output=True,text=True,timeout=10)
            assert public.returncode==0 and not json.loads(public.stdout)['manager_visible'], public.stderr
            ordinary = subprocess.run([registry_probe],env=env,capture_output=True,text=True,timeout=10)
            assert ordinary.returncode==0, ordinary.stderr
            owner = capture_client('capture-initial')
            hidden = subprocess.run([probe,'--bind',str(owner.events[0]['global'])],env=env,
                capture_output=True,text=True,timeout=10)
            assert hidden.returncode==2 and 'invalid global' in hidden.stderr, hidden
            shell = Shell(shell_probe,broker,env,artifacts,0,version=18); shells.append(shell)
            shell.wait(lambda:shell.output_batches,'capture shell inventory')
            with (artifacts/'client.log').open('w') as log:
                app = subprocess.Popen([client],env=dict(env,GDK_BACKEND='wayland'),stdout=log,stderr=log)
            processes.append(app)
            window = until(lambda:next((w for w in command('windows') if w['pid']==app.pid),None),'capture test content')
            if fullscreen_client:
                until(lambda:any(w['pid']==app.pid and w['fullscreen'] for w in command('windows')),'translucent fullscreen test content')
            else:assert command(f"move {window['id']} -100 50")['ok']
            for transform in range(8):
                for scale in (120,150,180,210,240):
                    heads = configure(scale,transform)
                    for head in heads:
                        path = artifacts/f"frame-{transform}-{scale}-{head['name']}.raw"
                        before = len(owner.events); owner.send(f"capture {head['name']} {path.resolve()}")
                        frame = owner.wait('frame',before)
                        assert (frame['width'],frame['height'])==(801,601), frame
                        raw = path.read_bytes(); assert len(raw)==frame['stride']*frame['height']
                        def pixel(x,y):
                            if frame['flags'] & 1: y=frame['height']-1-y
                            return struct.unpack_from('<I',raw,y*frame['stride']+x*4)[0]|0xff000000
                        w,h=frame['width'],frame['height']
                        pixels=[pixel((2*x+1)*w//4,(2*y+1)*h//4) for y in range(2) for x in range(2)]
                        pixels.append(pixel(w//2,h//2))
                        reference=command('output-samples '+head['name'])
                        assert pixels==reference['samples']+[reference['center']], (frame,head,pixels,reference)
                        color_checks=None
                        if sample_color:
                            from scene_color import check_frame
                            color_checks=check_frame(frame,raw,head,transforms[head['name']],command)
                        records.append(dict(scale=scale,transform=transform,output=head,frame=frame,color_samples=color_checks,
                            pixels=pixels,sha256=hashlib.sha256(raw).hexdigest(),file=path.name))
            assert any(len(set(row['pixels']))>1 for row in records), 'No nonuniform client pixels were verified'
            replacement = capture_client('capture-replacement')
            owner.process.wait(timeout=5); assert owner.process.returncode==2
            if sample_color:assert command(f"sample-color {heads[0]['x']+10} {heads[0]['y']+10}")['ok']
            locker=Client(lock_probe,None,env,artifacts,'locker',broker,b'L'); clients.append(locker)
            locker.send('lock'); locker.wait('locked')
            replacement.process.wait(timeout=5); assert replacement.process.returncode==2
            assert command('lock-state')['locked']
            if sample_color:assert not command(f"sample-color {heads[0]['x']+10} {heads[0]['y']+10}")['ok']
            # Even a new broker-authorized backend cannot connect during a lock.
            local, remote=socket.socketpair()
            broker.sendmsg([b'V'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[local.fileno()]))]);local.close()
            rejected=subprocess.run([probe,'--registry'],env=dict(env,WAYLAND_SOCKET=str(remote.fileno())),
                pass_fds=[remote.fileno()],capture_output=True,text=True,timeout=5); remote.close()
            assert rejected.returncode!=0 and not rejected.stdout, rejected
            locker.send('unlock'); until(lambda:not command('lock-state')['locked'],'unlock after capture revocation')
            resumed=capture_client('capture-resumed')
            before=len(resumed.events); path=artifacts/'resumed.raw'
            resumed.send(f"capture {heads[0]['name']} {path.resolve()}"); resumed.wait('frame',before)
            broker.close(); resumed.process.wait(timeout=5); assert resumed.process.returncode==2
            (artifacts/'results.json').write_text(json.dumps(dict(frames=records,
                checks=['ordinary registry hidden','guessed global rejected','descriptor consumed and CLOEXEC',
                    'replacement revokes old backend','lock revokes active backend','locked reconnect refused',
                    'unlock permits new backend','broker loss revokes backend'],hardware_tested=False,
                portal_tested=False,pipewire_tested=False,scene_color_samples=sum(len(c['color_samples'] or []) for c in records)),indent=2)+'\n')
            print(f'Native capture: {len(records)} output frames and capability/lock checks PASS')
        finally:
            for item in clients:
                stop_process(item.process); item.pump()
                item.process.stdin.close(); item.process.stdout.close(); item.log.close()
            for item in shells: item.stop()
            for process in processes: stop_process(process)
            stop_process(server);server.stdout.close();control.close();broker.close()


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('compositor','probe','shell-probe','registry-probe','lock-probe','client'):p.add_argument('--'+name,required=True)
    p.add_argument('--artifacts',type=Path,required=True)
    p.add_argument('--sample-color',action='store_true')
    p.add_argument('--fullscreen-client',action='store_true')
    run(**vars(p.parse_args()))
