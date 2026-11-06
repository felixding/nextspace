#!/usr/bin/env python3
"""Exercise native commands through Gecko controllers and a real native app."""
import argparse,json,os,socket,subprocess,time
from pathlib import Path
from marionette import Marionette
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--port',type=int,required=True);p.add_argument('--expected-pid',type=int,required=True)
p.add_argument('--fixture',type=Path,required=True);p.add_argument('--pasteboard-probe',type=Path,required=True)
p.add_argument('--native-text-app',type=Path,required=True);p.add_argument('--backend',required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--command-filter',action='store_true',help='Require application command validation with empty helper storage')
p.add_argument('--application-menus',action='store_true',help='Require the shared native menu queue and exported activation path')
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);results=[];m=Marionette(a.port);native_app=None
if a.application_menus:
 if not a.command_filter:p.error('--application-menus requires --command-filter')
 menu_binding=json.loads((a.fixture/'menu-binding.json').read_text())
 assert menu_binding['shared_helper'] and menu_binding['owner']==a.expected_pid
runtime=dict(os.environ,**json.loads((a.fixture/'runtime.json').read_text()));runtime.pop('LD_PRELOAD',None)
def command(text):
 with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:
  s.settimeout(15);s.connect(str(a.fixture/'control.sock'));s.send(json.dumps(dict(command=text)).encode());return json.loads(s.recv(65536))
def physical_key(code,*modifiers):
 for c in modifiers:assert command(f'key {c} 1')['ok']
 for pressed in [1,0]:assert command(f'key {code} {pressed}')['ok']
 for c in reversed(modifiers):assert command(f'key {c} 0')['ok']
def key(name,native=False):
 letter={'copy':'c','cut':'x','paste':'v'}[name]
 if not native:
  js("window.__commandKeyUp=false;document.addEventListener('keyup',function done(e){if(e.key==="+json.dumps(letter)+"){window.__commandKeyUp=true;document.removeEventListener('keyup',done,true)}},true);return true")
 physical_key({'copy':46,'cut':45,'paste':47}[name],56)
 if not native:wait(lambda:js('return window.__commandKeyUp'))
def focus_window(window):
 for c in [f"raise {window['id']}",f"focus {window['id']}"]:assert command(c)['ok']
def browser_focus():
 focus_window(browser)
 for c in ['pointer 400 500','button 272']:assert command(c)['ok']
def wait(predicate,timeout=5):
 deadline=time.monotonic()+timeout
 while True:
  value=predicate()
  if value:return value
  assert time.monotonic()<deadline,'condition timed out'
  time.sleep(.02)
def js(script):return m.command('WebDriver:ExecuteScript',dict(script=script,args=[]))['value']
def context(name):m.command('Marionette:SetContext',dict(value=name))
def check(case,condition,**details):
 results.append(dict(case=case,passed=bool(condition),**details));(a.output/'results.json').write_text(json.dumps(results,indent=2,ensure_ascii=False)+'\n');assert condition,results[-1]
def clipboard():
 result=subprocess.run([str(a.pasteboard_probe),'--export-text'],env=runtime,text=True,capture_output=True,timeout=5)
 assert result.returncode in (0,1),result.stderr
 return result.stdout if result.returncode==0 else None
def clipboard_generation():
 return int(subprocess.check_output([str(a.pasteboard_probe),'--change-count'],env=runtime,text=True,timeout=5))
def frontend_seed(text,typed=True):
 dismiss_menubar()
 return js("gURLBar._setValue("+json.dumps(text)+",{allowTrim:true,valueIsTyped:"+str(typed).lower()+"});gURLBar.setPageProxyState('invalid');gURLBar.inputField.focus();gURLBar.inputField.select();return {value:gURLBar.value,clipboard:gURLBar._getSelectedValueForClipboard()}")
def dismiss_menubar():
 # A standalone Alt release activates Firefox's own menu. Restore the fixture
 # through real Escape input before the next independent editing case.
 if js("let m=document.getElementById('toolbar-menubar');return m?.getAttribute('autohide')==='true'&&!m.hasAttribute('inactive')"):
  physical_key(1);wait(lambda:js("return document.getElementById('toolbar-menubar').hasAttribute('inactive')"))
