#!/usr/bin/env python3
"""Verify owned read-only surface origins against actual compositor windows."""
import argparse,json,os,select,socket,subprocess,tempfile
from contextlib import contextmanager
from pathlib import Path
from integration import read_json_lines,until

def run(compositor,probe,artifacts):
    artifacts.mkdir(parents=True,exist_ok=True);records=[];children=[]
    def check(case,condition,**data):
        records.append(dict(case=case,passed=bool(condition),**data))
        (artifacts/'results.json').write_text(json.dumps(records,indent=2)+'\n')
        assert condition,records[-1]
    with tempfile.TemporaryDirectory(prefix='nxs-surface-geometry-') as runtime:
        env=dict(os.environ,XDG_RUNTIME_DIR=runtime,WLR_BACKENDS='headless',WLR_RENDERER='pixman')
        for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET'):env.pop(key,None)
        control,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);control.settimeout(5)
        with (artifacts/'compositor.log').open('w') as errors:
            server=subprocess.Popen([compositor,'-c',str(child.fileno())],pass_fds=[child.fileno()],env=env,stdout=subprocess.PIPE,stderr=errors,text=True)
        child.close()
        def command(text):control.sendall(text.encode());return json.loads(control.recv(65536))
        @contextmanager
        def application(name,*args):
            path=artifacts/(name+'.jsonl')
            with path.open('w') as log,(artifacts/(name+'.stderr')).open('w') as errors:
                client=subprocess.Popen([probe,*args],stdin=subprocess.PIPE,stdout=log,stderr=errors,env=env,text=True)
            children.append(client)
            def send(text):client.stdin.write(text+'\n');client.stdin.flush()
            def events():return read_json_lines(path)
            def window():return next((w for w in command('windows') if w['pid']==client.pid),None)
            def snapshot(index=1):return next((e for e in reversed(events()) if e['event']=='surface-geometry' and e['observer']==index),None)
            try:yield client,send,events,window,snapshot
            finally:
                if client.poll() is None:client.terminate()
                client.wait(timeout=5);client.stdin.close()
        try:
            assert select.select([server.stdout],[],[],10)[0]
            ready=server.stdout.readline().strip();assert ready.startswith('WAYLAND_DISPLAY=');env['WAYLAND_DISPLAY']=ready.split('=',1)[1]
            for label,argument in [('plain','--geometry'),('owned','--geometry-metrics')]:
                with application(label,argument) as (client,send,events,window,snapshot):
                    offset=[0,0]
                    def agrees(index=1):
                        w=window();s=snapshot(index)
                        return w and s and s['mapped']==1 and (s['x'],s['y'],s['width'],s['height'])==(
                            w['x']+(w['frame_left'] if w['server_decorated'] else 0)-offset[0],
                            w['y']+(w['frame_top'] if w['server_decorated'] else 0)-offset[1],w['surface_width'],w['surface_height'])
                    def verified(case):check(label+'-'+case,until(agrees,case),geometry=snapshot(),window=window())
                    until(lambda:window() and window()['server_decorated'],'mapped native frame');verified('initial-origin')
                    check(label+'-independent-observers',until(lambda:agrees(0) and agrees(1),'two observer snapshots'))
                    w=window();check(label+'-metadata-policy',w['client_id']==(1 if label=='owned' else 0) and w['focused'] and w['level']==0)
                    command(f"move {w['id']} 120 90");until(lambda:window()['x']==120 and window()['y']==90,'window moved');verified('moved-origin')
                    send('geometry 5 7 300 220');offset[:]=[5,7];verified('xdg-geometry-offset')
                    send('mode 1');send('commit');until(lambda:not window()['server_decorated'],'client decoration');verified('client-decoration-origin')
                    send('mode 2');send('commit');until(lambda:window()['server_decorated'],'server decoration');verified('restored-frame-origin')
                    if label=='owned':
                        send('metrics 3 31 4 12');until(lambda:window()['frame_top']==31,'custom native extents');verified('custom-extents-origin')
                    send('fullscreen');until(lambda:window()['fullscreen'],'fullscreen');verified('fullscreen-origin')
                    send('unfullscreen');until(lambda:not window()['fullscreen'],'restored fullscreen');verified('restored-fullscreen-origin')
                    send('client-size 341 259');offset[:]=[0,0]
                    until(lambda:(window()['surface_width'],window()['surface_height'])==(341,259),'client chooses normal size')
                    with application(label+'-focus-peer','--geometry') as (peer,peer_send,peer_events,peer_window,peer_snapshot):
                        until(lambda:peer_window() and peer_window()['focused'],'peer takes keyboard focus')
                        check(label+'-client-size-survives-focus-loss',(window()['surface_width'],window()['surface_height'])==(341,259))
                        command(f"focus {window()['id']}")
                        until(lambda:window()['focused'],'original window regains focus')
                        # Wait for the configure to reach the client and its
                        # resulting buffer to reach the server before checking.
                        send('sync');send('sync')
                        until(lambda:len([e for e in events() if e['event']=='sync'])>=2,'focus configure barrier')
                        check(label+'-client-size-survives-focus-return',(window()['surface_width'],window()['surface_height'])==(341,259))
                        hint=next(e for e in reversed(events()) if e['event']=='size-hint')
                        check(label+'-focus-configure-keeps-committed-size',(hint['width'],hint['height'])==(341,259))
                    verified('client-size-origin-after-focus')
                    send('unwatch 0');send('sync');until(lambda:any(e['event']=='sync' for e in events()),'observer deletion barrier')
                    count=sum(e['event']=='surface-geometry' and e['observer']==0 for e in events())
                    command(f"move {window()['id']} 180 130");until(lambda:window()['x']==180,'move with one observer');verified('remaining-observer')
                    check(label+'-deleted-observer-quiet',sum(e['event']=='surface-geometry' and e['observer']==0 for e in events())==count)
                    send('watch 0');check(label+'-recreated-observer',until(lambda:agrees(0),'recreated observer'))
                    send('unmap');check(label+'-unmapped-snapshot',until(lambda:snapshot() and snapshot()['mapped']==0,'unmapped geometry'))
                    check(label+'-unmap-keeps-observer',not any(e['event']=='geometry-closed' for e in events()))
                    send('remap');verified('remapped-origin')
                    send('close-toplevel');check(label+'-closed-observers',until(lambda:len([e for e in events() if e['event']=='geometry-closed'])==2,'closed observers'))
                    send('quit');client.wait(timeout=5);check(label+'-clean-client-exit',client.returncode==0)
            with application('invalid','--geometry') as (client,send,events,window,snapshot):
                until(lambda:window() and snapshot() and snapshot()['mapped'],'invalid test mapped')
                send('invalid-observer');client.wait(timeout=5);check('invalid-role-rejected',client.returncode!=0 and server.poll() is None)
            with application('older-client') as (client,send,events,window,snapshot):
                w=until(window,'version-7 client maps');check('older-client-frame-policy',w['server_decorated'] and w['frame_top']==22)
                send('quit');client.wait(timeout=5);check('older-client-clean-exit',client.returncode==0)
            check('compositor-survives-client-teardown',server.poll() is None)
            print(json.dumps(dict(passed=len(records))))
        finally:
            for client in children:
                if client.poll() is None:client.terminate();client.wait(timeout=5)
            if server.poll() is None:server.terminate()
            server.wait(timeout=5);control.close();server.stdout.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('compositor','probe'):p.add_argument('--'+name,required=True)
    p.add_argument('--artifacts',type=Path,required=True);run(**vars(p.parse_args()))
