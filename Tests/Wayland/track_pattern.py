"""Compare real slider/scroller track geometry with the original checker."""
import hashlib
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageChops
from artwork_reference import artwork_original, assert_not_enlarged
from gnustep import headless_session, pasteboard_storage, process_runtime
from integration import read_json_lines, until
from text_input import stop_process
from vector_art import Artwork


def references(directory):
    # Independent top-down reference; AppKit's drawing coordinates are bottom-up.
    cells=' '.join(f'M{x} {y}h1v1h-1Z' for y in range(12) for x in range(12) if (x+y)%2==0)
    source=directory/'reference.svg'
    source.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12">'
        '<defs><symbol id="Track" viewBox="0 0 12 12"><path fill="#aaa" d="M0 0H12V12H0Z"/>'
        f'<path fill="#555" d="{cells}"/></symbol></defs><use id="preview" href="#Track"/></svg>')
    art=Artwork(source)
    frames=[art.render('Track',(n,n)) for n in (12,15,18,21,24)]
    original,_=artwork_original('track-pattern','Track')
    assert frames[0].tobytes()==original.tobytes(), 'Original track phase or palette changed'
    assert_not_enlarged(frames,'One-point track checker at backing density')
    return frames


def preview(reference,density):
    factor=density/120
    expected=Image.new('RGBA',(int(300*factor),int(96*factor)))
    n=reference.width
    for y in range(-int(-136*factor)%n-n,expected.height,n):
        for x in range(-int(20*factor)%n-n,expected.width,n):
            expected.paste(reference,(x,y))
    return expected


def run(compositor,application,theme,pasteboard_server,pasteboard_probe,artifacts):
    artifacts.mkdir(parents=True)
    frames=references(artifacts)
    cases=[]
    with headless_session(compositor,artifacts/'native') as (env,command),pasteboard_storage(pasteboard_server,pasteboard_probe,env,artifacts):
        with (artifacts/'application.log').open('w') as log,(artifacts/'application.stderr').open('w') as errors:
            app=subprocess.Popen([str(application),'-GSBackend','libgnustep-wayland','-GSTheme',str(theme),
                '-GSSuppressAppIcon','YES'],env=env,stdout=log,stderr=errors)
        try:
            def window():
                assert app.poll() is None,(artifacts/'application.stderr').read_text()
                return next((w for w in command('windows') if w['pid']==app.pid and w['title']=='Native Track Pattern'),None)
            until(window,'real slider/scroller track window')
            output=command('outputs')[0]
            seen=set()
            for index,density in enumerate((120,150,180,210,240,120)):
                w=window()
                path=Path(env['NEXTSPACE_WAYLAND_CAPTURE_DIR'])/f"window-{w['client_id']}-{density}.png"
                previous=path.stat().st_mtime_ns if density in seen and path.exists() else 0
                assert command(f"test-scale {output['name']} {density} 10000")['ok'] and command('confirm')['ok']
                assert command(f"move {w['id']} {output['x']+10} {output['y']+10}")['ok']

                def captured():
                    w=window()
                    rows=[r for r in read_json_lines(artifacts/'application.log') if r.get('event')=='frame' and round(r['scale']*120)==density]
                    if w['preferred_scale']!=density or not rows:return None
                    try:
                        if path.stat().st_mtime_ns<=previous:return None
                        with Image.open(path) as image:
                            if image.size!=(w['buffer_width'],w['buffer_height']):return None
                            return w,image.convert('RGBA'),rows[-1]
                    except OSError:return None

                w,actual,state=until(captured,'fresh native track pattern pixels')
                assert state['pattern_logical']==[12,12]
                assert state['representations']==[{'class':'NSCustomImageRep','width':0,'height':0}],state
                factor=density/120
                cropped=actual.crop(tuple(int(value*factor) for value in (20,164,320,260)))
                expected=preview(frames[index%5],density)
                maximum=max(v[1] for v in ImageChops.difference(cropped,expected).getextrema())
                directory=artifacts/f'{index}-{density}'
                directory.mkdir()
                actual.save(directory/'window.png');cropped.save(directory/'actual.png');expected.save(directory/'expected.png')
                assert maximum==0,(density,maximum)
                cases.append(dict(density=density,window=w,state=state,maximum_channel_difference=maximum,
                    capture=str((directory/'window.png').relative_to(artifacts)),fresh_capture=True,
                    capture_mtime_ns=path.stat().st_mtime_ns,previous_capture_mtime_ns=previous))
                seen.add(density)
            runtime=process_runtime(app.pid)
            paths={line.split()[-1] for line in Path(f'/proc/{app.pid}/maps').read_text().splitlines() if '.theme/' in line.split()[-1]}
            runtime['theme_binaries']={str(Path(p).resolve()):hashlib.sha256(Path(p).read_bytes()).hexdigest()
                for p in paths if Path(p).read_bytes()[:4]==b'\x7fELF'}
            assert len(runtime['theme_binaries'])==1,runtime
            (artifacts/'runtime.json').write_text(json.dumps(runtime,indent=2)+'\n')
        finally:
            stop_process(app)
    result=dict(passed=True,cases=cases,native_image_comparisons=len(cases),original_100_rgba_exact=True,
        procedural_representation=True,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Track pattern: six fresh native captures, original checker and backing-density geometry PASS',flush=True)
    return result
