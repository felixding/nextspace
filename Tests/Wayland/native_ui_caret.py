#!/usr/bin/env python3
"""Compare long-document browser editing with native NSTextView key results."""
import argparse,json,shlex,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
for name in ['ssh-config','fixture','output']:p.add_argument('--'+name,required=True)
p.add_argument('--browser',choices=['firefox','chromium'],required=True)
p.add_argument('--session');p.add_argument('--cdp');p.add_argument('--browser-pid',type=int)
p.add_argument('--restart',action='store_true')
p.add_argument('--step-keys',action='store_true',help='Wait for each real key and record its native comparison')
p.add_argument('--case',choices=['down','up','selection-down','selection-up','wrapped-down','insert-offscreen','cancel-insert','extended'])
a=p.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True);rows=[]
ssh=['ssh','-F',a.ssh_config,'lima-nextspace-gui']
def remote(code):return json.loads(subprocess.check_output(ssh+[shlex.join(['python3','-c',code])],text=True))
def control(operation,**values):
 request=dict(operation=operation,**values)
 return remote('import socket,json\nwith socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:\n s.settimeout(40);s.connect('+repr(a.fixture+'/control.sock')+');s.send('+repr(json.dumps(request).encode())+');print(s.recv(65536).decode())')
if a.browser=='chromium':
 assert a.session and a.cdp and a.browser_pid
 browser=['agent-browser','--session',a.session,'--cdp',a.cdp]
 def ab(*args):return subprocess.check_output(browser+list(args),text=True)
def js(code):
 if a.browser=='firefox':return control('firefox-eval',script='return '+code)['value']
 return json.loads(ab('eval',code))
screens=0
def screen():
 global screens
 if a.browser=='firefox':return control('firefox-screenshot')['path']
 screens+=1;local=out/(f'screen-{screens}.png');ab('screenshot',str(local.resolve()))
 target=a.fixture+'/'+out.name+f'-screen-{screens}.png'
 subprocess.run(ssh+['cat > '+shlex.quote(target)],input=local.read_bytes(),check=True)
 return target
def wait(read,predicate):
 end=time.monotonic()+20
 while True:
  value=read()
  if predicate(value):return value
  assert time.monotonic()<end,value
  time.sleep(.03)
