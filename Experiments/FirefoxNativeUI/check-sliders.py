#!/usr/bin/env python3
"""Qualify actual NSSlider pixels, input and Gecko range semantics."""
import argparse,base64,io,json
from pathlib import Path
from PIL import Image,ImageChops
from marionette import Marionette
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--port',type=int,default=2829);p.add_argument('--expected-pid',type=int,required=True)
p.add_argument('--references',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);results=[];m=Marionette(a.port)
def execute(script):return m.command('WebDriver:ExecuteScript',dict(script=script,args=[]))['value']
def check(case,condition,**details):
    results.append(dict(case=case,passed=bool(condition),**details));(a.output/'results.json').write_text(json.dumps(results,indent=2)+'\n');assert condition,results[-1]
def element(identifier):return next(iter(m.command('WebDriver:FindElement',dict(using='css selector',value='#'+identifier))['value'].values()))
def click(identifier):m.command('WebDriver:ElementClick',dict(id=element(identifier)))
def focus(identifier):execute('document.getElementById('+json.dumps(identifier)+').focus();return true')
def key(value):m.command('WebDriver:PerformActions',dict(actions=[dict(type='key',id='keyboard',actions=[dict(type='keyDown',value=value),dict(type='keyUp',value=value)])]))
def pointer(actions):m.command('WebDriver:PerformActions',dict(actions=[dict(type='pointer',id='mouse',parameters=dict(pointerType='mouse'),actions=actions)]))
def reset():m.command('WebDriver:Refresh')
def crop(identifier):
    rect=execute('return document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()')
    pixels=base64.b64decode(m.command('WebDriver:TakeScreenshot',dict(full=False))['value'])
    x,y,w,h=[round(rect[k]) for k in ('x','y','width','height')]
    return Image.open(io.BytesIO(pixels)).convert('RGB').crop((x,y,x+w,y+h))
def compare(identifier,reference=None,focused=False,label=None):
    label=label or identifier+('-focused' if focused else '-normal')
    rect=execute('return document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()')
    pixels=base64.b64decode(m.command('WebDriver:TakeScreenshot',dict(full=False))['value']);(a.output/(label+'.png')).write_bytes(pixels)
    x,y,w,h=[round(rect[k]) for k in ('x','y','width','height')]
    actual=Image.open(io.BytesIO(pixels)).convert('RGB').crop((x,y,x+w,y+h))
    root=a.references.parent/'focused-references' if focused else a.references
    expected=Image.open(root/((reference or identifier)+'.png')).convert('RGBA');background=Image.new('RGBA',expected.size,'white');background.alpha_composite(expected)
    difference=ImageChops.difference(actual,background.convert('RGB')).getbbox() if actual.size==expected.size else 'size'
    check('native-pixels-'+label,difference is None,difference=difference,actual_size=actual.size,reference_size=expected.size)
