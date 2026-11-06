#!/usr/bin/env python3
"""Verify native invalidation descriptor readiness, isolation and lifetime."""
import argparse,array,ctypes as C,fcntl,json,os,select,socket,time,signal
from pathlib import Path
from helper import Response
from native_controls import ControlRequest,ControlInputRequest,MAGIC
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--socket',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--helper-pid',type=int,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
connection=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET);connection.settimeout(3);connection.connect(str(a.socket))
process=0x4e4f5441;other=process+1;sequence=0;results=[]
descriptors=[os.eventfd(0,os.EFD_NONBLOCK|os.EFD_CLOEXEC) for _ in range(3)]
def check(case,condition,**data):
    results.append(dict(case=case,passed=bool(condition),**data));(a.output/'results.json').write_text(json.dumps(results,indent=2)+'\n');assert condition,results[-1]
def exchange(req,descriptor=None,payload=b'',client=connection):
    global sequence
    sequence+=1;req.reserved=sequence
    rights=[] if descriptor is None else [(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[descriptor]))]
    client.sendmsg([bytes(req),payload],rights);data=client.recv(65536);response=Response.from_buffer_copy(data)
    assert response.magic==MAGIC and response.reserved==sequence and response.size==len(data)
    return response
def request(operation,owner=process,kind=1,control=1,descriptor=None,client=connection,**values):
    req=ControlRequest(magic=MAGIC,operation=operation,process=owner,kind=kind,control=control,
        width=128,height=24,maximum=100,value=50,enabled=1)
    for name,value in values.items():setattr(req,name,value)
    return exchange(req,descriptor,client=client)
def register(descriptor,owner=process,generation=None,client=connection):
    if generation is None:generation=request(9,owner=owner).parts[4].x
    return request(15,owner=owner,kind=0,control=0,descriptor=descriptor,value=generation,client=client).parts[3].x==1
def unregister(owner=process):return request(16,owner=owner,kind=0,control=0).parts[3].x==1
def key():
    req=ControlInputRequest(magic=MAGIC,operation=8,process=process,kind=1,control=1,text_size=1,unmodified_size=1)
    return exchange(req,payload=b'  ')
def ready(descriptor,timeout=0):return bool(select.select([descriptor],[],[],timeout)[0])
def drain(descriptor):
    try:return os.eventfd_read(descriptor)
    except BlockingIOError:return 0
def eventfd_identity(path):
    info=dict(line.split(':',1) for line in path.read_text().splitlines() if ':' in line)
    return int(info['eventfd-id']) if 'eventfd-id' in info else None
identities=[eventfd_identity(Path('/proc/self/fdinfo')/str(fd)) for fd in descriptors]
def helper_identities():
    found=set()
    for path in Path('/proc/'+str(a.helper_pid)+'/fdinfo').iterdir():
        try:found.add(eventfd_identity(path))
        except FileNotFoundError:pass
    return found
