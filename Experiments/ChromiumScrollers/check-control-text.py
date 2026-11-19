#!/usr/bin/env python3
"""Check real native text editors over the shared browser helper transport."""
import argparse
import array
import ctypes as C
import json
import os
from pathlib import Path
import socket
import sys
from helper import Request,Response
from native_controls import ControlRequest,ControlInputRequest,ControlTextRequest,TextResponse,MAGIC
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--socket',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--references',type=Path,required=True)
a,_=p.parse_known_args();a.output.mkdir(parents=True,exist_ok=True)
connection=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET);connection.settimeout(3);connection.connect(str(a.socket))
process=0x54455854;sequence=0;results=[];kind=7
assert C.sizeof(ControlTextRequest)==56 and C.sizeof(TextResponse)==40

def exchange(req,payload=b''):
    global sequence
    sequence+=1;req.reserved=sequence
    connection.sendmsg([bytes(req),payload])
    data,ancillary,flags,_=connection.recvmsg(1024*1024,socket.CMSG_SPACE(16))
    assert not flags&(socket.MSG_TRUNC|socket.MSG_CTRUNC)
    response=Response.from_buffer_copy(data)
    for level,typ,raw in ancillary:
        if level==socket.SOL_SOCKET and typ==socket.SCM_RIGHTS:
            descriptors=array.array('i');descriptors.frombytes(raw)
            try:
                size=response.size-C.sizeof(Response)
                payload=os.pread(descriptors[0],size,0);assert len(payload)==size
                data+=payload
            finally:
                for fd in descriptors:os.close(fd)
    assert response.magic==req.magic and response.size==len(data) and response.reserved==sequence
    return response,data[C.sizeof(Response):]

def request(operation,**values):
    req=ControlRequest(magic=MAGIC,operation=operation,process=process,kind=kind,control=kind,
        width=180,height=24,maximum=1,enabled=1)
    for name,value in values.items():setattr(req,name,value)
    return exchange(req)

def model(text,start=0,length=0,editable=1):
    text=text.encode() if isinstance(text,str) else text
    req=ControlTextRequest(magic=MAGIC,operation=17,process=process,kind=kind,control=kind,
        text_size=len(text),selection_start=start,selection_length=length,editable=editable)
    return exchange(req,text)

def key(text=b'',key=0,modifiers=0,operation=8,focused=0):
    req=ControlInputRequest(magic=MAGIC,operation=operation,process=process,kind=kind,control=kind,
        text_size=len(text),unmodified_size=len(text),key=key,modifiers=modifiers,focused=focused)
    return exchange(req,text+text)[0]

def value(expected):
    response,payload=request(18)
    assert response.parts[3].x==1
    state=TextResponse.from_buffer_copy(payload)
    text=payload[C.sizeof(TextResponse):]
    assert len(text)==state.text_size and text.decode()==expected
    return state,response

def check(case,condition):
    results.append(dict(case=case,passed=bool(condition)))
    (a.output/'results.json').write_text(json.dumps(results,indent=2)+'\n');assert condition,case

