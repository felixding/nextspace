#!/usr/bin/env python3
"""Check handoff ownership/lifetime with real pidfds and a native-call spy."""
import argparse
import json
import os
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
    finally:
        broker.close()
        if child and child.poll() is None:child.terminate();child.wait()
        output.write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps(dict(passed=len(rows))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path)
    run(p.parse_args().output)
