#!/usr/bin/env python3
"""Run an owned browser control fixture with native provider, input and capture."""
import argparse,array,signal
import json,os,select,socket,subprocess,tempfile,time,sys,uuid
from contextlib import ExitStack
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Tests/Wayland'))
from gnustep import pasteboard_storage
from text_input import Client
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
browsers=parser.add_mutually_exclusive_group(required=True)
browsers.add_argument('--firefox',type=Path)
browsers.add_argument('--chromium',type=Path)
parser.add_argument('--library',type=Path,required=True)
parser.add_argument('--hook',type=Path,required=True)
parser.add_argument('--backend',required=True)
parser.add_argument('--theme',help='Use the same explicit GNUstep theme for the native host and references')
parser.add_argument('--control-helper',type=Path,help='Use an alternative control host for owned fault-injection tests')
parser.add_argument('--capture-probe',type=Path,required=True)
parser.add_argument('--compositor',default='/usr/NextSpace/bin/nextspace-compositor')
parser.add_argument('--export-menus',action='store_true',help='Enable Firefox menu export on a private test bus; requires the app-menu Wayland protocol')
parser.add_argument('--file-portal',action='store_true',help='Run the shared native FileChooser backend through a real private portal frontend')
parser.add_argument('--shared-menus',action='store_true',help='Bind the exported menu in the existing native text/control helper')
parser.add_argument('--menu-shell-probe',type=Path,help='Use the actual Workspace shell/menu connections for automatic active-window association')
parser.add_argument('--port',type=int,default=2833)
parser.add_argument('--library-path',action='append',default=[])
parser.add_argument('--hold',action='store_true',help='Keep the owned test/control fixture open until quit')
parser.add_argument('--native-frame',action='store_true',help='Use the compositor frame through the existing system-decoration settings')
parser.add_argument('--native-tabs',action='store_true',help='Retired; browser-owned tabs remain unchanged')
a=parser.parse_args()
if not a.hook.is_file():parser.error('--hook must name an existing compiled adapter')
out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
if a.shared_menus and not a.export_menus:parser.error('--shared-menus requires --export-menus')
if a.menu_shell_probe and not a.shared_menus:parser.error('--menu-shell-probe requires --shared-menus')
if a.chromium and (a.export_menus or not a.hold):parser.error('--chromium currently requires --hold and the standalone control helper')
import hashlib
if a.firefox:
 pin=json.loads((Path(__file__).with_name('binary-pin.json')).read_text())
 for name,path in [('firefox-esr',a.firefox),('libxul.so',a.firefox.parent/'libxul.so')]:
  assert hashlib.file_digest(path.open('rb'),'sha256').hexdigest()==pin['files_sha256']['usr/lib/firefox-esr/'+name],path
else:assert hashlib.file_digest(a.chromium.open('rb'),'sha256').hexdigest()=='7bcc9f719bc77d34358194026b4f148a468e97e4ddc45366e6ce02c119fb9bd1'
with socket.socket() as port_probe:port_probe.bind(('127.0.0.1',a.port))
def interrupted(signum,frame):raise KeyboardInterrupt
signal.signal(signal.SIGTERM,interrupted)
children=[];services=ExitStack();capture=None;menu_parent=menu_child=None;menu_shell=None;cdp_pipe=None

def cdp_call(request):
 assert cdp_pipe is not None;return cdp_pipe.call(request)

def stop(p):
 if p.poll() is None:
  p.terminate()
  try:p.wait(timeout=8)
  except subprocess.TimeoutExpired:p.kill();p.wait()

