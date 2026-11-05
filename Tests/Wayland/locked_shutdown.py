#!/usr/bin/env python3
"""A locked compositor must tear down cleanly with live or disappearing clients."""
import argparse
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import tempfile
from integration import until
from text_input import Client, stop_process


def run(compositor, locker, client, artifacts):
    artifacts.mkdir(parents=True)
    records=[]
    for scale in (120,150,180,210,240):
        for order in ('server','locker','client'):
            directory=artifacts/f'{scale}-{order}';directory.mkdir()
            with tempfile.TemporaryDirectory(prefix='nextspace-locked-exit-') as runtime:
                env=dict(os.environ,XDG_RUNTIME_DIR=runtime,WLR_BACKENDS='headless',
                    WLR_HEADLESS_OUTPUTS='2',WLR_RENDERER='pixman',XDG_SESSION_CLASS='user')
                for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET'):env.pop(key,None)
                control,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
                broker,peer=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);control.settimeout(5)
                with (directory/'compositor.log').open('w') as log:
                    server=subprocess.Popen([compositor,'-c',str(child.fileno()),'-S',str(peer.fileno())],env=env,
                        pass_fds=[child.fileno(),peer.fileno()],stdout=subprocess.PIPE,stderr=log,text=True)
                child.close();peer.close();app=lock=None
                def command(text):
                    control.sendall(text.encode());return json.loads(control.recv(65536))
                try:
                    assert select.select([server.stdout],[],[],10)[0]
                    env['WAYLAND_DISPLAY']=server.stdout.readline().strip().split('=',1)[1]
                    for head in command('outputs'):
                        assert command(f"test-scale {head['name']} {scale} 10000")['ok'];assert command('confirm')['ok']
                    with (directory/'client.log').open('w') as log:
                        app=subprocess.Popen([client],env=dict(env,GDK_BACKEND='wayland'),stdin=subprocess.PIPE,stdout=log,stderr=log)
                    until(lambda:any(w['pid']==app.pid and w['visible'] for w in command('windows')),'live shutdown client')
                    lock=Client(locker,None,env,directory,'locker',broker,b'L');lock.send('lock');lock.send('paint')
                    lock.wait('locked');until(lambda:command('lock-state')['acknowledged'],'shutdown fixture locked')
                    if order=='locker':stop_process(lock.process)
                    elif order=='client':stop_process(app)
                    assert command('lock-state')['locked']
                    server.terminate();server.wait(timeout=10)
                    assert server.returncode==0,(directory/'compositor.log').read_text()[-5000:]
                    records.append(dict(scale=scale,order=order,exit=server.returncode))
                finally:
                    if lock:
                        stop_process(lock.process);lock.pump();lock.log.close();lock.process.stdout.close();lock.process.stdin.close()
                    if app:stop_process(app);app.stdin.close()
                    stop_process(server);server.stdout.close();control.close();broker.close()
    (artifacts/'results.json').write_text(json.dumps(dict(cases=records),indent=2)+'\n')
    print(f'Locked compositor shutdown: {len(records)} cases PASS')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('compositor','locker','client'):p.add_argument('--'+name,required=True)
    p.add_argument('--artifacts',type=Path,required=True)
    run(**vars(p.parse_args()))
