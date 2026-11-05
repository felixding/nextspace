#!/usr/bin/env python3
"""Check complete native field pixels and actual Gecko text transactions."""
import argparse,base64,io,json,time
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
def key(value,modifier=None):
 actions=([dict(type='keyDown',value=modifier)] if modifier else [])+[dict(type='keyDown',value=value),dict(type='keyUp',value=value)]+([dict(type='keyUp',value=modifier)] if modifier else [])
 m.command('WebDriver:PerformActions',dict(actions=[dict(type='key',id='keyboard',actions=actions)]))
def state(identifier='normal'):
 return execute('let e=document.getElementById('+json.dumps(identifier)+');return {value:e.value,start:e.selectionStart,end:e.selectionEnd}')
def focus(identifier='normal',start=1,end=3):
 execute('let e=document.getElementById('+json.dumps(identifier)+');e.focus();e.setSelectionRange('+str(start)+','+str(end)+');events=[];return true')
def reset():m.command('WebDriver:Refresh')
def compare(identifier,focused=False,reference=None,label=None):
 rect=execute('return document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()')
 pixels=base64.b64decode(m.command('WebDriver:TakeScreenshot',dict(full=False))['value'])
 label=label or identifier+('-focused' if focused else '-normal');(a.output/(label+'.png')).write_bytes(pixels)
 x,y,w,h=[round(rect[k]) for k in ('x','y','width','height')]
 actual=Image.open(io.BytesIO(pixels)).convert('RGB').crop((x,y,x+w,y+h))
 root=a.references.parent/'focused-references' if focused else a.references
 expected=Image.open(root/((reference or identifier)+'.png')).convert('RGBA');bg=Image.new('RGBA',expected.size,'white');bg.alpha_composite(expected)
 difference=ImageChops.difference(actual,bg.convert('RGB')).getbbox() if actual.size==expected.size else 'size'
 check('native-pixels-'+label,difference is None,difference=difference)
 if focused:
  outer=Image.open(io.BytesIO(pixels)).convert('RGB').crop((x-3,y-3,x+w+3,y+h+3))
  margin=Image.new('RGB',outer.size,'white');margin.paste(bg.convert('RGB'),(3,3))
  check('native-focus-margin-'+identifier,ImageChops.difference(outer,margin).getbbox() is None)
