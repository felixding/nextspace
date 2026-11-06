#!/usr/bin/env python3
"""Verify native browser pixels in the actual Workspace desktop output."""
from pathlib import Path
import hashlib,json,os,shlex,signal,socket,subprocess,sys,tempfile,time,uuid
sys.path.insert(0,str(Path(__file__).resolve().parent))
from gnustep import private_defaults
from PIL import Image,ImageChops
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"Experiments/FirefoxNativeUI"))
from marionette import Marionette
import argparse
parser=argparse.ArgumentParser(description="Compare real desktop screencopy with independent native controls; never use a browser screenshot.")
for name in ['supervisor','compositor','workspace','capture-probe','library','hook','firefox','backend-bundle','output']:
 parser.add_argument('--'+name,type=Path,required=True)
parser.add_argument('--library-path',action='append',default=[])
parser.add_argument('--port',type=int,default=2863)
parser.add_argument('--no-frontend',action='store_true')
parser.add_argument('--document',type=Path,help='Optional owned HTML control fixture')
parser.add_argument('--restart-host',action='store_true',help='Verify actual desktop native pixels after owned host replacement')
parser.add_argument('--menus',action='store_true',help='Verify exclusive detached menus across the actual desktop applications')
parser.add_argument('--menu-only-activation',action='store_true',help='Verify actual icon activation and native keys without a document window')
parser.add_argument('--native-frame',action='store_true',help='Request the existing desktop frame through Firefox system-decoration settings')
args=parser.parse_args()
if args.menu_only_activation and not args.menus:parser.error('--menu-only-activation requires --menus')
assert 1<=args.port<=65535
for name in ['supervisor','compositor','workspace','capture_probe','library','hook','firefox']:
 assert getattr(args,name).is_file(),name
assert args.backend_bundle.is_dir()
with socket.socket() as port_probe:port_probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);port_probe.bind(('127.0.0.1',args.port))
root=args.output.resolve();root.mkdir(mode=0o700)
repo=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo/'Libraries/NativeUI/Bridge'))
from browser_frames import prepare_native_frame
pin=json.loads((repo/'Experiments/FirefoxNativeUI/binary-pin.json').read_text())
for name,path in [('firefox-esr',args.firefox),('libxul.so',args.firefox.parent/'libxul.so')]:
 assert hashlib.file_digest(path.open('rb'),'sha256').hexdigest()==pin['files_sha256']['usr/lib/firefox-esr/'+name],name
