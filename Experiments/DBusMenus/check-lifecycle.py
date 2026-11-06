#!/usr/bin/env python3
"""Check real Firefox Edit actions and lazy bookmark menus via native controls."""
import argparse,json,os,signal,socket,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'FirefoxNativeUI'))
from marionette import Marionette
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--port',type=int,required=True);p.add_argument('--expected-pid',type=int,required=True);p.add_argument('--menu-host',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--require-menu-lifecycle-binding',action='store_true');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);rows=[]
host=json.loads(a.menu_host.read_text());native_output=Path(host['arguments'][host['arguments'].index('--output')+1]);assert '--lifecycle' in host['arguments']
launch=json.loads((a.fixture/'launch.json').read_text());assert launch['pids'][-1]==a.expected_pid
held=False

def check(case,passed,**data):
 rows.append(dict(case=case,passed=bool(passed),**data));(a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
def control(command):
 with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:s.settimeout(15);s.connect(str(a.fixture/'control.sock'));s.send(json.dumps(dict(command=command)).encode());return json.loads(s.recv(65536))
def wait(read,predicate):
 end=time.monotonic()+8
 while True:
  v=read()
  if predicate(v):return v
  assert time.monotonic()<end,v
  time.sleep(.015)
def states():
 path=native_output/'native-items.json';s=path.stat();stamp=(s.st_ino,s.st_mtime_ns);os.kill(host['pid'],signal.SIGUSR1)
 wait(lambda:(path.stat().st_ino,path.stat().st_mtime_ns),lambda v:v!=stamp)
 return json.loads(path.read_text())
def item(title):
 return wait(lambda:next((i for i in states() if i['title']==title and i['visible'] and i['frame'][2]>0),None),bool)
def point(row):
 f=row['frame'];return round(f[0]+f[2]/2),round(f[1]+f[3]/2)
def hover(title):
 row=item(title);x,y=point(row)
 # NSMenu can report visibility before its Wayland popup has mapped. A motion
 # sent then belongs to the underlying browser and cannot highlight this item.
 def mapped():
  surfaces=control('popups')+[w for w in control('windows') if w['pid']==host['pid'] and w['visible'] and w['presented']]
  return any(w.get('buffer_width',0)>0 and w['x']<=x<w['x']+w['width'] and w['y']<=y<w['y']+w['height'] for w in surfaces)
 wait(mapped,bool)
 assert control(f'pointer {x} {y}')['ok'];return row
def open_menu(title):
 global held
 hover(title);assert control('button 272 1')['ok'];held=True
def choose(title):
 global held
 row=hover(title);index=row['index']
 wait(lambda:next((i for i in states() if i['index']==index),None),lambda i:i is not None and i['highlighted']>=0)
 if a.require_menu_lifecycle_binding:
  bar=wait(bar_state,lambda v:v['inactive'] and v['height']==initial_bar['height'])
  check('held-native-menu-retains-internal-toolbar-layout-'+title,bar['native'] and bar['inactive'],state=bar)
 assert control('capture HEADLESS-1')['event']['event']=='frame'
 assert control('button 272 0')['ok'];held=False
m=Marionette(a.port)
try:
 def bar_state():
  previous=m.command('Marionette:GetContext')['value']
  m.command('Marionette:SetContext',dict(value='chrome'))
  try:return m.command('WebDriver:ExecuteScript',dict(script="let t=document.getElementById('toolbar-menubar');return {inactive:t.hasAttribute('inactive'),height:t.getBoundingClientRect().height,native:document.getElementById('main-menubar').hasAttribute('native')}",args=[]))['value']
  finally:m.command('Marionette:SetContext',dict(value=previous))
 session=m.command('WebDriver:NewSession',{});check('owned-browser',session['capabilities']['moz:processID']==a.expected_pid)
 if a.require_menu_lifecycle_binding:
  hook=(a.fixture/'hook.log').read_text()
  check('native-browser-menu-lifecycle-binding-active',f'{a.expected_pid} native Gecko external menu lifecycle binding installed' in hook)
 initial_bar=bar_state()
 if a.require_menu_lifecycle_binding:check('initial-internal-toolbar-inactive',initial_bar['native'] and initial_bar['inactive'],state=initial_bar)
 handles=m.command('WebDriver:GetWindowHandles');m.command('WebDriver:SwitchToWindow',dict(handle=handles[0]))
 def context(name):m.command('Marionette:SetContext',dict(value=name))
 def js(code):return m.command('WebDriver:ExecuteScript',dict(script=code,args=[]))['value']
 context('content');check('owned-original-tab','/test-text.html' in js('return location.href'))
 js("window.__nativeLifecycleClickUp=false;document.addEventListener('mouseup',()=>window.__nativeLifecycleClickUp=true,{once:true});return true")
 browser=next(w for w in control('windows') if w['pid']==a.expected_pid and w['visible']);control(f"focus {browser['id']}");control('pointer 400 500');control('button 272')
 wait(lambda:js('return window.__nativeLifecycleClickUp'),bool)
 js('normal.value="Undo target";normal.focus();normal.select();return true')
 for command in ['key 56 1','key 45 1','key 45 0','key 56 0']:assert control(command)['ok']
 wait(lambda:js('return normal.value'),lambda v:v=='');check('engine-cut-established',js('return normal.value')=='')
 context('chrome');check('actual-undo-controller-enabled',js('let c=document.commandDispatcher.getControllerForCommand("cmd_undo");return !!c&&c.isCommandEnabled("cmd_undo")'))
 open_menu('Edit');choose('Undo');context('content');value=wait(lambda:js('return normal.value'),lambda v:v=='Undo target');check('native-edit-menu-undo',value=='Undo target',value=value)
 open_menu('Edit');choose('Redo');value=wait(lambda:js('return normal.value'),lambda v:v=='');check('native-edit-menu-redo',value=='',value=value)
 context('content');js('location.hash="";return true')
 wait(lambda:js('return location.hash'),lambda value:value=='')
 context('chrome')
 folder_title='Native lifecycle folder '+a.output.name
 created=m.command('WebDriver:ExecuteAsyncScript',dict(script='''let title=arguments[0],done=arguments[arguments.length-1];(async()=>{let folder=await PlacesUtils.bookmarks.insert({parentGuid:PlacesUtils.bookmarks.unfiledGuid,type:PlacesUtils.bookmarks.TYPE_FOLDER,title});let link=await PlacesUtils.bookmarks.insert({parentGuid:folder.guid,url:"file:///workspace/Experiments/FirefoxNativeUI/test-text.html#native-menu-bookmark",title:"Native lifecycle destination"});return {folder:folder.guid,link:link.guid}})().then(done,e=>done({error:String(e)}));''',args=[folder_title]))['value'];check('real-bookmark-fixture-created','error' not in created,bookmarks=created)
 # Closed Places views can stop observing insertions. Actual native opening
 # must prepare the branch; a projected-folder precondition would bypass that.
 open_menu('Bookmarks');hover('Other Bookmarks');hover(folder_title);choose('Native lifecycle destination')
 context('content');url=wait(lambda:js('return location.href'),lambda v:v.endswith('#native-menu-bookmark'));check('native-lazy-bookmark-command',url.endswith('#native-menu-bookmark'),url=url)
 context('chrome');js('window.__nativeLifecycleCleanup=true;return true')
 # Inspect real popup delivery; the bridge has no DOM knowledge.
 events=js('return window.__nativePopupProbe??[]');(a.output/'browser-popup-events.json').write_text(json.dumps(events,indent=2)+'\n')
 prefix=a.menu_host.with_name(a.menu_host.name.removesuffix('-host.json'))
 trace=wait(lambda:Path(str(prefix)+'.stdout').read_text(),lambda text:text.count('"event": "native-submenu-prepared"')==text.count('"event": "native-submenu-closed"'))
 (a.output/'menu.log').write_text(trace)
 prepared=[json.loads(l) for l in trace.splitlines() if '"event": "native-submenu-prepared"' in l];closed=[json.loads(l) for l in trace.splitlines() if '"event": "native-submenu-closed"' in l]
 check('native-lifecycle-delivers-real-branches',len(prepared)>=5 and len(closed)>=5,prepared=len(prepared),closed=len(closed))
 if a.require_menu_lifecycle_binding:
  bar=wait(bar_state,lambda v:v['inactive'] and v['height']==initial_bar['height'])
  check('closed-native-menu-retains-internal-toolbar-layout',bar['native'],state=bar)
 check('no-stale-command-errors','application-error' not in trace and 'native-submenu-error' not in trace)
 print(json.dumps(dict(passed=len(rows))))
finally:
 if held:control('button 272 0')
 for key in [56,29,42,125]:control(f'key {key} 0')
 m.close()