try:
 session=m.command('WebDriver:NewSession',{});check('owned-fixture',session['capabilities']['moz:processID']==a.expected_pid)
 check('fixture-title',m.command('WebDriver:GetTitle')['value']=='Gecko native text transport')
 m.command('WebDriver:SetWindowRect',dict(width=900,height=850))
 for identifier in ('normal','password','readonly','disabled','unicode','limited'):compare(identifier)
 for identifier in ('normal','password','readonly','unicode','limited'):
  reset();focus(identifier);compare(identifier,True)
 reset();execute('normal.value="Updated";return true');compare('normal',reference='updated',label='programmatic-model')
 check('programmatic-no-input-events',not execute('return events.some(e=>e.type==="input"||e.type==="change")'))
 reset();execute('normal.style.width="240px";normal.style.height="30px";return true');compare('normal',reference='wide',label='resized-model')
 reset();focus();key('X');check('native-selection-replacement',state()==dict(value='HXlo',start=2,end=2),state=state())
 changes=execute('return events.filter(e=>e.type==="beforeinput"||e.type==="input")')
 check('trusted-insert-transaction',[e['type'] for e in changes]==['beforeinput','input'] and all(e['trusted'] and e['inputType']=='insertText' and e['data']=='X' for e in changes),events=changes)
 key('\ue003');check('native-backspace-transaction',state()==dict(value='Hlo',start=1,end=1),state=state())
 reset();focus();key('X');execute('password.focus();return true');check('engine-blur-change',execute('return events.some(e=>e.id==="normal"&&e.type==="change"&&e.trusted&&e.value==="HXlo")'))
 reset();focus();key('X');execute('document.execCommand("undo");return true');check('engine-undo-retained',state()['value']=='Hello',state=state())
 reset();focus();execute('normal.addEventListener("beforeinput",e=>e.preventDefault());return true');key('X');check('cancel-beforeinput',state()==dict(value='Hello',start=1,end=3),state=state())
 reset();focus();execute('normal.addEventListener("beforeinput",e=>{e.preventDefault();e.target.value="Script";e.target.setSelectionRange(2,2)},{once:true});return true');key('X');check('beforeinput-canonical-script-value',state()==dict(value='Script',start=2,end=2),state=state())
 reset();focus();execute('normal.addEventListener("input",e=>{e.target.value="Input update"},{once:true});return true');key('X');check('input-canonical-script-value',state()['value']=='Input update',state=state())
 reset();focus();execute('normal.addEventListener("keydown",e=>e.preventDefault());return true');key('X');check('cancel-keydown',state()==dict(value='Hello',start=1,end=3),state=state())
 reset();focus(start=3,end=3);key('a','\ue009');check('native-emacs-control-a',state()['start']==state()['end']==0,state=state())
 key('e','\ue009');check('native-emacs-control-e',state()['start']==state()['end']==5,state=state())
 native=next(x for x in json.loads((a.references/'results.json').read_text()) if x['id']=='normal')
 for expected in native['keys']:
  reset();execute('normal.value="Alpha beta";return true');focus(start=3,end=3)
  code=expected['key'];key(code.split('+')[-1] if code.startswith('Control+') else '\ue003' if code=='Backspace' else '\ue017','\ue009' if code.startswith('Control+') else None)
  check('native-reference-'+code,state()=={k:expected[k] for k in ('value','start','end')},state=state(),expected=expected)
 reset();focus('password');key('X');check('secure-engine-value',state('password')==dict(value='HXlo',start=2,end=2),state=state('password'))
 reset();focus('readonly');key('X');check('readonly-retained',state('readonly')['value']=='Hello')
 reset();focus('unicode',9,9);key('X');check('native-unicode-utf16',state('unicode')==dict(value='日本語Café🙂X',start=10,end=10),state=state('unicode'))
 reset();focus('limited',3,3);key('X');key('Y');check('engine-maxlength',state('limited')['value']=='abcX',state=state('limited'))
 reset();focus();key('\ue007');check('native-return-engine-submit',execute('return submits')==1)
 key('X');check('editing-after-return',state()==native['return_sequence'],state=state(),expected=native['return_sequence'])
 reset();focus();execute('normal.addEventListener("input",e=>e.target.replaceWith(e.target.cloneNode()));return true');key('X');check('input-replaces-frame',state()['value']=='HXlo',state=state())
 reset();focus();execute('normal.addEventListener("beforeinput",e=>e.target.remove());return true');key('X');check('beforeinput-removes-frame',execute('return !document.getElementById("normal")'))
 reset();focus();key('\ue004');check('native-next-focus',execute('return document.activeElement.id')=='password')
 reset();focus();execute('normal.style.appearance="none";return true');key('X');check('style-change-keeps-engine-input',state()['value']=='HXlo',state=state())
 reset();focus();execute('window.cacheMarker=23;normal.cacheMarker=47;normal.value="Updated";ordinary.focus();return true')
 m.command('WebDriver:Navigate',dict(url='about:blank'));m.command('WebDriver:Back')
 check('cache-restores-value',state()['value']=='Updated',state=state())
 cache=execute('return {window:window.cacheMarker,node:normal.cacheMarker,shows:cacheShows}')
 check('cache-restores-page',cache.get('window')==23 and cache.get('node')==47 and True in cache['shows'],cache=cache)
 compare('normal',reference='updated',label='bfcache-updated')
 reset();compare('normal',label='restored-normal')
 reset();focus(start=3,end=3)
 def caret_image():
  rect=execute('return normal.getBoundingClientRect().toJSON()')
  pixels=base64.b64decode(m.command('WebDriver:TakeScreenshot',dict(full=False))['value'])
  x,y,w,h=[round(rect[k]) for k in ('x','y','width','height')]
  return Image.open(io.BytesIO(pixels)).convert('RGB').crop((x,y,x+w,y+h))
 initial=caret_image();deadline=time.monotonic()+2;difference=None
 while time.monotonic()<deadline and difference is None:
  time.sleep(.1);difference=ImageChops.difference(initial,caret_image()).getbbox()
 check('native-caret-browser-invalidation',difference is not None and state()==dict(value='Hello',start=3,end=3),difference=difference)
 print(json.dumps(dict(passed=len(results))))
finally:
 try:m.command('WebDriver:ReleaseActions')
 finally:m.close()
