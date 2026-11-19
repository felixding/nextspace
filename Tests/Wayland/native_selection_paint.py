"""Selection changes must repaint complete native fields without another input.

Build the independent GNUstep reference before the selection stimulus. Unlike
static control comparisons, never blur, move focus, type or click to obtain the
post-selection image: those actions can mask a missing repaint notification.
"""
import argparse,json,math,time
from pathlib import Path
from PIL import Image,ImageChops
from native_density_controls import DensityFixture

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--root',type=Path,required=True)
p.add_argument('--family',choices=('chromium','firefox'),required=True)
p.add_argument('--port',type=int,required=True)
p.add_argument('--scale',type=float,default=2)
a=p.parse_args()
x=DensityFixture(a.root,a.family,a.port,a.scale,report='selection-paint-checks.json')
def edges(value):
    n=round(value)
    return [n] if abs(value-n)<.0001 else list(dict.fromkeys([math.floor(value+.5),math.floor(value),math.ceil(value)]))
try:
    for identifier,kind in [('text',7),('search',14),('password',8),('notes',9)]:
        label=identifier+'-canonical-selection';value='Alpha beta'
        # Keep this notification regression independent of engine auto-size
        # half-point baseline snapping; density fixtures cover intrinsic sizes.
        x.js('(()=>{const e=document.getElementById('+json.dumps(identifier)+');e.style.boxSizing="border-box";e.style.width="300px";e.style.height='+json.dumps('120px' if kind==9 else '24px')+';e.value="Alpha beta";e.scrollIntoView({block:"center"})})()')
        box=x.js('document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()')
        model=dict(id=label,kind=kind,title='',enabled=True,state=0,text=value,
                   width=math.floor(box['width']*x.scale+.5)/x.scale,
                   height=math.floor(box['height']*x.scale+.5)/x.scale,scale=x.scale,
                   selection_start=0,selection_length=len(value),editable=1)
        ref=x.command('reference '+json.dumps(dict(name=label,controls=[model],focus=True)),timeout=60)
        native=Image.open(Path(ref['path'])/(label+'.png')).convert('RGBA')
        expected=Image.new('RGBA',native.size,'white');expected.alpha_composite(native);expected=expected.convert('RGB')
        expected.save(a.root/(label+'-expected.png'))
        # Establish real seat/field focus only before the stimulus.
        x.focus_field(identifier)
        # Park the composited pointer before changing the selection. Moving it
        # afterward would itself cause damage and could hide a repaint bug.
        assert x.command('pointer 1500 1100')['ok']
        time.sleep(.1);x.update_origin()
        box=x.js('document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()')
        x.check(identifier+'-selection-stimulus-starts-in-focused-field',x.js('document.hasFocus()&&document.activeElement.id==='+json.dumps(identifier)))
        x.js('document.getElementById('+json.dumps(identifier)+').select()')
        state=x.js('(()=>{const e=document.getElementById('+json.dumps(identifier)+');return {start:e.selectionStart,end:e.selectionEnd,focused:document.hasFocus()&&document.activeElement===e}})()')
        x.check(identifier+'-engine-canonical-selection-changed',state['focused'] and state['start']==0 and state['end']==len(value))
        lefts=edges(math.floor(x.origin_pixels[0]+.5)+box['x']*x.scale)
        tops=edges(math.floor(x.origin_pixels[1]+.5)+box['y']*x.scale)
        deadline=time.monotonic()+3;matched=False
        while True:
            shot=x.command('capture '+x.command('outputs')[0]['name']);event=shot['event']
            desktop=Image.frombytes('RGB',(event['width'],event['height']),Path(shot['path']).read_bytes(),'raw','BGRX',event['stride'])
            for top in tops:
                for left in lefts:
                    actual=desktop.crop((left,top,left+expected.width,top+expected.height))
                    difference=ImageChops.difference(actual,expected)
                    if difference.getbbox() is None:matched=True;break
                if matched:break
            if matched or time.monotonic()>=deadline:break
            time.sleep(.05)
        actual.save(a.root/(label+'-actual.png'));difference.save(a.root/(label+'-diff.png'))
        (a.root/(label+'-geometry.json')).write_text(json.dumps(dict(box=box,origin=x.origin_pixels,scale=x.scale,viewport=list(expected.size),state=state),indent=2)+'\n')
        x.check(identifier+'-native-selection-background-updates-without-another-input',matched)
    print(json.dumps(dict(complete=True,checks=len(x.results))))
finally:
    if a.family=='firefox':x.driver.close()
