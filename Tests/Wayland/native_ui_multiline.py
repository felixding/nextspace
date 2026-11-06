#!/usr/bin/env python3
"""Check native multiline browser transactions with actual compositor-seat keys."""
import argparse,json,shlex,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
for name in ['ssh-config','fixture','output']:p.add_argument('--'+name,required=True)
p.add_argument('--browser',choices=['firefox','chromium'],required=True)
p.add_argument('--session');p.add_argument('--cdp');p.add_argument('--browser-pid',type=int)
p.add_argument('--restart',action='store_true')
a=p.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True);rows=[]
ssh=['ssh','-F',a.ssh_config,'lima-nextspace-gui']
def remote(code):return json.loads(subprocess.check_output(ssh+[shlex.join(['python3','-c',code])],text=True))
def control(operation,**values):
 request=dict(operation=operation,**values)
 return remote('import socket,json\nwith socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:\n s.settimeout(30);s.connect('+repr(a.fixture+'/control.sock')+');s.send('+repr(json.dumps(request).encode())+');print(s.recv(65536).decode())')
if a.browser=='chromium':
 assert a.session and a.cdp and a.browser_pid
 browser=['agent-browser','--session',a.session,'--cdp',a.cdp]
 def ab(*args):return subprocess.check_output(browser+list(args),text=True)
def js(expression):
 if a.browser=='firefox':return control('firefox-eval',script='return '+expression)['value']
 return json.loads(ab('eval',expression))
def wait(read,predicate,timeout=15):
 end=time.monotonic()+timeout
 while True:
  value=read()
  if predicate(value):return value
  assert time.monotonic()<end,value
  time.sleep(.02)
