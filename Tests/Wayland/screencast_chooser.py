#!/usr/bin/env python3
"""Exercise the native consent dialog with real Wayland keyboard input."""
import argparse
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import tempfile
import uuid
from gnustep import private_defaults, process_runtime
from integration import until
from text_input import stop_process


def run(compositor, chooser, pasteboard_server, artifacts):
    artifacts.mkdir(parents=True)
    records=[]
    with tempfile.TemporaryDirectory(prefix='nextspace-share-dialog-') as runtime:
        env=dict(os.environ,XDG_RUNTIME_DIR=runtime,WLR_BACKENDS='headless',WLR_HEADLESS_OUTPUTS='1',
            WLR_RENDERER='pixman',NEXTSPACE_SESSION_ID=str(uuid.uuid4()),NEXTSPACE_GS_BACKEND='wayland',
            NEXTSPACE_WAYLAND_CAPTURE_DIR=str(artifacts.resolve()))
        for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET'):env.pop(key,None)
        private_defaults(env,runtime)
        control,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);control.settimeout(5)
        with (artifacts/'compositor.log').open('w') as log:
            server=subprocess.Popen([compositor,'-c',str(child.fileno())],env=env,pass_fds=[child.fileno()],
                stdout=subprocess.PIPE,stderr=log,text=True)
        child.close();storage=app=None
        def command(text):
            control.sendall(text.encode());return json.loads(control.recv(65536))
        try:
            assert select.select([server.stdout],[],[],10)[0]
            env['WAYLAND_DISPLAY']=server.stdout.readline().strip().split('=',1)[1]
            with (artifacts/'pasteboard.log').open('w') as log:
                storage=subprocess.Popen([pasteboard_server,'--no-fork'],env=env,stdout=log,stderr=log)
            head=command('outputs')[0]
            for scale in (120,150,180,210,240):
                assert command(f"test-scale {head['name']} {scale} 10000")['ok'];assert command('confirm')['ok']
                for action,key,expected in (('share',28,'HEADLESS-1\n'),('cancel',1,'')):
                    with (artifacts/f'{action}-{scale}.log').open('w') as log:
                        app=subprocess.Popen([chooser,'-GSBackend','libgnustep-wayland','-GSTheme','NextSpace'],
                            env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True)
                    app.stdin.write('HEADLESS-1\nHEADLESS-2\n');app.stdin.close();app.stdin=None
                    def ready():
                        assert app.poll() is None,(artifacts/f'{action}-{scale}.log').read_text()[-2000:]
                        return next((w for w in command('windows') if w['pid']==app.pid and w['visible'] and
                            w['title']=='Screen Sharing' and w['preferred_scale']==scale),None)
                    window=until(ready,'native screen sharing consent dialog',timeout=15)
                    if not records: runtime_record=process_runtime(app.pid)
                    assert command(f"focus {window['id']}")['ok']
                    for pressed in (1,0):assert command(f'key {key} {pressed}')['ok']
                    output,_=app.communicate(timeout=10)
                    assert app.returncode==0 and output==expected,(app.returncode,output)
                    records.append(dict(scale=scale,action=action,output=output,window=window))
            (artifacts/'results.json').write_text(json.dumps(dict(cases=records,runtime=runtime_record),indent=2)+'\n')
            print(f'Native screen-sharing dialog: {len(records)} Share/Cancel cases PASS')
        finally:
            for process in (app,storage,server):
                if process:stop_process(process)
            server.stdout.close();control.close()


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('compositor','chooser','pasteboard-server'):p.add_argument('--'+name,required=True)
    p.add_argument('--artifacts',type=Path,required=True)
    run(**vars(p.parse_args()))
