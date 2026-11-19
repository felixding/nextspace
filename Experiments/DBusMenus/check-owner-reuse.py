#!/usr/bin/env python3
"""Repeated trusted owner snapshots retain an in-flight native menu binding."""
import argparse,importlib.util,json,os,socket,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ChromiumScrollers'))

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--broker',type=Path,default=Path(__file__).with_name('broker.py'))
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
spec=importlib.util.spec_from_file_location('owner_broker',a.broker)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
created=[];rows=[]
class Binding:
    def __init__(self,*args,**kw):self.alive=True;self.stops=0;created.append(self)
    def is_alive(self):return self.alive
    def stop(self):self.alive=False;self.stops+=1
    def close(self):self.stop();return True
    def tick(self):pass
module.MenuBinding=Binding
def check(case,passed):
    rows.append(dict(case=case,passed=bool(passed)))
    a.output.write_text(json.dumps(rows,indent=2)+'\n')
    assert passed,case
with tempfile.TemporaryDirectory(prefix='native-owner-reuse-') as temporary:
    control,peer=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
    broker=object.__new__(module.MenuBroker)
    broker.control=control;broker.native=None;broker.output=Path(temporary)
    broker.models=None;broker.current=None;broker.pending=module._UNCHANGED;broker.selected_pid=0
    broker.dispatch=lambda *args:None;broker.log=lambda *args,**kw:None
    request=dict(operation='bind',window=12,pid=os.getpid(),title='Original application',service=':1.8',path='/native/menu')
    def send(**updates):
        peer.send(json.dumps(dict(request,**updates)).encode());broker.receive()
        return json.loads(peer.recv(8192))
    try:
        check('initial-owner-accepted',send()['accepted'])
        original=broker.pending
        check('repeat-pending-owner-accepted',send()['accepted'])
        check('pending-menu-identity-retained',broker.pending is original and len(created)==1 and original['binding'].is_alive())
        broker.current=original;broker.pending=module._UNCHANGED
        # A lifecycle callback may pump any number of these same snapshots.
        for unused in range(12):check('repeat-current-owner-accepted-'+str(unused),send()['accepted'])
        check('current-menu-not-stopped-or-replaced',broker.current is original and broker.pending is module._UNCHANGED and original['binding'].stops==0 and len(created)==1)
        class Models:
            def __init__(self):self.selected=[];self.context_owners=[]
            def has_owner(self,pid):return False
            def select_owner(self,pid):self.selected.append(pid)
            def cancel_foreign_contexts(self,pid):self.context_owners.append(pid)
        models=Models();broker.models=models;broker.pump=lambda:None
        for unused in range(3):broker.tick()
        check('dbus-owner-retained-for-native-context-menus',models.selected==[os.getpid()]*3)
        check('dbus-menu-retained-with-context-menu-models',broker.current is original and original['binding'].is_alive())
        check('modal-owner-snapshot-accepted',send()['accepted'])
        check('modal-context-owner-updated-before-tick',models.context_owners==[os.getpid()])
        broker.models=None
        check('changed-address-accepted',send(path='/native/another')['accepted'])
        check('changed-address-replaces-original',broker.pending is not original and len(created)==2 and original['binding'].stops==1)
        changed=broker.pending
        check('repeat-new-pending-owner-accepted',send(path='/native/another')['accepted'])
        check('replacement-menu-identity-retained',broker.pending is changed and len(created)==2 and changed['binding'].is_alive())
        broker.models=models
        check('clear-owner-accepted',send(operation='clear')['accepted'])
        check('native-app-context-dismissal-before-tick',models.context_owners[-1]==0)
        check('clear-retires-pending-menu',broker.pending is None and not changed['binding'].is_alive() and broker.selected_pid==0)
        print(json.dumps(dict(complete=True,checks=len(rows))))
    finally:
        for item in [broker.current,broker.pending if broker.pending is not module._UNCHANGED else None]:
            if item:broker.dispose(item)
        control.close();peer.close()
