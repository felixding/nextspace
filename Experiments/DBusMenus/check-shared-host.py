#!/usr/bin/env python3
"""Check shared-host address authority, client ownership and menu replacement."""
import argparse,ctypes as C,json,os,socket,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ChromiumScrollers'))
from native_controls import ControlRequest,ControlInputRequest,MAGIC
from helper import Response

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);rows=[]
host=json.loads((a.fixture/'menu-binding.json').read_text());assert host['shared_helper']
def check(case,passed,**data):
 rows.append(dict(case=case,passed=bool(passed),**data));(a.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
def control(command):
 with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:
  s.settimeout(15);s.connect(str(a.fixture/'control.sock'));s.send(json.dumps(dict(command=command)).encode());return json.loads(s.recv(65536))
def request(message):return control('menu-broker '+json.dumps(message))
def wait(read,predicate):
 end=time.monotonic()+8
 while True:
  value=read()
  if predicate(value):return value
  assert time.monotonic()<end,value
  time.sleep(.015)
def roots():return [w for w in control('windows') if w['pid']==host['pid'] and w['visible']]
root=wait(roots,lambda ws:len(ws)==1)[0]
window=next(w for w in control('windows') if w['pid']==host['owner'] and w['id']==host['window'])
address=dict(operation='bind',window=window['id'],pid=window['pid'],service=window['appmenu_service'],path=window['appmenu_path'],title='Firefox')
wrong=dict(address,pid=os.getpid());assert wrong['pid']!=host['owner']
check('wrong-window-owner-pid-rejected',not request(wrong)['accepted'])
check('rejected-address-preserves-native-menu',roots()[0]['id']==root['id'])
check('malformed-address-rejected',not request(dict(address,title='bad\0title'))['accepted'])
check('unknown-broker-operation-rejected',not request(dict(operation='invalid'))['accepted'])

# A second client can read the existing diagnostic state but must not claim
# that client's widget to execute a key or change the native first responder.
active={}
for line in Path(host['log']).read_text().splitlines():
 event=json.loads(line)
 if event['event']=='native-form-control':active[(event['process'],event['control'],event['kind'])]=event
 elif event['event']=='native-form-destroy':active.pop((event['process'],event['control'],event['kind']),None)
process,identifier,kind=next(key for key in active if key[2]==7)
arguments=host['arguments'];endpoint=arguments[arguments.index('--socket')+1]
with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as client:
 client.settimeout(8);client.connect(endpoint)
 poll=ControlRequest(magic=MAGIC,operation=5,process=process,kind=kind,control=identifier)
 client.send(bytes(poll));packet=client.recv(128*1024);state=Response.from_buffer_copy(packet)
 check('forged-input-target-is-an-existing-control',state.parts[1].width>0)
 start=len(Path(host['log']).read_text().splitlines())
 for operation in [7,8]:
  data=ControlInputRequest(magic=MAGIC,operation=operation,process=process,kind=kind,control=identifier,
      focused=1,type=0,modifiers=2,key=0,text_size=1,unmodified_size=1)
  if operation==7:data.text_size=data.unmodified_size=0
  client.send(bytes(data)+(b'zz' if operation==8 else b''))
  response=Response.from_buffer_copy(client.recv(128*1024))
  check('other-client-cannot-'+('focus' if operation==7 else 'execute-menu-key'),response.parts[3].x==0)
 trace=[json.loads(line) for line in Path(host['log']).read_text().splitlines()[start:]]
 check('rejected-input-queues-no-application-command',not any(e['event']=='application-command-queued' for e in trace))

check('trusted-source-can-clear-menu',request(dict(operation='clear'))['accepted'])
wait(roots,lambda ws:not ws)
check('shared-helper-survives-menu-removal',Path('/proc',str(host['pid'])).exists())
check('trusted-source-can-rebind-real-address',request(address)['accepted'])
new=wait(roots,lambda ws:len(ws)==1)[0]
check('rebound-menu-is-a-real-native-window',new['level']==20 and not new['accepts_focus'])

# Real GLib/native descriptor wakeups allow an idle wait instead of a busy loop.
def ticks():return sum(int(n) for n in Path('/proc',str(host['pid']),'stat').read_text().split(') ',1)[1].split()[11:13])
before=ticks();time.sleep(.25);elapsed=(ticks()-before)/os.sysconf('SC_CLK_TCK')
check('shared-native-host-does-not-spin-while-idle',elapsed<.1,cpu_seconds=elapsed)
print(json.dumps(dict(passed=len(rows))))
