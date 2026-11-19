#!/usr/bin/env python3
"""Check native deactivation against a paused and resumed private compositor."""
import argparse,json,os,resource,select,signal,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Wayland'))
from gnustep import headless_session

p=argparse.ArgumentParser(description=__doc__)
for name in ['build','compositor','backend-bundle','gui-library-path','base-library-path','output']:
    p.add_argument('--'+name,required=True,type=Path)
p.add_argument('--queued-enter',action='store_true')
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
libraries=[a.gui_library_path,a.base_library_path,a.build/'native-ui',a.build,Path('/Library/Libraries'),Path('/usr/NextSpace/lib')]
extra=dict(LD_LIBRARY_PATH=':'.join(map(str,libraries)),GNUSTEP_CONFIG_FILE='/Library/Preferences/GNUstep.conf',WLR_HEADLESS_OUTPUTS='1')
with headless_session(a.compositor,a.output,extra_env=extra) as (env,command):
    bundles=Path(env['GNUSTEP_CONFIG_FILE']).parent/'empty-library/Bundles';bundles.mkdir(parents=True)
    (bundles/a.backend_bundle.name).symlink_to(a.backend_bundle.resolve(),target_is_directory=True)
    with (a.output/'probe.stderr').open('w') as error:
        actor=subprocess.Popen([str(a.build/'native-ui/native-focus-fence-probe'),'-GSBackend','wayland']+(['--queued-enter'] if a.queued_enter else []),
            env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=error,text=True)
        compositor=None;events=[]
        def event():
            assert select.select([actor.stdout],[],[],15)[0],'Native activation probe stalled'
            line=actor.stdout.readline();assert line,('Native activation probe exited',actor.poll())
            value=json.loads(line);events.append(value);return value
        try:
            assert event()['phase']=='ready'
            # Resolve the exact private server executable owned by this fixture.
            target=a.compositor.resolve()
            for process in Path('/proc').iterdir():
                if process.name.isdigit():
                    try:
                        args=(process/'cmdline').read_bytes().split(b'\0')
                        if args and Path(os.fsdecode(args[0])).resolve()==target:
                            runtime=(process/'environ').read_bytes().split(b'\0')
                            if ('XDG_RUNTIME_DIR='+env['XDG_RUNTIME_DIR']).encode() in runtime:compositor=int(process.name)
                    except (OSError,ValueError):pass
            assert compositor,'Owned private compositor not found'
            if a.queued_enter:
                from integration import until
                until(lambda:any(w['title']=='Queued focus source' and w['focused'] for w in command('windows')),'original source has actual seat focus')
            os.kill(compositor,signal.SIGSTOP)
            actor.stdin.write('paused\n');actor.stdin.flush()
            assert event()['phase']=='waiting-for-ack'
            os.kill(compositor,signal.SIGCONT);compositor=None
            actor.stdin.write('resumed\n');actor.stdin.flush()
            assert event()['phase']=='passed'
            assert actor.wait(timeout=5)==0
        finally:
            if compositor:os.kill(compositor,signal.SIGCONT)
            if actor.poll() is None:actor.terminate();actor.wait(timeout=5)
            (a.output/'results.json').write_text(json.dumps(dict(passed=bool(events and events[-1]['phase']=='passed'),events=events),indent=2)+'\n')
print(json.dumps(dict(passed=True)))
