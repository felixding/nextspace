#!/usr/bin/env python3
"""Compare real Chromium pointer selection with independent NativeUI references.

agent-browser owns navigation, model inspection and screenshots. Its CLI cannot
send fractional pointer coordinates or hold Shift across pointer input, so this
checker uses the existing owned page CDP endpoint for those input events only.
Node's built-in WebSocket supplies the transport without another browser driver.
"""
import argparse,json,select,subprocess,time,urllib.request
from pathlib import Path
from PIL import Image,ImageChops
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--session',required=True);p.add_argument('--cdp',type=int,required=True)
p.add_argument('--references',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
p.add_argument('--node',default='node')
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);results=[]
command=['agent-browser','--session',a.session,'--cdp',str(a.cdp)]
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
def compare(identifier,reference,label):
 rect=execute('document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()')
 path=a.output/(label+'.png');browser('screenshot',str(path.resolve()))
 x,y,w,h=[int(rect[k]) for k in ('x','y','width','height')]
 actual=Image.open(path).convert('RGB').crop((x,y,x+w,y+h))
 expected=Image.open(a.references/(reference+'.png')).convert('RGBA')
 bg=Image.new('RGBA',expected.size,'white');bg.alpha_composite(expected)
 difference=ImageChops.difference(actual,bg.convert('RGB')).getbbox() if actual.size==expected.size else 'size'
 check('native-pixels-'+label,difference is None,difference=difference)
