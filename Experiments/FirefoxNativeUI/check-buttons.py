#!/usr/bin/env python3
"""Qualify native input-button pixels against the actual engine form actions."""
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
try:
    session=m.command('WebDriver:NewSession',{});assert session['capabilities']['moz:processID']==a.expected_pid
    (a.output/'session.json').write_text(json.dumps(session,indent=2)+'\n')
    check('owned-fixture',m.command('WebDriver:GetTitle')['value']=='Gecko native input button transport')
    m.command('WebDriver:SetWindowRect',dict(width=900,height=700))
    for identifier in ('button','submit','reset','disabled','default-submit','default-reset'):compare(identifier)
    for identifier in ('button','submit','reset','disabled','default-submit','default-reset'):
        execute('document.getElementById('+json.dumps(identifier)+').style.cssText="width:auto;height:auto";return true')
        compare(identifier,'auto-'+identifier,label='auto-'+identifier)
    execute('document.getElementById("button").value="Updated title";return true')
    compare('button','auto-updated',label='auto-updated-title')
    execute('document.getElementById("button").value="日本語Café";return true')
    compare('button','auto-unicode',label='auto-unicode-title')
    execute('document.getElementById("button").value="";return true')
    compare('button','auto-empty',label='auto-empty-title')
    reset();execute('document.getElementById("button").style.cssText="width:auto;height:auto;font:32px monospace;line-height:60px";return true')
    compare('button','auto-button',label='native-font-metrics')
    for display in ('flex','grid'):
        reset();execute('let row=document.getElementById("button").parentNode;row.style.cssText='+json.dumps('display:'+display+';align-items:start;justify-items:start')+';document.getElementById("button").style.cssText="width:auto;height:auto";return true')
        compare('button','auto-button',label=display+'-native-intrinsic')
    for size in ('min-content','max-content'):
        reset();execute('document.getElementById("button").style.cssText='+json.dumps('width:'+size+';height:auto')+';return true')
        compare('button','auto-button',label=size+'-native-intrinsic')
    reset();execute('document.getElementById("button").style.cssText="width:auto;height:auto;min-width:120px;min-height:30px";return true')
    compare('button','min-size',label='css-min-size')
    reset();execute('document.getElementById("button").style.cssText="width:auto;height:auto;max-width:70px;max-height:18px";return true')
    compare('button','max-size',label='css-max-size')
    reset()
    click('button');check('native-mouse-engine-action',execute('return actions')==1)
    compare('button',focused=True,label='mouse-focus')
    reset();focus('button');compare('button',focused=True)
    key(' ');check('native-key-engine-action',execute('return actions')==1)
    key('\ue004');check('native-focus-traversal',execute('return document.activeElement.id')=='submit')
    execute('document.getElementById("text").value="Submitted data";return true');click('submit')
    check('actual-trusted-form-submit',execute('return submissions.length===1 && submissions[0].trusted && submissions[0].submitter==="submit" && submissions[0].message==="Submitted data"'))
    click('reset');check('actual-form-reset',execute('return resets===1 && document.getElementById("text").value==="Original"'))
    click('disabled');check('disabled-button-no-action',execute('return actions')==1)
    reset();focus('button');execute('document.getElementById("button").addEventListener("keydown",event=>event.preventDefault());return true');key(' ')
    check('page-cancels-native-key',execute('return actions')==0)
    reset();execute('document.getElementById("button").addEventListener("click",event=>event.preventDefault());return true');click('button')
    check('ordinary-click-handler-retained',execute('return actions')==1)
    execute('document.getElementById("submit").addEventListener("click",event=>event.preventDefault());return true');click('submit')
    check('cancelled-submit-preserved',execute('return submissions.length')==0)
    reset();execute('document.getElementById("button").value="Updated title";return true');compare('button','updated',label='updated-title')
    execute('document.getElementById("button").value="日本語Café";return true');compare('button','unicode',label='unicode-title')
    reset();execute('''let button=document.getElementById('button');
      button.style.cssText='appearance:none;border:2px solid black;background:#fc0;color:#246;font:16px serif;width:160px;height:28px';
      let peer=button.cloneNode();peer.id='styled-peer';peer.removeAttribute('onclick');
      let row=document.createElement('div');row.className='row';row.append(peer);button.parentNode.after(row);return true''')
    check('style-change-restores-whole-engine-control',ImageChops.difference(crop('button'),crop('styled-peer')).getbbox() is None)
    click('button');check('styled-fallback-action',execute('return actions')==1)
    execute('document.getElementById("styled-peer").parentNode.remove();document.getElementById("button").style.cssText="";document.activeElement.blur();return true')
    compare('button',label='native-after-style-restored')
    execute('document.getElementById("button").style.width="160.5px";return true')
    crop('button');click('button');check('fractional-size-fallback-action',execute('return actions')==2)
    execute('document.getElementById("button").style.cssText="";document.activeElement.blur();return true')
    compare('button',label='native-after-size-restored')
    reset();execute('document.getElementById("button").style.cssText="width:240px;height:32px";return true');compare('button','resized',label='resized')
    reset();pointer([dict(type='pointerMove',origin={'element-6066-11e4-a52e-4f735466cecf':element('button')},x=0,y=0,duration=0),dict(type='pointerDown',button=0)])
    compare('button','button-pressed',focused=True,label='held-native-button')
    pointer([dict(type='pointerMove',origin='viewport',x=500,y=400,duration=0),dict(type='pointerUp',button=0)])
    check('native-cancelled-gesture',execute('return actions')==0)
    reset();execute('document.getElementById("button").addEventListener("focus",event=>event.target.replaceWith(event.target.cloneNode()));return true');click('button')
    check('focus-handler-replacement',execute('return actions')==0)
    reset();compare('button',label='reload')
    click('ordinary');check('ordinary-engine-button',execute('return document.getElementById("ordinary").textContent')=='Activated')
    reset();first=m.command('WebDriver:GetWindowHandle')['value']
    other=m.command('WebDriver:NewWindow',dict(type='tab',focus=True))['handle']
    m.command('WebDriver:SwitchToWindow',dict(handle=other))
    check('other-tab-active',m.command('WebDriver:GetTitle')['value']=='')
    m.command('WebDriver:SwitchToWindow',dict(handle=first));focus('button');key(' ')
    check('reactivated-native-engine-action',execute('return actions')==1)
    compare('button',focused=True,label='tab-reactivated')
    m.command('WebDriver:SwitchToWindow',dict(handle=other));m.command('WebDriver:CloseWindow')
    m.command('WebDriver:SwitchToWindow',dict(handle=first));reset()
    execute('window.cacheMarker=23;document.getElementById("button").cacheMarker=47;return true')
    m.command('WebDriver:Navigate',dict(url='about:blank'));check('navigation-away',m.command('WebDriver:GetTitle')['value']=='')
    m.command('WebDriver:Back')
    check('actual-bfcache-restore',execute('return window.cacheMarker===23 && document.getElementById("button").cacheMarker===47 && cacheShows.includes(true)'))
    focus('button');key(' ');check('restored-native-engine-action',execute('return actions')==1)
    compare('button',focused=True,label='bfcache-restored')
    m.command('WebDriver:Navigate',dict(url='about:blank'))
    print(json.dumps(dict(passed=len(results))),flush=True)
finally:
    try:m.command('WebDriver:ReleaseActions')
    finally:m.close()
