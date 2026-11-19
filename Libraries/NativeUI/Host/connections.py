"""Restore session-owned connections and subscriptions, never controls or edits."""
import array
import itertools
import os
from pathlib import Path
import select
import socket
import struct

MAGIC=0x4e584146
PREPARED,CLIENT,OWNER,REMOVE,EPOCH,READY,STOP=range(1,8)
NOTIFY,FILTER,COMMANDS,MENUS=1,2,4,8
PACKET=struct.Struct('=IIQIiII')


class HostConnections:
    def __init__(self,descriptor):
        self.channel=socket.socket(fileno=os.dup(descriptor))
        self.channel.settimeout(2)
        self.clients={};self.snapshots={};self.restoring=True;self.pending=None
        self.epoch=0

    def send(self,operation,client=0,process=0,pid=0,flags=0,descriptors=()):
        payload=PACKET.pack(MAGIC,operation,client,process,pid,flags,self.epoch)
        ancillary=[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',descriptors))] if descriptors else []
        if self.channel.sendmsg([payload],ancillary)!=len(payload):raise RuntimeError('Incomplete native activation packet')

    def start(self,forms,add_client):
        self.forms=forms;self.add_client=add_client
        self.send(PREPARED)

    def forget(self,client):
        for identity,connection in list(self.clients.items()):
            if connection is client:
                del self.clients[identity]
                for key in list(self.snapshots):
                    if key[0]==identity:del self.snapshots[key]

    def snapshot(self,identity,process):
        connection=self.clients[identity];owner=self.forms.notifiers.get(process)
        if not owner or owner['client'] is not connection:
            if self.snapshots.pop((identity,process),None) is not None:self.send(REMOVE,identity,process)
            return
        entry=self.forms.text_filters.get(process)
        endpoint=entry.get('socket') if entry else None
        flags=NOTIFY|(FILTER if endpoint else 0)
        if endpoint:flags|=(COMMANDS if entry.get('commands') else 0)|(MENUS if entry.get('menus') else 0)
        signature=(owner['identity'],owner['descriptor'],owner['lifetime'],id(entry),flags,endpoint.fileno() if endpoint else -1)
        if self.snapshots.get((identity,process))==signature:return
        descriptors=[owner['descriptor'],owner['lifetime']]
        if endpoint:descriptors.append(endpoint.fileno())
        self.send(OWNER,identity,process,owner['pid'],flags,descriptors)
        self.snapshots[(identity,process)]=signature

    def synchronize(self):
        if self.restoring:return
        for identity,connection in list(self.clients.items()):
            processes={p for p,e in self.forms.notifiers.items() if e['client'] is connection}
            processes.update(p for c,p in self.snapshots if c==identity)
            for process in processes:self.snapshot(identity,process)

    def before_reply(self,client,response):
        if self.restoring:return False
        pending=self.pending
        if pending and pending[0] is client and response.parts[3].x==1:
            identity=next((identity for identity,connection in self.clients.items() if connection is client),None)
            if identity is not None:self.snapshot(identity,pending[1])
        return True

    def receive(self):
        data,ancillary,flags,_=self.channel.recvmsg(PACKET.size,socket.CMSG_SPACE(8*4),socket.MSG_CMSG_CLOEXEC)
        descriptors=[]
        try:
            for level,kind,payload in ancillary:
                if level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS:
                    values=array.array('i');values.frombytes(payload[:len(payload)//values.itemsize*values.itemsize]);descriptors.extend(values)
            if len(data)!=PACKET.size or flags&(socket.MSG_TRUNC|socket.MSG_CTRUNC):raise RuntimeError('Invalid native activation envelope')
            magic,operation,identity,process,pid,bits,epoch=PACKET.unpack(data)
            if magic!=MAGIC or not epoch or (self.epoch and epoch!=self.epoch):raise RuntimeError('Invalid native activation generation')
            self.epoch=epoch
            if operation==STOP and not descriptors:raise SystemExit(0)
            elif operation==CLIENT and len(descriptors)==1 and identity not in self.clients:
                connection=socket.socket(fileno=os.dup(descriptors[0]))
                if connection.family!=socket.AF_UNIX or connection.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)!=socket.SOCK_SEQPACKET:
                    connection.close();raise RuntimeError('Invalid activated client socket')
                connection.getpeername();connection.setblocking(True)
                connection.setsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED,1)
                self.clients[identity]=connection;self.add_client(connection)
            elif operation==OWNER and self.restoring and identity in self.clients and bits&NOTIFY and not bits&~15 and len(descriptors)==(3 if bits&FILTER else 2):
                self.restore(self.clients[identity],process,pid,bits,descriptors)
            elif operation==EPOCH and not descriptors and self.restoring:
                # Old decisions must be older than every callback in this
                # generation, even if an owner sends one after restoration.
                self.forms.host_epoch=epoch
                self.forms.edit_serial=itertools.count((epoch<<32)+1)
                for entry in self.forms.text_filters.values():entry['serial']=epoch<<32
                self.restoring=False
                self.synchronize()
                for process in self.forms.notifiers:
                    self.forms.generations[process]=epoch<<32;self.forms.signal(process)
                self.send(READY)
            else:raise RuntimeError('Unsupported native activation packet')
        finally:
            for descriptor in descriptors:os.close(descriptor)

    def restore(self,connection,process,pid,flags,descriptors):
        from native_controls import ControlRequest,MAGIC as CONTROL_MAGIC
        if select.select([descriptors[1]],[],[],0)[0]:return
        info=dict(line.split(':',1) for line in Path('/proc/self/fdinfo/'+str(descriptors[1])).read_text().splitlines() if ':' in line)
        if int(info.get('Pid','-1'))!=pid:return
        request=ControlRequest(magic=CONTROL_MAGIC,operation=15,process=process)
        self.forms.notification_message(connection,request,descriptors[:1],pid)
        owner=self.forms.notifiers.get(process)
        if not owner or owner['client'] is not connection or owner['pid']!=pid:raise RuntimeError('Cannot restore native owner')
        if flags&FILTER:
            request.operation=19;self.forms.text_filter_message(connection,request,descriptors[2:],pid)
            if process not in self.forms.text_filters:raise RuntimeError('Cannot restore native callbacks')
            self.forms.text_filters[process]['serial']=self.epoch<<32
            for bit,operation in [(COMMANDS,23),(MENUS,24)]:
                if flags&bit:
                    request.operation=operation;request.state=1;self.forms.text_filter_message(connection,request,(),pid)
