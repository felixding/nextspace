"""Compare the three real file-panel image controls at every native density."""
import hashlib
import json
import math
from pathlib import Path
import subprocess

from PIL import Image
from application_artwork import representations
from artwork_reference import assert_svg_representations
from filepanel_fidelity import verify
from folder_artwork import compare_icon
from gnustep import headless_session,pasteboard_storage,process_runtime
from integration import read_json_lines,until
from nextspirit_art import NextSpiritArtwork
from review import panel_action,request
from vector_art import Artwork

ROLES={'_setHomeDirectory:':'PanelHome','_mountMedia:':'PanelMount','_unmountMedia:':'PanelUnmount'}


def run(compositor,review,probe,density_probe,observer,desktopkit_resources,theme,
        pasteboard_server,pasteboard_probe,artifacts):
    artifacts.mkdir(parents=True)
    repository=Path(__file__).resolve().parents[2]
    home=NextSpiritArtwork(repository/'Applications/Artwork/NeXTSpirit','workspace_icons')
    media=Artwork(repository/'Applications/Artwork/FilePanel.svg')
    fidelity=verify(repository,home)
    resources,frames={},{}
    for name in ROLES.values():
        renderer=home if name=='PanelHome' else media
        resource=desktopkit_resources/('NXT'+name+'.tiff')
        directory=artifacts/'resources'/name
        directory.mkdir(parents=True)
        assert_svg_representations(renderer,name,resource,(24,24))
        frames[name],metadata=representations(density_probe,resource,directory,(24,24))
        resources[name]=dict(path=str(resource),sha256=hashlib.sha256(resource.read_bytes()).hexdigest(),metadata=metadata)
        alias=theme/'Resources/ThemeImages'/dict(PanelHome='common_Home.tiff',PanelMount='common_Mount.tiff',PanelUnmount='common_Unmount.tiff')[name]
        assert alias.read_bytes()==resource.read_bytes()
    traces=artifacts/'traces'
    traces.mkdir()
    document=artifacts/'document.tiff'
    Image.new('RGB',(128,128),'blue').save(document)
    original=document.read_bytes()
    cases=[]
    extra=dict(LD_PRELOAD=str(observer),NEXTSPACE_IMAGE_USAGE_DIR=str(traces))
    with headless_session(compositor,artifacts/'native',extra_env=extra) as (env,command),pasteboard_storage(pasteboard_server,pasteboard_probe,env,artifacts):
        with (artifacts/'application.log').open('w') as log:
            app=subprocess.Popen([str(review),'-GSBackend','libgnustep-wayland','-GSTheme',str(theme),
                '-GSFilePath',str(document),'-NSUseRunningCopy','NO'],env=env,stdout=log,stderr=log)
        try:
            until(lambda:request(probe,env,artifacts,'ready')['ready'],'Review application connection')
            until(lambda:any(w['pid']==app.pid and document.name in w['title'] for w in command('windows')),'actual file-panel document')
            target=command('outputs')[0]
            for action in ('open-panel','save'):
                for index,density in enumerate((120,150,180,210,240)):
                    assert command(f"test-scale {target['name']} {density} 15000")['ok'] and command('confirm')['ok']
                    directory=artifacts/(action+'-'+str(density))

                    def painted(value,current,directory):
                        rows=[row for path in traces.glob('*.jsonl') for row in read_json_lines(path)]
                        images=[]
                        for selector in ROLES:
                            candidates=[row for row in rows if row.get('focus_action')==selector and row['window']==current['client_id'] and round(row['window_scale']*120)==density]
                            if not candidates:return False
                            row=candidates[-1]
                            x,y,width,height=row['image_base']
                            factor=density/120
                            box=(math.floor(x*factor),math.floor((current['height']-y-height)*factor),math.ceil((x+width)*factor),math.ceil((current['height']-y)*factor))
                            colors=value['image'].crop(box).getcolors(10000)
                            if colors is None or len(colors)<=4:return False
                            images.append(row)
                        (directory/'images.json').write_text(json.dumps(images,indent=2)+'\n')
                        return True

                    state=panel_action(command,env,directory,app.pid,probe,action,target,density,cancel=True,capture_ready=painted)
                    window=state['window']
                    actual=Image.open(directory/'panel.png').convert('RGBA')
                    for row in json.loads((directory/'images.json').read_text()):
                        name=ROLES[row['focus_action']]
                        assert row['selected_width']==row['selected_height']==24*density//120
                        view=dict(name=name,resource=row['resource'],logical=[24,24],representations=[[r['width'],r['height']] for r in row['representations'] if r['class']=='NSBitmapImageRep'],base=row['image_base'],visible=row['image_visible'],selected=False,dimmed=False)
                        renderer=home if name=='PanelHome' else media
                        compared=compare_icon(renderer,frames[name][index],name,view,window,actual,density,directory/name,
                            resource=Path(resources[name]['path']),scan_aligned=True)
                        cases.append(dict(panel=action,density=density,symbol=name,view=view,window=window,comparison=compared,panel_action=state))
                    (artifacts/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
            assert document.read_bytes()==original
            (artifacts/'runtime.json').write_text(json.dumps(process_runtime(app.pid),indent=2)+'\n')
        finally:
            if app.poll() is None:
                app.terminate()
                app.wait(timeout=5)
    result=dict(passed=True,source_fidelity=fidelity,native_image_comparisons=len(cases),actual_open_save_cancellations=10,
        source_file_preserved=True,kernel_device_operations_requested=False,resources=resources,cases=cases,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('File-panel artwork: thirty native image comparisons and ten real cancellations PASS',flush=True)
    return result
