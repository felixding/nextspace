#!/usr/bin/env python3
"""Experimental renderer transport to the unchanged native NSScroller bridge."""
import argparse,ctypes as C,json,os,select,socket
from pathlib import Path
class Request(C.Structure):
    _fields_=[('magic',C.c_uint32),('operation',C.c_uint32),('process',C.c_uint32),('layer',C.c_uint32),('control',C.c_uint64),('horizontal',C.c_int32),('reserved',C.c_int32),('length',C.c_double),('total',C.c_double),('page',C.c_double),('value',C.c_double)]
class Rect(C.Structure):
    _fields_=[('x',C.c_double),('y',C.c_double),('width',C.c_double),('height',C.c_double)]
class Response(C.Structure):
    _fields_=[('magic',C.c_uint32),('size',C.c_uint32),('width',C.c_int32),('height',C.c_int32),('stride',C.c_int32),('reserved',C.c_int32),('parts',Rect*7)]
class Bitmap(C.Structure):
    _fields_=[('width',C.c_int),('height',C.c_int),('stride',C.c_int),('pixels',C.c_void_p)]
Changed=C.CFUNCTYPE(None,C.c_void_p,C.c_double)
Pump=C.CFUNCTYPE(None,C.c_void_p)

def run(library,path):
    native=C.CDLL(str(library));native.nxs_scroller_create.argtypes=[C.c_int,Changed,Pump,C.c_void_p];native.nxs_scroller_create.restype=C.c_void_p
    native.nxs_scroller_sync.argtypes=[C.c_void_p]+[C.c_double]*7+[C.c_int]
    native.nxs_scroller_part.argtypes=[C.c_void_p,C.c_int];native.nxs_scroller_part.restype=Rect
    native.nxs_scroller_draw.argtypes=[C.c_void_p,C.c_double];native.nxs_scroller_draw.restype=Bitmap
    native.nxs_scroller_destroy.argtypes=[C.c_void_p]
    native.nxs_scroller_tracking.argtypes=[C.c_void_p];native.nxs_scroller_tracking.restype=C.c_int
    native.nxs_scroller_track.argtypes=[C.c_void_p,C.c_double,C.c_double,C.c_uint]
    native.nxs_scroller_send.argtypes=[C.c_void_p,C.c_int,C.c_double,C.c_double,C.c_uint]
    server=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET);server.bind(str(path));os.chmod(path,0o600);server.listen(20)
    clients=[];controls={};contexts={};pending=[];active=None
    def log(event,**data):print(json.dumps(dict(event=event,**data)),flush=True)
    @Changed
    def changed(context,value):
        state=contexts[context];state['value']=value
        log('native-action',process=state['key'][0],control=state['key'][1],value=value)
    @Pump
    def pump(context):dispatch(0)
    def response(client,req,state,pixels=False):
        result=Response();result.magic=req.magic;result.reserved=req.reserved
        if state and state.get('native'):
            for part in range(1,7):result.parts[part]=native.nxs_scroller_part(state['native'],part)
            result.parts[0].x=state['value'];result.parts[0].y=bool(state.get('starting') or native.nxs_scroller_tracking(state['native']))
        data=b''
        if pixels:
            bitmap=native.nxs_scroller_draw(state['native'],1)
            result.width=bitmap.width;result.height=bitmap.height;result.stride=bitmap.stride
            data=C.string_at(bitmap.pixels,bitmap.stride*bitmap.height)
        result.size=C.sizeof(Response)+len(data)
        client.sendmsg([bytes(result),data])
    def message(client,data):
        if len(data)!=C.sizeof(Request):return
        req=Request.from_buffer_copy(data)
        if req.magic!=0x4e585343:return
        key=(req.process,req.control,req.horizontal);state=controls.get(key)
        if req.operation==1:
            if req.layer>1 or not 1<=req.length<=8192:return
            if state is None:
                context=len(contexts)+1;state=dict(key=key,context=context,value=req.value,client=client,destroy=False);contexts[context]=state
                state['native']=native.nxs_scroller_create(req.horizontal,changed,pump,context);controls[key]=state
                if not state['native']:raise RuntimeError('Native NSScroller initialization failed')
                log('native-control',process=req.process,control=req.control,horizontal=bool(req.horizontal),length=req.length,total=req.total,page=req.page)
            metrics=(req.length,req.total,req.page)
            if state.get('metrics')!=metrics:
                state['metrics']=metrics
                log('native-metrics',process=req.process,control=req.control,horizontal=bool(req.horizontal),length=req.length,total=req.total,page=req.page)
            if not native.nxs_scroller_tracking(state['native']):state['value']=req.value
            native.nxs_scroller_sync(state['native'],req.length,0,req.total,req.page,40,req.page*.875,state['value'],1)
            response(client,req,state,req.layer==1)
        elif state:
            if req.operation==2 and active is None:
                state['starting']=True;pending.append((state,req.length,req.total,int(req.page)))
                log('native-press',process=req.process,control=req.control,x=req.length,y=req.total,modifiers=int(req.page))
            elif req.operation in (3,4) and native.nxs_scroller_tracking(state['native']):
                native.nxs_scroller_send(state['native'],0 if req.operation==3 else 1,req.length,req.total,int(req.page))
            elif req.operation==6:
                state['destroy']=True
                if native.nxs_scroller_tracking(state['native']):native.nxs_scroller_send(state['native'],1,0,0,0)
            response(client,req,state)
        else:response(client,req,None)
    def dispatch(timeout):
        ready,_,_=select.select([server]+clients,[],[],timeout)
        for client in ready:
            if client is server:
                connection,_=server.accept();clients.append(connection);continue
            try:
                data=client.recv(4096)
                if data:message(client,data);continue
            except (BrokenPipeError,ConnectionResetError):pass
            if active and active['client'] is client:native.nxs_scroller_send(active['native'],1,0,0,0)
            clients.remove(client);client.close()
    log('ready',socket=str(path),request_size=C.sizeof(Request),response_size=C.sizeof(Response))
    try:
        while True:
            dispatch(None)
            while pending:
                state,x,y,modifiers=pending.pop(0);active=state;state['starting']=False
                native.nxs_scroller_track(state['native'],x,y,modifiers)
                active=None;log('native-release',process=state['key'][0],control=state['key'][1],value=state['value'])
            for key,state in list(controls.items()):
                if state['destroy'] and not native.nxs_scroller_tracking(state['native']):
                    native.nxs_scroller_destroy(state['native']);state['native']=None;del controls[key];del contexts[state['context']]
    finally:
        for state in controls.values():native.nxs_scroller_destroy(state['native'])
        for client in clients:client.close()
        server.close();path.unlink(missing_ok=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--library',type=Path,required=True);p.add_argument('--socket',type=Path,required=True);args,remaining=p.parse_known_args();run(args.library,args.socket)