def check(case,passed,**evidence):
 rows.append(dict(case=case,passed=bool(passed),**evidence));(out/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
masks=remote('''import ctypes as C,json
from pathlib import Path
x=C.CDLL('libxkbcommon.so.0');x.xkb_context_new.argtypes=[C.c_int];x.xkb_context_new.restype=C.c_void_p
x.xkb_keymap_new_from_string.argtypes=[C.c_void_p,C.c_char_p,C.c_int,C.c_int];x.xkb_keymap_new_from_string.restype=C.c_void_p
x.xkb_keymap_mod_get_index.argtypes=[C.c_void_p,C.c_char_p];x.xkb_keymap_mod_get_index.restype=C.c_uint
context=x.xkb_context_new(0);mapping=x.xkb_keymap_new_from_string(context,Path('''+repr(a.fixture+'/keymap.xkb')+''').read_bytes(),1,0);assert mapping
print(json.dumps({k:1<<x.xkb_keymap_mod_get_index(mapping,v) for k,v in [('control',b'Control'),('alt',b'Mod1'),('shift',b'Shift')]}))''')
def state():return js('(()=>{let e=document.getElementById("native-caret");return {value:e.value,start:e.selectionStart,end:e.selectionEnd,top:e.scrollTop,left:e.scrollLeft,page:scrollY,events:__caretEvents,rect:e.getBoundingClientRect().toJSON()}})()')
def run(label,text,start,scroll,steps,cancel=False):
 if a.browser=='firefox':control('firefox-eval',context='chrome',script='gBrowser.selectedBrowser.focus();return true')
 js('(()=>{document.getElementById("native-caret")?.remove();let e=document.createElement("textarea");e.id="native-caret";e.style="position:absolute;left:30px;top:30px;width:240px;height:120px";e.value='+json.dumps(text)+';document.body.append(e);e.focus();e.setSelectionRange('+str(start)+','+str(start)+');window.scrollTo(0,0);e.scrollTop='+str(scroll)+';window.__caretEvents=[];for(let type of ["keydown","beforeinput","input","scroll"])e.addEventListener(type,v=>__caretEvents.push({type,trusted:v.isTrusted,inputType:v.inputType,top:e.scrollTop}));return true})()')
 if cancel:js('(()=>{document.getElementById("native-caret").addEventListener("beforeinput",e=>e.preventDefault(),{once:true});return true})()')
 screen()
 rect=state()['rect']
 keys=[dict(key=v.get('key',0),text=v.get('text',''),modifiers=v.get('native_modifiers',0)) for v in steps]
 reference=control('native-reference',name=out.name+'-'+label,focus=True,controls=[dict(id='textarea',kind=9,width=rect['width'],height=rect['height'],enabled=1,state=0,title='',text=text,selection_start=start,selection_length=0,scroll=[0,scroll],text_keys=keys,blur_after_keys=True,text_veto=cancel)])
 previous_text=text
 for native_step in reference['reference'][0]['text_keys']:
  previous_text=native_step.setdefault('value',previous_text)
 expected=reference['reference'][0]['text_keys'][-1]
 commands=[];sequence=[]
 for index,step in enumerate(steps):
  mask=sum(masks[m] for m in step.get('modifiers',[]));commands.extend([f'forward-modifiers {mask} 0 0 0',f"forward {step['code']} 1",f"forward {step['code']} 0"])
  if a.step_keys:
   assert control('keyboard',text='\n'.join(commands+['forward-modifiers 0 0 0 0','sync']))['ok'];commands=[]
   native_step=reference['reference'][0]['text_keys'][index]
   observed=wait(state,lambda s:sum(e['type']=='keydown' for e in s['events'])>=index+1 and all(s[k]==native_step[k] for k in ['value','start','end']))
   sequence.append({k:observed[k] for k in ['start','end','top','left']})
 commands+=['forward-modifiers 0 0 0 0','sync'];assert control('keyboard',text='\n'.join(commands))['ok']
 if a.step_keys:
  check(label+'-native-key-sequence',all(all(v[k]==n[k] for k in ['start','end','top','left']) for v,n in zip(sequence,reference['reference'][0]['text_keys'])),browser=sequence,native=reference['reference'][0]['text_keys'])
 current=wait(state,lambda s:sum(e['type']=='keydown' for e in s['events'])>=len(steps) and all(s[k]==expected[k] for k in ['value','start','end']))
 check(label+'-native-selection-and-model',all(current[k]==expected[k] for k in ['value','start','end']),native=expected,browser=current)
 current=wait(state,lambda s:s['top']==expected['top'] and s['left']==expected['left'])
 check(label+'-native-viewport',current['page']==0,native=expected,browser=current)
 check(label+'-trusted-key-events',all(e['trusted'] for e in current['events']) and sum(e['type']=='keydown' for e in current['events'])==len(steps),events=current['events'])
 if cancel:check(label+'-beforeinput-veto-keeps-model-and-viewport',any(e['type']=='beforeinput' for e in current['events']) and not any(e['type']=='input' for e in current['events']),browser=current)
 js('(()=>{document.body.tabIndex=-1;document.body.focus({preventScroll:true});return true})()')
 path=screen();rect=state()['rect'];box=tuple(round(rect[k]) for k in ['left','top','right','bottom'])
 diff=remote('from PIL import Image,ImageChops\nfrom pathlib import Path\nimport json\np=Path('+repr(path)+');saved=p.with_name('+repr(out.name+'-'+label+'.png')+');saved.write_bytes(p.read_bytes());a=Image.open(saved).convert("RGB").crop('+repr(box)+');b=Image.open('+repr(reference['path']+'/textarea.png')+').convert("RGB");d=ImageChops.difference(a,b);print(json.dumps(dict(equal=d.getbbox() is None,box=d.getbbox(),screen=str(saved))))')
 check(label+'-native-pixels',diff['equal'],**diff)
 current=state();check(label+'-viewport-after-paint',current['top']==expected['top'] and current['left']==expected['left'] and current['page']==0,browser=current,native=expected)
text='\n'.join('Line '+str(i) for i in range(80))
initial=control('status');pid=initial['browser'] if a.browser=='firefox' else a.browser_pid
window=next(w for w in initial['windows'] if w['pid']==pid and w['level']==0);control('shell',text='activate '+str(window['id']))
wait(lambda:control('status'),lambda s:any(w['pid']==pid and w['flags']&1 for w in s['windows']))
try:
 for phase in ['initial']+(['recovered'] if a.restart else []):
  if phase=='recovered':
   host=control('status')['host'];control('restart-host')
   wait(lambda:control('status'),lambda s:s['host'] and s['host']!=host and any(w['pid']==s['host'] and w['level']==20 and not w['flags']&(2|32) for w in s['windows']))
  if not a.case or a.case=='down':run(phase+'-down',text,0,0,[dict(code=108,key=9)]*40)
  if not a.case or a.case=='up':run(phase+'-up',text,len(text),1000000,[dict(code=103,key=8)]*40)
  if not a.case or a.case=='selection-down':run(phase+'-selection-down',text,0,0,[dict(code=108,key=9,native_modifiers=1,modifiers=['shift'])]*40)
  if not a.case or a.case in ['selection-up','extended']:run(phase+'-selection-up',text,len(text),1000000,[dict(code=103,key=8,native_modifiers=1,modifiers=['shift'])]*40)
  if not a.case or a.case in ['wrapped-down','extended']:run(phase+'-wrapped-down','A native text view owns wrapping and caret motion. '*100,0,0,[dict(code=108,key=9)]*40)
  if not a.case or a.case=='insert-offscreen':run(phase+'-insert-offscreen',text,len(text),0,[dict(code=44,text='Z',native_modifiers=1,modifiers=['shift'])])
  if not a.case or a.case in ['cancel-insert','extended']:run(phase+'-cancel-insert',text,len(text),0,[dict(code=44,text='Z',native_modifiers=1,modifiers=['shift'])],cancel=True)
 print(json.dumps(dict(passed=len(rows))))
finally:
 if a.browser=='chromium':ab('close')
