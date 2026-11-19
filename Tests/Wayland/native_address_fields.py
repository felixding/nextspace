"""Physical native editing in the original browsers' address models."""
import argparse
import json
import math
from pathlib import Path
import time
from native_density_controls import DensityFixture

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--root',required=True)
p.add_argument('--firefox-port',type=int)
p.add_argument('--scale',type=float,default=2)
a=p.parse_args()
t=DensityFixture(a.root,'firefox' if a.firefox_port else 'chromium',a.firefox_port or 9293,
                 expected_scale=a.scale,report='address-field-checks.json')
complete=False

def chrome_js(script):
    return t.driver.command('WebDriver:ExecuteScript',dict(script=script,args=[]))['value']

def state():
    if a.firefox_port:
        return chrome_js('let e=gURLBar.inputField;return {value:e.value,start:e.selectionStart,end:e.selectionEnd,focused:document.activeElement===e}')
    records=[line for line in (t.root/'hook.log').read_text().splitlines() if line.startswith('views-state ')]
    if not records:return None
    r=dict(item.split('=',1) for item in records[-1].split()[1:])
    return dict(value=bytes.fromhex(r['value_hex']).decode(),start=int(r['start']),end=int(r['end']),
                focused=bool(int(r['focused'])),**{k:int(r[k]) for k in ('x','y','width','height')})

def check(name,**expected):
    current=None
    def matches():
        nonlocal current
        current=state()
        return current and all(current[k]==v for k,v in expected.items())
    try:ok=t.until(matches,name)
    except AssertionError:
        (t.root/'address-field-failure.json').write_text(json.dumps(dict(case=name,expected=expected,actual=current),indent=2)+'\n')
        raise
    t.check(name,ok)

def type_text(value):
    codes=dict(zip('qwertyuiop',[16,17,18,19,20,21,22,23,24,25]))
    codes.update(zip('asdfghjkl',[30,31,32,33,34,35,36,37,38]))
    codes.update(zip('zxcvbnm',[44,45,46,47,48,49,50]))
    codes.update({' ':57,':':39,'/':53,'.':52,'-':12,'?':53,'=':13})
    for c in value:
        shift=c.isupper() or c in ':?'
        if shift:assert t.command('key 42 1')['ok']
        try:t.key(codes[c.lower()])
        finally:
            if shift:assert t.command('key 42 0')['ok']

def firefox_native_image(label='native-address',focused=True):
    from PIL import Image,ImageChops
    # Screencopy includes the pointer sprite and its shadow. Keep it outside
    # the complete native field, as the page-control image checks already do.
    assert t.command('pointer 1500 1100')['ok']
    box=chrome_js('let e=gURLBar.inputField;return {rect:e.getBoundingClientRect().toJSON(),value:e.value,start:e.selectionStart,end:e.selectionEnd,origin:[mozInnerScreenX,mozInnerScreenY],mask:getComputedStyle(e).maskImage,overflow:gURLBar.getAttribute("textoverflow")}')
    if not focused:
        assert box['value'].startswith('file:///workspace/Tests/Wayland/native-density-controls.html'),box
        assert box['overflow'] in ('left','right','both'),box
    rect=box['rect'];scale=t.scale
    model=dict(id='address',title='',state=0,kind=7,enabled=True,editable=True,
        width=round(rect['width']*60)/60,height=round(rect['height']*60)/60,scale=scale,
        text=box['value'],selection_start=box['start'],selection_length=box['end']-box['start'])
    reply=t.command('reference '+json.dumps(dict(name=label+'-reference',controls=[model],focus=focused)),timeout=60)
    image=Image.open(Path(reply['path'])/'address.png').convert('RGBA')
    expected=Image.new('RGBA',image.size,'white');expected.alpha_composite(image);expected=expected.convert('RGB')
    expected.save(t.root/(label+'-expected.png'))
    assert t.command('focus '+str(t.window['id']))['ok']
    deadline=time.monotonic()+10;matched=False
    while True:
        shot=t.command('capture '+t.command('outputs')[0]['name']);event=shot['event']
        desktop=Image.frombytes('RGB',(event['width'],event['height']),Path(shot['path']).read_bytes(),'raw','BGRX',event['stride'])
        left=(box['origin'][0]+rect['x'])*scale;top=(box['origin'][1]+rect['y'])*scale
        for y in range(math.floor(top)-1,math.ceil(top)+2):
            for x in range(math.floor(left)-1,math.ceil(left)+2):
                actual=desktop.crop((x,y,x+expected.width,y+expected.height));difference=ImageChops.difference(actual,expected)
                if difference.getbbox() is None:matched=True;break
            if matched:break
        if matched or time.monotonic()>=deadline:break
        time.sleep(.1)
    actual.save(t.root/(label+'-actual.png'));difference.save(t.root/(label+'-diff.png'))
    (t.root/(label+'-image.json')).write_text(json.dumps(dict(complete=matched,box=box,expected_size=list(expected.size),difference=difference.getbbox()),indent=2)+'\n')
    t.check(label+'-complete-field-image',matched)

