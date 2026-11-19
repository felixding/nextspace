"""Owned hierarchy serialization for the shared native control host."""
import ctypes as C
import math
import struct


class OutlineItem(C.Structure):
    _fields_ = [('size', C.c_uint32), ('flags', C.c_uint32),
                ('identifier', C.c_uint64), ('parent', C.c_uint64), ('title', C.c_char_p)]


class NativeOutlines:
    def __init__(self, server, request_type):
        self.server, self.request_type = server, request_type
        native = server.native
        self.available = hasattr(native, 'nxs_control_outline_capabilities')
        if self.available:
            native.nxs_control_outline_capabilities.restype = C.c_uint
            self.available = bool(native.nxs_control_outline_capabilities())
        if self.available:
            native.nxs_control_outline_items.argtypes = [C.c_void_p, C.POINTER(OutlineItem), C.c_uint32]
            native.nxs_control_outline_items.restype = C.c_int

    def message(self, client, data):
        s = self.server
        if len(data) < C.sizeof(self.request_type):
            return
        req = self.request_type.from_buffer_copy(data)
        state = s.controls.get((req.process, req.control, req.kind))
        if (not self.available or req.magic != 0x4e585549 or req.operation != 71 or req.kind != 18
                or req.flags or req.key_cell or req.count > 4096
                or req.text_size != len(data)-C.sizeof(req) or req.text_size > 65536
                or not state or state['destroy'] or state['client'] is not client
                or s._tracking(state) or not math.isfinite(req.scale)
                or req.scale != state.get('presentation', 1)):
            s._respond(client, req)
            return
        offset = C.sizeof(req)
        items = (OutlineItem*req.count)()
        for index in range(req.count):
            if offset+24 > len(data):
                s._respond(client, req)
                return
            identifier, parent, flags, size = struct.unpack_from('<QQII', data, offset)
            offset += 24
            if flags & ~15 or offset+size > len(data):
                s._respond(client, req)
                return
            title = data[offset:offset+size]
            offset += size
            try:
                title.decode('utf-8')
            except UnicodeDecodeError:
                s._respond(client, req)
                return
            if b'\0' in title:
                s._respond(client, req)
                return
            items[index] = OutlineItem(C.sizeof(OutlineItem), flags, identifier, parent, title)
        accepted = offset == len(data) and s.native.nxs_control_outline_items(state['native'], items, req.count)
        signature = (req.scale, data[C.sizeof(req):])
        if accepted and state.get('outline_model') != signature:
            state['outline_model'] = signature
            s.log('native-outline-model', process=req.process, control=req.control, count=req.count)
        s._respond(client, req, state, input_result=int(bool(accepted)))
