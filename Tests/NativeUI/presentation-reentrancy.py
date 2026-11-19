#!/usr/bin/env python3
"""Present a real native panel while another client's native command is active."""
import argparse,ctypes as C,importlib.util,json,os,select,socket,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('wire',str(Path(__file__).with_name('color-owner-transport.py')));wire=importlib.util.module_from_spec(spec);spec.loader.exec_module(wire)
from native_controls import ControlInputRequest,NativeCommand,NativeCommandDecision,COMMAND_MAGIC
p=argparse.ArgumentParser();p.add_argument('--endpoint',required=True);p.add_argument('--output',required=True,type=Path);a=p.parse_args();rows=[]
def check(case,passed,**info):
 rows.append(dict(case=case,passed=bool(passed),**info));a.output.write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
first=wire.Client(a.endpoint,0xb6000000+(os.getpid()&0xffff));second=wire.Client(a.endpoint,0xb7000000+(os.getpid()&0xffff))
third=wire.Client(a.endpoint,0xb8000000+(os.getpid()&0xffff))
callback,peer=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);callback.settimeout(3)
try:
 check('live-native-owners',first.register() and second.register() and third.register())
 check('native-button-created',third.request(1,kind=1,width=120,height=24,enabled=1)[0].width==120)
 check('native-editor-created',first.request(1,kind=7,width=120,height=24,enabled=1)[0].width==120)
 req=wire.ControlRequest(magic=wire.MAGIC,operation=19,process=first.process)
 check('native-callback-registered',first.exchange(req,peer.fileno())[0].parts[3].x==1)
 check('native-command-registered',first.request(23,kind=0,control=0,state=1)[0].parts[3].x==1)
 check('native-color-created',second.configure() and second.sync(.25,.5,.75))
 check('same-owner-color-created',first.request(1,kind=16,control=2,width=120,height=24,enabled=1)[0].width==120)
 req=ControlInputRequest(magic=wire.MAGIC,operation=7,process=first.process,kind=7,control=1,focused=1)
 check('native-editor-focused',first.exchange(req)[0].parts[3].y==1)
 req=ControlInputRequest(magic=wire.MAGIC,operation=8,process=first.process,kind=7,control=1,type=0,modifiers=2,key=0,text_size=1,unmodified_size=1)
 first.socket.send(bytes(req)+b'zz');opening=None;early=None;key_early=None;commands=[]
 while True:
  ready=select.select([callback,first.socket],[],[],3)[0];assert ready,'Native command did not complete'
  if callback in ready:
   data=callback.recv(4096);cmd=NativeCommand.from_buffer_copy(data);assert cmd.magic==COMMAND_MAGIC
   commands.append(dict(selector=data[C.sizeof(cmd):].decode(),phase=cmd.phase))
   if cmd.phase==1 and opening is None:
    # A callback owner cannot wait for its own native stack to unwind.
    # Preserve the provider's existing immediate refusal for that owner.
    own=wire.ControlRequest(magic=wire.MAGIC,operation=59,process=first.process,kind=16,control=2,state=1,reserved=91)
    first.socket.send(bytes(own))
    check('own-callback-does-not-deadlock',bool(select.select([first.socket],[],[],1)[0]))
    own_reply=wire.Response.from_buffer_copy(first.socket.recv(65536))
    check('own-callback-keeps-original-native-refusal',own_reply.reserved==91 and own_reply.parts[3].x==0)
    focus=ControlInputRequest(magic=wire.MAGIC,operation=7,process=third.process,kind=1,control=1,focused=1)
    check('other-native-button-focused',third.exchange(focus)[0].parts[3].y==1)
    key=ControlInputRequest(magic=wire.MAGIC,operation=8,process=third.process,kind=1,control=1,type=0,text_size=1,unmodified_size=1)
    third.socket.send(bytes(key)+b'  ')
    if select.select([third.socket],[],[],.15)[0]:key_early=third.socket.recv(65536)
    req=wire.ControlRequest(magic=wire.MAGIC,operation=59,process=second.process,kind=16,control=1,state=1)
    second.socket.send(bytes(req));opening=True
    if select.select([second.socket],[],[],.15)[0]:early=second.socket.recv(65536)
   callback.send(bytes(NativeCommandDecision(magic=cmd.magic,result=1,serial=cmd.serial)))
  if first.socket in ready:first.socket.recv(65536);break
 check('original-native-command-ran',opening is True and any(c['phase']==1 for c in commands),commands=commands)
 key_data=key_early if key_early is not None else third.socket.recv(65536)
 key_reply=wire.Response.from_buffer_copy(key_data)
 check('key-waits-for-unrelated-native-stack',key_early is None)
 check('original-native-button-handles-the-held-key-once',key_reply.parts[3].x==1 and key_reply.parts[0].width==1)
 data=early if early is not None else second.socket.recv(65536);r=wire.Response.from_buffer_copy(data)
 check('presentation-waits-for-native-stack',early is None,early_accepted=r.parts[3].x)
 check('original-panel-presentation-accepted',r.parts[3].x==1 and r.parts[0].height==1)
 check('original-panel-remains-open',second.request(0)[0].parts[0].height==1)
 check('explicit-native-panel-close',second.request(59,state=0)[0].parts[3].x==1 and second.request(0)[0].parts[0].height==0)
 print(json.dumps(dict(complete=True,checks=len(rows))))
finally:
 first.close();second.close();third.close();callback.close();peer.close()
