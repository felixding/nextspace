#!/usr/bin/env python3
"""Check native global menu keys after real web event cancellation/IPC."""
import argparse,ctypes as C,json,socket,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'FirefoxNativeUI'))
from marionette import Marionette
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ChromiumScrollers'))
from native_controls import ControlInputRequest,MAGIC
from helper import Response
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--fixture',type=Path,required=True);p.add_argument('--port',type=int,required=True)
p.add_argument('--expected-pid',type=int,required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);rows=[];m=Marionette(a.port)
host=json.loads((a.fixture/'menu-binding.json').read_text());launch=json.loads((a.fixture/'launch.json').read_text())
assert host['association']=='workspace' and host['owner']==a.expected_pid==launch['pids'][-1]
def check(case,passed,**data):
 rows.append(dict(case=case,passed=bool(passed),**data));(a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
def wait(read,predicate):
 end=time.monotonic()+10
 while True:
  value=read()
  if predicate(value):return value
  assert time.monotonic()<end,value
  time.sleep(.015)
def control(command):
 with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:
  s.settimeout(15);s.connect(str(a.fixture/'control.sock'));s.send(json.dumps(dict(command=command)).encode());return json.loads(s.recv(65536))
def context(value):m.command('Marionette:SetContext',dict(value=value))
def js(script):return m.command('WebDriver:ExecuteScript',dict(script=script,args=[]))['value']
def trace():return [json.loads(l) for l in Path(host['log']).read_text().splitlines()]
def key(code,*modifiers):
 for command in [*(f'key {c} 1' for c in modifiers),f'key {code} 1',f'key {code} 0',*(f'key {c} 0' for c in reversed(modifiers))]:assert control(command)['ok']
def tabs():return m.command('WebDriver:GetWindowHandles')
def original():
 context('content');m.command('WebDriver:SwitchToWindow',dict(handle=initial))
 browser=next(w for w in control('windows') if w['pid']==a.expected_pid and w['id']==host['window'])
 assert control('focus '+str(browser['id']))['ok']
 js("document.body.tabIndex=0;document.body.focus();window.__globalKeys=[];for(let type of ['keydown','keyup'])document.addEventListener(type,e=>window.__globalKeys.push({type:e.type,key:e.key,trusted:e.isTrusted,prevented:e.defaultPrevented}),{capture:false});return true")
 check('body-focus-is-outside-native-text-fields',js('return document.activeElement===document.body'))
def new_tab(label):
 before=set(tabs());start=len(trace());hook_start=len((a.fixture/'hook.log').read_text())
 key(20,56)
 after=wait(tabs,lambda hs:len(hs)==len(before)+1)
 check(label+'-creates-one-real-tab',len(after)==len(before)+1)
 events=wait(lambda:trace()[start:],lambda rs:any(r['event']=='application-command' for r in rs))
 queued=[r for r in events if r['event']=='application-command-queued'];executed=[r for r in events if r['event']=='application-command']
 check(label+'-one-native-menu-command',len(queued)==len(executed)==1 and queued[0]['native']==executed[0]['native'],queued=queued,executed=executed)
 hook=(a.fixture/'hook.log').read_text()[hook_start:]
 check(label+'-native-query-then-global-execution',hook.count('native-global-menu-key execute=1')==1 and 'native-global-menu-key execute=0' in hook)
 new=next(h for h in after if h not in before);m.command('WebDriver:SwitchToWindow',dict(handle=new));m.command('WebDriver:CloseWindow');m.command('WebDriver:SwitchToWindow',dict(handle=initial))
 context('chrome')
 state=js("let bar=document.getElementById('toolbar-menubar');return {height:bar.getBoundingClientRect().height,inactive:bar.hasAttribute('inactive'),native:document.getElementById('main-menubar').hasAttribute('native')}")
 check(label+'-retains-hidden-internal-menubar',state==dict(height=0,inactive=True,native=True),state=state)
 context('content')
try:
 session=m.command('WebDriver:NewSession',{});check('owned-browser',session['capabilities']['moz:processID']==a.expected_pid)
 initial=tabs()[0];m.command('WebDriver:SwitchToWindow',dict(handle=initial))
 check('global-menu-key-binding-installed','native Gecko global menu key binding installed' in (a.fixture/'hook.log').read_text())
 original();new_tab('body-global-shortcut')
 original();js("let button=document.createElement('button');button.id='global-menu-focus';button.textContent='Ordinary focus';document.body.append(button);button.focus();return true")
 check('ordinary-button-is-focused',js("return document.activeElement.id==='global-menu-focus'"));new_tab('button-global-shortcut')
 original();before=set(tabs());start=len(trace());hook_start=len((a.fixture/'hook.log').read_text())
 js("window.__globalCancelled=false;document.addEventListener('keydown',function cancel(e){if(e.key==='t'&&e.altKey){e.preventDefault();window.__globalCancelled=e.defaultPrevented;document.removeEventListener('keydown',cancel,true)}},true);return true")
 key(20,56);wait(lambda:js("return window.__globalCancelled&&window.__globalKeys.some(e=>e.type==='keyup'&&e.key==='t')"),bool)
 time.sleep(.15)
 check('web-cancelled-global-shortcut-preserves-tabs',set(tabs())==before)
 check('web-cancelled-global-shortcut-queues-no-action',not [r for r in trace()[start:] if r['event']=='application-command-queued'])
 check('cancelled-key-keeps-real-native-reservation-query','native-global-menu-key execute=0' in (a.fixture/'hook.log').read_text()[hook_start:])
 check('cancelled-key-never-executes-native-action','native-global-menu-key execute=1' not in (a.fixture/'hook.log').read_text()[hook_start:])
 original();before=set(tabs());start=len(trace())
 js("document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'t',code:'KeyT',altKey:true,bubbles:true,cancelable:true}));return true")
 check('untrusted-synthetic-shortcut-preserves-tabs',set(tabs())==before)
 check('untrusted-synthetic-shortcut-queues-no-action',not [r for r in trace()[start:] if r['event']=='application-command-queued'])
 original();start=len(trace());key(36)
 delivered=wait(lambda:js("return window.__globalKeys.filter(e=>e.key==='j')"),lambda rs:any(r['type']=='keyup' for r in rs))
 check('unmatched-key-keeps-trusted-web-delivery',any(r['type']=='keydown' and r['trusted'] and not r['prevented'] for r in delivered))
 check('unmatched-key-executes-no-menu-command',not [r for r in trace()[start:] if r['event']=='application-command-queued'])
 active=set()
 for row in trace():
  if row['event']=='native-notifier' and row['operation']==15 and row['accepted']:active.add(row['process'])
  elif (row['event'] in ['native-notifier-disconnect','native-notifier-owner-exit'] or
        row['event']=='native-notifier' and row['operation']==16 and row['accepted']):active.discard(row['process'])
 check('forged-global-key-target-has-real-notifier',bool(active))
 process=next(iter(active));arguments=host['arguments'];endpoint=arguments[arguments.index('--socket')+1]
 before=set(tabs());start=len(trace())
 with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as client:
  client.settimeout(8);client.connect(endpoint)
  for execute in [0,1]:
   request=ControlInputRequest(magic=MAGIC,operation=27,process=process,type=0,modifiers=2,key=0,
       text_size=1,unmodified_size=1,focused=execute)
   client.send(bytes(request)+b'tt');reply=Response.from_buffer_copy(client.recv(128*1024))
   check('other-client-cannot-'+('execute' if execute else 'query')+'-global-menu-key',reply.parts[3].x==0)
 check('forged-global-key-executes-no-application-command',set(tabs())==before and not [r for r in trace()[start:] if r['event']=='application-command-queued'])
 check('no-menu-callback-errors',not [r for r in trace() if r['event'] in ['callback-error','native-submenu-error','application-error','layout-error']])
 print(json.dumps(dict(passed=len(rows))))
finally:
 control('key 56 0');m.close()
