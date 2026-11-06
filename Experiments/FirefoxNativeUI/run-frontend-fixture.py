#!/usr/bin/env python3
"""Run an owned Firefox frontend fixture with native provider, input and capture."""
import argparse,array,signal
import json,os,select,socket,subprocess,tempfile,time,sys,uuid
from contextlib import ExitStack
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Tests/Wayland'))
from gnustep import pasteboard_storage
from text_input import Client
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--firefox',type=Path,required=True)
parser.add_argument('--library',type=Path,required=True)
parser.add_argument('--hook',type=Path,required=True)
parser.add_argument('--backend',required=True)
parser.add_argument('--capture-probe',type=Path,required=True)
parser.add_argument('--compositor',default='/usr/NextSpace/bin/nextspace-compositor')
parser.add_argument('--export-menus',action='store_true',help='Enable Firefox menu export on a private test bus; requires the app-menu Wayland protocol')
parser.add_argument('--shared-menus',action='store_true',help='Bind the exported menu in the existing native text/control helper')
parser.add_argument('--menu-shell-probe',type=Path,help='Use the actual Workspace shell/menu connections for automatic active-window association')
parser.add_argument('--port',type=int,default=2833)
parser.add_argument('--library-path',action='append',default=[])
parser.add_argument('--hold',action='store_true',help='Keep the owned test/control fixture open until quit')
parser.add_argument('--native-frame',action='store_true',help='Use the compositor frame through the existing system-decoration settings')
parser.add_argument('--native-tabs',action='store_true',help='Bind the browser tab container to the shared GNUstep NSTabView')
a=parser.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
if a.shared_menus and not a.export_menus:parser.error('--shared-menus requires --export-menus')
if a.menu_shell_probe and not a.shared_menus:parser.error('--menu-shell-probe requires --shared-menus')
pin=json.loads((Path(__file__).with_name('binary-pin.json')).read_text())
import hashlib
for name,path in [('firefox-esr',a.firefox),('libxul.so',a.firefox.parent/'libxul.so')]:
 assert hashlib.file_digest(path.open('rb'),'sha256').hexdigest()==pin['files_sha256']['usr/lib/firefox-esr/'+name],path
