#!/usr/bin/env python3
"""Real-process color ownership, lifetime and data authority through NativeUI."""
import argparse,array,ctypes as C,json,os,socket,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Experiments/ChromiumScrollers'))
from native_controls import ControlRequest,ControlColorRequest,ColorModel,MAGIC
from helper import Response

class Client:
 def __init__(self,path,identity):
  self.process=identity;self.control=1;self.socket=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
  self.socket.settimeout(10);self.socket.connect(path);self.fd=os.eventfd(0,os.EFD_CLOEXEC|os.EFD_NONBLOCK)
 def exchange(self,request,descriptor=None):
  self.socket.sendmsg([bytes(request)],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[descriptor]))] if descriptor is not None else [])
  data=self.socket.recv(65536);assert len(data)>=C.sizeof(Response)
  response=Response.from_buffer_copy(data);assert response.magic==MAGIC and response.size==len(data)
  return response,data[C.sizeof(Response):]
 def request(self,operation,**values):
  request=ControlRequest(magic=MAGIC,operation=operation,process=self.process,kind=16,control=self.control)
  for name,value in values.items():setattr(request,name,value)
  return self.exchange(request)
 def register(self):
  return self.exchange(ControlRequest(magic=MAGIC,operation=15,process=self.process),self.fd)[0].parts[3].x==1
 def configure(self):return self.request(1,width=120,height=24,maximum=1,enabled=1)[0].width==120
 def sync(self,red,green,blue):
  request=ControlColorRequest(magic=MAGIC,operation=55,process=self.process,kind=16,control=self.control,red=red,green=green,blue=blue,alpha=1)
  return self.exchange(request)[0].parts[3].x==1
 def color(self):
  response,payload=self.request(56)
  if response.parts[3].x!=1:return None
  model=ColorModel.from_buffer_copy(payload);return [model.red,model.green,model.blue,model.alpha]
 def close(self):self.socket.close();os.close(self.fd)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--endpoint',required=True);p.add_argument('--desktop',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();rows=[]
 def desktop(text):
  with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as connection:
   connection.settimeout(10);connection.connect(a.desktop);connection.send(json.dumps(dict(command=text)).encode());return json.loads(connection.recv(65536))
 def check(name,value,**data):
  rows.append(dict(case=name,passed=bool(value),**data));a.output.write_text(json.dumps(rows,indent=2)+'\n');assert value,rows[-1]
 def capture_stage(name):
  root=Path(a.desktop).parent
  (root/(name+'-windows.json')).write_text(json.dumps(desktop('windows'),indent=2)+'\n')
  if (root/'capture.fifo').exists():
   sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Wayland'))
   from desktop_input import Desktop
   Desktop(root).capture(name)
 def panel_window(visible=True):
  # A native RPC reply precedes the compositor processing its Wayland commit.
  # Observe that asynchronous mapping within the existing three-second limit.
  deadline=time.monotonic()+3
  while True:
   panel=next((w for w in desktop('windows') if w['title']=='Colors' and w['visible']),None)
   if bool(panel)==visible:return panel
   assert time.monotonic()<deadline,('native panel mapping',visible,panel)
   time.sleep(.02)
 parent=Client(a.endpoint,0xa1000000+(os.getpid()&0xffff));check('borrower-needs-live-registration',parent.request(61,x=123)[0].parts[3].x==0)
 check('parent-registration',parent.register())
 control,peer=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);child=os.fork()
 if not child:
  control.close();parent.close();source=Client(a.endpoint,0xa2000000+(os.getpid()&0xffff));assert source.register() and source.configure() and source.sync(1,0,0)
  peer.send(b'ready')
  while True:
   command=json.loads(peer.recv(1024));op=command['op']
   if op=='offer':result=source.request(60,x=command.get('token',123),state=command.get('state',1))[0].parts[3].x==1
   elif op=='sync':result=source.sync(*command['rgb'])
   elif op=='color':result=source.color()
   elif op=='poll':result=source.request(5)[0].parts[0].height
   elif op=='ack':result=source.request(67,x=command['token'])[0].parts[3].x==1
   elif op=='panel':result=source.request(59,state=command['state'])[0].parts[3].x==1
   elif op=='remove':result=source.request(6)[0].width==0
   elif op=='new':source.control+=1;result=source.configure() and source.sync(0,0,1)
   elif op=='exit':source.close();peer.close();os._exit(0)
   peer.send(json.dumps(result).encode())
 peer.close();assert control.recv(1024)==b'ready'
 def source(op,**data):control.send(json.dumps(dict(op=op,**data)).encode());return json.loads(control.recv(1024))
 try:
  check('missing-offer-cannot-be-borrowed',parent.request(61,x=123)[0].parts[3].x==0)
  check('reveal-cannot-create-native-session',not source('panel',state=2))
  check('malformed-source-offer-rejected',not source('offer',state=3))
  check('source-publishes-owned-reference',source('offer'))
  # A sibling is not an ancestor and cannot acquire its sibling's reference.
  result_read,result_write=os.pipe();ack_read,ack_write=os.pipe();sibling=os.fork()
  if not sibling:
   os.close(result_read);os.close(ack_write);control.close();parent.close();other=Client(a.endpoint,0xa3000000+(os.getpid()&0xffff));assert other.register()
   allowed=other.request(61,x=123)[0].parts[3].x==1
   assert other.configure() and other.sync(0,0,1) and other.request(60,x=123,state=1)[0].parts[3].x==1
   os.write(result_write,b'1' if allowed else b'0');assert os.read(ack_read,1)==b'x';other.close();os._exit(0)
  os.close(result_write);os.close(ack_read);denied=os.read(result_read,1)==b'0';os.close(result_read)
  check('sibling-process-cannot-borrow',denied)
  check('ambiguous-live-sources-are-rejected',parent.request(61,x=123)[0].parts[3].x==0)
  os.write(ack_write,b'x');os.close(ack_write);assert os.waitpid(sibling,0)[1]==0
  check('ancestor-borrows-existing-native-well',parent.request(61,x=123)[0].parts[3].x==1)
  check('borrowed-native-color-model',parent.color()==[1,0,0,1])
  result_read,result_write=os.pipe();inheritor=os.fork()
  if not inheritor:
   os.close(result_read);control.close()
   # Same inherited socket and claimed identity, different kernel sender PID.
   os.write(result_write,b'1' if parent.color() is not None else b'0');parent.close();os._exit(0)
  os.close(result_write);denied=os.read(result_read,1)==b'0';os.close(result_read);assert os.waitpid(inheritor,0)[1]==0
  check('inherited-socket-cannot-impersonate-borrower',denied)
  check('borrower-cannot-write-source-model',not parent.sync(0,1,0) and source('color')==[1,0,0,1])
  check('borrower-opens-original-panel',parent.request(59,state=1)[0].parts[0].height==1 and source('poll')==1)
  panel=panel_window()
  capture_stage('color-owner-before-wheel')
  panel=panel_window()
  # This fixture has no browser activation token. Acquire actual focus with
  # ordinary titlebar input, then choose the original panel's wheel tab: the
  # shared NSColorPanel remembers the mode used by earlier browser trials.
  for text in [f"pointer {round(panel['x']+panel['width']/2)} {panel['y']+11}",'button 272 1','button 272 0']:assert desktop(text)['ok']
  deadline=time.monotonic()+3
  while not panel_window()['focused'] and time.monotonic()<deadline:time.sleep(.02)
  check('fixture-panel-acquires-focus-through-titlebar',panel_window()['focused'])
  for text in [f"pointer {round(panel['x']+panel['width']/2)} {panel['y']+84}",'button 272 1','button 272 0']:assert desktop(text)['ok']
  capture_stage('color-owner-wheel-tab-selected')
  panel=panel_window()
  for text in [f"pointer {panel['x']+120} {panel['y']+155}",'button 272 1','button 272 0']:assert desktop(text)['ok']
  deadline=time.monotonic()+3;selected=parent.color()
  while selected==[1,0,0,1] and time.monotonic()<deadline:time.sleep(.02);selected=parent.color()
  actions=parent.request(5)[0].parts[0].width
  capture_stage('color-owner-after-wheel')
  check('real-native-wheel-action-through-borrowed-well',selected!=[1,0,0,1] and actions>0,color=selected)
  check('stale-source-echo-cannot-overwrite-native-action',source('sync',rgb=[1,0,0]) and parent.color()==selected)
  check('source-script-model-stays-authoritative',source('sync',rgb=[0,1,0]) and parent.color()==[0,1,0,1])
  response=parent.request(5)[0]
  check('programmatic-update-is-not-native-action',response.parts[0].width==actions and response.parts[2].height==actions)
  parent.control=2;check('single-reference-has-one-borrower',parent.request(61,x=123)[0].parts[3].x==0);parent.control=1
  foreign=Client(a.endpoint,parent.process)
  try:check('foreign-connection-cannot-read-reference',foreign.color() is None)
  finally:foreign.close()
  check('return-reference-closes-panel',parent.request(62)[0].parts[3].x==1 and source('poll')==0)
  check('return-keeps-original-field-alive',source('color')==[0,1,0,1])
  def panel_visible(expected=True):return bool(panel_window(expected))
  def close_panel():
   panel=panel_window()
   for text in [f"pointer {panel['x']+panel['width']-10} {panel['y']+10}",'button 272 1','button 272 0']:
    assert desktop(text)['ok']
   deadline=time.monotonic()+3
   while source('poll') and time.monotonic()<deadline:time.sleep(.02)
  check('source-publishes-deferred-reference',source('offer',state=2,token=201))
  check('borrowed-deferred-panel-opens',parent.request(61,x=201)[0].parts[3].x==1 and parent.request(59,state=1)[0].parts[0].height==1)
  existing_panel=panel_window()['id']
  check('source-reveals-running-borrowed-panel',source('panel',state=2))
  check('reveal-retains-original-native-panel',panel_window()['id']==existing_panel)
  check('reveal-keeps-borrowed-reference',parent.color()==source('color'))
  close_panel()
  check('native-close-waits-for-original-model',source('poll')==0 and panel_visible())
  check('borrower-cannot-acknowledge-source-model',parent.request(67,x=201)[0].parts[3].x==0 and panel_visible())
  check('wrong-session-acknowledgement-rejected',not source('ack',token=200) and panel_visible())
  check('return-reference-keeps-deferred-panel',parent.request(62)[0].parts[3].x==1 and panel_visible())
  check('original-source-acknowledgement-closes-panel',source('ack',token=201) and not panel_visible(False))
  check('duplicate-source-acknowledgement-is-idempotent',source('ack',token=201) and not panel_visible(False))
  check('new-deferred-session-opens',source('offer',state=2,token=202) and parent.request(61,x=202)[0].parts[3].x==1 and parent.request(59,state=1)[0].parts[0].height==1)
  check('old-session-cannot-close-reopened-native-panel',not source('ack',token=201) and source('poll')==1 and panel_visible())
  check('original-model-completion-requests-and-closes',source('ack',token=202) and not panel_visible(False))
  check('deferred-reference-return-after-completion',parent.request(62)[0].parts[3].x==1)
  check('direct-source-publishes-deferred-session',source('offer',state=2,token=203) and source('panel',state=1) and panel_visible())
  close_panel()
  check('direct-source-close-waits-for-model',source('poll')==0 and panel_visible())
  check('direct-source-model-acknowledgement-closes',source('ack',token=203) and not panel_visible(False))
  check('source-can-republish-reference',source('offer') and parent.request(61,x=123)[0].parts[3].x==1)
  parent.request(59,state=1);source('remove')
  check('source-retirement-revokes-reference',parent.color() is None and parent.request(5)[0].width==0)
  check('new-source-instance',source('new') and source('offer',token=124))
  parent.control=3;check('new-instance-borrows-own-color',parent.request(61,x=124)[0].parts[3].x==1 and parent.color()==[0,0,1,1])
  parent.request(59,state=1);control.send(json.dumps(dict(op='exit')).encode());assert os.waitpid(child,0)[1]==0;child=0
  deadline=time.monotonic()+3
  while parent.color() is not None and time.monotonic()<deadline:time.sleep(.02)
  check('source-exit-revokes-reference',parent.color() is None and parent.request(5)[0].width==0)
 finally:
  if child:
   try:control.send(json.dumps(dict(op='exit')).encode());os.waitpid(child,0)
   except (OSError,BrokenPipeError):pass
  control.close();parent.close()
 print(json.dumps(dict(passed=len(rows))))

if __name__=='__main__':main()
