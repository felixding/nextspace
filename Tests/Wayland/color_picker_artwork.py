"""Verify shared picker artwork and actual mode buttons at all five densities."""
import json
import math
from pathlib import Path
from PIL import Image,ImageChops
from application_artwork import representations,placed_reference
from color_panel import color_panel
from integration import until

MODES=('GSGrayColorPicker','GSRGBColorPicker','GSCMYKColorPicker','GSHSBColorPicker')


def compare(actual,reference,view,window,density,artifacts,name):
    assert view['logical'] in ([36,24],[24,24])
    factor=density/120;x,y,width,height=view['drawing_base']
    origin=(x*factor,(window['height']-y-height)*factor);left,top=[math.floor(v+.5) for v in origin]
    size=(round(width*factor),round(height*factor));crop=actual.crop((left,top,left+size[0],top+size[1]))
    expected=placed_reference(reference,(origin[0]-left,origin[1]-top),Image.new('RGBA',crop.size,crop.getpixel((0,0))),
                              artifacts,density,size=(width*factor,height*factor),pad=True)
    maximum=max(v[1] for v in ImageChops.difference(crop,expected).getextrema())
    assert maximum<=1,(name,density,maximum,view)
    return dict(name=name,origin=origin,crop=[left,top,*size],maximum_channel_difference=maximum)


def run(compositor,application,probe,density_probe,artifacts,baseline=False):
    resources=Path('/Library/ColorPickers/StandardPicker.bundle/Resources')
    frames={};selections={};cases=[];clicks=[]
    # Resource checks precede the live panel; both use the same installed files.
    resource_artifacts=artifacts/'resources';resource_artifacts.mkdir(parents=True)
    for name in MODES:
        if baseline:
            with Image.open(resources/(name+'.tiff')) as image:frames[name]=[image.convert('RGBA')]*5
        else:frames[name],selections[name]=representations(density_probe,resources/(name+'.tiff'),resource_artifacts,(36,24))
    with color_panel(compositor,application,probe,artifacts/'panel') as panel:
        command=panel.command
        main=next(c for c in panel.controls()['image_cells'] if c.get('matrix_columns')==3 and c['column']==0)
        panel.click(main['base'])
        until(lambda:len([c for c in panel.controls()['image_cells'] if c.get('matrix_columns')==4])==4,
              'The native slider picker exposes its four mode buttons')
        for at,density in enumerate((120,150,180,210,240)):
            for output in command('outputs'):
                assert command(f"test-scale {output['name']} {density} 10000")['ok'] and command('confirm')['ok']
            output=command('outputs')[0];w=panel.window()
            assert command(f"move {w['id']} {output['x']+100} {output['y']+100}")['ok']
            until(lambda:panel.captured(density),'Slider-picker backing density')
            for mode,name in enumerate(MODES):
                state=panel.controls();buttons=sorted([c for c in state['image_cells'] if c.get('matrix_columns')==4],key=lambda c:c['column'])
                assert len(buttons)==4;panel.click(buttons[mode]['base'])
                # The pinned GNUstep subpickers report mode masks (1,2,4,8),
                # rather than the public enum. Preserve and record that baseline.
                state=until(lambda:(s if (s:=panel.controls())['color_mode']==1<<mode else None),'Native color-picker mode changes')
                assert len(state['fields'])==len(state['sliders'])==(1,3,4,3)[mode]
                buttons=sorted([c for c in state['image_cells'] if c.get('matrix_columns')==4],key=lambda c:c['column'])
                assert [c['column'] for c in buttons if c['selected']]==[mode]
                main=next(c for c in state['image_cells'] if c.get('matrix_columns')==3 and c['column']==0)
                expected=[[36,24]] if baseline else [[36,24],[45,30],[54,36],[63,42],[72,48]]
                assert all(v['representations']==expected for v in [*buttons,main])
                directory=artifacts/f'{density}-{mode}';directory.mkdir()
                def drawn():
                    value=panel.captured(density)
                    if not value:return False
                    window,pixels=value
                    try:
                        checks=[compare(pixels,frames[n][at],view,window,density,directory,n)
                                for n,view in zip(MODES,buttons)]
                        checks.append(compare(pixels,frames[name][at],main,window,density,directory,name))
                    except AssertionError as failure:
                        pixels.save(directory/'pending-window.png');(directory/'pending.txt').write_text(str(failure));return False
                    return window,pixels,checks
                window,pixels,checks=until(drawn,'Native slider-picker image pixels')
                assert not window['legacy'];pixels.save(directory/'window.png')
                cases.append(dict(scale=density,mode=mode,name=name,window=window,controls=state,comparisons=checks))
                clicks.append(dict(scale=density,mode=mode,button=buttons[mode]['base']))
    result=dict(passed=True,cases=cases,clicks=clicks,resource_selections=selections,baseline=baseline,
                native_comparisons=sum(len(c['comparisons']) for c in cases),application_runtime=panel.runtime,
                normal_keyboard_quit=panel.normal_keyboard_quit,all_processes_reaped=panel.app.poll() is not None,full_plan_complete=False)
    (artifacts/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Shared slider pickers: 100 native image comparisons and twenty real mode-button actions PASS.')
    return result
