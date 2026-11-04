"""Render a real GNUstep help attachment with all five backing representations."""
import json
import math
from pathlib import Path
import subprocess

from PIL import Image
from application_artwork import representations
from artwork_reference import assert_svg_representations
from folder_artwork import compare_icon
from gnustep import headless_session,pasteboard_storage,process_runtime
from help_fidelity import verify
from integration import until,read_json_lines
from vector_art import Artwork


def run(compositor,application,observer,density_probe,theme,pasteboard_server,pasteboard_probe,artifacts):
    artifacts.mkdir(parents=True)
    repository=Path(__file__).resolve().parents[2]
    fidelity=verify(repository)
    art=Artwork(repository/'Applications/Artwork/Navigation.svg')
    resource=theme/'Resources/ThemeImages/common_HelpLink.tiff'
    directory=artifacts/'resource'
    directory.mkdir()
    assert_svg_representations(art,'HelpLink',resource,(12,12))
    frames,metadata=representations(density_probe,resource,directory,(12,12))
    traces=artifacts/'traces'
    traces.mkdir()
    cases=[]
    extra=dict(LD_PRELOAD=str(observer),NEXTSPACE_IMAGE_USAGE_DIR=str(traces))
    with headless_session(compositor,artifacts/'native',extra_env=extra) as (env,command),pasteboard_storage(pasteboard_server,pasteboard_probe,env,artifacts):
        with (artifacts/'application.log').open('w') as log,(artifacts/'application.stderr').open('w') as errors:
            app=subprocess.Popen([str(application),'-GSBackend','libgnustep-wayland','-GSTheme',str(theme),'-GSSuppressAppIcon','YES'],env=env,stdout=log,stderr=errors)
        try:
            def window():
                assert app.poll() is None,(artifacts/'application.stderr').read_text()
                return next((w for w in command('windows') if w['pid']==app.pid and w['title']=='Native Help Attachment'),None)
            until(window,'native help attachment window')
            target=command('outputs')[0]
            for index,density in enumerate((120,150,180,210,240)):
                assert command(f"test-scale {target['name']} {density} 15000")['ok'] and command('confirm')['ok']
                w=window()
                assert command(f"move {w['id']} {target['x']+240} {target['y']+100}")['ok']
                directory=artifacts/str(density)
                directory.mkdir()

                def captured():
                    w=window()
                    if not w or w['preferred_scale']!=density:return None
                    events=[r for r in read_json_lines(artifacts/'application.log') if r.get('event')=='frame' and round(r['scale']*120)==density]
                    rows=[r for path in traces.glob('*.jsonl') for r in read_json_lines(path) if r.get('focus_class')=='NSTextView' and r.get('logical_width')==12 and round(r['window_scale']*120)==density]
                    if not events or not rows:return None
                    row=rows[-1]
                    path=Path(env['NEXTSPACE_WAYLAND_CAPTURE_DIR'])/f"window-{w['client_id']}-{density}.png"
                    try:
                        with Image.open(path) as image:
                            if image.size!=(w['buffer_width'],w['buffer_height']):return None
                            actual=image.convert('RGBA')
                    except OSError:return None
                    x,y,width,height=row['image_base']
                    factor=density/120
                    box=(math.floor(x*factor),math.floor((w['height']-y-height)*factor),math.ceil((x+width)*factor),math.ceil((w['height']-y)*factor))
                    if len(actual.crop(box).getcolors(10000) or [])<=3:return None
                    return w,actual,row,events[-1]

                w,actual,row,state=until(captured,'rendered help attachment')
                assert state['target']=='owned-guide.rtf' and state['marker']=='intro'
                assert state['logical']==[12,12] and state['representations']==[[n,n] for n in (12,15,18,21,24)]
                assert row['selected_width']==row['selected_height']==12*density//120
                actual.save(directory/'window.png')
                view=dict(name='HelpLink',resource=row['resource'],logical=[12,12],representations=state['representations'],base=row['image_base'],visible=row['image_visible'],selected=False,dimmed=False,native_composite=True)
                compared=compare_icon(art,frames[index],'HelpLink',view,w,actual,density,directory/'image',resource=resource)
                cases.append(dict(density=density,state=state,view=view,window=w,comparison=compared))
                (artifacts/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
            (artifacts/'runtime.json').write_text(json.dumps(process_runtime(app.pid),indent=2)+'\n')
        finally:
            if app.poll() is None:
                app.terminate()
                app.wait(timeout=5)
    result=dict(passed=True,source_fidelity=fidelity,native_image_comparisons=len(cases),resource_metadata=metadata,
                real_help_attachment=True,link_target_and_marker_preserved=True,cases=cases,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Help link: five native attachment comparisons and exact original visible RGBA PASS',flush=True)
    return result
