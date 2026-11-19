#!/usr/bin/env python3
"""Return one failed native layout measurement in an owned browser fixture."""
import argparse
import json
from pathlib import Path
import socket
import struct
import sys

source=Path(__file__).resolve().parents[2]/'Experiments/ChromiumScrollers'
sys.path.insert(0,str(source))
import helper

original=helper.send_response
failed=False

def send_response(client,response,data=b''):
    global failed
    # The adapter requests its original 128x128 native scroll-view layout.
    if (not failed and response.magic==0x4e585343 and not data and
            0<response.parts[0].width<128 and 0<response.parts[0].height<=128 and
            response.width==0 and response.height==0 and
            all(bytes(part)==bytes(helper.Rect()) for part in response.parts[1:])):
        failed=True
        pid,uid,gid=struct.unpack('3i',client.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        print(json.dumps(dict(event='test-bootstrap-scroller-layout-failed',pid=pid,
                             sequence=response.reserved)),flush=True)
        response.parts[0]=helper.Rect()
    return original(client,response,data)

helper.send_response=send_response
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--library',required=True,type=Path)
parser.add_argument('--socket',required=True,type=Path)
parser.add_argument('--dbus-menu-fd',type=int)
parser.add_argument('--dbus-menu-output',type=Path)
args,remaining=parser.parse_known_args()
helper.run(args.library,args.socket,args.dbus_menu_fd,args.dbus_menu_output)
