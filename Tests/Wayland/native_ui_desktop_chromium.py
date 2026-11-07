#!/usr/bin/env python3
"""Verify Chromium detached menus and host recovery in the actual Workspace desktop."""
from pathlib import Path
import hashlib,json,os,shlex,signal,socket,subprocess,sys,tempfile,time,uuid
sys.path.insert(0,str(Path(__file__).resolve().parent))
from gnustep import private_defaults
from PIL import Image,ImageChops
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"Experiments/FirefoxNativeUI"))
import argparse
parser=argparse.ArgumentParser(description="Verify native detached-menu ownership and complete restored menu pixels using real desktop screencopy.")
for name in ['supervisor','compositor','workspace','capture-probe','library','hook','chromium','backend-bundle','output']:
 parser.add_argument('--'+name,type=Path,required=True)
parser.add_argument('--library-path',action='append',default=[])
parser.add_argument('--port',type=int,default=9246)
parser.add_argument('--activation-fallback',action='store_true',help='Verify proxy menus decline menu-only activation and retain document focus')
parser.add_argument('--native-frame',action='store_true',help='Request the existing desktop frame through the Chromium profile preference')
parser.add_argument('--native-tabs',action='store_true',help='Verify the experimental shared native tab container')
parser.add_argument('--popup-recovery',action='store_true',help='Verify retained native select models and first actions after host replacement')
parser.add_argument('--button-sizing',action='store_true',help='Verify native button sizes/pixels/actions before and after host replacement')
parser.add_argument('--document',type=Path,help='Optional owned HTML control fixture')
args=parser.parse_args()
if args.button_sizing and not args.document:parser.error('--button-sizing requires --document')
assert 1<=args.port<=65535
for name in ['supervisor','compositor','workspace','capture_probe','library','hook','chromium']:
 assert getattr(args,name).is_file(),name
