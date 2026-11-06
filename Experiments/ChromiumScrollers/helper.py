#!/usr/bin/env python3
"""Experimental renderer transport to the independent native UI provider."""
import argparse,array,ctypes as C,fcntl,itertools,json,os,select,signal,socket,struct,sys,time
from pathlib import Path
from native_controls import MAGIC as CONTROL_MAGIC, NativeControlServer, ControlInputRequest
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

def send_response(client,response,data=b''):
    response.size=C.sizeof(response)+len(data)
    if len(data)<=65536:
        client.sendmsg([bytes(response),data])
        return
    descriptor=os.memfd_create('nextspace-native-ui',os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING)
    try:
        remaining=memoryview(data)
        while remaining:remaining=remaining[os.write(descriptor,remaining):]
        fcntl.fcntl(descriptor,fcntl.F_ADD_SEALS,fcntl.F_SEAL_WRITE|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_SEAL)
        client.sendmsg([bytes(response)],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[descriptor]))])
    finally:os.close(descriptor)

def run(library,path,menu_descriptor=None,menu_output=None,prepared=None,activation=None):
    started=time.monotonic()
    native=C.CDLL(str(library));native.nxs_scroller_create.argtypes=[C.c_int,Changed,Pump,C.c_void_p];native.nxs_scroller_create.restype=C.c_void_p
    native.nxs_scroller_width.argtypes=[];native.nxs_scroller_width.restype=C.c_double
    native.nxs_scroller_sync.argtypes=[C.c_void_p]+[C.c_double]*7+[C.c_int]
    native.nxs_scroller_part.argtypes=[C.c_void_p,C.c_int];native.nxs_scroller_part.restype=Rect
    native.nxs_scroller_draw.argtypes=[C.c_void_p,C.c_double];native.nxs_scroller_draw.restype=Bitmap
    native.nxs_scroller_destroy.argtypes=[C.c_void_p]
    native.nxs_scroller_tracking.argtypes=[C.c_void_p];native.nxs_scroller_tracking.restype=C.c_int
    native.nxs_scroller_track.argtypes=[C.c_void_p,C.c_double,C.c_double,C.c_uint]
    native.nxs_scroller_send.argtypes=[C.c_void_p,C.c_int,C.c_double,C.c_double,C.c_uint]
    server=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
    server.setblocking(False)
    clients=[];controls={};contexts={};pending=[];active=None;forms=None;sources={};menu_broker=None;menu_sources=set()
    native_dispatch_depth=0;deferred_keys=set()
    def add_source(connection):
        if forms and forms.source_capabilities:
            source=native.nxs_native_ui_source_create(connection if isinstance(connection,int) else connection.fileno())
            if not source:raise RuntimeError('Cannot register embedding descriptor with native loop')
            sources[connection]=source
    def remove_source(connection):
        source=sources.pop(connection,None)
        if source:assert native.nxs_native_ui_source_destroy(source)
    context_ids=itertools.count(1)
    def log(event,**data):print(json.dumps(dict(event=event,**data)),flush=True)
    @Changed
    def changed(context,value):
        state=contexts[context];state['value']=value
        log('native-action',process=state['key'][0],control=state['key'][1],value=value)
    @Pump
    def pump(context):reentrant_dispatch(0)
    def response(client,req,state,pixels=False,scroller_width=0):
        result=Response();result.magic=req.magic;result.reserved=req.reserved
        result.parts[0].width=scroller_width
        if req.operation==7:
            result.parts[0].height=bool(forms)
            if forms:
                result.parts[0].x=forms.wheel_capabilities
                result.parts[4].width=forms.input_capabilities
                result.parts[4].height=forms.event_capabilities
                result.parts[5].width=forms.range_capabilities
                result.parts[5].x=forms.pointer_capabilities
                result.parts[6].width=forms.popup_capabilities
                result.parts[6].height=forms.popup_open_capabilities
                result.parts[6].x=forms.notification_capabilities
                result.parts[6].y=forms.text_capabilities
                result.parts[5].y=forms.command_capabilities
                result.parts[5].height=forms.menus.capabilities
                for part,kind in ((1,2),(2,3),(3,1)):
                    result.parts[part].width,result.parts[part].height=forms.preferred(kind)
        if state and state.get('native'):
            for part in range(1,7):result.parts[part]=native.nxs_scroller_part(state['native'],part)
            result.parts[0].x=state['value'];result.parts[0].y=bool(state.get('starting') or native.nxs_scroller_tracking(state['native']))
        data=b''
        if pixels:
            bitmap=native.nxs_scroller_draw(state['native'],1)
            result.width=bitmap.width;result.height=bitmap.height;result.stride=bitmap.stride
            data=C.string_at(bitmap.pixels,bitmap.stride*bitmap.height)
        if forms:forms.send(client,result,data)
        else:send_response(client,result,data)
    def emit_response(client,result,data=b''):
        if activation and not activation.before_reply(client,result):return
        send_response(client,result,data)
    def message(client,data,descriptors,sender_pid):
        if len(data)>=4 and int.from_bytes(data[:4],'little')==CONTROL_MAGIC:
            if forms:
                if (native_dispatch_depth and len(data)>=C.sizeof(ControlInputRequest) and int.from_bytes(data[4:8],'little')==8 and not descriptors
                        and client not in deferred_keys and len(deferred_keys)<128
                        and (forms.menus.busy() or menu_broker and menu_broker.busy())):
                    # NSMenu is validating/tracking on the native stack. A
                    # temporary refusal is not an unhandled application key.
                    # Preserve the original packet/sequence, then revalidate
                    # its lifetime and focus after that native call returns.
                    deferred_keys.add(client)
                    deadline=time.monotonic()+1
                    def later():
                        deferred_keys.discard(client)
                        if client in clients:
                            if time.monotonic()>=deadline:
                                # Never apply an input after the caller's
                                # bounded RPC wait could have fallen back.
                                forms._respond(client,ControlInputRequest.from_buffer_copy(data))
                                log('native-key-expired')
                            else:message(client,data,(),sender_pid)
                    pending.append(later);log('native-key-deferred')
                    return
                previous=activation.pending if activation else None
                if activation:
                    operation=int.from_bytes(data[4:8],'little')
                    activation.pending=(client,int.from_bytes(data[8:12],'little')) if operation in (15,16,19,20,23,24) else None
                try:forms.message(client,data,descriptors,sender_pid)
                finally:
                    if activation:activation.pending=previous
            return
        if descriptors:return
        if len(data)!=C.sizeof(Request):return
        req=Request.from_buffer_copy(data)
        if req.magic!=0x4e585343:return
        if req.operation==7:
            response(client,req,None,scroller_width=native.nxs_scroller_width())
            return
        key=(req.process,req.control,req.horizontal);state=controls.get(key)
        if req.operation==1:
            if req.layer>1 or not 1<=req.length<=8192:return
            if state is None:
                context=next(context_ids);state=dict(key=key,context=context,value=req.value,client=client,destroy=False);contexts[context]=state
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
            if req.operation==2 and not pending and active is None and (not forms or forms.active is None):
                state['starting']=True;pending.append(lambda: track_scroller(state,req.length,req.total,int(req.page)))
                log('native-press',process=req.process,control=req.control,x=req.length,y=req.total,modifiers=int(req.page))
            elif req.operation in (3,4) and native.nxs_scroller_tracking(state['native']):
                native.nxs_scroller_send(state['native'],0 if req.operation==3 else 1,req.length,req.total,int(req.page))
            elif req.operation==6:
                state['destroy']=True
                if native.nxs_scroller_tracking(state['native']):native.nxs_scroller_send(state['native'],1,0,0,0)
            response(client,req,state)
        else:response(client,req,None)
    def dispatch(timeout,native_events=True):
        nonlocal menu_sources
        if pending:timeout=0
        readers,writers,menu_delay=set(),set(),None
        if menu_broker:
            menu_broker.pump();readers,writers,menu_delay=menu_broker.poll()
            for descriptor in menu_sources-readers:remove_source(descriptor)
            for descriptor in readers-menu_sources:add_source(descriptor)
            menu_sources=readers
        maximum=60 if timeout is None and sources else 0
        if menu_delay is not None:maximum=min(maximum,menu_delay)
        if writers:maximum=0
        native_wait=forms.dispatch_events(maximum) if forms and native_events else -1
        if sources:timeout=0
        if native_wait>=0:
            timeout=native_wait if timeout is None else min(timeout,native_wait)
        if menu_delay is not None:timeout=menu_delay if timeout is None else min(timeout,menu_delay)
        readable=([server] if server else [])+([] if activation and activation.restoring else clients)+list(readers)+(forms.notification_fds()+forms.text_filter_fds() if forms else [])
        if activation:readable.insert(0,activation.channel)
        ready,writable,_=select.select(readable,list(writers),[],timeout)
        if writable:menu_broker.pump()
        for client in ready:
            if activation and client is activation.channel:
                activation.receive();continue
            if isinstance(client,int):
                if client in readers:menu_broker.ready(client)
                elif client in forms.text_filter_fds():forms.text_filter_ready(client)
                else:forms.owner_exited(client)
                continue
            if client is server:
                try:connection,_=server.accept()
                except BlockingIOError:continue
                connection.setblocking(True)
                if forms and forms.notification_capabilities:connection.setsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED,1)
                clients.append(connection);add_source(connection);continue
            if client not in clients:continue
            try:
                # Drawing or a validator can pump this dispatcher recursively.
                # A nested pass may consume a packet from this ready snapshot.
                data,ancillary,flags,_=client.recvmsg(128*1024,socket.CMSG_SPACE(4*4)+socket.CMSG_SPACE(12),socket.MSG_CMSG_CLOEXEC|socket.MSG_DONTWAIT)
                descriptors=[];sender_pid=None
                for level,kind,payload in ancillary:
                    if level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS:
                        values=array.array('i');values.frombytes(payload[:len(payload)//values.itemsize*values.itemsize]);descriptors.extend(values)
                    elif level==socket.SOL_SOCKET and kind==socket.SCM_CREDENTIALS and len(payload)>=12:
                        sender_pid=struct.unpack('3i',payload[:12])[0]
                try:
                    if data and not flags&(socket.MSG_TRUNC|socket.MSG_CTRUNC):message(client,data,descriptors,sender_pid)
                finally:
                    for descriptor in descriptors:os.close(descriptor)
                if data:continue
            except BlockingIOError:continue
            except (BrokenPipeError,ConnectionResetError):pass
            for state in controls.values():
                if state['client'] is client:
                    state['destroy']=True
                    if native.nxs_scroller_tracking(state['native']):native.nxs_scroller_send(state['native'],1,0,0,0)
            if forms:forms.disconnect(client)
            if activation:activation.forget(client)
            clients.remove(client);remove_source(client);client.close()
        if activation:activation.synchronize()
    def reentrant_dispatch(timeout,native_events=True):
        nonlocal native_dispatch_depth
        native_dispatch_depth+=1
        try:dispatch(timeout,native_events)
        finally:native_dispatch_depth-=1
    def track_scroller(state,x,y,modifiers):
        nonlocal active
        state['starting']=False
        if state['destroy']:return
        active=state
        try:native.nxs_scroller_track(state['native'],x,y,modifiers)
        finally:active=None
        log('native-release',process=state['key'][0],control=state['key'][1],value=state['value'])
    if hasattr(native,'nxs_control_create'):
        forms=NativeControlServer(native,Bitmap,Response,Pump,reentrant_dispatch,pending,emit_response,
                                  lambda: not pending and active is None and forms.active is None,log)
        forms.prepare()
    if menu_descriptor is not None:
        if not forms or not forms.notification_capabilities:raise RuntimeError('Shared menus require authenticated native owner notifications')
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'DBusMenus'))
        from broker import MenuBroker
        menu_broker=MenuBroker(native,menu_descriptor,menu_output or path.parent/'menus',reentrant_dispatch,log,models=forms.menus)
        forms.input_owner=menu_broker.allows_input
        if menu_broker.key_capabilities:
            forms.menus.application_key=menu_broker.key;forms.menus.capabilities|=2
        signal.signal(signal.SIGUSR1,lambda *unused:menu_broker.current and menu_broker.current['binding'].dump_states())
    for horizontal in (0,1):
        pointer=native.nxs_scroller_create(horizontal,Changed(),Pump(),None)
        if not pointer:raise RuntimeError('Native scroller preparation failed')
        try:
            native.nxs_scroller_sync(pointer,128,0,100,20,1,20,0,1)
            if not native.nxs_scroller_draw(pointer,1).pixels:raise RuntimeError('Native scroller drawing failed')
        finally:native.nxs_scroller_destroy(pointer)
    if prepared:prepared(native)
    if activation:
        server.close();server=None
        def adopt(connection):clients.append(connection);add_source(connection)
        activation.start(forms,adopt);add_source(activation.channel)
    else:
        server.bind(str(path));os.chmod(path,0o600);server.listen(20)
        add_source(server)
    log('ready',socket=str(path),request_size=C.sizeof(Request),response_size=C.sizeof(Response),preparation_seconds=time.monotonic()-started)
    try:
        while True:
            dispatch(None)
            while pending:
                pending.pop(0)()
            for key,state in list(controls.items()):
                if state['destroy'] and not native.nxs_scroller_tracking(state['native']):
                    native.nxs_scroller_destroy(state['native']);state['native']=None;del controls[key];del contexts[state['context']]
            if forms:forms.cleanup()
            if menu_broker:menu_broker.tick()
    finally:
        # Record the original failure before closing the private roles. A
        # supervisor reacting to EOF must not obscure its diagnostic cause.
        import traceback
        exception_type,_,exception_trace=sys.exc_info()
        log('transport-stopping',exception=exception_type.__name__ if exception_type else None,
            frames=[dict(file=frame.filename,line=frame.lineno,function=frame.name) for frame in traceback.extract_tb(exception_trace)])
        for connection in list(sources):remove_source(connection)
        if menu_broker:menu_broker.close()
        if forms:forms.close()
        for state in controls.values():native.nxs_scroller_destroy(state['native'])
        for client in clients:client.close()
        if server:server.close();path.unlink(missing_ok=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--library',type=Path,required=True);p.add_argument('--socket',type=Path,required=True)
    p.add_argument('--dbus-menu-fd',type=int);p.add_argument('--dbus-menu-output',type=Path)
    args,remaining=p.parse_known_args();run(args.library,args.socket,args.dbus_menu_fd,args.dbus_menu_output)
