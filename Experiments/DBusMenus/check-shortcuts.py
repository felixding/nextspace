#!/usr/bin/env python3
"""Check GNUstep menu shortcuts and editing in the same owned Firefox host."""
import argparse,json,socket,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'FirefoxNativeUI'))
from marionette import Marionette

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--fixture',type=Path,required=True);p.add_argument('--port',type=int,required=True)
p.add_argument('--expected-pid',type=int,required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);rows=[]
host=json.loads((a.fixture/'menu-binding.json').read_text());launch=json.loads((a.fixture/'launch.json').read_text())
assert host['shared_helper'] and host['owner']==a.expected_pid==launch['pids'][-1]
assert host['pid']==launch['pids'][-2]
log_path=Path(host['log']);m=Marionette(a.port)
def check(case,passed,**data):
 rows.append(dict(case=case,passed=bool(passed),**data));(a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
def wait(read,predicate):
 end=time.monotonic()+8
 while True:
  value=read()
  if predicate(value):return value
  assert time.monotonic()<end,value
  time.sleep(.015)
def control(command):
 with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:
  s.settimeout(15);s.connect(str(a.fixture/'control.sock'));s.send(json.dumps(dict(command=command)).encode());return json.loads(s.recv(65536))
def context(name):m.command('Marionette:SetContext',dict(value=name))
def js(script):return m.command('WebDriver:ExecuteScript',dict(script=script,args=[]))['value']
def events(start):return [json.loads(line) for line in log_path.read_text().splitlines()[start:]]
def key(code,letter,*modifiers):
 js("window.__nativeShortcutUp=false;document.addEventListener('keyup',function done(e){if(e.key.toLowerCase()==="+json.dumps(letter)+"){window.__nativeShortcutUp=true;document.removeEventListener('keyup',done,true)}},true);return true")
 for command in [*(f'key {c} 1' for c in modifiers),f'key {code} 1',f'key {code} 0',*(f'key {c} 0' for c in reversed(modifiers))]:assert control(command)['ok']
 wait(lambda:js('return window.__nativeShortcutUp'),bool)
def state(frontend):
 return js("let e="+('gURLBar.inputField' if frontend else 'normal')+";return {value:e.value,start:e.selectionStart,end:e.selectionEnd}")
def token(title):
 path=Path(host['output'])/'native-items.json';old=path.stat().st_mtime_ns
 assert control('menu-broker '+json.dumps(dict(operation='snapshot')))['accepted']
 wait(lambda:path.stat().st_mtime_ns,lambda value:value!=old)
 return next(i['command'] for i in json.loads(path.read_text()) if i['title']==title)
def application_key(label,title,frontend,expected,shift=False):
 identity=token(title);start=len(log_path.read_text().splitlines())
 key({'Cut':45,'Undo':44,'Redo':44}[title],{'Cut':'x','Undo':'z','Redo':'z'}[title],56,*([42] if shift else []))
 actual=wait(lambda:state(frontend),lambda v:v['value']==expected)
 trace=wait(lambda:events(start),lambda rows:any(e['event']=='application-command' and e.get('native')==identity for e in rows))
 queued=[e for e in trace if e['event']=='application-command-queued' and e.get('native')==identity]
 executed=[e for e in trace if e['event']=='application-command' and e.get('native')==identity]
 check(label+'-native-menu-shortcut',len(queued)==len(executed)==1,state=actual,native=identity)
try:
 session=m.command('WebDriver:NewSession',{});check('owned-browser',session['capabilities']['moz:processID']==a.expected_pid)
 m.command('WebDriver:SwitchToWindow',dict(handle=m.command('WebDriver:GetWindowHandles')[0]))
 context('content');m.command('WebDriver:Refresh')
 wait(lambda:js("return document.readyState==='complete'&&!!document.getElementById('normal')"),bool)
 root=next(w for w in control('windows') if w['pid']==host['pid'] and w['visible'])
 check('native-menu-and-editors-share-helper',root['pid']==launch['pids'][-2],pid=root['pid'])
 for frontend in [False,True]:
  label='address' if frontend else 'web';expected='Address undo target' if frontend else 'Web undo target'
  context('content')
  js("window.__nativeShortcutClick=false;document.addEventListener('mouseup',()=>window.__nativeShortcutClick=true,{once:true});return true")
  browser=next(w for w in control('windows') if w['pid']==a.expected_pid and w['visible'])
  for command in [f"focus {browser['id']}",'pointer 400 500','button 272']:assert control(command)['ok']
  wait(lambda:js('return window.__nativeShortcutClick'),bool)
  if frontend:
   context('chrome');js("gURLBar._setValue("+json.dumps(expected)+",{allowTrim:true,valueIsTyped:true});gURLBar.setPageProxyState('invalid');gURLBar.inputField.focus();gURLBar.inputField.select();return true")
  else:js('normal.value='+json.dumps(expected)+';normal.focus();normal.select();return true')
  application_key(label+'-cut','Cut',frontend,'')
  application_key(label+'-undo','Undo',frontend,expected)
  application_key(label+'-redo','Redo',frontend,'',shift=True)
  application_key(label+'-restore','Undo',frontend,expected)
  start=len(log_path.read_text().splitlines());key(30,'a',29);actual=state(frontend)
  check(label+'-native-emacs-control-a',actual==dict(value=expected,start=0,end=0),state=actual)
  key(18,'e',29);actual=state(frontend)
  check(label+'-native-emacs-control-e',actual==dict(value=expected,start=len(expected),end=len(expected)),state=actual)
  check(label+'-emacs-navigation-executes-no-menu-command',not any(e['event']=='application-command-queued' for e in events(start)))
 print(json.dumps(dict(passed=len(rows))))
finally:
 for code in [56,29,42,125]:control(f'key {code} 0')
 m.close()
