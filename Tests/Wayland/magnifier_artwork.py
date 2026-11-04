"""Check the real magnifier button and custom cursor at every target density."""
import json
import math
from pathlib import Path
from PIL import Image
from application_artwork import representations,placed_reference
from color_panel import color_panel
from cursor_assets import pixels_hash
from integration import until


def compare(actual,reference,view,window,density,artifacts):
    assert view['logical']==[32,32]
    factor=density/120;x,y,width,height=view['drawing_base']
    origin=(x*factor,(window['height']-y-height)*factor);left,top=[math.floor(v+.5) for v in origin]
    size=(round(width*factor),round(height*factor));crop=actual.crop((left,top,left+size[0],top+size[1]))
    background=crop.getpixel((0,crop.height//2));offset=(origin[0]-left,origin[1]-top)
    foreground=placed_reference(reference,offset,Image.new('RGBA',crop.size),artifacts,density,size=(width*factor,height*factor),pad=True)
    expected=placed_reference(reference,offset,Image.new('RGBA',crop.size,background),artifacts,density,size=(width*factor,height*factor),pad=True)
    # The transparent margin can overlap the button bezel. Check the actual
    # painted glyph against its flat interior background, including soft edges.
    points=[(x,y) for y in range(crop.height) for x in range(crop.width) if foreground.getpixel((x,y))[3]]
    maximum=max(abs(a-b) for p in points for a,b in zip(crop.getpixel(p),expected.getpixel(p)))
    assert maximum<=1,('Native magnifier pixels differ',density,maximum,view)
    return dict(origin=list(origin),crop=[left,top,*size],background=list(background),
                checked_foreground_pixels=len(points),maximum_channel_difference=maximum)


def run(compositor,application,probe,density_probe,artifacts,baseline=False):
    resource=Path('/Library/Images/MagnifyGlass.tiff');directory=artifacts/'resources';directory.mkdir(parents=True)
    if baseline:
        with Image.open(resource) as image:frames=[image.convert('RGBA')]*5
        selections=None
    else:frames,selections=representations(density_probe,resource,directory,(32,32))
    cases=[]
    with color_panel(compositor,application,probe,artifacts/'panel') as panel:
        command=panel.command
        for at,density in enumerate((120,150,180,210,240)):
            for output in command('outputs'):
                assert command(f"test-scale {output['name']} {density} 10000")['ok'] and command('confirm')['ok']
            output=command('outputs')[0];window=panel.window()
            assert command(f"move {window['id']} {output['x']+100} {output['y']+100}")['ok']
            until(lambda:panel.captured(density),'Magnifier panel backing density')
            state=panel.controls();view=next(c for c in state['image_cells'] if c['name']=='MagnifyGlass')
            assert view['resource']==str(resource)
            assert view['representations']==([[32,32]] if baseline else [[32,32],[40,40],[48,48],[56,56],[64,64]])
            directory=artifacts/str(density);directory.mkdir()
            def painted():
                value=panel.captured(density)
                if not value:return False
                window,pixels=value
                try:check=compare(pixels,frames[at],view,window,density,directory)
                except AssertionError as failure:
                    pixels.save(directory/'pending-window.png');(directory/'pending.txt').write_text(str(failure));return False
                return window,pixels,check
            window,pixels,check=until(painted,'Magnifier native button pixels');pixels.save(directory/'window.png')
            button=next(b for b in state['buttons'] if b['action']=='_magnify:');panel.click(button['base'])
            expected_hash=None if baseline else pixels_hash(frames[at].convert('RGBa').tobytes('raw','BGRa'))
            trace=[]
            def tracking():
                if not baseline:
                    cursor=command('color-pick-state');trace.append(cursor)
                    return cursor if cursor.get('active') and cursor.get('density')==density and \
                        (cursor.get('width'),cursor.get('height'))==(32*density//120,)*2 and \
                        cursor.get('pixels_hash')==expected_hash else False
                cursor=command('cursor-state');trace.append(cursor)
                return cursor if cursor.get('width')==cursor.get('height')==32 and \
                    (cursor.get('buffer_width'),cursor.get('buffer_height'))==(32*density//120,)*2 and \
                    (expected_hash is None or cursor.get('pixels_hash')==expected_hash) else False
            try:cursor=until(tracking,'Magnifier custom cursor pixels and density')
            finally:(directory/'cursor-trace.json').write_text(json.dumps(trace,indent=2)+'\n')
            assert (cursor['hotspot_x'],cursor['hotspot_y'])==(12,13)
            # Finish in the owner's client; color-value checks remain separate.
            assert command(f"pointer {window['x']+100} {window['y']+75}")['ok'] and command('button 272')['ok']
            restored=panel.controls();assert restored['color_mode']==state['color_mode']
            if not baseline:until(lambda:not command('color-pick-state')['active'],'Magnifier selection exits')
            # Keyboard focus otherwise leaves the button's dotted focus ring
            # across the translucent handle on the next density. Tab moves it.
            for value in (1,0):assert command(f'key 15 {value}')['ok']
            cases.append(dict(scale=density,window=window,image_view=view,button_comparison=check,cursor=cursor,
                              expected_cursor_hash=expected_hash,tracking_exited=True))
    result=dict(passed=True,cases=cases,resource_selections=selections,baseline=baseline,
                application_runtime=panel.runtime,normal_keyboard_quit=panel.normal_keyboard_quit,
                all_processes_reaped=panel.app.poll() is not None,screen_sampling_qualified=False,full_plan_complete=False)
    (artifacts/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Magnifier: five native button comparisons, five custom cursor buffers and tracking exits PASS.')
    return result