assert args.backend_bundle.is_dir()
with socket.socket() as port_probe:port_probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);port_probe.bind(('127.0.0.1',args.port))
root=args.output.resolve();root.mkdir(mode=0o700)
repo=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo/'Libraries/NativeUI/Bridge'))
from browser_frames import prepare_native_frame
assert hashlib.file_digest(args.chromium.open('rb'),'sha256').hexdigest()=='7bcc9f719bc77d34358194026b4f148a468e97e4ddc45366e6ce02c119fb9bd1'
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
children=[];session=None;connection=None;cdp_pipe=None
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

 wait(lambda:command('windows'),lambda windows:len({w['pid'] for w in windows if w['accepts_focus'] and w['level']==0 and not w['legacy']})>=2)
 browser_env=dict(env,**published());url=(args.document.resolve() if args.document else repo/'Experiments/FirefoxNativeUI/test-desktop.html').as_uri()
 current=dict(browser_env,LD_PRELOAD=str(args.hook))
 current['NEXTSPACE_CHROMIUM_SOCKET']=browser_env['NEXTSPACE_NATIVE_UI_SOCKET'];current['NEXTSPACE_CHROMIUM_LOG']=str(root/'chromium-hook.log')
 if args.native_tabs:current.update(NEXTSPACE_CHROMIUM_TABS='1',NEXTSPACE_CHROMIUM_TABS_TRACE='1')
 if args.native_frame:
  prepare_native_frame('chromium',runtime/'chromium-profile',current)
 for flag in ['FORMS','INPUT','TEXT','MULTILINE','MULTILINE_VIEWPORT','WHEEL','VIEWS','PROGRESS','ANIMATION','SLIDERS','POPUPS','MENUS','MENU_KEYS']:current['NEXTSPACE_CHROMIUM_'+flag]='1'
 launch=[str(args.chromium),'--ozone-platform=wayland','--gtk-version=4','--disable-gpu','--disable-dev-shm-usage','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-sync','--disable-component-update','--password-store=basic','--remote-debugging-port='+str(args.port),'--window-size=1120,800','--user-data-dir='+str(runtime/'chromium-profile'),url]
 if args.popup_recovery or args.button_sizing:
  from chromium_cdp_pipe import CDPPipe
  launch.append('--remote-debugging-pipe');cdp_pipe=CDPPipe(launch,current,root,args.hook);browser=cdp_pipe.process
 else:
  with (root/'chromium.stdout').open('w') as log,(root/'chromium.stderr').open('w') as error:browser=subprocess.Popen(launch,env=current,stdout=log,stderr=error)
 children.append(browser)
 windows=wait(lambda:command('windows'),lambda windows:any(w['pid']==browser.pid and w['level']==0 for w in windows))
 window=next(w for w in windows if w['pid']==browser.pid and w['level']==0)
 if args.native_frame:
  window=next(w for w in wait(lambda:command('windows'),lambda windows:any(w['pid']==browser.pid and w['server_decorated'] for w in windows)) if w['pid']==browser.pid and w['level']==0)
  check('browser-uses-shared-native-frame',window['server_decorated'],window=window)
 assert command('move '+str(window['id'])+' 240 80')['ok'];assert command('focus '+str(window['id']))['ok']
 import urllib.request
 def pages():
  try:return [page for page in json.load(urllib.request.urlopen('http://127.0.0.1:'+str(args.port)+'/json/list',timeout=2)) if page['type']=='page']
  except OSError:return []
 check('owned-pinned-browser-document',bool(wait(pages,lambda pages:any(page['url']==url for page in pages))))
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
  assert command('pointer 1400 900')['ok']
  desktop(label)
  return windows

 def browser_menu(label):
  hosts=wait(owned_hosts,lambda pids:len(pids)==1)
  assert command('focus '+str(window['id']))['ok']
  wait(lambda:command('windows'),lambda windows:any(w['pid']==hosts[0] and w['level']==20 and w['visible'] and w['title']=='Chromium' for w in windows))
  windows=menu_selection(label,hosts[0],window['id'])
  menu=next(w for w in windows if w['pid']==hosts[0] and w['level']==20 and w['visible'])
  check(label+'-represented-application-title',menu['title']=='Chromium',title=menu['title'])
  if args.activation_fallback:check(label+'-proxy-declines-activation-fallback',menu.get('activation_fallback') is False)
  return windows
 def menu_title_click(label,windows):
  owner=owned_hosts()[0]
  menu=next(w for w in windows if w['pid']==owner and w['level']==20 and w['visible'])
  assert command('pointer '+str(round(menu['x']+menu['width']/2))+' '+str(menu['y']+10))['ok']
  assert command('button 272')['ok']
  # Do not refocus the browser: that would conceal focus theft by the proxy.
  return menu_selection(label,owner,window['id'])
 def shortcut(label):
  before=pages();start=len((root/'chromium-hook.log').read_text())
  for event in ['key 56 1','key 20 1','key 20 0','key 56 0']:assert command(event)['ok']
  after=wait(pages,lambda pages:len(pages)==len(before)+1)
  trace=(root/'chromium-hook.log').read_text()[start:]
  check(label+'-native-new-tab-once',len(after)==len(before)+1 and trace.count('app-menu-execute ')==1,trace=trace)
  check(label+'-original-document-retained',any(page['url']==url for page in after))
  assert command('focus '+str(window['id']))['ok']
 initial=browser_menu('chromium-menu')
 if args.native_tabs:
  from browser_tabs import run as tab_checks
  tabs=tab_checks(command,wait,check,desktop,pages,root,window,args,browser_env,repo)
 if args.activation_fallback:initial=menu_title_click('chromium-menu-title-retains-focus',initial)
 documents={w['pid']:w for w in initial if w['pid']!=browser.pid and w['accepts_focus'] and w['level']==0 and not w['legacy']}
 check('multiple-native-desktop-applications',len(documents)>=2,applications=list(documents))
 for index,(pid,document) in enumerate(documents.items()):
  assert command('focus '+str(document['id']))['ok'];menu_selection('native-app-'+str(index),pid,document['id'])
  assert command('focus '+str(window['id']))['ok'];browser_menu('chromium-after-native-'+str(index))
 shortcut('desktop');menus=browser_menu('chromium-after-native-command')
 selected_root=next(w for w in menus if w['pid'] in owned_hosts() and w['level']==20 and w['visible'])
 menu_box=(selected_root['x'],selected_root['y'],selected_root['x']+selected_root['width'],selected_root['y']+selected_root['height'])
 before_replacement=desktop('before-host-replacement').crop(menu_box);before_replacement.save(root/'menu-reference-before-replacement.png')
 if args.popup_recovery or args.button_sizing:
  from popup_recovery import PopupRecovery
  page=next(page for page in pages() if page['url']==url)
  def cdp(method,params=None,target=True):
   request=dict(method=method,params=params or {})
   if target:request['sessionId']=target_session
   reply=cdp_pipe.call(request);assert 'error' not in reply,reply;return reply['result']
  target_session=cdp('Target.attachToTarget',dict(targetId=page['id'],flatten=True),False)['sessionId']
  cdp('Target.activateTarget',dict(targetId=page['id']),False)
  def js(script):
   reply=cdp('Runtime.evaluate',dict(expression='(function(){'+script+'}).call(window)',returnByValue=True,awaitPromise=True))
   assert 'exceptionDetails' not in reply,reply;return reply['result'].get('value')
  def origin():
   w=next(w for w in command('windows') if w['id']==window['id']);inside=js('return {height:innerHeight,scale:devicePixelRatio}');assert inside['scale']==1
   return [w['x']+(w['frame_left'] if w['server_decorated'] else 0),w['y']+(w['frame_top'] if w['server_decorated'] else 0)+w['surface_height']-inside['height']]
  if args.button_sizing:
   def button_lifetime():
    entries=[json.loads(line) for line in (root/'session.stdout').read_text().splitlines() if line.startswith('{') and line.endswith('}')]
    processes={entry['process'] for entry in entries if entry.get('event')=='native-form-control' and entry.get('kind')==1}
    registered={entry['process'] for entry in entries if entry.get('event')=='native-notifier' and entry.get('operation')==15 and entry.get('accepted')}
    return dict(controls=sorted(processes),registered=sorted(registered),ready=bool(processes) and processes<=registered)
   lifetime=wait(button_lifetime,lambda state:state['ready']);check('button-only-renderer-native-input-lifetime-registered',lifetime['ready'],**lifetime)
  if args.popup_recovery:
   popup_recovery=PopupRecovery(js,check,command,wait,desktop,root,args,browser_env,repo,owned_hosts,origin=origin,indent='    ');popup_recovery.before()
  if args.button_sizing:
   from button_sizing import ButtonFixture,run as button_checks
   button_phase='before-host';button_root=root/('buttons-'+button_phase);button_root.mkdir()
   class DesktopButtonFixture(ButtonFixture):
    def image(self,label):return desktop('button-'+button_phase+'-'+label)
   def button_command(text):
    if not text.startswith('reference '):return command(text)
    spec=json.loads(text[10:]);definition=button_root/'references-controls.json';definition.write_text(json.dumps(spec['controls'])+'\n');location=button_root/spec['name']
    subprocess.run([sys.executable,str(repo/'Experiments/ChromiumScrollers/native-control-reference.py'),'--library',str(args.library),'--controls',str(definition),'--output',str(location),'-GSBackend','wayland']+(['--focus'] if spec.get('focus') else []),env=browser_env,check=True,stdout=(button_root/'references.log').open('a'),stderr=(button_root/'references.stderr').open('a'),timeout=20)
    return dict(path=str(location))
   def button_check(case,passed,**evidence):check('button-'+button_phase+'-'+case,passed,**evidence)
   button_fixture=DesktopButtonFixture(button_root,button_command,js,button_check,browser.pid,origin,lambda:None)
   js('window.__nativeButtonRecoveryMarker="retained";return true');button_checks(button_fixture)
 if args.button_sizing:
  entries=[json.loads(line) for line in (root/'session.stdout').read_text().splitlines() if line.startswith('{') and line.endswith('}')]
  button_processes={entry['process'] for entry in entries if entry.get('event')=='native-form-key' and entry.get('kind')==1}
  button_models={(entry['process'],entry['control']) for entry in entries if entry.get('event')=='native-form-control' and entry.get('kind')==1 and entry['process'] in button_processes}
  check('buttons-bound-before-host-replacement',bool(button_models),models=sorted(button_models))
  button_host_log_offset=(root/'session.stdout').stat().st_size
 old_hosts=owned_hosts();check('one-owned-native-host',len(old_hosts)==1,hosts=old_hosts)
 before_ready=(root/'session.stdout').read_text().count('NEXTSPACE_NATIVE_UI_SOCKET=')
 os.kill(old_hosts[0],signal.SIGKILL)
 replacement=wait(owned_hosts,lambda pids:len(pids)==1 and pids[0]!=old_hosts[0])
 wait(lambda:(root/'session.stdout').read_text(),lambda text:text.count('NEXTSPACE_NATIVE_UI_SOCKET=')>before_ready)
 if args.popup_recovery:popup_recovery.after()
 if args.button_sizing:
  check('host-replacement-retains-button-document',js('return window.__nativeButtonRecoveryMarker')=='retained')
  button_phase='after-host';button_root=root/('buttons-'+button_phase);button_root.mkdir();button_fixture.root=button_root;button_checks(button_fixture)
  entries=[json.loads(line) for line in (root/'session.stdout').read_bytes()[button_host_log_offset:].decode().splitlines() if line.startswith('{') and line.endswith('}')]
  recreated={(entry['process'],entry['control']) for entry in entries if entry.get('event')=='native-form-control' and entry.get('kind')==1}
  check('every-retained-button-recreated-in-new-native-host',button_models<=recreated,before=sorted(button_models),recreated=sorted(recreated))
 if args.activation_fallback:check('host-replacement-retains-browser-keyboard-focus',any(w['id']==window['id'] and w['focused'] for w in command('windows')))
 restored=browser_menu('host-replaced-menu')
 if args.activation_fallback:menu_title_click('host-replaced-menu-title-retains-focus',restored)
 wait(lambda:desktop('host-replaced-menu-pixels'),lambda image:ImageChops.difference(image.crop(menu_box),before_replacement).getbbox() is None)
 check('complete-native-menu-pixels-after-host-replacement',True)
 shortcut('host-replaced')
 check('host-replaced-browser-process-retained',browser.poll() is None,old_host=old_hosts[0],new_host=replacement[0])
 browser_menu('final-chromium-menu')
 wait(lambda:desktop('final-chromium-menu-pixels'),lambda image:ImageChops.difference(image.crop(menu_box),before_replacement).getbbox() is None)
 check('complete-native-menu-pixels-after-recovered-command',True)
 if args.native_tabs:tabs.recovered()
 if args.native_frame:
  from browser_frame_actions import run as frame_actions
  frame_actions(command,wait,check,desktop,window['id'],tabs.pixels if args.native_tabs else None)
 print(json.dumps(dict(passed=len(rows))),flush=True)
 stop(browser)

finally:
 if cdp_pipe:cdp_pipe.close()
 sample_processes()
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
