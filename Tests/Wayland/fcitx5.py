#!/usr/bin/env python3
"""Real Fcitx5 engines through the authorized Wayland relay and native AppKit."""
from pathlib import Path
import argparse,array,hashlib,json,os,select,shlex,socket,subprocess,tempfile
from integration import read_json_lines,until
from gnustep import private_defaults
from text_input import stop_process
from alerts import assert_on_output

ENGINES = {
    'pinyin': dict(label='Pinyin',keys=(49,23,35,30,24),text='你好',candidates=True,partial='',preedit=None),
    'hangul': dict(label='Hangul',keys=(34,37,31,19,50,33),text='한글 ',candidates=False,partial='한',preedit='글'),
}

def run(compositor,probe,artifacts,nested=False,terminal=None,workspace_probe=None,
        engine_name='pinyin',replace_selection=False,wire_trace=True,pasteboard_server=None,pasteboard_probe=None):
    method=ENGINES[engine_name]
    artifacts.mkdir(parents=True)
    home=artifacts/'home';home.mkdir();config=home/'.config/fcitx5';config.mkdir(parents=True)
    (config/'profile').write_text('''[Groups/0]
Name=Default
Default Layout=us
DefaultIM=pinyin

[Groups/0/Items/0]
Name=keyboard-us
Layout=

[Groups/0/Items/1]
Name=pinyin
Layout=

[GroupOrder]
0=Default
'''.replace('pinyin',engine_name))
    with tempfile.TemporaryDirectory(prefix='nextspace-real-ime-') as runtime:
        env=dict(os.environ,HOME=str(home),XDG_CONFIG_HOME=str(home/'.config'),XDG_DATA_HOME=str(home/'.local/share'),
            XDG_CACHE_HOME=str(home/'.cache'),XDG_RUNTIME_DIR=runtime,WLR_BACKENDS='headless',WLR_HEADLESS_OUTPUTS='2',
            WLR_RENDERER='pixman',NEXTSPACE_SESSION_ID=Path(runtime).name,LANG='C.UTF-8',XDG_CURRENT_DESKTOP='NextSpace')
        for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','WAYLAND_DEBUG','GTK_IM_MODULE','QT_IM_MODULE','XMODIFIERS'):env.pop(key,None)
        private_defaults(env,runtime)
        control,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);control.settimeout(5)
        broker,broker_child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
        bus=server=engine=client=storage=None
        def command(value):
            control.sendall(value.encode());return json.loads(control.recv(65536))
        def key(code):
            for value in (1,0):assert command(f'key {code} {value}')['ok']
        def remote(*arguments):
            return subprocess.run(['fcitx5-remote',*arguments],env=env,capture_output=True,text=True,timeout=3)
        def activate(label):
            for flags in (('-s',engine_name),('-o',)):
                def ready():
                    assert engine.poll() is None,(artifacts/'engine.log').read_text()[-3000:]
                    result=remote(*flags)
                    with (artifacts/(f'remote-{label}-'+flags[0].strip('-')+'.log')).open('a') as log:
                        log.write(json.dumps(dict(returncode=result.returncode,stdout=result.stdout,stderr=result.stderr))+'\n')
                    return result.returncode==0
                # Loading the dictionary can exceed fcitx5-remote's own call
                # deadline. Selecting an engine is idempotent; typing is not.
                until(ready,'real '+method['label']+' engine activated',timeout=20)
        def events():return read_json_lines(log_path,'{')
        def runtime_record(executable,path):
            libraries=sorted({line.split()[-1] for line in Path(f'/proc/{client.pid}/maps').read_text().splitlines()
                if any(token in line for token in ('libgnustep-','libobjc.so.'))})
            path.write_text(json.dumps(dict(executable=str(executable),libraries=libraries),indent=2)+'\n')
        def state(predicate):
            def check():
                assert client.poll() is None,errors_path.read_text()[-3000:]
                rows=[row for row in events() if row.get('event')=='input-state']
                return rows[-1] if rows and predicate(rows[-1]) else None
            return until(check,'real engine native text/marked state')
        try:
            with (artifacts/'bus.log').open('w') as errors:
                bus=subprocess.Popen(['dbus-daemon','--session','--nofork','--print-address=1'],env=env,stdout=subprocess.PIPE,stderr=errors,text=True)
            assert select.select([bus.stdout],[],[],5)[0]
            env['DBUS_SESSION_BUS_ADDRESS']=bus.stdout.readline().strip()
            with (artifacts/'compositor.log').open('w') as errors:
                server=subprocess.Popen([str(compositor),'-c',str(child.fileno()),'-S',str(broker_child.fileno())],
                    env=env,pass_fds=[child.fileno(),broker_child.fileno()],stdout=subprocess.PIPE,stderr=errors,text=True)
            child.close();broker_child.close()
            assert select.select([server.stdout],[],[],10)[0]
            env['WAYLAND_DISPLAY']=server.stdout.readline().strip().split('=',1)[1]
            if pasteboard_server:
                with (artifacts/'pasteboard.log').open('w') as log:
                    storage=subprocess.Popen([str(pasteboard_server),'--no-fork'],env=env,stdout=log,stderr=log)
                until(lambda: subprocess.run([str(pasteboard_probe),'--ping'],env=env,
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0,'owned pasteboard storage')
            first,connection=socket.socketpair();broker.sendmsg([b'I'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[first.fileno()]))]);first.close()
            with (artifacts/'engine.log').open('w') as log:
                engine=subprocess.Popen(['fcitx5','-D','--disable','all','--enable',
                    'wayland,waylandim,dbus,keyboard,'+engine_name+',punctuation,classicui','--verbose=waylandim=5'],
                    env=dict(env,WAYLAND_SOCKET=str(connection.fileno()),WAYLAND_DEBUG='1' if wire_trace else ''),
                    pass_fds=[connection.fileno()],stdout=log,stderr=log)
            connection.close()
            def engine_ready():
                assert engine.poll() is None,(artifacts/'engine.log').read_text()[-3000:]
                owner=subprocess.run(['busctl','--address='+env['DBUS_SESSION_BUS_ADDRESS'],'call',
                    'org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','NameHasOwner',
                    's','org.fcitx.Fcitx5'],capture_output=True,text=True,timeout=3)
                marker='get_input_method(' if wire_trace else 'INIT IM V2'
                return owner.returncode==0 and owner.stdout.strip()=='b true' and marker in (artifacts/'engine.log').read_text()
            until(engine_ready,'real input method ready',timeout=20)
            records=[];burst_records=[]
            outputs=command('outputs')
            for mode in range(4):
                engine_start=(artifacts/'engine.log').stat().st_size
                log_path=artifacts/f'probe-{mode}.log'
                errors_path=artifacts/f'probe-{mode}.stderr'
                with log_path.open('w') as log,errors_path.open('w') as errors:
                    client=subprocess.Popen([str(probe),'-GSBackend','libgnustep-wayland','-GSTheme','NextSpace',
                        '-NSUseRunningCopy','NO','-TextInputProbe','YES','-TextInputRunLoopMode',str(mode),
                        '-NestedIMEProbe','YES' if nested and mode==3 else 'NO'],
                        env=env,stdout=log,stderr=errors)
                field=until(lambda:next((row for row in events() if row.get('event')=='text-field'),None),'native field geometry')
                def window():
                    assert client.poll() is None,errors_path.read_text()[-3000:]
                    return next((w for w in command('windows') if w['pid']==client.pid and w['title']=='WaylandProbe' and w['width']>200),None)
                w=until(window,'native document')
                runtime_record(probe,artifacts/f'runtime-{mode}.json')
                output=next(head for head in command('outputs') if head['name']==outputs[0]['name'])
                assert command(f"move {w['id']} {output['x']+10} {output['y']+10}")['ok']
                assert command(f"focus {w['id']}")['ok'];w=window()
                assert command(f"pointer {w['x']+field['start_x']+40} {w['y']+w['height']-field['start_y']}")['ok']
                assert command('button 272')['ok']
                for x,pressed in ((field['start_x'],1),(field['end_x'],0)):
                    assert command(f"pointer {w['x']+x} {w['y']+w['height']-field['start_y']}")['ok']
                    assert command(f'button 272 {pressed}')['ok']
                state(lambda row:row['selection']>20)
                if not replace_selection:key(14);state(lambda row:row['text']=='')
                activate(mode)
                if wire_trace:
                    context=b'Selection, keyboard input and text metrics' if replace_selection else b''
                    until(lambda: b'surrounding_text("'+context+b'",' in
                        (artifacts/'engine.log').read_bytes()[engine_start:], 'engine receives the field context')
                expected=''
                for index,scale in enumerate((120,150,180,210,240)):
                    output=outputs[index%len(outputs)]
                    assert command(f"test-scale {output['name']} {scale} 10000")['ok'];assert command('confirm')['ok']
                    output=next(head for head in command('outputs') if head['name']==output['name'])
                    assert command(f"move {w['id']} {output['x']+10} {output['y']+10}")['ok']
                    until(lambda: window()['preferred_scale']==scale and window()['buffer_width']==
                        (window()['width']*scale+60)//120,'native field density')
                    assert command(f"focus {w['id']}")['ok']
                    for code in method['keys']:key(code)
                    marked=state(lambda row:row['marked'] and row['text'].startswith(expected))
                    popups=until(lambda: [popup for popup in command('input-popups') if popup['width']>0 and popup['height']>0],
                        'real engine candidate popup') if method['candidates'] else []
                    for popup in popups:assert_on_output(popup,[output])
                    key(57);expected+=method['text']
                    committed=state(lambda row:row['text']==expected and not row['marked'])
                    assert committed['cursor']==len(expected),committed
                    records.append(dict(mode=mode,scale=scale,marked=marked,committed=committed,popups=popups,window=window()))
                    (artifacts/'results.json').write_text(json.dumps(dict(cases=records,complete=False),indent=2)+'\n')
                if engine_name=='hangul':
                    # Keep forwarded Spaces interleaved with later IME commits.
                    for _ in range(2):
                        for code in method['keys']:key(code)
                        key(57)
                    expected+=method['text']*2
                    committed=state(lambda row:row['text']==expected and not row['marked'])
                    burst_records.append(dict(mode=mode,committed=committed))
                stop_process(client);client=None
            nested_events=[row for row in events() if row.get('event')=='nested-ime'] if nested else []
            if nested:assert any(row['queued']>0 for row in nested_events),nested_events
            terminal_records=[]
            if terminal:
                directory=artifacts/'terminal';directory.mkdir()
                typed=directory/'typed';ready=directory/'ready';script=directory/'read-input.sh'
                script.write_text('#!/bin/sh\nstty -echo -icanon min 1 time 0\ntouch '+shlex.quote(str(ready))+
                    '\nexec cat > '+shlex.quote(str(typed))+'\n');script.chmod(0o700)
                engine_start=(artifacts/'engine.log').stat().st_size
                with (directory/'terminal.log').open('w') as log:
                    client=subprocess.Popen([str(terminal),'-Shell',str(script),'-NSUseRunningCopy','NO',
                        '-GSBackend','libgnustep-wayland','-GSTheme','NextSpace'],env=env,stdout=log,stderr=log)
                until(lambda: ready.exists() and typed.exists(),'Terminal PTY reader')
                def terminal_state():
                    result=subprocess.run([str(workspace_probe),'--terminal-input'],env=env,
                        capture_output=True,text=True,timeout=10)
                    return json.loads(result.stdout) if result.returncode==0 else None
                def terminal_window():
                    assert client.poll() is None,(directory/'terminal.log').read_text()[-3000:]
                    return next((w for w in command('windows') if w['pid']==client.pid and w['width']>200),None)
                w=until(terminal_window,'real-engine Terminal window')
                runtime_record(terminal,directory/'runtime.json')
                assert command(f"focus {w['id']}")['ok'];until(terminal_state,'Terminal input client')
                activate('terminal')
                if wire_trace:
                    until(lambda: b'surrounding_text("", 0, 0)' in (artifacts/'engine.log').read_bytes()[engine_start:],
                        'engine receives Terminal context')
                expected=b''
                for index,scale in enumerate((120,150,180,210,240)):
                    output=outputs[index%len(outputs)]
                    assert command(f"test-scale {output['name']} {scale} 10000")['ok'];assert command('confirm')['ok']
                    output=next(head for head in command('outputs') if head['name']==output['name'])
                    assert command(f"move {w['id']} {output['x']+10} {output['y']+10}")['ok']
                    until(lambda: terminal_window()['preferred_scale']==scale,'Terminal density')
                    assert command(f"focus {w['id']}")['ok']
                    for code in method['keys']:key(code)
                    marked=until(lambda: (row:=terminal_state()) and row['marked'] and
                        (method['preedit'] is None or row['preedit']==method['preedit']) and row,
                        'Terminal '+method['label']+' preedit')
                    assert marked['glyphs_covered'],marked
                    # Hangul commits the completed syllable while composing the next one.
                    partial=expected+method['partial'].encode()
                    until(lambda: typed.read_bytes()==partial,'committed prefix without preedit leakage')
                    popups=until(lambda: [popup for popup in command('input-popups') if popup['width']>0 and popup['height']>0],
                        'Terminal candidate popup') if method['candidates'] else []
                    for popup in popups:assert_on_output(popup,[output])
                    key(57);expected+=method['text'].encode()
                    until(lambda: typed.read_bytes()==expected,'exact committed '+method['label']+' PTY bytes')
                    until(lambda: (row:=terminal_state()) and not row['marked'],'Terminal clears preedit')
                    terminal_records.append(dict(scale=scale,marked=marked,bytes=len(expected),popups=popups,window=terminal_window()))
                (directory/'results.json').write_text(json.dumps(dict(cases=terminal_records,bytes=len(expected)),indent=2)+'\n')
                if engine_name=='hangul':
                    for _ in range(2):
                        for code in method['keys']:key(code)
                        key(57)
                    expected+=method['text'].encode()*2
                    until(lambda: typed.read_bytes()==expected,'interleaved IME/raw-key PTY bytes')
                    burst_records.append(dict(application='Terminal',bytes=len(expected)))
                stop_process(client);client=None
            mapped=sorted({
                line.split()[-1] for line in Path(f'/proc/{engine.pid}/maps').read_text().splitlines()
                if any(name in line for name in ('/fcitx5/','/libFcitx5','/libhangul','/libime'))})
            libraries=[];data_files={}
            for name in mapped:
                path=Path(name)
                with path.open('rb') as stream:elf=stream.read(4)==b'\x7fELF'
                if elf:libraries.append(name)
                else:data_files[name]=dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size)
            (artifacts/'engine-runtime.json').write_text(json.dumps(dict(executable='/usr/bin/fcitx5',
                libraries=libraries,data_files=data_files),indent=2)+'\n')
            (artifacts/'results.json').write_text(json.dumps(dict(cases=records,complete=True,native=True,real_engine=True,
                input_method='Fcitx5 '+method['label'],candidate_tested=method['candidates'],
                replace_selection=replace_selection,wire_trace=wire_trace,nested_events=nested_events,
                terminal_cases=terminal_records,burst_cases=burst_records,
                display_unset='DISPLAY' not in env),indent=2)+'\n')
            print('Actual Fcitx5 '+method['label']+': five densities and four native AppKit run-loop modes PASS')
        except BaseException:
            (artifacts/'failure.json').write_text(json.dumps(dict(events=events() if client else [],
                windows=command('windows') if server and server.poll() is None else [],engine_exit=engine.poll() if engine else None),indent=2)+'\n')
            raise
        finally:
            for process in (client,engine,storage):
                if process:stop_process(process)
            if server:
                if server.poll() is None:command('quit');server.wait(timeout=5)
                server.stdout.close()
            if bus:stop_process(bus);bus.stdout.close()
            control.close();broker.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('compositor','probe','artifacts'):parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--nested',action='store_true')
    parser.add_argument('--engine',choices=ENGINES,default='pinyin')
    parser.add_argument('--replace-selection',action='store_true')
    parser.add_argument('--no-wire-trace',action='store_true')
    parser.add_argument('--pasteboard-server',type=Path);parser.add_argument('--pasteboard-probe',type=Path)
    parser.add_argument('--terminal',type=Path);parser.add_argument('--workspace-probe',type=Path)
    args=parser.parse_args()
    if bool(args.terminal)!=bool(args.workspace_probe):parser.error('--terminal and --workspace-probe are required together')
    if bool(args.pasteboard_server)!=bool(args.pasteboard_probe):parser.error('--pasteboard-server and --pasteboard-probe are required together')
    run(args.compositor.resolve(),args.probe.resolve(),args.artifacts.resolve(),args.nested,
        args.terminal.resolve() if args.terminal else None,args.workspace_probe.resolve() if args.workspace_probe else None,
        args.engine,args.replace_selection,not args.no_wire_trace,args.pasteboard_server,args.pasteboard_probe)
