#!/usr/bin/env python3
"""Check handoff ownership/lifetime with real pidfds and a native-call spy."""
import argparse
import json
import os
import socket
import struct
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Libraries/NativeUI/Bridge'))
from auxiliary_activation import AuxiliaryActivation
from color_owners import ColorOwners


def run(output):
    rows=[];calls=[];visible=True;authorized=True
    def check(case,passed):
        rows.append(dict(case=case,passed=bool(passed)));assert passed,case
    native=SimpleNamespace(nxs_control_popup_state=lambda control:SimpleNamespace(visible=visible),
        nxs_control_auxiliary_activate=lambda control,token:calls.append((control,token)) or 1)
    source,receiver=object(),object()
    server=SimpleNamespace(auxiliary_capabilities=1,native=native,log=lambda *a,**k:None,
        owns_process=lambda client,process,pid:authorized and client is receiver and process==7,
        notifiers={7:dict(client=receiver,pid=os.getpid())})
    broker=AuxiliaryActivation(server,ColorOwners.ancestor)
    state=dict(key=(7,1,17),native=1,client=receiver,destroy=False)
    request=SimpleNamespace(process=1,kind=0,control=42,state=1,x=123,width=0,height=0,y=0,
        minimum=0,maximum=0,value=0,enabled=0,indeterminate=0,modifiers=0)
    child=None
    try:
        broker.publish(source,request,os.getpid(),b'first-token')
        broker.prune()
        check('periodic-pruning-preserves-live-unconsumed-token',len(broker.tokens)==1)
        broker.open(state,os.getpid())
        check('same-application-handoff-crosses-separate-connections',calls==[(1,b'first-token')])
        broker.open(state,os.getpid())
        check('consumed-token-cannot-be-replayed',len(calls)==1 and len(broker.pending)==1)
        visible=False;broker.prune();broker.publish(source,request,os.getpid(),b'late-token')
        check('late-token-cannot-activate-closed-popup',len(calls)==1 and not broker.pending)
        visible=True;broker.disconnect(source)
        child=subprocess.Popen(['sleep','30'])
        broker.publish(source,request,child.pid,b'other-family-token')
        broker.open(state,os.getpid())
        check('child-cannot-supply-parent-application-activation',len(calls)==1)
        broker.retire(state);child.terminate();child.wait();broker.prune();child=None
        check('exited-source-is-retired-by-real-pidfd',not broker.tokens)
        authorized=False;broker.publish(source,request,os.getpid(),b'unowned-token');broker.open(state,os.getpid())
        check('unowned-receiver-cannot-claim-token',len(calls)==1 and not broker.pending)
        authorized=True;broker.disconnect(source)
        broker.publish(source,request,os.getppid(),b'ancestor-token');broker.open(state,os.getpid())
        check('real-live-ancestor-may-delegate-to-child',len(calls)==2 and calls[-1]==(1,b'ancestor-token'))
        broker.publish(source,request,os.getpid(),b'one');broker.publish(object(),request,os.getppid(),b'two')
        broker.open(state,os.getpid())
        check('ambiguous-live-ancestors-are-rejected',len(calls)==2)
        state['destroy']=True;broker.prune()
        check('destroyed-popup-releases-pending-handoff',not broker.pending)
        broker.close()
        check('shutdown-releases-token-lifetimes',not broker.tokens)
        for payload in [b'',b'bad\0token',b'x'*4097]:broker.publish(source,request,os.getpid(),payload)
        check('malformed-publications-create-no-source',not broker.tokens)
        parents=[];order=[];server.auxiliary_capabilities=3;state['destroy']=False
        native.nxs_control_auxiliary_parent=lambda control,handle:parents.append((control,handle)) or order.append('parent') or 1
        native.nxs_control_auxiliary_activate=lambda control,token:order.append('activate') or 1
        request.state=2
        broker.publish(source,request,os.getpid(),b'parented-token\0original-export')
        broker.open(state,os.getpid())
        check('authenticated-source-supplies-original-parent',parents==[(1,b'original-export')])
        check('parent-is-associated-before-activation',order==['parent','activate'])
        for payload in [b'token',b'token\0',b'token\0owner\0extra',b'token\0'+b'x'*4097]:
            broker.publish(source,request,os.getpid(),payload)
        check('invalid-parent-payload-cannot-create-a-source',not broker.tokens)
        request.state=1;broker.publish(source,request,os.getpid(),b'unparented-token');broker.open(state,os.getpid())
        check('reuse-without-parent-clears-old-association',parents[-1]==(1,None))
        broker.publish(source,request,os.getpid(),b'superseded-token')
        request.state=0;request.x=0
        broker.publish(object(),request,os.getpid(),b'')
        check('other-connection-cannot-clear-source-grant',len(broker.tokens)==1)
        broker.publish(source,request,os.getpid(),b'')
        check('new-input-clears-previous-source-grant',not broker.tokens)
        prior=len(order);broker.open(state,os.getpid())
        check('popup-waits-for-current-input-token',len(order)==prior and bool(broker.pending))
        request.state=1;request.x=124
        broker.publish(source,request,os.getpid(),b'current-token')
        check('current-input-token-completes-handoff',len(order)==prior+2 and not broker.pending)
        broker.open(state,os.getpid());request.state=0;request.x=0
        broker.publish(source,request,os.getpid(),b'')
        check('new-input-retires-superseded-pending-handoff',not broker.pending)
        broker.close();order.clear();parents.clear()
        sources=[]
        native.nxs_native_ui_source_create=lambda fd:sources.append(fd) or fd+1
        native.nxs_native_ui_source_destroy=lambda handle:sources.remove(handle-1)
        request.state=3;request.control=0;request.text_size=0;request.value=0
        provider,remote=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
        provider.settimeout(1)
        try:
            broker.register(source,request,os.getpid(),[remote.fileno()])
            check('presentation-provider-is-bound-to-live-source',len(broker.providers)==1 and len(sources)==1)
            broker.open(state,os.getpid())
            check('provider-without-real-input-cannot-request-activation',not order and not broker.providers[(source,os.getpid())]['requested'])
            request.state=0;request.control=42
            broker.publish(source,request,os.getpid(),b'')
            broker.open(state,os.getpid());ticket=struct.unpack('<Q',provider.recv(8))[0]
            check('presentation-requests-a-fresh-toolkit-token',ticket>0 and not order)
            request.state=2;request.value=ticket
            broker.publish(object(),request,os.getpid(),b'foreign-token\0owner')
            check('another-connection-cannot-answer-presentation-request',not order and not broker.tokens)
            broker.publish(source,request,os.getpid(),b'fresh-token\0owner')
            check('fresh-request-completes-original-native-presentation',order==['parent','activate'] and not broker.pending)
            broker.publish(source,request,os.getpid(),b'replayed-token\0owner')
            check('presentation-reply-cannot-be-replayed',not broker.tokens and len(order)==2)
            broker.open(state,os.getpid());old=struct.unpack('<Q',provider.recv(8))[0]
            request.state=0;request.value=0
            broker.publish(source,request,os.getpid(),b'')
            request.state=2;request.value=old
            broker.publish(source,request,os.getpid(),b'superseded-token\0owner')
            check('new-input-rejects-inflight-old-token',not broker.tokens and not broker.pending and len(order)==2)
            broker.open(state,os.getpid());request.value=struct.unpack('<Q',provider.recv(8))[0]
            check('new-input-gets-a-distinct-presentation-ticket',request.value>old)
            visible=False
            broker.publish(source,request,os.getpid(),b'closed-token\0owner')
            check('late-request-reply-cannot-activate-closed-window',len(order)==2 and not broker.pending)
            visible=True
            broker.open(state,os.getpid());ticket=struct.unpack('<Q',provider.recv(8))[0]
            check('reopening-requests-fresh-token-instead-of-retained-grant',ticket>request.value and len(order)==2)
            request.value=ticket
            broker.publish(source,request,os.getpid(),b'current-token\0owner')
            check('reopening-uses-current-presentation-reply',len(order)==4 and not broker.pending)
            broker.disconnect(source)
            check('provider-disconnect-closes-source-and-lifetime',not broker.providers and not sources)
            request.state=3;request.control=0;request.value=0
            read,write=os.pipe()
            try:
                broker.register(source,request,os.getpid(),[read])
                check('non-socket-cannot-register-as-token-provider',not broker.providers and not sources)
            finally:os.close(read);os.close(write)
            stream,other=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
            try:
                broker.register(source,request,os.getpid(),[other.fileno()])
                check('stream-socket-cannot-replace-packet-contract',not broker.providers and not sources)
            finally:stream.close();other.close()
        finally:
            provider.close();remote.close()

    finally:
        broker.close()
        if child and child.poll() is None:child.terminate();child.wait()
        output.write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps(dict(passed=len(rows))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path)
    run(p.parse_args().output)
