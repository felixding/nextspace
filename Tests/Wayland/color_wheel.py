"""Check the shared color wheel's native input, cache density and scale changes."""
import colorsys
import json
import math
from pathlib import Path
from PIL import Image
from application_artwork import placed_reference
from integration import until
from color_panel import color_panel


def check_cache(path, wheel, density):
    """Independently evaluate HSV and alpha in every actual cache pixel."""
    factor=density/120;width,height=wheel['base'][2:]
    with Image.open(path) as image:actual=image.convert('RGBa')
    assert actual.size==(math.ceil(width*factor),math.ceil(height*factor))
    cx,cy=width*factor/2,height*factor/2;radius=(min(width,height)/2-2)*factor
    pixels=[];maximum=0
    for y in range(actual.height):
        for x in range(actual.width):
            dx,dy=x-cx,cy-y;distance=math.hypot(dx,dy)
            alpha=max(0,min(1,radius-distance+.5))
            rgb=colorsys.hsv_to_rgb(math.atan2(dy,dx)/(2*math.pi)%1,
                                   min(1,distance/radius),wheel['brightness'])
            expected=tuple(int(v*alpha*255) for v in rgb)+(int(alpha*255),)
            maximum=max(maximum,max(abs(a-b) for a,b in zip(actual.getpixel((x,y)),expected)))
            pixels.append(expected)
    assert maximum<=1,maximum
    reference=Image.new('RGBa',actual.size);reference.putdata(pixels)
    return reference.convert('RGBA'),dict(pixels=actual.width*actual.height,maximum_channel_difference=maximum)


def check_native(actual, reference, wheel, window, density, crop, artifacts):
    """Check native interior colors separately from fractional edge coverage."""
    factor=density/120;x,y,width,height=wheel['base'];left,top,right,bottom=crop
    actual=actual.crop(crop);origin=(x*factor-left,(window['height']-y-height)*factor-top)
    expected=placed_reference(reference,origin,Image.new('RGBA',actual.size,actual.getpixel((0,0))),
                              artifacts,density,size=(width*factor,height*factor))
    radius=(min(width,height)/2-2)*factor;cx,cy=width*factor/2,height*factor/2
    marker_x=cx+math.cos(wheel['hue']*2*math.pi)*wheel['saturation']*radius+origin[0]
    marker_y=cy-math.sin(wheel['hue']*2*math.pi)*wheel['saturation']*radius+origin[1]
    maximum=0;count=0
    for y in range(actual.height):
        for x in range(actual.width):
            if math.hypot(x-origin[0]-cx,y-origin[1]-cy)>radius-3*factor:continue
            if abs(x-marker_x)<4*factor and abs(y-marker_y)<4*factor:continue
            maximum=max(maximum,max(abs(a-b) for a,b in zip(actual.getpixel((x,y)),expected.getpixel((x,y)))))
            count+=1
    assert count>10000 and maximum<=2,(count,maximum)
    return dict(pixels=count,maximum_channel_difference=maximum,excludes_marker_and_edge_coverage=True)


def run(compositor, application, probe, artifacts, baseline=False):
    cases=[]
    with color_panel(compositor,application,probe,artifacts) as panel:
        command=panel.command
        for index,density in enumerate((120,150,180,210,240,120)):
            for output in command('outputs'):
                assert command(f"test-scale {output['name']} {density} 10000")['ok'] and command('confirm')['ok']
            output=command('outputs')[0];w=panel.window()
            assert command(f"move {w['id']} {output['x']+100} {output['y']+100}")['ok']
            w,_=until(lambda:panel.captured(density),'Shared color panel backing density')
            meta=panel.controls();wheel,=meta['wheels'];slider,=meta['sliders']
            panel.click(slider['base'],dy=.99)
            until(lambda:panel.controls()['wheels'][0]['brightness']>.95,'Native brightness slider changes the wheel')
            panel.click(wheel['base'],dx=.75,dy=.5)
            meta=panel.controls();wheel,=meta['wheels']
            assert wheel['saturation']>.4 and wheel['brightness']>.95
            width,height=wheel['base'][2:];factor=1 if baseline else density/120
            expected=[[math.ceil(width*factor),math.ceil(height*factor)]]
            meta=until(lambda:(m if (m:=panel.controls())['wheels'][0]['representations']==expected else None),
                       'Color wheel cache matches its rendering density')
            # Sampling an interior point waits for the native color change,
            # rather than accepting the previous black wheel submission.
            x,y,width,height=wheel['base']
            def painted():
                value=panel.captured(density)
                if not value:return False
                current,pixels=value
                sample=(int((x+width*.65)*density/120),int((current['height']-y-height*.5)*density/120))
                r,g,b,a=pixels.getpixel(sample)
                return value if r>240 and r>g+30 and abs(g-b)<12 else False
            w,pixels=until(painted,'Native color wheel submits its selected brightness')
            panel.query(artifacts/f'cache-{index}-{density}.tiff')
            pixels.save(artifacts/f'panel-{index}-{density}.png')
            left=math.floor(x*density/120);top=math.floor((w['height']-y-height)*density/120)
            right=math.ceil((x+width)*density/120);bottom=math.ceil((w['height']-y)*density/120)
            pixels.crop((left,top,right,bottom)).save(artifacts/f'wheel-{index}-{density}.png')
            reference,cache_check=check_cache(artifacts/f'cache-{index}-{density}.tiff',wheel,120 if baseline else density)
            native_check=None if baseline else check_native(pixels,reference,wheel,w,density,
                (left,top,right,bottom),artifacts)
            cases.append(dict(scale=density,window=w,wheel=meta['wheels'][0],crop=[left,top,right,bottom],
                              slider=meta['sliders'][0],cache_check=cache_check,native_check=native_check,baseline=baseline))
    result=dict(passed=True,cases=cases,application_runtime=panel.runtime,
                normal_keyboard_quit=panel.normal_keyboard_quit,
                all_processes_reaped=panel.app.poll() is not None,baseline=baseline,full_plan_complete=False)
    (artifacts/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Shared color wheel: six native density/input cases and normal quit PASS.')
    return result
