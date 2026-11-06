#!/usr/bin/env python3
"""Exercise lazy submenu preparation in the actual native tracking loop."""
import argparse,json,os,select,socket,subprocess,sys,tempfile,time,uuid
from pathlib import Path
from contextlib import ExitStack
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Wayland'))
from gnustep import pasteboard_storage
from text_input import Client
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--backend',required=True);p.add_argument('--previous-provider',type=Path,required=True);p.add_argument('--compositor',default='/usr/NextSpace/bin/nextspace-compositor');p.add_argument('--capture-probe',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
rows=[];children=[]
def check(case,passed,**data):
 rows.append(dict(case=case,passed=bool(passed),**data));(a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
def until(read,predicate):
 deadline=time.monotonic()+8
 while True:
  v=read()
  if predicate(v):return v
  assert time.monotonic()<deadline,v
  time.sleep(.01)
def stop(p):
 if p.poll() is None:
  p.terminate()
  try:p.wait(timeout=5)
  except subprocess.TimeoutExpired:p.kill();p.wait()
class Actor:
 def __init__(self,name,env,eager=False):
  self.root=a.output/name;self.root.mkdir();self.events=[];self.pending=b''
  self.p=subprocess.Popen([str(a.build/'native-ui/native-menu-lifecycle-probe')]+(['--eager'] if eager else [])+['-GSBackend',a.backend],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(self.root/'stderr').open('w'));children.append(self.p);os.set_blocking(self.p.stdout.fileno(),False);self.wait('ready',0)
 def pump(self):
  while select.select([self.p.stdout],[],[],0)[0]:
   data=os.read(self.p.stdout.fileno(),65536)
   if not data:break
   self.pending+=data
   while b'\n' in self.pending:
    line,self.pending=self.pending.split(b'\n',1);self.events.append(json.loads(line));(self.root/'events.json').write_text(json.dumps(self.events,indent=2)+'\n')
 def wait(self,event,start):
  def read():
   self.pump();v=next((e for e in self.events[start:] if e['event']==event),None);assert v or self.p.poll() is None,(self.p.returncode,(self.root/'stderr').read_text());return v
  return until(read,bool)
 def send(self,text):self.p.stdin.write((text+'\n').encode());self.p.stdin.flush()
 def state(self,index=-1):
  self.pump();start=len(self.events);self.send('state '+str(index));return self.wait('state',start)
 def mode(self,text):
  self.pump();start=len(self.events);self.send(text+'\nsync');self.wait('sync',start)
 def finish(self):
  self.send('quit');self.p.wait(timeout=8);self.pump();assert self.p.returncode==0,(self.p.returncode,(self.root/'stderr').read_text())
with tempfile.TemporaryDirectory(prefix='nxs-menu-life-') as runtime:
 env=dict(os.environ,XDG_RUNTIME_DIR=runtime,WLR_BACKENDS='headless',WLR_RENDERER='pixman',NEXTSPACE_SESSION_ID='menu-life-'+uuid.uuid4().hex)
 for k in ['DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','LD_PRELOAD','NEXTSPACE_NATIVE_UI_PROVIDER']:env.pop(k,None)
 parent,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);parent.settimeout(10)
 broker,peer=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
 compositor=subprocess.Popen([a.compositor,'-c',str(child.fileno()),'-S',str(peer.fileno())],env=env,pass_fds=[child.fileno(),peer.fileno()],stdout=subprocess.PIPE,stderr=(a.output/'compositor.log').open('w'),text=True);children.append(compositor);child.close();peer.close();services=ExitStack()
 def control(t):parent.sendall(t.encode());return json.loads(parent.recv(65536))
 def point(s):return [round(s['item'][0]+s['item'][2]/2),round(s['item'][1]+s['item'][3]/2)]
 def press(actor,index):
  state=actor.state(index);x,y=point(state);assert control(f'pointer {x} {y}')['ok'];assert control('button 272 1')['ok'];return state
 def choose(actor,index,highlight):
  state=until(lambda:actor.state(index),lambda s:s['visible'] and s['item'][2]>0);x,y=point(state);assert control(f'pointer {x} {y}')['ok'];until(lambda:actor.state(index),lambda s:s['highlighted']==highlight);assert control('button 272 0')['ok']
 try:
  assert select.select([compositor.stdout],[],[],10)[0];env['WAYLAND_DISPLAY']=compositor.stdout.readline().strip().split('=',1)[1]
  services.enter_context(pasteboard_storage(Path('/Library/bin/gpbs-wayland'),a.build/'native-ui/native-pasteboard-probe',env,a.output))
  capture=Client(str(a.capture_probe),None,env,a.output,'capture',broker,b'V');children.append(capture.process)
  snapshots={}
  def image(actor,label):
   head=control('outputs')[0];path=actor.root/(label+'.raw');start=len(capture.events)
   capture.send('capture '+head['name']+' '+str(path));frame=capture.wait('frame',start)
   im=Image.frombytes('RGB',(frame['width'],frame['height']),path.read_bytes(),'raw','BGRX',frame['stride'])
   if frame['flags']&1:im=im.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
   im.save(actor.root/(label+'.png'));return im
  for mode in ['eager','prepared']:
   actor=Actor(mode,env,eager=mode=='eager');control('pointer 1200 500')
   snapshots[(mode,'root')]=image(actor,'root')
   press(actor,0);until(lambda:actor.state(1),lambda s:s['visible'] and s['item'][2]>0)
   # Native visibility precedes the first mapped buffer on Wayland. Require
   # the actual popup before comparing complete, unaltered capture pixels.
   until(lambda:control('popups'),lambda popups:len(popups)==1 and popups[0]['buffer_width']>0)
   snapshots[(mode,'submenu')]=image(actor,'submenu')
   control('button 272 0');until(actor.state,lambda s:not s['tracking'])
   actor.finish();until(lambda:control('windows'),lambda ws:not ws)
  for label in ['root','submenu']:
   expected=snapshots[('eager',label)];actual=snapshots[('prepared',label)]
   check('lifecycle-inherits-native-'+label+'-pixels',expected.size==actual.size and expected.tobytes()==actual.tobytes())
  previous=subprocess.run([str(a.build/'native-ui/native-menu-lifecycle-probe'),'--expect-no-lifecycle'],env=dict(env,NEXTSPACE_NATIVE_UI_PROVIDER=str(a.previous_provider)),capture_output=True,text=True,timeout=10)
  check('older-provider-rejects-lifecycle',previous.returncode==0,stdout=previous.stdout,stderr=previous.stderr)
  actor=Actor('lazy',env);s=actor.state(0);check('empty-lazy-branch-enabled',s['enabled']==1 and s['opens']==0,source=s)
  press(actor,0);s=until(lambda:actor.state(1),lambda s:s['visible']);check('native-open-populates-branch',s['opens']==1 and s['item'][2]>0,source=s)
  check('refreshed-native-disabled-item',not actor.state(2)['enabled'])
  other=actor.state(6);check('unrelated-branch-retained',other['enabled'] and other['opens']==1)
  choose(actor,1,0);s=until(actor.state,lambda s:s['actions']==1 and not s['tracking']);check('prepared-native-action',s['last']==200 and s['closes']==1,source=s)
  press(actor,0);more=until(lambda:actor.state(3),lambda s:s['visible']);x,y=point(more);control(f'pointer {x} {y}')
  nested=until(lambda:actor.state(4),lambda s:s['visible'] and s['opens']==3);check('nested-native-prepare',nested['item'][2]>0,source=nested)
  choose(actor,4,0);s=until(actor.state,lambda s:s['actions']==2 and not s['tracking']);check('nested-native-action-and-close',s['last']==204 and s['opens']==s['closes']==3,source=s)
  actor.finish();until(lambda:control('windows'),lambda ws:not ws)
  for name in ['reject','cancel']:
   actor=Actor(name,env);actor.mode(name);press(actor,0)
   s=until(actor.state,lambda s:s['opens']==1 and s['closes']==1)
   check(name+'-balances-lifecycle',s['actions']==0,source=s)
   check(name+'-maps-no-submenu',not control('popups'))
   control('button 272 0');actor.finish();until(lambda:control('windows'),lambda ws:not ws)
  print(json.dumps(dict(passed=len(rows))))
 finally:
  for p in reversed(children[1:]):stop(p)
  services.close()
  if compositor.poll() is None:control('quit')
  stop(compositor);parent.close();(a.output/'cleanup.json').write_text(json.dumps([dict(pid=p.pid,exit=p.returncode) for p in children],indent=2)+'\n')