try:
    if a.firefox_port:t.driver.command('Marionette:SetContext',dict(value='chrome'))
    t.chord(38,29)  # Original browser command focuses its original address model.
    check('original-address-model-focused',focused=True)
    if a.firefox_port:
        # The initial valid, overflowing URL exercises Firefox's original
        # unfocused mask; an uncommitted short search draft would not.
        t.key(1)
        t.driver.command('Marionette:SetContext',dict(value='content'))
        box=t.js('document.getElementById("text").getBoundingClientRect().toJSON()')
        t.point(box,10,8);t.button(1);t.button(0)
        t.driver.command('Marionette:SetContext',dict(value='chrome'))
        check('original-address-model-blurred-by-page-click',focused=False)
        firefox_native_image('native-address-unfocused',focused=False)
        box=chrome_js('let e=gURLBar.inputField;return {rect:e.getBoundingClientRect().toJSON(),origin:[mozInnerScreenX,mozInnerScreenY]}')
        x=(box['origin'][0]+box['rect']['x']+12)*t.scale/t.output_scale
        y=(box['origin'][1]+box['rect']['y']+box['rect']['height']/2)*t.scale/t.output_scale
        assert t.command(f'pointer {round(x)} {round(y)}')['ok']
        t.button(1);t.button(0)
        check('native-address-refocused-by-physical-click',focused=True)
    t.chord(30,56)
    type_text('Alpha beta')
    check('native-typing-updates-original-address-model',value='Alpha beta',start=10,end=10)
    t.chord(30,56)
    check('native-address-select-all',value='Alpha beta',start=0,end=10)
    t.chord(46,56)
    t.chord(30,29)
    check('native-address-emacs-beginning',value='Alpha beta',start=0,end=0)
    t.chord(18,29)
    check('native-address-emacs-end',value='Alpha beta',start=10,end=10)
    t.chord(30,29);t.chord(37,29)
    check('native-address-emacs-kill',value='',start=0,end=0)
    t.chord(44,56)
    check('native-address-undo-original-history',value='Alpha beta')
    assert t.command('key 42 1')['ok']
    try:t.chord(44,56)
    finally:assert t.command('key 42 0')['ok']
    check('native-address-redo-original-history',value='')
    t.chord(47,56)
    check('native-address-system-clipboard-paste',value='Alpha beta',start=10,end=10)
    # Leave a stable selection for an actual compositor capture, including the
    # surrounding original tabs and toolbar buttons for scope inspection.
    t.chord(30,56);check('native-address-final-selection',start=0,end=10)
    if a.firefox_port:
        firefox_native_image()
        width=chrome_js('return outerWidth')
        t.driver.command('WebDriver:SetWindowRect',dict(width=width-40))
        t.until(lambda:chrome_js('return outerWidth')<width,'original address viewport resized')
        t.chord(38,29);t.chord(30,56)
        firefox_native_image('native-address-resized')
    shot=t.command('capture '+t.command('outputs')[0]['name'])
    from PIL import Image
    e=shot['event'];Image.frombytes('RGB',(e['width'],e['height']),Path(shot['path']).read_bytes(),
                                   'raw','BGRX',e['stride']).save(t.root/'native-address-desktop.png')
    complete=True
finally:
    (t.root/'address-field-status.json').write_text(json.dumps(dict(complete=complete,checks=t.results),indent=2)+'\n')
    # Keep the captured address trial intact, then dismiss its original
    # autocomplete popup before the next page-control trial shares this seat.
    if complete:t.key(1)
    if a.firefox_port:t.driver.close()
