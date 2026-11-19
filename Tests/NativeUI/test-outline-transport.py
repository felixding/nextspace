#!/usr/bin/env python3
"""Regression for the real shared request sequence slot in outline models."""
import ctypes as C
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'Experiments/ChromiumScrollers'))
sys.path.insert(0, str(ROOT/'Libraries/NativeUI/Bridge'))
from native_controls import ControlListRequest
from outlines import NativeOutlines


class Function:
    def __init__(self, callback): self.callback = callback
    def __call__(self, *args): return self.callback(*args)


class TransportTest(unittest.TestCase):
    def setUp(self):
        self.client = object()
        self.calls = []
        class Server:
            def _tracking(self, state): return False
            def _respond(inner, client, req, state=None, **reply): self.reply = reply
            def log(self, *args, **kwargs): pass
        self.server = Server()
        self.server.controls = {(23, 41, 18): dict(native=123, destroy=False, client=self.client, presentation=1)}
        self.server.native = type('Native', (), {})()
        self.server.native.nxs_control_outline_capabilities = Function(lambda: 1)
        def model(control, items, count):
            self.calls.append([(items[i].identifier, items[i].parent, items[i].flags, items[i].title) for i in range(count)])
            return 1
        self.server.native.nxs_control_outline_items = Function(model)
        self.transport = NativeOutlines(self.server, ControlListRequest)

    def packet(self):
        title = 'Root'.encode()
        body = struct.pack('<QQII', 7, 0, 3, len(title))+title
        req = ControlListRequest(magic=0x4e585549, operation=71, process=23, kind=18,
            control=41, text_size=len(body), reserved=173, count=1, scale=1)
        return bytes(req)+body

    def test_nonzero_shared_sequence_is_preserved(self):
        self.transport.message(self.client, self.packet())
        self.assertEqual(self.reply['input_result'], 1)
        self.assertEqual(self.calls, [[(7, 0, 3, b'Root')]])

    def test_wrong_owner_does_not_reach_native_model(self):
        self.transport.message(object(), self.packet())
        self.assertFalse(self.calls)
        self.assertNotIn('input_result', self.reply)

    def test_truncated_model_does_not_reach_native_model(self):
        self.transport.message(self.client, self.packet()[:-1])
        self.assertFalse(self.calls)


if __name__ == '__main__': unittest.main()