def value(identifier):return execute('return document.getElementById('+json.dumps(identifier)+').valueAsNumber')
def changes():return execute('return events.filter(e=>e.type==="input"||e.type==="change")')
def move(identifier,x=0,y=0):return dict(type='pointerMove',origin={'element-6066-11e4-a52e-4f735466cecf':element(identifier)},x=x,y=y,duration=0)
try:
    session=m.command('WebDriver:NewSession',{});assert session['capabilities']['moz:processID']==a.expected_pid
    (a.output/'session.json').write_text(json.dumps(session,indent=2)+'\n')
    check('owned-fixture',m.command('WebDriver:GetTitle')['value']=='Gecko native range transport')
    m.command('WebDriver:SetWindowRect',dict(width=900,height=850))
    for identifier in ('normal','coarse','custom','disabled','vertical','locked'):compare(identifier)
    native_models={r['id']:r for r in json.loads((a.references/'results.json').read_text())}
    for identifier in ('normal','coarse','custom','vertical','locked'):
        reset();focus(identifier);compare(identifier,focused=True)
        for code,expected in zip(('\ue014','\ue011','\ue010','\ue00f'),native_models[identifier]['keys']):
            key(code);check('native-key-model-'+identifier+'-'+expected['key'],value(identifier)==expected['value'],value=value(identifier),expected=expected['value'])
    reset();focus('normal');key('\ue014')
    check('trusted-key-input-change',[e['type'] for e in changes()]==['input','change'] and all(e['trusted'] for e in changes()))
    key('\ue004');check('native-next-focus',execute('return document.activeElement.id')=='coarse')
    reset();focus('normal');execute('document.getElementById("normal").addEventListener("keydown",event=>event.preventDefault());return true');key('\ue014')
    check('page-cancels-native-key',value('normal')==25 and not changes())
    reset();execute('document.getElementById("normal").value=75;return true');compare('normal','updated',label='programmatic-model')
    check('programmatic-no-input-change',not changes())
    reset();click('disabled');check('disabled-no-action',value('disabled')==35 and not changes())
    reset();pointer([move('normal',-50),dict(type='pointerDown',button=0)])
    pressed_value=value('normal')
    pointer([move('normal',40)])
    check('continuous-engine-input',value('normal')!=25 and value('normal')!=pressed_value and any(e['type']=='input' and e['trusted'] for e in changes()) and not any(e['type']=='change' for e in changes()),pressed_value=pressed_value,value=value('normal'),events=changes())
    pointer([dict(type='pointerUp',button=0)])
    check('trusted-drag-commit',any(e['type']=='change' and e['trusted'] for e in changes()))
    trace=[json.loads(line) for line in (a.output.parent/'native.jsonl').read_text().splitlines()]
    native=next(e['value'] for e in reversed(trace) if e['event']=='native-form-action' and e['kind']==4)
    expected=execute('let copy=document.getElementById("normal").cloneNode();copy.value='+json.dumps(str(native))+';return copy.valueAsNumber')
    check('native-value-uses-engine-sanitizer',value('normal')==expected,value=value('normal'),native=native,expected=expected)
    reset();focus('normal');execute('document.getElementById("normal").addEventListener("input",event=>event.target.replaceWith(event.target.cloneNode()));return true');key('\ue014')
    check('input-handler-replaces-frame',value('normal')==native_models['normal']['keys'][0]['value'],value=value('normal'))
    reset();pointer([move('normal',-50),dict(type='pointerDown',button=0),move('normal',40)])
    focus('coarse');pointer([dict(type='pointerUp',button=0)])
    check('blur-finishes-native-drag',any(e['id']=='normal' and e['type']=='change' and e['trusted'] for e in changes()))
    reset();pointer([move('normal',-50),dict(type='pointerDown',button=0),move('normal',40)])
    key('\ue00c');pointer([dict(type='pointerUp',button=0)])
    check('engine-cancels-native-gesture',value('normal')==25,value=value('normal'))
    reset();pointer([move('normal',-50),dict(type='pointerDown',button=0)])
    execute('document.getElementById("normal").remove();return true');pointer([dict(type='pointerUp',button=0)])
    check('remove-during-native-tracking',not execute('return !!document.getElementById("normal")'))
    reset();pointer([move('normal',-50),dict(type='pointerDown',button=0)])
    execute('document.getElementById("normal").style.appearance="none";return true');crop('normal');pointer([dict(type='pointerUp',button=0)])
    check('style-change-releases-native-tracking',0<=value('normal')<=100)
    reset();execute('document.getElementById("normal").style.width="280px";return true')
    compare('normal','resized',label='resize')
    reset();execute('let element=document.getElementById("normal"),parent=element.parentNode;element.remove();parent.append(element);return true');focus('normal');key('\ue014')
    check('reinsert-new-native-binding',value('normal')==native_models['normal']['keys'][0]['value'])
    reset();compare('normal',label='reload')
    click('ordinary');check('ordinary-engine-action',execute('return document.getElementById("ordinary").textContent')=='Activated')
    reset();first=m.command('WebDriver:GetWindowHandle')['value']
    other=m.command('WebDriver:NewWindow',dict(type='tab',focus=True))['handle']
    m.command('WebDriver:SwitchToWindow',dict(handle=other));check('other-tab-active',m.command('WebDriver:GetTitle')['value']=='')
    m.command('WebDriver:SwitchToWindow',dict(handle=first));compare('normal',label='tab-restored')
    focus('normal');key('\ue014');check('reactivated-native-model',value('normal')==native_models['normal']['keys'][0]['value'])
    m.command('WebDriver:SwitchToWindow',dict(handle=other));m.command('WebDriver:CloseWindow');m.command('WebDriver:SwitchToWindow',dict(handle=first));reset()
    execute('window.cacheMarker=23;document.getElementById("normal").cacheMarker=47;return true')
    m.command('WebDriver:Navigate',dict(url='about:blank'));check('navigation-away',m.command('WebDriver:GetTitle')['value']=='')
    m.command('WebDriver:Back');check('actual-bfcache-restore',execute('return cacheMarker===23 && document.getElementById("normal").cacheMarker===47 && cacheShows.includes(true)'))
    compare('normal',label='bfcache-restored');focus('normal');key('\ue014')
    check('restored-native-engine-model',value('normal')==native_models['normal']['keys'][0]['value'])
    m.command('WebDriver:Navigate',dict(url='about:blank'))
    print(json.dumps(dict(passed=len(results))),flush=True)
finally:
    try:m.command('WebDriver:ReleaseActions')
    finally:m.close()
