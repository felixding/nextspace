#!/usr/bin/env python3
"""Verify native timer invalidation through the existing helper transport."""
import argparse
import ctypes as C
import hashlib
import json
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
process = 0x414e494d
sequence = 0

def exchange(operation, indeterminate=1, owner=process):
    global sequence
    sequence += 1
    request = ControlRequest(magic=MAGIC, operation=operation, process=owner, kind=5,
        control=1, reserved=sequence, width=128, height=24, minimum=0, maximum=100,
        value=50, enabled=1, indeterminate=indeterminate)
    connection.send(bytes(request))
    data = connection.recv(65536)
    result = Response.from_buffer_copy(data)
    assert result.magic == MAGIC and result.reserved == sequence and result.size == len(data)
    assert result.parts[4].width == 1
    return result, data[C.sizeof(Response):]

try:
    response, pixels = exchange(1)
    assert len(pixels) == 128*24*4 and response.parts[0].width == 0
    generation = response.parts[4].x
    # No paint/poll messages arrive while this sleeps. The helper must wake on
    # the native library's deadline and observe its actual repaint flag.
    time.sleep(.25)
    response, _ = exchange(9)
    assert response.parts[4].x > generation
    assert exchange(9, owner=process+1)[0].parts[4].x == 0
    hashes, deadlines, generations = [], [], []
    deadline = time.monotonic()+5
    while len(hashes)<12 and time.monotonic()<deadline:
        response, _ = exchange(9)
        current = response.parts[4].x
        if not generations or current > generations[-1]:
            response, pixels = exchange(1)
            assert len(pixels)==128*24*4 and response.parts[0].width==0
            generations.append(current)
            hashes.append(hashlib.sha256(pixels).hexdigest())
            (args.output/f'frame-{len(hashes):02d}.argb').write_bytes(pixels)
        wait = response.parts[4].y
        deadlines.append(wait)
        time.sleep(min(.1,max(.001,wait+.003)))
    assert len(hashes)==12 and len(set(hashes))>=2
    response, stable = exchange(1, indeterminate=0)
    generation = response.parts[4].x
    time.sleep(.3)
    assert exchange(9)[0].parts[4].x == generation
    assert exchange(1, indeterminate=0)[1] == stable
    response, _ = exchange(1)
    time.sleep(.2)
    assert exchange(9)[0].parts[4].x > response.parts[4].x
    response, _ = exchange(6)
    generation = response.parts[4].x
    time.sleep(.2)
    assert exchange(9)[0].parts[4].x == generation
    result = dict(frames=12, unique_native_images=len(set(hashes)), idle_native_wakeup=True,
        process_isolation=True, stopped_stable=True, restart=True, destroy_stops_invalidation=True,
        native_actions=0, generations=generations, native_next_delays=deadlines)
finally:
    connection.close()
(args.output/'results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
