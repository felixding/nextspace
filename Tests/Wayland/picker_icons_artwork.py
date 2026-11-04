"""Check real named-color/wheel mode buttons at all target densities."""
import json
from pathlib import Path
from PIL import Image
from application_artwork import representations
from color_panel import color_panel
from color_picker_artwork import compare
from integration import until
from picker_icons_fidelity import NAMES,SIZES


def mode_images(state):
    buttons=[c for c in state['image_cells'] if c.get('matrix_columns')==3];assert len(buttons)==3
    wheel,=[c for c in buttons if c['logical']==[24,24]]
    named,=[c for c in buttons if c['column']!=0 and c['logical']==[36,24]]
    return {NAMES[0]:named,NAMES[1]:wheel}


def run(compositor,application,probe,density_probe,artifacts,baseline=False):
    artifacts.mkdir(parents=True);frames={};selections={};cases=[]
    for name,size,bundle in zip(NAMES,SIZES,['NamedPicker','WheelPicker']):
        resource=Path('/Library/ColorPickers')/(bundle+'.bundle')/'Resources'/(name+'.tiff')
        if baseline:
            with Image.open(resource) as image:frames[name]=[image.convert('RGBA')]*5
        else:
            directory=artifacts/'resources'/name;directory.mkdir(parents=True)
            frames[name],selections[name]=representations(density_probe,resource,directory,size)
    with color_panel(compositor,application,probe,artifacts/'panel') as panel:
        command=panel.command
        for index,density in enumerate((120,150,180,210,240)):
            for output in command('outputs'):
                assert command(f"test-scale {output['name']} {density} 10000")['ok'] and command('confirm')['ok']
            output=command('outputs')[0];w=panel.window();assert command(f"move {w['id']} {output['x']+100} {output['y']+100}")['ok']
            until(lambda:panel.captured(density),'Named/wheel picker backing density')
            for name,mode in zip(NAMES,[5,6]):
                views=mode_images(panel.controls());column=views[name]['column'];panel.click(views[name]['base'])
                state=until(lambda:(s if (s:=panel.controls())['color_mode']==mode else None),'Real named/wheel picker mode action')
                assert len(state['wheels'])==(0 if mode==5 else 1)
                buttons=sorted([c for c in state['image_cells'] if c.get('matrix_columns')==3],key=lambda c:c['column'])
                assert [c['column'] for c in buttons if c['selected']]==[column]
                views=mode_images(state)
                for name,size in zip(NAMES,SIZES):
                    view=views[name]
                    assert view['logical']==list(size)
                    assert view['representations']==([list(size)] if baseline else [[v*d//120 for v in size] for d in (120,150,180,210,240)])
                directory=artifacts/f'{density}-{mode}';directory.mkdir()
                def painted():
                    value=panel.captured(density)
                    if not value:return False
                    window,pixels=value
                    try:checks=[compare(pixels,frames[name][index],view,window,density,directory,name) for name,view in views.items()]
                    except AssertionError as failure:
                        pixels.save(directory/'pending-window.png');(directory/'pending.txt').write_text(str(failure));return False
                    return window,pixels,checks
                window,pixels,checks=until(painted,'Real named/wheel picker image pixels');assert not window['legacy'];pixels.save(directory/'window.png')
                cases.append(dict(scale=density,mode=mode,selected_column=column,window=window,controls=state,comparisons=checks))
    result=dict(passed=True,cases=cases,baseline=baseline,resource_selections=selections,native_comparisons=20,mode_actions=10,
                application_runtime=panel.runtime,normal_keyboard_quit=panel.normal_keyboard_quit,all_processes_reaped=panel.app.poll() is not None,full_plan_complete=False)
    (artifacts/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('Named/wheel pickers: twenty native image comparisons and ten real mode actions PASS.');return result