def frontend_state():return js("let e=gURLBar.inputField;return {value:e.value,start:e.selectionStart,end:e.selectionEnd}")
def state(identifier='normal'):return js('let e=document.getElementById('+json.dumps(identifier)+');return {value:e.value,start:e.selectionStart,end:e.selectionEnd}')
def web_seed(identifier='normal',value='Hello',start=0,end=None):
 context('chrome');dismiss_menubar();js('gBrowser.selectedBrowser.focus();return true');context('content')
 end=len(value.encode('utf-16-le'))//2 if end is None else end
 js('let e=document.getElementById('+json.dumps(identifier)+');e.value='+json.dumps(value)+';e.focus();e.setSelectionRange('+str(start)+','+str(end)+');window.__commandEvents=[];return true')
def events():return js('return window.__commandEvents')
def web_reset():
 context('chrome');js('gBrowser.selectedBrowser.focus();return true')
 context('content');m.command('WebDriver:Refresh')
 js("window.__commandEvents=[];for(let type of ['copy','cut','paste','beforeinput','input'])document.addEventListener(type,e=>window.__commandEvents.push({type:e.type,id:e.target.id,trusted:e.isTrusted,inputType:e.inputType??null}));return true")
def unchanged(case,identifier='normal',value='Hello',start=0,end=5):
 actual=state(identifier);check(case,actual==dict(value=value,start=start,end=end),state=actual)
def modifier_checks(label,seed,read):
 for code,name in [(56,'Alt'),(29,'Control'),(42,'Shift'),(125,'Super')]:
  seed();before=read();js("window.__modifierEdits=[];let e=document.activeElement;for(let type of ['beforeinput','input'])e.addEventListener(type,e=>window.__modifierEdits.push(e.type),{once:true});return true")
  for pressed in [1,0]:
   event='keydown' if pressed else 'keyup'
   expected='Meta' if name=='Super' else name
   js("window.__modifierDelivered=false;document.addEventListener("+json.dumps(event)+",function done(e){if(e.key==="+json.dumps(expected)+"){window.__modifierDelivered=true;document.removeEventListener("+json.dumps(event)+",done,true)}},true);return true")
   assert command(f'key {code} {pressed}')['ok'];wait(lambda:js('return window.__modifierDelivered'));actual=read()
   check(label+'-'+name+('-down' if pressed else '-up'),actual==before,state=actual)
  changes=js('return window.__modifierEdits');check(label+'-'+name+'-no-edit-events',not changes,events=changes)
