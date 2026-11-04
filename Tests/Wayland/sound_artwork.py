#!/usr/bin/env python3
"""Compare real Sound Mixer image views with vector-derived resources."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
from PIL import Image, ImageChops, ImageFilter
from application_artwork import placed_reference, representations
from artwork_reference import artwork_original
from gnustep import headless_session, process_runtime
from integration import until


def run(compositor, application, probe, density_probe, artifacts):
    artifacts.mkdir(parents=True)
    source=Path(__file__).resolve().parents[2]
    layout_path=source/'Tests/Wayland/artwork-originals/sound-mixer-layout.json'
    layout=json.loads(layout_path.read_text())
    for name,expected in layout['gorm_source_hashes'].items():
        assert hashlib.sha256((source/name).read_bytes()).hexdigest()==expected, name
    original_bounds={name:artwork_original('sound_controls',name)[0].getchannel('A').getbbox()
        for name in ('volMute','volLoud','micMute','micLoud')}
    resources=application.parent/'Resources/Sound.preferences/Resources'
    images={name:representations(density_probe,resources/(name+'.tiff'),artifacts,(36,36))
        for name in ('volMute','volLoud','micMute','micLoud')}
    with headless_session(compositor,artifacts,application.parent.parent) as (env,command):
        env['PULSE_SERVER']='unix:'+env['XDG_RUNTIME_DIR']+'/absent-audio-server'
        with (artifacts/'application.log').open('w') as log:
            app=subprocess.Popen([str(application),'-GSBackend','libgnustep-wayland','-GSTheme','NextSpace'],env=env,stdout=log,stderr=log)
        try:
            until(lambda:any(w['pid']==app.pid and w['width']>300 for w in command('windows')),'Preferences startup',timeout=20)
            paths=sorted({line.split()[-1] for line in Path(f'/proc/{app.pid}/maps').read_text().splitlines() if '.preferences/' in line.split()[-1]})
            (artifacts/'loaded-modules.json').write_text(json.dumps(paths,indent=2)+'\n')
            (artifacts/'application-runtime.json').write_text(json.dumps(process_runtime(app.pid),indent=2)+'\n')
            assert str((resources.parent/'Sound').resolve()) in paths, paths
            target=command('outputs')[0];records=[];state=None
            def query(mode,directory):
                result=subprocess.run([str(probe),'--preferences-mixer',*([] if mode=='initial' else [str(mode)])],env=env,capture_output=True,text=True,timeout=15)
                (directory/'query.log').write_text(result.stdout+result.stderr);assert result.returncode==0,result.stderr
                return json.loads(result.stdout)
            for at,density in enumerate((120,150,180,210,240)):
                assert command(f"test-scale {target['name']} {density} 10000")['ok'] and command('confirm')['ok']
                for mode in (('initial',0,1) if at==0 else (0,1)):
                    directory=artifacts/f'{density}-{mode}';directory.mkdir()
                    if state is None:state=query(mode,directory)
                    def window():return next(w for w in command('windows') if w['pid']==app.pid and w['client_id']==state['window'])
                    assert command(f"move {window()['id']} {target['x']+10} {target['y']+10}")['ok']
                    path=artifacts/'captures'/f"window-{state['window']}-{density}.png";path.unlink(missing_ok=True)
                    state=query(mode,directory);assert state['mode']==(0 if mode=='initial' else mode)
                    def captured():
                        assert app.poll() is None
                        w=window()
                        if w['preferred_scale']!=density or w['buffer_width']!=(w['width']*density+60)//120:return False
                        try:
                            with Image.open(path) as image:actual=image.convert('RGBA')
                        except OSError:return False
                        return (w,actual) if actual.size==(w['buffer_width'],w['buffer_height']) else False
                    w,actual=until(captured,'native Mixer buffer');actual.save(directory/'window.png');assert not w['legacy']
                    assert len(state['images'])==4;comparisons=[]
                    for view in state['images']:
                        expected_layout={key:value for key,value in layout['views'][view['key']].items() if key!='logical'}
                        assert {key:view[key] for key in expected_layout}==expected_layout, ('Original Mixer layout changed',view)
                        name=('vol' if state['mode']==0 else 'mic')+('Mute' if 'Mute' in view['key'] else 'Loud')
                        frames,metadata=images[name];assert view['logical']==[36,36]
                        assert view['representations']==[[r['width'],r['height']] for r in metadata['representations']]
                        assert view['alignment']==0
                        x,y,width,height=view['base'];assert (width,height)==(36,36)
                        # NSImageCell uses centerScanRect to align its image to
                        # backing pixels before drawing the selected density.
                        factor=density/120;origin=tuple(math.floor(value+.5) for value in (x*factor,(w['height']-y-height)*factor));left,top=map(math.floor,origin)
                        vx,vy,vw,vh=view['visible']
                        clip=(vx*factor-left,(w['height']-vy-vh)*factor-top,vw*factor,vh*factor)
                        ink_box=frames[at].getchannel('A').getbbox();assert ink_box is not None
                        def fits(box):
                            return (box[0]>=((vx-x)*factor)-.00001 and box[2]<=((vx+vw-x)*factor)+.00001
                                and box[1]>=((y+height-vy-vh)*factor)-.00001 and box[3]<=((y+height-vy)*factor)+.00001)
                        original_fits=fits(tuple(value*factor for value in original_bounds[name]))
                        assert fits(ink_box)==original_fits, ('New Mixer clipping',mode,view,ink_box)
                        size=(math.ceil(width*factor+origin[0]-left),math.ceil(height*factor+origin[1]-top))
                        crop=actual.crop((left,top,left+size[0],top+size[1]));control=directory/view['key'];control.mkdir();crop.save(control/'actual.png')
                        opacity=.5 if not view['enabled'] and view['frame_style']==0 else 1
                        expected=placed_reference(frames[at],(origin[0]-left,origin[1]-top),Image.new('RGBA',size,crop.getpixel((0,0))),control,density,size=(width*factor,height*factor),pad=True,opacity=opacity,clip=clip)
                        expected.save(control/'expected.png')
                        # Gorm places neighboring controls over the image view's
                        # transparent padding. Compare the entire symbol and a
                        # one-pixel halo, retaining native disabled opacity.
                        mask_dir=control/'mask';mask_dir.mkdir()
                        ink=placed_reference(frames[at],(origin[0]-left,origin[1]-top),Image.new('RGBA',size),mask_dir,density,size=(width*factor,height*factor),pad=True,clip=clip).getchannel('A')
                        mask=ink.point(lambda value:255 if value else 0).filter(ImageFilter.MaxFilter(3));mask.save(control/'mask.png')
                        difference=Image.composite(ImageChops.difference(crop,expected),Image.new('RGBA',size),mask)
                        maximum=max(pair[1] for pair in difference.getextrema())
                        assert maximum<=1,(density,mode,view['key'],maximum)
                        comparisons.append(dict(key=view['key'],resource=name,maximum_channel_difference=maximum,opacity=opacity,symbol_and_halo_pixels=sum(mask.histogram()[1:]),halo_pixels=1,source_ink_fits_visible_rect=fits(ink_box),original_ink_fits_visible_rect=original_fits,original_layout_preserved=True))
                    records.append(dict(scale=density,mode=mode,state=state,window=w,comparisons=comparisons))
            (artifacts/'application-runtime.json').write_text(json.dumps(process_runtime(app.pid),indent=2)+'\n')
            paths=sorted({line.split()[-1] for line in Path(f'/proc/{app.pid}/maps').read_text().splitlines() if '.preferences/' in line.split()[-1]})
            assert str((resources.parent/'Sound').resolve()) in paths
            (artifacts/'loaded-modules.json').write_text(json.dumps(paths,indent=2)+'\n')
            (artifacts/'results.json').write_text(json.dumps(dict(cases=records,resources={name:metadata for name,(_,metadata) in images.items()},original_layout_sha256=hashlib.sha256(layout_path.read_bytes()).hexdigest(),initial_images_refreshed=True,audio_transport_tested=False,missing_audio_server=True,complete=True),indent=2)+'\n')
            print('Sound Mixer: 20 resource selections and 44 symbol-and-halo pixel checks PASS')
        finally:
            if app.poll() is None:app.terminate();app.wait(timeout=5)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('compositor','application','probe','density-probe','artifacts'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();run(*(getattr(args,name).resolve() for name in ('compositor','application','probe','density_probe','artifacts')))
