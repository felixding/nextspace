#!/usr/bin/env python3
"""Exercise real Gecko checkbox/radio actions and independent native images."""
import argparse,base64,io,json
from pathlib import Path
from PIL import Image,ImageChops
from marionette import Marionette

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--port',type=int,default=2829)
p.add_argument('--expected-pid',type=int,required=True)
p.add_argument('--references',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);results=[]
m=Marionette(a.port)
def execute(script):return m.command('WebDriver:ExecuteScript',dict(script=script,args=[]))['value']
def check(case,condition,**details):
    results.append(dict(case=case,passed=bool(condition),**details))
    (a.output/'results.json').write_text(json.dumps(results,indent=2)+'\n');assert condition,results[-1]
def compare(identifier,reference=None,focused=False,label=None):
    label=label or identifier+('-focused' if focused else '-normal')
    rect=execute('return document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()')
    image=m.command('WebDriver:TakeScreenshot',dict(full=False))['value'];data=base64.b64decode(image)
    (a.output/(label+'.png')).write_bytes(data)
    x,y,w,h=[round(rect[k]) for k in ('x','y','width','height')]
    actual=Image.open(io.BytesIO(data)).convert('RGB').crop((x,y,x+w,y+h))
    folder=a.references.parent/'focused-references' if focused else a.references
    expected=Image.open(folder/((reference or identifier)+'.png')).convert('RGBA')
    background=Image.new('RGBA',expected.size,'white');background.alpha_composite(expected)
    difference=ImageChops.difference(actual,background.convert('RGB')).getbbox() if actual.size==expected.size else 'size'
    check('native-pixels-'+label,difference is None,difference=difference,actual_size=actual.size,reference_size=expected.size)
def element(identifier):
    return next(iter(m.command('WebDriver:FindElement',dict(using='css selector',value='#'+identifier))['value'].values()))
def click(identifier):m.command('WebDriver:ElementClick',dict(id=element(identifier)))
def keys(*values):
    m.command('WebDriver:PerformActions',dict(actions=[dict(type='key',id='keyboard',actions=[action for value in values for action in [dict(type='keyDown',value=value),dict(type='keyUp',value=value)]])]))
def pointer(actions):
    m.command('WebDriver:PerformActions',dict(actions=[dict(type='pointer',id='mouse',parameters=dict(pointerType='mouse'),actions=actions)]))
def move_to(identifier):
    return dict(type='pointerMove',origin={'element-6066-11e4-a52e-4f735466cecf':element(identifier)},x=0,y=0,duration=0)
