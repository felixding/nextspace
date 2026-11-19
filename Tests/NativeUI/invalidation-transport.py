#!/usr/bin/env python3
"""Observe real native animation without repainting unrelated controls."""
import argparse,importlib.util,json,os,struct,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('color_transport',Path(__file__).with_name('color-owner-transport.py'))
wire=importlib.util.module_from_spec(spec);spec.loader.exec_module(wire)
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--endpoint',required=True);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
rows=[]
def check(case,passed,**details):
 rows.append(dict(case=case,passed=bool(passed),**details));a.output.write_text(json.dumps(rows,indent=2)+'\n');assert passed,rows[-1]
client=wire.Client(a.endpoint,0xb4000000+(os.getpid()&0xffff))
def request(operation,kind=0,control=0,**values):return client.request(operation,kind=kind,control=control,**values)
def draw(kind,control):
 if kind==5:return request(1,kind,control,width=80,height=20,maximum=1,enabled=1,indeterminate=1)
 return request(5,kind,control)
def snapshot(since):
 response,data=request(9,value=since)
 assert len(data)>=8,'Host omitted native dirty-control receipts'
 magic,count=struct.unpack_from('II',data);assert magic==0x4e584449
 if count==0xffffffff:assert len(data)==8;return response.parts[4].x,None
 assert count<=1024 and len(data)==8+count*16
 ids=[(kind,control) for control,kind,reserved in struct.iter_unpack('QII',data[8:]) if not reserved]
 assert len(ids)==count
 return response.parts[4].x,ids
try:
 check('live-notification-owner',client.register())
 for kind,control in [(7,1),(5,2)]:
  r,_=request(1,kind,control,width=80,height=20,maximum=1,enabled=1,indeterminate=int(kind==5))
  check('native-control-created-'+str(kind),r.width==80 and r.height==20)
 generation,dirty=snapshot(0);check('initial-snapshot-requires-full-resync',dirty is None)
 for kind,control in [(7,1),(5,2)]:draw(kind,control)
 deadline=time.monotonic()+12;cycles=0
 while cycles<5:
  previous=generation;generation,dirty=snapshot(previous)
  if dirty is None:
   for kind,control in [(7,1),(5,2)]:draw(kind,control)
  if dirty is not None and (5,2) in dirty:
   check('native-animation-isolated-'+str(cycles),(7,1) not in dirty,controls=dirty)
   draw(5,2)  # Another image reader must not consume the receipt.
   ignored,repeated=snapshot(previous)
   check('image-read-preserves-animation-receipt-'+str(cycles),repeated is not None and (5,2) in repeated)
   cycles+=1
  assert time.monotonic()<deadline,'Original native animation did not advance'
  time.sleep(.03)
 # A borrowed color well must not wake for another source control's animation.
 request(1,16,3,width=80,height=20,maximum=1,enabled=1)
 request(60,16,3,x=12345,state=1)
 parent=wire.Client(a.endpoint,0xb5000000+(os.getpid()&0xffff))
 try:
  check('color-borrower-notification-owner',parent.register())
  check('color-alias-owned-reference',parent.request(61,x=12345)[0].parts[3].x==1)
  try:os.eventfd_read(parent.fd)
  except BlockingIOError:pass
  start=parent.request(9,kind=0,control=0)[0].parts[4].x
  for cycle in range(3):
   draw(5,2);time.sleep(.08);snapshot(generation)
  current=parent.request(9,kind=0,control=0)[0].parts[4].x
  check('borrower-ignores-unrelated-native-animation',current==start,before=start,after=current)
  client.control=3;check('source-color-model-changes',client.sync(1,0,0))
  current=parent.request(9,kind=0,control=0)[0].parts[4].x
  check('borrower-receives-its-color-model-change',current>start and parent.color()[:3]==[1,0,0])
 finally:parent.close()
 # The original packet format remains sufficient for a legacy polling client.
 response,legacy=request(9);check('legacy-generation-zero-remains-full-resync',struct.unpack_from('II',legacy)==(0x4e584449,0xffffffff))
 print(json.dumps(dict(complete=True,checks=len(rows))))
finally:client.close()
