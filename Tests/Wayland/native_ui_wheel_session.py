#!/usr/bin/env python3
"""Own a headless compositor, real GNUstep reference window and pinned browser.

The private control socket exposes the compositor's inherited test capability
only inside this fixture. It does not add a desktop protocol or input API.
"""
import argparse,json,os,select,socket,subprocess,sys,time
from contextlib import ExitStack
from pathlib import Path
from gnustep import headless_session,pasteboard_storage
from integration import process_runtime

REPO=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser(description=__doc__)
for name in ['compositor','backend-bundle','build','library','chromium','hook','output']:
    p.add_argument('--'+name,type=Path,required=True)
p.add_argument('--library-path',action='append',default=[])
p.add_argument('--port',type=int,default=9249)
a=p.parse_args();out=a.output;children=[]
def stop(process):
    if process.poll() is None:
        process.terminate()
        try:process.wait(timeout=8)
        except subprocess.TimeoutExpired:process.kill();process.wait()
with headless_session(a.compositor,out,extra_env=dict(
    GNUSTEP_CONFIG_FILE='/Library/Preferences/GNUstep.conf',
    LD_LIBRARY_PATH=':'.join(a.library_path))) as (env,command),ExitStack() as services:
    env.pop('LD_PRELOAD',None)
    bundles=Path(env['GNUSTEP_CONFIG_FILE']).parent/'empty-library/Bundles';bundles.mkdir(parents=True)
    assert a.backend_bundle.name=='libgnustep-wayland-032.bundle'
    (bundles/a.backend_bundle.name).symlink_to(a.backend_bundle.resolve(),target_is_directory=True)
    services.enter_context(pasteboard_storage(Path('/Library/bin/gpbs-wayland'),a.build/'native-ui/native-pasteboard-probe',env,out))
    control_path=out/'control.sock'
    with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as server:
        server.bind(str(control_path));control_path.chmod(0o600);server.listen(1)
        endpoint=Path(env['XDG_RUNTIME_DIR'])/'native.sock'
        try:
            native=subprocess.Popen([str(a.build/'native-ui/native-wheel-probe'),'--seat','-GSBackend','wayland'],
                env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(out/'native-seat.stderr').open('w'),text=True)
            children.append(native)
            assert select.select([native.stdout],[],[],15)[0]
            assert json.loads(native.stdout.readline())['event']=='native-wheel-ready'
            helper=subprocess.Popen([sys.executable,str(REPO/'Experiments/ChromiumScrollers/helper.py'),
                '--library',str(a.library),'--socket',str(endpoint),'-GSBackend','wayland'],env=env,
                stdout=(out/'helper.jsonl').open('w'),stderr=(out/'helper.stderr').open('w'))
            children.append(helper);end=time.monotonic()+30
            while not endpoint.exists():
                assert helper.poll() is None and time.monotonic()<end;time.sleep(.02)
            browser_env=dict(env,LD_PRELOAD=str(a.hook),NEXTSPACE_CHROMIUM_SOCKET=str(endpoint),
                NEXTSPACE_CHROMIUM_LOG=str(out/'hook.log'))
            for flag in ['FORMS','INPUT','TEXT','MULTILINE','MULTILINE_VIEWPORT','WHEEL','VIEWS']:
                browser_env['NEXTSPACE_CHROMIUM_'+flag]='1'
            args=[str(a.chromium),'--ozone-platform=wayland','--gtk-version=4','--disable-gpu',
                '--disable-dev-shm-usage','--no-first-run','--no-default-browser-check',
                '--disable-background-networking','--disable-sync','--disable-component-update',
                '--password-store=basic','--remote-debugging-port='+str(a.port),'--window-size=900,700',
                '--user-data-dir='+env['XDG_RUNTIME_DIR']+'/profile',
                (REPO/'Experiments/ChromiumScrollers/test-multiline.html').as_uri()]
            browser=subprocess.Popen(args,env=browser_env,stdout=(out/'browser.stdout').open('w'),stderr=(out/'browser.stderr').open('w'))
            children.append(browser)
            (out/'launch.json').write_text(json.dumps(dict(pids=[c.pid for c in children],command=args),indent=2)+'\n')
            print(json.dumps(dict(event='wheel-fixture-ready',control=str(control_path))),flush=True)
            while True:
                connection,_=server.accept()
                with connection:
                    request=json.loads(connection.recv(65536));text=request['command']
                    if text=='quit':connection.send(json.dumps(dict(ok=True)).encode());break
                    if text.startswith('native '):
                        native.stdin.write(text[7:]+'\n');native.stdin.flush()
                        assert select.select([native.stdout],[],[],10)[0]
                        result=json.loads(native.stdout.readline())
                    elif text.startswith('reference '):
                        spec=json.loads(text.split(' ',1)[1]);name=spec['name']
                        assert name==Path(name).name and name not in ('.','..')
                        target=out/name;target.mkdir();source=target/'controls.json';source.write_text(json.dumps(spec['controls']))
                        with (target/'stdout').open('w') as stdout,(target/'stderr').open('w') as stderr:
                            subprocess.run([sys.executable,str(REPO/'Experiments/ChromiumScrollers/native-control-reference.py'),
                                '--library',str(a.library),'--controls',str(source),'--output',str(target),
                                '-GSBackend','wayland'],env=env,stdout=stdout,stderr=stderr,timeout=30,check=True)
                        result=dict(path=str(target),reference=json.loads((target/'results.json').read_text()))
                    else:result=command(text)
                    connection.send(json.dumps(result).encode())
        finally:
            (out/'processes.json').write_text(json.dumps([process_runtime(c.pid) for c in children if c.poll() is None],indent=2)+'\n')
            for child in reversed(children):stop(child)
            control_path.unlink(missing_ok=True)
            (out/'cleanup.json').write_text(json.dumps(dict(exits=[c.returncode for c in children],live=[c.pid for c in children if c.poll() is None]))+'\n')