try:
 session=m.command('WebDriver:NewSession',{});check('owned-browser',session['capabilities']['moz:processID']==a.expected_pid)
 browser=next(w for w in command('windows') if w['pid']==a.expected_pid and w['visible'] and w['presented']);browser_focus()
 for code in [56,29,42,125]:assert command(f'key {code} 0')['ok']
 context('chrome');modifier_checks('frontend-modifier',lambda:frontend_seed('Selected text'),frontend_state)
 context('chrome');js('gBrowser.selectedBrowser.focus();return true');context('content')
 for identifier in ['normal','password']:
  modifier_checks(identifier+'-modifier',lambda:web_seed(identifier),lambda:state(identifier))
 if a.command_filter:
  for name in ['frontend','web']:
   context('chrome');expected='Cold '+name+':日本語🙂';frontend_seed(expected)
   js("gURLBar._copyCutController.doCommand('cmd_copy');return true")
   if name=='frontend':frontend_seed('');read=frontend_state
   else:web_seed(value='');read=state
   subprocess.run([str(a.pasteboard_probe),'--empty'],env=runtime,check=True,timeout=5)
   empty=subprocess.run([str(a.pasteboard_probe),'--export-text'],env=runtime,capture_output=True,text=True,timeout=5)
   check(name+'-helper-storage-empty',empty.returncode==1 and not empty.stdout)
   if a.application_menus:
    control_snapshot=command('menu-broker '+json.dumps(dict(operation='snapshot')));assert control_snapshot['accepted']
    paste_identity=next(i['command'] for i in json.loads((Path(menu_binding['output'])/'native-items.json').read_text()) if i['title']=='Paste')
   before=len((a.fixture/'helper.jsonl').read_text().splitlines());key('paste');wait(lambda:read()['value']==expected)
   actual=read();length=len(expected.encode('utf-16-le'))//2
   check(name+'-paste-without-helper-data',actual==dict(value=expected,start=length,end=length),state=actual)
   trace=[json.loads(line) for line in (a.fixture/'helper.jsonl').read_text().splitlines()[before:]]
   if a.application_menus:
    queued=[r for r in trace if r['event']=='application-command-queued' and r.get('native')==paste_identity]
    executed=[r for r in trace if r['event']=='application-command' and r.get('native')==paste_identity]
    check(name+'-native-application-menu-command',len(queued)==len(executed)==1,queued=queued,executed=executed)
   else:
    callbacks=[r for r in trace if r['event']=='native-command']
    check(name+'-native-application-command-callbacks',any(r['phase']==0 and r['result']==1 for r in callbacks) and any(r['phase']==1 for r in callbacks),callbacks=callbacks)
 native_text='Native source: 日本語, 한글, emoji 😸';source=a.output/'native-source.txt';source.write_text(native_text)
 log=(a.output/'native-app.log').open('w')
 native_app=subprocess.Popen([str(a.native_text_app),'-NSUseRunningCopy','NO','-GSBackend',a.backend,'-NSOpen',str(source)],env=dict(runtime,WAYLAND_DEBUG='client'),stdout=log,stderr=log)
 native=wait(lambda:next((w for w in command('windows') if w['pid']==native_app.pid and w['visible'] and w['presented'] and w['width']>200 and source.stem in w['title']),None),timeout=15)
 (a.output/'native-window.json').write_text(json.dumps(native,indent=2)+'\n')
 focus_window(native)
 for c in [f"pointer {native['x']+native['width']//2} {native['y']+native['height']//2}",'button 272']:assert command(c)['ok']
 physical_key(30,56);key('copy',native=True);wait(lambda:clipboard()==native_text);check('real-native-application-copy',clipboard()==native_text)
 browser_focus();context('chrome');frontend_seed('');key('paste');wait(lambda:frontend_state()['value']==native_text)
 actual=frontend_state();check('native-to-frontend-paste',actual==dict(value=native_text,start=32,end=32),state=actual)
 # Spy only on the application's own custom controller, invoking it unchanged.
 js("window.__commandSpy=[];let c=gURLBar._copyCutController;window.__commandOriginal=c.doCommand;c.doCommand=function(command){window.__commandSpy.push(command);return window.__commandOriginal.call(this,command)};return true")
 initial=frontend_seed('https://example.invalid/日本語?q=space%20test',False);before=frontend_state();key('copy')
 check('frontend-application-copy-controller',js('return window.__commandSpy').count('cmd_copy')==1)
 check('frontend-copy-preserves-selection',frontend_state()==before,state=frontend_state())
 focus_window(native);wait(lambda:clipboard()==initial['clipboard']);check('frontend-formatted-system-clipboard',clipboard()==initial['clipboard'],display=initial['value'],clipboard=clipboard())
 generation=clipboard_generation()
 physical_key(30,56);key('paste',native=True);physical_key(30,56);key('copy',native=True)
 wait(lambda:clipboard_generation()>generation and clipboard()==initial['clipboard'])
 browser_focus();frontend_seed('');key('paste')
 try:wait(lambda:frontend_state()['value']==initial['clipboard'])
 except AssertionError:
  platform=js("let c=Cc['@mozilla.org/widget/clipboard;1'].getService(Ci.nsIClipboard);let controller=gURLBar.inputField.controllers.getControllerForCommand('cmd_paste');return {hasPlainText:c.hasDataMatchingFlavors(['text/plain'],c.kGlobalClipboard),pasteEnabled:controller.isCommandEnabled('cmd_paste')}")
  check('frontend-native-application-roundtrip',False,state=frontend_state(),clipboard=clipboard(),platform=platform)
 check('frontend-native-application-roundtrip',frontend_state()['value']==initial['clipboard'],state=frontend_state())
 frontend_seed('Cut me');key('cut');wait(lambda:frontend_state()['value']=='')
 check('frontend-application-cut-controller',js('return window.__commandSpy').count('cmd_cut')==1)
 check('frontend-cut-selection',frontend_state()==dict(value='',start=0,end=0),state=frontend_state())
 key('paste');wait(lambda:frontend_state()['value']=='Cut me');check('frontend-paste-after-cut',frontend_state()==dict(value='Cut me',start=6,end=6),state=frontend_state())
 js('gURLBar._copyCutController.doCommand=window.__commandOriginal;delete window.__commandOriginal;return true')
 web_reset();web_seed();key('copy');unchanged('web-copy-preserves-selection')
 copied=events();check('web-trusted-copy-event',copied==[dict(type='copy',id='normal',trusted=True,inputType=None)],events=copied)
 key('cut');wait(lambda:state()['value']=='');check('web-cut-state',state()==dict(value='',start=0,end=0),state=state())
 cut=events()[1:];check('web-trusted-cut-events',[e['type'] for e in cut]==['cut','beforeinput','input'] and all(e['trusted'] for e in cut) and all(e['inputType']=='deleteByCut' for e in cut[1:]),events=cut)
 js('window.__commandEvents=[];return true');key('paste');wait(lambda:state()['value']=='Hello');check('web-paste-state',state()==dict(value='Hello',start=5,end=5),state=state())
 pasted=events();check('web-trusted-paste-events',[e['type'] for e in pasted]==['paste','beforeinput','input'] and all(e['trusted'] for e in pasted) and all(e['inputType']=='insertFromPaste' for e in pasted[1:]),events=pasted)
 js('document.execCommand("undo");return true');check('paste-keeps-engine-undo',state()['value']=='',state=state())
 js('document.execCommand("undo");return true');check('cut-keeps-engine-undo',state()['value']=='Hello',state=state())
 for event,name in [('keydown','cancel-keydown'),('paste','cancel-paste'),('beforeinput','cancel-paste-beforeinput')]:
  web_reset();web_seed()
  js("normal.addEventListener('keydown',e=>{if(e.key==='v')e.preventDefault()});return true" if event=='keydown' else 'normal.addEventListener('+json.dumps(event)+',e=>e.preventDefault(),{once:true});return true')
  key('paste');unchanged(name)
  check(name+'-no-input',not any(e['type']=='input' for e in events()),events=events())
 for event in ['cut','beforeinput']:
  web_reset();web_seed();js('normal.addEventListener('+json.dumps(event)+',e=>e.preventDefault(),{once:true});return true');key('cut');unchanged('cancel-cut-'+event)
  check('cancel-cut-'+event+'-no-input',not any(e['type']=='input' for e in events()),events=events())
 web_reset();web_seed();js("normal.addEventListener('copy',e=>{e.clipboardData.setData('text/plain','Custom clipboard');e.preventDefault()},{once:true});return true")
 key('copy');web_seed(value='');key('paste');wait(lambda:state()['value']=='Custom clipboard');check('custom-copy-data-goes-through-gecko',state()==dict(value='Custom clipboard',start=16,end=16),state=state())
 web_reset();web_seed('limited','abc',1,3);key('paste');wait(lambda:state('limited')['value']=='aCus');check('paste-retains-engine-maxlength',state('limited')==dict(value='aCus',start=4,end=4),state=state('limited'))
 web_reset();web_seed('readonly');key('cut');unchanged('readonly-cut-blocked','readonly');key('paste');unchanged('readonly-paste-blocked','readonly')
 key('copy');web_seed(value='');key('paste');wait(lambda:state()['value']=='Hello');check('readonly-copy-allowed',state()['value']=='Hello',state=state())
 for name in ['copy','cut']:
  web_reset();web_seed('password');key(name);unchanged('secure-'+name+'-blocked','password')
  web_seed(value='');key('paste');wait(lambda:state()['value']=='Hello');check('secure-'+name+'-preserves-clipboard',state()['value']=='Hello',state=state())
 web_reset();web_seed('password');key('paste');wait(lambda:state('password')['start']==5);unchanged('secure-paste-allowed','password',start=5,end=5)
 web_reset();web_seed();js("normal.addEventListener('beforeinput',e=>{e.preventDefault();e.target.value='Script';e.target.setSelectionRange(2,2)},{once:true});return true");key('paste');unchanged('paste-beforeinput-script-model',value='Script',start=2,end=2)
 web_reset();web_seed();js("normal.addEventListener('beforeinput',e=>e.target.remove(),{once:true});return true");key('paste');check('paste-handler-removes-frame',js('return !document.getElementById("normal")'))
 web_reset();web_seed();key('copy');check('remaining-field-usable-after-frame-removal',any(e['type']=='copy' and e['trusted'] for e in events()))
 print(json.dumps(dict(passed=len(results))))
finally:
 for code in [56,29,42,125]:command(f'key {code} 0')
 try:
  context('chrome');js('if(window.__commandOriginal){gURLBar._copyCutController.doCommand=window.__commandOriginal;delete window.__commandOriginal;}return true')
 except (OSError,EOFError,RuntimeError):pass
 if native_app:
  native_app.terminate()
  try:native_app.wait(timeout=5)
  except subprocess.TimeoutExpired:native_app.kill();native_app.wait()
  (a.output/'native-app-cleanup.json').write_text(json.dumps(dict(pid=native_app.pid,exit=native_app.returncode))+'\n')
 m.close()
