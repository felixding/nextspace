"""Real native button receives a release queued before its tracking starts."""
import argparse,ctypes as C,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Experiments/ChromiumScrollers'))
from helper import Bitmap,Pump,Response
from native_controls import NativeControlServer,ControlRequest,MAGIC
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--library',required=True);a,_=p.parse_known_args()
pending=[];events=[];replies=[];client=object();native=C.CDLL(a.library)
server=NativeControlServer(native,Bitmap,Response,Pump,lambda _:None,pending,
 lambda client,response,data:replies.append(bytes(response)),lambda:not pending and server.active is None,
 lambda event,**fields:events.append(dict(event=event,**fields)))
checks=[]
def send(control,operation,**values):
 r=ControlRequest(magic=MAGIC,operation=operation,process=1,control=control,kind=1,reserved=operation,width=120,height=24,enabled=1,**values)
 server.message(client,bytes(r))
def trial(control,release,expected,cancel=False,destroy=False):
 send(control,1);send(control,2,x=10,y=10)
 assert server.controls[(1,control,1)]['starting']
 if release!=(10,10):send(control,3,x=release[0],y=release[1])
 send(control,4,x=release[0],y=release[1])
 if cancel:send(control,68,value=2)
 if destroy:send(control,6)
 while pending:pending.pop(0)()
 state=server.controls[(1,control,1)]
 assert state['actions']==expected,(control,state['actions'],events)
 assert not server._tracking(state)
 checks.append(dict(case=str(control),actions=state['actions'],passed=True))
try:
 trial(1,(10,10),1)
 trial(2,(-100,-100),0)
 trial(3,(10,10),0,cancel=True)
 trial(4,(10,10),0,destroy=True)
 assert server.active is None
 print(json.dumps(dict(complete=True,checks=checks)))
finally:server.close()