check('fixture-title',execute('document.title')=='Blink native text transport')
with urllib.request.urlopen('http://127.0.0.1:'+str(a.cdp)+'/json/list') as response:pages=json.load(response)
owned=[page for page in pages if page.get('type')=='page' and page.get('url')=='file:///workspace/Experiments/ChromiumScrollers/test-text.html']
assert len(owned)==1,owned
node_code=r"""
import {createInterface} from 'node:readline';
const socket=new WebSocket(process.argv[1]);
socket.addEventListener('message',event=>{const value=JSON.parse(event.data);if(value.id)process.stdout.write(JSON.stringify(value)+'\n');});
await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
for await(const line of createInterface({input:process.stdin}))socket.send(line);
socket.close();
"""
child=subprocess.Popen([a.node,'--input-type=module','-e',node_code,owned[0]['webSocketDebuggerUrl']],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
serial=0
last=[0,0]
def cdp(method,**params):
 global serial
 serial+=1;child.stdin.write(json.dumps(dict(id=serial,method=method,params=params))+'\n');child.stdin.flush()
 assert select.select([child.stdout],[],[],10)[0], 'Owned page input protocol timed out'
 response=json.loads(child.stdout.readline());assert response.get('id')==serial and 'error' not in response,response
 return response.get('result')
def pointer(kind,x=None,y=None,shift=False,clicks=1):
 if x is not None:last[:]=[x,y]
 return cdp('Input.dispatchMouseEvent',type=kind,x=last[0],y=last[1],button='left' if kind!='mouseMoved' else 'none',
  buttons=0 if kind=='mouseReleased' else 1 if kind=='mousePressed' or held[0] else 0,modifiers=8 if shift else 0,clickCount=clicks)
held=[False]
def press(identifier='normal',x=3,drag=None,shift=False,clicks=1):
 rect=execute('document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()')
 pointer('mouseMoved',rect['x']+x,rect['y']+12,shift);pointer('mousePressed',shift=shift,clicks=clicks);held[0]=True
 if drag is not None:pointer('mouseMoved',rect['x']+drag,rect['y']+12,shift)
def release(shift=False):pointer('mouseReleased',shift=shift);held[0]=False
try:
 native=json.loads((a.references/'results.json').read_text())
 for identifier in ('normal','password','readonly','unicode','limited'):
  for expected in next(x for x in native if x['id']==identifier)['pointers']:
   reset();focus(identifier,1 if expected['modifiers'] else 0,3 if expected['modifiers'] else 0)
   shift=bool(expected['modifiers']);press(identifier,expected['x'],expected['end_x'] if expected['x']!=expected['end_x'] else None,shift,expected.get('click_count',1))
   if expected['x']!=expected['end_x']:
    deadline=time.monotonic()+2
    while time.monotonic()<deadline and state(identifier)!={k:expected[k] for k in ('value','start','end')}:pass
   release(shift)
   check('native-pointer-'+identifier+'-'+expected['name'],state(identifier)=={k:expected[k] for k in ('value','start','end')},state=state(identifier),expected=expected)
   if expected['start']!=expected['end']:compare(identifier,identifier+'-pointer-'+expected['name'],'pointer-'+identifier+'-'+expected['name'])
 reset();execute('ordinary.focus();true');press(x=10);release()
 check('first-click-native-focus',execute('document.activeElement.id')=='normal' and state()==dict(value='Hello',start=1,end=1),state=state())
 events=execute('events.filter(e=>["mousedown","mouseup","click"].includes(e.type))')
 check('trusted-mouse-events',[e['type'] for e in events]==['mousedown','mouseup','click'] and all(e['trusted'] for e in events),events=events)
 check('selection-no-input-events',not execute('events.some(e=>e.type==="input"||e.type==="change")'))
 browser('press','X');check('edit-after-click',state()==dict(value='HXello',start=2,end=2),state=state())
 reset();focus(start=0,end=0);press(drag=25)
 deadline=time.monotonic()+2
 while time.monotonic()<deadline and state()!=dict(value='Hello',start=0,end=3):pass
 check('held-native-selection',state()==dict(value='Hello',start=0,end=3),state=state())
 compare('normal','normal-pointer-forward','held-selection');release();browser('press','X')
 check('edit-after-drag',state()==dict(value='Xlo',start=1,end=1),state=state())
 for event in ('mousedown','pointerdown'):
  reset();focus();execute('normal.addEventListener('+json.dumps(event)+',e=>e.preventDefault());true');press(x=10);release()
  check('cancel-'+event,state()==dict(value='Hello',start=1,end=3),state=state())
 reset();focus(start=0,end=0);press(drag=25);execute('normal.value="Updated";true');browser('screenshot',str((a.output/'script-during-drag.png').resolve()));release();browser('press','X')
 check('script-value-during-drag',state()==dict(value='UpdatedX',start=8,end=8),state=state())
 reset();focus(start=0,end=0);press(drag=25);execute('normal.setSelectionRange(4,4);true');browser('screenshot',str((a.output/'selection-during-drag.png').resolve()));release()
 check('script-selection-during-drag',state()==dict(value='Hello',start=4,end=4),state=state())
 reset();focus(start=0,end=0);press(drag=25);execute('normal.style.width="240px";true');browser('screenshot',str((a.output/'resize-during-drag.png').resolve()));release();focus(start=5,end=5);browser('press','X')
 check('resize-during-drag',state()==dict(value='HelloX',start=6,end=6),state=state())
 reset();focus(start=0,end=0);press(drag=25);execute('normal.readOnly=true;true');browser('screenshot',str((a.output/'readonly-during-drag.png').resolve()));release();browser('press','X')
 check('readonly-during-drag',state()['value']=='Hello',state=state())
 reset();focus(start=0,end=0);press(drag=25);execute('normal.disabled=true;true');browser('screenshot',str((a.output/'disabled-during-drag.png').resolve()));release()
 execute('normal.disabled=false;normal.focus();normal.setSelectionRange(5,5);true');browser('press','X')
 check('disabled-during-drag',state()==dict(value='HelloX',start=6,end=6),state=state())
 reset();focus(start=0,end=0);press(drag=25);execute('password.focus();true');release();browser('press','X')
 check('focus-transfer-during-drag',state()['value']=='Hello' and state('password')['value']!='Hello',state=state(),other=state('password'))
 reset();focus();execute('normal.addEventListener("mouseup",e=>e.preventDefault());true');press(x=10);release();browser('press','X')
 check('cancel-mouseup-releases-editor',state()==dict(value='HXello',start=2,end=2),state=state())
 reset();execute('normal.addEventListener("focus",e=>e.target.replaceWith(e.target.cloneNode()),{once:true});ordinary.focus();true');press(x=10);release()
 check('focus-handler-replacement',state()['value']=='Hello',state=state())
 press(x=10);release();check('pointer-after-replacement',state()==dict(value='Hello',start=1,end=1),state=state())
 reset();focus();execute('normal.addEventListener("mousedown",e=>e.target.remove(),{once:true});true');press(x=10);release()
 check('handler-removes-field',execute('!document.getElementById("normal")'))
 print(json.dumps(dict(passed=len(results))))
finally:
 if held[0]:release()
 child.stdin.close()
 try:child.wait(timeout=5)
 except subprocess.TimeoutExpired:child.terminate();child.wait(timeout=5)
