#!/usr/bin/env python3
"""Real desktop-portal requests and PipeWire frames in an owned headless session."""
import argparse
import array
import hashlib
import json
import os
from pathlib import Path
import select
import shlex
import signal
import socket
import subprocess
import tempfile
import time
import uuid

import dbus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
from gnustep import private_defaults, process_runtime
from integration import until
from shell import Shell
from outputs import WorkspaceOutputs
from text_input import stop_process


def run(compositor, shell_probe, receiver, chooser, client, artifacts, backend='/usr/libexec/xdg-desktop-portal-wlr',
        native_chooser=False, pasteboard_server='/Library/bin/gpbs-wayland', supervisor=None, workspace_probe=None,
        lock_probe=None, portal_configuration=None, capture_launcher=None, client_args=()):
    artifacts.mkdir(parents=True)
    DBusGMainLoop(set_as_default=True)
    processes, logs, records = [], [], []
    backend_path=backend
    assert not supervisor or (workspace_probe and lock_probe), "Supervised portal checks need shell and lock probes"
    with tempfile.TemporaryDirectory(prefix='nextspace-portal-') as runtime:
        env=dict(os.environ,XDG_RUNTIME_DIR=runtime,XDG_CONFIG_HOME=runtime+'/config',
            XDG_CACHE_HOME=runtime+'/cache',XDG_CURRENT_DESKTOP='NEXTSPACE',XDG_SESSION_TYPE='wayland',
            XDG_SESSION_CLASS='user',WLR_BACKENDS='headless',WLR_HEADLESS_OUTPUTS='2',WLR_RENDERER='pixman',
            NEXTSPACE_SESSION_ID=str(uuid.uuid4()),NEXTSPACE_GS_BACKEND='wayland',
            NEXTSPACE_WAYLAND_CAPTURE_DIR=str(artifacts.resolve()))
        for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET'):env.pop(key,None)
        if native_chooser:private_defaults(env,runtime)
        def start(arguments,label,extra=None,**options):
            log=(artifacts/(label+'.log')).open('w');logs.append(log)
            item=subprocess.Popen(arguments,env=dict(env,**(extra or {})),stderr=log,
                stdout=options.pop('stdout',log),**options);processes.append(item);return item
        control,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
        broker,peer=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
        control.settimeout(5);shell=None;bus=None
        def command(text):
            control.sendall(text.encode());return json.loads(control.recv(65536))
        config=Path(env['XDG_CONFIG_HOME']);(config/'xdg-desktop-portal').mkdir(parents=True)
        if portal_configuration:
            (config/'xdg-desktop-portal/nextspace-portals.conf').write_bytes(Path(portal_configuration).read_bytes())
        else:
            (config/'xdg-desktop-portal/portals.conf').write_text('[preferred]\ndefault=none\norg.freedesktop.impl.portal.ScreenCast=wlr\norg.freedesktop.impl.portal.Screenshot=none\n')
        choice=Path(runtime,'choice');choice.write_text('HEADLESS-1')
        chooser_input=artifacts.resolve()/'chooser-input.txt'
        wrapper=Path(runtime,'choose');wrapper.write_text('#!/bin/sh\ncat > '+shlex.quote(str(chooser_input))+
            '\nselection=$(cat '+shlex.quote(str(choice))+')\n'+
            'case "$selection" in native-*) exec '+shlex.quote(chooser)+' < '+shlex.quote(str(chooser_input))+';; esac\n'+
            '[ "$selection" = cancel ] && exit 0\nprintf "%s\\n" "$selection"\n');wrapper.chmod(0o700)
        backend_config=Path(runtime,'wlr.ini');backend_config.write_text('[screencast]\nchooser_type=dmenu\nchooser_cmd='+str(wrapper)+'\nmax_fps=30\n')
        try:
            listener=None;lock_fifo=None
            if supervisor:
                pipewire=start(['pipewire'],'pipewire')
                until(lambda:Path(runtime,'pipewire-0').exists(),'owned PipeWire socket')
                listener=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
                address=Path(runtime,'control');listener.bind(str(address));listener.listen(1);listener.settimeout(15)
                wrapper=Path(runtime,'compositor')
                wrapper.write_text('#!/usr/bin/python3\nimport os,socket,sys\ns=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)\n'+
                    's.connect('+repr(str(address))+')\nos.set_inheritable(s.fileno(),True)\n'+
                    'os.execv('+repr(compositor)+',['+repr(compositor)+',"-c",str(s.fileno()),*sys.argv[1:]])\n')
                capture_wrapper=Path(runtime,'capture-backend')
                capture_wrapper.write_text('#!/bin/sh\nexec '+(shlex.quote(capture_launcher) if capture_launcher else
                    shlex.quote(backend_path)+' --replace -l DEBUG -c '+shlex.quote(str(backend_config)))+'\n')
                fifo=Path(runtime,'locker-commands');os.mkfifo(fifo,0o600);lock_fifo=os.open(fifo,os.O_RDWR|os.O_NONBLOCK)
                locker_wrapper=Path(runtime,'locker')
                locker_wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(lock_probe)+' < '+shlex.quote(str(fifo))+' >> '+shlex.quote(str(artifacts.resolve()/'locker.jsonl'))+'\n')
                for path in (wrapper,capture_wrapper,locker_wrapper):path.chmod(0o700)
                server=start([supervisor,'--compositor',str(wrapper),'--capture-backend',str(capture_wrapper),
                    '--locker',str(locker_wrapper),'--private-bus','--',workspace_probe],
                    'supervisor',stdout=subprocess.PIPE,stdin=subprocess.PIPE)
                control.close();child.close();peer.close()
                control,_=listener.accept();control.settimeout(5)
                shell=WorkspaceOutputs.from_process(server,artifacts)
                env.update(shell.environment)
            else:
                daemon=start(['dbus-daemon','--session','--nofork','--print-address=1'],'dbus',stdout=subprocess.PIPE,text=True)
                assert select.select([daemon.stdout],[],[],10)[0]
                env['DBUS_SESSION_BUS_ADDRESS']=daemon.stdout.readline().strip()
                server=start([compositor,'-c',str(child.fileno()),'-S',str(peer.fileno())],'compositor',
                    pass_fds=[child.fileno(),peer.fileno()],stdout=subprocess.PIPE,text=True)
                child.close();peer.close();assert select.select([server.stdout],[],[],10)[0]
                env['WAYLAND_DISPLAY']=server.stdout.readline().strip().split('=',1)[1]
                shell=Shell(shell_probe,broker,env,artifacts,0,version=18)
            shell.wait(lambda:shell.output_batches,'portal shell')
            if native_chooser:start([pasteboard_server,'--no-fork'],'pasteboard')
            content=start([client,*client_args],'content',dict(GDK_BACKEND='wayland'),stdin=subprocess.PIPE)
            until(lambda:any(w['pid']==content.pid and w['visible'] for w in command('windows')),'portal test content')
            if not supervisor:
                pipewire=start(['pipewire'],'pipewire')
                until(lambda:Path(runtime,'pipewire-0').exists(),'owned PipeWire socket')
            wireplumber=start(['wireplumber'],'wireplumber')
            if not supervisor:
                local,remote=socket.socketpair()
                broker.sendmsg([b'V'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[local.fileno()]))]);local.close()
                backend=start([backend_path,'-l','DEBUG','-c',str(backend_config)],'backend',
                    dict(WAYLAND_SOCKET=str(remote.fileno())),pass_fds=[remote.fileno()]);remote.close()
            def backend_pid():
                if not supervisor:return backend.pid if backend.poll() is None else None
                for pid in Path(f'/proc/{server.pid}/task/{server.pid}/children').read_text().split():
                    try:
                        if Path(f'/proc/{pid}/exe').resolve()==Path(backend_path).resolve():return int(pid)
                    except FileNotFoundError:pass
                return None
            bus=dbus.bus.BusConnection(env['DBUS_SESSION_BUS_ADDRESS'])
            until(lambda:bus.name_has_owner('org.freedesktop.impl.portal.desktop.wlr'),'authorized portal backend')
            if supervisor:bus.start_service_by_name('org.freedesktop.portal.Desktop',0)
            else:start(['/usr/libexec/xdg-desktop-portal','--verbose'],'portal')
            until(lambda:bus.name_has_owner('org.freedesktop.portal.Desktop'),'desktop portal')
            def bus_pid(name):
                return int(bus.call_blocking('org.freedesktop.DBus','/org/freedesktop/DBus',
                    'org.freedesktop.DBus','GetConnectionUnixProcessID','s',[name]))
            runtimes=dict(backend=process_runtime(backend_pid()),frontend=process_runtime(bus_pid('org.freedesktop.portal.Desktop')),
                pipewire=process_runtime(pipewire.pid),compositor_or_supervisor=process_runtime(server.pid))
            portal=bus.get_object('org.freedesktop.portal.Desktop','/org/freedesktop/portal/desktop')
            interface=dbus.Interface(portal,'org.freedesktop.portal.ScreenCast')
            implementation=dbus.Interface(bus.get_object('org.freedesktop.impl.portal.desktop.wlr',
                '/org/freedesktop/portal/desktop'),'org.freedesktop.impl.portal.ScreenCast')
            responses={}
            closed=[]
            bus.add_signal_receiver(lambda code,result,path:responses.__setitem__(path,(int(code),result)),
                signal_name='Response',dbus_interface='org.freedesktop.portal.Request',path_keyword='path')
            bus.add_signal_receiver(lambda details,path:closed.append(str(path)),signal_name='Closed',
                dbus_interface='org.freedesktop.portal.Session',path_keyword='path')
            context=GLib.MainContext.default()
            consent=[]
            def request(method,*arguments,_consent=None,**options):
                options['handle_token']='n'+uuid.uuid4().hex
                path=str(method(*arguments,dbus.Dictionary(options,signature='sv')))
                acted=False
                def received():
                    nonlocal acted
                    while context.pending():context.iteration(False)
                    assert backend_pid(),(artifacts/('supervisor.log' if supervisor else 'backend.log')).read_text()[-2500:]
                    if _consent and not acted:
                        window=next((w for w in command('windows') if w['title']=='Screen Sharing' and w['visible']),None)
                        if window:
                            assert command(f"focus {window['id']}")['ok']
                            if _consent=='HEADLESS-2':
                                before={w['id'] for w in command('windows') if w['pid']==window['pid'] and w['visible']}
                                before_popups=len(command('popups'))
                                x=window['x']+window['frame_left']+150
                                y=window['y']+window['frame_top']+84
                                (artifacts/('chooser-'+path.rsplit('/',1)[-1]+'.json')).write_text(json.dumps(dict(
                                    window=window,windows=command('windows'),popups=command('popups'),
                                    hit=command(f'hit {x} {y}'),x=x,y=y),indent=2)+'\n')
                                assert command(f'hit {x} {y}')['id']==window['id']
                                assert command(f'pointer {x} {y}')['ok']
                                assert command('button 272 1')['ok']
                                def visible():
                                    return {w['id'] for w in command('windows') if w['pid']==window['pid'] and w['visible']}
                                def menu_surface():
                                    popups=command('popups')
                                    if len(popups)>before_popups:return popups[0]
                                    return next((w for w in command('windows') if w['id'] in visible()-before),None)
                                menu=until(menu_surface,'native display list opened')
                                assert command(f"pointer {menu['x']+menu['width']//2} {menu['y']+menu['height']*3//4}")['ok']
                                assert command('button 272 0')['ok']
                                until(lambda:not (visible()-before) and len(command('popups'))==before_popups,'native display selection confirmed')
                            key=1 if _consent=='cancel' else 28
                            for pressed in (1,0):assert command(f'key {key} {pressed}')['ok']
                            consent.append(dict(action=_consent,window=window,runtime=process_runtime(window['pid'])));acted=True
                    return responses.get(path)
                return until(received,'portal response '+path,timeout=20)
            def create(selection_result=0,consent_action=None):
                code,result=request(interface.CreateSession,session_handle_token='s'+uuid.uuid4().hex)
                assert code==0,(code,result);session=result['session_handle']
                code,result=request(interface.SelectSources,session,types=dbus.UInt32(1),
                    cursor_mode=dbus.UInt32(1),multiple=dbus.Boolean(False),persist_mode=dbus.UInt32(0),_consent=consent_action)
                assert code==selection_result,(code,result);return session
            def close(session):
                bus.get_object('org.freedesktop.portal.Desktop',session).Close(dbus_interface='org.freedesktop.portal.Session')
            for scale in (120,150,180,210,240):
                shell.send('outputs');before=shell.output_batches
                shell.wait(lambda:shell.output_batches>before,'portal layout inventory')
                layout=[]
                for index,head in enumerate(sorted(shell.outputs.values(),key=lambda h:h['id'])):
                    layout.append(dict(id=head['id'],enabled=1,primary=int(index==0),width=801,height=601,
                        refresh=60000,scale=scale if index==0 else 180,transform=1 if scale==210 else 0,
                        x=-301 if index==0 else 501,y=-101 if index==0 else 0))
                shell.configure_outputs(layout)
                target=min(command('outputs'),key=lambda head:head['x'])
                window=next(w for w in command('windows') if w['pid']==content.pid)
                assert command(f"move {window['id']} {target['x']+20} {target['y']+20}")['ok']
                for head in command('outputs'):
                    head=dict(head,transform=next(item['transform'] for item in layout
                        if shell.outputs[item['id']]['name']==head['name']))
                    use_native=native_chooser
                    choice.write_text('native-share' if use_native else head['name'])
                    session=create(consent_action=head['name'] if use_native else None)
                    code,result=request(interface.Start,session,'')
                    assert code==0,(code,result)
                    streams=result['streams'];assert len(streams)==1,streams
                    node,properties=streams[0]
                    # The backend must serialize the matched session rather than
                    # its list iterator after it has reached the list sentinel.
                    impl_code,impl_result=implementation.Start(dbus.ObjectPath('/org/freedesktop/portal/desktop/request/probe/r'+uuid.uuid4().hex),
                        session,'','',dbus.Dictionary({},signature='sv'))
                    assert impl_code==0 and int(impl_result['persist_mode'])==0 and 'restore_data' not in impl_result,impl_result
                    assert list(properties['position'])==[head['x'],head['y']],(head,properties)
                    assert list(properties['size'])==[head['width'],head['height']],(head,properties)
                    fd=interface.OpenPipeWireRemote(session,dbus.Dictionary({},signature='sv')).take()
                    path=artifacts/f"frame-{scale}-{head['name']}.raw"
                    with (artifacts/f"receiver-{scale}-{head['name']}.log").open('w') as log:
                        received=subprocess.Popen([receiver,str(fd),str(node),str(path.resolve()),'--continuous'],env=env,
                            pass_fds=[fd],stdout=subprocess.PIPE,stderr=log,text=True)
                    processes.append(received);os.close(fd)
                    observations=[];deadline=time.monotonic()+15
                    while True:
                        assert received.poll() is None,(artifacts/f"receiver-{scale}-{head['name']}.log").read_text()
                        assert time.monotonic()<deadline,observations
                        if not select.select([received.stdout],[],[],1)[0]:continue
                        frame=json.loads(received.stdout.readline())
                        assert (frame['width'],frame['height'])==(801,601),frame
                        if frame['sequence']==1:assert frame['damage']==[0,0,801,601],frame
                        assert frame['transform']==head['transform'],(frame,head)
                        current=Path(str(path)+f".{frame['sequence']}.raw")
                        raw=current.read_bytes()
                        assert frame['format'] in (7,8,11,12),frame
                        def pixel(x,y):
                            offset=y*frame['stride']+x*4
                            r,g,b=raw[offset:offset+3]
                            if frame['format'] in (8,12):r,b=b,r
                            return 0xff000000|(r<<16)|(g<<8)|b
                        w,h=frame['width'],frame['height']
                        pixels=[pixel((2*x+1)*w//4,(2*y+1)*h//4) for y in range(2) for x in range(2)]
                        pixels.append(pixel(w//2,h//2))
                        reference=command('output-samples '+head['name'])
                        matched=pixels==reference['samples']+[reference['center']]
                        observations.append(dict(frame=frame,pixels=pixels,reference=reference,matched=matched,file=current.name))
                        if matched:
                            path=current;break
                    stop_process(received)
                    assert received.returncode==0,received.returncode
                    received.stdout.close()
                    records.append(dict(scale=scale,output=head,properties=dict(properties),frame=frame,
                        file=path.name,pixels=pixels,observations=observations,sha256=hashlib.sha256(raw).hexdigest()))
                    close(session)
            choice.write_text('native-cancel' if native_chooser else 'cancel')
            session=create(1,consent_action='cancel' if native_chooser else None)
            try: close(session)
            except dbus.DBusException as error:
                assert error.get_dbus_name() in ('org.freedesktop.DBus.Error.UnknownMethod',
                    'org.freedesktop.DBus.Error.UnknownObject'), error
            assert any(len(set(row['pixels']))>1 for row in records),'No nonuniform portal content verified'
            lifecycle=[]
            if supervisor:
                def pump():
                    while context.pending():context.iteration(False)
                    shell.pump()
                    assert server.poll() is None,(artifacts/'supervisor.log').read_text()[-3000:]
                def gone(session):
                    pump();return str(session) in closed
                def ready_backend(previous):
                    pump();pid=backend_pid()
                    return pid if pid and pid!=previous and bus.name_has_owner('org.freedesktop.impl.portal.desktop.wlr') else None
                def capture_session():
                    choice.write_text('native-share' if native_chooser else 'HEADLESS-1')
                    session=create(consent_action='share' if native_chooser else None)
                    code,result=request(interface.Start,session,'');assert code==0,(code,result)
                    return session,int(result['streams'][0][0])
                def no_capture_nodes():
                    graph=json.loads(subprocess.check_output(['pw-dump'],env=env,text=True,timeout=5))
                    return not any(item.get('info',{}).get('props',{}).get('node.name','').startswith('xdpw-stream-') for item in graph)
                def recovery_frame(session,node,label):
                    fd=interface.OpenPipeWireRemote(session,dbus.Dictionary({},signature='sv')).take()
                    path=artifacts/(label+'.raw')
                    frame=subprocess.run([receiver,str(fd),str(node),str(path.resolve())],env=env,pass_fds=[fd],
                        capture_output=True,text=True,timeout=15);os.close(fd)
                    assert frame.returncode==0,frame.stderr
                    result=json.loads(frame.stdout);assert (result['width'],result['height'])==(801,601)
                    assert result['damage']==[0,0,801,601],result
                    return dict(frame=result,file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                current,node=capture_session();previous=backend_pid()
                os.write(lock_fifo,b'lock\npaint\n');os.kill(server.pid,signal.SIGUSR1)
                until(lambda:command('lock-state')['acknowledged'],'portal session locked')
                until(lambda:backend_pid() is None,'locked capture backend revoked and reaped')
                until(lambda:gone(current),'portal session closed on lock')
                until(no_capture_nodes,'locked PipeWire producer removed')
                assert not bus.name_has_owner('org.freedesktop.impl.portal.desktop.wlr')
                os.write(lock_fifo,b'unlock\n')
                until(lambda:not command('lock-state')['locked'],'portal session unlocked')
                os.write(lock_fifo,b'quit\n')
                recovered=until(lambda:ready_backend(previous),'capture backend after unlock',timeout=15)
                current,node=capture_session()
                lifecycle.append(dict(case='lock/unlock',previous=previous,recovered=recovered,
                    **recovery_frame(current,node,'after-unlock')))
                previous=recovered;os.kill(previous,signal.SIGKILL)
                until(no_capture_nodes,'backend crash removes PipeWire producer')
                # SIGKILL cannot emit the backend's Closed signal. The client
                # observes transport loss and closes its remaining frontend handle.
                close(current)
                recovered=until(lambda:ready_backend(previous),'capture backend after crash',timeout=15)
                current,node=capture_session()
                lifecycle.append(dict(case='backend crash',previous=previous,recovered=recovered,
                    **recovery_frame(current,node,'after-backend-crash')))
                previous=recovered;stop_process(pipewire);stop_process(wireplumber)
                until(lambda:gone(current),'portal session closed on PipeWire loss')
                until(lambda:'retrying in five seconds' in (artifacts/'supervisor.log').read_text(),
                    'bounded capture retry during user service loss',timeout=15)
                pipewire=start(['pipewire'],'pipewire-restarted')
                until(lambda:Path(runtime,'pipewire-0').exists(),'restarted PipeWire socket')
                wireplumber=start(['wireplumber'],'wireplumber-restarted')
                recovered=until(lambda:ready_backend(previous),'capture backend after PipeWire restart',timeout=20)
                current,node=capture_session()
                lifecycle.append(dict(case='PipeWire restart',previous=previous,recovered=recovered,
                    **recovery_frame(current,node,'after-pipewire-restart')))
                close(current);until(no_capture_nodes,'explicit portal stop removes producer')
                current,node=capture_session()
                assert command('remove-output HEADLESS-1')['ok']
                until(no_capture_nodes,'unplugged capture target removes producer')
                close(current)
                lifecycle.append(dict(case='target unplug',producer_removed=True,remaining_output_usable=bool(command('outputs'))))
                capture_pid=backend_pid()
                frontend_pid=bus_pid('org.freedesktop.portal.Desktop')
                shell.send('quit');server.wait(timeout=10)
                assert server.returncode==0
                assert not Path(f'/proc/{capture_pid}').exists() and not Path(f'/proc/{frontend_pid}').exists()
                assert pipewire.poll() is None and wireplumber.poll() is None,'Unrelated user services were stopped'
                lifecycle.append(dict(case='session cleanup',capture_reaped=True,activated_portal_reaped=True,
                    external_pipewire_preserved=True,external_wireplumber_preserved=True))
            log_path=artifacts/('supervisor.log' if supervisor else 'portal.log')
            assert 'GLib-CRITICAL' not in log_path.read_text(),log_path
            (artifacts/'results.json').write_text(json.dumps(dict(frames=records,cancellation=True,
                native_chooser_tested=native_chooser,consent=consent,lifecycle=lifecycle,runtimes=runtimes,
                screenshot_supported=False,hardware_tested=False),indent=2)+'\n')
            print(f'Desktop portal/PipeWire: {len(records)} frames and cancellation PASS')
        finally:
            (artifacts/'partial-results.json').write_text(json.dumps(dict(frames=records),indent=2)+'\n')
            if bus:bus.close()
            if 'lock_fifo' in locals() and lock_fifo is not None:os.close(lock_fifo)
            if 'listener' in locals() and listener:listener.close()
            if shell:shell.stop()
            for process in reversed(processes):
                stop_process(process)
                if process.stdin:process.stdin.close()
                if process.stdout and process.stdout not in logs:process.stdout.close()
            for log in logs:log.close()
            control.close();broker.close();child.close();peer.close()


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('compositor','shell-probe','receiver','chooser','client'):p.add_argument('--'+name,required=True)
    p.add_argument('--artifacts',type=Path,required=True)
    p.add_argument('--backend',default='/usr/libexec/xdg-desktop-portal-wlr')
    p.add_argument('--native-chooser',action='store_true')
    for name in ('supervisor','workspace-probe','lock-probe'):p.add_argument('--'+name)
    p.add_argument('--pasteboard-server',default='/Library/bin/gpbs-wayland')
    p.add_argument('--portal-configuration')
    p.add_argument('--capture-launcher')
    p.add_argument('--client-argument',dest='client_args',action='append',default=[])
    run(**vars(p.parse_args()))
