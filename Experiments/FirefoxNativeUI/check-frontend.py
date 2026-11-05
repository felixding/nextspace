#!/usr/bin/env python3
"""Compare an owned Firefox address editor with independent NativeUI controls."""
import argparse,base64,io,json,os,subprocess,time
from pathlib import Path
from PIL import Image,ImageChops
from marionette import Marionette
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--port',type=int,required=True);p.add_argument('--expected-pid',type=int,required=True)
p.add_argument('--fixture',type=Path,required=True);p.add_argument('--library',type=Path,required=True)
p.add_argument('--backend',required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);results=[];m=Marionette(a.port)
def js(script):return m.command('WebDriver:ExecuteScript',dict(script=script,args=[]))['value']
def check(case,condition,**details):
 results.append(dict(case=case,passed=bool(condition),**details));(a.output/'results.json').write_text(json.dumps(results,indent=2)+'\n');assert condition,results[-1]
def seed(start=3,end=3):
 return js("let e=document.getElementById('urlbar-input');e.focus();e.value='Alpha beta';e.setSelectionRange("+str(start)+','+str(end)+");return e.getBoundingClientRect().toJSON()")
def state():return js("let e=document.getElementById('urlbar-input');return {value:e.value,start:e.selectionStart,end:e.selectionEnd}")
def key(value,modifier=None):
 actions=([dict(type='keyDown',value=modifier)] if modifier else [])+[dict(type='keyDown',value=value),dict(type='keyUp',value=value)]+([dict(type='keyUp',value=modifier)] if modifier else [])
 m.command('WebDriver:PerformActions',dict(actions=[dict(type='key',id='keyboard',actions=actions)]))
