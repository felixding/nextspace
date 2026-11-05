#!/usr/bin/env python3
"""Check real native popup models, keys, tracking and lifecycle over IPC."""
import argparse
import ctypes as C
import json
import os
from pathlib import Path
import socket
import time
from helper import Response
from native_controls import ControlRequest,ControlInputRequest,ControlPopupRequest,MAGIC

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--socket',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--references',type=Path,required=True)
p.add_argument('--helper-pid',type=int,required=True)
a,_=p.parse_known_args();a.output.mkdir(parents=True,exist_ok=True)
connection=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET);connection.settimeout(3);connection.connect(str(a.socket))
process=0x504f5055;sequence=0;control=1;results=[]
items=[('First',1),('Disabled',0),('',2),('Repeated',1),('First',1)]

def exchange(req,payload=b''):
    global sequence
    sequence+=1;req.reserved=sequence
    connection.sendmsg([bytes(req),payload]);data=connection.recv(65536)
    response=Response.from_buffer_copy(data)
    assert response.magic==MAGIC and response.size==len(data) and response.reserved==sequence
    return response,data[C.sizeof(Response):]

def request(operation,**values):
    req=ControlRequest(magic=MAGIC,operation=operation,process=process,kind=6,control=control,
        width=180,height=24,maximum=1,value=-1,enabled=1)
    for name,value in values.items():setattr(req,name,value)
    return exchange(req)

def model(selected=0,owner=process,payload=None):
    if payload is None:
        payload=b''.join(flags.to_bytes(4,'little')+len(title.encode()).to_bytes(4,'little')+title.encode() for title,flags in items)
    req=ControlPopupRequest(magic=MAGIC,operation=11,process=owner,kind=6,control=control,
        text_size=len(payload),count=len(items),selected=selected)
    return exchange(req,payload)

def input(operation=8,key=0,text=b'',**values):
    req=ControlInputRequest(magic=MAGIC,operation=operation,process=process,kind=6,control=control,
        key=key,text_size=len(text),unmodified_size=len(text))
    for name,value in values.items():setattr(req,name,value)
    return exchange(req,text+text)[0]

def check(case,condition,**data):
    results.append(dict(case=case,passed=bool(condition),**data))
    (a.output/'results.json').write_text(json.dumps(results,indent=2)+'\n');assert condition,results[-1]

def hold(stage):
    if os.environ.get('NXS_NATIVE_UI_POPUP_HOLD'):
        print(json.dumps(dict(event=stage)),flush=True);assert input_line()=='\n'

def input_line():
    import sys
    return sys.stdin.readline()

def wait_for(predicate):
    deadline=time.monotonic()+3
    while True:
        response=request(5)[0]
        if predicate(response):return response
        assert time.monotonic()<deadline,'Native popup state timeout'
        time.sleep(.01)

try:
    response,_=request(1)
    check('popup-capability',response.parts[5].height==1)
    check('native-screen-origin-request',request(13,x=240,y=160)[0].parts[3].x==1)
    response,pixels=model()
    check('native-item-model',response.parts[3].x==1 and response.parts[0].x==0)
    (a.output/'popup-normal.argb').write_bytes(pixels)
    check('native-control-pixels',pixels==(a.references/'popup-normal.argb').read_bytes())
    check('native-focus',input(operation=7,focused=1).parts[3].y==1)
    response,pixels=request(1,value=0)
    (a.output/'popup-focused.argb').write_bytes(pixels)
    check('native-focus-pixels',pixels==(a.references/'popup-focused.argb').read_bytes())
    hold('host-live')
    check('native-open-key',input(text=b' ').parts[6].width>0)
    # No RPCs while this sleeps: native Wayland/window events must continue
    # through the native loop. The parent observes its mapped menu window.
    time.sleep(.1)
    def cpu_time():
        fields=Path('/proc/'+str(a.helper_pid)+'/stat').read_text().rsplit(') ',1)[1].split()
        return (int(fields[11])+int(fields[12]))/os.sysconf('SC_CLK_TCK')
    before=cpu_time();time.sleep(.2);used=cpu_time()-before
    check('idle-menu-no-busy-poll',used<.1,cpu_seconds=used,wall_seconds=.2)
    hold('popup-live')
    response=input(key=5)
    check('native-escape-cancels',response.parts[6].width==0 and response.parts[0].width==0)
    hold('popup-closed')
    input(text=b' ');input(key=9);input(key=1)
    check('disabled-item-no-selection',request(5)[0].parts[0].x==0 and request(5)[0].parts[0].width==0)
    input(key=5);model()
    input(text=b' ')
    for unused in range(3):input(key=9)
    response=input(key=1)
    check('native-keyboard-selection',response.parts[0].x==3 and response.parts[0].width==1 and response.parts[6].width==0)
    response,_=model(selected=4)
    check('duplicate-label-index-retained',response.parts[3].x==1 and response.parts[0].x==4)
    check('other-process-model-isolated',model(selected=0,owner=process+1)[0].parts[3].x==0 and request(5)[0].parts[0].x==4)
    invalid=b'\x01\0\0\0\x01\0\0\0\xff'
    check('invalid-model-atomic',model(payload=invalid)[0].parts[3].x==0 and request(5)[0].parts[0].x==4)
    model(selected=0);request(2,x=18,y=12)
    wait_for(lambda r:r.parts[0].y and r.parts[6].width>0)
    deadline=time.monotonic()+3
    while True:
        rect=request(12,x=4)[0].parts[6]
        request(3,x=rect.x+rect.width/2,y=rect.y+rect.height/2)
        response=request(5)[0]
        if response.parts[5].y==4:break
        assert time.monotonic()<deadline
        time.sleep(.01)
    check('tracking-rejects-model-replacement',model()[0].parts[3].x==0)
    request(4,x=rect.x+rect.width/2,y=rect.y+rect.height/2)
    response=wait_for(lambda r:not r.parts[0].y)
    check('native-mouse-selection',response.parts[0].x==4 and response.parts[0].width==2)
    request(1,enabled=0,value=4)
    before=request(5)[0].parts[0].width;input(text=b' ')
    check('disabled-no-menu-or-action',request(5)[0].parts[6].width==0 and request(5)[0].parts[0].width==before)
    request(1,enabled=1,value=4);input(operation=7,focused=1);input(text=b' ')
    request(6)
    response=wait_for(lambda r:r.parts[6].width==0)
    check('destroy-open-menu',response.parts[6].width==0)
finally:connection.close()
print(json.dumps(dict(passed=len(results),results=results)))
