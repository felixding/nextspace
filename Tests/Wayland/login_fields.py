"""Check all reconstructed Login artwork and button states on native Wayland."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from PIL import Image,ImageChops,ImageDraw
from application_artwork import placed_reference
from artwork_reference import artwork_original
from login_greeter import greeter_account,run as greeter
from integration import until



def check_panel_pixels(actual, expected, state, window, directory, scale):
    """Check unobstructed artwork regions using the live image-view placement."""
    x,y,width,height=state['panel_base'];factor=scale/120
    left,top=x*factor,(window['height']-y-height)*factor
    mask=Image.new('1',actual.size);draw=ImageDraw.Draw(mask)
    # Wordmark, cube, separators and the frame have no overlaid UI controls.
    regions=[(105,12,357,70),(192,174,275,256),(3,88,458,91),(3,169,458,172),
        (0,0,462,5),(0,0,5,260),(457,0,462,260),(0,255,462,260)]
    for x0,y0,x1,y1 in regions:
        box=(math.ceil(left+x0*width/462*factor)+1,math.ceil(top+y0*height/260*factor)+1,
            math.floor(left+x1*width/462*factor)-2,math.floor(top+y1*height/260*factor)-2)
        if box[2]>=box[0] and box[3]>=box[1]:draw.rectangle(box,fill=1)
    delta=Image.composite(ImageChops.difference(actual,expected),Image.new('RGBA',actual.size),mask)
    maximum=max(high for low,high in delta.getextrema())
    actual.save(directory/'panel-actual.png');expected.save(directory/'panel-expected.png');mask.save(directory/'panel-mask.png')
    tested=sum(byte.bit_count() for byte in mask.tobytes())
    assert tested>20000,(scale,tested)
    assert maximum<=1,('Login panel artwork',scale,maximum)
    return dict(maximum_channel_difference=maximum,tested_pixels=tested,regions=regions)


def placed_artwork(reference, info, window, background, directory, scale):
    x,y,width,height=info['base'];factor=scale/120
    origin=x*factor,(window['height']-y-height)*factor
    opacity=1 if info.get('enabled',True) or not info.get('dims_when_disabled',True) else .5
    expected=placed_reference(reference,origin,background,directory,scale,
        size=(width*factor,height*factor),pad=True,opacity=opacity)
    box=math.floor(origin[0]),math.floor(origin[1]),math.ceil(origin[0]+width*factor),math.ceil(origin[1]+height*factor)
    return expected,box


def exact_artwork_region(actual, expected, box, directory, name):
    a,b=actual.crop(box),expected.crop(box)
    maximum=max(high for low,high in ImageChops.difference(a,b).getextrema())
    a.save(directory/(name+'-actual.png'));b.save(directory/(name+'-expected.png'))
    assert maximum<=1,(name,maximum,box)
    return dict(maximum_channel_difference=maximum,tested_pixels=a.width*a.height,box=box)

def run(compositor, application, systemkit, workspace_probe, density_probe, artifacts):
    artifacts.mkdir(parents=True)
    systemkit=systemkit.resolve()
    records=[]
    with greeter_account(application,artifacts) as account:
        for density in (120,150,180,210,240):
            directory=artifacts/str(density)
            def check(capture, images, scale, *, env, identity, window, compositor_pid):
                assert 'DISPLAY' not in env and not window.get('legacy'),window
                output=directory/'artwork';output.mkdir()
                if os.geteuid()==0:os.chown(output,account[0],account[1])
                query=subprocess.run([str(workspace_probe),'--login-artwork',str(output)],
                    env=env,capture_output=True,text=True,timeout=20,**identity)
                (directory/'query.log').write_text(query.stdout+query.stderr)
                assert query.returncode==0,query.stderr
                state=json.loads(query.stdout)
                assert len(state['inputs'])==2,state
                (directory/'state.json').write_text(json.dumps(state,indent=2)+'\n')
                assert state['representations']==[[328,63],[410,79],[492,95],[574,110],[656,126]],state
                assert all(math.isclose(a,b,abs_tol=.00001) for a,b in zip(state['logical'],(328,63)))
                assert state['frame_style']==0,state
                buttons=[]
                for name in ('power','restart'):
                    for key,suffix in (('image','up'),('alternateImage','down')):
                        target=output/(name+'-'+key+'.png')
                        result=subprocess.run([str(density_probe),'--image-reference',str(output/(name+'-'+key+'.tiff')),str(target)],
                            env=env,capture_output=True,text=True,timeout=15,**identity)
                        (directory/(name+'-'+key+'.log')).write_text(result.stdout+result.stderr)
                        assert result.returncode==0,result.stderr
                        with Image.open(images/(name+'button'+suffix+'.tiff')) as submitted:
                            submitted.seek(0);reference=submitted.convert('RGBA')
                        with Image.open(target) as actual:assert actual.convert('RGBA').tobytes()==reference.tobytes(),(name,key)
                        buttons.append(dict(button=name,state=key,original=name+'button'+suffix))
                runtime_code='import sys; sys.path.insert(0,'+repr(str(Path(__file__).parent))+'); from gnustep import process_runtime; import json; print(json.dumps([process_runtime(int(pid)) for pid in sys.argv[1:]]))'
                runtime=json.loads(subprocess.check_output([sys.executable,'-c',runtime_code,str(window['pid']),str(compositor_pid)],env=env,text=True,**identity))
                for name,data in zip(('application','compositor'),runtime):
                    (directory/(name+'-runtime.json')).write_text(json.dumps(data,indent=2)+'\n')
                with Image.open(capture) as image:background=image.convert('RGBA')
                with Image.open(images/'Fields.tiff') as image:
                    image.seek((120,150,180,210,240).index(scale));reference=image.convert('RGBA')
                x,y,width,height=state['base'];factor=scale/120
                px,py,pw,ph=state['panel_base']
                with Image.open(images/'Panel.tiff') as image:
                    assert image.n_frames==5, 'Login panel has no high-density artwork'
                    image.seek((120,150,180,210,240).index(scale));panel=image.convert('RGBA')
                backdrop=Image.new('RGBA',background.size,(170,170,170,255))
                backdrop=placed_reference(panel,(px*factor,(window['height']-py-ph)*factor),backdrop,directory,scale,
                    size=(pw*factor,ph*factor),pad=True,
                    clip=(px*factor,(window['height']-py-ph)*factor,pw*factor,ph*factor))
                panel_result=check_panel_pixels(background,backdrop,state,window,directory,scale)
                origin=(x*factor,(window['height']-y-height)*factor)
                expected=placed_reference(reference,origin,backdrop,directory,scale,
                    size=(width*factor,height*factor),pad=True,opacity=1 if state['enabled'] else .5)
                left,top=math.floor(origin[0]),math.floor(origin[1])
                box=(left,top,math.ceil(origin[0]+width*factor),math.ceil(origin[1]+height*factor))
                actual=background.crop(box);expected=expected.crop(box)
                mask=Image.new('1',actual.size,1);draw=ImageDraw.Draw(mask)
                # Text fields and their caret overlay the background image.
                # Their separate rendering checks remain outside this asset test.
                for ix,iy,iw,ih in state['inputs']:
                    bounds=(math.floor(ix*factor)-left-1,math.floor((window['height']-iy-ih)*factor)-top-1,
                        math.ceil((ix+iw)*factor)-left+1,math.ceil((window['height']-iy)*factor)-top+1)
                    draw.rectangle(bounds,fill=0)
                draw.rectangle((0,0,actual.width-1,actual.height-1),outline=0,width=1)
                delta=ImageChops.difference(actual,expected)
                delta=Image.composite(delta,Image.new('RGBA',delta.size),mask)
                maximum=max(high for low,high in delta.getextrema())
                actual.save(directory/'fields-actual.png');expected.save(directory/'fields-expected.png');mask.save(directory/'fields-mask.png')
                assert maximum<=1,(scale,maximum)
                label_info=state['labels']
                assert label_info['representations']==[[115,63],[144,79],[173,95],[201,110],[230,126]],label_info
                assert label_info['logical']==[115,63] and label_info['frame_style']==0,label_info
                with Image.open(images/'FieldNames.tiff') as image:
                    image.seek((120,150,180,210,240).index(scale));label_image=image.convert('RGBA')
                label_expected,label_box=placed_artwork(label_image,label_info,window,backdrop,directory,scale)
                label_result=exact_artwork_region(background,label_expected,label_box,directory,'labels')
                button_cases=[]
                for name in ('power','restart'):
                    info=state['buttons'][name];assert not info['highlighted'] and info['logical']==[48,48],info
                    assert info['image']==info['alternateImage']==[[48,48],[60,60],[72,72],[84,84],[96,96]],info
                    with Image.open(images/(name+'buttonup.tiff')) as image:
                        image.seek((120,150,180,210,240).index(scale));reference=image.convert('RGBA')
                    expected,button_box=placed_artwork(reference,info,window,backdrop,directory,scale)
                    result=exact_artwork_region(background,expected,button_box,directory,name+'-normal')
                    button_cases.append(dict(button=name,highlighted=False,info=info,**result))
                def query_highlight(name,highlighted):
                    output=directory/(name+('-pressed' if highlighted else '-released'));output.mkdir()
                    if os.geteuid()==0:os.chown(output,account[0],account[1])
                    query=subprocess.run([str(workspace_probe),'--login-artwork',str(output),name,str(int(highlighted))],
                        env=env,capture_output=True,text=True,timeout=20,**identity)
                    (output/'query.log').write_text(query.stdout+query.stderr)
                    assert query.returncode==0,query.stderr
                    value=json.loads(query.stdout);(output/'state.json').write_text(json.dumps(value,indent=2)+'\n')
                    return value
                live=directory/'captures'/f"window-{window['client_id']}-{scale}.png"
                try:
                    for name in ('power','restart'):
                        changed=query_highlight(name,True);info=changed['buttons'][name];assert info['highlighted'],info
                        with Image.open(images/(name+'buttondown.tiff')) as image:
                            image.seek((120,150,180,210,240).index(scale));reference=image.convert('RGBA')
                        expected,button_box=placed_artwork(reference,info,window,backdrop,directory,scale)
                        last=[None,None]
                        def displayed():
                            try:
                                with Image.open(live) as image:full=image.convert('RGBA')
                            except OSError:return None
                            delta=ImageChops.difference(full.crop(button_box),expected.crop(button_box))
                            maximum=max(high for low,high in delta.getextrema());last[:]=full,maximum
                            return full if maximum<=1 else None
                        try:full=until(displayed,'native Login '+name+' highlighted image',timeout=10)
                        except Exception:
                            if last[0] is not None:last[0].save(directory/(name+'-pressed-failure.png'))
                            (directory/(name+'-pressed-failure.json')).write_text(json.dumps(dict(info=info,maximum=last[1]),indent=2)+'\n')
                            raise
                        full.save(directory/(name+'-pressed-panel.png'))
                        result=exact_artwork_region(full,expected,button_box,directory,name+'-pressed')
                        button_cases.append(dict(button=name,highlighted=True,info=info,**result))
                finally:
                    restored=query_highlight('all',False)
                    assert not any(info['highlighted'] for info in restored['buttons'].values()),restored
                records.append(dict(scale=scale,window=window,state=state,maximum_channel_difference=maximum,
                    display_unset=True,panel=panel_result,labels=label_result,button_cases=button_cases,
                    tested_pixels=sum(byte.bit_count() for byte in mask.tobytes()),button_assignments=buttons))
            greeter(compositor,application,systemkit,directory,density,False,False,False,
                account=account,artwork_check=check)
    assert len(records)==5
    result=dict(passed=True,native_panel_cases=5,native_field_cases=5,native_label_cases=5,native_button_cases=20,original_button_assignments=20,cases=records,
        full_login_artwork_qualified=True,remaining_login_designs=0,full_plan_complete=False)
    repository=Path(__file__).resolve().parents[2]
    result['test_sources']={str(Path(module.__file__).relative_to(repository)):hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
        for module in sys.modules.values() if getattr(module,'__file__',None) and
        Path(module.__file__).is_relative_to(repository/'Tests/Wayland') and Path(module.__file__).suffix=='.py'}
    result['executables']={str(path):hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (compositor,application,workspace_probe,density_probe)}
    (artifacts/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Real Login: all seven designs, five panel/field/label captures and twenty button states/assignments PASS')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('compositor','application','systemkit','workspace-probe','density-probe','artifacts'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    run(args.compositor.resolve(),args.application.resolve(),args.systemkit.resolve(),
        args.workspace_probe.resolve(),args.density_probe.resolve(),args.artifacts.resolve())
