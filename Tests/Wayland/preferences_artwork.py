#!/usr/bin/env python3
"""Check vector module icons through the actual Preferences icon matrix."""
import argparse
import json
import math
from pathlib import Path
import subprocess
from PIL import Image, ImageChops
from application_artwork import placed_reference, representations
from gnustep import headless_session, process_runtime
from integration import until

MODULE_IMAGES = (('Display','Monitor',(66,57)), ('Keyboard','Keyboard',(66,57)), ('Mouse','Mouse',(44,44)),
    ('Date','Date',(66,57)), ('Screen','Screen',(60,48)), ('Sound','Sound',(44,46)),
    ('Font','FontPreferences',(48,48)), ('Services','Services',(48,48)),
    ('Localization','Localization',(52,49)), ('Expert','Expert',(60,49)),
    ('Login','Loginwindow',(66,57)))


def run(compositor, application, probe, density_probe, artifacts, modules=None, runtime_root=None):
    artifacts.mkdir(parents=True)
    source_fidelity = None
    if not modules or 'Login' in modules:
        from login_preferences_fidelity import verify
        source_fidelity = verify(Path(__file__).resolve().parents[2])
    resources = application.parent / 'Resources'
    images = {}
    if modules and set(modules) - {row[0] for row in MODULE_IMAGES}:
        raise ValueError('Unknown Preferences module')
    for module, name, logical in MODULE_IMAGES:
        if modules and module not in modules:
            continue
        bundle = ((runtime_root or Path('/usr/NextSpace')) / 'Apps/Login.app/Resources/Login.preferences'
            if module == 'Login' else resources / (module+'.preferences'))
        path = bundle / ('Resources/'+name+'.tiff')
        frames, metadata = representations(density_probe, path, artifacts, logical)
        images[module] = (frames, metadata, bundle)
    with headless_session(compositor, artifacts, application.parent.parent) as (env, command):
        captures = artifacts / 'captures'; app = None
        try:
            with (artifacts/'application.log').open('w') as output:
                app = subprocess.Popen([str(application),'-GSBackend','libgnustep-wayland','-GSTheme','NextSpace'],env=env,stdout=output,stderr=output)
            until(lambda: any(w['pid']==app.pid and w['width']>300 for w in command('windows')), 'Preferences startup',timeout=20)
            runtime = process_runtime(app.pid)
            (artifacts/'application-runtime.json').write_text(json.dumps(runtime,indent=2)+'\n')
            if runtime_root:
                toolkit = ('libgnustep-', 'libobjc', 'libCoreFoundation', 'libdispatch', 'libSystemKit', 'libDesktopKit')
                misplaced = [path for path in runtime['libraries'] if any(name in Path(path).name for name in toolkit)
                    and not Path(path).is_relative_to(runtime_root)]
                assert not misplaced, ('Unexpected toolkit or backend outside the private runtime', misplaced)
            target=command('outputs')[0]; records=[]; state=None
            for at,density in enumerate((120,150,180,210,240)):
                assert command(f"test-scale {target['name']} {density} 10000")['ok'] and command('confirm')['ok']
                for module,(frames,metadata,bundle) in images.items():
                    directory=artifacts/f'{module}-{density}'; directory.mkdir()
                    def query():
                        caption={'Date':'Date & Time','Login':'Login Window'}.get(module,module)
                        result=subprocess.run([str(probe),'--preferences-icon',caption],env=env,capture_output=True,text=True,timeout=15)
                        (directory/'query.log').write_text(result.stdout+result.stderr)
                        assert result.returncode==0,result.stderr
                        return json.loads(result.stdout)
                    if state is None:state=query()
                    paths={line.split()[-1] for line in Path(f'/proc/{app.pid}/maps').read_text().splitlines() if '.preferences/' in line.split()[-1]}
                    expected_module=bundle/module
                    assert str(expected_module.resolve()) in paths, (module,sorted(paths))
                    (directory/'loaded-modules.json').write_text(json.dumps(sorted(paths),indent=2)+'\n')
                    def window(): return next(w for w in command('windows') if w['pid']==app.pid and w['client_id']==state['window'])
                    assert command(f"move {window()['id']} {target['x']+10} {target['y']+10}")['ok']
                    path=captures/f"window-{state['window']}-{density}.png"; path.unlink(missing_ok=True)
                    state=query()
                    assert state['representations']==[[r['width'],r['height']] for r in metadata['representations']]
                    attempts=0
                    def capture():
                        nonlocal attempts
                        attempts+=1
                        w=window()
                        if w['preferred_scale']!=density or w['buffer_width']!=(w['width']*density+60)//120:return False
                        try:
                            with Image.open(path) as image:actual=image.convert('RGBA')
                        except OSError:return False
                        if actual.size!=(w['buffer_width'],w['buffer_height']):return False
                        actual.save(directory/'window.png')
                        x,y,width,height=state['base']; factor=density/120
                        def stable_pixel(value):
                            # Message-port doubles can place an integral edge just below its pixel.
                            return round(value) if math.isclose(value,round(value),abs_tol=1e-7) else value
                        origin=tuple(map(stable_pixel,(x*factor,(w['height']-y-height)*factor)))
                        left,top=map(math.floor,origin)
                        size=tuple(math.ceil(stable_pixel(value)) for value in
                            (width*factor+origin[0]-left,height*factor+origin[1]-top))
                        actual=actual.crop((left,top,left+size[0],top+size[1])); actual.save(directory/'actual.png')
                        expected=placed_reference(frames[at],(origin[0]-left,origin[1]-top),
                            Image.new('RGBA',size,actual.getpixel((0,0))),directory,density,size=(width*factor,height*factor),pad=True)
                        expected.save(directory/'expected.png')
                        inset=0 if density in (120,240) else 1
                        difference=ImageChops.difference(actual,expected).crop((inset,inset,size[0]-inset,size[1]-inset))
                        maximum=max(channel[1] for channel in difference.getextrema())
                        # Scrolling can commit one frame from the preceding cell first.
                        return (w,maximum,inset) if maximum<=1 else False
                    w,maximum,inset=until(capture,f'painted Preferences {module} icon at {density}',timeout=20)
                    records.append(dict(module=module,scale=density,window=w,state=state,
                        maximum_channel_difference=maximum,excluded_bounding_pixels=inset,capture_attempts=attempts))
            (artifacts/'results.json').write_text(json.dumps(dict(cases=records,resources={name:metadata for name,(_,metadata,_) in images.items()},source_fidelity=source_fidelity,complete=True),indent=2)+'\n')
            print(f'Preferences module artwork: {len(images)*5} selections and {len(records)} native matrix pixel checks PASS')
        finally:
            if app is not None and app.poll() is None: app.terminate(); app.wait(timeout=5)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('compositor','application','probe','density-probe','artifacts'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--module', action='append', choices=[row[0] for row in MODULE_IMAGES])
    parser.add_argument('--runtime-root', type=Path, help='Require toolkit and backend libraries inside this private prefix')
    args=parser.parse_args()
    run(*(getattr(args,name).resolve() for name in ('compositor','application','probe','density_probe','artifacts')),
        modules=args.module, runtime_root=args.runtime_root.resolve() if args.runtime_root else None)
