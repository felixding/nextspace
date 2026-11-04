#!/usr/bin/env python3
"""Check Review's real page buttons and their actions on native Wayland."""
import argparse
import json
from pathlib import Path
import subprocess

from PIL import Image
from application_artwork import representations
from gnustep import headless_session, process_runtime
from integration import until
from review import document, request
from review_page_fidelity import NAMES


def compare(actual, reference, view, window, density):
    factor = density/120
    x,y,width,height = view['drawing_base']
    position = (x*factor,(window['height']-y-height)*factor)
    assert all(abs(value-round(value)) < .00001 for value in position), ('Unaligned page image',view)
    assert [round(width*factor),round(height*factor)] == list(reference.size), ('Page image rescaled',view)
    left,top = map(round,position)
    crop = actual.crop((left,top,left+reference.width,top+reference.height))
    pixels = [(x,y) for y in range(reference.height) for x in range(reference.width)
        if reference.getpixel((x,y))[3]]
    # These crisp vector shapes have fully opaque ink. The transparent margin
    # can overlap the button bezel; it is not an independent flat background.
    assert pixels and all(reference.getpixel(p)[3] == 255 for p in pixels)
    maximum = max(abs(crop.getpixel(p)[c]-reference.getpixel(p)[c]) for p in pixels for c in range(4))
    assert maximum <= 1, ('Native page image differs',view['name'],density,maximum)
    return dict(name=view['name'],origin=[left,top],checked_opaque_pixels=len(pixels),maximum_channel_difference=maximum)


def run(compositor, application, probe, density_probe, artifacts):
    artifacts.mkdir(parents=True)
    resources = application.parent/'Resources'
    images = {name:representations(density_probe,resources/(name+'.tiff'),artifacts,(13,13)) for name in NAMES}
    source = document(artifacts); records = []; clicks = []
    with headless_session(compositor,artifacts,application.parent.parent) as (env,command):
        with (artifacts/'application.log').open('w') as log:
            app = subprocess.Popen([str(application),'-GSBackend','libgnustep-wayland','-GSTheme','NextSpace'],env=env,stdout=log,stderr=log)
        try:
            until(lambda:any(w['pid']==app.pid for w in command('windows')),'Review startup',timeout=20)
            query = lambda action,*args:request(probe,env,artifacts,action,*args)
            assert query('open',str(source))['frames'] == 3
            def window():
                assert app.poll() is None, (artifacts/'application.log').read_text()[-4000:]
                return next(w for w in command('windows') if w['pid']==app.pid and source.name in w['title'])
            (artifacts/'application-runtime.json').write_text(json.dumps(process_runtime(app.pid),indent=2)+'\n')
            target = command('outputs')[0]
            for at,density in enumerate((120,150,180,210,240)):
                assert command(f"test-scale {target['name']} {density} 10000")['ok'] and command('confirm')['ok']
                assert command(f"move {window()['id']} {target['x']+10} {target['y']+10}")['ok']
                until(lambda:window()['preferred_scale']==density,'Review page-button density')
                for highlighted in (False,True):
                    directory = artifacts/f'{density}-{int(highlighted)}'; directory.mkdir()
                    w = window(); path = artifacts/'captures'/f"window-{w['client_id']}-{density}.png"; path.unlink(missing_ok=True)
                    state = query('artwork',str(int(highlighted)))
                    assert len(state['images']) == 2 and state['window'] == w['client_id']
                    for view in state['images']:
                        assert view['logical'] == [13,13] and view['highlighted'] == highlighted and view['enabled']
                        metadata = images[view['name']][1]
                        assert view['representations'] == [[r['width'],r['height']] for r in metadata['representations']]
                    def capture():
                        current = window()
                        try:
                            with Image.open(path) as image: actual = image.convert('RGBA')
                        except OSError: return False
                        if actual.size != (current['buffer_width'],current['buffer_height']): return False
                        try: checks = [compare(actual,images[view['name']][0][at],view,current,density) for view in state['images']]
                        except AssertionError:
                            actual.save(directory/'pending-window.png'); return False
                        return current,actual,checks
                    current,actual,checks = until(capture,'Review page-button native pixels')
                    assert not current['legacy']; actual.save(directory/'window.png')
                    records.append(dict(scale=density,highlighted=highlighted,window=current,state=state,comparisons=checks,capture=str(directory.relative_to(artifacts)/'window.png')))
                state = query('artwork','0')
                assert command(f"focus {window()['id']}")['ok'] and query('state')['index'] == 0
                for name,index in (('PageDown',1),('PageUp',0)):
                    view = next(v for v in state['images'] if v['name']==name); w = window(); x,y,width,height = view['base']
                    point = [round(w['x']+x+width/2),round(w['y']+w['height']-y-height/2)]
                    assert command(f'pointer {point[0]} {point[1]}')['ok']
                    try: assert command('button 272 1')['ok']
                    finally: assert command('button 272 0')['ok']
                    until(lambda:query('state')['index']==index,'Review page button action')
                    clicks.append(dict(scale=density,button=name,index=index,pointer=point))
            result = dict(complete=True,cases=records,clicks=clicks,resources={n:metadata for n,(_,metadata) in images.items()})
            (artifacts/'results.json').write_text(json.dumps(result,indent=2)+'\n')
            print('Review page buttons: 20 native artwork comparisons and ten real pointer actions PASS.')
            return result
        finally:
            if app.poll() is None: app.terminate(); app.wait(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('compositor','application','probe','density-probe','artifacts'):
        parser.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args()
    run(*(getattr(args,name).resolve() for name in ('compositor','application','probe','density_probe','artifacts')))