with tempfile.TemporaryDirectory(prefix='native-gecko-frontend-') as d:
 runtime=Path(d);runtime.chmod(0o700)
 env=dict(os.environ,XDG_RUNTIME_DIR=d,WLR_BACKENDS='headless',WLR_RENDERER='pixman',LD_LIBRARY_PATH=':'.join(a.library_path),MOZ_ENABLE_WAYLAND='1')
 for k in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','LD_PRELOAD'):env.pop(k,None)
 parent,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);parent.settimeout(5)
 broker,peer=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
 server=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET);server.bind(str(out/'control.sock'));server.listen(1)
 def command(text):
  parent.sendall(text.encode());return json.loads(parent.recv(65536))
 try:
  compositor=subprocess.Popen([a.compositor,'-c',str(child.fileno()),'-S',str(peer.fileno())],pass_fds=[child.fileno(),peer.fileno()],env=env,stdout=subprocess.PIPE,stderr=(out/'compositor.log').open('w'),text=True);children.append(compositor);child.close();peer.close()
  assert select.select([compositor.stdout],[],[],10)[0]
  env['WAYLAND_DISPLAY']=compositor.stdout.readline().strip().split('=',1)[1]
  env['NEXTSPACE_SESSION_ID']='firefox-native-frontend-'+uuid.uuid4().hex
  if a.export_menus or a.file_portal:
   bus=subprocess.Popen(['dbus-daemon','--session','--nofork','--print-address=1'],stdout=subprocess.PIPE,stderr=(out/'bus.stderr').open('w'),text=True);children.append(bus)
   assert select.select([bus.stdout],[],[],10)[0]
   env['DBUS_SESSION_BUS_ADDRESS']=bus.stdout.readline().strip()
  if a.export_menus:
   registrar=subprocess.Popen(['python3',str(Path(__file__).resolve().parents[2]/'Tests/NativeUI/dbus-menu-registrar.py')],env=env,stdout=subprocess.PIPE,stderr=(out/'registrar.stderr').open('w'),text=True);children.append(registrar)
   assert select.select([registrar.stdout],[],[],10)[0]
   ready=registrar.stdout.readline();assert json.loads(ready)['event']=='ready';(out/'registrar-ready.json').write_text(ready)
  if a.file_portal:
   portal_source=Path(__file__).resolve().parents[2]/'Libraries/NativeUI/Portal'
   portal_dir=runtime/'portals';portal_dir.mkdir()
   (portal_dir/'nextspace-native.portal').write_text((portal_source/'nextspace-native.portal').read_text())
   config_dir=runtime/'config';config_dir.mkdir()
   preferences=config_dir/'xdg-desktop-portal';preferences.mkdir()
   (preferences/'nextspace-portals.conf').write_text('[preferred]\ndefault=none\norg.freedesktop.impl.portal.FileChooser=nextspace-native\n')
   (portal_dir/'nextspace-portals.conf').write_text((preferences/'nextspace-portals.conf').read_text())
   env.update(XDG_SESSION_TYPE='wayland',XDG_SESSION_CLASS='user',XDG_CURRENT_DESKTOP='NEXTSPACE',XDG_CONFIG_HOME=str(config_dir),XDG_DESKTOP_PORTAL_DIR=str(portal_dir),GTK_USE_PORTAL='1')
   portal_args=['python3',str(portal_source/'main.py'),'--library',str(a.library.resolve().parent/'native-ui/libnextspace-native-ui.so.1'),'-GSBackend',a.backend]
   if a.theme:portal_args+=['-GSTheme',a.theme]
   portal=subprocess.Popen(portal_args,env=env,stdout=(out/'file-portal.jsonl').open('w'),stderr=(out/'file-portal.stderr').open('w'));children.append(portal)
   deadline=time.monotonic()+15
   while '"event": "ready"' not in (out/'file-portal.jsonl').read_text():
    assert portal.poll() is None and time.monotonic()<deadline;time.sleep(.02)
   frontend=subprocess.Popen(['/usr/libexec/xdg-desktop-portal','--replace','--verbose'],env=env,stdout=(out/'portal-frontend.log').open('w'),stderr=(out/'portal-frontend.stderr').open('w'));children.append(frontend)
  capture=Client(str(a.capture_probe),None,env,out,'capture',broker,b'V')
  assert capture.events[0]['manager_visible']
  services.enter_context(pasteboard_storage(Path('/Library/bin/gpbs-wayland'),a.library.resolve().parent/'native-ui/native-pasteboard-probe',env,out))
  endpoint=runtime/'native.sock'
  (out/'native-endpoint.json').write_text(json.dumps(dict(path=str(endpoint)))+'\n')
  helper_script=a.control_helper or Path(__file__).resolve().parent.parent/'ChromiumScrollers/helper.py'
  helper_args=['python3',str(helper_script.resolve()),'--library',str(a.library.resolve()),'--socket',str(endpoint),'-GSBackend',a.backend]
  if a.theme:helper_args+=['-GSTheme',a.theme]
  if a.shared_menus:
   menu_parent,menu_child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);menu_parent.settimeout(8)
   helper_args+=['--dbus-menu-fd',str(menu_child.fileno()),'--dbus-menu-output',str(out/'shared-menus')]
  helper=subprocess.Popen(helper_args,env=env,pass_fds=[menu_child.fileno()] if menu_child else [],stdout=(out/'helper.jsonl').open('w'),stderr=(out/'helper.stderr').open('w'));children.append(helper)
  if menu_child:menu_child.close()
  deadline=time.monotonic()+30
  while not endpoint.exists():
   assert helper.poll() is None and time.monotonic()<deadline;time.sleep(.02)
  if a.menu_shell_probe:
   shell_server,shell_client=socket.socketpair()
   broker.sendmsg([b'C'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[shell_server.fileno()]))]);shell_server.close()
   shell_args=[str(a.menu_shell_probe),'--nextspace-shell-fd',str(shell_client.fileno()),'--nextspace-native-menu-fd',str(menu_parent.fileno())]
   menu_shell=subprocess.Popen(shell_args,env=env,pass_fds=[shell_client.fileno(),menu_parent.fileno()],stdin=subprocess.PIPE,stdout=(out/'menu-shell.jsonl').open('w'),stderr=(out/'menu-shell.stderr').open('w'))
   children.append(menu_shell);shell_client.close();menu_parent.close()
   (out/'menu-shell-launch.json').write_text(json.dumps(dict(pid=menu_shell.pid,arguments=shell_args))+'\n')
  runtime_keys=['XDG_RUNTIME_DIR','WAYLAND_DISPLAY','NEXTSPACE_SESSION_ID','LD_LIBRARY_PATH']+(['DBUS_SESSION_BUS_ADDRESS'] if a.export_menus or a.file_portal else [])
  (out/'runtime.json').write_text(json.dumps({key:env[key] for key in runtime_keys})+'\n')
  profile=runtime/'profile';profile.mkdir()
  prefs={'marionette.port':a.port,'browser.shell.checkDefaultBrowser':False,'browser.startup.page':0,'browser.aboutwelcome.enabled':False,'browser.startup.homepage_override.mstone':'ignore','datareporting.policy.dataSubmissionEnabled':False,'gfx.webrender.software':True}
  if a.file_portal:prefs['widget.use-xdg-desktop-portal.file-picker']=1
  if a.export_menus:prefs.update({'widget.gtk.global-menu.enabled':True,'widget.gtk.global-menu.wayland.enabled':True})
  if a.firefox:(profile/'user.js').write_text(''.join('user_pref('+json.dumps(k)+', '+json.dumps(v)+');\n' for k,v in prefs.items()))
  if a.native_frame:
   sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Libraries/NativeUI/Bridge'))
   from browser_frames import prepare_native_frame
   prepare_native_frame('firefox' if a.firefox else 'chromium',profile,env)
  env['LD_PRELOAD']=str(a.hook.resolve())
  env.update(NEXTSPACE_FIREFOX_SOCKET=str(endpoint),NEXTSPACE_FIREFOX_LOG=str(out/'hook.log'),NEXTSPACE_FIREFOX_INPUT='1',NEXTSPACE_FIREFOX_TEXT='1')
  for flag in ('NEXTSPACE_FIREFOX_FRONTEND','NEXTSPACE_FIREFOX_TABS'):env.pop(flag,None)
  if a.export_menus:env['NEXTSPACE_FIREFOX_MENU_LIFECYCLE']='1'
  if a.shared_menus:env['NEXTSPACE_FIREFOX_MENU_KEYS']='1'
  launch_options={}
  if a.firefox:
   args=[str(a.firefox.resolve()),'--no-remote','--profile',str(profile),'--marionette','--remote-allow-system-access',Path(__file__).with_name('test-text.html').resolve().as_uri()]
  else:
   env.update(NEXTSPACE_CHROMIUM_SOCKET=str(endpoint),NEXTSPACE_CHROMIUM_LOG=str(out/'hook.log'))
   for flag in ['FORMS','INPUT','TEXT','PROGRESS','ANIMATION','SLIDERS','POPUPS','MULTILINE','MULTILINE_VIEWPORT','WHEEL']:env['NEXTSPACE_CHROMIUM_'+flag]='1'
   for flag in ['NEXTSPACE_CHROMIUM_VIEWS','NEXTSPACE_CHROMIUM_TABS']:env.pop(flag,None)
   args=[str(a.chromium.resolve()),'--ozone-platform=wayland','--gtk-version=4','--disable-gpu','--disable-dev-shm-usage','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-sync','--disable-component-update','--password-store=basic','--remote-debugging-pipe','--remote-debugging-port='+str(a.port),'--window-size=1120,800','--user-data-dir='+str(profile),Path(__file__).resolve().parent.parent.joinpath('ChromiumScrollers/test-popups.html').as_uri()]
  if a.chromium:
   from chromium_cdp_pipe import CDPPipe
   cdp_pipe=CDPPipe(args,env,out,a.hook.resolve());browser=cdp_pipe.process
  else:browser=subprocess.Popen(args,env=env,stdout=(out/'browser.stdout').open('w'),stderr=(out/'browser.stderr').open('w'),**launch_options)
  children.append(browser)
  (out/'launch.json').write_text(json.dumps(dict(pids=[p.pid for p in children],capture=capture.process.pid,command=args,engine='firefox' if a.firefox else 'chromium'),indent=2)+'\n')
  if a.shared_menus:
   deadline=time.monotonic()+30
   while True:
    assert browser.poll() is None and helper.poll() is None and time.monotonic()<deadline
    window=next((w for w in command('windows') if w['pid']==browser.pid and w.get('appmenu_service') and w.get('appmenu_path')),None)
    if window:break
    time.sleep(.02)
   if not a.menu_shell_probe:
    menu_parent.send(json.dumps(dict(operation='bind',window=window['id'],pid=window['pid'],
        service=window['appmenu_service'],path=window['appmenu_path'],title='Firefox')).encode())
    assert json.loads(menu_parent.recv(4096))['accepted']
   menu_output=out/'shared-menus'/str(window['id'])
   while not (menu_output/'native-items.json').exists():
    assert helper.poll() is None and time.monotonic()<deadline;time.sleep(.02)
   (out/'menu-binding.json').write_text(json.dumps(dict(shared_helper=True,pid=helper.pid,owner=browser.pid,
       window=window['id'],output=str(menu_output),log=str(out/'helper.jsonl'),arguments=helper_args,
       association='workspace' if menu_shell else 'fixture'),indent=2)+'\n')
  print('Owned '+('Firefox' if a.firefox else 'Chromium')+' control fixture ready',flush=True)
  if not a.hold:
   sys.path.insert(0,str(Path(__file__).resolve().parent))
   from marionette import Marionette
   deadline=time.monotonic()+30
   while True:
    assert browser.poll() is None and time.monotonic()<deadline
    try:client=Marionette(a.port);client.close();break
    except ConnectionRefusedError:time.sleep(.05)
   subprocess.run(['python3',str(Path(__file__).with_name('check-frontend.py')),'--port',str(a.port),
    '--expected-pid',str(browser.pid),'--fixture',str(out),'--library',str(a.library.resolve()),
    '--backend',a.backend,'--output',str(out/'checks')],env=env,check=True,timeout=120)
   raise SystemExit(0)
  while True:
   connection,_=server.accept()
   with connection:
    request=json.loads(connection.recv(65536));text=request['command']
    if text=='quit':connection.send(json.dumps(dict(ok=True)).encode());break
    if text.startswith('cdp '):connection.send(json.dumps(cdp_call(json.loads(text[4:]))).encode());continue
    if text.startswith('menu-broker ') and menu_parent and not menu_shell:
     menu_parent.send(text.split(' ',1)[1].encode());connection.send(menu_parent.recv(4096))
     continue
    if text.startswith('reference '):
     spec=json.loads(text.split(' ',1)[1]);path=out/'references-controls.json';path.write_text(json.dumps(spec['controls']))
     location=out/spec['name'];reference_env=dict(env);reference_env.pop('LD_PRELOAD',None)
     subprocess.run(['python3',str(Path(__file__).resolve().parent.parent/'ChromiumScrollers/native-control-reference.py'),'--library',str(a.library.resolve()),'--controls',str(path),'--output',str(location),'-GSBackend',a.backend]+(['-GSTheme',a.theme] if a.theme else [])+(['--focus'] if spec.get('focus') else []),env=reference_env,check=True,stdout=(out/'references.log').open('a'),stderr=(out/'references.stderr').open('a'))
     connection.send(json.dumps(dict(path=str(location))).encode())
    elif text.startswith('capture '):
     name=text.split(' ',1)[1];heads=command('outputs');head=next(x for x in heads if x['name']==name)
     path=out/'capture.raw';start=len(capture.events);capture.send('capture '+name+' '+str(path));event=capture.wait('frame',start)
     connection.send(json.dumps(dict(event=event,path=str(path),output=head)).encode())
    else:connection.send(json.dumps(command(text)).encode())
 finally:
  if cdp_pipe:cdp_pipe.close()
  if menu_parent:menu_parent.close()
  if capture:capture.stop()
  for p in reversed(children[1:]):stop(p)
  services.close()
  if children:stop(children[0])
  parent.close();broker.close();server.close();(out/'control.sock').unlink()
  (out/'cleanup.json').write_text(json.dumps(dict(exits=[p.returncode for p in children],capture_exit=capture.process.returncode if capture else None))+'\n')
