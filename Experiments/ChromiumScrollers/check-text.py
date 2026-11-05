#!/usr/bin/env python3
"""Check actual native field pixels and Blink text transactions in an owned fixture."""
import argparse,json,subprocess,time
from pathlib import Path
from PIL import Image,ImageChops

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--session',required=True);p.add_argument('--cdp',required=True)
p.add_argument('--references',type=Path,required=True);p.add_argument('--focused-references',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);results=[]
command=['agent-browser','--session',a.session,'--cdp',a.cdp]
def browser(*args):return subprocess.check_output(command+list(args),text=True)
def execute(script):return json.loads(browser('eval',script))
def check(case,condition,**details):
 results.append(dict(case=case,passed=bool(condition),**details));(a.output/'results.json').write_text(json.dumps(results,indent=2)+'\n');assert condition,results[-1]
def reset():
 execute('window.__reloadPending=true;location.reload();true')
 browser('wait','--fn','document.readyState==="complete" && !!window.events && !window.__reloadPending')
def focus(identifier='normal',start=1,end=3):
 execute('(()=>{let e=document.getElementById('+json.dumps(identifier)+');e.focus();e.setSelectionRange('+str(start)+','+str(end)+');events=[];return true})()')
def state(identifier='normal'):
 return execute('(()=>{let e=document.getElementById('+json.dumps(identifier)+');return {value:e.value,start:e.selectionStart,end:e.selectionEnd}})()')
def key(value):browser('press',value)
def compare(identifier,focused=False,reference=None,label=None):
 rect=execute('document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()')
 label=label or identifier+('-focused' if focused else '-normal');path=a.output/(label+'.png');browser('screenshot',str(path.resolve()))
 x,y,w,h=[int(rect[k]) for k in ('x','y','width','height')]
 actual=Image.open(path).convert('RGB').crop((x,y,x+w,y+h))
 expected=Image.open((a.focused_references if focused else a.references)/((reference or identifier)+'.png')).convert('RGBA')
 bg=Image.new('RGBA',expected.size,'white');bg.alpha_composite(expected)
 difference=ImageChops.difference(actual,bg.convert('RGB')).getbbox() if actual.size==expected.size else 'size'
 check('native-pixels-'+label,difference is None,difference=difference,rect=rect)

check('fixture-title',execute('document.title')=='Blink native text transport')
reset()
for identifier in ('normal','password','readonly','disabled','unicode','limited'):compare(identifier)
for identifier in ('normal','password','readonly','unicode','limited'):
 reset();focus(identifier);compare(identifier,True)
reset();focus();key('X');check('native-selection-replacement',state()==dict(value='HXlo',start=2,end=2),state=state())
edits=execute('events.filter(e=>e.type==="beforeinput"||e.type==="input")')
check('trusted-insert-transaction',[e['type'] for e in edits]==['beforeinput','input'] and all(e['trusted'] and e['inputType']=='insertText' and e['data']=='X' for e in edits),events=edits)
execute('events=[];true');key('Backspace');check('native-backspace',state()==dict(value='Hlo',start=1,end=1),state=state())
edits=execute('events.filter(e=>e.type==="beforeinput"||e.type==="input")')
check('trusted-delete-transaction',[e['type'] for e in edits]==['beforeinput','input'] and all(e['trusted'] and e['inputType']=='deleteContentBackward' for e in edits),events=edits)
native=next(x for x in json.loads((a.references/'results.json').read_text()) if x['id']=='normal')
for expected in native['keys']:
 reset();execute('normal.value="Alpha beta";true');focus(start=3,end=3);key(expected['key'])
 check('native-reference-'+expected['key'],state()=={k:expected[k] for k in ('value','start','end')},state=state(),expected=expected)
reset();focus();execute('normal.addEventListener("beforeinput",e=>e.preventDefault());true');key('X')
check('cancel-beforeinput-insert',state()==dict(value='Hello',start=1,end=3),state=state())
key('Backspace');check('cancel-beforeinput-delete',state()==dict(value='Hello',start=1,end=3),state=state())
reset();focus();execute('normal.addEventListener("beforeinput",e=>{e.preventDefault();e.target.value="Script";e.target.setSelectionRange(2,2)},{once:true});true');key('X')
check('beforeinput-script-model',state()==dict(value='Script',start=2,end=2),state=state())
reset();focus();execute('normal.addEventListener("input",e=>e.target.value="Input update",{once:true});true');key('X')
check('input-script-model',state()['value']=='Input update',state=state())
for event in ('keydown','keypress'):
 reset();focus();execute('normal.addEventListener('+json.dumps(event)+',e=>e.preventDefault());true');key('X')
 check('cancel-'+event,state()==dict(value='Hello',start=1,end=3),state=state())
reset();focus();key('X');execute('document.execCommand("undo");true');check('engine-undo-retained',state()['value']=='Hello',state=state())
reset();focus();key('X');execute('password.focus();true');check('engine-blur-change',execute('events.some(e=>e.id==="normal"&&e.type==="change"&&e.trusted&&e.value==="HXlo")'))
reset();focus('password');key('X');check('secure-engine-value',state('password')==dict(value='HXlo',start=2,end=2),state=state('password'))
reset();focus('readonly');key('X');check('readonly-retained',state('readonly')['value']=='Hello')
reset();execute('disabled.focus();true');check('disabled-no-focus',execute('document.activeElement.id')!='disabled')
reset();focus('unicode',9,9);key('X');check('unicode-utf16',state('unicode')==dict(value='日本語Café🙂X',start=10,end=10),state=state('unicode'))
reset();focus('limited',3,3);key('X');key('Y');check('engine-maxlength',state('limited')['value']=='abcX',state=state('limited'))
reset();focus();key('Enter');check('engine-form-submit',execute('submits')==1)
reset();execute('normal.value="Updated";true');compare('normal',reference='updated',label='programmatic-model')
reset();focus(start=0,end=0);browser('screenshot',str((a.output/'caret-before-programmatic-selection.png').resolve()))
execute('normal.setSelectionRange(1,3);true');compare('normal',True,label='programmatic-selection')
reset();focus();execute('normal.addEventListener("input",e=>e.target.replaceWith(e.target.cloneNode()),{once:true});true');key('X')
check('input-replaces-frame',state()['value']=='HXlo',state=state())
reset();focus();execute('normal.addEventListener("beforeinput",e=>e.target.remove(),{once:true});true');key('X')
check('beforeinput-removes-frame',execute('!document.getElementById("normal")'))
reset();focus(start=3,end=3)
def caret_image(index):
 rect=execute('normal.getBoundingClientRect().toJSON()');path=a.output/('caret-'+str(index)+'.png')
 browser('screenshot',str(path.resolve()));x,y,w,h=[int(rect[k]) for k in ('x','y','width','height')]
 return Image.open(path).convert('RGB').crop((x,y,x+w,y+h))
first=caret_image(0);deadline=time.monotonic()+4;difference=None;index=0
while time.monotonic()<deadline and difference is None:
 index+=1;difference=ImageChops.difference(first,caret_image(index)).getbbox()
check('native-caret-browser-invalidation',difference==(24,3,25,18) and state()==dict(value='Hello',start=3,end=3),difference=difference,state=state())
print(json.dumps(dict(passed=len(results))))
