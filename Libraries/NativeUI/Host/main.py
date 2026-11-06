#!/usr/bin/env python3
"""Session-owned transport host for the independent native UI library."""
import argparse
import fcntl
import os
from pathlib import Path
import signal
import socket
import stat
import struct
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',type=Path,required=True)
    parser.add_argument('-GSBackend',dest='backend',required=True)
    args=parser.parse_args()
    if os.environ.get('XDG_SESSION_CLASS')!='user':
        parser.error('A native UI host requires an authenticated user session')
    endpoint=Path(os.environ['NEXTSPACE_NATIVE_UI_SOCKET'])
    parent=endpoint.parent.stat()
    if (not endpoint.is_absolute() or not stat.S_ISDIR(parent.st_mode) or parent.st_uid!=os.getuid()
            or parent.st_mode&0o077):
        parser.error('The native UI endpoint requires a private user-owned directory')
    # Consume the inherited private role before starting AppKit or D-Bus.
    for descriptor in (3,4):
        fcntl.fcntl(descriptor,fcntl.F_SETFD,fcntl.fcntl(descriptor,fcntl.F_GETFD)|fcntl.FD_CLOEXEC)
        with socket.fromfd(descriptor,socket.AF_UNIX,socket.SOCK_SEQPACKET) as peer:
            if peer.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)!=socket.SOCK_SEQPACKET:
                parser.error('Native host roles must be Unix SEQPACKET sockets')
            pid,uid,gid=struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            if pid!=os.getppid() or uid!=os.getuid():
                parser.error('Native host roles must belong to this session supervisor')
    installed=Path(__file__).resolve().parent
    runtime=installed if (installed/'ChromiumScrollers/helper.py').exists() else installed.parents[2]/'Experiments'
    sys.path.insert(0,str(runtime/'ChromiumScrollers'))
    sys.path.insert(0,str(runtime/'DBusMenus'))
    from menu_service import WaylandMenuService
    from connections import HostConnections
    from helper import run
    def finish(*unused):raise SystemExit(0)
    signal.signal(signal.SIGTERM,finish)
    signal.signal(signal.SIGINT,finish)
    # The private bus advertises the actual Wayland menu consumer only while
    # its host is alive. X11 registration is explicitly unsupported.
    service=None
    def ready(native):
        nonlocal service
        if native.nxs_native_ui_menu_capabilities()&7!=7:
            raise RuntimeError('The session host requires native menu models, cancellation and lifecycle support')
        service=WaylandMenuService()
    try:run(args.library,endpoint,3,endpoint.parent/'menus',prepared=ready,activation=HostConnections(4))
    finally:
        if service:service.close()


if __name__=='__main__':main()
