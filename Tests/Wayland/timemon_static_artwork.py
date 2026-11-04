"""Verify TimeMon's actual Info image, its menu action and normal keyboard quit."""
import json
import math
from pathlib import Path
import subprocess
from PIL import Image, ImageChops
from application_artwork import image_view_clip, placed_reference, representations
from gnustep import headless_session, process_runtime
from integration import until
from timemon_pause import application_action


def open_panel(command, app, artifacts, title, row):
    """Use the real TimeMon Info submenu, waiting for its leaf highlight."""
    def windows():
        assert app.poll() is None, 'TimeMon exited before opening '+title
        return [w for w in command('windows') if w['pid']==app.pid and w['visible']]
    menu=next(w for w in windows() if w['level']==20)
    assert (menu['width'],menu['height'])==(100,122)
    assert command(f"move {menu['id']} 100 100")['ok']
    until(lambda:next((w for w in windows() if w['id']==menu['id'] and w['x']==w['y']==100),None),'TimeMon menu position')
    assert command('pointer 145 131')['ok'] and command('button 272 1')['ok']
    submenu=until(lambda:next(iter(command('popups')),None),'TimeMon Info submenu')
    leaf_y=31+20*row
    assert command(f"pointer {submenu['x']+45} {submenu['y']+leaf_y}")['ok']
    def highlighted():
        for path in (artifacts/'native/captures').glob('window-*-120.png'):
            try:
                with Image.open(path) as image:pixels=image.convert('RGBA')
            except OSError:continue
            if pixels.size==(submenu['buffer_width'],submenu['buffer_height']) and pixels.getpixel((3,leaf_y))[:3]==(255,255,255):return pixels
        return False
    until(highlighted,title+' menu highlight').save(artifacts/(title.lower()+'-menu-highlight.png'))
    assert command('button 272 0')['ok']
    panel=until(lambda:next((w for w in windows() if w['title']==title),None),'TimeMon '+title+' panel opens')
    (artifacts/(title.lower()+'-opening.json')).write_text(json.dumps(dict(menu=menu,submenu=submenu,leaf_y=leaf_y,panel=panel),indent=2)+'\n')
    return panel


def run(compositor, application, probe, density_probe, resources, artifacts):
    artifacts.mkdir(parents=True)
    references, density = representations(density_probe, resources/'TimeMon.gorm/TM-info.tiff', artifacts, logical=(50,50))
    cases = []
    with headless_session(compositor, artifacts/'native') as (env,command):
        with (artifacts/'application.log').open('w') as log:
            app = subprocess.Popen([str(application),'-GSBackend','libgnustep-wayland',
                '-GSTheme','NextSpace','-NSUseRunningCopy','NO','-UpdatePeriod','3600'],
                env=env,stdout=log,stderr=log)
        def windows():
            assert app.poll() is None, (artifacts/'application.log').read_text()
            return [w for w in command('windows') if w['pid']==app.pid and w['visible']]
        def panel():
            return next((w for w in windows() if w['title']=='Info'),None)
        try:
            until(lambda: application_action(probe,env,artifacts,'state'),'TimeMon registration')
            open_panel(command, app, artifacts, 'Info', 0)
            for index,density_value in enumerate((120,150,180,210,240)):
                for output in command('outputs'):
                    assert command(f"test-scale {output['name']} {density_value} 10000")['ok'] and command('confirm')['ok']
                output=command('outputs')[0];current=panel()
                assert command(f"move {current['id']} {output['x']+100} {output['y']+100}")['ok']
                result=subprocess.run([str(probe),'--info-artwork','TimeMon','Info','--existing'],env=env,
                    capture_output=True,text=True,timeout=15)
                (artifacts/f'query-{density_value}.log').write_text(result.stdout+result.stderr)
                assert result.returncode==0,result.stderr
                metadata=json.loads(result.stdout);view,=metadata['images']
                assert view['representations']==[[n,n] for n in (50,63,75,88,100)]
                assert view['width']==view['height']==50
                def captured():
                    w=panel()
                    if not w or w['preferred_scale']!=density_value:return False
                    path=artifacts/'native/captures'/f"window-{w['client_id']}-{density_value}.png"
                    try:
                        with Image.open(path) as image:pixels=image.convert('RGBA')
                    except OSError:return False
                    return (w,pixels) if pixels.size==(w['buffer_width'],w['buffer_height']) else False
                current,actual=until(captured,'TimeMon Info native backing density')
                assert not current['legacy'] and (current['width'],current['height'])==(322,161)
                actual.save(artifacts/f'info-{density_value}.png')
                factor=density_value/120;x,y,width,height=view['drawing_base']
                origin=(x*factor,(current['height']-y-height)*factor)
                left,top=[math.floor(value+.5) for value in origin]
                edges=image_view_clip(view['base'],current['height'],density_value)
                clip=(edges[0]-left,edges[1]-top,edges[2]-edges[0],edges[3]-edges[1])
                reference=references[index]
                crop=actual.crop((left,top,left+reference.width,top+reference.height))
                expected=placed_reference(reference,(origin[0]-left,origin[1]-top),crop.getpixel((0,0)),
                    artifacts,density_value,size=(width*factor,height*factor),clip=clip)
                crop.save(artifacts/f'actual-{density_value}.png');expected.save(artifacts/f'expected-{density_value}.png')
                maximum=max(v[1] for v in ImageChops.difference(crop,expected).getextrema())
                assert maximum<=1,(density_value,maximum,view)
                cases.append(dict(scale=density_value,window=current,image_view=view,origin=origin,
                                  crop=[left,top],view_clip=clip,maximum_channel_difference=maximum))
            runtime=process_runtime(app.pid)
            assert command(f"focus {current['id']}")['ok']
            for key,state in ((56,1),(16,1),(16,0),(56,0)):
                assert command(f'key {key} {state}')['ok']
            app.wait(timeout=10);assert app.returncode==0
            until(lambda:not any(w['pid']==app.pid for w in command('windows')),'TimeMon normal quit removes its surfaces')
        finally:
            command('button 272 0')
            if app.poll() is None:app.terminate();app.wait(timeout=5)
    result=dict(passed=True,cases=cases,density=density,application_runtime=runtime,
                real_pointer_info_action=True,normal_keyboard_quit=True,owned_application_reaped=app.poll() is not None,
                full_plan_complete=False)
    (artifacts/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print('TimeMon Info: five native pixel comparisons, real menu action and normal keyboard quit PASS.')
    return result
