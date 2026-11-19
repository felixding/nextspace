#!/usr/bin/env python3
"""Drop one real bootstrap capability reply; keep the native provider unchanged."""
import argparse
import json
from pathlib import Path
import socket
import struct
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Experiments/ChromiumScrollers'))
import helper

original=helper.send_response
withheld=False

def send_response(client,response,data=b''):
    global withheld
    if not withheld and response.magic==0x4e585343 and response.parts[4].width==3 and response.parts[6].x==1:
        withheld=True
        pid,uid,gid=struct.unpack('3i',client.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        print(json.dumps(dict(event='test-bootstrap-capability-reply-withheld',pid=pid,sequence=response.reserved)),flush=True)
        return
    return original(client,response,data)

helper.send_response=send_response
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--library',required=True,type=Path)
parser.add_argument('--socket',required=True,type=Path)
parser.add_argument('--dbus-menu-fd',type=int)
parser.add_argument('--dbus-menu-output',type=Path)
args,remaining=parser.parse_known_args()
helper.run(args.library,args.socket,args.dbus_menu_fd,args.dbus_menu_output)
