"""Default UA sizes, CSS constraints and independent original native pixels."""
import argparse
import json
import re
import sys
import time
from native_date_fields import FirefoxDates


def run(t):
    t.until(lambda:t.js('normal.getBoundingClientRect().height')>10,'original native auto height')
    original=t.js('normal.getBoundingClientRect().height')
    for name in ['normal','empty','readonly','disabled','clock','stamp']:
        t.check(name+'-auto-size-has-native-height',t.js(name+'.getBoundingClientRect().height')>=original)
    for name,height in [('minimum',48),('maximum',10),('explicit',30)]:
        t.check(name+'-preserves-original-css-height',t.js('parseFloat(getComputedStyle('+name+').height)')==height)
    t.js('normal.style.height="40px"')
    t.check('style-height-update-remains-engine-owned',t.js('parseFloat(getComputedStyle(normal).height)')==40)
    t.js('normal.style.height=""')
    t.check('clearing-style-restores-native-auto-height',t.js('normal.getBoundingClientRect().height')==original)
    t.js('document.activeElement.blur()')
    assert t.command('pointer 1500 1100')['ok']
    time.sleep(.15)
    for name,elements,flags in [('normal',2,20),('empty',2,28),('readonly',2,20),('disabled',2,20),('clock',4,52),('stamp',5,20)]:
        model=t.js('(()=>{let e='+name+';return {box:e.getBoundingClientRect().toJSON(),enabled:!e.disabled&&!e.readOnly,value:e.type==="datetime-local"?Date.parse(e.value+"Z"):e.valueAsNumber}})()')
        field=dict(id=name,kind=17,title='',state=0,width=model['box']['width'],height=model['box']['height'],
                   enabled=model['enabled'],date_flags=flags,date_elements=elements,date_style=0,date_value=(model['value'] or 0)/1000)
        t.component_pixels(name,field,model['box'],'default-date')
    # An integral width at a fractional origin and a fractional default number
    # width must use the engine's actual device-pixel viewport.
    geometry=t.until(lambda:re.findall(r'native-number id=\d+ stepper=\d+ rect=([\d.]+),([\d.]+) ([\d.]+)x([\d.]+)',(t.root/'hook.log').read_text()),'default native number paint')
    x,y,width,height=map(float,geometry[-1])
    box=t.js('number.getBoundingClientRect().toJSON()')
    for field,offset in [
        (dict(id='default-number-editor',kind=7,title='',state=0,width=x,height=round(box['height']),enabled=True,editable=True,text='12'),(0,0)),
        (dict(id='default-number-stepper',kind=15,title='',state=0,width=width,height=height,enabled=True,minimum=-sys.float_info.max,maximum=sys.float_info.max,value=0),(x,y))]:
        area=dict(x=box['x']+offset[0],y=box['y']+offset[1])
        t.component_pixels(field['id'],field,area,'default-number')
    t.js('window.events=[]')
    for event in [f"pointer {round(t.origin[0]+box['x']+x+width/2)} {round(t.origin[1]+box['y']+y+height/4)}",'button 272 1','button 272 0']:
        assert t.command(event)['ok'];time.sleep(.1)
    t.check('default-native-stepper-edits-original-model',t.until(lambda:t.js('number.value')=='13','default native number increment'))
    t.check('default-number-keeps-original-trusted-events',t.js('events')==[
        dict(id='number',type=kind,trusted=True) for kind in ['input','change']])
    t.js('normal.focus();window.events=[]');t.key(103)
    t.check('default-native-date-editor-updates-original-model',t.js('normal.value')=='2026-12-10')
    t.check('default-date-keeps-original-trusted-events',t.js('events')==[
        dict(id='normal',type=kind,trusted=True) for kind in ['input','change']])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True);p.add_argument('--port',required=True,type=int);a=p.parse_args()
    t=FirefoxDates(a.root,a.port,'native-default-control-fields.html','Native default controls')
    try:run(t)
    finally:
        (t.root/'default-controls-checks.json').write_text(json.dumps(t.results,indent=2)+'\n')
        t.close()