with socket.socket() as port_probe:port_probe.bind(('127.0.0.1',a.port))
def interrupted(signum,frame):raise KeyboardInterrupt
signal.signal(signal.SIGTERM,interrupted)
children=[];services=ExitStack();capture=None;menu_parent=menu_child=None;menu_shell=None

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
  if a.export_menus:
   bus=subprocess.Popen(['dbus-daemon','--session','--nofork','--print-address=1'],stdout=subprocess.PIPE,stderr=(out/'bus.stderr').open('w'),text=True);children.append(bus)
   assert select.select([bus.stdout],[],[],10)[0]
   env['DBUS_SESSION_BUS_ADDRESS']=bus.stdout.readline().strip()
   registrar=subprocess.Popen(['python3',str(Path(__file__).resolve().parents[2]/'Tests/NativeUI/dbus-menu-registrar.py')],env=env,stdout=subprocess.PIPE,stderr=(out/'registrar.stderr').open('w'),text=True);children.append(registrar)
   assert select.select([registrar.stdout],[],[],10)[0]
   ready=registrar.stdout.readline();assert json.loads(ready)['event']=='ready';(out/'registrar-ready.json').write_text(ready)
  capture=Client(str(a.capture_probe),None,env,out,'capture',broker,b'V')
  assert capture.events[0]['manager_visible']
  services.enter_context(pasteboard_storage(Path('/Library/bin/gpbs-wayland'),a.library.resolve().parent/'native-ui/native-pasteboard-probe',env,out))
  endpoint=runtime/'native.sock'
  helper_args=['python3',str(Path(__file__).resolve().parent.parent/'ChromiumScrollers/helper.py'),'--library',str(a.library.resolve()),'--socket',str(endpoint),'-GSBackend',a.backend]
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
  runtime_keys=['XDG_RUNTIME_DIR','WAYLAND_DISPLAY','NEXTSPACE_SESSION_ID','LD_LIBRARY_PATH']+(['DBUS_SESSION_BUS_ADDRESS'] if a.export_menus else [])
  (out/'runtime.json').write_text(json.dumps({key:env[key] for key in runtime_keys})+'\n')
  profile=runtime/'profile';profile.mkdir()
  prefs={'marionette.port':a.port,'browser.shell.checkDefaultBrowser':False,'browser.startup.page':0,'browser.aboutwelcome.enabled':False,'browser.startup.homepage_override.mstone':'ignore','datareporting.policy.dataSubmissionEnabled':False,'gfx.webrender.software':True}
  if a.export_menus:prefs.update({'widget.gtk.global-menu.enabled':True,'widget.gtk.global-menu.wayland.enabled':True})
  (profile/'user.js').write_text(''.join('user_pref('+json.dumps(k)+', '+json.dumps(v)+');\n' for k,v in prefs.items()))
  if a.native_frame:
   sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Libraries/NativeUI/Bridge'))
   from browser_frames import prepare_native_frame
   prepare_native_frame('firefox',profile,env)
  env.update(LD_PRELOAD=str(a.hook.resolve()),NEXTSPACE_FIREFOX_SOCKET=str(endpoint),NEXTSPACE_FIREFOX_LOG=str(out/'hook.log'),NEXTSPACE_FIREFOX_INPUT='1',NEXTSPACE_FIREFOX_TEXT='1',NEXTSPACE_FIREFOX_FRONTEND='1')
  if a.native_tabs:env['NEXTSPACE_FIREFOX_TABS']='1'
  if a.export_menus:env['NEXTSPACE_FIREFOX_MENU_LIFECYCLE']='1'
  if a.shared_menus:env['NEXTSPACE_FIREFOX_MENU_KEYS']='1'
  args=[str(a.firefox.resolve()),'--no-remote','--profile',str(profile),'--marionette','--remote-allow-system-access',Path(__file__).with_name('test-text.html').resolve().as_uri()]
  browser=subprocess.Popen(args,env=env,stdout=(out/'browser.stdout').open('w'),stderr=(out/'browser.stderr').open('w'));children.append(browser)
  (out/'launch.json').write_text(json.dumps(dict(pids=[p.pid for p in children],capture=capture.process.pid,command=args),indent=2)+'\n')
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
  print('Owned Firefox frontend fixture ready',flush=True)
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
    if text.startswith('menu-broker ') and menu_parent and not menu_shell:
     menu_parent.send(text.split(' ',1)[1].encode());connection.send(menu_parent.recv(4096))
     continue
    if text.startswith('reference '):
     spec=json.loads(text.split(' ',1)[1]);path=out/'references-controls.json';path.write_text(json.dumps(spec['controls']))
     location=out/spec['name'];reference_env=dict(env);reference_env.pop('LD_PRELOAD',None)
     subprocess.run(['python3',str(Path(__file__).resolve().parent.parent/'ChromiumScrollers/native-control-reference.py'),'--library',str(a.library.resolve()),'--controls',str(path),'--output',str(location),'-GSBackend',a.backend]+(['--focus'] if spec.get('focus') else []),env=reference_env,check=True,stdout=(out/'references.log').open('a'),stderr=(out/'references.stderr').open('a'))
     connection.send(json.dumps(dict(path=str(location))).encode())
    elif text.startswith('capture '):
     name=text.split(' ',1)[1];heads=command('outputs');head=next(x for x in heads if x['name']==name)
     path=out/'capture.raw';start=len(capture.events);capture.send('capture '+name+' '+str(path));event=capture.wait('frame',start)
     connection.send(json.dumps(dict(event=event,path=str(path),output=head)).encode())
    else:connection.send(json.dumps(command(text)).encode())
 finally:
  if menu_parent:menu_parent.close()
  if capture:capture.stop()
  for p in reversed(children[1:]):stop(p)
  services.close()
  if children:stop(children[0])
  parent.close();broker.close();server.close();(out/'control.sock').unlink()
  (out/'cleanup.json').write_text(json.dumps(dict(exits=[p.returncode for p in children],capture_exit=capture.process.returncode if capture else None))+'\n')