def check(case,passed,**values):
 rows.append(dict(case=case,passed=bool(passed),**values));(out/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
masks=remote('''import ctypes as C,json
from pathlib import Path
x=C.CDLL('libxkbcommon.so.0');x.xkb_context_new.argtypes=[C.c_int];x.xkb_context_new.restype=C.c_void_p
x.xkb_keymap_new_from_string.argtypes=[C.c_void_p,C.c_char_p,C.c_int,C.c_int];x.xkb_keymap_new_from_string.restype=C.c_void_p
x.xkb_keymap_mod_get_index.argtypes=[C.c_void_p,C.c_char_p];x.xkb_keymap_mod_get_index.restype=C.c_uint
context=x.xkb_context_new(0);mapping=x.xkb_keymap_new_from_string(context,Path('''+repr(a.fixture+'/keymap.xkb')+''').read_bytes(),1,0);assert mapping
print(json.dumps({k:1<<x.xkb_keymap_mod_get_index(mapping,v) for k,v in [('control',b'Control'),('alt',b'Mod1'),('shift',b'Shift')]}))''')
def key(code,modifier=None):
 mask=masks[modifier] if modifier else 0
 assert control('keyboard',text=f'forward-modifiers {mask} 0 0 0\nforward {code} 1\nforward {code} 0\nforward-modifiers 0 0 0 0\nsync')['ok']
def state():return js('(()=>{let e=document.getElementById("native-multiline");return {value:e.value,start:e.selectionStart,end:e.selectionEnd,events:window.__multilineEvents}})()')
def content_focus():
 if a.browser=='firefox':
  script='return (()=>{let m=document.getElementById("toolbar-menubar");return m?.getAttribute("autohide")==="true"&&!m.hasAttribute("inactive")})()'
  if control('firefox-eval',context='chrome',script=script)['value']:
   key(1);wait(lambda:control('firefox-eval',context='chrome',script=script)['value'],lambda active:not active)
  control('firefox-eval',context='chrome',script='gBrowser.selectedBrowser.focus();return true')
def model(text,start=0,end=None,readonly=False):
 content_focus()
 return js('(()=>{let e=document.getElementById("native-multiline");e.readOnly='+json.dumps(readonly)+';e.value='+json.dumps(text)+';e.focus();e.setSelectionRange('+str(start)+','+str(start if end is None else end)+');window.__multilineEvents=[];return true})()')
def fields(label):
 content_focus()
 js('(()=>{let e=document.getElementById("native-multiline");if(!e){e=document.createElement("textarea");e.id="native-multiline";e.style="display:block;width:240px;height:120px";document.body.prepend(e);for(let type of ["keydown","keypress","beforeinput","input"])e.addEventListener(type,v=>window.__multilineEvents.push({type,inputType:v.inputType,trusted:v.isTrusted}));}e.scrollIntoView();return true})()')
 js('(()=>{let e=document.getElementById("native-multiline");if(!e.__clipboardEvents){e.__clipboardEvents=true;for(let type of ["copy","cut","paste"])e.addEventListener(type,v=>window.__multilineEvents.push({type,trusted:v.isTrusted}));}return true})()')
 model('Alpha\nBeta',8)
 if a.browser=='firefox':control('firefox-screenshot')
 else:ab('screenshot','--screenshot-dir',str(out.resolve()))
 key(30,'control');s=wait(state,lambda s:s['start']==s['end']==6)
 check(label+'-native-line-start',s['value']=='Alpha\nBeta',state=s)
 key(18,'control');s=wait(state,lambda s:s['start']==s['end']==10)
 check(label+'-native-line-end',s['value']=='Alpha\nBeta',state=s)
 js('(window.__multilineEvents=[],true)');key(28)
 s=wait(state,lambda s:s['value']=='Alpha\nBeta\n')
 check(label+'-native-newline-events',s['start']==s['end']==11 and [e['inputType'] for e in s['events'] if e['type']=='input']==['insertLineBreak'] and all(e['trusted'] for e in s['events']),state=s)
 js('(()=>{window.__multilineEvents=[];document.getElementById("native-multiline").addEventListener("beforeinput",e=>e.preventDefault(),{once:true});return true})()');key(28)
 s=wait(state,lambda s:any(e['type']=='beforeinput' for e in s['events']))
 check(label+'-newline-cancellation',s['value']=='Alpha\nBeta\n' and not any(e['type']=='input' for e in s['events']),state=s)
 key(44,'shift');s=wait(state,lambda s:s['value']=='Alpha\nBeta\nZ')
 check(label+'-native-insertion',s['start']==s['end']==12,state=s)
 model('日本語Café🙂\nNext',9);key(44,'shift');s=wait(state,lambda s:s['value']=='日本語Café🙂Z\nNext')
 check(label+'-utf16-selection',s['start']==s['end']==10,state=s)
 model('Alpha\nBeta',8)
 js('(()=>{document.getElementById("native-multiline").addEventListener("keydown",e=>e.preventDefault(),{once:true});return true})()');key(30,'control')
 s=wait(state,lambda s:any(e['type']=='keydown' for e in s['events']))
 check(label+'-keydown-cancellation',s['start']==s['end']==8,state=s)
 model('Alpha\nBeta',6,10);key(46,'alt');wait(state,lambda s:any(e['type']=='copy' for e in s['events']));model('',0);key(47,'alt')
 s=wait(state,lambda s:s['value']=='Beta')
 check(label+'-native-clipboard-controller',s['start']==s['end']==4,state=s)
 model('Read only\nSecond',0,readonly=True);key(44,'shift')
 s=wait(state,lambda s:any(e['type']=='keydown' for e in s['events']))
 check(label+'-read-only',s['value']=='Read only\nSecond' and not any(e['type']=='input' for e in s['events']),state=s)
try:
 initial=control('status');pid=initial['browser'] if a.browser=='firefox' else a.browser_pid
 window=next(w for w in initial['windows'] if w['pid']==pid and w['level']==0)
 control('shell',text='activate '+str(window['id']))
 wait(lambda:control('status'),lambda s:any(w['pid']==pid and w['flags']&1 for w in s['windows']))
 fields('before-host-loss')
 if a.restart:
  host=control('status')['host'];control('restart-host')
  wait(lambda:control('status'),lambda s:s['host'] and s['host']!=host and any(w['pid']==s['host'] and w['level']==20 and not w['flags']&(2|32) for w in s['windows']),30)
  fields('after-host-loss')
finally:
 if a.browser=='chromium':ab('close')
print(json.dumps(dict(passed=len(rows))))