def presses():return [json.loads(l) for l in (a.fixture/'helper.jsonl').read_text().splitlines() if '"event": "native-form-press"' in l]
try:
 session=m.command('WebDriver:NewSession',{});check('owned-browser',session['capabilities']['moz:processID']==a.expected_pid)
 m.command('Marionette:SetContext',dict(value='chrome'))
 rect=seed(1,3)
 check('browser-frontend-input',js("return document.documentURI==='chrome://browser/content/browser.xhtml' && document.getElementById('urlbar-input').type==='text'"))
 # DOMRect exposes floats; recover the engine's existing 1/60 CSS-unit bounds.
 spec=[dict(id='address',kind=7,width=round(rect['width']*60)/60,height=round(rect['height']*60)/60,
  enabled=1,state=0,title='',text='Alpha beta',selection_start=1,selection_length=2)]
 controls=a.output/'controls.json';controls.write_text(json.dumps(spec)+'\n');references=a.output/'references'
 env=dict(os.environ,**json.loads((a.fixture/'runtime.json').read_text()));env.pop('LD_PRELOAD',None)
 subprocess.run(['python3',str(Path(__file__).resolve().parent.parent/'ChromiumScrollers/native-control-reference.py'),
  '--library',str(a.library),'--controls',str(controls),'--output',str(references),'--focus','--keys','--pointers','--click-counts',
  '-GSBackend',a.backend],env=env,check=True,timeout=30,stdout=(a.output/'references.stdout').open('w'),stderr=(a.output/'references.stderr').open('w'))
 native=json.loads((references/'results.json').read_text())[0]
 expected=Image.open(references/'address.png').convert('RGBA');bg=Image.new('RGBA',expected.size,'white');bg.alpha_composite(expected);expected=bg.convert('RGB')
 match=None;deadline=time.monotonic()+5
 while not match and time.monotonic()<deadline:
  raw=base64.b64decode(m.command('WebDriver:TakeScreenshot',dict(full=False))['value']);actual=Image.open(io.BytesIO(raw)).convert('RGB')
  for y in range(round(rect['y'])-2,round(rect['y'])+3):
   for x in range(round(rect['x'])-2,round(rect['x'])+3):
    if ImageChops.difference(actual.crop((x,y,x+expected.width,y+expected.height)),expected).getbbox() is None:match=[x,y,expected.width,expected.height]
  if not match:time.sleep(.02)
 (a.output/'native-field.png').write_bytes(raw);check('complete-native-field-pixels',match is not None,matched_rectangle=match,dom_rectangle=rect)
 for ref in native['pointers']:
  rect=seed(1 if ref['modifiers'] else 0,3 if ref['modifiers'] else 0);x,y=round(rect['x']),round(rect['y']);clicks=ref.get('click_count',1)
  actions=[dict(type='pointerMove',duration=0,x=round(x+ref['x']),y=y+12),dict(type='pointerDown',button=0)]
  for _ in range(1,clicks):actions += [dict(type='pointerUp',button=0),dict(type='pointerDown',button=0)]
  if ref['x']!=ref['end_x']:actions += [dict(type='pointerMove',duration=100,x=round(x+ref['end_x']),y=y+12),dict(type='pause',duration=100)]
  actions.append(dict(type='pointerUp',button=0));before=len(presses())
  shift=[dict(type='keyDown',value='\ue008')]+[dict(type='pause')]*(len(actions)-2)+[dict(type='keyUp',value='\ue008')]
  m.command('WebDriver:PerformActions',dict(actions=[dict(type='pointer',id='mouse',parameters=dict(pointerType='mouse'),actions=actions)]+([dict(type='key',id='shift',actions=shift)] if ref['modifiers'] else [])))
  actual=state();wanted={k:ref[k] for k in ('value','start','end')};entries=presses()[before:]
  check('native-pointer-'+ref['name'],actual==wanted,state=actual,expected=wanted)
  check('native-tracking-'+ref['name'],len(entries)==clicks and [e['click_count'] for e in entries]==list(range(1,clicks+1)),presses=entries)
  if ref['start']!=ref['end']:
   image=Image.open(references/('address-pointer-'+ref['name']+'.png')).convert('RGBA')
   bg=Image.new('RGBA',image.size,'white');bg.alpha_composite(image);expected=bg.convert('RGB');difference=True;deadline=time.monotonic()+5
   while difference is not None and time.monotonic()<deadline:
    raw=base64.b64decode(m.command('WebDriver:TakeScreenshot',dict(full=False))['value']);image=Image.open(io.BytesIO(raw)).convert('RGB')
    difference=ImageChops.difference(image.crop((match[0],match[1],match[0]+expected.width,match[1]+expected.height)),expected).getbbox()
    if difference is not None:time.sleep(.02)
   (a.output/('pointer-'+ref['name']+'.png')).write_bytes(raw)
   check('complete-pointer-pixels-'+ref['name'],difference is None,difference=difference)
  m.command('WebDriver:ReleaseActions')
 for ref in native['keys']:
  seed();name=ref['key'];modifier='\ue009' if name.startswith('Control+') else None
  value=name.split('+')[-1];value={'Backspace':'\ue003','Delete':'\ue017'}.get(value,value)
  key(value,modifier);actual=state();wanted={k:ref[k] for k in ('value','start','end')}
  check('native-key-'+name,actual==wanted,state=actual,expected=wanted)
 seed(1,3)
 js("window.__nativeFrontendEvents=[];let e=document.getElementById('urlbar-input');for(let type of ['beforeinput','input'])e.addEventListener(type,e=>window.__nativeFrontendEvents.push({type:e.type,trusted:e.isTrusted,inputType:e.inputType,data:e.data}));return true")
 key('X');check('native-typing-transaction',state()==dict(value='AXha beta',start=2,end=2),state=state())
 events=js('return window.__nativeFrontendEvents');check('trusted-insert-events',[e['type'] for e in events]==['beforeinput','input'] and all(e['trusted'] and e['inputType']=='insertText' for e in events),events=events)
 seed(1,3);js("document.getElementById('urlbar-input').addEventListener('beforeinput',e=>e.preventDefault(),{once:true});return true")
 key('Y');check('cancel-beforeinput',state()==dict(value='Alpha beta',start=1,end=3),state=state())
 print(json.dumps(dict(passed=len(results))))
finally:m.close()
