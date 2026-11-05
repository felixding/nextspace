#!/usr/bin/env python3
"""Exercise provider-owned focus and keys over the browser helper transport."""
import argparse
import ctypes as C
import json
from pathlib import Path
import socket
from helper import Response
from native_controls import ControlRequest, ControlInputRequest, MAGIC

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--socket', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
connection = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
connection.settimeout(3)
connection.connect(str(args.socket))
sequence = 0
assert C.sizeof(ControlInputRequest) == 56

def exchange(request, text=b'', unmodified=b''):
    global sequence
    sequence += 1
    request.reserved = sequence
    connection.sendmsg([bytes(request), text, unmodified])
    data = connection.recv(65536)
    result = Response.from_buffer_copy(data)
    assert result.magic == MAGIC and result.reserved == sequence and result.size == len(data)
    return result

def configure(kind, **values):
    request = ControlRequest(magic=MAGIC, operation=1, process=0x494e5054, kind=kind, control=kind,
                             width=128, height=24, minimum=0, maximum=100, value=50, enabled=1)
    for name, value in values.items():setattr(request, name, value)
    return exchange(request)

def input_request(kind, operation=8, text=b'', **values):
    request = ControlInputRequest(magic=MAGIC, operation=operation, process=0x494e5054,
                                  kind=kind, control=kind, text_size=len(text), unmodified_size=len(text))
    for name, value in values.items():setattr(request, name, value)
    return exchange(request, text, text)

results = []
try:
    for kind in (1, 2, 3, 4):
        response = configure(kind)
        assert int(response.parts[3].width) & 3 == 3
        response = input_request(kind, operation=7, focused=1)
        assert response.parts[3].x == response.parts[3].y == 1
        before = response.parts[0].width
        response = input_request(kind, key=7 if kind == 4 else 0, text=b'' if kind == 4 else b' ')
        assert response.parts[3].x == 1 and response.parts[0].width == before + 1
        if kind in (2, 3):assert response.parts[0].height == 1
        if kind == 4:assert 50 < response.parts[0].x <= 100
        response = input_request(kind, type=1, text=b' ')
        assert response.parts[0].width == before + 1
        assert input_request(kind, key=2).parts[3].x == 2
        assert input_request(kind, key=2, modifiers=1).parts[3].x == 3
        response = input_request(kind, text=b'x')
        assert response.parts[3].x == 0 and response.parts[0].width == before + 1
        response = input_request(kind, operation=7, focused=0)
        assert response.parts[3].x == 1 and response.parts[3].y == 0
        response = input_request(kind, text=b' ')
        assert response.parts[3].x == 0 and response.parts[0].width == before + 1
        configure(kind, enabled=0)
        assert input_request(kind, operation=7, focused=1).parts[3].x == 0
        response = input_request(kind, text=b' ')
        assert response.parts[0].width == before + 1
        results.append(dict(kind=kind, native_key_actions=1, focus_and_blur=True,
                            navigation_requests=2, disabled_actions=0, unfocused_actions=0))
        exchange(ControlRequest(magic=MAGIC, operation=6, process=0x494e5054, kind=kind, control=kind))
finally:
    connection.close()
args.output.parent.mkdir(exist_ok=True, parents=True)
args.output.write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results))
