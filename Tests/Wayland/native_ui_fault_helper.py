#!/usr/bin/env python3
"""Run the real native host, rejecting one armed list-state request for tests."""
import ctypes as C,json,os,runpy,sys
from pathlib import Path
source=Path(__file__).resolve().parents[2]/'Experiments/ChromiumScrollers'
sys.path.insert(0,str(source))
from native_controls import NativeControlServer,ControlRequest
arm=Path(os.environ['NEXTSPACE_NATIVE_UI_FAULT_FILE'])
original=NativeControlServer.list_message

def list_message(self,client,data):
 if len(data)==C.sizeof(ControlRequest) and int.from_bytes(data[4:8],'little')==49 and arm.exists():
  request=ControlRequest.from_buffer_copy(data);spec=json.loads(arm.read_text())
  state=self.controls.get((request.process,request.control,request.kind))
  if spec==dict(kind=request.kind,operation=request.operation) and state and state['client'] is client and not state['destroy']:
   arm.unlink();receipt=dict(process=request.process,control=request.control,kind=request.kind,operation=request.operation)
   self.log('test-native-control-rejection',**receipt)
   arm.with_suffix('.receipt.json').write_text(json.dumps(receipt)+'\n')
   self._respond(client,request,state,input_result=0);return
 return original(self,client,data)

NativeControlServer.list_message=list_message
runpy.run_path(str(source/'helper.py'),run_name='__main__')