try:
    bootstrap,_=exchange(Request(magic=0x4e585343,operation=7,process=process))
    for kind in (7,8):
        label='password' if kind==8 else 'text'
        response,_=request(1)
        check(label+'-created',response.width==180 and response.height==24)
        response,pixels=model('Hello',1,2)
        check(label+'-model',response.parts[3].x==1 and response.parts[0].width==0)
        suffix='secure-normal' if kind==8 else 'normal'
        (a.output/(label+'-native.argb')).write_bytes(pixels)
        check(label+'-native-pixels',pixels==(a.references/('text-'+suffix+'.argb')).read_bytes())
        check(label+'-focus',key(operation=7,focused=1).parts[3].y==1)
        if bootstrap.parts[5].x==1:
            for invalid in (0,-1):
                check(label+'-reject-click-count-'+str(invalid),request(22,state=invalid,x=25,y=12)[0].parts[3].x==0)
            for clicks in (2,3):
                model('Alpha beta')
                response,_=request(22,state=clicks,x=25,y=12)
                check(label+'-click-count-accepted-'+str(clicks),response.parts[3].x==1)
                check(label+'-busy-click-rejected-'+str(clicks),request(22,state=clicks,x=25,y=12)[0].parts[3].x==0)
                request(4,x=25,y=12)
                state,response=value('Alpha beta')
                check(label+'-native-click-selection-'+str(clicks),state.selection_start==0 and
                    state.selection_length==(10 if clicks==3 else 5))
            model('Hello',1,2)
        response,pixels=request(1)
        suffix='secure-focused' if kind==8 else 'focused'
        check(label+'-native-focused-pixels',pixels==(a.references/('text-'+suffix+'.argb')).read_bytes())
        key(b'X');state,response=value('HXlo')
        check(label+'-selection-replace',state.selection_start==2 and state.selection_length==0 and response.parts[2].width==1)
        key(key=3);value('Hlo')
        reported,command=request(21)
        if reported.parts[3].x==1:check(label+'-native-command-selector',command==b'deleteBackward:')
        check(label+'-tab',key(key=2).parts[3].x==2)
        check(label+'-backtab',key(key=2,modifiers=1).parts[3].x==3)
        model('日本語Café🙂',9);key(b'X');value('日本語Café🙂X')
        check(label+'-utf16-unicode',True)
        if kind==7:
            model('Alpha beta',5);key(b'a',modifiers=4)
            check('emacs-control-a',value('Alpha beta')[0].selection_start==0)
            key(b'e',modifiers=4)
            check('emacs-control-e',value('Alpha beta')[0].selection_start==10)
            model('Copy me',0,7);key(b'c',modifiers=2);value('Copy me')
            reported,command=request(21)
            if reported.parts[3].x==1:check('native-copy-command-without-mutation',command==b'copy:')
            model('Destination',11);key(b'v',modifiers=2);value('DestinationCopy me')
            check('native-alt-copy-paste',True)
            model('Cut me',0,6);key(b'x',modifiers=2);value('')
            key(b'v',modifiers=2);value('Cut me');check('native-alt-cut',True)
            model('Copy me',0,7);key(b'c',modifiers=2)
        else:
            model('Protected',0,9);key(b'c',modifiers=2)
            model('');key(b'v',modifiers=2);value('Copy me')
            check('secure-copy-keeps-previous-clipboard',True)
        before=value('Copy me')[1]
        key(key=1);after=request(5)[0]
        check(label+'-return-activation',after.parts[2].height==before.parts[2].height+1)
        model('Read only',0,9,editable=0);before=value('Read only')[1].parts[2].width
        key(b'Y');key(b'v',modifiers=2)
        state,response=value('Read only')
        check(label+'-read-only',not state.flags&2 and response.parts[2].width==before)
        for invalid in (b'bad\0value',b'\xc0'):
            check(label+'-reject-invalid-text',model(invalid)[0].parts[3].x==0);value('Read only')
        check(label+'-reject-invalid-range',model('x',2)[0].parts[3].x==0);value('Read only')
        request(1,enabled=0)
        if bootstrap.parts[5].x==1:
            check(label+'-disabled-click',request(22,state=2,x=25,y=12)[0].parts[3].x==0)
        check(label+'-disabled-focus',key(operation=7,focused=1).parts[3].x==0)
        check(label+'-disabled-key',key(b'Z').parts[3].x==0);value('Read only')
        request(6)
        check(label+'-destroyed',request(18)[0].parts[3].x==0)
    if os.environ.get('NXS_NATIVE_UI_TEXT_HOLD'):
        print(json.dumps(dict(event='host-live')),flush=True);assert sys.stdin.readline()=='\n'
finally:connection.close()
print(json.dumps(dict(native_text_transport=results)))
