#!/usr/bin/env python3
import argparse,json,shlex,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser(description='Check native Chromium clipboard commands through real application paths.');p.add_argument('--ssh-config',type=Path,required=True);p.add_argument('--ssh-host',default='lima-nextspace-gui');p.add_argument('--session',required=True);p.add_argument('--cdp',required=True);p.add_argument('--pasteboard-probe',required=True);p.add_argument('--fixture',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--negative',action='store_true');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
ssh=['ssh','-F',str(a.ssh_config),a.ssh_host];ab=['agent-browser','--session',a.session,'--cdp',a.cdp];rows=[]
def remote(code):return json.loads(subprocess.check_output(ssh+[shlex.join(['python3','-c',code])],text=True))
def controls(commands):
 code="import socket,json;from pathlib import Path\nroot=Path("+repr(a.fixture)+")\nresults=[]\nfor text in "+repr(commands)+":\n with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:\n  s.settimeout(15);s.connect(str(root/'control.sock'));s.send(json.dumps(dict(command=text)).encode());results.append(json.loads(s.recv(65536)))\nprint(json.dumps(results))"
 return remote(code)
def control(command):return controls([command])[0]
def key(code,*mods):
 commands=[f'key {c} 1' for c in mods]+[f'key {code} 1',f'key {code} 0']+[f'key {c} 0' for c in reversed(mods)]
 assert all(r['ok'] for r in controls(commands))
def js(script):return json.loads(subprocess.check_output(ab+['eval',script],text=True))
def action(*args):return subprocess.check_output(ab+list(args),text=True)
def views():
 return remote("import json;from pathlib import Path\nlines=[l for l in (Path("+repr(a.fixture)+")/'hook.log').read_text().splitlines() if l.startswith('views-state ')]\nr=dict(t.split('=',1) for t in lines[-1].split()[1:]);print(json.dumps(dict(value=bytes.fromhex(r['value_hex']).decode(),start=int(r['start']),end=int(r['end']),focused=int(r['focused']))))")
def wait(read,predicate):
 deadline=time.monotonic()+5
 while True:
  value=read()
  if predicate(value) or time.monotonic()>=deadline:return value
  time.sleep(.025)
def check(case,condition,**details):
 rows.append(dict(case=case,passed=bool(condition),**details));(a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
 if not a.negative:assert condition,rows[-1]
def pb(mode):
 return remote("import json,subprocess,os;from pathlib import Path\nr=Path("+repr(a.fixture)+");env=dict(os.environ,**json.loads((r/'runtime.json').read_text()));p=subprocess.run(["+repr(a.pasteboard_probe)+","+repr(mode)+"],env=env,capture_output=True,text=True,timeout=5);print(json.dumps(dict(code=p.returncode,text=p.stdout)))")
def address_focus():
 assert all(r['ok'] for r in controls(['pointer 80 391','button 272']));key(38,29)
 wait(views,lambda s:s['focused']==1)
 # Enter the real address field to activate its platform input context.
 assert all(r['ok'] for r in controls(['pointer 220 60','button 272']))
def clear_address():
 key(102);key(107,42);key(14);actual=wait(views,lambda s:s['value']=='')
 check('address-cleared',actual['value']=='',state=actual)
def source():
 address_focus();clear_address()
 for c in 'Alpha beta':
  code={'a':30,'l':38,'p':25,'h':35,' ':57,'b':48,'e':18,'t':20}[c.lower()];key(code,*([42] if c.isupper() else []))
 actual=wait(views,lambda s:s['value']=='Alpha beta');check('actual-address-source',actual['value']=='Alpha beta',state=actual)
 key(102);key(107,42);key(46,56)
 def oracle():
  js("(()=>{document.querySelector('#clipboard-oracle')?.remove();let e=document.createElement('textarea');e.id='clipboard-oracle';document.body.append(e);return true})()")
  action('click','#clipboard-oracle');action('press','Control+v');return wait(lambda:js("document.querySelector('#clipboard-oracle').value"),lambda v:v=='Alpha beta')
 assert pb('--empty')['code']==0;value=oracle();check('real-platform-clipboard',value=='Alpha beta',value=value)
 empty=pb('--export-text');check('helper-storage-empty',empty==dict(code=1,text=''),snapshot=empty)
def reset_web():
 js("window.__pendingReload=true;location.reload();true")
 action('wait','--fn','document.readyState==="complete" && !!window.events && !window.__pendingReload')
 js("(()=>{window.__clipboardEvents=[];for(let type of ['copy','cut','paste','beforeinput','input'])document.addEventListener(type,e=>__clipboardEvents.push({type:e.type,id:e.target.id,trusted:e.isTrusted,inputType:e.inputType??null}));return true})()")
def seed(identifier='normal',value='Hello',start=0,end=None):
 action('click','#'+identifier)
 if end is None:end=len(value.encode('utf-16-le'))//2
 js('(()=>{let e=document.getElementById('+json.dumps(identifier)+');e.value='+json.dumps(value)+';e.setSelectionRange('+str(start)+','+str(end)+');window.__clipboardEvents=[];return true})()')
def state(identifier='normal'):
 return js('(()=>{let e=document.getElementById('+json.dumps(identifier)+');return {value:e.value,start:e.selectionStart,end:e.selectionEnd}})()')
def webkey(name):
 letter={'copy':'c','cut':'x','paste':'v'}[name]
 js("(()=>{window.__clipboardKeyUp=false;document.addEventListener('keyup',function done(e){if(e.key==="+json.dumps(letter)+"){__clipboardKeyUp=true;document.removeEventListener('keyup',done,true)}},true);return true})()")
 key({'copy':46,'cut':45,'paste':47}[name],56)
 action('wait','--fn','window.__clipboardKeyUp===true')
def edits():return js('window.__clipboardEvents')
def unchanged(case,identifier='normal',value='Hello',start=0,end=5):
 actual=state(identifier);check(case,actual==dict(value=value,start=start,end=end),state=actual)
def extended_checks():
 reset_web();seed();webkey('copy');unchanged('web-copy-preserves-selection')
 changes=edits();check('web-trusted-copy',changes==[dict(type='copy',id='normal',trusted=True,inputType=None)],events=changes)
 webkey('cut');actual=wait(state,lambda v:v['value']=='');check('web-cut',actual==dict(value='',start=0,end=0),state=actual)
 changes=edits()[1:];check('web-trusted-cut-events',[e['type'] for e in changes]==['cut','beforeinput','input'] and all(e['trusted'] for e in changes) and all(e['inputType']=='deleteByCut' for e in changes[1:]),events=changes)
 js('window.__clipboardEvents=[];true');webkey('paste');actual=wait(state,lambda v:v['value']=='Hello');check('web-paste',actual==dict(value='Hello',start=5,end=5),state=actual)
 changes=edits();check('web-trusted-paste-events',[e['type'] for e in changes]==['paste','beforeinput','input'] and all(e['trusted'] for e in changes) and all(e['inputType']=='insertFromPaste' for e in changes[1:]),events=changes)
 js('document.execCommand("undo");true');check('paste-keeps-engine-undo',state()['value']=='',state=state())
 js('document.execCommand("undo");true');check('cut-keeps-engine-undo',state()['value']=='Hello',state=state())
 reset_web();text='日本語Café🙂';seed('unicode',text);webkey('copy');seed(value='');webkey('paste')
 actual=wait(state,lambda v:v['value']==text);length=len(text.encode('utf-16-le'))//2
 check('unicode-copy-paste',actual==dict(value=text,start=length,end=length),state=actual)
 reset_web();seed();webkey('copy')
 for event in ['keydown','paste','beforeinput']:
  reset_web();seed()
  js("normal.addEventListener('keydown',e=>{if(e.key==='v')e.preventDefault()});true" if event=='keydown' else 'normal.addEventListener('+json.dumps(event)+',e=>e.preventDefault(),{once:true});true')
  webkey('paste');unchanged('cancel-paste-'+event);check('cancel-paste-'+event+'-no-input',not any(e['type']=='input' for e in edits()),events=edits())
 for event in ['cut','beforeinput']:
  reset_web();seed();js('normal.addEventListener('+json.dumps(event)+',e=>e.preventDefault(),{once:true});true');webkey('cut');unchanged('cancel-cut-'+event)
 reset_web();seed();js("normal.addEventListener('copy',e=>{e.clipboardData.setData('text/plain','Custom clipboard');e.preventDefault()},{once:true});true");webkey('copy');seed(value='');webkey('paste')
 actual=wait(state,lambda v:v['value']=='Custom clipboard');check('custom-copy-data',actual==dict(value='Custom clipboard',start=16,end=16),state=actual)
 reset_web();seed('limited','abc',1,3);webkey('paste');actual=wait(lambda:state('limited'),lambda v:v['value']=='aCus');check('paste-maxlength',actual==dict(value='aCus',start=4,end=4),state=actual)
 reset_web();seed('readonly');webkey('cut');unchanged('readonly-cut','readonly');webkey('paste');unchanged('readonly-paste','readonly');webkey('copy');seed(value='');webkey('paste');actual=wait(state,lambda v:v['value']=='Hello');check('readonly-copy',actual['value']=='Hello',state=actual)
 for name in ['copy','cut']:
  reset_web();seed('password');webkey(name);unchanged('secure-'+name,'password');seed(value='');webkey('paste');actual=wait(state,lambda v:v['value']=='Hello');check('secure-'+name+'-keeps-clipboard',actual['value']=='Hello',state=actual)
 reset_web();seed('password');webkey('paste');actual=wait(lambda:state('password'),lambda v:v['start']==5);check('secure-paste',actual==dict(value='Hello',start=5,end=5),state=actual)
 reset_web();seed();js("normal.addEventListener('beforeinput',e=>{e.preventDefault();e.target.value='Script';e.target.setSelectionRange(2,2)},{once:true});true");webkey('paste');unchanged('paste-script-model',value='Script',start=2,end=2)
 reset_web();seed();js("normal.addEventListener('paste',e=>e.target.remove(),{once:true});true");webkey('paste');check('paste-handler-removes-field',js('!document.getElementById("normal")'))
 reset_web();seed();webkey('copy');check('remaining-field-usable',any(e['type']=='copy' and e['trusted'] for e in edits()))

launch=remote("import json;from pathlib import Path;print((Path("+repr(a.fixture)+")/'launch.json').read_text())")
check('owned-text-fixture',js('location.href')==launch['command'][-1] and js('document.title')=='Blink native text transport')
w=next(w for w in control('windows') if w['pid']==launch['pids'][-1] and w['visible'])
assert control(f"raise {w['id']}")['ok'] and control(f"focus {w['id']}")['ok']
for name in ['frontend','web']:
 source()
 before=remote("import json;from pathlib import Path;print(len((Path("+repr(a.fixture)+")/'helper.jsonl').read_text().splitlines()))")
 if name=='frontend':
  address_focus();clear_address();key(47,56);actual=wait(views,lambda s:s['value']=='Alpha beta')
 else:
  action('click','#normal');js("(()=>{normal.value='';normal.setSelectionRange(0,0);return true})()");key(47,56)
  actual=wait(lambda:js("({value:normal.value,start:normal.selectionStart,end:normal.selectionEnd})"),lambda s:s['value']=='Alpha beta')
 check(name+'-cold-paste',actual['value']=='Alpha beta',state=actual)
 if not a.negative:
  callbacks=remote("import json;from pathlib import Path;lines=(Path("+repr(a.fixture)+")/'helper.jsonl').read_text().splitlines();print(json.dumps([json.loads(l) for l in lines["+str(before)+":] if '\"event\": \"native-command\"' in l]))")
  check(name+'-native-command-callbacks',any(r['phase']==0 and r['result']==1 for r in callbacks) and any(r['phase']==1 for r in callbacks),callbacks=callbacks)
if a.negative:assert [r['case'] for r in rows if not r['passed']]==['frontend-cold-paste','web-cold-paste'],rows
else:extended_checks()
print(json.dumps(dict(checks=len(rows),passed=sum(r['passed'] for r in rows),negative=a.negative)))
