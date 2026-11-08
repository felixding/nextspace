"""Bounded native action receipts; application data only. GPL-2.0-or-later."""
from collections import deque
import struct

HEADER = struct.Struct('<IIIIQQ')
ACTION = struct.Struct('<QIid')
LOST, BASELINE = 1, 2


class ActionLog:
    def __init__(self, serial, limit=256):
        self.floor = self.last = serial
        self.limit = limit
        self.events = deque()

    def append(self, serial, event, value, state):
        if serial != self.last+1:
            raise RuntimeError('Nonsequential native action receipt')
        self.last = serial
        self.events.append((serial, event, state, value))
        while len(self.events) > self.limit:
            self.floor = self.events.popleft()[0]

    def snapshot(self, after, baseline=False):
        if not 0 <= after <= self.last:
            raise ValueError('Invalid native action cursor')
        if baseline:
            after = self.last
        lost = after < self.floor
        while self.events and self.events[0][0] <= after:
            self.floor = self.events.popleft()[0]
        events = list(self.events)
        return HEADER.pack(HEADER.size, len(events), int(lost)*LOST+int(baseline)*BASELINE,
                           0, self.floor, self.last)+b''.join(ACTION.pack(*row) for row in events)
