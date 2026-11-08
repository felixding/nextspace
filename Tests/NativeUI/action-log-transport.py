#!/usr/bin/env python3
"""Native target/action receipts, cursors and real-process ownership."""
import argparse
import array
import ctypes as C
import json
import os
from pathlib import Path
import socket
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'Experiments/ChromiumScrollers'))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'Libraries/NativeUI/Bridge'))
from native_controls import ControlRequest, ControlActionsRequest, MAGIC
from helper import Response
from action_log import ActionLog, HEADER, ACTION, BASELINE, LOST

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--endpoint', required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
rows = []
cookie = 0xb1000000+(os.getpid()&0xffff)
assert cookie != os.getpid()


def check(name, value):
    rows.append(dict(case=name, passed=bool(value)))
    args.output.write_text(json.dumps(rows, indent=2)+'\n')
    print(json.dumps(rows[-1]), flush=True)
    assert value, name


def exchange(connection, request, descriptor=None):
    connection.sendmsg([bytes(request)], [(socket.SOL_SOCKET, socket.SCM_RIGHTS,
        array.array('i', [descriptor]))] if descriptor is not None else [])
    data = connection.recv(65536)
    response = Response.from_buffer_copy(data)
    assert response.magic == MAGIC and response.size == len(data)
    return response, data[C.sizeof(Response):]


def request(connection, operation, **values):
    model = ControlRequest(magic=MAGIC, operation=operation, process=cookie, kind=15, control=1)
    for name, value in values.items():
        setattr(model, name, value)
    return exchange(connection, model)


def actions(connection, after=0, subscribe=1, **values):
    model = ControlActionsRequest(magic=MAGIC, operation=63, process=cookie, kind=15,
                                  control=1, after=after, subscribe=subscribe)
    for name, value in values.items():
        setattr(model, name, value)
    response, payload = exchange(connection, model)
    if response.parts[3].x != 1 or not subscribe:
        return response, None, []
    size, count, flags, reserved, floor, last = HEADER.unpack_from(payload)
    assert size == HEADER.size and not reserved and len(payload) == size+count*ACTION.size
    events = [ACTION.unpack_from(payload, size+index*ACTION.size) for index in range(count)]
    return response, dict(count=count, flags=flags, floor=floor, last=last), events


def click(connection, y, expected):
    request(connection, 2, x=12, y=y)
    deadline = time.monotonic()+3
    while time.monotonic() < deadline:
        response, header, events = actions(connection)
        if header['last'] >= expected:
            break
        time.sleep(.01)
    else:
        raise AssertionError('The original NSStepper did not send its action')
    request(connection, 4, x=12, y=y)
    while time.monotonic() < deadline:
        if not request(connection, 5)[0].parts[0].y:
            return
        time.sleep(.01)
    raise AssertionError('Original native stepper tracking did not end')


with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as owner:
    owner.settimeout(10)
    owner.connect(args.endpoint)
    descriptor = os.eventfd(0, os.EFD_NONBLOCK | os.EFD_CLOEXEC)
    try:
        check('action-request-envelope-retains-legacy-size', C.sizeof(ControlActionsRequest) == C.sizeof(ControlRequest) == 104)
        check('original-native-stepper-created', request(owner, 1, width=24, height=26,
              minimum=-1000, maximum=1000, value=0, enabled=1)[0].width == 24)
        check('unregistered-action-subscription-rejected', actions(owner)[0].parts[3].x == 0)
        registration = ControlRequest(magic=MAGIC, operation=15, process=cookie)
        check('registered-cookie-is-distinct-from-kernel-pid', exchange(owner, registration, descriptor)[0].parts[3].x == 1)
        response, baseline, events = actions(owner)
        check('subscription-returns-explicit-baseline', baseline == dict(count=0, flags=BASELINE, floor=0, last=0) and not events)
        click(owner, 6, 1)
        upper = actions(owner)[1]['last']
        click(owner, 20, upper+1)
        response, snapshot, events = actions(owner)
        last = snapshot['last']
        check('opposite-original-native-actions-remain-ordered',
              last > upper >= 1 and [row[0] for row in events] == list(range(1,last+1))
              and all(row[1] == 2 for row in events)
              and [row[3] for row in events] == list(range(1,upper+1))+list(range(upper-1,2*upper-last-1,-1)))
        check('unacknowledged-receipts-can-be-read-again', actions(owner)[2] == events)
        check('cursor-acknowledges-receipts-without-replay', actions(owner, last)[1] == dict(count=0, flags=0, floor=last, last=last))
        check('acknowledged-history-loss-is-explicit', actions(owner)[1]['flags'] & LOST)
        check('future-cursor-rejected', actions(owner, last+1)[0].parts[3].x == 0)
        check('malformed-model-rejected', actions(owner, last, padding=1)[0].parts[3].x == 0)
        with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as stranger:
            stranger.settimeout(5)
            stranger.connect(args.endpoint)
            check('another-connection-cannot-read-receipts', actions(stranger, last)[0].parts[3].x == 0)
        reader, writer = os.pipe()
        child = os.fork()
        if not child:
            os.close(reader)
            try:
                denied = actions(owner, last)[0].parts[3].x == 0
                os.write(writer, b'1' if denied else b'0')
                os._exit(0)
            except BaseException:
                os._exit(1)
        os.close(writer)
        denied = os.read(reader, 1)
        os.close(reader)
        status = os.waitpid(child, 0)[1]
        check('inherited-socket-cannot-impersonate-registered-process', denied == b'1' and status == 0)
        check('owner-remains-authorized-after-child-denial', actions(owner, last)[0].parts[3].x == 1)
        check('owner-can-end-action-subscription', actions(owner, last, 0)[0].parts[3].x == 1)
        click_response = request(owner, 2, x=12, y=6)
        time.sleep(.04)
        request(owner, 4, x=12, y=6)
        deadline = time.monotonic()+3
        while time.monotonic() < deadline and request(owner, 5)[0].parts[0].y:
            time.sleep(.01)
        response, new_baseline, events = actions(owner)
        check('resubscription-does-not-replay-unobserved-actions',
              new_baseline['flags'] == BASELINE and new_baseline['last'] > last and not events)
        request(owner, 6)
        check('retired-control-has-no-action-capability', actions(owner)[0].parts[3].x == 0)
    finally:
        os.close(descriptor)

# Retention is a transport-data contract. No control or event is fabricated in
# the UI process to force exhaustion of the original native repeat loop.
log = ActionLog(0, limit=2)
for serial, value in enumerate([1, 0, -1], 1):
    log.append(serial, 2, value, 0)
header = HEADER.unpack_from(log.snapshot(0))
check('bounded-retention-reports-a-gap-and-current-serial', header[1] == 2 and header[2] == LOST and header[4:] == (1, 3))