rows=[]
observed={}
def sample_processes():
 processes={}
 for entry in Path('/proc').iterdir():
  if not entry.name.isdigit():continue
  try:
   status=dict(line.split(':',1) for line in (entry/'status').read_text().splitlines() if ':' in line)
   processes[int(entry.name)]=dict(pid=int(entry.name),parent=int(status['PPid']),state=status['State'].strip(),seccomp=status.get('Seccomp','').strip(),no_new_privs=status.get('NoNewPrivs','').strip(),arguments=(entry/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace').strip())
  except (OSError,ValueError):pass
 owned={p.pid for p in children}
 if session:owned.add(session.pid)
 for _ in range(len(processes)):
  before=len(owned);owned.update(pid for pid,value in processes.items() if value['parent'] in owned)
  if len(owned)==before:break
 observed.update({pid:value for pid,value in processes.items() if pid in owned})
 return processes
def check(case,passed,**evidence):
 sample_processes()
 rows.append(dict(case=case,passed=bool(passed),**evidence));(root/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
temporary=tempfile.TemporaryDirectory(prefix='nxs-ui-desktop-')
runtime=Path(temporary.name)
compositor=args.compositor
workspace=args.workspace
probe=args.capture_probe
env=dict(os.environ,GNUSTEP_CONFIG_FILE='/Library/Preferences/GNUstep.conf',XDG_RUNTIME_DIR=str(runtime),XDG_SESSION_CLASS='user',WLR_BACKENDS='headless',WLR_HEADLESS_OUTPUTS='1',WLR_RENDERER='pixman',NEXTSPACE_SESSION_ID='preview-'+uuid.uuid4().hex,NEXTSPACE_GS_BACKEND='wayland',LD_LIBRARY_PATH=':'.join([str(args.library.parent),*args.library_path]))
for key in ['DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','LD_PRELOAD','NEXTSPACE_NATIVE_UI_SOCKET']:env.pop(key,None)
private_defaults(env,runtime);bundles=runtime/'empty-library/Bundles';bundles.mkdir(parents=True)
(bundles/args.backend_bundle.name).symlink_to(args.backend_bundle.resolve(),target_is_directory=True)
def wrapper(name,text):
 p=root/name;p.write_text(text);p.chmod(0o700);return p
control_server=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET);control_server.bind(str(runtime/'compositor-control'));control_server.listen(1);control_server.settimeout(30)
comp=wrapper('compositor','#!/usr/bin/python3\nimport os,socket,sys\ns=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET);s.connect('+repr(str(runtime/'compositor-control'))+');s.set_inheritable(True)\nos.execv('+repr(str(compositor))+',['+repr(str(compositor))+',"-c",str(s.fileno())]+sys.argv[1:])\n')
fifo=root/'capture.fifo';os.mkfifo(fifo,0o600);capture_fd=os.open(fifo,os.O_RDWR)
capture=wrapper('capture','#!/usr/bin/python3\nimport os\nf=os.open('+repr(str(fifo))+',os.O_RDWR);os.dup2(f,0);os.close(f)\nf=os.open('+repr(str(root/'capture.jsonl'))+',os.O_CREAT|os.O_APPEND|os.O_WRONLY,0o600);os.dup2(f,1);os.close(f)\nos.execv('+repr(str(probe))+',['+repr(str(probe))+'])\n')
host=wrapper('host','#!/bin/sh\nexec /usr/bin/python3 '+shlex.quote(str(repo/'Libraries/NativeUI/Host/main.py'))+' --library '+shlex.quote(str(args.library))+' -GSBackend wayland\n')
children=[];session=None;connection=None;client=None
def wait(read,predicate,timeout=30):
 end=time.monotonic()+timeout
 while True:
  value=read()
  if predicate(value):return value
  assert session is None or session.poll() is None, 'Desktop session exited'
  assert time.monotonic()<end,str(value)[-3000:]
  time.sleep(.05)
def command(text):
 connection.send(text.encode());return json.loads(connection.recv(1024*1024))
def published():
 data={}
 for line in (root/'session.stdout').read_text().splitlines():
  if line.startswith(('WAYLAND_DISPLAY=','DBUS_SESSION_BUS_ADDRESS=','NEXTSPACE_NATIVE_UI_SOCKET=','NEXTSPACE_SESSION_ID=')):
   k,v=line.split('=',1);data[k]=v
 return data
def frames():
 result=[]
 if (root/'capture.jsonl').exists():
  for line in (root/'capture.jsonl').read_text().splitlines():
   try:result.append(json.loads(line))
   except ValueError:pass
 return result
def stop(process):
 if process.poll() is None:
  process.terminate()
  try:process.wait(timeout=15)
  except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
try:
 with (root/'session.stdout').open('w') as log,(root/'session.stderr').open('w') as error:
  session=subprocess.Popen([str(args.supervisor),'--private-bus','--native-ui-host',str(host),'--compositor',str(comp),'--capture-backend',str(capture),'--',str(workspace),'-GSBackend','wayland','-GSTheme','NextSpace','-NSUseRunningCopy','NO'],env=env,stdout=log,stderr=error)
 connection,_=control_server.accept();connection.settimeout(10)
 wait(published,lambda s:'NEXTSPACE_NATIVE_UI_SOCKET' in s and 'WAYLAND_DISPLAY' in s)
 wait(lambda:(root/'session.stderr').read_text(),lambda s:'Workspace is ready' in s,60)
 wait(frames,lambda rows:any(v.get('event')=='ready' and v.get('manager_visible') for v in rows))
 heads=command('outputs');head=heads[0];assert command('resize-output '+head['name']+' 1600 1000')['ok']
 if args.menus:
  # Workspace autolaunches native applications asynchronously. Let their
  # document windows map before deliberately focusing the browser under test.
  wait(lambda:command('windows'),lambda windows:len({w['pid'] for w in windows if w['accepts_focus'] and w['level']==0 and not w['legacy']})>=2)
 browser_env=dict(env,**published());url=(args.document.resolve() if args.document else repo/'Experiments/FirefoxNativeUI/test-desktop.html').as_uri()
 family='firefox'
 current=dict(browser_env);prefix='NEXTSPACE_'+family.upper()+'_';current[prefix+'SOCKET']=browser_env['NEXTSPACE_NATIVE_UI_SOCKET'];current[prefix+'LOG']=str(root/(family+'-hook.log'))
 profile=runtime/'firefox-profile';profile.mkdir();prefs={'browser.shell.checkDefaultBrowser':False,'browser.startup.page':0,'browser.aboutwelcome.enabled':False,'browser.startup.homepage_override.mstone':'ignore','widget.gtk.global-menu.enabled':True,'widget.gtk.global-menu.wayland.enabled':True,'gfx.webrender.software':True}
 prefs.update({'marionette.port':args.port,'datareporting.policy.firstRunURL':'','browser.startup.firstrunSkipsHomepage':True})
 (profile/'user.js').write_text(''.join('user_pref('+json.dumps(k)+','+json.dumps(v)+');\n' for k,v in prefs.items()))
 if args.native_frame:prepare_native_frame('firefox',profile,current)
 current.update(LD_PRELOAD=str(args.hook),MOZ_ENABLE_WAYLAND='1')
 for flag in ['INPUT','TEXT','BUTTONS','SLIDERS','MULTILINE','MULTILINE_VIEWPORT','WHEEL','FRONTEND','MENU_LIFECYCLE','MENU_KEYS']:current[prefix+flag]='1'
 if args.no_frontend:current.pop(prefix+'FRONTEND')
 browser_command=[str(args.firefox),'--no-remote','--profile',str(profile),'--marionette','--remote-allow-system-access','--width','1120','--height','800',url]
 with (root/(family+'.stdout')).open('w') as log,(root/(family+'.stderr')).open('w') as error:browser=subprocess.Popen(browser_command,env=current,stdout=log,stderr=error)
 children.append(browser)
 window=wait(lambda:command('windows'),lambda rows:any(w['pid']==browser.pid and w['level']==0 for w in rows))
 window=next(w for w in window if w['pid']==browser.pid and w['level']==0)
 if args.native_frame:
  window=next(w for w in wait(lambda:command('windows'),lambda windows:any(w['pid']==browser.pid and w['server_decorated'] for w in windows)) if w['pid']==browser.pid and w['level']==0)
  check('browser-uses-shared-native-frame',window['server_decorated'],window=window)
 assert command('move '+str(window['id'])+' 240 80')['ok'];assert command('focus '+str(window['id']))['ok']
 # Wait for genuine native textarea painting and the asynchronous menu binding.
 wait(lambda:(root/(family+'-hook.log')).read_text() if (root/(family+'-hook.log')).exists() else '',lambda s:'native-text' in s,30)
 client=None
 def connect():
  try:return Marionette(args.port)
  except (ConnectionError,OSError):return None
 client=wait(connect,bool)
 session_info=client.command('WebDriver:NewSession',{})
 check('owned-browser-session',session_info['capabilities']['moz:processID']==browser.pid)
 handles=client.command('WebDriver:GetWindowHandles')
 selected=None
 for handle in handles:
  client.command('WebDriver:SwitchToWindow',dict(handle=handle))
  value=client.command('WebDriver:ExecuteScript',dict(script='return location.href',args=[]))['value']
  if value==url:selected=handle
 assert selected,handles
 for handle in handles:
  if handle==selected:continue
  client.command('WebDriver:SwitchToWindow',dict(handle=handle));client.command('WebDriver:CloseWindow')
 client.command('WebDriver:SwitchToWindow',dict(handle=selected))
 state=wait(lambda:client.command('WebDriver:ExecuteScript',dict(script='return {ready:document.readyState,title:document.title,left:document.getElementById("notes")?.clientLeft}',args=[]))['value'],lambda v:v['ready']=='complete' and v['title']=='Native controls on the desktop')
 (root/'firefox-native-state.json').write_text(json.dumps(state)+'\n')
 def js(script,context='content'):
  client.command('Marionette:SetContext',dict(value=context))
  return client.command('WebDriver:ExecuteScript',dict(script=script,args=[]))['value']
 def desktop(label):
  raw=root/(label+'.raw');before=sum(v.get('event')=='frame' for v in frames());os.write(capture_fd,('capture '+head['name']+' '+str(raw)+'\n').encode())
  frame=wait(frames,lambda values:sum(v.get('event')=='frame' for v in values)>before)[-1]
  image=Image.frombytes('RGBA' if frame['format']==0 else 'RGB',(frame['width'],frame['height']),raw.read_bytes(),'raw','BGRA' if frame['format']==0 else 'BGRX',frame['stride'],-1 if frame['flags']&1 else 1).convert('RGB')
  image.save(root/(label+'.png'));raw.unlink();return image
 def owned_hosts():
  processes=sample_processes()
  return [pid for pid,value in processes.items() if pid in observed and str(repo/'Libraries/NativeUI/Host/main.py') in value['arguments'] and not value['state'].startswith('Z')]
 def menu_selection(label,owner,focused):
  def selected(windows):
   roots=[w for w in windows if w['level']==20 and w['visible']]
   return len(roots)==1 and roots[0]['pid']==owner and any(w['id']==focused and w['focused'] for w in windows)
  try:windows=wait(lambda:command('windows'),selected)
  except AssertionError:
   (root/(label+'-failed-windows.json')).write_text(json.dumps(command('windows'),indent=2)+'\n')
   (root/(label+'-failed-popups.json')).write_text(json.dumps(command('popups'),indent=2)+'\n')
   desktop(label+'-failed');raise
  check(label+'-only-active-main-menu',selected(windows),menus=[w for w in windows if w['level'] in (10,20)])
  check(label+'-no-inactive-submenus',all(w['pid']==owner for w in windows if w['level']==10 and w['visible']))
  (root/(label+'-windows.json')).write_text(json.dumps(windows,indent=2)+'\n')
  desktop(label)
  return windows
 def browser_menu(label):
  hosts=wait(owned_hosts,lambda pids:len(pids)==1)
  windows=menu_selection(label,hosts[0],window['id'])
  menu=next(w for w in windows if w['pid']==hosts[0] and w['level']==20 and w['visible'])
  check(label+'-represented-application-title',menu['title']==window['app_id'],title=menu['title'])
  if args.menu_only_activation:check(label+'-proxy-declines-activation-fallback',menu.get('activation_fallback') is False)
  return windows
 def menu_shortcut(label):
  js('document.body.focus({preventScroll:true});return true')
  before=set(client.command('WebDriver:GetWindowHandles'))
  start=len((root/'session.stdout').read_text())
  for event in ['key 56 1','key 20 1','key 20 0','key 56 0']:assert command(event)['ok']
  handles=wait(lambda:client.command('WebDriver:GetWindowHandles'),lambda handles:len(handles)==len(before)+1)
  trace=[json.loads(line) for line in (root/'session.stdout').read_text()[start:].splitlines() if line.startswith('{')]
  check(label+'-native-menu-command-once',sum(row.get('event')=='application-command' for row in trace)==1)
  added=next(handle for handle in handles if handle not in before)
  client.command('WebDriver:SwitchToWindow',dict(handle=added));client.command('WebDriver:CloseWindow')
  client.command('WebDriver:SwitchToWindow',dict(handle=selected))
  assert command('focus '+str(window['id']))['ok']
 def compare(label):
  chrome=js('return gBrowser.selectedBrowser.getBoundingClientRect().toJSON()','chrome')
  models=js("return ['title','password','notes','check','radio','range','progress','button',...Array.from(document.querySelectorAll('button[data-native-control]'),e=>e.id)].map(id=>{let e=document.getElementById(id);return {id,rect:e.getBoundingClientRect().toJSON(),value:e.localName==='button'?e.innerText:e.value,checked:e.checked,enabled:!e.matches(':disabled'),top:e.scrollTop,auto:e.hasAttribute('data-native-auto')}})")
  controls=[]
  kinds=dict(title=7,password=8,notes=9,check=2,radio=3,range=4,progress=5,button=1)
  for model in models:
   identifier=model['id'];rect=model['rect'];kind=kinds.get(identifier,1);item=dict(id=identifier,kind=kind,width=rect['width'],height=rect['height'],enabled=int(model['enabled']),state=int(model.get('checked') or 0),title='')
   if identifier in ('title','password','notes'):item.update(text=model['value'],scroll=[0,model['top']])
   elif kind==1:
    item['title']=model['value']
    if model['auto']:item['preferred_size']=True
   elif identifier=='range':item.update(minimum=0,maximum=100,value=float(model['value']),step=1)
   elif identifier=='progress':item.update(value=float(model['value'])/100)
   controls.append(item)
  definition=root/(label+'-controls.json');definition.write_text(json.dumps(controls)+'\n');references=root/(label+'-references')
  subprocess.run([sys.executable,str(repo/'Experiments/ChromiumScrollers/native-control-reference.py'),'--library',str(args.library),'--controls',str(definition),'--output',str(references),'-GSBackend','wayland'],env=browser_env,stdout=(root/(label+'-reference.stdout')).open('w'),stderr=(root/(label+'-reference.stderr')).open('w'),check=True,timeout=30)
  time.sleep(1)
  image=desktop(label)
  current_window=next(w for w in command('windows') if w['id']==window['id'])
  (root/(label+'-geometry.json')).write_text(json.dumps(dict(chrome=chrome,window=current_window,models=models),indent=2)+'\n')
  differences=[]
  left,top=(current_window['frame_left'],current_window['frame_top']) if current_window['server_decorated'] else (0,0)
  for model in models:
   rect=model['rect'];x=round(current_window['x']+left+chrome['x']+rect['x']);y=round(current_window['y']+top+chrome['y']+rect['y']);w,h=round(rect['width']),round(rect['height'])
   actual=image.crop((x,y,x+w,y+h));actual.save(root/(label+'-'+model['id']+'-actual.png'))
   native=Image.open(references/(model['id']+'.png')).convert('RGBA');background=Image.new('RGBA',native.size,'white');background.alpha_composite(native)
   difference=ImageChops.difference(actual,background.convert('RGB')).getbbox() if actual.size==native.size else 'size'
   differences.append(dict(control=model['id'],difference=difference,actual_size=actual.size,native_size=native.size,box=[x,y,x+w,y+h]))
  check(label+'-actual-desktop-native-pixels',all(d['difference'] is None for d in differences),controls=differences)
 js('document.body.tabIndex=-1;document.body.focus({preventScroll:true});notes.scrollTop=73;return true')
 compare('initial')
 if args.menus:
  initial=browser_menu('browser-menu')
  if args.menu_only_activation:
   hosts=owned_hosts()
   candidates=[w for w in initial if w['level']==20 and w['pid'] not in hosts and not w['legacy'] and
     not any(d['pid']==w['pid'] and d['accepts_focus'] for d in initial)]
   check('owned-menu-only-application-available',bool(candidates),candidates=candidates)
   utility=candidates[0];pid=utility['pid']
   check('menu-only-window-declares-fallback',utility.get('activation_fallback') is True and not utility['accepts_focus'])
   icon=next(w for w in initial if w['pid']==pid and w['style']&64 and w['visible'])
   check('menu-only-application-belongs-to-desktop',pid in observed,pid=pid)
   assert command('pointer '+str(round(icon['x']+icon['width']/2))+' '+str(round(icon['y']+icon['height']/2)))['ok']
   assert command('button 272')['ok'];time.sleep(.4)
   menu_selection('menu-only-single-click-keeps-browser',hosts[0],window['id'])
   assert command('button 272')['ok'];time.sleep(.08);assert command('button 272')['ok']
   active_windows=menu_selection('menu-only-icon-activation',pid,utility['id'])
   active_menu=next(w for w in active_windows if w['id']==utility['id'])
   assert command('pointer '+str(round(active_menu['x']+active_menu['width']/2))+' '+str(active_menu['y']+10))['ok']
   assert command('button 272')['ok']
   menu_selection('menu-only-title-click-retains-activation',pid,utility['id'])
   for event in ['key 56 1','key 16 1','key 16 0','key 56 0']:assert command(event)['ok']
   wait(lambda:command('windows'),lambda windows:not any(w['pid']==pid for w in windows))
   check('menu-only-native-quit-key',not any(w['pid']==pid for w in command('windows')))
   assert command('focus '+str(window['id']))['ok'];browser_menu('browser-after-menu-only-application')
  native_documents={w['pid']:w for w in initial if w['pid']!=browser.pid and w['accepts_focus'] and w['level']==0 and not w['legacy']}
  check('multiple-native-desktop-applications',len(native_documents)>=2,applications=list(native_documents))
  for index,(pid,document) in enumerate(native_documents.items()):
   assert command('focus '+str(document['id']))['ok']
   menu_selection('native-app-'+str(index),pid,document['id'])
   assert command('focus '+str(window['id']))['ok']
   browser_menu('browser-after-native-'+str(index))
  # Coordinates come from the existing native menu's own layout, not a test
  # implementation of menu geometry. Keep the submenu open during a switch.
  menu_path=Path(browser_env['NEXTSPACE_NATIVE_UI_SOCKET']).parent/'menus'/str(window['id'])/'native-items.json'
  items=json.loads(menu_path.read_text());item=next(item for item in items if item['title']=='File' and item['visible'])
  x,y,w,h=item['frame'];assert command('pointer '+str(round(x+w/2))+' '+str(round(y+h/2)))['ok']
  try:
   assert command('button 272 1')['ok']
   popups=wait(lambda:command('popups'),bool)
   (root/'native-submenu-popups.json').write_text(json.dumps(popups,indent=2)+'\n')
   windows=command('windows')
   check('native-submenu-coexists-with-one-main-menu',len([w for w in windows if w['level']==20 and w['visible']])==1)
   check('native-submenu-retains-browser-keyboard-focus',any(w['id']==window['id'] and w['focused'] for w in windows))
   desktop('native-submenu')
   pid,document=next(iter(native_documents.items()));assert command('focus '+str(document['id']))['ok']
   menu_selection('native-app-during-submenu',pid,document['id'])
   wait(lambda:command('popups'),lambda popups:not popups)
   check('switch-dismisses-native-submenu',not command('popups'))
  finally:assert command('button 272 0')['ok']
  assert command('focus '+str(window['id']))['ok'];browser_menu('browser-after-submenu');menu_shortcut('desktop')
  compare('after-native-tab-return')
 if js('return !!document.getElementById("nested-label")'):
  def click(selector):
   element=client.command('WebDriver:FindElement',dict(using='css selector',value=selector))['value']
   client.command('WebDriver:ElementClick',dict(id=next(iter(element.values()))))
  def key(value):
   client.command('WebDriver:PerformActions',dict(actions=[dict(type='key',id='html-keyboard',actions=[dict(type='keyDown',value=value),dict(type='keyUp',value=value)])]))
  click('#nested-label')
  check('html-descendant-hit-target-preserved',js('return htmlEvents.some(e=>e.type==="click"&&e.trusted&&e.button==="nested"&&e.id!=="nested")') is True)
  js('window.htmlEvents=[];return true');click('#submit')
  check('html-trusted-native-submit',js('return htmlEvents.filter(e=>e.type==="submit"&&e.id==="submit"&&e.trusted).length')==1)
  js('window.htmlEvents=[];return true');key(' ')
  html_events=js('return htmlEvents')
  check('html-native-keyboard-submit-once',len([e for e in html_events if e['type']=='submit' and e['id']=='submit' and e['trusted']])==1,events=html_events)
  js('window.htmlEvents=[];document.getElementById("submit").addEventListener("keydown",e=>e.preventDefault(),{once:true});return true');key(' ')
  check('html-page-cancels-keyboard-activation',js('return htmlEvents.filter(e=>e.type==="submit").length')==0)
  js('window.htmlEvents=[];document.getElementById("submit").addEventListener("click",e=>e.preventDefault(),{once:true});return true');click('#submit')
  check('html-page-cancels-submit-click',js('return htmlEvents.filter(e=>e.type==="submit").length')==0)
  js('window.htmlEvents=[];document.getElementById("formValue").value="modified";return true');click('#reset')
  check('html-native-reset-uses-real-form',js('return document.getElementById("formValue").value==="original"&&htmlEvents.some(e=>e.type==="reset"&&e.trusted)') is True)
  js('window.htmlEvents=[];return true');click('#disabled')
  check('html-disabled-button-does-not-activate',js('return htmlEvents.filter(e=>e.type==="click").length')==0)
  js('document.body.focus({preventScroll:true});return true')
  compare('after-html-actions')
  js('let e=document.getElementById("button");e.style.cssText="appearance:none;border:2px solid black;background:#fc0;color:#246;font:16px serif;width:180px;height:28px";let p=e.cloneNode(true);p.id="styled-peer";e.after(p);return true')
  chrome=js('return gBrowser.selectedBrowser.getBoundingClientRect().toJSON()','chrome')
  rectangles=js('return ["button","styled-peer"].map(id=>document.getElementById(id).getBoundingClientRect().toJSON())')
  time.sleep(1);screen=desktop('html-style-fallback');crops=[]
  current_window=next(w for w in command('windows') if w['id']==window['id'])
  left,top=(current_window['frame_left'],current_window['frame_top']) if current_window['server_decorated'] else (0,0)
  for rect in rectangles:
   x,y=round(current_window['x']+left+chrome['x']+rect['x']),round(current_window['y']+top+chrome['y']+rect['y'])
   crops.append(screen.crop((x,y,x+round(rect['width']),y+round(rect['height']))))
  check('html-author-style-restores-complete-engine-control',ImageChops.difference(*crops).getbbox() is None)
  js('document.getElementById("styled-peer").remove();document.getElementById("button").style.cssText="";return true')
  compare('html-native-style-restored')
 js('title.value="Updated desktop title";notes.value="Updated notes\\n"+notes.value;notes.scrollTop=150;check.checked=false;radio.checked=false;range.value=75;progress.value=35;if(button.localName==="button")button.textContent="Updated action";else button.value="Updated action";title.style.width="440px";notes.style.width="620px";return true')
 compare('updated-and-resized')
 check('programmatic-updates-preserve-events',js('return events.length')==0)
 element=client.command('WebDriver:FindElement',dict(using='css selector',value='#button'))['value']
 client.command('WebDriver:ElementClick',dict(id=next(iter(element.values()))))
 check('trusted-native-button-action',js('return action?.trusted') is True)
 js('document.body.focus({preventScroll:true});return true')
 compare('after-native-action')
 element=client.command('WebDriver:FindElement',dict(using='css selector',value='#title'))['value']
 client.command('WebDriver:ElementClick',dict(id=next(iter(element.values()))))
 client.command('WebDriver:PerformActions',dict(actions=[dict(type='key',id='desktop-keyboard',actions=[dict(type=phase,value=value) for value in ['\ue010','!'] for phase in ['keyDown','keyUp']])]))
 check('native-edit-retains-engine-value-and-trusted-events',js('return title.value==="Updated desktop title!" && events.some(e=>e.type==="input"&&e.id==="title"&&e.trusted)') is True)
 js('document.body.focus({preventScroll:true});return true')
 compare('after-native-edit')
 client.command('WebDriver:Navigate',dict(url=url))
 wait(lambda:js('return document.readyState'),lambda value:value=='complete')
 js('document.body.tabIndex=-1;document.body.focus({preventScroll:true});notes.scrollTop=73;return true')
 compare('reloaded')
 if args.restart_host:
  old_hosts=owned_hosts();check('one-owned-native-host',len(old_hosts)==1,hosts=old_hosts)
  before_ready=(root/'session.stdout').read_text().count('NEXTSPACE_NATIVE_UI_SOCKET=')
  js('window.__nativeDesktopMarker="retained";return true');os.kill(old_hosts[0],signal.SIGKILL)
  replacement=wait(owned_hosts,lambda pids:len(pids)==1 and pids[0]!=old_hosts[0])
  wait(lambda:(root/'session.stdout').read_text(),lambda text:text.count('NEXTSPACE_NATIVE_UI_SOCKET=')>before_ready)
  check('owned-host-replacement-retains-document',js('return window.__nativeDesktopMarker')=='retained',old_host=old_hosts[0],new_host=replacement[0])
  if args.menus:browser_menu('host-replaced-menu');menu_shortcut('host-replaced')
  compare('host-replaced')
 client.command('WebDriver:Navigate',dict(url='about:blank'))
 check('navigation-away',client.command('WebDriver:GetTitle')['value']=='')
 client.close();client=None
 if args.native_frame:
  from browser_frame_actions import run as frame_actions
  frame_actions(command,wait,check,desktop,window['id'])
 print(json.dumps(dict(passed=len(rows),native_images=sum(len(r.get('controls',[])) for r in rows))),flush=True)
 stop(browser)

finally:
 sample_processes()
 if client:
  try:client.close()
  except (ConnectionError,OSError,AssertionError):pass
 for p in reversed(children):stop(p)
 if session:stop(session)
 if connection:connection.close()
 control_server.close();os.close(capture_fd)
 processes=sample_processes()
 live=[pid for pid in observed if pid in processes and not processes[pid]['state'].startswith('Z')]
 (root/'processes.json').write_text(json.dumps(list(observed.values()),indent=2)+'\n')
 (root/'GNUstep.conf').write_bytes(Path(env['GNUSTEP_CONFIG_FILE']).read_bytes())
 (root/'cleanup.json').write_text(json.dumps(dict(session_exit=session.returncode if session else None,browser_exits=[p.returncode for p in children],live=live))+'\n')
 temporary.cleanup()
 assert not live,live