def changes():return execute('return events.filter(e=>e.type==="input"||e.type==="change")')
def focus(identifier):execute('document.getElementById('+json.dumps(identifier)+').focus();return true')
def reset():m.command('WebDriver:Refresh')
try:
    session=m.command('WebDriver:NewSession',{});assert session['capabilities']['moz:processID']==a.expected_pid
    (a.output/'session.json').write_text(json.dumps(session,indent=2)+'\n')
    check('owned-fixture',m.command('WebDriver:GetTitle')['value']=='Gecko native checkbox and radio transport')
    m.command('WebDriver:SetWindowRect',dict(width=900,height=700))
    for identifier in ('check','checked','mixed','disabled','radio','selected'):compare(identifier)
    click('check')
    check('mouse-engine-model',execute('return document.getElementById("check").checked'))
    check('trusted-input-change',[e['type'] for e in changes()]==['input','change'] and all(e['trusted'] for e in changes()))
    compare('check','checked',focused=True,label='mouse-checked')
    reset();focus('check');compare('check',focused=True)
    keys(' ')
    check('native-key-engine-action',execute('return document.getElementById("check").checked') and [e['type'] for e in changes()]==['input','change'] and all(e['trusted'] for e in changes()))
    compare('check','checked',focused=True,label='keyboard-checked')
    keys(' ')
    check('second-key-exactly-one-toggle',not execute('return document.getElementById("check").checked') and len(changes())==4)
    keys('\ue004')
    check('native-next-focus',execute('return document.activeElement.id')=='checked')
    m.command('WebDriver:PerformActions',dict(actions=[dict(type='key',id='keyboard',actions=[dict(type='keyDown',value='\ue008'),dict(type='keyDown',value='\ue004'),dict(type='keyUp',value='\ue004'),dict(type='keyUp',value='\ue008')])]))
    check('native-previous-focus',execute('return document.activeElement.id')=='check')
    reset();focus('check')
    execute('document.getElementById("check").addEventListener("keydown",e=>e.preventDefault());return true')
    keys(' ')
    check('page-cancels-native-key',not execute('return document.getElementById("check").checked') and not changes())
    reset();focus('check')
    execute('document.getElementById("check").dispatchEvent(new KeyboardEvent("keydown",{key:" ",bubbles:true,cancelable:true}));return true')
    check('untrusted-key-no-native-action',not execute('return document.getElementById("check").checked') and not changes())
    reset();execute('document.getElementById("check").addEventListener("click",e=>e.preventDefault());return true');click('check')
    check('engine-cancels-click-model',not execute('return document.getElementById("check").checked') and not changes())
    reset();execute('document.getElementById("check").addEventListener("focus",event=>{let previous=event.target,next=previous.cloneNode();previous.replaceWith(next);});return true');click('check')
    check('focus-handler-replaces-frame-safely',not execute('return document.getElementById("check").checked') and not changes())
    reset();click('radio')
    check('engine-radio-group',execute('return document.getElementById("radio").checked && !document.getElementById("selected").checked'))
    compare('radio','selected',focused=True,label='radio-selected')
    compare('selected','radio',label='radio-group-cleared')
    reset();click('disabled')
    check('disabled-no-engine-edit',not execute('return document.getElementById("disabled").checked') and not changes())
    reset();click('mixed')
    check('mixed-engine-activation',execute('return document.getElementById("mixed").checked && !document.getElementById("mixed").indeterminate') and len(changes())==2)
    reset();focus('radio');keys(' ')
    check('native-key-radio-group',execute('return document.getElementById("radio").checked && !document.getElementById("selected").checked') and len(changes())==2)
    reset();pointer([move_to('check'),dict(type='pointerDown',button=0)])
    compare('check','check-pressed',focused=True,label='held-mouse')
    pointer([dict(type='pointerMove',origin='viewport',x=500,y=400,duration=0),dict(type='pointerUp',button=0)])
    check('native-drag-cancel',not execute('return document.getElementById("check").checked') and not changes())
    reset();pointer([move_to('check'),dict(type='pointerDown',button=0)])
    execute('document.getElementById("check").remove();return true')
    pointer([dict(type='pointerUp',button=0)])
    check('remove-during-tracking',not execute('return !!document.getElementById("check")') and not changes())
    reset();execute('let p=document.getElementById("check"),parent=p.parentNode;p.remove();parent.prepend(p);return true');click('check')
    check('reinsert-new-native-object',execute('return document.getElementById("check").checked') and len(changes())==2)
    reset();execute('let p=document.getElementById("check"),n=p.cloneNode();p.replaceWith(n);return true');focus('check');keys(' ')
    check('replace-before-key',execute('return document.getElementById("check").checked'))
    click('ordinary');check('ordinary-engine-action',execute('return document.getElementById("ordinary").textContent')=='Activated')
    reset();compare('check',label='reload-check')
    first=m.command('WebDriver:GetWindowHandle')['value']
    other=m.command('WebDriver:NewWindow',dict(type='tab',focus=True))['handle']
    m.command('WebDriver:SwitchToWindow',dict(handle=other))
    check('other-tab-active',m.command('WebDriver:GetTitle')['value']=='')
    m.command('WebDriver:SwitchToWindow',dict(handle=first))
    focus('check');keys(' ')
    check('reactivated-native-engine-action',execute('return document.getElementById("check").checked'))
    compare('check','checked',focused=True,label='tab-reactivated')
    m.command('WebDriver:SwitchToWindow',dict(handle=other));m.command('WebDriver:CloseWindow')
    m.command('WebDriver:SwitchToWindow',dict(handle=first))
    reset()
    execute('window.cacheMarker=23;document.getElementById("check").cacheMarker=47;return true')
    m.command('WebDriver:Navigate',dict(url='about:blank'))
    check('navigation-away',m.command('WebDriver:GetTitle')['value']=='')
    m.command('WebDriver:Back')
    check('actual-bfcache-restore',execute('return window.cacheMarker===23 && document.getElementById("check").cacheMarker===47 && cacheShows.includes(true)'))
    focus('check');keys(' ')
    check('restored-native-engine-action',execute('return document.getElementById("check").checked'))
    compare('check','checked',focused=True,label='bfcache-restored')
    m.command('WebDriver:Navigate',dict(url='about:blank'))
    print(json.dumps(dict(passed=len(results))),flush=True)
finally:
    try:m.command('WebDriver:ReleaseActions')
    finally:m.close()