try:
    # Queue registration as the very first packet, without a warm-up RPC.
    # Sender credentials must survive packets sent before the server accepts.
    for trial in range(128):
        peer=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET);peer.settimeout(3)
        peer.connect(str(a.socket));descriptor=os.eventfd(0,os.EFD_NONBLOCK|os.EFD_CLOEXEC)
        try:
            owner=0x52454700+trial
            assert register(descriptor,owner,generation=0,client=peer), ('first-packet-registration',trial)
            assert request(16,owner=owner,kind=0,control=0,client=peer).parts[3].x==1
        finally:os.close(descriptor);peer.close()
    check('fresh-connection-first-packet-credentials',True,connections=128)
    request(1);request(1,owner=other)
    focus=ControlInputRequest(magic=MAGIC,operation=7,process=process,kind=1,control=1,focused=1)
    assert exchange(focus).parts[3].y==1
    check('register-separate-process-descriptors',register(descriptors[0]) and register(descriptors[1],other))
    drain(descriptors[0]);drain(descriptors[1])
    check('idle-descriptors-not-readable',not ready(descriptors[0],.05) and not ready(descriptors[1]))
    before=request(9).parts[4].x;response=key()
    check('native-action-wakes-owner',response.parts[0].width==1 and ready(descriptors[0],1) and not ready(descriptors[1]))
    drain(descriptors[0]);check('generation-follows-native-action',request(9).parts[4].x>before)
    key();key();check('invalidations-coalesce',ready(descriptors[0],1) and drain(descriptors[0])>=2)
    null=os.open('/dev/null',os.O_WRONLY)
    try:check('reject-file-descriptor',not register(null))
    finally:os.close(null)
    blocking=os.eventfd(0,os.EFD_CLOEXEC)
    try:check('reject-blocking-counter-without-changing-flags',not register(blocking) and not fcntl.fcntl(blocking,fcntl.F_GETFL)&os.O_NONBLOCK)
    finally:os.close(blocking)
    semaphore=os.eventfd(0,os.EFD_CLOEXEC|os.EFD_NONBLOCK|os.EFD_SEMAPHORE)
    try:check('reject-semaphore-counter',not register(semaphore))
    finally:os.close(semaphore)
    key();check('bad-registration-retains-original',ready(descriptors[0],1));drain(descriptors[0])
    check('reject-cross-process-shared-counter',not register(descriptors[0],other))
    key();check('process-isolation-after-rejection',ready(descriptors[0],1) and not ready(descriptors[1]));drain(descriptors[0])
    check('unregister-preserves-caller-descriptor',unregister() and fcntl.fcntl(descriptors[0],fcntl.F_GETFD)>=0)
    key();check('unregistered-no-notification',not ready(descriptors[0],.05))
    check('registration-catches-missed-generation',register(descriptors[0],generation=0) and ready(descriptors[0],1));drain(descriptors[0])
    os.eventfd_write(descriptors[0],2**64-2);key()
    check('saturated-counter-never-blocks',drain(descriptors[0])==2**64-2)
    key();check('counter-usable-after-drain',ready(descriptors[0],1));drain(descriptors[0])
    check('replace-registration',register(descriptors[2]))
    check('replacement-closes-old-helper-reference',identities[0] not in helper_identities())
    key();check('replacement-is-exclusive',ready(descriptors[2],1) and not ready(descriptors[0]));drain(descriptors[2])
    # No client message arrives during this wait. An actual native timer must
    # invalidate the progress view and make the registered descriptor readable.
    request(1,kind=5,control=2,indeterminate=1)
    before=request(1,kind=5,control=2,indeterminate=1).parts[4].x;drain(descriptors[2]);start=time.monotonic()
    awakened=ready(descriptors[2],2);elapsed=time.monotonic()-start
    check('native-timer-wakes-without-polling',awakened and request(9).parts[4].x>before,seconds=elapsed)
    request(6,kind=5,control=2)
    check('unregister-idempotent',unregister() and unregister())
    check('other-process-still-registered',unregister(other) and fcntl.fcntl(descriptors[1],fcntl.F_GETFD)>=0)
    check('unregister-closes-helper-references',not set(identities)&helper_identities())
    peer=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET);peer.settimeout(3);peer.connect(str(a.socket))
    try:
        assert register(descriptors[0],owner=process+2,generation=0,client=peer)
        assert identities[0] in helper_identities()
    finally:peer.close()
    deadline=time.monotonic()+3
    while identities[0] in helper_identities():
        assert time.monotonic()<deadline,'Notifier leaked after disconnect'
        time.sleep(.01)
    check('disconnect-closes-only-helper-reference',fcntl.fcntl(descriptors[0],fcntl.F_GETFD)>=0)
    # A renderer can die while its inherited request connection is still held
    # by its parent. Killing this owned child reproduces that exact lifetime.
    reader,writer=os.pipe();child=os.fork()
    if child==0:
        os.close(reader)
        try:
            request(1,owner=process+3,kind=5,control=3,indeterminate=1)
            accepted=register(descriptors[0],owner=process+3)
            os.write(writer,b'1' if accepted else b'0')
            while True:signal.pause()
        finally:os._exit(1)
    os.close(writer)
    try:
        assert select.select([reader],[],[],5)[0] and os.read(reader,1)==b'1'
        assert identities[0] in helper_identities()
    finally:
        os.close(reader);os.kill(child,signal.SIGKILL);os.waitpid(child,0)
    deadline=time.monotonic()+3
    while identities[0] in helper_identities():
        assert time.monotonic()<deadline,'Notifier leaked after owner crash'
        time.sleep(.01)
    check('owner-crash-releases-notifier-with-shared-connection-alive',request(9).magic==MAGIC)
    check('owner-crash-destroys-its-native-control',request(5,owner=process+3,kind=5,control=3).parts[1].width==0)
finally:
    connection.close()
    for descriptor in descriptors:os.close(descriptor)
print(json.dumps(dict(passed=len(results),results=results)))
