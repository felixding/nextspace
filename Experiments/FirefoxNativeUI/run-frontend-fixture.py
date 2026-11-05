#!/usr/bin/env python3
"""Run an owned Firefox frontend fixture with native provider, input and capture."""
import argparse,signal
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
parser.add_argument('--port',type=int,default=2833)
parser.add_argument('--library-path',action='append',default=[])
parser.add_argument('--hold',action='store_true',help='Keep the owned test/control fixture open until quit')
a=parser.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
pin=json.loads((Path(__file__).with_name('binary-pin.json')).read_text())
import hashlib
for name,path in [('firefox-esr',a.firefox),('libxul.so',a.firefox.parent/'libxul.so')]:
 assert hashlib.file_digest(path.open('rb'),'sha256').hexdigest()==pin['files_sha256']['usr/lib/firefox-esr/'+name],path
with socket.socket() as port_probe:port_probe.bind(('127.0.0.1',a.port))
def interrupted(signum,frame):raise KeyboardInterrupt
signal.signal(signal.SIGTERM,interrupted)
children=[];services=ExitStack();capture=None

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
  compositor=subprocess.Popen(['/usr/NextSpace/bin/nextspace-compositor','-c',str(child.fileno()),'-S',str(peer.fileno())],pass_fds=[child.fileno(),peer.fileno()],env=env,stdout=subprocess.PIPE,stderr=(out/'compositor.log').open('w'),text=True);children.append(compositor);child.close();peer.close()
  assert select.select([compositor.stdout],[],[],10)[0]
  env['WAYLAND_DISPLAY']=compositor.stdout.readline().strip().split('=',1)[1]
  env['NEXTSPACE_SESSION_ID']='firefox-native-frontend-'+uuid.uuid4().hex
  capture=Client(str(a.capture_probe),None,env,out,'capture',broker,b'V')
  assert capture.events[0]['manager_visible']
  services.enter_context(pasteboard_storage(Path('/Library/bin/gpbs-wayland'),a.library.resolve().parent/'native-ui/native-pasteboard-probe',env,out))
  endpoint=runtime/'native.sock'
  helper=subprocess.Popen(['python3',str(Path(__file__).resolve().parent.parent/'ChromiumScrollers/helper.py'),'--library',str(a.library.resolve()),'--socket',str(endpoint),'-GSBackend',a.backend],env=env,stdout=(out/'helper.jsonl').open('w'),stderr=(out/'helper.stderr').open('w'));children.append(helper)
  deadline=time.monotonic()+30
  while not endpoint.exists():
   assert helper.poll() is None and time.monotonic()<deadline;time.sleep(.02)
  (out/'runtime.json').write_text(json.dumps({key:env[key] for key in ['XDG_RUNTIME_DIR','WAYLAND_DISPLAY','NEXTSPACE_SESSION_ID','LD_LIBRARY_PATH']})+'\n')
  profile=runtime/'profile';profile.mkdir()
  prefs={'marionette.port':a.port,'browser.shell.checkDefaultBrowser':False,'browser.startup.page':0,'browser.aboutwelcome.enabled':False,'browser.startup.homepage_override.mstone':'ignore','datareporting.policy.dataSubmissionEnabled':False,'gfx.webrender.software':True}
  (profile/'user.js').write_text(''.join('user_pref('+json.dumps(k)+', '+json.dumps(v)+');\n' for k,v in prefs.items()))
  env.update(LD_PRELOAD=str(a.hook.resolve()),NEXTSPACE_FIREFOX_SOCKET=str(endpoint),NEXTSPACE_FIREFOX_LOG=str(out/'hook.log'),NEXTSPACE_FIREFOX_INPUT='1',NEXTSPACE_FIREFOX_TEXT='1',NEXTSPACE_FIREFOX_FRONTEND='1')
  args=[str(a.firefox.resolve()),'--no-remote','--profile',str(profile),'--marionette','--remote-allow-system-access',Path(__file__).with_name('test-text.html').resolve().as_uri()]
  browser=subprocess.Popen(args,env=env,stdout=(out/'browser.stdout').open('w'),stderr=(out/'browser.stderr').open('w'));children.append(browser)
  (out/'launch.json').write_text(json.dumps(dict(pids=[p.pid for p in children],capture=capture.process.pid,command=args),indent=2)+'\n')
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
  if capture:capture.stop()
  for p in reversed(children[1:]):stop(p)
  services.close()
  if children:stop(children[0])
  parent.close();broker.close();server.close();(out/'control.sock').unlink()
  (out/'cleanup.json').write_text(json.dumps(dict(exits=[p.returncode for p in children],capture_exit=capture.process.returncode if capture else None))+'\n')
