#!/usr/bin/env python3
"""Exercise the real UI provider through the helper's generic-control transport."""
import argparse
import array
import ctypes as C
import json
import os
from pathlib import Path
import socket
import time
from helper import Response
from native_controls import ControlRequest, MAGIC

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--socket', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
connection = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
connection.settimeout(3)
connection.connect(str(args.socket))
sequence = 0

def request(kind, operation, **values):
    global sequence
    sequence += 1
    title = values.pop('title', b'')
    req = ControlRequest(magic=MAGIC, operation=operation, process=0x54455354, kind=kind,
                         control=0x1000 + kind, text_size=len(title), reserved=sequence,
                         width=128, height=24, minimum=0, maximum=100, value=50, enabled=1)
    for name, value in values.items():
        setattr(req, name, value)
    connection.sendmsg([bytes(req), title])
    packet, ancillary, flags, _ = connection.recvmsg(1024 * 1024, socket.CMSG_SPACE(16))
    response = Response.from_buffer_copy(packet)
    for level, kind, data in ancillary:
        if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
            descriptors = array.array('i'); descriptors.frombytes(data)
            try:
                pixels = bytearray()
                while len(pixels) < response.size - C.sizeof(response):
                    chunk = os.pread(descriptors[0], response.size - C.sizeof(response) - len(pixels), len(pixels))
                    assert chunk
                    pixels.extend(chunk)
                packet += pixels
            finally:
                for descriptor in descriptors:os.close(descriptor)
    assert response.magic == MAGIC and response.size == len(packet) and response.reserved == sequence
    return response, packet[C.sizeof(Response):]

results = []
try:
    for kind in (1, 2, 3):
        response, pixels = request(kind, 1, title=b'Native control')
        assert (response.width, response.height, response.stride) == (128, 24, 512)
        assert len(pixels) == 128 * 24 * 4
        (args.output / f'kind-{kind}.argb').write_bytes(pixels)
        before = response.parts[0].width
        request(kind, 2, x=64, y=12)
        request(kind, 4, x=64, y=12)
        deadline = time.monotonic() + 2
        while True:
            response, _ = request(kind, 5)
            if not response.parts[0].y:
                break
            assert time.monotonic() < deadline, 'Native tracking did not release'
        assert response.parts[0].width == before + 1
        if kind in (2, 3):
            assert response.parts[0].height == 1
        request(kind, 1, title=b'Native control', state=0)
        request(kind, 2, x=64, y=12)
        request(kind, 3, x=180, y=80)
        request(kind, 4, x=180, y=80)
        deadline = time.monotonic() + 2
        while True:
            response, _ = request(kind, 5)
            if not response.parts[0].y:
                break
            assert time.monotonic() < deadline
        assert response.parts[0].width == before + 1, 'Cancelled native gesture activated'
        request(kind, 1, title=b'Native control', enabled=0)
        request(kind, 2, x=64, y=12)
        request(kind, 4, x=64, y=12)
        response, _ = request(kind, 5)
        assert response.parts[0].width == before + 1
        results.append(dict(kind=kind, actions=response.parts[0].width, cancelled_actions=0, disabled_actions=0))
        if kind==1:
            large,pixels=request(kind,1,width=640,height=64,title=b'Native control')
            assert len(pixels)==640*64*4
        request(kind, 6)
finally:
    connection.close()
(args.output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results))
