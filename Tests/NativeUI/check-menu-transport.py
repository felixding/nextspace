#!/usr/bin/env python3
"""Drive native menu IPC, idle owner callbacks and lifecycle on private Wayland."""
import argparse,json,os,select,socket,subprocess,sys,tempfile,time,uuid
from pathlib import Path
from contextlib import ExitStack
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Wayland'))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Experiments/ChromiumScrollers'))
from text_input import Client
from gnustep import pasteboard_storage
from native_controls import ControlRequest
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
p.add_argument('--capture-probe',type=Path,required=True);p.add_argument('--backend',required=True);p.add_argument('--compositor',default='/usr/NextSpace/bin/nextspace-compositor');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
rows=[];children=[]
def check(case,passed,**data):
 rows.append(dict(case=case,passed=bool(passed),**data));(a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
def stop(child):
 if child.poll() is None:
  child.terminate()
  try:child.wait(timeout=5)
  except subprocess.TimeoutExpired:child.kill();child.wait()
def until(read,predicate,timeout=6):
 deadline=time.monotonic()+timeout
 while True:
  result=read()
  if predicate(result):return result
  assert time.monotonic()<deadline,result
  time.sleep(.01)
class Actor:
 def __init__(self,endpoint,env,name,extra=()):
  self.out=a.output/name;self.out.mkdir(exist_ok=True);self.events=[];self.pending=b''
  self.child=subprocess.Popen([str(a.build/'native-ui/native-menu-transport-probe'),str(endpoint),*extra],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(self.out/'stderr').open('w'));children.append(self.child)
  os.set_blocking(self.child.stdout.fileno(),False)
  self.ready=self.wait(lambda e:e.get('event')=='menu-live',0)
 def pump(self):
  while select.select([self.child.stdout],[],[],0)[0]:
   data=os.read(self.child.stdout.fileno(),65536)
   if not data:break
   self.pending+=data
   while b'\n' in self.pending:
    line,self.pending=self.pending.split(b'\n',1);self.events.append(json.loads(line));(self.out/'events.json').write_text(json.dumps(self.events,indent=2)+'\n')
 def wait(self,predicate,start=None,timeout=10):
  if start is None:start=len(self.events)
  def read():
   self.pump();match=next((e for e in self.events[start:] if predicate(e)),None)
   assert match or self.child.poll() is None,(self.child.returncode,(self.out/'stderr').read_text())
   return match
  return until(read,bool,timeout)
 def request(self,text):
  start=len(self.events);self.child.stdin.write((text+'\n').encode());self.child.stdin.flush();return self.wait(lambda e:e.get('event')=='state',start)
 def finish(self):
  self.child.stdin.write(b'quit\n');self.child.stdin.flush();self.child.wait(timeout=10);self.pump();assert self.child.returncode==0,(self.child.returncode,(self.out/'stderr').read_text())
with tempfile.TemporaryDirectory(prefix='nxs-menu-wire-') as runtime:
 env=dict(os.environ,XDG_RUNTIME_DIR=runtime,WLR_BACKENDS='headless',WLR_RENDERER='pixman',NEXTSPACE_SESSION_ID='native-menu-wire-'+uuid.uuid4().hex)
 for key in ['DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','LD_PRELOAD','NEXTSPACE_NATIVE_UI_PROVIDER']:env.pop(key,None)
 parent,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);parent.settimeout(10)
 broker,peer=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
 compositor=subprocess.Popen([a.compositor,'-c',str(child.fileno()),'-S',str(peer.fileno())],pass_fds=[child.fileno(),peer.fileno()],env=env,stdout=subprocess.PIPE,stderr=(a.output/'compositor.log').open('w'),text=True);children.append(compositor);child.close();peer.close();services=ExitStack();capture=None
 def control(text):parent.sendall(text.encode());return json.loads(parent.recv(65536))
 try:
  assert select.select([compositor.stdout],[],[],10)[0];env['WAYLAND_DISPLAY']=compositor.stdout.readline().strip().split('=',1)[1]
  services.enter_context(pasteboard_storage(Path('/Library/bin/gpbs-wayland'),a.build/'native-ui/native-pasteboard-probe',env,a.output))
  capture=Client(str(a.capture_probe),None,env,a.output,'capture',broker,b'V');children.append(capture.process);assert capture.events[0]['manager_visible']
  endpoint=Path(runtime)/'native.sock'
  helper=subprocess.Popen([sys.executable,str(Path(__file__).resolve().parents[2]/'Experiments/ChromiumScrollers/helper.py'),'--library',str(a.build/'libnextspace-native-scroller.so.1'),'--socket',str(endpoint),'-GSBackend',a.backend],env=env,stdout=(a.output/'helper.jsonl').open('w'),stderr=(a.output/'helper.stderr').open('w'));children.append(helper)
  until(lambda:endpoint.exists() or helper.poll(),lambda x:x is True,timeout=30)
  def windows():return [w for w in control('windows') if w['pid']==helper.pid and w['visible'] and w['presented'] and w['buffer_width']>0]
  def point(actor,index):
   state=actor.request('state '+str(index));root=until(windows,lambda w:len(w)==1)[0]
   return [round(root['x']+state['item'][0]-state['frame'][0]+state['item'][2]/2),round(root['y']+state['item'][1]-state['frame'][1]+state['item'][3]/2)]
  def held(actor,index):
   x,y=point(actor,index);assert control(f'pointer {x} {y}')['ok'];assert control('button 272 1')['ok']
   return until(lambda:actor.request('state '+str(index)),lambda s:s['tracking'] and s['highlighted']==index-1)
  def click(actor,index,command):
   held(actor,index);start=len(actor.events);assert control('button 272 0')['ok']
   return actor.wait(lambda e:e.get('event')=='menu-command' and e['phase']==1 and e['command']==command,start)
  # Queue a physical menu callback while its UI owner deliberately leaves the
  # wake pending. Its next RPC must survive nested callback RPCs overtaking it.
  pending=Actor(endpoint,env,'pending-reply');until(windows,lambda w:len(w)==1)
  x,y=point(pending,2);pending.request('pause')
  offset=(a.output/'helper.jsonl').stat().st_size
  assert control(f'pointer {x} {y}')['ok'];assert control('button 272 1')['ok']
  assert control('button 272 0')['ok']
  until(lambda:(a.output/'helper.jsonl').read_text()[offset:],lambda text:'"event": "native-menu-awaiting-owner"' in text)
  resumed=pending.request('resume-with-rpc')
  pending.wait(lambda e:e.get('event')=='menu-command' and e['phase']==1,0)
  barrier_events=[json.loads(line) for line in (a.output/'helper.jsonl').read_text()[offset:].splitlines()]
  check('pending-reply-survives-nested-menu-RPC',resumed['accepted'] and
   any(e['event']=='native-menu-reply-deferred' for e in barrier_events) and
   any(e['event']=='native-menu-reply-resumed' and e['replies']>0 for e in barrier_events),source=resumed)
  pending.finish();until(windows,lambda w:not w)
  worker=Actor(endpoint,env,'worker-reply');until(windows,lambda w:len(w)==1)
  x,y=point(worker,2);worker.request('pause');offset=(a.output/'helper.jsonl').stat().st_size
  assert control(f'pointer {x} {y}')['ok'];assert control('button 272 1')['ok'];assert control('button 272 0')['ok']
  until(lambda:(a.output/'helper.jsonl').read_text()[offset:],lambda text:'"event": "native-menu-awaiting-owner"' in text)
  state=worker.request('worker-with-menu');event=worker.wait(lambda e:e.get('event')=='worker-reply',0)
  check('idle-owner-acknowledges-while-worker-awaits-reply',state['accepted'] and event['owner_callbacks'],source=state)
  worker.wait(lambda e:e.get('event')=='menu-command' and e['phase']==1,0);worker.finish();until(windows,lambda w:not w)
  actor=Actor(endpoint,env,'owner');check('menu-model-crosses-IPC',actor.ready['pid']==actor.child.pid)
  until(windows,lambda w:len(w)==1);initial=actor.request('state 2');check('native-state-crosses-IPC',initial['visible'] and initial['item'][2]>0,source=initial)
  start=len(actor.events);event=click(actor,2,2);check('idle-native-action-runs-on-owner',event['idle']==1,event=event)
  state=actor.request('state -1');check('application-command-executes-once',state['actions']==1 and state['last']==2,source=state)
  actor.request('disable');state=actor.request('key d');check('application-validation-rejects-disabled',state['actions']==1 and state['enabled']==1,source=state)
  actor.request('enable');state=actor.request('key z');check('native-key-matching-through-IPC',state['actions']==2 and state['last']==1,source=state)
  for name in ['bad-model','bad-count']:
   state=actor.request(name);check(name+'-preserves-live-menu',state['visible'] and state['actions']==2,source=state)
  # A second process cannot operate another process's menu, even over its own
  # connected socket. SCM_CREDENTIALS must match the registered owner PID.
  with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as attacker:
   attacker.settimeout(5);attacker.connect(str(endpoint));req=ControlRequest();req.magic=0x4e585549;req.operation=28;req.process=actor.ready['process'];req.control=1;req.state=-1
   attacker.send(bytes(req));reply=attacker.recv(4096)
   # The response acceptance is the first double in part 3, after its 24-byte prefix.
   import struct
   accepted=struct.unpack_from('d',reply,24+3*32)[0];check('foreign-owner-request-rejected',accepted==0)
  event=click(actor,4,4);actor.wait(lambda e:e.get('event')=='endpoint-replaced',0)
  until(windows,lambda w:not w)
  until(lambda:(a.output/'helper.jsonl').read_text(),lambda text:'"event": "native-menu-destroy"' in text)
  actor.request('model');actor.request('show');event=click(actor,2,2)
  state=actor.request('state -1');check('replacement-endpoint-survives-old-decision',state['actions']==4 and state['last']==2 and event['idle']==1,source=state)
  event=click(actor,3,3);until(windows,lambda w:not w)
  until(lambda:actor.request('state -1'),lambda s:not s['accepted'])
  actor.request('model');actor.request('show');state=actor.request('key z');check('late-menu-reply-after-destroy-drained',state['actions']==6 and state['last']==1,source=state)
  actor.request('peer-loss');until(windows,lambda w:not w);actor.finish();check('callback-peer-loss-removes-menu',not control('popups'))
  for name,extra in [('expiry',['--expire']),('owner-exit',[])]:
   actor=Actor(endpoint,env,name,extra);until(windows,lambda w:len(w)==1)
   held(actor,2)
   if name=='owner-exit':
    actor.child.kill();actor.child.wait(timeout=5)
   else:
    assert control('button 272 0')['ok']
   until(windows,lambda w:not w,timeout=6)
   check(name+'-removes-native-menu',not control('popups'))
   assert control('button 272 0')['ok']
   if name=='expiry':
    state=actor.request('state -1');check('expired-validation-does-not-execute',state['actions']==0,source=state);actor.finish()
  check('helper-remains-live',helper.poll() is None)
 finally:
  for child in reversed(children[2:]):stop(child)
  if capture:capture.stop()
  services.close();stop(compositor);parent.close();broker.close()
  (a.output/'cleanup.json').write_text(json.dumps([dict(pid=p.pid,exit=p.returncode) for p in children],indent=2)+'\n')
print(json.dumps(dict(passed=len(rows))))
