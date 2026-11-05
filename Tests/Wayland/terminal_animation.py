#!/usr/bin/env python3
"""Qualify real Terminal Info-panel and active miniwindow scrolling artwork."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from PIL import Image, ImageChops
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
from application_artwork import placed_reference, representations
from artwork_reference import assert_svg_representations
from folder_artwork import compare_icon
from gnustep import headless_session, pasteboard_storage, process_runtime, capture_process_failure
from integration import until


def compare_frame(reference,state,window,background,actual,density,directory):
    factor = density/120
    x,y,width,height = state['destination'];left,top = x*factor,(window['height']-y-height)*factor
    destination = (left,top,left+width*factor,top+height*factor)
    clip = destination
    # Cropped image compositing keeps the logical destination's exact coverage.
    logical = state['logical']
    source_top = logical[1]-state['source_y']-height
    clip_rect = (clip[0],clip[1],clip[2]-clip[0],clip[3]-clip[1])
    origin = (left,top-source_top*factor)
    size = tuple(n*factor for n in logical)
    if density != 120:
        # GSdrawImageRep first draws the complete bitmap into its group.
        # DPSimage clips that bitmap's bounds; the cropped destination is
        # clipped separately when the completed group is painted.
        expected = placed_reference(reference,origin,background,directory,density,
            size=size,clip=clip_rect,source_clip=(*origin,*size),pad=True)
    else:
        expected = placed_reference(reference,origin,background,directory,density,size=size,clip=clip_rect,pad=True)
    box = (math.floor(left)-1,math.floor(top)-1,math.ceil(destination[2])+1,math.ceil(destination[3])+1)
    before,after = expected.crop(box),actual.crop(box)
    before.save(directory/'expected.png');after.save(directory/'actual.png')
    difference = ImageChops.difference(before,after)
    maximum = max(hi for lo,hi in difference.getextrema())
    rounded = sum(max(pixel)>1 for pixel in difference.getdata())
    # Clipped NSImageRep sampling may differ by two levels in a few pixels;
    # keep both the channel bound and affected area narrow.
    assert maximum <= 2 and rounded <= before.width*before.height*.02,(state['kind'],density,state['source_y'],maximum,rounded)
    return dict(maximum_channel_difference=maximum,two_level_pixels=rounded,compared_pixels=before.width*before.height,
        clip=clip,source_top=source_top)


def run(compositor,application,probe,density_probe,pasteboard_server,pasteboard_probe,artifacts,theme=Path('NextSpace')):
    artifacts.mkdir(parents=True)
    art = Artwork(Path(__file__).resolve().parents[2]/'Applications/Terminal/Artwork.svg')
    resources = {};images = {}
    for name,logical in (('ScrollingMach',(27,35)),('ScrollingOutput',(28,35)),('DWG',(128,10))):
        relatives = ('English.lproj/Info.gorm/'+name+'.tiff',) if name=='DWG' else (name+'.tiff','English.lproj/Info.gorm/'+name+'.tiff')
        for relative in relatives:
            source = application.parent/'Resources'/relative;directory = artifacts/'resources'/Path(relative).with_suffix('');directory.mkdir(parents=True)
            assert_svg_representations(art,name,source,logical)
            frames,metadata = representations(density_probe,source,directory,logical)
            resources[relative] = dict(name=name,source=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),metadata=metadata)
            images[name] = frames
    with headless_session(compositor,artifacts/'native',application.parent.parent) as (env,command):
        with pasteboard_storage(pasteboard_server,pasteboard_probe,env,artifacts/'native') as storage:
            arguments = [str(application),'-GSBackend','libgnustep-wayland','-GSTheme',str(theme),'-NSUseRunningCopy','NO','-Shell','/bin/sh','-LoginShell','NO']
            (artifacts/'command.json').write_text(json.dumps(arguments,indent=2)+'\n')
            with (artifacts/'application.log').open('w') as log:app = subprocess.Popen(arguments,env=env,stdout=log,stderr=log)
            children = [];cases = [];footer_cases = []
            try:
                def ready():
                    assert app.poll() is None,(artifacts/'application.log').read_text()[-8000:]
                    return any(w['pid']==app.pid and w['width']>300 for w in command('windows'))
                until(ready,'native Terminal startup',timeout=30)

                def query(kind,directory,position=None):
                    result = subprocess.run([str(probe),'--terminal-animation',kind,*([str(position)] if position is not None else [])],env=env,capture_output=True,text=True,timeout=15)
                    (directory/'query.log').write_text(result.stdout+result.stderr)
                    assert result.returncode == 0,result.stderr
                    return json.loads(result.stdout)

                assert query('start',artifacts)['started']
                until(lambda: query('program',artifacts)['running'],'owned foreground sleep job')
                initial = {kind:query(kind,artifacts) for kind in ('output','mach')}
                target = command('outputs')[0]
                for index,density in enumerate((120,150,180,210,240)):
                    sample = artifacts/str(density);sample.mkdir()
                    assert command(f"test-scale {target['name']} {density} 10000")['ok'] and command('confirm')['ok']
                    for kind,name in (('mach','ScrollingMach'),('output','ScrollingOutput')):
                        directory = sample/kind;directory.mkdir()
                        window_id = initial[kind]['window']
                        def current(): return next(w for w in command('windows') if w['pid']==app.pid and w['client_id']==window_id)
                        assert command(f"move {current()['id']} {target['x']+20} {target['y']+20}")['ok']
                        path = Path(env['NEXTSPACE_WAYLAND_CAPTURE_DIR'])/f'window-{window_id}-{density}.png'
                        previous = None

                        def captured():
                            assert app.poll() is None
                            window = current()
                            if window['preferred_scale'] != density: return False
                            try:
                                with Image.open(path) as image:full = image.convert('RGBA')
                            except OSError: return False
                            expected = tuple((window[k]*density+60)//120 for k in ('width','height'))
                            if previous is not None and full.tobytes()==previous.tobytes(): return False
                            return (window,full) if full.size==expected==(window['buffer_width'],window['buffer_height']) else False

                        path.unlink(missing_ok=True);query(kind,directory,-1)
                        window,background = until(captured,'static Terminal icon background')
                        background.save(directory/'background.png')
                        previous = background
                        for frame,source_y in enumerate((12,11,10,9,8,7,6,12)):
                            output = directory/str(frame);output.mkdir();path.unlink(missing_ok=True)
                            state = query(kind,output,(0,11,10,9,8,7,6,5)[frame])
                            assert state['source_y']==source_y and state['next_position']==source_y-1
                            assert state['animates']==(frame!=7) and state['program_running']
                            assert state['mini']==(kind=='output') and state['destination'][2:]==[27,23]
                            installed = application.parent/'Resources'/(name+'.tiff')
                            # initWithContentsOfFile expands the representations and
                            # may discard NSImage's filename. Pixels prove the binding.
                            if state['resource']: assert Path(state['resource']).resolve()==installed.resolve()
                            assert state['representations']==[list(image.size) for image in images[name]]
                            window,full = until(captured,'actual Terminal animation frame');assert not window['legacy'];full.save(output/'window.png')
                            (output/'case.json').write_text(json.dumps(dict(state=state,window=window),indent=2)+'\n')
                            comparison = compare_frame(images[name][index],state,window,background,full,density,output)
                            cases.append(dict(kind=kind,scale=density,frame=frame,state=state,window=window,comparison=comparison))
                            previous = full
                    footer_directory = sample/'footer';footer_directory.mkdir()
                    def query_footer():
                        value = subprocess.run([str(probe),'--application-footer','Terminal'],env=env,
                            capture_output=True,text=True,timeout=15)
                        (footer_directory/'query.log').write_text(value.stdout+value.stderr)
                        assert value.returncode==0,value.stderr
                        return json.loads(value.stdout)
                    footer = query_footer()
                    def footer_window():return next(w for w in command('windows') if w['pid']==app.pid and w['client_id']==footer['window'])
                    assert command(f"move {footer_window()['id']} {target['x']+20} {target['y']+20}")['ok']
                    path = Path(env['NEXTSPACE_WAYLAND_CAPTURE_DIR'])/f"window-{footer['window']}-{density}.png"
                    path.unlink(missing_ok=True);footer = query_footer()
                    def captured_footer():
                        assert app.poll() is None
                        window = footer_window()
                        if window['preferred_scale']!=density:return False
                        try:
                            with Image.open(path) as image:full = image.convert('RGBA')
                        except OSError:return False
                        expected = tuple((window[k]*density+60)//120 for k in ('width','height'))
                        return (window,full) if full.size==expected==(window['buffer_width'],window['buffer_height']) else False
                    window,full = until(captured_footer,'actual Terminal credit image');assert not window['legacy']
                    full.save(footer_directory/'window.png')
                    installed = [Path(item['source']) for item in resources.values() if item['name']=='DWG']
                    if footer['resource']:assert Path(footer['resource']).resolve() in [p.resolve() for p in installed]
                    # Decoding NSImage from Gorm may discard its filename.
                    # The native representation sizes and live pixels still
                    # prove the binding to the installed credit resource.
                    reference_view = dict(footer,resource=str(installed[0]))
                    (footer_directory/'case.json').write_text(json.dumps(dict(state=footer,window=window),indent=2)+'\n')
                    comparison = compare_icon(art,images['DWG'][index],'DWG',reference_view,window,full,density,footer_directory/'image',scan_aligned=True)
                    footer_cases.append(dict(scale=density,state=footer,window=window,comparison=comparison,
                        reference_source=str(installed[0]),filename_retained=bool(footer['resource'])))
                (artifacts/'runtime.json').write_text(json.dumps(process_runtime(app.pid),indent=2)+'\n')
                (artifacts/'maps.txt').write_text(Path(f'/proc/{app.pid}/maps').read_text())
                pending = [app.pid];seen = set()
                while pending:
                    pid = pending.pop()
                    for task in Path(f'/proc/{pid}/task').iterdir():
                        for child in map(int,(task/'children').read_text().split()):
                            if child not in seen:seen.add(child);pending.append(child);children.append(process_runtime(child))
                assert {Path(child['executable']).name for child in children}=={Path('/bin/sh').resolve().name,'sleep'}
                (artifacts/'children.json').write_text(json.dumps(children,indent=2)+'\n')
            except BaseException:
                capture_process_failure(app,artifacts,'failure-application');raise
            finally:
                if app.poll() is None:app.terminate();app.wait(timeout=5)
                until(lambda: all(not Path('/proc',str(child['pid'])).exists() for child in children),'owned Terminal jobs exit')
    assert len(cases)==80 and len(footer_cases)==5
    result = dict(passed=True,cases=cases,footer_cases=footer_cases,resources=resources,native_animation_comparisons=len(cases),
        native_footer_comparisons=len(footer_cases),resource_representation_selections=25,
        info_panel_and_real_miniwindow=True,owned_pasteboard_pid=storage.pid,owned_pasteboard_reaped=storage.poll() is not None,
        owned_terminal_children_reaped=True,terminal_returncode=app.returncode,
        positions_pinned_for_capture=True,info_timers_paused_for_capture=True,
        full_current_source_build=False,full_package_lifecycle_qualified=False,full_plan_complete=False)
    (artifacts/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'Terminal artwork: {len(cases)} animation frames, five footer comparisons and real active miniwindow PASS')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    names = ('compositor','application','probe','density-probe','pasteboard-server','pasteboard-probe','artifacts')
    for name in names:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--theme',type=Path,default=Path('NextSpace'));args = parser.parse_args()
    run(*(getattr(args,n.replace('-','_')).resolve() for n in names),theme=args.theme)
