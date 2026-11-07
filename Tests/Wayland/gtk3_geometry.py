#!/usr/bin/env python3
"""Qualify the GTK geometry transport independently of any browser or provider."""
import argparse,json,os,select,socket,subprocess,sys,tempfile
from pathlib import Path
from integration import read_json_lines,until

def run(compositor,library,artifacts,library_path=(),older_compositor=None):
    artifacts.mkdir(parents=True,exist_ok=True);results=[]
    def check(case,condition,**data):
        results.append(dict(case=case,passed=bool(condition),**data))
        (artifacts/'results.json').write_text(json.dumps(results,indent=2)+'\n');assert condition,results[-1]
    for label,executable,available in [('current',compositor,True)]+([('older',older_compositor,False)] if older_compositor else []):
        root=artifacts/label;root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='nxs-gtk3-geometry-') as runtime:
            # Geometry tests need neither an accessibility bus nor AppKit.
            env=dict(os.environ,XDG_RUNTIME_DIR=runtime,WLR_BACKENDS='headless',WLR_RENDERER='pixman',GTK_CSD='0',NO_AT_BRIDGE='1')
            if library_path:env['LD_LIBRARY_PATH']=':'.join(library_path)
            for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','LD_PRELOAD'):env.pop(key,None)
            control,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);control.settimeout(5)
            with (root/'compositor.log').open('w') as errors:
                server=subprocess.Popen([executable,'-c',str(child.fileno())],pass_fds=[child.fileno()],env=env,stdout=subprocess.PIPE,stderr=errors,text=True)
            child.close();client=None
            def command(text):control.sendall(text.encode());return json.loads(control.recv(65536))
            try:
                assert select.select([server.stdout],[],[],10)[0]
                ready=server.stdout.readline().strip();assert ready.startswith('WAYLAND_DISPLAY=');env['WAYLAND_DISPLAY']=ready.split('=',1)[1]
                with (root/'client.jsonl').open('w') as log,(root/'client.stderr').open('w') as errors:
                    client=subprocess.Popen([sys.executable,str(Path(__file__).with_name('gtk3_geometry_child.py')),'--library',library],env=env,stdin=subprocess.PIPE,stdout=log,stderr=errors,text=True)
                def events():return read_json_lines(root/'client.jsonl')
                def send(text):client.stdin.write(text+'\n');client.stdin.flush()
                def window():
                    assert client.poll() is None,client.returncode
                    return next((w for w in command('windows') if w['pid']==client.pid and w['visible']),None)
                def snapshot():return next((e for e in reversed(events()) if e['event']=='geometry'),None)
                def matches():
                    w=window();s=snapshot()
                    return w and s and s['received'] and s['mapped'] and (s['x'],s['y'],s['width'],s['height'])==(
                        w['x']+(w['frame_left'] if w['server_decorated'] else 0),w['y']+(w['frame_top'] if w['server_decorated'] else 0),w['surface_width'],w['surface_height'])
                until(window,'ordinary GTK window')
                if available:
                    check(label+'-ordinary-gtk-origin',until(matches,'plain GTK geometry'),snapshot=snapshot(),window=window())
                    check(label+'-no-added-app-policy',window()['client_id']==0 and window()['level']==0)
                    command(f"move {window()['id']} 60 45")
                    check(label+'-moved-gtk-origin',until(lambda:matches() and snapshot()['x']==61,'plain GTK move'),snapshot=snapshot())
                    send('popup');check(label+'-popup-retains-original-path',until(lambda:any(e['event']=='popup' and not e['received'] for e in events()),'unobserved GTK popup'))
                    check(label+'-parent-survives-popup',client.poll() is None and window() is not None)
                    before=len([e for e in events() if e['event']=='geometry'])
                    for _ in range(10):send('status')
                    until(lambda:len([e for e in events() if e['event']=='status'])==10,'unchanged queries')
                    check(label+'-unchanged-queries-stay-quiet',len([e for e in events() if e['event']=='geometry'])==before)
                    send('replace');check(label+'-window-replacement',until(lambda:matches() and snapshot()['generation']==2,'replacement geometry'),snapshot=snapshot())
                else:
                    send('status');check(label+'-explicit-unavailable-fallback',until(lambda:any(e['event']=='status' and not e['received'] for e in events()),'old compositor fallback'))
                    check(label+'-no-fabricated-origin',snapshot() is None and window()['client_id']==0)
                send('close-display');check(label+'-display-close',until(lambda:any(e['event']=='display-closed' for e in events()),'GDK close'))
                send('quit');client.wait(timeout=5);check(label+'-clean-exit',client.returncode==0)
                check(label+'-no-runtime-diagnostics',not (root/'client.stderr').read_text().strip(),stderr=(root/'client.stderr').read_text())
            finally:
                if client:
                    if client.poll() is None:client.terminate();client.wait(timeout=5)
                    client.stdin.close()
                if server.poll() is None:server.terminate()
                server.wait(timeout=5);control.close();server.stdout.close()
                (root/'cleanup.json').write_text(json.dumps(dict(compositor=dict(pid=server.pid,exit=server.returncode),client=dict(pid=client.pid,exit=client.returncode) if client else None),indent=2)+'\n')
    print(json.dumps(dict(passed=len(results))))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('compositor','library'):p.add_argument('--'+name,required=True)
    p.add_argument('--older-compositor');p.add_argument('--library-path',action='append',default=[])
    p.add_argument('--artifacts',type=Path,required=True);run(**vars(p.parse_args()))
