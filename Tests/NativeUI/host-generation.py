#!/usr/bin/env python3
"""A late-registering client learns the session epoch before native callbacks."""
import argparse
import ctypes as C
import json
from pathlib import Path
import socket
import sys

repo=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(repo/'Experiments/ChromiumScrollers'),str(repo/'Libraries/NativeUI/Host')]
from connections import HostConnections,PACKET,MAGIC,EPOCH,READY
from helper import Response
from native_controls import NativeControlServer,ControlRequest
from native_menus import NativeMenuServer

parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();checks=[]
def check(case,passed):
    checks.append(dict(case=case,passed=bool(passed)));assert passed,case

server=NativeControlServer.__new__(NativeControlServer)
server.generations={};server.host_epoch=0;server.notifiers={};server.text_filters={}
server.controls={};server.global_generations={};server.response_type=Response
server.event_deadline=-1
for name in ('input','event','range','popup','tab','popup_title','radio'):
    setattr(server,name+'_capabilities',0)
notified=[];server.signal=notified.append
local,supervisor=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
client,receiver=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
host=HostConnections(local.fileno())
try:
    host.start(server,lambda peer:None);supervisor.recv(PACKET.size)
    supervisor.send(PACKET.pack(MAGIC,EPOCH,0,0,0,0,7))
    host.receive()
    check('session-epoch-handshake-completes',PACKET.unpack(supervisor.recv(PACKET.size))[1]==READY)
    check('no-early-subscriber-required-for-epoch',not server.notifiers and not server.generations)
    def send(peer,response,payload=b''):
        response.size=C.sizeof(response)+len(payload);peer.send(bytes(response)+payload)
    server.send=send
    request=ControlRequest(process=901,kind=17,control=1)
    server._respond(client,request)
    first=Response.from_buffer_copy(receiver.recv(65536))
    check('first-control-reply-already-carries-host-epoch',int(first.parts[4].x)>>32==7)
    menus=NativeMenuServer.__new__(NativeMenuServer);menus.server=server
    menus.respond(client,request)
    reply=Response.from_buffer_copy(receiver.recv(65536))
    check('first-detached-menu-reply-carries-same-epoch',int(reply.parts[4].x)>>32==7)
    server.invalidate(901,fanout=False)
    server._respond(client,request)
    reply=Response.from_buffer_copy(receiver.recv(65536))
    check('first-invalidation-stays-within-original-epoch',reply.parts[4].x==first.parts[4].x+1)
    callback=next(server.edit_serial)
    check('first-native-callback-cannot-change-client-epoch',callback>>32==int(first.parts[4].x)>>32)
    request.process=902;server._respond(client,request)
    reply=Response.from_buffer_copy(receiver.recv(65536))
    check('subsequent-new-client-also-starts-in-current-epoch',int(reply.parts[4].x)>>32==7)
    check('invalidation-signals-the-correct-client',notified==[901])
finally:
    host.channel.close();local.close();supervisor.close();client.close();receiver.close()
    args.output.write_text(json.dumps(checks,indent=2)+'\n')
print(json.dumps(dict(passed=len(checks))))
